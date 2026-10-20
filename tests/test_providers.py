"""Answer providers in backend/llm.py.

The Claude, ChatGPT and Gemini tests call the real SDKs against a local mock
HTTP server, so they check the exact requests without API keys. Each one is
skipped when its SDK is not installed.
"""
from __future__ import annotations

import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend import llm


# --- Mock API server -------------------------------------------------------------

class MockAPI:
    """Records each request and answers with the response queued for its path."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.responses: dict[str, dict] = {}
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                api.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                key = next((k for k in api.responses if k in self.path), None)
                response = api.responses[key] if key else {}
                if isinstance(response, dict) and "__sse__" in response:
                    # A streaming response: server-sent events, as the real APIs send them.
                    lines = []
                    for name, data in response["__sse__"]:
                        if name:
                            lines.append(f"event: {name}")
                        lines.append(f"data: {json.dumps(data)}\n")
                    payload = ("\n".join(lines) + "\n").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                payload = json.dumps(response).encode()
                self.send_response(200 if key else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def last(self) -> dict:
        return self.requests[-1]


@pytest.fixture
def mock_api(monkeypatch):
    api = MockAPI()
    # Fresh SDK clients for each test; the providers create them on first use.
    monkeypatch.setattr(llm, "_clients", {})
    yield api
    api.server.shutdown()


def claude_message(*content, stop_reason="end_turn"):
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": llm.CLAUDE_MODEL,
        "content": list(content), "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


# --- Claude ------------------------------------------------------------------------

@pytest.fixture
def claude(mock_api):
    anthropic = pytest.importorskip("anthropic")
    llm._clients["claude"] = anthropic.Anthropic(api_key="test", base_url=mock_api.url, max_retries=0)
    return mock_api


def test_claude_request_uses_effort_and_refusal_fallback(claude, monkeypatch):
    monkeypatch.setattr(llm, "CLAUDE_MODEL", "claude-opus-5-5")
    claude.responses["/v1/messages"] = claude_message(
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "Monthly [S1]."},
    )
    usage = llm.Usage()
    token = llm._usage.set(usage)
    try:
        assert llm._claude_generate("Be accurate.", "Question?") == "Monthly [S1]."
    finally:
        llm._usage.reset(token)
    assert (usage.input_tokens, usage.output_tokens) == (10, 5)  # from the response's usage

    request = claude.last()
    assert request["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert request["body"]["fallbacks"] == "default"
    assert request["body"]["output_config"] == {"effort": llm.CLAUDE_EFFORT}
    assert request["body"]["system"] == "Be accurate."
    assert request["body"]["messages"] == [{"role": "user", "content": "Question?"}]


def test_claude_models_without_fallback_support_omit_it(claude, monkeypatch):
    monkeypatch.setattr(llm, "CLAUDE_MODEL", "claude-haiku-5-5")
    claude.responses["/v1/messages"] = claude_message({"type": "text", "text": "Monthly."})
    llm._claude_generate("system", "prompt")
    assert "fallbacks" not in claude.last()["body"]
    assert "anthropic-beta" not in claude.last()["headers"]


def test_claude_refusal_raises_provider_error(claude):
    claude.responses["/v1/messages"] = claude_message(stop_reason="refusal")
    with pytest.raises(llm.ProviderError, match="declined"):
        llm._claude_generate("system", "prompt")


def claude_stream(*texts, stop_reason="end_turn"):
    """The server-sent events of a streamed Claude answer."""
    message = {**claude_message(), "content": [], "stop_reason": None}
    events = [("message_start", {"type": "message_start", "message": message}),
              ("content_block_start", {"type": "content_block_start", "index": 0,
                                       "content_block": {"type": "text", "text": ""}})]
    events += [("content_block_delta", {"type": "content_block_delta", "index": 0,
                                        "delta": {"type": "text_delta", "text": text}}) for text in texts]
    events += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
               ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                  "usage": {"output_tokens": 5}}),
               ("message_stop", {"type": "message_stop"})]
    return {"__sse__": events}


def test_claude_streams_with_the_same_request(claude, monkeypatch):
    monkeypatch.setattr(llm, "CLAUDE_MODEL", "claude-opus-5-5")
    claude.responses["/v1/messages"] = claude_stream("Clean them ", "every month ", "[S1].")
    usage = llm.Usage()
    token = llm._usage.set(usage)
    try:
        assert list(llm._claude_stream("Be accurate.", "Question?")) == ["Clean them ", "every month ", "[S1]."]
    finally:
        llm._usage.reset(token)
    assert (usage.input_tokens, usage.output_tokens) == (10, 5)
    request = claude.last()
    assert request["body"]["stream"] is True
    assert request["body"]["fallbacks"] == "default"  # refusal fallback stays on when streaming
    assert request["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"


def test_claude_refusal_mid_stream_raises_after_the_partial_text(claude):
    claude.responses["/v1/messages"] = claude_stream("Partial ", stop_reason="refusal")
    pieces = []
    with pytest.raises(llm.ProviderError, match="declined"):
        for piece in llm._claude_stream("system", "prompt"):
            pieces.append(piece)
    assert pieces == ["Partial "]  # the caller is told to discard these


# --- ChatGPT -----------------------------------------------------------------------

def test_chatgpt_request_and_answer(mock_api):
    openai = pytest.importorskip("openai")
    llm._clients["openai"] = openai.OpenAI(api_key="test", base_url=f"{mock_api.url}/v1", max_retries=0)
    mock_api.responses["/v1/responses"] = {
        "id": "resp_1", "object": "response", "created_at": 0, "status": "completed",
        "model": llm.OPENAI_MODEL, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "output": [{
            "type": "message", "id": "m1", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": "Monthly [S1].", "annotations": []}],
        }],
    }
    assert llm._openai_generate("Be accurate.", "Question?") == "Monthly [S1]."
    body = mock_api.last()["body"]
    assert body["model"] == llm.OPENAI_MODEL
    assert body["instructions"] == "Be accurate."
    assert body["input"] == "Question?"
    assert body["max_output_tokens"] == llm.API_MAX_TOKENS


@pytest.fixture
def chatgpt(mock_api):
    openai = pytest.importorskip("openai")
    llm._clients["openai"] = openai.OpenAI(api_key="test", base_url=f"{mock_api.url}/v1", max_retries=0)
    return mock_api


def openai_stream(*texts, end="response.completed"):
    events = [("response.output_text.delta", {"type": "response.output_text.delta", "sequence_number": i,
                                               "item_id": "m1", "output_index": 0, "content_index": 0,
                                               "delta": text, "logprobs": []})
              for i, text in enumerate(texts)]
    events.append((end, {"type": end, "sequence_number": len(texts),
                         "response": {"id": "resp_1", "object": "response", "status": end.split(".")[-1]}}))
    return {"__sse__": events}


def test_chatgpt_streams(chatgpt):
    chatgpt.responses["/v1/responses"] = openai_stream("Monthly ", "[S1].")
    assert list(llm._openai_stream("Be accurate.", "Question?")) == ["Monthly ", "[S1]."]
    assert chatgpt.last()["body"]["stream"] is True


def test_chatgpt_failed_stream_raises(chatgpt):
    chatgpt.responses["/v1/responses"] = openai_stream("Mon", end="response.failed")
    with pytest.raises(llm.ProviderError, match="failed"):
        list(llm._openai_stream("system", "prompt"))


# --- Gemini ------------------------------------------------------------------------

@pytest.fixture
def gemini(mock_api):
    pytest.importorskip("google.genai")
    from google import genai
    from google.genai import types as genai_types

    llm._clients["gemini"] = genai.Client(
        api_key="test", http_options=genai_types.HttpOptions(base_url=mock_api.url)
    )
    return mock_api


def test_gemini_request_and_answer(gemini):
    gemini.responses[":generateContent"] = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "Monthly [S1]."}]},
                        "finishReason": "STOP"}],
    }
    assert llm._gemini_generate("Be accurate.", "Question?") == "Monthly [S1]."
    request = gemini.last()
    assert f"/models/{llm.GEMINI_MODEL}:generateContent" in request["path"]
    assert request["body"]["systemInstruction"]["parts"][0]["text"] == "Be accurate."
    assert request["body"]["generationConfig"]["maxOutputTokens"] == llm.API_MAX_TOKENS


def test_gemini_streams(gemini):
    gemini.responses[":streamGenerateContent"] = {"__sse__": [
        (None, {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]})
        for text in ("Monthly ", "[S1].")
    ]}
    assert list(llm._gemini_stream("Be accurate.", "Question?")) == ["Monthly ", "[S1]."]
    assert ":streamGenerateContent" in gemini.last()["path"]


def test_gemini_blocked_response_raises_provider_error(gemini):
    gemini.responses[":generateContent"] = {"candidates": [{"finishReason": "SAFETY"}]}
    with pytest.raises(llm.ProviderError, match="no text"):
        llm._gemini_generate("system", "prompt")


# --- Availability and selection ----------------------------------------------------

def test_api_provider_needs_its_key(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", types.ModuleType("openai"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.PROVIDERS["chatgpt"].unavailable_reason() == "Set OPENAI_API_KEY."
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert llm.PROVIDERS["chatgpt"].unavailable_reason() is None


def test_api_provider_needs_its_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` fail
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert llm.PROVIDERS["claude"].unavailable_reason() == "Install the 'anthropic' package."


def fake_torch(has_gpu: bool) -> types.ModuleType:
    module = types.ModuleType("torch")
    module.cuda = types.SimpleNamespace(is_available=lambda: has_gpu)
    return module


def test_without_gpu_only_the_small_local_model_is_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", fake_torch(has_gpu=False))
    monkeypatch.setitem(sys.modules, "transformers", types.ModuleType("transformers"))
    monkeypatch.setattr(llm, "ALLOW_CPU", False)
    assert llm.PROVIDERS["qwen-small"].unavailable_reason() is None
    for provider_id in ("qwen", "gemma", "gpt-oss"):
        assert "No CUDA GPU" in llm.PROVIDERS[provider_id].unavailable_reason()


def test_with_gpu_all_local_models_are_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", fake_torch(has_gpu=True))
    monkeypatch.setitem(sys.modules, "transformers", types.ModuleType("transformers"))
    for provider_id in ("qwen", "gemma", "gpt-oss", "qwen-small"):
        assert llm.PROVIDERS[provider_id].unavailable_reason() is None


def test_default_provider_falls_back_to_first_available(monkeypatch):
    def provider(provider_id, reason):
        return llm.Provider(provider_id, provider_id, "api", "m", lambda: reason, lambda s, p: "")

    monkeypatch.setattr(llm, "PROVIDERS", {
        "a": provider("a", "Set A_KEY."),
        "b": provider("b", None),
        "c": provider("c", None),
    })
    monkeypatch.setattr(llm, "DEFAULT_PROVIDER", "c")
    assert llm.default_provider() == "c"
    monkeypatch.setattr(llm, "DEFAULT_PROVIDER", "a")  # configured but unavailable
    assert llm.default_provider() == "b"
    monkeypatch.setattr(llm, "DEFAULT_PROVIDER", "")
    assert llm.default_provider() == "b"


def test_generate_rejects_unknown_provider():
    with pytest.raises(KeyError):
        llm.generate("does-not-exist", "system", "prompt")


@pytest.mark.parametrize("raw, expected", [
    ("<|channel|>analysis<|message|>Thinking...<|end|><|start|>assistant"
     "<|channel|>final<|message|>Monthly [S1].<|return|>", "Monthly [S1]."),
    ("Plain answer<|return|>", "Plain answer"),
])
def test_gpt_oss_output_keeps_only_the_final_answer(raw, expected):
    assert llm._gpt_oss_final(raw) == expected
