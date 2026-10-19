"""Back up and restore all AfriSearch data (database, uploads, indexes).

    python -m backend.backup create [--out backups] [--keep 14]
    python -m backend.backup restore backups/afrisearch-backup-....tar.gz [--force]

Safe to run while the app is serving: the database is copied with SQLite's
backup API, which gives a consistent snapshot even mid-write. Files indexed while
a backup runs may be missing from it; they are picked up by the next one.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend import __version__, config

PREFIX = "afrisearch-backup-"


def create(data_dir: Path, out_dir: Path, keep: int = 14) -> Path:
    """Write a backup archive and delete the oldest beyond `keep`; returns the archive path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    moment = datetime.now(timezone.utc)
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    archive = out_dir / f"{PREFIX}{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        database = data_dir / "afrisearch.db"
        snapshot = Path(tmp) / "afrisearch.db"
        if database.exists():
            source, target = sqlite3.connect(database), sqlite3.connect(snapshot)
            with target:
                source.backup(target)
            source.close()
            target.close()
        info = {"version": __version__, "created_at": moment.isoformat(timespec="seconds")}
        (Path(tmp) / "backup.json").write_text(json.dumps(info), encoding="utf-8")
        partial = archive.with_suffix(".partial")
        with tarfile.open(partial, "w:gz") as tar:
            tar.add(Path(tmp) / "backup.json", arcname="backup.json")
            if snapshot.exists():
                tar.add(snapshot, arcname="afrisearch.db")
            if (data_dir / "workspaces").is_dir():
                tar.add(data_dir / "workspaces", arcname="workspaces")
        partial.rename(archive)  # never leave a half-written file with the final name
    backups = sorted(out_dir.glob(f"{PREFIX}*.tar.gz"))
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink()
    return archive


def restore(archive: Path, data_dir: Path, force: bool = False) -> Path | None:
    """Unpack a backup into data_dir. Existing data is kept aside unless the folder is empty.

    Returns where the previous data was moved, if anywhere. Stop the app first.
    """
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        if "backup.json" not in names:
            raise ValueError(f"{archive} is not an AfriSearch backup.")
        moved = None
        if data_dir.exists() and any(data_dir.iterdir()):
            if not force:
                raise FileExistsError(f"{data_dir} is not empty. Use --force to move its contents aside first.")
            moved = data_dir.with_name(f"{data_dir.name}.before-restore-{datetime.now():%Y%m%d-%H%M%S}")
            shutil.move(str(data_dir), moved)
        data_dir.mkdir(parents=True, exist_ok=True)
        tar.extractall(data_dir, filter="data")  # refuses absolute paths and ../ tricks
    (data_dir / "backup.json").unlink(missing_ok=True)
    return moved


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=config.DATA_DIR, help="data folder (default: AFRISEARCH_DATA_DIR)")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("create", help="write a backup archive")
    make.add_argument("--out", type=Path, default=config.ROOT / "backups")
    make.add_argument("--keep", type=int, default=14, help="how many backups to keep (0 keeps all)")
    back = commands.add_parser("restore", help="restore a backup archive (stop the app first)")
    back.add_argument("archive", type=Path)
    back.add_argument("--force", action="store_true", help="move existing data aside instead of refusing")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            archive = create(args.data, args.out, args.keep)
            print(f"Backup written: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            moved = restore(args.archive, args.data, args.force)
            print(f"Restored {args.archive} into {args.data}" + (f"; previous data moved to {moved}" if moved else ""))
    except (FileExistsError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
