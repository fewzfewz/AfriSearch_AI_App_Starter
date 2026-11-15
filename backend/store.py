"""Each workspace's documents and search index, stored under DATA_DIR/workspaces/<id>/."""
from __future__ import annotations

import hashlib
import io
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


UNSUPPORTED_MESSAGE = ("Supported: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), TXT, Markdown, CSV, HTML "
                       "and images (PNG, JPG, TIFF, WebP, BMP). Save older .doc/.xls/.ppt files in the newer format.")


def content_problem(filename: str, content: bytes) -> str | None:
    """Why the file's content doesn't match its type, or None if it looks right."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and b"%PDF-" not in content[:1024]:
        return "This doesn't look like a PDF file."
    if suffix in config.TEXT_EXTENSIONS and b"\x00" in content[:65536]:
        return "This doesn't look like a text file."
    if suffix in config.OFFICE_EXTENSIONS and not content.startswith(b"PK\x03\x04"):
        # .docx/.xlsx/.pptx are zip files; the old .doc/.xls/.ppt formats are not.
        return "This isn't a modern Office file. Save it as .docx, .xlsx or .pptx and upload again."
    if suffix in config.IMAGE_EXTENSIONS:
        from PIL import Image

        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
        except Image.DecompressionBombError:
            return "This image has too many pixels to read safely."
        except Exception:
            return "This doesn't look like a valid image."
    return None


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
        self.tags_path = directory / "tags.json"
        self.outlines_path = directory / "outlines.json"
        self.summaries_path = directory / "summaries.json"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # `lock` guards chunks/embeddings; `rebuild_lock` serializes changes to the index.
        self.lock = threading.Lock()
        self.rebuild_lock = threading.Lock()
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: np.ndarray | None = None
        self._bm25_index: Any = None
        self._bm25_chunks_len: int = -1
        self.load()

    # --- persistence -------------------------------------------------------------

    def load(self) -> None:
        self.chunks, self.embeddings = [], None
        self._bm25_index, self._bm25_chunks_len = None, -1
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
        self._bm25_index, self._bm25_chunks_len = None, -1
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

    def load_tags(self) -> dict[str, list[str]]:
        if self.tags_path.exists():
            try:
                data = json.loads(self.tags_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {
                        str(k): [str(t).strip() for t in v if str(t).strip()]
                        for k, v in data.items()
                        if isinstance(v, list)
                    }
            except (OSError, ValueError):
                return {}
        return {}

    def save_tags(self, tags: dict[str, list[str]]) -> None:
        self.tags_path.write_text(json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_document_tags(self, source_id: str) -> list[str]:
        return self.load_tags().get(source_id, [])

    def set_document_tags(self, source_id: str, tags: list[str]) -> list[str]:
        self.file_path(source_id)  # raises FileNotFoundError if source_id is not stored
        cleaned: list[str] = []
        seen: set[str] = set()
        for t in tags:
            tag_str = str(t).strip()
            if not tag_str or len(tag_str) > 50:
                continue
            lower = tag_str.lower()
            if lower not in seen:
                seen.add(lower)
                cleaned.append(tag_str)
        cleaned = cleaned[:20]

        with self.rebuild_lock:
            all_tags = self.load_tags()
            if cleaned:
                all_tags[source_id] = cleaned
            else:
                all_tags.pop(source_id, None)
            self.save_tags(all_tags)
        return cleaned

    def all_tags(self) -> list[str]:
        all_tags = self.load_tags()
        unique: dict[str, str] = {}
        for tags in all_tags.values():
            for t in tags:
                lower = t.lower()
                if lower not in unique:
                    unique[lower] = t
        return sorted(unique.values(), key=lambda s: s.lower())

    # --- outlines & summaries ----------------------------------------------------

    def load_outlines(self) -> dict[str, list[dict[str, Any]]]:
        if self.outlines_path.exists():
            try:
                data = json.loads(self.outlines_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                return {}
        return {}

    def save_outlines(self, outlines: dict[str, list[dict[str, Any]]]) -> None:
        self.outlines_path.write_text(json.dumps(outlines, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_document_outline(self, source_id: str) -> list[dict[str, Any]]:
        outlines = self.load_outlines()
        if source_id in outlines and outlines[source_id]:
            return outlines[source_id]
        try:
            path = self.file_path(source_id)
            pages, _ = extract.extract_file(path)
            from backend import outline as doc_outline
            extracted = doc_outline.extract_outline(path, pages)
            if extracted:
                outlines[source_id] = extracted
                self.save_outlines(outlines)
            return extracted
        except Exception as exc:
            logger.debug("Lazy outline extraction skipped for %s: %s", source_id, exc)
            return []

    def load_summaries(self) -> dict[str, str]:
        if self.summaries_path.exists():
            try:
                data = json.loads(self.summaries_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if v}
            except (OSError, ValueError):
                return {}
        return {}

    def save_summaries(self, summaries: dict[str, str]) -> None:
        self.summaries_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_document_summary(self, source_id: str) -> str | None:
        return self.load_summaries().get(source_id)

    def set_document_summary(self, source_id: str, summary: str) -> None:
        summaries = self.load_summaries()
        summaries[source_id] = summary
        self.save_summaries(summaries)

    def uploaded_files(self) -> list[Path]:
        return [
            path for path in sorted(self.upload_dir.iterdir())
            if path.is_file() and path.suffix.lower() in config.ALLOWED_EXTENSIONS
        ]

    def bytes_used(self) -> int:
        return sum(path.stat().st_size for path in self.uploaded_files())

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
        used = self.bytes_used()
        # Hashes of files already stored, so the same document isn't indexed twice.
        known_hashes = {
            file_sha256(path.read_bytes()): manifest.get(path.name, path.name) for path in self.uploaded_files()
        }
        for filename, content in files:
            original_name = Path(filename or "upload.txt").name
            if Path(original_name).suffix.lower() not in config.ALLOWED_EXTENSIONS:
                errors.append({"filename": original_name, "error": UNSUPPORTED_MESSAGE})
                continue
            if not content:
                errors.append({"filename": original_name, "error": "File is empty."})
                continue
            if len(content) > config.MAX_UPLOAD_BYTES:
                errors.append({"filename": original_name, "error": "File exceeds 15 MB limit."})
                continue
            problem = content_problem(original_name, content)
            if problem:
                errors.append({"filename": original_name, "error": problem})
                continue
            if config.WORKSPACE_QUOTA_BYTES and used + len(content) > config.WORKSPACE_QUOTA_BYTES:
                quota_mb = config.WORKSPACE_QUOTA_BYTES / 1024 / 1024
                errors.append({"filename": original_name, "error": (
                    f"The workspace's storage is full ({used / 1024 / 1024:.0f} of {quota_mb:.0f} MB used). "
                    "Delete documents you no longer need, or ask about a larger plan.")})
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
            used += len(content)
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
            batch_size = int(os.getenv("AFRISEARCH_EMBED_BATCH_SIZE", "64"))
            new_embeddings = models.get_embedder().encode(
                [models.PASSAGE_PREFIX + item["text"] for item in new_chunks],
                batch_size=batch_size,
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
            tags = self.load_tags()
            if tags.pop(source_id, None) is not None:
                self.save_tags(tags)
            outlines = self.load_outlines()
            if outlines.pop(source_id, None) is not None:
                self.save_outlines(outlines)
            summaries = self.load_summaries()
            if summaries.pop(source_id, None) is not None:
                self.save_summaries(summaries)
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
        tags_map = self.load_tags()
        outlines_map = self.load_outlines()
        summaries_map = self.load_summaries()
        for doc in documents.values():
            path = self.upload_dir / doc["source_id"]
            stat = path.stat() if path.is_file() else None
            doc["bytes"] = stat.st_size if stat else None
            doc["uploaded_at"] = (datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
                                  if stat else None)
            doc["tags"] = tags_map.get(doc["source_id"], [])
            doc["outline"] = outlines_map.get(doc["source_id"], [])
            doc["summary"] = summaries_map.get(doc["source_id"])
        return list(documents.values()), len(stale)

    def passages(self, source_id: str) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {"chunk_id": item["chunk_id"], "source_name": item["source_name"], "page": item.get("page"),
                 "page_end": item.get("page_end"), "ocr": item.get("ocr", False), "text": item["text"]}
                for item in self.chunks if item["source_id"] == source_id
            ]

    def _get_bm25_index(self, chunks: list[dict[str, Any]]) -> Any:
        from backend.bm25 import BM25Index
        if self._bm25_index is None or self._bm25_chunks_len != len(chunks):
            corpus = [c["text"] for c in chunks]
            self._bm25_index = BM25Index(corpus)
            self._bm25_chunks_len = len(chunks)
        return self._bm25_index

    def _retrieve_single(
        self,
        query: str,
        top_k: int,
        min_score: float,
        rerank: bool,
        current_chunks: list[dict[str, Any]],
        current_embeddings: np.ndarray,
        target_sids: list[str],
    ) -> list[dict[str, Any]]:
        vector = models.get_embedder().encode(
            models.QUERY_PREFIX + query,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        dense_scores = current_embeddings @ vector
        scores = np.array(dense_scores, copy=True)

        # BM25 Okapi lexical scoring: boost passages with exact keyword matches
        bm25_index = self._get_bm25_index(current_chunks)
        bm25_scores = bm25_index.score(query)
        max_bm25 = float(np.max(bm25_scores)) if len(bm25_scores) > 0 else 0.0
        if max_bm25 > 0.0:
            norm_bm25 = bm25_scores / (max_bm25 + 1e-6)
            scores += 0.25 * norm_bm25

        # Outline precision routing: check if query specifically targets a chapter or section
        from backend import outline as doc_outline
        for s_id in target_sids:
            outl = self.get_document_outline(s_id)
            matched = doc_outline.match_outline_target(query, outl)
            if matched and matched.get("page"):
                p_start = matched["page"]
                p_end = matched.get("page_end", p_start)
                for i, chunk in enumerate(current_chunks):
                    if chunk["source_id"] == s_id:
                        p = chunk.get("page")
                        if p and p_start <= p <= p_end:
                            scores[i] += 0.40  # Boost matching chapter passages
                break

        limit = max(top_k, models.RERANK_CANDIDATES) if rerank else top_k
        results = []
        for idx in np.argsort(-scores, kind="stable")[:limit]:
            score = float(scores[int(idx)])
            dense_val = float(dense_scores[int(idx)])
            if dense_val < min_score and score < min_score:
                break  # below semantic threshold
            item = dict(current_chunks[int(idx)])
            item["score"] = dense_val
            item["hybrid_score"] = score
            results.append(item)
        if rerank and results:
            rerank_scores = models.get_reranker().predict(
                [(query, item["text"]) for item in results], show_progress_bar=False,
            )
            for item, value in zip(results, rerank_scores):
                item["rerank_score"] = float(value)
            results.sort(key=lambda item: item["rerank_score"], reverse=True)
        return results[:top_k]

    def _expand_chunk_context(self, chunk: dict[str, Any], chunks_map: dict[str, dict[str, Any]]) -> str:
        """Sentence-window context expansion: smoothly incorporates immediate lead-in/out context."""
        c_id = chunk.get("chunk_id", "")
        if "-" not in c_id:
            return chunk.get("text", "")
        src_id, idx_str = c_id.rsplit("-", 1)
        try:
            idx = int(idx_str)
        except ValueError:
            return chunk.get("text", "")

        prev_c = chunks_map.get(f"{src_id}-{idx-1}")
        next_c = chunks_map.get(f"{src_id}-{idx+1}")

        parts = []
        if prev_c and prev_c.get("source_id") == chunk.get("source_id"):
            prev_text = prev_c.get("text", "").strip()
            prev_sents = [s.strip() for s in prev_text.split(". ") if s.strip()]
            lead_in = ". ".join(prev_sents[-2:]) if len(prev_sents) >= 2 else prev_text
            if lead_in and not lead_in.endswith("."):
                lead_in += "."
            parts.append(f"... {lead_in}")

        parts.append(chunk.get("text", "").strip())

        if next_c and next_c.get("source_id") == chunk.get("source_id"):
            next_text = next_c.get("text", "").strip()
            next_sents = [s.strip() for s in next_text.split(". ") if s.strip()]
            lead_out = ". ".join(next_sents[:2]) if len(next_sents) >= 2 else next_text
            parts.append(f"{lead_out} ...")

        return "\n\n".join(parts)

    def retrieve(
        self, question: str, top_k: int = 4, min_score: float | None = None, rerank: bool | None = None,
        source_ids: list[str] | None = None, tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Best passages for the question, most relevant first.

        Passages must reach `min_score` semantic similarity. If reranking is on (the
        default when a reranker is configured), the reranker reorders the best
        candidates; `score` stays the semantic similarity either way. `source_ids`
        limits the search to those documents; `tags` limits the search to documents
        carrying any of the specified tags.
        """
        if min_score is None:
            min_score = models.MIN_SCORE
        if rerank is None:
            rerank = bool(models.RERANKER_ID)
        rerank = rerank and bool(models.RERANKER_ID)

        # Tag filtering: resolve matching source_ids
        query_tags = {t.strip().lower() for t in tags if t.strip()} if tags else None
        if query_tags is not None:
            tags_map = self.load_tags()
            matching_ids = {
                s_id for s_id, doc_tags in tags_map.items()
                if any(t.lower() in query_tags for t in doc_tags)
            }
            if not matching_ids:
                return []
            if source_ids is not None:
                scope = set(source_ids) & matching_ids
                if not scope:
                    return []
            else:
                scope = matching_ids
        else:
            scope = set(source_ids) if source_ids else None

        with self.lock:
            if not self.chunks or self.embeddings is None:
                return []
            # Only search chunks embedded with the current search model; vectors from
            # another model are not comparable even when they have the same size.
            current = [
                i for i, item in enumerate(self.chunks)
                if item.get("index_version") == models.INDEX_VERSION and (scope is None or item["source_id"] in scope)
            ]
            if not current:
                return []
            current_chunks = [self.chunks[i] for i in current]
            current_embeddings = self.embeddings[current]

        target_sids = source_ids or list({c["source_id"] for c in current_chunks})
        chunks_map = {c["chunk_id"]: c for c in current_chunks}

        # Query Decomposition for Multi-Hop / Comparative reasoning
        from backend.decompose import decompose_query
        subqueries = decompose_query(question)

        if len(subqueries) > 1:
            per_facet_k = max(2, (top_k + len(subqueries) - 1) // len(subqueries))
            facet_buckets: list[list[dict[str, Any]]] = []
            for sq in subqueries:
                sq_res = self._retrieve_single(
                    sq,
                    top_k=per_facet_k,
                    min_score=min_score,
                    rerank=rerank,
                    current_chunks=current_chunks,
                    current_embeddings=current_embeddings,
                    target_sids=target_sids,
                )
                for item in sq_res:
                    item["facet"] = sq
                facet_buckets.append(sq_res)

            combined: list[dict[str, Any]] = []
            seen_ids = set()
            max_len = max(len(b) for b in facet_buckets) if facet_buckets else 0
            for i in range(max_len):
                for b in facet_buckets:
                    if i < len(b):
                        cand = b[i]
                        if cand["chunk_id"] not in seen_ids:
                            seen_ids.add(cand["chunk_id"])
                            combined.append(cand)
            if combined:
                results = combined[:top_k]
                for item in results:
                    item["expanded_text"] = self._expand_chunk_context(item, chunks_map)
                return results

        results = self._retrieve_single(
            question,
            top_k=top_k,
            min_score=min_score,
            rerank=rerank,
            current_chunks=current_chunks,
            current_embeddings=current_embeddings,
            target_sids=target_sids,
        )
        for item in results:
            item["expanded_text"] = self._expand_chunk_context(item, chunks_map)
        return results

    def retrieve_deep(
        self,
        question: str,
        source_ids: list[str] | None = None,
        tags: list[str] | None = None,
        provider: str | None = None,
        model: str | None = None,
        max_total_chunks: int | None = None,
        coalesce_target_chars: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve broad, multi-chapter or full document context for Deep Book Mode.

        For focused or book-length documents, loads comprehensive text ordered by chapter/page,
        coalescing contiguous passages into cohesive multi-page sections tailored to the model's budget.
        """
        def_chunks, def_chars = model_context_budget(provider, model)
        if max_total_chunks is None:
            max_total_chunks = def_chunks
        if coalesce_target_chars is None:
            coalesce_target_chars = def_chars

        # Resolve tag scope if present
        query_tags = {t.strip().lower() for t in tags if t.strip()} if tags else None
        if query_tags is not None:
            tags_map = self.load_tags()
            matching_ids = {
                s_id for s_id, doc_tags in tags_map.items()
                if any(t.lower() in query_tags for t in doc_tags)
            }
            if not matching_ids:
                return []
            if source_ids is not None:
                scope = set(source_ids) & matching_ids
                if not scope:
                    return []
            else:
                scope = matching_ids
        else:
            scope = set(source_ids) if source_ids else None

        with self.lock:
            if not self.chunks:
                return []
            current_chunks = [
                item for item in self.chunks
                if (scope is None or item["source_id"] in scope)
            ]
            if not current_chunks:
                return []

        # If total chunks in scope is within budget, keep all in natural document order
        if len(current_chunks) <= max_total_chunks:
            selected_chunks = list(current_chunks)
        else:
            with self.lock:
                current_indices = [
                    i for i, item in enumerate(self.chunks)
                    if (scope is None or item["source_id"] in scope)
                ]
                has_embeddings = (
                    self.embeddings is not None and
                    len(self.embeddings) == len(self.chunks)
                )

            by_doc: dict[str, list[int]] = {}
            for idx in current_indices:
                by_doc.setdefault(self.chunks[idx]["source_id"], []).append(idx)

            scores_by_idx: dict[int, float] = {}
            if has_embeddings:
                try:
                    vector = models.get_embedder().encode(
                        models.QUERY_PREFIX + question,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    ).astype(np.float32)
                    chunk_embeddings = self.embeddings[current_indices]
                    scores = chunk_embeddings @ vector
                    for rel_i, s in enumerate(scores):
                        scores_by_idx[current_indices[rel_i]] = float(s)
                except Exception as exc:
                    logger.warning("Deep mode semantic anchor search fallback: %s", exc)

            # Determine relevant documents based on question similarity
            doc_scores: dict[str, float] = {}
            for s_id, indices in by_doc.items():
                if scores_by_idx:
                    doc_scores[s_id] = max((scores_by_idx.get(idx, 0.0) for idx in indices), default=0.0)
                else:
                    doc_scores[s_id] = 1.0

            sorted_docs = sorted(doc_scores.keys(), key=lambda d: doc_scores[d], reverse=True)
            top_score = doc_scores.get(sorted_docs[0], 1.0) if sorted_docs else 1.0

            # Keep docs within 70% of top score or at least top 1 doc
            relevant_docs = {
                d for d in sorted_docs
                if doc_scores[d] >= max(0.35, top_score * 0.70)
            }
            if not relevant_docs and sorted_docs:
                relevant_docs = {sorted_docs[0]}

            # Prioritized chunk selection
            chunk_priority: dict[int, float] = {}

            # Outline-guided precision routing: if query explicitly matches a chapter/section
            from backend import outline as doc_outline
            matched_outline_range: tuple[str, int, int] | None = None
            for s_id in relevant_docs:
                outl = self.get_document_outline(s_id)
                matched = doc_outline.match_outline_target(question, outl)
                if matched and matched.get("page"):
                    p_start = matched["page"]
                    p_end = matched.get("page_end", p_start)
                    matched_outline_range = (s_id, p_start, p_end)
                    break

            if matched_outline_range:
                m_sid, m_start, m_end = matched_outline_range
                for idx in current_indices:
                    chunk = self.chunks[idx]
                    if chunk["source_id"] == m_sid:
                        p = chunk.get("page")
                        if p and m_start <= p <= m_end:
                            chunk_priority[idx] = max(chunk_priority.get(idx, 0.0), 3.0)

            # 1. Semantic anchors + immediate context
            if scores_by_idx:
                scored_candidates = [
                    (scores_by_idx[idx], idx)
                    for idx in current_indices
                    if self.chunks[idx]["source_id"] in relevant_docs
                ]
                scored_candidates.sort(reverse=True)
                for score, global_idx in scored_candidates[:max_total_chunks]:
                    chunk_priority[global_idx] = max(chunk_priority.get(global_idx, 0.0), score + 1.0)
                    if global_idx - 1 >= 0 and self.chunks[global_idx - 1]["source_id"] == self.chunks[global_idx]["source_id"]:
                        chunk_priority[global_idx - 1] = max(chunk_priority.get(global_idx - 1, 0.0), score + 0.5)
                    if global_idx + 1 < len(self.chunks) and self.chunks[global_idx + 1]["source_id"] == self.chunks[global_idx]["source_id"]:
                        chunk_priority[global_idx + 1] = max(chunk_priority.get(global_idx + 1, 0.0), score + 0.5)

            # 2. Structural anchors (TOC/Intro + Conclusion) for relevant docs
            head_count = 2 if max_total_chunks <= 12 else 4
            tail_count = 1 if max_total_chunks <= 12 else 3

            for s_id in relevant_docs:
                indices = by_doc.get(s_id, [])
                for idx in indices[:head_count]:
                    chunk_priority[idx] = max(chunk_priority.get(idx, 0.0), 0.8)
                if len(indices) > head_count:
                    for idx in indices[-tail_count:]:
                        chunk_priority[idx] = max(chunk_priority.get(idx, 0.0), 0.7)

            # If still room, fill sequentially from top relevant doc
            if len(chunk_priority) < max_total_chunks and sorted_docs:
                for idx in by_doc.get(sorted_docs[0], []):
                    if idx not in chunk_priority:
                        chunk_priority[idx] = 0.1
                    if len(chunk_priority) >= max_total_chunks:
                        break

            # Pick highest priority chunks up to budget
            top_selected = sorted(chunk_priority.keys(), key=lambda i: chunk_priority[i], reverse=True)[:max_total_chunks]

            # Re-sort in natural document reading order!
            selected_chunks = [self.chunks[i] for i in sorted(top_selected)]

        # Coalesce contiguous chunks from the same document into cohesive reading sections
        coalesced: list[dict[str, Any]] = []
        current_block: dict[str, Any] | None = None

        for chunk in selected_chunks:
            if current_block is None:
                current_block = {
                    "source_id": chunk["source_id"],
                    "source_name": chunk["source_name"],
                    "page": chunk.get("page"),
                    "page_end": chunk.get("page_end") or chunk.get("page"),
                    "ocr": chunk.get("ocr", False),
                    "texts": [chunk["text"]],
                    "total_len": len(chunk["text"]),
                }
            else:
                same_doc = chunk["source_id"] == current_block["source_id"]
                is_close_page = (
                    chunk.get("page") is None or
                    current_block["page_end"] is None or
                    abs((chunk.get("page") or 0) - (current_block["page_end"] or 0)) <= 2
                )
                within_size = current_block["total_len"] + len(chunk["text"]) <= coalesce_target_chars

                if same_doc and is_close_page and within_size:
                    current_block["texts"].append(chunk["text"])
                    current_block["total_len"] += len(chunk["text"])
                    if chunk.get("page_end"):
                        current_block["page_end"] = max(current_block["page_end"] or 0, chunk["page_end"])
                    current_block["ocr"] = current_block["ocr"] or chunk.get("ocr", False)
                else:
                    coalesced.append({
                        "chunk_id": f"{current_block['source_id']}-sec-{len(coalesced) + 1}",
                        "source_id": current_block["source_id"],
                        "source_name": current_block["source_name"],
                        "page": current_block["page"],
                        "page_end": current_block["page_end"],
                        "ocr": current_block["ocr"],
                        "score": 1.0,
                        "text": "\n\n".join(current_block["texts"]),
                    })
                    current_block = {
                        "source_id": chunk["source_id"],
                        "source_name": chunk["source_name"],
                        "page": chunk.get("page"),
                        "page_end": chunk.get("page_end") or chunk.get("page"),
                        "ocr": chunk.get("ocr", False),
                        "texts": [chunk["text"]],
                        "total_len": len(chunk["text"]),
                    }

        if current_block is not None:
            coalesced.append({
                "chunk_id": f"{current_block['source_id']}-sec-{len(coalesced) + 1}",
                "source_id": current_block["source_id"],
                "source_name": current_block["source_name"],
                "page": current_block["page"],
                "page_end": current_block["page_end"],
                "ocr": current_block["ocr"],
                "score": 1.0,
                "text": "\n\n".join(current_block["texts"]),
            })

        return coalesced


def model_context_budget(provider: str | None, model: str | None) -> tuple[int, int]:
    """Returns (max_chunks, coalesce_chars) tailored to the model's processing capacity."""
    prov = (provider or "").lower()
    mod = (model or "").lower()

    # 1. Ultra-Large Context Cloud Models (Gemini: 1M+ tokens)
    if "gemini" in prov or "gemini" in mod or "google" in prov:
        return (100, 4500)  # ~100,000+ tokens

    # 2. Large Context Cloud Models (Claude: 200k, GPT-4o: 128k)
    if "claude" in prov or "anthropic" in prov or "chatgpt" in prov or "openai" in prov or "gpt-4" in mod or "o1" in mod or "o3" in mod:
        return (50, 3000)   # ~40,000 tokens

    # 3. Local CPU Models (e.g. qwen-small / 0.5B on CPU)
    if prov in ("qwen-small", "local-cpu") or "0.5b" in mod or "small" in prov:
        # High-density, fast CPU execution budget (fits CPU memory and generates crisp answers in seconds)
        return (8, 900)   # ~1,200 - 1,800 tokens

    # 4. Local GPU Models (qwen 27B, gemma 26B, gpt-oss)
    if prov in ("qwen", "gemma", "gpt-oss", "local"):
        return (25, 2000)   # ~12,000 tokens

    # Default fallback
    return (25, 2000)


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
