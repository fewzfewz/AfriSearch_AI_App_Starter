"""Indexing in the background, so uploads return at once and the UI can show progress."""
from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from backend import db, store

logger = logging.getLogger("afrisearch.jobs")

# One worker: indexing is CPU-heavy (OCR, embeddings), so jobs run one at a time.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indexer")
_futures: dict[str, Future] = {}
PROGRESS_INTERVAL = 0.5  # seconds between page-by-page progress writes


def start_index_job(workspace_id: str, user_id: str, full: bool = False) -> dict[str, Any]:
    """Queue indexing of a workspace; returns the job (an already active one if there is one)."""
    active = db.list_jobs(workspace_id, active_only=True, limit=1)
    if active:
        return active[0]
    job = db.create_job(workspace_id, user_id)
    _futures[job["id"]] = _executor.submit(_run, job["id"], workspace_id, full)
    return job


def wait(job_id: str, timeout: float | None = None) -> None:
    """Block until a job finishes (used by tests and the synchronous API)."""
    future = _futures.get(job_id)
    if future:
        future.result(timeout=timeout)


def _run(job_id: str, workspace_id: str, full: bool) -> None:
    db.update_job(job_id, status="running")
    last_write = 0.0

    def progress(update: dict[str, Any]) -> None:
        nonlocal last_write
        moment = time.monotonic()
        # Write every new file and stage at once; throttle page-by-page updates.
        page_update = update.get("page") not in (None, update.get("page_count"))
        if not page_update or moment - last_write >= PROGRESS_INTERVAL:
            last_write = moment
            db.update_job(job_id, progress=update)

    try:
        result = store.get_store(workspace_id).rebuild(full=full, progress=progress)
    except Exception as exc:
        logger.exception("Indexing job %s failed", job_id)
        db.update_job(job_id, status="failed", error=f"Indexing failed: {exc}")
    else:
        db.update_job(job_id, status="done", result=result, progress={"stage": "done"})
    finally:
        _futures.pop(job_id, None)
