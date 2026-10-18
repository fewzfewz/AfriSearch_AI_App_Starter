"""Grading rules for the evaluation set.

Answers are graded with simple, deterministic checks (no AI judge), so a run
costs nothing extra and gives the same score every time:

- answerable question: correct if the answer contains every required fact,
  where each fact lists accepted wordings (e.g. ["13", "thirteen"]);
- unanswerable question: correct if nothing relevant was retrieved or the
  answer says the documents don't cover it.

Keyword checks can miss a correct answer phrased unexpectedly, so read the
failures the script prints rather than trusting the numbers alone.
"""
from __future__ import annotations

import re
from typing import Any

_ADVERB = r"(?:explicitly |specifically |directly |clearly )?"
REFUSAL = re.compile(
    rf"(?:do|does|did) not {_ADVERB}(?:provide|contain|mention|include|say|have|cover|specify|state|address)"
    rf"|(?:don't|doesn't|didn't) {_ADVERB}(?:provide|contain|mention|include|say|have|cover|specify|state|address)"
    rf"|not (?:enough|sufficient) information|no information"
    rf"|not {_ADVERB}(?:mentioned|provided|stated|covered|specified|addressed)"
    rf"|(?:cannot|can't|unable to) (?:find|answer|determine)",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[\s*(S\d+(?:\s*,\s*S\d+)*)\s*\]")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def contains_all(answer: str, must_include: list[list[str]]) -> bool:
    """True if, for every fact, at least one accepted wording appears in the answer."""
    text = normalize(answer)
    return all(any(normalize(option) in text for option in fact) for fact in must_include)


def is_refusal(answer: str) -> bool:
    return bool(REFUSAL.search(answer))


def cited_source_names(answer: str, sources: list[dict[str, Any]]) -> set[str]:
    """Names of the documents behind the [S#] labels the answer cites."""
    names = set()
    for group in CITATION.findall(answer):
        for label in group.split(","):
            index = int(label.strip()[1:]) - 1
            if 0 <= index < len(sources):
                names.add(sources[index]["source_name"])
    return names


def retrieval_rank(sources: list[dict[str, Any]], expected: str) -> int | None:
    """1-based rank of the first passage from the expected document, or None."""
    for rank, source in enumerate(sources, start=1):
        if source["source_name"] == expected:
            return rank
    return None


def grade(question: dict[str, Any], answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if question.get("source") is None:
        return {
            "answerable": False,
            "correct": not sources or is_refusal(answer),
            "cites_source": None,
        }
    return {
        "answerable": True,
        "correct": contains_all(answer, question["must_include"]),
        "cites_source": question["source"] in cited_source_names(answer, sources),
    }
