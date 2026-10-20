"""/ask/stream: sources first, then the answer in pieces, then the cleaned answer."""
import json

import pytest

from conftest import SOLAR_GUIDE, upload

QUESTION = {"question": "How often should solar panels be cleaned?"}


def events(response) -> list[dict]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


@pytest.fixture
def indexed(client):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    return client


@pytest.fixture
def streaming_model(fake_model, monkeypatch):
    """Gives the fake provider a stream function that yields `pieces`."""
    from backend import llm

    pieces = ["Clean the panels ", "every month ", "[S1, S9]."]
    calls = []

    def stream(system, prompt):
        calls.append(prompt)
        for piece in pieces:
            if isinstance(piece, Exception):
                raise piece
            yield piece

    monkeypatch.setattr(llm.PROVIDERS["fake"], "stream", stream)
    return pieces, calls


def test_streams_sources_then_pieces_then_cleaned_answer(indexed, streaming_model):
    pieces, calls = streaming_model
    result = events(indexed.post("/ask/stream", json=QUESTION))
    assert [e["type"] for e in result] == ["sources", "token", "token", "token", "done"]
    assert result[0]["sources"][0]["source_name"] == "guide.txt"
    assert result[0]["provider"] == "fake"
    assert "".join(e["text"] for e in result[1:4]) == "".join(pieces)
    assert result[-1]["answer"] == "Clean the panels every month [S1]."
    assert result[-1]["removed_citations"] == ["S9"]
    assert "SOURCE PASSAGES" in calls[0]


def test_providers_without_streaming_send_the_whole_answer(indexed, fake_model):
    result = events(indexed.post("/ask/stream", json=QUESTION))
    assert [e["type"] for e in result] == ["sources", "token", "done"]
    assert result[1]["text"] == fake_model.answer
    assert result[-1]["answer"] == fake_model.answer


def test_errors_during_generation_become_error_events(indexed, streaming_model):
    from backend import llm

    pieces, _ = streaming_model
    pieces[1:] = [llm.ProviderError("The model refused.")]
    result = events(indexed.post("/ask/stream", json=QUESTION))
    assert [e["type"] for e in result] == ["sources", "token", "error"]
    assert result[-1]["detail"] == "The model refused."
    assert result[-1]["discard_partial"] is True  # the streamed text was not a real answer


def test_unexpected_errors_name_the_provider(indexed, streaming_model):
    pieces, _ = streaming_model
    pieces[:] = [ConnectionError("network down")]
    result = events(indexed.post("/ask/stream", json=QUESTION))
    assert result[-1] == {"type": "error", "detail": "fake failed: network down", "discard_partial": False}


def test_no_relevant_passages(indexed, streaming_model):
    _, calls = streaming_model
    result = events(indexed.post("/ask/stream", json={"question": "Rais wa kwanza wa Tanzania alikuwa nani?"}))
    assert result[0]["sources"] == []
    from backend import answers

    assert result[-1]["answer"] == answers.CANNED["no_sources"]["sw"]  # the question is in Swahili
    assert calls == []  # the model is not asked


def test_search_only(indexed, streaming_model):
    result = events(indexed.post("/ask/stream", json={**QUESTION, "generate_answer": False}))
    assert [e["type"] for e in result] == ["sources", "done"]
    assert result[0]["provider"] is None
    assert result[-1]["answer"] is None


def test_problems_found_before_streaming_are_http_errors(client, indexed, fake_model):
    fake_model.unavailable = "Set FAKE_API_KEY."
    # Named explicitly: without a provider the app would fall back to another, real model.
    response = indexed.post("/ask/stream", json={**QUESTION, "provider": "fake"})
    assert response.status_code == 400
    assert "Set FAKE_API_KEY" in response.json()["detail"]

    assert indexed.post("/ask/stream", json={**QUESTION, "provider": "nope"}).status_code == 400


def test_nothing_indexed(client, fake_model):
    assert client.post("/ask/stream", json=QUESTION).status_code == 400
