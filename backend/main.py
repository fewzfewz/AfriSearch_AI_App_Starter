from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Unless HF_HOME is set explicitly, keep model weights in a dedicated cache
# directory (~/.cache/hf_models) instead of the default ~/.cache/huggingface.
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path.home() / ".cache" / "hf_models")

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sentence_transformers import CrossEncoder, SentenceTransformer

from backend import llm

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_PATH = DATA_DIR / "index.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
MANIFEST_PATH = DATA_DIR / "manifest.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Multilingual (94 languages incl. Amharic, Swahili, Somali, Hausa, Afaan Oromo);
# "sentence-transformers/all-MiniLM-L6-v2" is a smaller English-focused option.
DEFAULT_EMBEDDER = "intfloat/multilingual-e5-small"
# Per-model search settings, matched by model-id prefix. E5 models are trained
# with "query: "/"passage: " prefixes and score unrelated text much higher than
# MiniLM, so each needs its own relevance cutoff. 0.75 was tuned for
# multilingual-e5-small with evaluation/run_eval.py: cross-language questions often
# score 0.75-0.80, so a higher cutoff drops relevant passages.
EMBEDDER_SETTINGS = {
    "intfloat/multilingual-e5-": {"query_prefix": "query: ", "passage_prefix": "passage: ", "min_score": 0.75},
    "intfloat/e5-": {"query_prefix": "query: ", "passage_prefix": "passage: ", "min_score": 0.75},
}
DEFAULT_SETTINGS = {"query_prefix": "", "passage_prefix": "", "min_score": 0.2}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
ALLOWED_EXTENSIONS = {".pdf", ".txt"} | IMAGE_EXTENSIONS
# OCR (Tesseract) reads scanned PDF pages and photos of documents. Languages are
# Tesseract codes joined with "+"; those not installed are skipped.
OCR_LANGUAGES = os.getenv("AFRISEARCH_OCR_LANGS", "eng+amh+swa")
OCR_DPI = 300
# PDF pages with less extractable text than this are treated as scanned images.
MIN_PAGE_CHARS = 25
CHUNK_SIZE = 180  # target words per chunk
CHUNK_OVERLAP = 35  # words of whole sentences repeated from the previous chunk
# Set by set_embedder(): the search model, its prefixes, and the INDEX_VERSION
# stored on each chunk (documents indexed with other settings are re-embedded).
EMBEDDER_ID = DEFAULT_EMBEDDER
QUERY_PREFIX = PASSAGE_PREFIX = ""
INDEX_VERSION = ""
# Passages scoring below this cosine similarity are treated as irrelevant.
MIN_SCORE = 0.0
# A cross-encoder reads the question and each of the best RERANK_CANDIDATES passages
# together and reorders them. On the evaluation set it raised "right document ranked
# first" from 32/39 to 36/39, at about 1-2 s per question on a laptop CPU.
# AFRISEARCH_RERANKER=off turns it off; requests can also skip it with rerank=false.
DEFAULT_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
RERANKER_ID = ""  # set by set_reranker(); empty means off
RERANK_CANDIDATES = 12

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("afrisearch")

index_lock = threading.Lock()
# Serializes operations that change the index (rebuild, delete).
rebuild_lock = threading.Lock()
# Guards lazy embedder loading so concurrent first requests load it once.
model_lock = threading.Lock()
embedder: SentenceTransformer | None = None
reranker: CrossEncoder | None = None
chunks: list[dict[str, Any]] = []
chunk_embeddings: np.ndarray | None = None


def load_manifest() -> dict[str, str]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def save_manifest(manifest: dict[str, str]) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_index_from_disk()
    yield


app = FastAPI(
    title="AfriSearch AI API",
    description="Local document ingestion, semantic retrieval, and grounded Q&A.",
    version="0.1.0",
    lifespan=lifespan,
)



