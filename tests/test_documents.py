"""Uploading, indexing and deleting documents through the API."""
import io

from pypdf import PdfWriter

from conftest import SOLAR_GUIDE, upload


def blank_pdf() -> bytes:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(buffer)
    return buffer.getvalue()


def test_upload_and_index_a_text_file(client, app_env):
    result = upload(client, ("guide.txt", SOLAR_GUIDE))
    assert [item["filename"] for item in result["saved"]] == ["guide.txt"]

    indexed = client.post("/documents/index").json()
    assert indexed["new_documents"] == ["guide.txt"]
    assert indexed["indexed_chunks"] == len(app_env.store.chunks) > 0
    assert indexed["failed"] == []

    documents = client.get("/documents").json()["documents"]
    assert [doc["source_name"] for doc in documents] == ["guide.txt"]


def test_duplicate_upload_is_rejected_even_with_another_name(client):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    result = upload(client, ("copy-of-guide.txt", SOLAR_GUIDE))
    assert result["saved"] == []
    assert "Duplicate" in result["errors"][0]["error"]


def test_unsupported_and_empty_files_are_rejected(client):
    result = upload(client, ("notes.docx", b"data"), ("empty.txt", b""))
    assert result["saved"] == []
    assert {error["filename"] for error in result["errors"]} == {"notes.docx", "empty.txt"}


def test_indexing_only_embeds_new_files(client, app_env):
    embedder = app_env.embedder
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    assert len(embedder.batch_sizes) == 1

    embedder.batch_sizes.clear()
    nothing_new = client.post("/documents/index").json()
    assert nothing_new["new_chunks"] == 0
    assert embedder.batch_sizes == []

    upload(client, ("other.txt", b"Batteries last about ten years."))
    added = client.post("/documents/index").json()
    assert added["new_documents"] == ["other.txt"]
    assert embedder.batch_sizes == [added["new_chunks"]]


def test_full_rebuild_embeds_every_document_again(client, app_env):
    embedder = app_env.embedder
    upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years."))
    total = client.post("/documents/index").json()["indexed_chunks"]
    embedder.batch_sizes.clear()

    rebuilt = client.post("/documents/index", params={"full": True}).json()
    assert rebuilt["indexed_chunks"] == total
    assert embedder.batch_sizes == [total]


def test_documents_indexed_with_old_settings_are_reembedded(client, app_env):
    from backend import models

    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    for chunk in app_env.store.chunks:
        chunk["index_version"] = "old-settings"
    app_env.embedder.batch_sizes.clear()

    result = client.post("/documents/index").json()
    assert result["new_documents"] == ["guide.txt"]
    assert all(chunk["index_version"] == models.INDEX_VERSION for chunk in app_env.store.chunks)


def test_unreadable_and_textless_pdfs_are_reported(client):
    upload(client, ("guide.txt", SOLAR_GUIDE), ("scan.pdf", blank_pdf()), ("broken.pdf", b"%PDF-1.4 junk"))
    result = client.post("/documents/index").json()
    failed = {item["filename"]: item["error"] for item in result["failed"]}
    assert set(failed) == {"scan.pdf", "broken.pdf"}
    assert "scanned PDF and needs OCR" in failed["scan.pdf"]
    assert "Could not read file" in failed["broken.pdf"]
    assert result["new_documents"] == ["guide.txt"]


def test_failed_file_can_be_deleted(client):
    upload(client, ("scan.pdf", blank_pdf()))
    failed = client.post("/documents/index").json()["failed"][0]
    assert client.delete(f"/documents/{failed['source_id']}").status_code == 200
    assert client.post("/documents/index").json()["failed"] == []


