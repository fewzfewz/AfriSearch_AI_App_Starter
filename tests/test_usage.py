"""Tokens and estimated cost of hosted-model answers, per workspace."""
import json

import pytest

from backend import db, llm
from conftest import SOLAR_GUIDE, upload

QUESTION = {"question": "How often should solar panels be cleaned?", "save": True}


@pytest.fixture
def billed_model(fake_model, monkeypatch):
    """The fake provider reports 1000 input and 200 output tokens per answer, as a priced model."""
    def generate(system, prompt):
        llm._record(1000, 200)
        return fake_model.answer

    def stream(system, prompt):
        yield "Clean them "
        llm._record(1000, 200)
        yield "every month [S1]."

    provider = llm.PROVIDERS["fake"]
    monkeypatch.setattr(provider, "generate", generate)
    monkeypatch.setattr(provider, "stream", stream)
    monkeypatch.setattr(provider, "model", "claude-opus-5-5")  # $4 / $20 per million tokens
    return provider


@pytest.fixture
def indexed(client):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    return client


COST = (1000 * 4 + 200 * 20) / 1_000_000  # 0.008


def test_answers_record_tokens_and_cost(indexed, billed_model):
    answer = indexed.post("/ask", json=QUESTION).json()
    message = indexed.get(f"/chats/{answer['chat_id']}").json()["messages"][1]
    assert message["data"]["usage"] == {"input_tokens": 1000, "output_tokens": 200, "cost_usd": COST}

    lines = indexed.post("/ask/stream", json=QUESTION).text.splitlines()
    assert json.loads(lines[-1])["type"] == "done"

    usage = indexed.get("/insights").json()["usage"]
    assert usage["answers"] == 2
    assert (usage["input_tokens"], usage["output_tokens"]) == (2000, 400)
    assert usage["cost_usd"] == pytest.approx(2 * COST)
    assert usage["models"][0]["model"] == "claude-opus-5-5"


def test_unknown_prices_count_tokens_without_cost(indexed, billed_model, monkeypatch):
    monkeypatch.setattr(billed_model, "model", "some-new-model")
    indexed.post("/ask", json=QUESTION)
    usage = indexed.get("/insights").json()["usage"]
    assert usage["input_tokens"] == 1000 and usage["cost_usd"] is None and usage["unpriced_answers"] == 1

    monkeypatch.setenv("AFRISEARCH_MODEL_PRICES", "some-new-model=1/2, broken=x")
    indexed.post("/ask", json=QUESTION)
    assert indexed.get("/insights").json()["usage"]["cost_usd"] == pytest.approx((1000 * 1 + 200 * 2) / 1e6)


def test_local_models_and_canned_answers_cost_nothing(indexed, fake_model):
    indexed.post("/ask", json=QUESTION)  # the plain fake model reports no tokens
    indexed.post("/ask", json={"question": "Rais wa kwanza wa Tanzania alikuwa nani?"})
    assert indexed.get("/insights").json()["usage"]["answers"] == 0


def test_refusals_still_count(indexed, billed_model, monkeypatch):
    def refuse(system, prompt):
        llm._record(1000, 3)
        raise llm.ProviderError("Declined.")

    monkeypatch.setattr(billed_model, "generate", refuse)
    assert indexed.post("/ask", json=QUESTION).status_code == 400
    assert indexed.get("/insights").json()["usage"]["input_tokens"] == 1000


def test_usage_stays_with_the_workspace_after_account_deletion(indexed, billed_model):
    indexed.post("/ask", json=QUESTION)
    db.delete_user("local")
    with db.connect() as conn:
        assert [row["user_id"] for row in conn.execute("SELECT user_id FROM usage")] == [""]