class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)
    top_k: int = Field(default=4, ge=1, le=8)
    generate_answer: bool = True
    # One of llm.PROVIDERS; defaults to AFRISEARCH_DEFAULT_PROVIDER or the first available.
    provider: str | None = None
    # Reorder passages with the reranker; defaults to on when one is configured.
    rerank: bool | None = None


def get_embedder() -> SentenceTransformer:
    global embedder
    if embedder is None:
        with model_lock:
            if embedder is None:
                embedder = SentenceTransformer(EMBEDDER_ID)
    return embedder


def set_embedder(model_id: str) -> None:
    """Choose the search model; the next indexing run re-embeds documents if it changed."""
    global EMBEDDER_ID, QUERY_PREFIX, PASSAGE_PREFIX, MIN_SCORE, INDEX_VERSION, embedder
    settings = next(
        (values for start, values in EMBEDDER_SETTINGS.items() if model_id.startswith(start)),
        DEFAULT_SETTINGS,
    )
    with model_lock:
        EMBEDDER_ID = model_id
        QUERY_PREFIX = os.getenv("AFRISEARCH_QUERY_PREFIX", settings["query_prefix"])
        PASSAGE_PREFIX = os.getenv("AFRISEARCH_PASSAGE_PREFIX", settings["passage_prefix"])
        MIN_SCORE = float(os.getenv("AFRISEARCH_MIN_SCORE", settings["min_score"]))
        INDEX_VERSION = f"sentences-{CHUNK_SIZE}-{CHUNK_OVERLAP}|{EMBEDDER_ID}"
        if PASSAGE_PREFIX:
            INDEX_VERSION += f"|{PASSAGE_PREFIX}"
        embedder = None


set_embedder(os.getenv("AFRISEARCH_EMBEDDER", DEFAULT_EMBEDDER))


def get_reranker() -> CrossEncoder:
    global reranker
    if reranker is None:
        with model_lock:
            if reranker is None:
                reranker = CrossEncoder(RERANKER_ID)
    return reranker


def set_reranker(model_id: str) -> None:
    """Choose the reranking model; an empty id or "off" turns reranking off."""
    global RERANKER_ID, reranker
    model_id = model_id.strip()
    with model_lock:
        RERANKER_ID = "" if model_id.lower() in {"", "off", "none", "0", "false"} else model_id
        reranker = None


set_reranker(os.getenv("AFRISEARCH_RERANKER", DEFAULT_RERANKER))


def load_index_from_disk() -> None:
    global chunks, chunk_embeddings
    if INDEX_PATH.exists() and EMBEDDINGS_PATH.exists():
        try:
            loaded_chunks = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            loaded_vectors = np.load(EMBEDDINGS_PATH)
            if len(loaded_chunks) == len(loaded_vectors):
                chunks = loaded_chunks
                chunk_embeddings = loaded_vectors.astype(np.float32)
        except (OSError, ValueError, json.JSONDecodeError):
            # Keep the app available; the user can re-index their documents.
            chunks = []
            chunk_embeddings = None


def persist_index() -> None:
    INDEX_PATH.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if chunk_embeddings is not None:
        np.save(EMBEDDINGS_PATH, chunk_embeddings)


# Latin punctuation plus the Ethiopic full stop (።) and question mark (፧). Two
# Ethiopic wordspaces (፡፡) look identical to ። and are common in typed text and OCR output.
SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?።፧])|(?<=፡፡))\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_BOUNDARY.split(text) if s.strip()]


