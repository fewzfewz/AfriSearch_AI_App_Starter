"""Reranking: reordering the best semantic matches with a cross-encoder."""
import pytest

from conftest import upload

GUIDES = [
    ("panels.txt", b"Solar panels should be cleaned every month with clean water."),
    ("battery.txt", b"Solar batteries should be kept off the floor. Panels and batteries need care."),
    ("inverter.txt", b"The inverter of solar panels should be inspected once a year."),
]


class FakeReranker:
    """Scores a passage by how many times it mentions the word 'battery'/'batteries'."""

    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] = []

    def predict(self, pairs, **kwargs):
        self.pairs.extend(pairs)
        return [text.lower().count("batter") for _, text in pairs]


@pytest.fixture
def reranked(client, app_env, monkeypatch):
    main, _ = app_env
    fake = FakeReranker()
    monkeypatch.setattr(main, "RERANKER_ID", "fake-reranker")
    monkeypatch.setattr(main, "reranker", fake)
    upload(client, *GUIDES)
    client.post("/documents/index")
    return main, fake


QUESTION = "How should solar panels be cleaned?"


def test_reranker_reorders_passages_but_keeps_semantic_scores(reranked):
    main, fake = reranked
    semantic = main.retrieve(QUESTION, top_k=3, rerank=False)
    results = main.retrieve(QUESTION, top_k=3)
    assert semantic[0]["source_name"] == "panels.txt"
    assert results[0]["source_name"] == "battery.txt"  # what the fake reranker prefers
    assert [r["rerank_score"] for r in results] == sorted((r["rerank_score"] for r in results), reverse=True)
    by_name = {r["source_name"]: r["score"] for r in semantic}
    assert all(r["score"] == by_name[r["source_name"]] for r in results)
    assert {question for question, _ in fake.pairs} == {QUESTION}


def test_reranker_sees_more_candidates_than_it_returns(reranked, monkeypatch):
    main, fake = reranked
    monkeypatch.setattr(main, "RERANK_CANDIDATES", 3)
    results = main.retrieve(QUESTION, top_k=1)
    assert len(fake.pairs) == 3
    assert [r["source_name"] for r in results] == ["battery.txt"]


def test_relevance_cutoff_applies_before_reranking(reranked):
    main, fake = reranked
    assert main.retrieve("Rais wa kwanza wa Tanzania alikuwa nani?") == []  # no shared words
    assert fake.pairs == []


def test_ask_can_skip_reranking(reranked, client, fake_model):
    _, fake = reranked
    response = client.post("/ask", json={"question": QUESTION, "rerank": False}).json()
    assert response["reranked"] is False
    assert response["sources"][0]["source_name"] == "panels.txt"
    assert response["sources"][0]["rerank_score"] is None
    assert fake.pairs == []

    response = client.post("/ask", json={"question": QUESTION}).json()
    assert response["reranked"] is True
    assert response["sources"][0]["source_name"] == "battery.txt"
    assert response["sources"][0]["rerank_score"] == 2


def test_without_a_reranker_requests_to_rerank_are_ignored(client, app_env, fake_model):
    upload(client, *GUIDES)
    client.post("/documents/index")
    response = client.post("/ask", json={"question": QUESTION, "rerank": True}).json()
    assert response["reranked"] is False
    assert client.get("/health").json()["reranker"] is None


@pytest.mark.parametrize("value, expected", [
    ("off", ""), ("", ""), ("none", ""), ("my/reranker", "my/reranker"),
])
def test_set_reranker(app_env, monkeypatch, value, expected):
    main, _ = app_env
    main.set_reranker(value)
    assert main.RERANKER_ID == expected
    assert main.reranker is None
