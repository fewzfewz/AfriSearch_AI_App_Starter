"""Each workspace's documents and search index, stored under DATA_DIR/workspaces/<id>/."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from backend import config, extract, models
from backend.text import chunk_document, page_range

logger = logging.getLogger("afrisearch.store")

# Called with a dict describing indexing progress (see DocumentStore.rebuild).
ProgressCallback = Callable[[dict[str, Any]], None]


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_chunks(
    source_id: str, source_name: str, pages: list[tuple[int | None, str]],
    ocr_pages: set[int | None] = frozenset(),
) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"{source_id}-{idx}",
            "source_id": source_id,
            "source_name": source_name,
            "page": first_page,
            "page_end": last_page,
            "index_version": models.INDEX_VERSION,
            "ocr": bool(page_range(first_page, last_page) & ocr_pages),
            "text": text,
        }
        for idx, (first_page, last_page, text) in enumerate(chunk_document(pages))
    ]


def display_name(stored_name: str, manifest: dict[str, str]) -> str:
    # Recover original display name: from manifest, or clean up UUID prefix if legacy
    original_name = manifest.get(stored_name)
    if not original_name:
        match = re.match(r"^[0-9a-f]{32}_(.*)$", stored_name)
        original_name = match.group(1) if match else stored_name
    return original_name


class DocumentStore:
    """Uploads, chunks and embeddings of one workspace."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.upload_dir = directory / "uploads"
        self.index_path = directory / "index.json"
        self.embeddings_path = directory / "embeddings.npy"
        self.manifest_path = directory / "manifest.json"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # `lock` guards chunks/embeddings; `rebuild_lock` serializes changes to the index.
        self.lock = threading.Lock()
        self.rebuild_lock = threading.Lock()
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: np.ndarray | None = None
        self.load()

    # --- persistence -------------------------------------------------------------

    def load(self) -> None:
        self.chunks, self.embeddings = [], None
        if self.index_path.exists() and self.embeddings_path.exists():
            try:
                loaded_chunks = json.loads(self.index_path.read_text(encoding="utf-8"))
                loaded_vectors = np.load(self.embeddings_path)
                if len(loaded_chunks) == len(loaded_vectors):
                    self.chunks = loaded_chunks
                    self.embeddings = loaded_vectors.astype(np.float32)
            except (OSError, ValueError, json.JSONDecodeError):
                pass  # keep the workspace usable; re-indexing rebuilds the files

    def _persist(self) -> None:
        if self.chunks and self.embeddings is not None:
            self.index_path.write_text(json.dumps(self.chunks, ensure_ascii=False, indent=2), encoding="utf-8")
            np.save(self.embeddings_path, self.embeddings)
        else:
            self.index_path.unlink(missing_ok=True)
            self.embeddings_path.unlink(missing_ok=True)

    def load_manifest(self) -> dict[str, str]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        return {}

    def save_manifest(self, manifest: dict[str, str]) -> None:
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def uploaded_files(self) -> list[Path]:
        return [
            path for path in sorted(self.upload_dir.iterdir())
            if path.is_file() and path.suffix.lower() in config.ALLOWED_EXTENSIONS
        ]

    def file_path(self, source_id: str) -> Path:
        """The stored upload for a source id; raises FileNotFoundError for anything else."""
        path = self.upload_dir / source_id
        # source_id must be a plain file name inside upload_dir (no path traversal).
        if Path(source_id).name != source_id or not path.is_file():
            raise FileNotFoundError(source_id)
        return path

    # --- uploads -------------------------------------------------------------------

    def save_uploads(self, files: list[tuple[str, bytes]]) -> tuple[list[dict], list[dict]]:
        """Store (filename, content) pairs; returns (saved, errors). Duplicates are rejected."""
        saved, errors = [], []
        manifest = self.load_manifest()
        # Hashes of files already stored, so the same document isn't indexed twice.
        known_hashes = {
            file_sha256(path.read_bytes()): manifest.get(path.name, path.name) for path in self.uploaded_files()
        }
        for filename, content in files:
            original_name = Path(filename or "upload.txt").name
            if Path(original_name).suffix.lower() not in config.ALLOWED_EXTENSIONS:
                errors.append({"filename": original_name,
                               "error": "Only PDF, TXT and images (PNG, JPG, TIFF, WebP, BMP) are supported."})
                continue
            if not content:
                errors.append({"filename": original_name, "error": "File is empty."})
                continue
            if len(content) > config.MAX_UPLOAD_BYTES:
                errors.append({"filename": original_name, "error": "File exceeds 15 MB limit."})
                continue
            digest = file_sha256(content)
            if digest in known_hashes:
                errors.append({"filename": original_name,
                               "error": f"Duplicate of already uploaded file '{known_hashes[digest]}'."})
                continue
            known_hashes[digest] = original_name
            # Unique stored names prevent accidental overwrite when filenames collide.
            stored_name = f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', original_name)}"
            (self.upload_dir / stored_name).write_bytes(content)
            manifest[stored_name] = original_name
            saved.append({"filename": original_name, "stored_name": stored_name, "bytes": len(content)})
        if saved:
            self.save_manifest(manifest)
        return saved, errors

    # --- indexing ------------------------------------------------------------------

    def rebuild(self, full: bool = False, progress: ProgressCallback | None = None) -> dict[str, Any]:
        """Bring the index in line with the uploads.

        Only files without up-to-date chunks are extracted and embedded; chunks of
        files that no longer exist are dropped. `full=True` re-embeds everything.
        `progress` receives {"stage", "file", "file_number", "file_count", "page",
        "page_count"} as files are read, then {"stage": "embedding"}.
        """
        with self.rebuild_lock:
            return self._rebuild(full, progress or (lambda update: None))

    def _rebuild(self, full: bool, progress: ProgressCallback) -> dict[str, Any]:
        manifest = self.load_manifest()
        uploaded = self.uploaded_files()
        uploaded_ids = {path.name for path in uploaded}

        with self.lock:
            old_chunks = list(self.chunks)
            old_embeddings = self.embeddings

        # Keep existing chunks for files that are still uploaded and were indexed
        # with the current chunker/embedder settings.
        stale_ids = {item["source_id"] for item in old_chunks if item.get("index_version") != models.INDEX_VERSION}
        keep = [] if full else [
            i for i, item in enumerate(old_chunks)
            if item["source_id"] in uploaded_ids and item["source_id"] not in stale_ids
        ]
        indexed_ids = {old_chunks[i]["source_id"] for i in keep}
        to_read = [path for path in uploaded if path.name not in indexed_ids]

        new_chunks: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        for number, path in enumerate(to_read, start=1):
            name = display_name(path.name, manifest)
            state = {"stage": "reading", "file": name, "file_number": number, "file_count": len(to_read),
                     "page": None, "page_count": None}
            progress(dict(state))

            def on_page(page: int, page_count: int, used_ocr: bool, state=state) -> None:
                state.update(page=page, page_count=page_count)
                progress(dict(state))

            try:
                pages, ocr_pages = extract.extract_file(path, on_page=on_page)
            except extract.OcrUnavailable as exc:
                what = ("This image" if path.suffix.lower() in config.IMAGE_EXTENSIONS
                        else "This looks like a scanned PDF and")
                failed.append({"source_id": path.name, "filename": name,
                               "error": f"{what} needs OCR, which is not available: {exc}"})
                continue
            except Exception as exc:
                logger.warning("Could not process %s: %s", path.name, exc)
                failed.append({"source_id": path.name, "filename": name, "error": f"Could not read file: {exc}"})
                continue
            if not pages:
                failed.append({"source_id": path.name, "filename": name,
                               "error": "No text found, even with OCR. The scan may be blank, handwritten or too blurry."})
                continue
            new_chunks.extend(create_chunks(path.name, name, pages, ocr_pages))

        new_embeddings = None
        if new_chunks:
            progress({"stage": "embedding", "passages": len(new_chunks), "file_count": len(to_read)})
            new_embeddings = models.get_embedder().encode(
                [models.PASSAGE_PREFIX + item["text"] for item in new_chunks],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).astype(np.float32)

        parts = []
        if keep and old_embeddings is not None:
            parts.append(old_embeddings[keep])
        if new_embeddings is not None:
            parts.append(new_embeddings)

        with self.lock:
            self.chunks = [old_chunks[i] for i in keep] + new_chunks
            self.embeddings = (np.concatenate(parts) if len(parts) > 1 else parts[0]) if self.chunks else None
            self._persist()
            total = len(self.chunks)

        new_docs = sorted({item["source_name"] for item in new_chunks})
        logger.info("Index %s: %d chunks, %d new documents, %d failed", self.dir.name, total, len(new_docs), len(failed))
        return {"indexed_chunks": total, "new_chunks": len(new_chunks), "new_documents": new_docs, "failed": failed}

    def remove(self, source_id: str) -> int:
        """Delete an uploaded file and drop its chunks from the index without re-embedding."""
        with self.rebuild_lock:
            self.file_path(source_id).unlink()
            manifest = self.load_manifest()
            if manifest.pop(source_id, None) is not None:
                self.save_manifest(manifest)
            with self.lock:
                keep = [i for i, item in enumerate(self.chunks) if item["source_id"] != source_id]
                removed = len(self.chunks) - len(keep)
                if removed:
                    self.chunks = [self.chunks[i] for i in keep]
                    self.embeddings = self.embeddings[keep] if self.chunks and self.embeddings is not None else None
                    self._persist()
            return removed

    def delete_all(self) -> None:
        with self.rebuild_lock, self.lock:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.chunks, self.embeddings = [], None

    # --- reading -------------------------------------------------------------------

    def status(self) -> str:
        """"empty", "stale" (only chunks from other search settings) or "ready"."""
        with self.lock:
            if not self.chunks or self.embeddings is None:
                return "empty"
            if not any(item.get("index_version") == models.INDEX_VERSION for item in self.chunks):
                return "stale"
            return "ready"

    def documents(self) -> tuple[list[dict[str, Any]], int]:
        """(documents with their details, number needing re-indexing)."""
        documents: dict[str, dict[str, Any]] = {}
        stale = set()
        with self.lock:
            chunks = list(self.chunks)
        for item in chunks:
            doc = documents.setdefault(item["source_id"], {
                "source_id": item["source_id"],
                "source_name": item["source_name"],
                "type": Path(item["source_name"]).suffix.lower().lstrip(".") or "txt",
                "ocr": False,
                "passages": 0,
                "pages": None,
            })
            doc["passages"] += 1
            doc["ocr"] = doc["ocr"] or bool(item.get("ocr"))
            last_page = item.get("page_end") or item.get("page")
            if last_page:
                doc["pages"] = max(doc["pages"] or 0, last_page)
            if item.get("index_version") != models.INDEX_VERSION:
                stale.add(item["source_id"])
        for doc in documents.values():
            path = self.upload_dir / doc["source_id"]
            stat = path.stat() if path.is_file() else None
            doc["bytes"] = stat.st_size if stat else None
            doc["uploaded_at"] = (datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
                                  if stat else None)
        return list(documents.values()), len(stale)

    def passages(self, source_id: str) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {"chunk_id": item["chunk_id"], "source_name": item["source_name"], "page": item.get("page"),
                 "page_end": item.get("page_end"), "ocr": item.get("ocr", False), "text": item["text"]}
                for item in self.chunks if item["source_id"] == source_id
            ]

    def retrieve(
        self, question: str, top_k: int = 4, min_score: float | None = None, rerank: bool | None = None,
        source_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Best passages for the question, most relevant first.

        Passages must reach `min_score` semantic similarity. If reranking is on (the
        default when a reranker is configured), the reranker reorders the best
        candidates; `score` stays the semantic similarity either way. `source_ids`
        limits the search to those documents.
        """
        if min_score is None:
            min_score = models.MIN_SCORE
        if rerank is None:
            rerank = bool(models.RERANKER_ID)
        rerank = rerank and bool(models.RERANKER_ID)
        with self.lock:
            if not self.chunks or self.embeddings is None:
                return []
            # Only search chunks embedded with the current search model; vectors from
            # another model are not comparable even when they have the same size.
            scope = set(source_ids) if source_ids else None
            current = [
                i for i, item in enumerate(self.chunks)
                if item.get("index_version") == models.INDEX_VERSION and (scope is None or item["source_id"] in scope)
            ]
            if not current:
                return []
            current_chunks = [self.chunks[i] for i in current]
            current_embeddings = self.embeddings[current]

        vector = models.get_embedder().encode(
            models.QUERY_PREFIX + question,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        scores = current_embeddings @ vector
        limit = max(top_k, models.RERANK_CANDIDATES) if rerank else top_k
        results = []
        for idx in np.argsort(-scores, kind="stable")[:limit]:
            score = float(scores[int(idx)])
            if score < min_score:
                break  # scores are sorted, so the rest are lower too
            item = dict(current_chunks[int(idx)])
            item["score"] = score
            results.append(item)
        if rerank and results:
            rerank_scores = models.get_reranker().predict(
                [(question, item["text"]) for item in results], show_progress_bar=False,
            )
            for item, value in zip(results, rerank_scores):
                item["rerank_score"] = float(value)
            results.sort(key=lambda item: item["rerank_score"], reverse=True)
        return results[:top_k]


_stores: dict[Path, DocumentStore] = {}
_stores_lock = threading.Lock()


def workspace_dir(workspace_id: str) -> Path:
    return config.DATA_DIR / "workspaces" / workspace_id


def get_store(workspace_id: str) -> DocumentStore:
    """The (cached) store of a workspace."""
    directory = workspace_dir(workspace_id)
    with _stores_lock:
        if directory not in _stores:
            _stores[directory] = DocumentStore(directory)
        return _stores[directory]


def forget_store(workspace_id: str) -> None:
    with _stores_lock:
        _stores.pop(workspace_dir(workspace_id), None)
