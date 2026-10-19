"""Saved chats, follow-up questions, background indexing, and when the model is asked."""
import json

import pytest

from backend import answers, jobs, models
from conftest import SOLAR_GUIDE, upload

QUESTION = "How often should solar panels be cleaned?"


@pytest.fixture
def indexed(client):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    return client


def stream(client, **body):
    return [json.loads(line) for line in client.post("/ask/stream", json=body).text.splitlines()]


def test_saved_questions_create_a_chat(indexed, fake_model):
    events = stream(indexed, question=QUESTION, save=True)
    chat_id = events[0]["chat_id"]
    assert chat_id and events[-1]["message_id"]

    chats = indexed.get("/chats").json()["chats"]
    assert [(c["id"], c["title"], c["questions"]) for c in chats] == [(chat_id, QUESTION, 1)]
    messages = indexed.get(f"/chats/{chat_id}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Clean them every month [S1]."
    assert messages[1]["data"]["sources"][0]["source_name"] == "guide.txt"
    assert messages[1]["data"]["provider"] == "fake"
    assert messages[1]["data"]["seconds"] is not None


def test_unsaved_questions_leave_no_chat(indexed, fake_model):
    assert stream(indexed, question=QUESTION)[0]["chat_id"] is None
    assert indexed.post("/ask", json={"question": QUESTION}).json()["message_id"] is None
    assert indexed.get("/chats").json()["chats"] == []


def test_follow_up_questions_use_the_conversation(indexed, fake_model, app_env):
    chat_id = stream(indexed, question=QUESTION, save=True)[0]["chat_id"]
    app_env.embedder.texts.clear()
    stream(indexed, question="What about it?", chat_id=chat_id)  # finds nothing on its own

    assert app_env.embedder.texts[-1].endswith(f"{QUESTION} What about it?")  # searched again with context
    _, prompt = fake_model.prompts[-1]
    assert "EARLIER IN THIS CONVERSATION" in prompt
    assert "Clean them every month" in prompt
    assert indexed.get("/chats").json()["chats"][0]["questions"] == 2


def test_new_topics_in_a_chat_are_searched_on_their_own(indexed, fake_model, app_env):
    chat_id = stream(indexed, question=QUESTION, save=True)[0]["chat_id"]
    app_env.embedder.texts.clear()
    stream(indexed, question="How often should inverters be inspected?", chat_id=chat_id)  # short, answerable alone
    assert len(app_env.embedder.texts) == 1
    assert app_env.embedder.texts[0].endswith("How often should inverters be inspected?")


def test_rating_a_message(indexed, fake_model):
    events = stream(indexed, question=QUESTION, save=True)
    rated = indexed.post("/feedback", json={"rating": "down", "question": QUESTION, "comment": "Too vague",
                                            "message_id": events[-1]["message_id"]})
    assert rated.status_code == 200
    messages = indexed.get(f"/chats/{events[0]['chat_id']}").json()["messages"]
    assert messages[1]["rating"] == "down"


def test_chats_can_be_renamed_and_deleted(indexed, fake_model):
    chat_id = indexed.post("/chats", json={"title": "Solar"}).json()["id"]
    assert indexed.patch(f"/chats/{chat_id}", json={"title": "Panels"}).json()["title"] == "Panels"
    assert indexed.delete(f"/chats/{chat_id}").status_code == 200
    assert indexed.get(f"/chats/{chat_id}").status_code == 404
    assert stream(indexed, question=QUESTION, chat_id="missing") == [{"detail": "Chat not found."}]


def test_chats_belong_to_their_workspace(indexed, fake_model):
    chat_id = stream(indexed, question=QUESTION, save=True)[0]["chat_id"]
    other = indexed.post("/workspaces", json={"name": "Other"}).json()["id"]
    assert indexed.get(f"/chats/{chat_id}", headers={"X-Workspace-Id": other}).status_code == 404


def test_background_indexing_reports_progress(client, app_env):
    upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years."))
    job = client.post("/documents/index", params={"wait": False}).json()["job"]
    assert job["status"] in ("queued", "running", "done")
    jobs.wait(job["id"], timeout=30)

    finished = client.get(f"/jobs/{job['id']}").json()
    assert finished["status"] == "done"
    assert finished["result"]["new_documents"] == ["guide.txt", "other.txt"]
    assert finished["progress"] == {"stage": "done"}
    assert client.get("/jobs", params={"active": True}).json()["jobs"] == []
    assert len(client.get("/documents").json()["documents"]) == 2


def test_progress_reports_each_file_and_page(app_env):
    from test_ocr import text_pdf

    store = app_env.store
    (store.upload_dir / "manual.pdf").write_bytes(text_pdf(
        "Inverters should be inspected once a year by a technician.",
        "Batteries should be kept dry and off the floor at all times."))
    updates = []
    store.rebuild(progress=updates.append)
    reading = [u for u in updates if u["stage"] == "reading"]
    assert [(u["file"], u["page"], u["page_count"]) for u in reading] == [
        ("manual.pdf", None, None), ("manual.pdf", 1, 2), ("manual.pdf", 2, 2)]
    assert updates[-1]["stage"] == "embedding"


def test_only_one_indexing_job_per_workspace(client, app_env, monkeypatch):
    from backend import db

    upload(client, ("guide.txt", SOLAR_GUIDE))
    queued = db.create_job(app_env.workspace_id, "local")  # pretend one is already waiting
    again = client.post("/documents/index", params={"wait": False}).json()["job"]
    assert again["id"] == queued["id"]


def test_interrupted_jobs_are_marked_failed(app_env):
    from backend import db

    job = db.create_job(app_env.workspace_id, "local")
    db.fail_interrupted_jobs()
    assert db.get_job(job["id"])["status"] == "failed"


def test_weak_matches_are_not_sent_to_the_model(indexed, fake_model, monkeypatch):
    class LowScores:
        def predict(self, pairs, **kwargs):
            return [-9.0 for _ in pairs]

    monkeypatch.setattr(models, "RERANKER_ID", "fake-reranker")
    monkeypatch.setattr(models, "reranker", LowScores())
    events = stream(indexed, question=QUESTION)
    assert events[0]["covered"] is False
    assert events[0]["sources"]  # still shown as the closest passages
    assert events[-1]["answer"] == answers.NOT_COVERED_ANSWER
    body = indexed.post("/ask", json={"question": QUESTION}).json()
    assert (body["covered"], body["answer"]) == (False, answers.NOT_COVERED_ANSWER)
    assert fake_model.prompts == []


def test_passages_far_below_the_best_are_dropped(indexed, fake_model, monkeypatch, client):
    upload(client, ("water.txt", b"Boil drinking water for one minute before drinking it."))
    client.post("/documents/index")

    class Scores:
        def predict(self, pairs, **kwargs):
            return [8.0 if "Solar" in text else 1.0 for _, text in pairs]  # water is 7 below

    monkeypatch.setattr(models, "RERANKER_ID", "fake-reranker")
    monkeypatch.setattr(models, "reranker", Scores())
    monkeypatch.setattr(models, "MIN_SCORE", 0.0)  # let both documents through the cutoff
    sources = indexed.post("/ask", json={"question": QUESTION}).json()["sources"]
    assert {s["source_name"] for s in sources} == {"guide.txt"}
    _, prompt = fake_model.prompts[-1]
    assert "water.txt" not in prompt

    monkeypatch.setattr(models, "RERANK_GAP", 10.0)
    sources = indexed.post("/ask", json={"question": QUESTION}).json()["sources"]
    assert {s["source_name"] for s in sources} == {"guide.txt", "water.txt"}


def test_answers_follow_the_question_language():
    assert "Amharic" in answers.language_instruction("የፀሐይ ፓነሎች በየስንት ጊዜው መጽዳት አለባቸው?")
    assert answers.language_instruction("Paneli zisafishwe mara ngapi?") == (
        "Write the answer in the same language as the question.")
    prompt = answers.build_prompt("Je?", [{"source_name": "a.txt", "page": None, "text": "x"}])
    assert "same language as the question" in prompt


def test_document_file_download(indexed, app_env):
    source_id = indexed.get("/documents").json()["documents"][0]["source_id"]
    response = indexed.get(f"/documents/{source_id}/file")
    assert response.status_code == 200
    assert response.content == SOLAR_GUIDE
    assert 'filename="guide.txt"' in response.headers["content-disposition"]
    assert indexed.get("/documents/missing.txt/file").status_code == 404


def test_insights(indexed, fake_model):
    stream(indexed, question=QUESTION, save=True)
    body = indexed.get("/insights").json()
    assert (body["documents"], body["questions"], body["chats"]) == (1, 1, 1)
    assert body["top_documents"] == [{"source_name": "guide.txt", "answers": 1}]
    assert len(body["per_day"]) == 14 and body["per_day"][-1]["questions"] == 1
    assert body["feedback"]["total"] == 0


@pytest.mark.parametrize("question, language", [
    ("How often should panels be cleaned?", "en"),
    ("የደረቀ ቡና እርጥበት ስንት በመቶ መሆን አለበት?", "am"),
    ("Mahindi yanapaswa kukaushwa hadi unyevu wa asilimia ngapi?", "sw"),
    ("Simu yangu ikiibiwa, nifanye nini?", "sw"),
    ("Qu'est-ce que la garantie?", "en"),  # unknown languages fall back to English
])
def test_question_language(question, language):
    assert answers.question_language(question) == language


def test_no_passages_message_uses_the_question_language(indexed, fake_model):
    body = indexed.post("/ask", json={"question": "Rais wa kwanza wa Tanzania alikuwa nani?"}).json()
    assert body["answer"] == answers.CANNED["no_sources"]["sw"]
