"""
Small LLM Client.

Thin wrapper around whichever provider is configured as the "small"
model (see SMALL_LLM_PROVIDER / SMALL_LLM_MODEL in .env). Used by the
non-reasoning services that still need an LLM call: Market Research
Service (Brick 6) and Information Extraction Service (Brick 7).

This client only knows how to send a prompt and get JSON back. It has
no opinion about what the prompt says or what the response means —
that judgment lives entirely in the calling service. It performs no
business reasoning itself.
"""

from __future__ import annotations

import json
import logging

import google.generativeai as genai
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

_NEMOTRON_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_NEMOTRON_REQUEST_TIMEOUT_SECONDS = 60.0


class SmallLlmClientError(RuntimeError):
    """Raised when the small LLM call fails or returns something unusable."""


def generate_json_response_from_small_llm(prompt: str, temperature: float = 0.3) -> dict:
    """
    Send a prompt to the configured small LLM and parse its response as a
    JSON object.

    Raises SmallLlmClientError on any failure: missing API key, network
    error, API error, or a response that isn't valid JSON. Callers are
    expected to catch this and degrade gracefully rather than let it
    crash the wider collection pipeline.
    """
    if settings.small_llm_provider == "gemini":
        raw_text = _call_gemini(
            api_key=settings.get_small_model_api_key(),
            model_name=settings.small_llm_model,
            prompt=prompt,
            temperature=temperature,
        )
    elif settings.small_llm_provider == "nemotron":
        raw_text = _call_nemotron(
            api_key=settings.get_small_model_api_key(),
            model_name=settings.small_llm_model,
            prompt=prompt,
            temperature=temperature,
        )
    else:
        raise SmallLlmClientError(f"Unsupported small_llm_provider: {settings.small_llm_provider!r}")

    return _parse_json_response(raw_text)


def _call_gemini(api_key: str, model_name: str, prompt: str, temperature: float) -> str:
    """Call the Gemini API with JSON response mode enabled. Returns the raw response text."""
    if not api_key:
        raise SmallLlmClientError(
            "No Gemini API key configured. Set GEMINI_API_KEY in your .env file."
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
    except Exception as error:  # noqa: BLE001 - any SDK/network failure should degrade gracefully
        raise SmallLlmClientError(f"Gemini API call failed: {error}") from error

    if not response.text:
        raise SmallLlmClientError("Gemini returned an empty response.")

    return response.text


def _call_nemotron(api_key: str, model_name: str, prompt: str, temperature: float) -> str:
    """Call the NVIDIA NIM (OpenAI-compatible) chat completions endpoint. Returns raw response text."""
    if not api_key:
        raise SmallLlmClientError(
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
            },
            timeout=_NEMOTRON_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SmallLlmClientError(f"Nemotron API call failed: {error}") from error

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise SmallLlmClientError(f"Unexpected Nemotron response shape: {data}") from error


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
        raise SmallLlmClientError(
            f"Small LLM response was not valid JSON: {error}. Raw response: {raw_text[:500]!r}"
        ) from error

    if not isinstance(parsed, dict):
        raise SmallLlmClientError(
            f"Small LLM response was valid JSON but not an object: {type(parsed).__name__}"
        )

    return parsed