def test_delete_document_removes_file_and_chunks(client, app_env):
    upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years."))
    client.post("/documents/index")
    documents = client.get("/documents").json()["documents"]
    guide = next(doc for doc in documents if doc["source_name"] == "guide.txt")

    result = client.delete(f"/documents/{guide['source_id']}").json()
    assert result["removed_chunks"] > 0
    assert not (app_env.store.upload_dir / guide["source_id"]).exists()
    remaining = client.get("/documents").json()["documents"]
    assert [doc["source_name"] for doc in remaining] == ["other.txt"]
    assert len(app_env.store.chunks) == len(app_env.store.embeddings)

    assert client.delete(f"/documents/{guide['source_id']}").status_code == 404


def test_delete_rejects_paths_outside_the_upload_folder(client, app_env):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    assert app_env.store.index_path.exists()

    # Not routed to the delete endpoint at all (404 or 405 depending on routing).
    assert client.delete("/documents/..%2Findex.json").status_code in (404, 405)
    assert app_env.store.index_path.exists()


def test_index_survives_a_restart(client, app_env):
    from backend.store import DocumentStore

    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    saved = [chunk["chunk_id"] for chunk in app_env.store.chunks]

    reloaded = DocumentStore(app_env.store.dir)  # as after a server restart
    assert [chunk["chunk_id"] for chunk in reloaded.chunks] == saved
    assert reloaded.embeddings.shape[0] == len(saved)


def test_document_tags_management_and_filtering(client, app_env):
    upload(client, ("guide.txt", SOLAR_GUIDE), ("finance.txt", b"Q3 revenue reached 1 million dollars."))
    client.post("/documents/index")
    docs = client.get("/documents").json()["documents"]
    guide = next(d for d in docs if d["source_name"] == "guide.txt")
    finance = next(d for d in docs if d["source_name"] == "finance.txt")

    # Initially empty tags
    assert guide.get("tags") == []
    assert finance.get("tags") == []

    # Tag guide as Legal and Guidelines
    res = client.patch(f"/documents/{guide['source_id']}/tags", json={"tags": ["Legal", "Guidelines"]})
    assert res.status_code == 200
    assert res.json()["tags"] == ["Legal", "Guidelines"]

    # Tag finance as Financial
    res2 = client.patch(f"/documents/{finance['source_id']}/tags", json={"tags": ["Financial"]})
    assert res2.status_code == 200
    assert res2.json()["tags"] == ["Financial"]

    # Check /documents/tags endpoint
    tags_res = client.get("/documents/tags").json()
    assert sorted(tags_res["tags"]) == ["Financial", "Guidelines", "Legal"]

    # List all documents and check tags
    all_docs_res = client.get("/documents").json()
    assert all_docs_res["tags"] == ["Financial", "Guidelines", "Legal"]
    g_doc = next(d for d in all_docs_res["documents"] if d["source_name"] == "guide.txt")
    assert g_doc["tags"] == ["Legal", "Guidelines"]

    # Filter by tag
    legal_docs = client.get("/documents?tag=Legal").json()["documents"]
    assert len(legal_docs) == 1
    assert legal_docs[0]["source_name"] == "guide.txt"

    fin_docs = client.get("/documents?tag=financial").json()["documents"]
    assert len(fin_docs) == 1
    assert fin_docs[0]["source_name"] == "finance.txt"

    empty_docs = client.get("/documents?tag=Nonexistent").json()["documents"]
    assert len(empty_docs) == 0

    # Replace document preserves tags
    client.post(
        f"/documents/{guide['source_id']}/replace",
        files={"file": ("guide-v2.txt", SOLAR_GUIDE + b"\nUpdated chapter.", "text/plain")},
    )
    client.post("/documents/index")
    updated_docs = client.get("/documents").json()["documents"]
    replaced_guide = next(d for d in updated_docs if d["source_name"] == "guide-v2.txt")
    assert replaced_guide["tags"] == ["Legal", "Guidelines"]

    # Delete document cleans up its tags
    client.delete(f"/documents/{finance['source_id']}")
    remaining_tags = client.get("/documents/tags").json()["tags"]
    assert "Financial" not in remaining_tags

