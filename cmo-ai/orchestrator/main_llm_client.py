"""
Main LLM Client.

Thin wrapper around whichever provider is configured as the "main"
reasoning model (see MAIN_LLM_PROVIDER / GEMINI_MODEL / NEMOTRON_MODEL in
.env). Used exclusively by the Orchestrator for diagnosis, strategy, and
report generation — the only component in cmoAI allowed to reason about
the business.

Deliberately self-contained rather than sharing code with
services/small_llm_client.py: the orchestrator's LLM access stays
independent of the services package, matching the architecture rule
that only the orchestrator makes business decisions. The two clients
look similar because the underlying HTTP mechanics genuinely are
similar — that's a coincidence of infrastructure, not shared reasoning.
"""

from __future__ import annotations

import json
import logging

import google.generativeai as genai
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

_NEMOTRON_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_NEMOTRON_REQUEST_TIMEOUT_SECONDS = 90.0
_DEFAULT_MAX_OUTPUT_TOKENS = 3000


class MainLlmClientError(RuntimeError):
    """Raised when the main reasoning LLM call fails or returns something unusable."""


def generate_json_response_from_main_llm(
    prompt: str,
    temperature: float = 0.4,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict:
    """
    Send a prompt to the configured main reasoning LLM and parse its
    response as a JSON object.

    Raises MainLlmClientError on any failure: missing API key, network
    error, API error, or a response that isn't valid JSON. The
    orchestrator is expected to catch this and raise OrchestratorError
    rather than fabricate a result.
    """
    model_name = settings.gemini_model if settings.main_llm_provider == "gemini" else settings.nemotron_model

    if settings.main_llm_provider == "gemini":
        raw_text = _call_gemini(
            api_key=settings.get_main_reasoning_model_api_key(),
            model_name=model_name,
            prompt=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    elif settings.main_llm_provider == "nemotron":
        raw_text = _call_nemotron(
            api_key=settings.get_main_reasoning_model_api_key(),
            model_name=model_name,
            prompt=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    else:
        raise MainLlmClientError(f"Unsupported main_llm_provider: {settings.main_llm_provider!r}")

    return _parse_json_response(raw_text)


def _call_gemini(
    api_key: str, model_name: str, prompt: str, temperature: float, max_output_tokens: int
) -> str:
    """Call the Gemini API with JSON response mode enabled. Returns the raw response text."""
    if not api_key:
        raise MainLlmClientError(
            "No Gemini API key configured. Set GEMINI_API_KEY in your .env file."
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
            ),
        )
    except Exception as error:  # noqa: BLE001 - any SDK/network failure must not crash the pipeline
        raise MainLlmClientError(f"Gemini API call failed: {error}") from error

    if not response.text:
        raise MainLlmClientError("Gemini returned an empty response.")

    return response.text


def _call_nemotron(
    api_key: str, model_name: str, prompt: str, temperature: float, max_output_tokens: int
) -> str:
    """Call the NVIDIA NIM (OpenAI-compatible) chat completions endpoint. Returns raw response text."""
    if not api_key:
        raise MainLlmClientError(
            "No NVIDIA API key configured. Set NVIDIA_API_KEY in your .env file."
        )

    try:
        response = httpx.post(
            _NEMOTRON_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_output_tokens,
            },
            timeout=_NEMOTRON_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise MainLlmClientError(f"Nemotron API call failed: {error}") from error

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise MainLlmClientError(f"Unexpected Nemotron response shape: {data}") from error


def _parse_json_response(raw_text: str) -> dict:
    """
    Parse the model's raw text response as JSON, tolerating markdown code
    fences some models still add even when asked for JSON-only output.
    """
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise MainLlmClientError(
            f"Main LLM response was not valid JSON: {error}. Raw response: {raw_text[:500]!r}"
        ) from error

    if not isinstance(parsed, dict):
        raise MainLlmClientError(
            f"Main LLM response was valid JSON but not an object: {type(parsed).__name__}"
        )

    return parsed
