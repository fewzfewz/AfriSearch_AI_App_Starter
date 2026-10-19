"""Shared fixtures.

Tests run against a temporary data directory with a fake embedder and a fake
answer model, so they need no model downloads, API keys or GPU, and never touch
the real data/ folder.
"""
from __future__ import annotations

import os
import re
import tempfile
import zlib
from typing import Any

# Before the backend is imported: anything that escapes a test's own temporary
# folder still lands in a throwaway directory, never in the real data/ folder.
os.environ["AFRISEARCH_DATA_DIR"] = tempfile.mkdtemp(prefix="afrisearch-tests-")

import numpy as np
import pytest


class FakeEmbedder:
    """Bag-of-words hashing: texts that share words get similar vectors."""

    dim = 256

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []  # one entry per batch (indexing) call
        self.texts: list[str] = []  # every text embedded, in order

    def encode(self, texts: Any, **kwargs: Any) -> np.ndarray:
        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        self.texts.extend(batch)
        if not single:
            self.batch_sizes.append(len(batch))
        vectors = np.zeros((len(batch), self.dim), dtype=np.float32)
        for row, text in enumerate(batch):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vectors[row, zlib.crc32(word.encode()) % self.dim] += 1
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors /= norms
        return vectors[0] if single else vectors


class Env:
    """The test app: a fake embedder, and the default workspace of the local user."""

    def __init__(self, embedder: FakeEmbedder) -> None:
        self.embedder = embedder

    @property
    def workspace_id(self) -> str:
        from backend import main
        from backend.auth import current_user

        # current_user() records the user, as on any request, before workspaces are made.
        return main.user_workspaces(current_user(None))[0]["id"]

    @property
    def store(self):
        from backend import store

        return store.get_store(self.workspace_id)


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """The app pointed at an empty temporary data directory, with a fake embedder."""
    from backend import config, extract, models, store

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AUTH_MODE", "none")
    monkeypatch.setattr(store, "_stores", {})
    embedder = FakeEmbedder()
    monkeypatch.setattr(models, "embedder", embedder)
    # The fake embedder scores on a MiniLM-like scale, whatever the default model is.
    monkeypatch.setattr(models, "MIN_SCORE", 0.2)
    # No reranker unless a test installs a fake one (see test_reranker.py).
    monkeypatch.setattr(models, "RERANKER_ID", "")
    monkeypatch.setattr(models, "reranker", None)
    # OCR is unavailable unless a test installs a fake one (see test_ocr.py), so
    # results don't depend on whether Tesseract is installed on this machine.
    monkeypatch.setattr(extract, "ocr_status", lambda: ([], "Tesseract is not installed (test)."))
    return Env(embedder)


@pytest.fixture
def client(app_env):
    """An API client; paths are relative to /api."""
    from fastapi.testclient import TestClient

    from backend import main

    return TestClient(main.app, base_url="http://testserver/api")


class FakeModel:
    """Stands in for an answer model; records prompts and returns a canned answer."""

    def __init__(self) -> None:
        self.answer = "Clean them every month [S1]."
        self.error: Exception | None = None
        self.unavailable: str | None = None
        self.prompts: list[tuple[str, str]] = []

    def check(self) -> str | None:
        return self.unavailable

    def generate(self, system: str, prompt: str) -> str:
        self.prompts.append((system, prompt))
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def fake_model(monkeypatch):
    """Registers a 'fake' answer provider and makes it the default."""
    from backend import llm

    model = FakeModel()
    provider = llm.Provider("fake", "Fake model", "local", "fake-1", model.check, model.generate)
    monkeypatch.setitem(llm.PROVIDERS, "fake", provider)
    monkeypatch.setattr(llm, "DEFAULT_PROVIDER", "fake")
    return model


def upload(client, *files: tuple[str, bytes]):
    """POST files to /api/documents/upload and return the JSON response."""
    response = client.post(
        "/documents/upload",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )
    assert response.status_code == 200
    return response.json()


SOLAR_GUIDE = (
    b"Solar Panel Maintenance Guide. Solar panels should be cleaned every month to remove dust. "
    b"Dust can lower output by up to 25 percent. "
    b"Inverters should be inspected once a year by a qualified technician."
)
