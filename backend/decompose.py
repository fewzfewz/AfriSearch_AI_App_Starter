"""Agentic Query Decomposition for Multi-Hop, Comparative, and Multi-Aspect RAG."""
from __future__ import annotations

import re


def clean_query_term(term: str) -> str:
    """Strip question noise, punctuation, and leading/trailing articles."""
    t = term.strip().rstrip("?.!,;:")
    t = re.sub(r"^(?:the|a|an|both|all|each)\s+", "", t, flags=re.IGNORECASE)
    return t.strip()


def decompose_query(question: str) -> list[str]:
    """Decompose a complex, comparative, or multi-faceted question into focused subqueries.

    Returns a list of 1 to 4 distinct subqueries. If the question is simple,
    returns [question].
    """
    q = question.strip()
    if not q:
        return [q]

    # 1. Multi-chapter pattern: 'Chapter 2 ... and Chapter 5' or 'ch 2 vs ch 5'
    ch_matches = list(re.finditer(r"\b(?:chapter|ch\.?)\s*(\d+)", q, re.IGNORECASE))
    if len(ch_matches) >= 2:
        # Check if there are distinct subjects associated with each chapter
        comp_match = re.search(r"\b(?:compare|comparison of)\s+(.+?)\s+(?:with|against|and)\s+(.+)", q, re.IGNORECASE)
        if comp_match:
            p1 = clean_query_term(comp_match.group(1))
            p2 = clean_query_term(comp_match.group(2))
            if p1 and p2 and p1.lower() != p2.lower():
                return [p1, p2]

        subqueries = []
        clean_q = re.sub(r"\b(?:compare|comparison of|differences?|between|versus|vs\.?|and|with)\b", " ", q, flags=re.IGNORECASE)
        topic_words = " ".join([
            w for w in re.findall(r"\b\w+\b", clean_q)
            if not re.match(r"^(?:chapter|ch|\d+)$", w, re.IGNORECASE)
        ])
        for m in ch_matches:
            ch_num = m.group(1)
            sq = f"Chapter {ch_num} {topic_words}".strip()
            if sq not in subqueries:
                subqueries.append(sq)
        if len(subqueries) >= 2:
            return subqueries[:4]

    # 2. Dual-aspect pattern: 'pros and cons of X', 'advantages and disadvantages of X'
    dual_match = re.search(
        r"\b(?:what\s+are\s+the\s+)?(advantages|pros|benefits|strengths)\s+and\s+(disadvantages|cons|drawbacks|limitations|weaknesses)\s+(?:of|for)\s+(.+)",
        q,
        re.IGNORECASE,
    )
    if dual_match:
        subject = clean_query_term(dual_match.group(3))
        pos_aspect = dual_match.group(1).lower()
        neg_aspect = dual_match.group(2).lower()
        return [f"{pos_aspect} of {subject}", f"{neg_aspect} of {subject}"]

    # 3. Compare / vs pattern: 'compare A with B', 'difference between A and B', 'A vs B'
    comp_match = re.search(r"\b(?:compare|comparison of)\s+(.+?)\s+(?:with|against|and)\s+(.+)", q, re.IGNORECASE)
    if comp_match:
        p1 = clean_query_term(comp_match.group(1))
        p2 = clean_query_term(comp_match.group(2))
        if p1 and p2 and p1.lower() != p2.lower():
            return [p1, p2]

    diff_match = re.search(r"\bdifferences?\s+between\s+(.+?)\s+and\s+(.+)", q, re.IGNORECASE)
    if diff_match:
        p1 = clean_query_term(diff_match.group(1))
        p2 = clean_query_term(diff_match.group(2))
        if p1 and p2 and p1.lower() != p2.lower():
            return [p1, p2]

    vs_match = re.search(r"\b(.+?)\s+(?:vs\.?|versus)\s+(.+)", q, re.IGNORECASE)
    if vs_match:
        p1 = clean_query_term(vs_match.group(1))
        p2 = clean_query_term(vs_match.group(2))
        if p1 and p2 and p1.lower() != p2.lower():
            return [p1, p2]

    # 4. Multi-subject conjunction: 'explain/what about X as well as Y' or 'X and Y'
    as_well_match = re.search(r"(?:explain|describe|what\s+about|details\s+on)\s+(.+?)\s+as\s+well\s+as\s+(.+)", q, re.IGNORECASE)
    if as_well_match:
        p1 = clean_query_term(as_well_match.group(1))
        p2 = clean_query_term(as_well_match.group(2))
        if p1 and p2 and p1.lower() != p2.lower():
            return [p1, p2]

    return [q]
