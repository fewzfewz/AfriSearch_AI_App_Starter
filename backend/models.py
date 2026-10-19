"""The search model (embedder) and the reranker, with their per-model settings."""
from __future__ import annotations

import os
import threading

from sentence_transformers import CrossEncoder, SentenceTransformer

from backend import config

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
# Set by set_embedder(): the search model, its prefixes, and the INDEX_VERSION
# stored on each chunk (documents indexed with other settings are re-embedded).
EMBEDDER_ID = DEFAULT_EMBEDDER
QUERY_PREFIX = PASSAGE_PREFIX = ""
INDEX_VERSION = ""
# Passages scoring below this cosine similarity are treated as irrelevant.
MIN_SCORE = 0.0

# A cross-encoder reads the question and each of the best RERANK_CANDIDATES passages
# together and reorders them. On the evaluation set it raised "right document ranked
# first" from 32/39 to 36/39, at about 0.5 s per question on a laptop CPU.
# AFRISEARCH_RERANKER=off turns it off; requests can also skip it with rerank=false.
DEFAULT_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
RERANKER_ID = ""  # set by set_reranker(); empty means off
RERANK_CANDIDATES = 12
# When the best reranked passage scores below this, the documents are treated as
# not covering the question and the answer model isn't asked. On the evaluation
# set, -5 stopped 3 of 6 off-topic questions (2 without it) and no answerable one;
# the lowest answerable question scored -3.2. -4 stopped 5 of 6 but sits closer.
MIN_RERANK_SCORE = float(os.getenv("AFRISEARCH_MIN_RERANK_SCORE", "-5"))
# Passages scoring this far below the best reranked one are dropped before the
# answer model sees them: unrelated passages make small models mix up facts (in
# testing, Qwen 2.5 0.5B answered "once a month" instead of "every two weeks").
# On the evaluation set, any gap from 3 to 8 kept the right document for all 39
# questions; 5 drops 45% of passages.
RERANK_GAP = float(os.getenv("AFRISEARCH_RERANK_GAP", "5"))

# Guards lazy model loading so concurrent first requests load each model once.
model_lock = threading.Lock()
embedder: SentenceTransformer | None = None
reranker: CrossEncoder | None = None


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
        INDEX_VERSION = f"sentences-{config.CHUNK_SIZE}-{config.CHUNK_OVERLAP}|{EMBEDDER_ID}"
        if PASSAGE_PREFIX:
            INDEX_VERSION += f"|{PASSAGE_PREFIX}"
        embedder = None


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


set_embedder(os.getenv("AFRISEARCH_EMBEDDER", DEFAULT_EMBEDDER))
set_reranker(os.getenv("AFRISEARCH_RERANKER", DEFAULT_RERANKER))
