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
    main, _ = app_env
    result = upload(client, ("guide.txt", SOLAR_GUIDE))
    assert [item["filename"] for item in result["saved"]] == ["guide.txt"]

    indexed = client.post("/documents/index").json()
    assert indexed["new_documents"] == ["guide.txt"]
    assert indexed["indexed_chunks"] == len(main.chunks) > 0
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
    _, embedder = app_env
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
    _, embedder = app_env
    upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years."))
    total = client.post("/documents/index").json()["indexed_chunks"]
    embedder.batch_sizes.clear()

    rebuilt = client.post("/documents/index", params={"full": True}).json()
    assert rebuilt["indexed_chunks"] == total
    assert embedder.batch_sizes == [total]


def test_documents_indexed_with_old_settings_are_reembedded(client, app_env):
    main, embedder = app_env
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    for chunk in main.chunks:
        chunk["index_version"] = "old-settings"
    embedder.batch_sizes.clear()

    result = client.post("/documents/index").json()
    assert result["new_documents"] == ["guide.txt"]
    assert all(chunk["index_version"] == main.INDEX_VERSION for chunk in main.chunks)


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
    main, _ = app_env
    upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years."))
    client.post("/documents/index")
    documents = client.get("/documents").json()["documents"]
    guide = next(doc for doc in documents if doc["source_name"] == "guide.txt")

    result = client.delete(f"/documents/{guide['source_id']}").json()
    assert result["removed_chunks"] > 0
    assert not (main.UPLOAD_DIR / guide["source_id"]).exists()
    remaining = client.get("/documents").json()["documents"]
    assert [doc["source_name"] for doc in remaining] == ["other.txt"]
    assert len(main.chunks) == len(main.chunk_embeddings)

    assert client.delete(f"/documents/{guide['source_id']}").status_code == 404


def test_delete_rejects_paths_outside_the_upload_folder(client, app_env):
    main, _ = app_env
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    assert main.INDEX_PATH.exists()

    assert client.delete("/documents/..%2Findex.json").status_code == 404
    assert main.INDEX_PATH.exists()


def test_index_survives_a_restart(client, app_env):
    main, _ = app_env
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    saved = [chunk["chunk_id"] for chunk in main.chunks]

    main.chunks, main.chunk_embeddings = [], None
    main.load_index_from_disk()
    assert [chunk["chunk_id"] for chunk in main.chunks] == saved
    assert main.chunk_embeddings.shape[0] == len(saved)
