"""
Tests for the small LLM client (Brick 6).

No real network/API calls are ever made. Gemini calls are tested by
monkeypatching the `genai` module reference inside the client; Nemotron
calls are tested by monkeypatching `httpx.post`.
"""

from __future__ import annotations

import httpx
import pytest

from services import small_llm_client as client


class _FakeGeminiResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeGeminiModel:
    def __init__(self, response_text: str, raise_error: Exception | None = None):
        self._response_text = response_text
        self._raise_error = raise_error

    def generate_content(self, prompt, generation_config=None):
        if self._raise_error:
            raise self._raise_error
        return _FakeGeminiResponse(self._response_text)


class _FakeGenaiModule:
    """Stand-in for google.generativeai, matching the small surface the client uses."""

    def __init__(self, response_text: str = "{}", raise_error: Exception | None = None):
        self.configured_with_key = None
        self._response_text = response_text
        self._raise_error = raise_error
        self.types = client.genai.types  # reuse real types module for GenerationConfig

    def configure(self, api_key):
        self.configured_with_key = api_key

    def GenerativeModel(self, model_name):  # noqa: N802 - matching real SDK's naming
        return _FakeGeminiModel(self._response_text, self._raise_error)


def test_parse_json_response_handles_plain_json():
    result = client._parse_json_response('{"a": 1, "b": [2, 3]}')
    assert result == {"a": 1, "b": [2, 3]}


def test_parse_json_response_strips_markdown_code_fences():
    raw = '```json\n{"a": 1}\n```'
    result = client._parse_json_response(raw)
    assert result == {"a": 1}


def test_parse_json_response_raises_on_invalid_json():
    with pytest.raises(client.SmallLlmClientError):
        client._parse_json_response("this is not json at all")


def test_parse_json_response_raises_when_top_level_is_not_an_object():
    with pytest.raises(client.SmallLlmClientError):
        client._parse_json_response("[1, 2, 3]")


def test_call_gemini_raises_when_api_key_missing():
    with pytest.raises(client.SmallLlmClientError, match="No Gemini API key"):
        client._call_gemini(api_key="", model_name="gemini-2.0-flash-lite", prompt="hi", temperature=0.3)


def test_call_gemini_returns_text_on_success(monkeypatch):
    fake_genai = _FakeGenaiModule(response_text='{"ok": true}')
    monkeypatch.setattr(client, "genai", fake_genai)

    result = client._call_gemini(api_key="fake-key", model_name="gemini-2.0-flash-lite", prompt="hi", temperature=0.3)

    assert result == '{"ok": true}'
    assert fake_genai.configured_with_key == "fake-key"


def test_call_gemini_wraps_sdk_errors(monkeypatch):
    fake_genai = _FakeGenaiModule(raise_error=RuntimeError("quota exceeded"))
    monkeypatch.setattr(client, "genai", fake_genai)

    with pytest.raises(client.SmallLlmClientError, match="quota exceeded"):
        client._call_gemini(api_key="fake-key", model_name="gemini-2.0-flash-lite", prompt="hi", temperature=0.3)


def test_call_gemini_raises_on_empty_response(monkeypatch):
    fake_genai = _FakeGenaiModule(response_text="")
    monkeypatch.setattr(client, "genai", fake_genai)

    with pytest.raises(client.SmallLlmClientError, match="empty response"):
        client._call_gemini(api_key="fake-key", model_name="gemini-2.0-flash-lite", prompt="hi", temperature=0.3)


def test_call_nemotron_raises_when_api_key_missing():
    with pytest.raises(client.SmallLlmClientError, match="No NVIDIA API key"):
        client._call_nemotron(api_key="", model_name="nemotron", prompt="hi", temperature=0.3)


def test_call_nemotron_returns_content_on_success(monkeypatch):
    def fake_post(url, headers, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
            request=request,
        )

    monkeypatch.setattr(client.httpx, "post", fake_post)

    result = client._call_nemotron(api_key="fake-key", model_name="nemotron-4", prompt="hi", temperature=0.3)
    assert result == '{"ok": true}'


def test_call_nemotron_raises_on_http_error(monkeypatch):
    def fake_post(url, headers, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(500, json={"error": "server error"}, request=request)

    monkeypatch.setattr(client.httpx, "post", fake_post)

    with pytest.raises(client.SmallLlmClientError, match="Nemotron API call failed"):
        client._call_nemotron(api_key="fake-key", model_name="nemotron-4", prompt="hi", temperature=0.3)


def test_call_nemotron_raises_on_unexpected_response_shape(monkeypatch):
    def fake_post(url, headers, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(client.httpx, "post", fake_post)

    with pytest.raises(client.SmallLlmClientError, match="Unexpected Nemotron response shape"):
        client._call_nemotron(api_key="fake-key", model_name="nemotron-4", prompt="hi", temperature=0.3)


def test_generate_json_response_routes_to_gemini_by_default(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "small_llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key")

    fake_genai = _FakeGenaiModule(response_text='{"result": "ok"}')
    monkeypatch.setattr(client, "genai", fake_genai)

    result = client.generate_json_response_from_small_llm("test prompt")
    assert result == {"result": "ok"}


def test_generate_json_response_raises_for_unsupported_provider(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "small_llm_provider", "some_unknown_provider")

    with pytest.raises(client.SmallLlmClientError, match="Unsupported small_llm_provider"):
        client.generate_json_response_from_small_llm("test prompt")
