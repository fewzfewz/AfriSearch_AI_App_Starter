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


def test_feedback_is_stored_and_summarized(client, app_env):
    main, _ = app_env
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
    assert len(client.get("/feedback?limit=1").json()["recent"]) == 1
    assert main.feedback_path().parent == main.DATA_DIR


def test_feedback_validation(client):
    assert client.post("/feedback", json={"rating": "meh", "question": QUESTION}).status_code == 422
    assert client.post("/feedback", json={"rating": "up", "question": ""}).status_code == 422


def test_damaged_feedback_lines_are_skipped(client, app_env):
    main, _ = app_env
    main.feedback_path().write_text('{"rating": "up", "question": "q"}\nnot json\n', encoding="utf-8")
    assert client.get("/feedback").json()["total"] == 1


def test_version_is_reported(client):
    from backend import __version__

    assert client.get("/").json()["version"] == __version__
