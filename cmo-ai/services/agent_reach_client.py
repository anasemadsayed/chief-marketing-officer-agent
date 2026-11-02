"""
Agent-Reach Client — bridge between cmoAI and the Agent-Reach ecosystem.

Agent-Reach itself is not a Python library; it is a CLI routing layer
that installs and health-checks a set of upstream tools — each platform
has its own command:

    LinkedIn:  Jina Reader  (`curl https://r.jina.ai/<URL>`)
               or mcporter  (`mcporter call linkedin.get_person_profile ...`)
    Facebook:  OpenCLI      (`opencli facebook profile <handle> -f yaml`)
    Instagram: OpenCLI      (`opencli instagram profile <handle> -f yaml`)

This module wraps those CLI calls behind a single
`fetch_social_profile_via_agent_reach(platform, url)` function that
`social_media_collector_service.py` can call instead of (or before
falling back to) the plain `requests.get()` codepath.

The module is designed for **graceful degradation**: if Agent-Reach or
its upstream tools are not installed, every function returns
``(None, "... not installed ...")`` and the caller falls back to the OG
meta-tag scraping path that already exists.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Availability checks ─────────────────────────────────────────────

def _command_is_available(name: str) -> bool:
    """True if *name* exists on $PATH."""
    return shutil.which(name) is not None


def is_agent_reach_available() -> bool:
    """True if the ``agent-reach`` CLI is installed and on $PATH."""
    return _command_is_available("agent-reach")


import os
from pathlib import Path

# ── Availability and Path Resolution ────────────────────────────────

def _resolve_opencli_command() -> tuple[Optional[str], dict[str, str]]:
    """
    Find the opencli binary and build an execution environment with Node.js in $PATH.
    Returns (binary_path_or_command, env_dict).
    """
    env = os.environ.copy()
    
    # 1. Add node_binary_dir to PATH if configured
    node_dir = getattr(settings, "node_binary_dir", "").strip()
    if node_dir and os.path.isdir(node_dir):
        env["PATH"] = f"{node_dir}:{env.get('PATH', '')}"

    # 2. Check explicitly configured binary path
    configured_path = getattr(settings, "opencli_binary_path", "").strip()
    if configured_path and os.path.exists(configured_path):
        return configured_path, env

    # 3. Check common NVM / standard paths
    common_paths = [
        "/home/nas_mousa/.nvm/versions/node/v22.23.3/bin/opencli",
        os.path.expanduser("~/.local/bin/opencli"),
        "/usr/local/bin/opencli",
        "/usr/bin/opencli",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p, env

    # 4. Fallback to PATH lookup
    found = shutil.which("opencli", path=env.get("PATH"))
    if found:
        return found, env

    return None, env


def is_opencli_available() -> bool:
    """True if ``opencli`` is accessible either via settings or on $PATH."""
    bin_path, _ = _resolve_opencli_command()
    return bin_path is not None


def is_jina_reader_available() -> bool:
    """Jina Reader works through ``curl`` — always available on Linux."""
    return _command_is_available("curl")


# ── Platform-specific fetchers ───────────────────────────────────────

def _fetch_linkedin_via_jina_reader(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Use Jina Reader to convert a public LinkedIn URL into clean Markdown.

    Jina Reader is a free service at ``https://r.jina.ai/<URL>`` that
    renders a page in a headless browser and returns its visible content
    as Markdown — far better than a raw ``requests.get()`` against
    LinkedIn's login wall.

    Returns ``(content, None)`` on success, ``(None, error)`` on failure.
    """
    jina_url = f"https://r.jina.ai/{url}"
    logger.info("Fetching LinkedIn content via Jina Reader: %s", jina_url)

    try:
        result = subprocess.run(
            [
                "curl", "-sS",
                "-H", "Accept: text/markdown",
                "--max-time", str(settings.agent_reach_timeout_seconds),
                jina_url,
            ],
            capture_output=True,
            text=True,
            timeout=settings.agent_reach_timeout_seconds + 10,
        )
    except subprocess.TimeoutExpired:
        return None, "Jina Reader request timed out"
    except OSError as exc:
        return None, f"Failed to execute curl: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return None, f"curl exited with code {result.returncode}: {stderr}"

    content = result.stdout.strip()
    if not content:
        return None, "Jina Reader returned empty content (page may require login)"

    return content, None


