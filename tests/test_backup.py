"""Backups: a full round trip, retention, and refusing to overwrite data."""
import tarfile

import pytest

from backend import backup, config, store
from conftest import SOLAR_GUIDE, upload


def test_backup_and_restore_round_trip(client, app_env, fake_model, tmp_path, monkeypatch):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    chat_id = client.post("/ask", json={"question": "How often should panels be cleaned?", "save": True}).json()["chat_id"]

    archive = backup.create(config.DATA_DIR, tmp_path / "backups")
    assert archive.name.startswith("afrisearch-backup-") and archive.suffixes == [".tar", ".gz"]

    restored = tmp_path / "restored"
    backup.restore(archive, restored)
    monkeypatch.setattr(config, "DATA_DIR", restored)  # as a new server would start on it
    monkeypatch.setattr(store, "_stores", {})
    assert [d["source_name"] for d in client.get("/documents").json()["documents"]] == ["guide.txt"]
    assert client.get(f"/chats/{chat_id}").json()["messages"][1]["role"] == "assistant"
    assert client.post("/ask", json={"question": "How often should panels be cleaned?"}).status_code == 200
    assert not (restored / "backup.json").exists()


def test_old_backups_are_deleted(app_env, tmp_path, monkeypatch):
    out = tmp_path / "backups"
    stamps = iter(f"2026010{i}-000000" for i in range(1, 6))

    class Clock:
        @staticmethod
        def now(tz=None):
            from datetime import datetime
            return datetime.strptime(next(stamps), "%Y%m%d-%H%M%S")

    monkeypatch.setattr(backup, "datetime", Clock)
    for _ in range(4):
        backup.create(config.DATA_DIR, out, keep=2)
    assert sorted(p.name for p in out.iterdir()) == [
        "afrisearch-backup-20260103-000000.tar.gz", "afrisearch-backup-20260104-000000.tar.gz"]


def test_restore_refuses_to_overwrite_unless_forced(client, app_env, tmp_path):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    archive = backup.create(config.DATA_DIR, tmp_path / "backups")
    with pytest.raises(FileExistsError):
        backup.restore(archive, config.DATA_DIR)
    moved = backup.restore(archive, config.DATA_DIR, force=True)
    assert moved.exists() and (config.DATA_DIR / "afrisearch.db").exists()


def test_restore_rejects_other_archives_and_path_tricks(tmp_path):
    bad = tmp_path / "bad.tar.gz"
    (tmp_path / "evil.txt").write_text("x")
    with tarfile.open(bad, "w:gz") as tar:
        tar.add(tmp_path / "evil.txt", arcname="../evil.txt")
    with pytest.raises(ValueError):
        backup.restore(bad, tmp_path / "data")  # no backup.json: not an AfriSearch backup

    tricky = tmp_path / "tricky.tar.gz"
    (tmp_path / "backup.json").write_text("{}")
    (tmp_path / "payload.txt").write_text("overwritten")
    with tarfile.open(tricky, "w:gz") as tar:
        tar.add(tmp_path / "backup.json", arcname="backup.json")
        tar.add(tmp_path / "payload.txt", arcname="../evil.txt")  # tries to write outside data2/
    with pytest.raises(tarfile.TarError):
        backup.restore(tricky, tmp_path / "data2")
    assert (tmp_path / "evil.txt").read_text() == "x"  # untouched