def chunk_document(
    pages: list[tuple[int | None, str]],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[tuple[int | None, int | None, str]]:
    """Group sentences into ~chunk_size-word chunks that may span pages.

    Chunks end on sentence boundaries where possible, and each chunk repeats
    the last ~overlap words of whole sentences from the previous one. Returns
    (first_page, last_page, text) tuples.
    """
    # Each unit is (page, words); sentences longer than chunk_size are split.
    units: list[tuple[int | None, list[str]]] = []
    for page, text in pages:
        for sentence in split_sentences(text):
            words = sentence.split()
            for start in range(0, len(words), chunk_size):
                units.append((page, words[start : start + chunk_size]))

    result: list[tuple[int | None, int | None, str]] = []
    current: list[tuple[int | None, list[str]]] = []
    current_words = 0
    has_new = False  # whether `current` holds anything beyond the carried-over overlap

    def flush() -> None:
        result.append((
            current[0][0],
            current[-1][0],
            " ".join(" ".join(words) for _, words in current),
        ))

    for unit in units:
        if current and current_words + len(unit[1]) > chunk_size:
            flush()
            # Carry trailing sentences (up to `overlap` words) into the next chunk.
            carried: list[tuple[int | None, list[str]]] = []
            carried_words = 0
            for prev in reversed(current):
                if carried_words + len(prev[1]) > overlap:
                    break
                carried.insert(0, prev)
                carried_words += len(prev[1])
            current, current_words = carried, carried_words
            has_new = False
        current.append(unit)
        current_words += len(unit[1])
        has_new = True

    if current and has_new:
        flush()
    return result


class OcrUnavailable(RuntimeError):
    """A file needs OCR but Tesseract (or its Python packages) is not installed."""


def ocr_status() -> tuple[list[str], str | None]:
    """(languages OCR will use, why OCR is unavailable or None)."""
    try:
        import pytesseract

        installed = set(pytesseract.get_languages(config=""))
    except ImportError:
        return [], "Install the 'pytesseract' and 'pypdfium2' packages."
    except Exception:  # TesseractNotFoundError and friends
        return [], "Install Tesseract OCR (for example: sudo apt install tesseract-ocr tesseract-ocr-amh)."
    wanted = [lang for lang in OCR_LANGUAGES.split("+") if lang]
    languages = [lang for lang in wanted if lang in installed] or (["eng"] if "eng" in installed else [])
    if not languages:
        return [], f"No Tesseract language data for {OCR_LANGUAGES} is installed."
    return languages, None


def ocr_image(image: Any) -> str:
    """Read the text in a PIL image with Tesseract."""
    languages, reason = ocr_status()
    if reason:
        raise OcrUnavailable(reason)
    import pytesseract

    return pytesseract.image_to_string(image.convert("L"), lang="+".join(languages)).strip()


def ocr_pdf_page(path: Path, page_number: int) -> str:
    try:
        import pypdfium2
    except ImportError as exc:
        raise OcrUnavailable("Install the 'pypdfium2' package.") from exc
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        image = pdf[page_number - 1].render(scale=OCR_DPI / 72).to_pil()
    finally:
        pdf.close()
    return ocr_image(image)


def extract_file(path: Path) -> tuple[list[tuple[int | None, str]], set[int | None]]:
    """Return (page, text) pairs and the pages whose text came from OCR.

    Page is None for TXT files and images. PDF pages without a usable text layer
    (scans) and image files are read with OCR; raises OcrUnavailable if they need
    it and it isn't installed.
    """
    suffix = path.suffix.lower()
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return ([(None, text)] if text else []), set()
    if suffix in IMAGE_EXTENSIONS:
        from PIL import Image

        with Image.open(path) as image:
            text = ocr_image(image)
        return ([(None, text)] if text else []), {None}
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages, ocr_pages = [], set()
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < MIN_PAGE_CHARS:
                scanned = ocr_pdf_page(path, page_number)
                if len(scanned) > len(text):
                    text = scanned
                    ocr_pages.add(page_number)
            if text:
                pages.append((page_number, text))
        return pages, ocr_pages
    raise ValueError("Only PDF, TXT and image files are supported.")


def page_range(first: int | None, last: int | None) -> set[int | None]:
    return {None} if first is None else set(range(first, (last or first) + 1))


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
            "index_version": INDEX_VERSION,
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


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def rebuild_index(full: bool = False) -> dict[str, Any]:
    with rebuild_lock:
        return _rebuild_index(full)


def _rebuild_index(full: bool) -> dict[str, Any]:
    """Bring the index in line with UPLOAD_DIR.

    Only files without up-to-date chunks are extracted and embedded; chunks of
    files that no longer exist are dropped. `full=True` re-embeds everything.
    """
    global chunks, chunk_embeddings
    manifest = load_manifest()
    uploaded = [
        path for path in sorted(UPLOAD_DIR.iterdir())
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    uploaded_ids = {path.name for path in uploaded}

    with index_lock:
        old_chunks = list(chunks)
        old_embeddings = chunk_embeddings

    # Keep existing chunks for files that are still uploaded and were indexed
    # with the current chunker/embedder settings.
    stale_ids = {
        item["source_id"] for item in old_chunks
        if item.get("index_version") != INDEX_VERSION
    }
    keep = [] if full else [
        i for i, item in enumerate(old_chunks)
        if item["source_id"] in uploaded_ids and item["source_id"] not in stale_ids
    ]
    indexed_ids = {old_chunks[i]["source_id"] for i in keep}

    new_chunks: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for path in uploaded:
        if path.name in indexed_ids:
            continue
        name = display_name(path.name, manifest)
        try:
            pages, ocr_pages = extract_file(path)
        except OcrUnavailable as exc:
            what = "This image" if path.suffix.lower() in IMAGE_EXTENSIONS else "This looks like a scanned PDF and"
            failed.append({"source_id": path.name, "filename": name,
                           "error": f"{what} needs OCR, which is not available: {exc}"})
            continue
        except Exception as exc:
            logger.warning("Could not process %s: %s", path.name, exc)
            failed.append({"source_id": path.name, "filename": name, "error": f"Could not read file: {exc}"})
            continue
        if not pages:
            failed.append({
                "source_id": path.name,
                "filename": name,
                "error": "No text found, even with OCR. The scan may be blank, handwritten or too blurry.",
            })
            continue
        new_chunks.extend(create_chunks(path.name, name, pages, ocr_pages))

    if new_chunks:
        new_embeddings = get_embedder().encode(
            [PASSAGE_PREFIX + item["text"] for item in new_chunks],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
    else:
        new_embeddings = None

    kept_chunks = [old_chunks[i] for i in keep]
    parts = []
    if keep and old_embeddings is not None:
        parts.append(old_embeddings[keep])
    if new_embeddings is not None:
        parts.append(new_embeddings)

    with index_lock:
        chunks = kept_chunks + new_chunks
        if chunks:
            chunk_embeddings = np.concatenate(parts) if len(parts) > 1 else parts[0]
            persist_index()
        else:
            chunk_embeddings = None
            INDEX_PATH.unlink(missing_ok=True)
            EMBEDDINGS_PATH.unlink(missing_ok=True)

    new_docs = sorted({item["source_name"] for item in new_chunks})
    logger.info("Index: %d chunks total, %d new documents, %d failed", len(chunks), len(new_docs), len(failed))
    return {
        "indexed_chunks": len(chunks),
        "new_chunks": len(new_chunks),
        "new_documents": new_docs,
        "failed": failed,
    }


def remove_document(source_id: str) -> int:
    """Delete an uploaded file and drop its chunks from the index without re-embedding."""
    global chunks, chunk_embeddings
    with rebuild_lock:
        path = UPLOAD_DIR / source_id
        # source_id must be a plain file name inside UPLOAD_DIR (no path traversal).
        if Path(source_id).name != source_id or not path.is_file():
            raise FileNotFoundError(source_id)
        path.unlink()

        manifest = load_manifest()
        if manifest.pop(source_id, None) is not None:
            save_manifest(manifest)

        with index_lock:
            keep = [i for i, item in enumerate(chunks) if item["source_id"] != source_id]
            removed = len(chunks) - len(keep)
            if removed:
                chunks = [chunks[i] for i in keep]
                if chunks and chunk_embeddings is not None:
                    chunk_embeddings = chunk_embeddings[keep]
                    persist_index()
                else:
                    chunks = []
                    chunk_embeddings = None
                    INDEX_PATH.unlink(missing_ok=True)
                    EMBEDDINGS_PATH.unlink(missing_ok=True)
        return removed


def retrieve(
    question: str, top_k: int = 4, min_score: float | None = None, rerank: bool | None = None,
) -> list[dict[str, Any]]:
    """Best passages for the question, most relevant first.

    Passages must reach `min_score` semantic similarity. If reranking is on (the
    default when a reranker is configured), the reranker reorders the best
    candidates; `score` stays the semantic similarity either way.
    """
    if min_score is None:
        min_score = MIN_SCORE
    if rerank is None:
        rerank = bool(RERANKER_ID)
    rerank = rerank and bool(RERANKER_ID)
    with index_lock:
        if not chunks or chunk_embeddings is None:
            return []
        # Only search chunks embedded with the current search model; vectors from
        # another model are not comparable even when they have the same size.
        current = [i for i, item in enumerate(chunks) if item.get("index_version") == INDEX_VERSION]
        if not current:
            return []
        current_chunks = [chunks[i] for i in current]
        current_embeddings = chunk_embeddings[current]

    vector = get_embedder().encode(
        QUERY_PREFIX + question,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32)
    scores = current_embeddings @ vector
    limit = max(top_k, RERANK_CANDIDATES) if rerank else top_k
    results = []
    for idx in np.argsort(-scores, kind="stable")[:limit]:
        score = float(scores[int(idx)])
        if score < min_score:
            break  # scores are sorted, so the rest are lower too
        item = dict(current_chunks[int(idx)])
        item["score"] = score
        results.append(item)
    if rerank and results:
        rerank_scores = get_reranker().predict(
            [(question, item["text"]) for item in results], show_progress_bar=False,
        )
        for item, value in zip(results, rerank_scores):
            item["rerank_score"] = float(value)
        results.sort(key=lambda item: item["rerank_score"], reverse=True)
    return results[:top_k]


CITATION_GROUP = re.compile(r"\[\s*(S\d+(?:\s*,\s*S\d+)*)\s*\]")


def clean_citations(answer: str, source_count: int) -> tuple[str, list[str]]:
    """Drop citation labels like [S7] that don't refer to a retrieved source."""
    valid = {f"S{i}" for i in range(1, source_count + 1)}
    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        labels = [label.strip() for label in match.group(1).split(",")]
        kept = [label for label in labels if label in valid]
        removed.extend(label for label in labels if label not in valid)
        return f"[{', '.join(kept)}]" if kept else ""

    cleaned = CITATION_GROUP.sub(replace, answer)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, removed


def format_pages(first: int | None, last: int | None, prefix: str = "") -> str:
    if not first:
        return ""
    if last and last != first:
        return f"{prefix}pages {first}-{last}"
    return f"{prefix}page {first}"


NO_SOURCES_ANSWER = (
    "The indexed documents do not contain passages relevant enough to answer this question."
)
SYSTEM_PROMPT = "Be accurate, concise, and grounded in provided evidence."


def build_prompt(question: str, sources: list[dict[str, Any]]) -> str:
    source_blocks = []
    for i, item in enumerate(sources, start=1):
        location = format_pages(item.get("page"), item.get("page_end"), prefix=", ")
        source_blocks.append(
            f"[S{i}] (from {item['source_name']}{location}): {item['text']}"
        )
    evidence = "\n\n".join(source_blocks)

    return (
        "You are AfriSearch, a careful document research assistant.\n"
        "Answer using only the source passages. Cite supported claims with labels such as [S1]. "
        "If the evidence does not answer the question, clearly say that the available documents "
        "do not provide enough information. Do not invent facts, numbers, or citations.\n\n"
        f"SOURCE PASSAGES:\n{evidence}\n\nQUESTION: {question}\n\n"
        # Small models otherwise tend to echo a source header instead of answering.
        "Write the answer in full sentences, each followed by the label of the passage "
        'that supports it, e.g. "... once a year [S1]."'
    )


def generate_answer(question: str, sources: list[dict[str, Any]], provider: str) -> str:
    if not sources:
        return NO_SOURCES_ANSWER
    return llm.generate(provider, SYSTEM_PROMPT, build_prompt(question, sources))


@app.get("/")
def root():
    return {
        "name": "AfriSearch AI API",
        "version": "0.1.0",
        "docs": "/docs",
        "index_ready": bool(chunks),
    }


@app.get("/providers")
def list_providers():
    return {
        "providers": [provider.describe() for provider in llm.PROVIDERS.values()],
        "default": llm.default_provider(),
    }


@app.get("/health")
def health():
    return {"status": "ok", "indexed_chunks": len(chunks), **search_settings()}


def search_settings() -> dict[str, Any]:
    languages, reason = ocr_status()
    return {"embedder": EMBEDDER_ID, "reranker": RERANKER_ID or None,
            "ocr": {"available": reason is None, "languages": languages, "reason": reason}}


@app.post("/documents/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    saved = []
    errors = []
    manifest = load_manifest()
    # Hashes of files already stored, so the same document isn't indexed twice.
    known_hashes = {
        file_sha256(path.read_bytes()): manifest.get(path.name, path.name)
        for path in UPLOAD_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    }

    for upload in files:
        original_name = Path(upload.filename or "upload.txt").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            errors.append({"filename": original_name,
                           "error": "Only PDF, TXT and images (PNG, JPG, TIFF, WebP, BMP) are supported."})
            continue

        content = await upload.read()
        if not content:
            errors.append({"filename": original_name, "error": "File is empty."})
            continue
        if len(content) > MAX_UPLOAD_BYTES:
            errors.append({"filename": original_name, "error": "File exceeds 15 MB limit."})
            continue
        digest = file_sha256(content)
        if digest in known_hashes:
            errors.append({
                "filename": original_name,
                "error": f"Duplicate of already uploaded file '{known_hashes[digest]}'.",
            })
            continue
        known_hashes[digest] = original_name

        # Unique stored names prevent accidental overwrite when filenames collide.
        stored_name = f"{uuid.uuid4().hex}_{re.sub(r'[^A-Za-z0-9._-]', '_', original_name)}"
        destination = UPLOAD_DIR / stored_name
        destination.write_bytes(content)
        manifest[stored_name] = original_name
        saved.append({"filename": original_name, "stored_name": stored_name, "bytes": len(content)})

    if saved:
        save_manifest(manifest)

    return {"saved": saved, "errors": errors, "message": "Upload finished. Index the documents to search new files."}


@app.post("/documents/index")
def index_documents(full: bool = False):
    """Index new uploads. Pass ?full=true to re-extract and re-embed every document."""
    try:
        result = rebuild_index(full=full)
    except Exception as exc:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc
    message = f"Added {len(result['new_documents'])} document(s); {result['indexed_chunks']} chunks indexed in total."
    if result["failed"]:
        message += f" {len(result['failed'])} file(s) could not be indexed."
    return {**result, "message": message}


@app.get("/documents")
def list_documents():
    unique = {}
    stale, ocr = set(), set()
    for item in chunks:
        unique[item["source_id"]] = item["source_name"]
        if item.get("index_version") != INDEX_VERSION:
            stale.add(item["source_id"])
        if item.get("ocr"):
            ocr.add(item["source_id"])
    return {"documents": [{"source_id": key, "source_name": name, "ocr": key in ocr}
                          for key, name in unique.items()],
            "indexed_chunks": len(chunks),
            # Documents indexed with another search model or chunking; re-index to search them.
            "stale_documents": len(stale),
            **search_settings()}


@app.delete("/documents/{source_id}")
def delete_document(source_id: str):
    try:
        removed = remove_document(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return {"source_id": source_id, "removed_chunks": removed,
            "message": f"Deleted document and {removed} indexed chunks."}


def check_index_ready() -> None:
    if not chunks or chunk_embeddings is None:
        raise HTTPException(status_code=400, detail="No documents indexed yet. Upload files and call /documents/index.")
    if not any(item.get("index_version") == INDEX_VERSION for item in chunks):
        raise HTTPException(
            status_code=409,
            detail="The search model or chunk settings changed. Re-index the documents "
                   "(Upload and index, or POST /documents/index) before asking.",
        )


def choose_provider(request: AskRequest) -> str | None:
    if not request.generate_answer:
        return None
    provider = request.provider or llm.default_provider()
    if provider not in llm.PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unavailable provider: {provider}. See GET /providers.",
        )
    return provider


def source_payload(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "label": f"S{i}",
            "source_name": item["source_name"],
            "page": item["page"],
            "page_end": item.get("page_end", item["page"]),
            "score": round(item["score"], 4),
            "rerank_score": round(item["rerank_score"], 4) if "rerank_score" in item else None,
            "ocr": item.get("ocr", False),
            "text": item["text"],
        }
        for i, item in enumerate(sources, start=1)
    ]


def search_summary(request: AskRequest, provider: str | None, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "question": request.question,
        "provider": provider,
        "model": llm.PROVIDERS[provider].model if provider else None,
        "reranked": any("rerank_score" in item for item in sources),
        "sources": source_payload(sources),
    }


@app.post("/ask")
def ask(request: AskRequest):
    check_index_ready()
    provider = choose_provider(request)
    sources = retrieve(request.question, request.top_k, rerank=request.rerank)
    answer = None
    removed_citations: list[str] = []
    if provider:
        try:
            answer = generate_answer(request.question, sources, provider)
        except llm.ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            # SDK errors: bad API key, rate limits, network, model download, GPU memory...
            logger.exception("Answer generation with %s failed", provider)
            raise HTTPException(status_code=502, detail=f"{provider} failed: {exc}") from exc
        answer, removed_citations = clean_citations(answer, len(sources))
    return {**search_summary(request, provider, sources), "answer": answer, "removed_citations": removed_citations}


@app.post("/ask/stream")
def ask_stream(request: AskRequest):
    """Like /ask, but streams newline-delimited JSON events as the answer is written.

    Events: {"type": "sources", ...} first (same fields as /ask minus the answer),
    then {"type": "token", "text": ...} pieces, then {"type": "done", "answer",
    "removed_citations"} with citations cleaned, or {"type": "error", "detail"}.
    """
    check_index_ready()
    provider = choose_provider(request)
    if provider:
        reason = llm.PROVIDERS[provider].unavailable_reason()
        if reason:
            raise HTTPException(status_code=400, detail=f"{llm.PROVIDERS[provider].label} is not available: {reason}")
    sources = retrieve(request.question, request.top_k, rerank=request.rerank)

    def event(kind: str, **fields: Any) -> str:
        return json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n"

    def events():
        yield event("sources", **search_summary(request, provider, sources))
        if not provider:
            yield event("done", answer=None, removed_citations=[])
            return
        pieces: list[str] = []
        try:
            if not sources:
                pieces.append(NO_SOURCES_ANSWER)
                yield event("token", text=NO_SOURCES_ANSWER)
            else:
                for piece in llm.stream(provider, SYSTEM_PROMPT, build_prompt(request.question, sources)):
                    pieces.append(piece)
                    yield event("token", text=piece)
        except llm.ProviderError as exc:
            yield event("error", detail=str(exc))
            return
        except Exception as exc:
            logger.exception("Answer generation with %s failed", provider)
            yield event("error", detail=f"{provider} failed: {exc}")
            return
        answer, removed = clean_citations("".join(pieces), len(sources))
        yield event("done", answer=answer, removed_citations=removed)

    return StreamingResponse(events(), media_type="application/x-ndjson")


# Load previously persisted index on module import as well, useful in some reload setups.
load_index_from_disk()
