"""Asking questions through /ask, with a fake answer model."""
import pytest

from backend import llm
from conftest import SOLAR_GUIDE, upload


@pytest.fixture
def indexed(client):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    return client


def ask(client, question, **extra):
    return client.post("/ask", json={"question": question, **extra})


def test_asking_before_indexing_fails(client, fake_model):
    assert ask(client, "How often should panels be cleaned?").status_code == 400


def test_relevant_question_gets_a_cited_answer(indexed, fake_model):
    response = ask(indexed, "How often should solar panels be cleaned?")
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Clean them every month [S1]."
    assert body["provider"] == "fake"
    assert body["model"] == "fake-1"
    assert body["sources"][0]["label"] == "S1"
    assert body["sources"][0]["source_name"] == "guide.txt"

    system, prompt = fake_model.prompts[0]
    assert "[S1] (from guide.txt)" in prompt
    assert "How often should solar panels be cleaned?" in prompt


def test_citations_to_missing_sources_are_removed(indexed, fake_model):
    fake_model.answer = "Monthly [S1] [S7]."
    body = ask(indexed, "How often should solar panels be cleaned?").json()
    assert body["answer"] == "Monthly [S1]."
    assert body["removed_citations"] == ["S7"]


def test_unrelated_question_skips_the_model(indexed, fake_model):
    body = ask(indexed, "zebra quantum violin").json()
    assert body["sources"] == []
    assert "do not contain passages relevant enough" in body["answer"]
    assert fake_model.prompts == []


def test_retrieval_only_request_returns_no_answer(indexed, fake_model):
    body = ask(indexed, "How often should solar panels be cleaned?", generate_answer=False).json()
    assert body["answer"] is None
    assert body["provider"] is None
    assert body["sources"]


def test_unknown_provider_is_rejected(indexed, fake_model):
    response = ask(indexed, "How often should solar panels be cleaned?", provider="nope")
    assert response.status_code == 400


def test_unavailable_provider_reports_why(indexed, fake_model):
    fake_model.unavailable = "Set FAKE_API_KEY."
    response = ask(indexed, "How often should solar panels be cleaned?", provider="fake")
    assert response.status_code == 400
    assert "Set FAKE_API_KEY." in response.json()["detail"]


def test_model_refusal_is_a_client_error(indexed, fake_model):
    fake_model.error = llm.ProviderError("Claude declined to answer this question.")
    response = ask(indexed, "How often should solar panels be cleaned?")
    assert response.status_code == 400
    assert "declined" in response.json()["detail"]


def test_unexpected_model_failure_is_a_gateway_error(indexed, fake_model):
    fake_model.error = RuntimeError("rate limited")
    response = ask(indexed, "How often should solar panels be cleaned?")
    assert response.status_code == 502
    assert "rate limited" in response.json()["detail"]


def test_providers_endpoint_lists_models_and_default(client, fake_model):
    body = client.get("/providers").json()
    ids = {provider["id"] for provider in body["providers"]}
    assert {"claude", "chatgpt", "gemini", "qwen", "gemma", "gpt-oss", "qwen-small", "fake"} <= ids
    assert body["default"] == "fake"
