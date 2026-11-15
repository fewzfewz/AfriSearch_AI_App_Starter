"""Multi-turn conversational coreference resolution and query rewriting for AfriSearch."""
from __future__ import annotations

import re
from typing import Any

PRONOUNS_AND_ANAPHORA = re.compile(
    r"\b(it|its|they|them|their|this|these|those|that|the same|above|aforementioned|former|latter|ones?)\b",
    re.IGNORECASE,
)
FOLLOW_UP_OPENERS = re.compile(
    r"^(?:and\b|what\s+about\b|how\s+about\b|also\b|additionally\b|furthermore\b)",
    re.IGNORECASE,
)
QUESTION_STOP_WORDS = {
    "the", "about", "does", "what", "with", "from", "this", "that", "have", "has",
    "chapter", "ch", "can", "you", "tell", "me", "show", "give", "explain", "describe",
    "please", "would", "could", "should", "will", "how", "why", "when", "where",
}


def extract_topic_entity(text: str) -> str:
    """Extract primary subject entities, chapter designations, and keywords from a question."""
    ch_match = re.search(r"\b(?:chapter|ch\.?)\s*(\d+)\b", text, re.IGNORECASE)
    ch_ref = f"Chapter {ch_match.group(1)}" if ch_match else ""

    cleaned = re.sub(
        r"^(?:what\s+does|what\s+is|what\s+are|how\s+does|how\s+do|explain|tell\s+me\s+about|describe)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:say\s+about|mean\s+by|discuss|cover)\s+", "", cleaned, flags=re.IGNORECASE)

    words = [
        w for w in re.findall(r"\b[a-zA-Z0-9_-]+\b", cleaned)
        if len(w) > 1 and w.lower() not in QUESTION_STOP_WORDS and not w.isdigit()
    ]
    topic = " ".join(words[:4])

    if ch_ref:
        return f"{ch_ref} {topic}".strip() if topic else ch_ref
    return topic


def rewrite_conversational_query(question: str, history: list[dict[str, str]] | None) -> str:
    """Rewrite a follow-up question in a chat to be standalone and self-contained for search.

    If the question is already independent or there is no history, returns question unchanged.
    """
    if not history:
        return question

    q = question.strip()
    if not q:
        return question

    has_pronoun = bool(PRONOUNS_AND_ANAPHORA.search(q))
    is_opener = bool(FOLLOW_UP_OPENERS.search(q))
    # Fragment follow-up e.g. "and the cost?", "any restrictions?"
    is_short_fragment = len(q.split()) <= 4 and not bool(re.search(r"\b(is|are|was|were|what|how)\b", q, re.IGNORECASE))

    if not (has_pronoun or is_opener or is_short_fragment):
        return question

    # Find the most recent substantive question in history
    for turn in reversed(history):
        prev_q = turn.get("question", "").strip()
        if not prev_q:
            continue

        entity = extract_topic_entity(prev_q)
        if not entity:
            continue

        # If current question already contains the core topic words, do not duplicate
        entity_words = [w.lower() for w in entity.split() if len(w) > 2]
        if any(w in q.lower() for w in entity_words):
            return question

        return f"{entity} {q}"

    return question
