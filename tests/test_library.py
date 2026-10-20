"""Document details, passages, search scope and answer feedback."""
from conftest import SOLAR_GUIDE, upload
from test_ocr import text_pdf

WATER_GUIDE = b"Boil drinking water for one minute. Store boiled water in a clean covered container."
QUESTION = "How long should drinking water be boiled?"


def index(client, *files):
    upload(client, *files)
    client.post("/documents/index")
    return {d["source_name"]: d for d in client.get("/documents").json()["documents"]}


def test_documents_list_details(client):
    docs = index(client, ("guide.txt", SOLAR_GUIDE),
                 ("manual.pdf", text_pdf("Inverters should be inspected once a year by a technician.",
                                         "Batteries should be kept dry and off the floor at all times.")))
    assert docs["guide.txt"]["type"] == "txt"
    assert docs["guide.txt"]["pages"] is None
    assert docs["guide.txt"]["passages"] == 1
    assert docs["guide.txt"]["bytes"] == len(SOLAR_GUIDE)
    assert docs["guide.txt"]["uploaded_at"].endswith("+00:00")
    assert docs["manual.pdf"]["type"] == "pdf"
    assert docs["manual.pdf"]["pages"] == 2
    assert docs["manual.pdf"]["ocr"] is False


def test_document_passages(client):
    docs = index(client, ("guide.txt", SOLAR_GUIDE))
    source_id = docs["guide.txt"]["source_id"]
    body = client.get(f"/documents/{source_id}/passages").json()
    assert body["source_name"] == "guide.txt"
    assert body["passages"][0]["text"].startswith("Solar Panel Maintenance Guide")
    assert client.get("/documents/missing.txt/passages").status_code == 404


def test_search_can_be_limited_to_some_documents(client, fake_model):
    docs = index(client, ("guide.txt", SOLAR_GUIDE), ("water.txt", WATER_GUIDE))
    everywhere = client.post("/ask", json={"question": QUESTION, "generate_answer": False}).json()
    assert everywhere["sources"][0]["source_name"] == "water.txt"

    only_solar = {"question": QUESTION, "generate_answer": False, "source_ids": [docs["guide.txt"]["source_id"]]}
    sources = client.post("/ask", json=only_solar).json()["sources"]
    assert {s["source_name"] for s in sources} <= {"guide.txt"}

    streamed = client.post("/ask/stream", json=only_solar).text
    assert "water.txt" not in streamed


def test_feedback_is_stored_and_summarized(client):
    for rating, comment in [("up", ""), ("down", "Wrong number"), ("up", "Great")]:
        response = client.post("/feedback", json={
            "rating": rating, "question": QUESTION, "answer": "One minute [S1].",
            "provider": "fake", "comment": comment, "sources": ["water.txt"],
        })
        assert response.status_code == 200
    summary = client.get("/feedback").json()
    assert (summary["total"], summary["up"], summary["down"]) == (3, 2, 1)
    assert summary["recent"][0]["comment"] == "Great"  # newest first
    assert summary["recent"][0]["time"]
    assert summary["recent"][0]["sources"] == ["water.txt"]
    assert len(client.get("/feedback?limit=1").json()["recent"]) == 1

    other = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    assert client.get("/feedback", headers={"X-Workspace-Id": other}).json()["total"] == 0


def test_feedback_validation(client):
    assert client.post("/feedback", json={"rating": "meh", "question": QUESTION}).status_code == 422
    assert client.post("/feedback", json={"rating": "up", "question": ""}).status_code == 422
    assert client.post("/feedback", json={"rating": "up", "question": QUESTION,
                                          "message_id": "missing"}).status_code == 404


def test_documents_from_the_old_folder_layout_move_into_the_first_workspace(app_env, client):
    from backend import config

    legacy = config.DATA_DIR / "uploads"
    legacy.mkdir(parents=True)
    (legacy / "guide.txt").write_bytes(SOLAR_GUIDE)
    (legacy / ".gitkeep").write_text("")
    (config.DATA_DIR / "feedback.jsonl").write_text(
        '{"rating": "up", "question": "q"}\nnot json\n', encoding="utf-8")

    result = client.post("/documents/index").json()  # first request creates the workspace
    assert result["new_documents"] == ["guide.txt"]
    assert [p.name for p in legacy.iterdir()] == [".gitkeep"]  # hidden files stay
    assert client.get("/feedback").json()["total"] == 1  # damaged lines are skipped
    assert (config.DATA_DIR / "feedback.jsonl.imported").exists()


def test_version_is_reported(client):
    from backend import __version__

    assert client.get("/").json()["version"] == __version__


def test_replacing_a_document_with_a_new_version(client, fake_model):
    docs = index(client, ("guide.txt", SOLAR_GUIDE))
    old_id = docs["guide.txt"]["source_id"]
    chat = client.post("/ask", json={"question": "How often should solar panels be cleaned?", "save": True}).json()

    new_version = b"Solar Panel Maintenance Guide, 2027 edition. Clean the panels every two weeks."
    response = client.post(f"/documents/{old_id}/replace", files={"file": ("guide.txt", new_version, "text/plain")})
    assert response.status_code == 200
    client.post("/documents/index")
    docs = client.get("/documents").json()["documents"]
    assert [d["source_name"] for d in docs] == ["guide.txt"] and docs[0]["source_id"] != old_id
    passages = client.get(f"/documents/{docs[0]['source_id']}/passages").json()["passages"]
    assert "2027 edition" in passages[0]["text"]
    old_answer = client.get(f"/chats/{chat['chat_id']}").json()["messages"][1]
    assert "every month" in old_answer["data"]["sources"][0]["text"]  # earlier answers keep their quotes

    assert client.post("/documents/missing.txt/replace", files={"file": ("x.txt", b"text", "text/plain")}).status_code == 404
    rejected = client.post(f"/documents/{docs[0]['source_id']}/replace", files={"file": ("bad.pdf", b"not a pdf", "application/pdf")})
    assert rejected.status_code == 400 and "PDF" in rejected.json()["detail"]
    assert len(client.get("/documents").json()["documents"]) == 1  # a rejected version leaves the old one