def _fetch_linkedin_via_mcporter(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Use ``mcporter call linkedin.get_person_profile`` for richer data
    (requires LinkedIn MCP server to be configured via Agent-Reach).

    Falls back gracefully if mcporter or the LinkedIn server is not set up.
    """
    if not _command_is_available("mcporter"):
        return None, "mcporter is not installed"

    match = re.search(r"linkedin\.com/(?:in|company)/([^/?#]+)", url)
    if not match:
        return None, f"Could not extract LinkedIn username/slug from URL: {url}"

    username = match.group(1)
    is_company = "/company/" in url

    tool_name = "linkedin.get_company_profile" if is_company else "linkedin.get_person_profile"
    param_name = "company_username" if is_company else "linkedin_username"

    logger.info("Fetching LinkedIn content via mcporter: %s=%s", tool_name, username)

    try:
        result = subprocess.run(
            ["mcporter", "call", tool_name, f'{param_name}="{username}"'],
            capture_output=True,
            text=True,
            timeout=settings.agent_reach_timeout_seconds + 10,
        )
    except subprocess.TimeoutExpired:
        return None, "mcporter LinkedIn call timed out"
    except OSError as exc:
        return None, f"Failed to execute mcporter: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return None, f"mcporter exited with code {result.returncode}: {stderr}"

    content = result.stdout.strip()
    if not content:
        return None, "mcporter returned empty LinkedIn response"

    return content, None


def _fetch_facebook_via_opencli(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Use OpenCLI to fetch Facebook page profile and recent posts.
    """
    opencli_bin, exec_env = _resolve_opencli_command()
    if not opencli_bin:
        return None, "opencli is not installed or not found in configured path"

    match = re.search(r"facebook\.com/(?:pg/)?([^/?#]+)", url)
    if not match:
        return None, f"Could not extract Facebook handle from URL: {url}"

    handle = match.group(1).rstrip("/")
    if handle.lower() in ("profile.php",):
        return None, "Facebook numeric profile URLs are not supported by opencli"

    logger.info("Fetching Facebook content via opencli: handle=%s using bin=%s", handle, opencli_bin)

    outputs = []
    # 1. Fetch profile
    try:
        res_prof = subprocess.run(
            [opencli_bin, "facebook", "profile", handle, "-f", "yaml"],
            capture_output=True,
            text=True,
            env=exec_env,
            timeout=settings.agent_reach_timeout_seconds,
        )
        if res_prof.returncode == 0 and res_prof.stdout.strip():
            outputs.append(f"--- Facebook Profile ---\n{res_prof.stdout.strip()}")
    except Exception as exc:
        logger.warning("Facebook profile fetch failed: %s", exc)

    # 2. Try fetching posts / feed if available in opencli
    try:
        res_posts = subprocess.run(
            [opencli_bin, "facebook", "search", handle, "-f", "yaml"],
            capture_output=True,
            text=True,
            env=exec_env,
            timeout=settings.agent_reach_timeout_seconds,
        )
        if res_posts.returncode == 0 and res_posts.stdout.strip():
            outputs.append(f"--- Facebook Recent Activity & Search ---\n{res_posts.stdout.strip()}")
    except Exception as exc:
        logger.warning("Facebook activity fetch failed: %s", exc)

    if not outputs:
        return None, "opencli returned empty Facebook data"

    return "\n\n".join(outputs), None


def _fetch_instagram_via_opencli(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Use OpenCLI to fetch Instagram profile AND recent posts.
    """
    opencli_bin, exec_env = _resolve_opencli_command()
    if not opencli_bin:
        return None, "opencli is not installed or not found in configured path"

    match = re.search(r"instagram\.com/([^/?#]+)", url)
    if not match:
        return None, f"Could not extract Instagram handle from URL: {url}"

    handle = match.group(1).rstrip("/")
    if handle.lower() in ("p", "reel", "stories", "explore", "accounts"):
        return None, f"URL points to an Instagram {handle} page, not a profile"

    logger.info("Fetching Instagram content via opencli: handle=%s using bin=%s", handle, opencli_bin)

    outputs = []

    # 1. Fetch user recent posts (captions, engagement, dates) - this has the actual marketing substance!
    try:
        res_posts = subprocess.run(
            [opencli_bin, "instagram", "user", handle, "-f", "yaml"],
            capture_output=True,
            text=True,
            env=exec_env,
            timeout=settings.agent_reach_timeout_seconds,
        )
        if res_posts.returncode == 0 and res_posts.stdout.strip():
            outputs.append(f"--- Instagram Recent Posts & Captions ---\n{res_posts.stdout.strip()}")
        else:
            logger.info("opencli instagram user returned code=%d stderr=%s", res_posts.returncode, res_posts.stderr[:200])
    except Exception as exc:
        logger.warning("Instagram user posts fetch error: %s", exc)

    # 2. Fetch profile overview
    try:
        res_prof = subprocess.run(
            [opencli_bin, "instagram", "profile", handle, "-f", "yaml"],
            capture_output=True,
            text=True,
            env=exec_env,
            timeout=settings.agent_reach_timeout_seconds,
        )
        if res_prof.returncode == 0 and res_prof.stdout.strip():
            outputs.append(f"--- Instagram Profile Overview ---\n{res_prof.stdout.strip()}")
    except Exception as exc:
        logger.warning("Instagram profile fetch error: %s", exc)

    if not outputs:
        return None, "opencli returned empty Instagram response"

    return "\n\n".join(outputs), None


# ── Public dispatch function ────────────────────────────────────────

def fetch_social_profile_via_agent_reach(
    platform: str,
    url: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Attempt to fetch rich social media profile content using the
    Agent-Reach tool ecosystem.

    Args:
        platform: One of ``"linkedin"``, ``"facebook"``, ``"instagram"``.
        url:      The full profile URL to fetch.

    Returns:
        A ``(content, None)`` tuple on success, or ``(None, error_message)``
        on any failure (tool not installed, timeout, parse error, etc.).

    The caller (social_media_collector_service) should treat a failure
    here as non-fatal and fall back to its existing OG-meta-tag scraping.
    """
    platform_lower = platform.lower()

    if platform_lower == "linkedin":
        # Try mcporter first (richer data), fall back to Jina Reader.
        content, error = _fetch_linkedin_via_mcporter(url)
        if content:
            return content, None
        logger.info("mcporter LinkedIn unavailable (%s), trying Jina Reader", error)
        return _fetch_linkedin_via_jina_reader(url)

    if platform_lower == "facebook":
        return _fetch_facebook_via_opencli(url)

    if platform_lower == "instagram":
        return _fetch_instagram_via_opencli(url)

    return None, f"Unsupported Agent-Reach platform: {platform}"
