"""Upload limits and checks, rate limits, storage quota, security headers."""
import io

import pytest
from PIL import Image

from backend import config, limits, main
from conftest import SOLAR_GUIDE, upload
from test_accounts import as_user, supabase  # noqa: F401  (fixture)


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_file_contents_must_match_their_type(client):
    result = upload(client, ("fake.pdf", b"MZ\x90\x00 an executable"), ("binary.txt", b"abc\x00\x01\x02"),
                    ("broken.png", b"not an image"), ("real.png", png()), ("guide.txt", SOLAR_GUIDE))
    errors = {e["filename"]: e["error"] for e in result["errors"]}
    assert "doesn't look like a PDF" in errors["fake.pdf"]
    assert "doesn't look like a text file" in errors["binary.txt"]
    assert "valid image" in errors["broken.png"]
    assert sorted(item["filename"] for item in result["saved"]) == ["guide.txt", "real.png"]


def test_oversized_uploads_are_stopped_while_reading(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    result = upload(client, ("big.txt", b"x" * 5000), ("small.txt", b"Batteries last ten years."))
    assert result["errors"] == [{"filename": "big.txt", "error": "File exceeds 15 MB limit."}]
    assert [item["filename"] for item in result["saved"]] == ["small.txt"]


def test_at_most_twenty_files_per_upload(client):
    files = [("files", (f"f{i}.txt", f"Document number {i}.".encode(), "text/plain")) for i in range(21)]
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 400
    assert "at most 20" in response.json()["detail"]


def test_workspace_storage_quota(client, monkeypatch, app_env):
    monkeypatch.setattr(config, "WORKSPACE_QUOTA_BYTES", len(SOLAR_GUIDE) + 10)
    result = upload(client, ("guide.txt", SOLAR_GUIDE), ("other.txt", b"Batteries last about ten years, mostly."))
    assert [item["filename"] for item in result["saved"]] == ["guide.txt"]
    assert "storage is full" in result["errors"][0]["error"]
    storage = client.get("/documents").json()["storage"]
    assert storage == {"used_bytes": len(SOLAR_GUIDE), "quota_bytes": len(SOLAR_GUIDE) + 10}


def test_questions_are_rate_limited_per_user(client, fake_model, monkeypatch, supabase):  # noqa: F811
    monkeypatch.setattr(limits, "ASK_LIMITS", [(2, 60, "questions per minute")])
    amina, juma = as_user(sub="amina"), as_user(sub="juma", email="juma@example.org")
    for headers in (amina, juma):
        client.post("/documents/upload", headers=headers, files=[("files", ("g.txt", SOLAR_GUIDE, "text/plain"))])
        client.post("/documents/index", headers=headers)
    question = {"question": "How often should solar panels be cleaned?"}
    assert [client.post("/ask", json=question, headers=amina).status_code for _ in range(2)] == [200, 200]
    blocked = client.post("/ask/stream", json=question, headers=amina)
    assert blocked.status_code == 429
    assert "2 questions per minute" in blocked.json()["detail"]
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert client.post("/ask", json=question, headers=juma).status_code == 200  # others aren't affected


def test_uploads_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(limits, "UPLOAD_LIMITS", [(3, 3600, "uploaded files per hour")])
    upload(client, ("a.txt", b"First document text."), ("b.txt", b"Second document text."))
    response = client.post("/documents/upload", files=[("files", (f"{n}.txt", f"Text {n}.".encode(), "text/plain"))
                                                        for n in ("c", "d")])
    assert response.status_code == 429
    assert "minutes" in response.json()["detail"]


def test_cannot_rate_another_members_private_answer(client, fake_model, supabase):  # noqa: F811
    owner, guest = as_user(sub="owner", email="owner@example.org"), as_user(sub="guest", email="guest@example.org")
    workspace = client.get("/me", headers=owner).json()["workspaces"][0]["id"]
    client.get("/me", headers=guest)
    client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "guest@example.org"})
    client.post("/documents/upload", headers=owner, files=[("files", ("g.txt", SOLAR_GUIDE, "text/plain"))])
    client.post("/documents/index", headers=owner)
    message_id = client.post("/ask", headers=owner, json={"question": "How often should panels be cleaned?",
                                                          "save": True}).json()["message_id"]
    rating = {"rating": "down", "question": "q", "message_id": message_id}
    assert client.post("/feedback", headers={**guest, "X-Workspace-Id": workspace}, json=rating).status_code == 404
    assert client.post("/feedback", headers=owner, json=rating).status_code == 200


def test_security_headers(client, monkeypatch, tmp_path):
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<html><script>document.title='x'</script></html>", encoding="utf-8")
    monkeypatch.setattr(config, "WEB_DIST", web)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(main, "_csp", [])
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    csp = headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "connect-src 'self' https://project.supabase.co" in csp
    assert "'sha256-" in csp  # the inline dark-mode script is allowed by its hash, nothing else inline
    assert "script-src 'self' 'sha256-" in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_health_reports_problems_with_503(client, monkeypatch, tmp_path):
    assert client.get("/health").json()["status"] == "ok"
    read_only = tmp_path / "read-only"
    read_only.mkdir()
    read_only.chmod(0o500)
    monkeypatch.setattr(config, "DATA_DIR", read_only)
    try:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert any("data folder" in p or "database" in p for p in response.json()["problems"])
    finally:
        read_only.chmod(0o700)
