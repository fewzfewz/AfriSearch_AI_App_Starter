"""Pure numpy BM25 Okapi implementation with inverted indexing and Reciprocal Rank Fusion."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np

# Tokenizer that captures words, hyphenated words, chapter numbers, and technical tokens like tags
TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]{2,}\b")


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase keywords, filtering single-character noise."""
    return TOKEN_PATTERN.findall(text.lower())


class BM25Index:
    """Fast in-memory BM25 Okapi index using an inverted list."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_count = len(corpus)

        tokenized_corpus = [tokenize(doc) for doc in corpus]
        self.doc_lens = np.array([len(doc) for doc in tokenized_corpus], dtype=np.float32)
        self.avgdl = float(np.mean(self.doc_lens)) if self.doc_count > 0 else 1.0

        # Build inverted index: term -> list of (doc_idx, frequency)
        self.inverted: dict[str, list[tuple[int, int]]] = {}
        df = Counter()
        for i, doc in enumerate(tokenized_corpus):
            counts = Counter(doc)
            for term, freq in counts.items():
                df[term] += 1
                if term not in self.inverted:
                    self.inverted[term] = []
                self.inverted[term].append((i, freq))

        # Precompute IDF for each term: ln(1 + (N - df + 0.5) / (df + 0.5))
        self.idf: dict[str, float] = {}
        for term, freq in df.items():
            self.idf[term] = math.log(1.0 + (self.doc_count - freq + 0.5) / (freq + 0.5))

    def score(self, query: str | list[str]) -> np.ndarray:
        """Compute BM25 Okapi scores for all documents in the corpus."""
        tokens = query if isinstance(query, list) else tokenize(query)
        scores = np.zeros(self.doc_count, dtype=np.float32)
        if not tokens or self.doc_count == 0:
            return scores

        query_counts = Counter(tokens)
        for term, q_freq in query_counts.items():
            if term not in self.inverted:
                continue
            idf_val = self.idf[term]
            for doc_id, freq in self.inverted[term]:
                dl = self.doc_lens[doc_id]
                denom = freq + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                scores[doc_id] += idf_val * (freq * (self.k1 + 1.0)) / denom

        return scores


def reciprocal_rank_fusion(
    dense_scores: np.ndarray,
    bm25_scores: np.ndarray,
    k: int = 60,
    dense_weight: float = 0.65,
    bm25_weight: float = 0.35,
) -> np.ndarray:
    """Combine dense semantic similarity and BM25 lexical scores using Reciprocal Rank Fusion.

    Documents with zero BM25 hits only receive their dense rank component without artificial lexical boost.
    """
    n = len(dense_scores)
    if n == 0:
        return np.zeros(0, dtype=np.float32)

    dense_order = np.argsort(-dense_scores)
    dense_ranks = np.empty_like(dense_order)
    dense_ranks[dense_order] = np.arange(n)

    bm25_order = np.argsort(-bm25_scores)
    bm25_ranks = np.empty_like(bm25_order)
    bm25_ranks[bm25_order] = np.arange(n)

    rrf = dense_weight / (k + dense_ranks)
    has_bm25 = bm25_scores > 0
    rrf[has_bm25] += bm25_weight / (k + bm25_ranks[has_bm25])
    return rrf.astype(np.float32)
