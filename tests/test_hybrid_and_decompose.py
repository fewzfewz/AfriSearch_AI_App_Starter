import pytest
import numpy as np
from backend.bm25 import BM25Index, reciprocal_rank_fusion, tokenize
from backend.decompose import decompose_query


def test_bm25_tokenization_and_scoring():
    corpus = [
        "HTML basic tags include paragraph p tag, heading h1 tag, and body tag.",
        "HTML formatting features bold b tag, italic i tag, underline u tag, and strikethrough.",
        "Solar panel cleaning should happen every month with soft brush and water.",
        "Inverter inspection must occur once a year by qualified electrical technician.",
    ]
    bm25 = BM25Index(corpus)
    assert bm25.doc_count == 4
    assert len(bm25.inverted) > 10

    # Formatting query should score doc 1 highest
    scores = bm25.score("HTML formatting bold italic")
    assert scores[1] > scores[0]
    assert scores[2] == 0.0
    assert scores[3] == 0.0

    # Solar cleaning query should score doc 2 highest
    solar_scores = bm25.score("solar cleaning water")
    assert solar_scores[2] > 0.0
    assert solar_scores[0] == 0.0


def test_reciprocal_rank_fusion():
    dense_scores = np.array([0.70, 0.85, 0.65], dtype=np.float32)
    bm25_scores = np.array([2.5, 0.0, 1.0], dtype=np.float32)

    fused = reciprocal_rank_fusion(dense_scores, bm25_scores, k=60)
    assert len(fused) == 3
    # Doc 0 has high BM25 and decent dense score
    assert fused[0] > fused[2]


def test_query_decomposition():
    # Comparative queries
    subs = decompose_query("Compare Chapter 2 basic tags with Chapter 5 formatting")
    assert len(subs) == 2
    assert "Chapter 2 basic tags" in subs[0]
    assert "Chapter 5 formatting" in subs[1]

    # Versus queries
    subs_vs = decompose_query("HTML pre tag vs HTML p tag")
    assert subs_vs == ["HTML pre tag", "HTML p tag"]

    # Differences between
    subs_diff = decompose_query("What are the differences between solar panels and inverters?")
    assert subs_diff == ["solar panels", "inverters"]

    # Advantages and disadvantages
    subs_dual = decompose_query("What are the advantages and disadvantages of SQLite?")
    assert len(subs_dual) == 2
    assert any("advantages" in s for s in subs_dual)
    assert any("disadvantages" in s for s in subs_dual)

    # Standard single query
    single = decompose_query("How do I format text in HTML?")
    assert single == ["How do I format text in HTML?"]
