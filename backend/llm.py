"""Answer-generation providers.

Hosted APIs (Claude, ChatGPT, Gemini) and open-weight models run locally on a
GPU with Hugging Face Transformers. Each provider turns a system prompt and a
user prompt into answer text; `backend.main` builds the prompts.

SDKs are imported lazily so a missing package or API key only disables that
provider instead of breaking the app.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("afrisearch.llm")

# Room for the model's reasoning plus the answer; reasoning tokens count toward it.
API_MAX_TOKENS = 16000
LOCAL_MAX_NEW_TOKENS = int(os.getenv("AFRISEARCH_LOCAL_MAX_NEW_TOKENS", "512"))


class ProviderError(RuntimeError):
    """Generation failed in a way the user should see (refusal, empty output, ...)."""


@dataclass
class Provider:
    id: str
    label: str
    kind: str  # "api" or "local"
    model: str
    check: Callable[[], str | None]  # returns why the provider is unavailable, or None
    generate: Callable[[str, str], str]  # (system, prompt) -> answer text

    def unavailable_reason(self) -> str | None:
        try:
            return self.check()
        except Exception as exc:  # e.g. torch import failure
            return str(exc)

    def describe(self) -> dict[str, Any]:
        reason = self.unavailable_reason()
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "model": self.model,
            "available": reason is None,
            "reason": reason,
        }


def _missing_package(module: str, package: str) -> str | None:
    try:
        __import__(module)
    except ImportError:
        return f"Install the '{package}' package."
    return None


def _missing_env(*names: str) -> str | None:
    if any(os.getenv(name) for name in names):
        return None
    return f"Set {' or '.join(names)}."


_clients: dict[str, Any] = {}
_clients_lock = threading.Lock()


def _client(name: str, factory: Callable[[], Any]) -> Any:
    with _clients_lock:
        if name not in _clients:
            _clients[name] = factory()
        return _clients[name]


# --- Claude (Anthropic) -------------------------------------------------------

CLAUDE_MODEL = os.getenv("AFRISEARCH_CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = os.getenv("AFRISEARCH_CLAUDE_EFFORT", "medium")
# Models that accept server-side refusal fallbacks (`fallbacks: "default"`).
CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


def _claude_check() -> str | None:
    return _missing_package("anthropic", "anthropic") or _missing_env(
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"
    )


def _claude_generate(system: str, prompt: str) -> str:
    import anthropic

    client = _client("claude", anthropic.Anthropic)
    request: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "max_tokens": API_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": CLAUDE_EFFORT},
    }
    if CLAUDE_MODEL in CLAUDE_FALLBACK_MODELS:
        # If a safety classifier declines, the API retries on Anthropic's
        # recommended fallback model instead of returning the refusal.
        request["betas"] = ["server-side-fallback-2026-07-01"]
        request["fallbacks"] = "default"
    response = client.beta.messages.create(**request)

    if response.stop_reason == "refusal":
        raise ProviderError("Claude declined to answer this question.")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise ProviderError(f"Claude returned no text (stop reason: {response.stop_reason}).")
    return text


# --- ChatGPT (OpenAI) ---------------------------------------------------------

OPENAI_MODEL = os.getenv("AFRISEARCH_OPENAI_MODEL", "gpt-6.1-sol")


def _openai_check() -> str | None:
    return _missing_package("openai", "openai") or _missing_env("OPENAI_API_KEY")


def _openai_generate(system: str, prompt: str) -> str:
    import openai

    client = _client("openai", openai.OpenAI)
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=system,
        input=prompt,
        max_output_tokens=API_MAX_TOKENS,
    )
    text = (response.output_text or "").strip()
    if not text:
        raise ProviderError(f"ChatGPT returned no text (status: {response.status}).")
    return text


# --- Gemini (Google) ----------------------------------------------------------

GEMINI_MODEL = os.getenv("AFRISEARCH_GEMINI_MODEL", "gemini-4-argon")


def _gemini_check() -> str | None:
    return _missing_package("google.genai", "google-genai") or _missing_env(
        "GEMINI_API_KEY", "GOOGLE_API_KEY"
    )


def _gemini_generate(system: str, prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = _client("gemini", genai.Client)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=API_MAX_TOKENS,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise ProviderError("Gemini returned no text (the response may have been blocked).")
    return text


# --- Local open-weight models (Transformers, GPU) -----------------------------

@dataclass
class LocalModelSpec:
    model_id: str
    multimodal: bool  # loaded with AutoModelForImageTextToText + AutoProcessor
    template_kwargs: dict[str, Any]  # extra chat-template options
    quantizable: bool  # can be loaded in 4-bit with bitsandbytes
    parse: Callable[[str], str] | None = None  # cleans raw decoded output
    cpu_ok: bool = False  # small enough to run without a GPU
    max_new_tokens: int = LOCAL_MAX_NEW_TOKENS


def _gpt_oss_final(raw: str) -> str:
    """gpt-oss writes reasoning to an 'analysis' channel; keep only the 'final' one."""
    marker = "<|channel|>final<|message|>"
    if marker in raw:
        raw = raw.rsplit(marker, 1)[1]
    return re.sub(r"<\|[^|]+\|>", "", raw).strip()


LOCAL_SPECS = {
    # The original starter model: small enough for a laptop CPU, weaker answers.
    "qwen-small": LocalModelSpec(
        model_id=os.getenv("AFRISEARCH_SMALL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"),
        multimodal=False,
        template_kwargs={},
        quantizable=False,
        cpu_ok=True,
        max_new_tokens=220,
    ),
    "qwen": LocalModelSpec(
        model_id=os.getenv("AFRISEARCH_QWEN_MODEL", "Qwen/Qwen3.8-27B"),
        multimodal=True,
        template_kwargs={"enable_thinking": False},
        quantizable=True,
    ),
    "gemma": LocalModelSpec(
        model_id=os.getenv("AFRISEARCH_GEMMA_MODEL", "google/gemma-4-26B-A4B-it"),
        multimodal=True,
        template_kwargs={"enable_thinking": False},
        quantizable=True,
    ),
    "gpt-oss": LocalModelSpec(
        model_id=os.getenv("AFRISEARCH_GPT_OSS_MODEL", "openai/gpt-oss-20b"),
        multimodal=False,
        template_kwargs={"reasoning_effort": "low"},
        quantizable=False,  # ships already quantized (MXFP4)
        parse=_gpt_oss_final,
    ),
}

# "4bit" roughly quarters GPU memory for Qwen and Gemma (needs bitsandbytes).
LOCAL_QUANTIZE = os.getenv("AFRISEARCH_LOCAL_QUANTIZE", "").lower()
ALLOW_CPU = os.getenv("AFRISEARCH_ALLOW_CPU", "") == "1"

# Only one local model stays loaded, so switching models frees GPU memory first.
_local_lock = threading.Lock()
_local_loaded: dict[str, Any] = {"key": None, "processor": None, "model": None}


def _local_checker(key: str) -> Callable[[], str | None]:
    spec = LOCAL_SPECS[key]

    def check() -> str | None:
        reason = _missing_package("torch", "torch") or _missing_package("transformers", "transformers")
        if reason:
            return reason
        import torch

        if not torch.cuda.is_available() and not (spec.cpu_ok or ALLOW_CPU):
            return "No CUDA GPU detected (set AFRISEARCH_ALLOW_CPU=1 to run on CPU anyway)."
        return None

    return check


def _load_local(key: str):
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoModelForImageTextToText,
        AutoProcessor,
        AutoTokenizer,
    )

    if _local_loaded["key"] == key:
        return _local_loaded["processor"], _local_loaded["model"]

    if _local_loaded["model"] is not None:
        logger.info("Unloading %s", _local_loaded["key"])
        _local_loaded.update(key=None, processor=None, model=None)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    spec = LOCAL_SPECS[key]
    kwargs: dict[str, Any] = {"dtype": "auto", "device_map": "auto"}
    if not torch.cuda.is_available():
        # Most laptop CPUs have no fast bfloat16 math; float32 is several times faster.
        kwargs["dtype"] = torch.float32
    if LOCAL_QUANTIZE == "4bit" and spec.quantizable:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16
        )

    logger.info("Loading %s", spec.model_id)
    if spec.multimodal:
        processor = AutoProcessor.from_pretrained(spec.model_id)
        model = AutoModelForImageTextToText.from_pretrained(spec.model_id, **kwargs)
    else:
        processor = AutoTokenizer.from_pretrained(spec.model_id)
        model = AutoModelForCausalLM.from_pretrained(spec.model_id, **kwargs)
    model.eval()
    _local_loaded.update(key=key, processor=processor, model=model)
    return processor, model


def _local_generator(key: str) -> Callable[[str, str], str]:
    spec = LOCAL_SPECS[key]

    def generate(system: str, prompt: str) -> str:
        import torch

        def content(text: str) -> Any:
            # Multimodal processors expect a list of typed parts.
            return [{"type": "text", "text": text}] if spec.multimodal else text

        messages = [
            {"role": "system", "content": content(system)},
            {"role": "user", "content": content(prompt)},
        ]
        # The lock covers loading and generation: one model, one request at a time.
        with _local_lock:
            processor, model = _load_local(key)
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                **spec.template_kwargs,
            ).to(model.device)
            with torch.no_grad():
                output = model.generate(
                    **inputs,
                    max_new_tokens=spec.max_new_tokens,
                    do_sample=False,
                    repetition_penalty=1.05,
                )
        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        if spec.parse:
            text = spec.parse(processor.decode(new_tokens, skip_special_tokens=False))
        else:
            text = processor.decode(new_tokens, skip_special_tokens=True).strip()
        if not text:
            raise ProviderError(f"{spec.model_id} returned no text.")
        return text

    return generate


PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in [
        Provider("claude", "Claude (Anthropic)", "api", CLAUDE_MODEL, _claude_check, _claude_generate),
        Provider("chatgpt", "ChatGPT (OpenAI)", "api", OPENAI_MODEL, _openai_check, _openai_generate),
        Provider("gemini", "Gemini (Google)", "api", GEMINI_MODEL, _gemini_check, _gemini_generate),
        Provider("qwen", "Qwen 3.8 (local GPU)", "local", LOCAL_SPECS["qwen"].model_id,
                 _local_checker("qwen"), _local_generator("qwen")),
        Provider("gemma", "Gemma 4 (local GPU)", "local", LOCAL_SPECS["gemma"].model_id,
                 _local_checker("gemma"), _local_generator("gemma")),
        Provider("gpt-oss", "gpt-oss (local GPU)", "local", LOCAL_SPECS["gpt-oss"].model_id,
                 _local_checker("gpt-oss"), _local_generator("gpt-oss")),
        Provider("qwen-small", "Qwen 2.5 0.5B (local, runs on CPU)", "local",
                 LOCAL_SPECS["qwen-small"].model_id,
                 _local_checker("qwen-small"), _local_generator("qwen-small")),
    ]
}

DEFAULT_PROVIDER = os.getenv("AFRISEARCH_DEFAULT_PROVIDER", "")


def default_provider() -> str | None:
    """The configured default if usable, else the first available provider."""
    if DEFAULT_PROVIDER in PROVIDERS and PROVIDERS[DEFAULT_PROVIDER].unavailable_reason() is None:
        return DEFAULT_PROVIDER
    return next((p.id for p in PROVIDERS.values() if p.unavailable_reason() is None), None)


def generate(provider_id: str, system: str, prompt: str) -> str:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise KeyError(provider_id)
    reason = provider.unavailable_reason()
    if reason:
        raise ProviderError(f"{provider.label} is not available: {reason}")
    return provider.generate(system, prompt)
