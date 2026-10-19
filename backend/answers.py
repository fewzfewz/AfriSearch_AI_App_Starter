"""Turning retrieved passages into a cited answer."""
from __future__ import annotations

from typing import Any

from backend import llm, models
from backend.text import format_pages, is_ethiopic

NO_SOURCES_ANSWER = (
    "The indexed documents do not contain passages relevant enough to answer this question."
)
NOT_COVERED_ANSWER = (
    "The documents don't seem to cover this question. The closest passages are listed below in case they help."
)
SYSTEM_PROMPT = "Be accurate, concise, and grounded in provided evidence."
# How much of the conversation a follow-up question sees.
HISTORY_TURNS = 2
HISTORY_CHARS = 600
# Questions this short in a chat are treated as follow-ups ("and the SB-500?") and
# searched together with the previous question.
FOLLOW_UP_WORDS = 8


def is_covered(sources: list[dict[str, Any]]) -> bool:
    """Whether the passages plausibly answer the question (see models.MIN_RERANK_SCORE)."""
    if not sources:
        return False
    best = sources[0].get("rerank_score")
    return best is None or best >= models.MIN_RERANK_SCORE


def focus(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop reranked passages far below the best one (see models.RERANK_GAP)."""
    if not sources or sources[0].get("rerank_score") is None:
        return sources
    floor = sources[0]["rerank_score"] - models.RERANK_GAP
    return [item for item in sources if item["rerank_score"] >= floor]


def search_query(question: str, history: list[dict[str, str]]) -> str:
    """A short question together with the previous one, for follow-ups that need context."""
    previous = [turn["question"] for turn in history if turn.get("question")]
    if previous and len(question.split()) <= FOLLOW_UP_WORDS:
        return f"{previous[-1]} {question}"
    return question


def language_instruction(question: str) -> str:
    if is_ethiopic(question):
        return "The question is written in Amharic (Ge'ez script). Write the answer in Amharic."
    return "Write the answer in the same language as the question."


def build_prompt(question: str, sources: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> str:
    source_blocks = []
    for i, item in enumerate(sources, start=1):
        location = format_pages(item.get("page"), item.get("page_end"), prefix=", ")
        source_blocks.append(f"[S{i}] (from {item['source_name']}{location}): {item['text']}")
    evidence = "\n\n".join(source_blocks)

    conversation = ""
    if history:
        turns = [f"Q: {turn['question']}\nA: {turn['answer'][:HISTORY_CHARS]}"
                 for turn in history[-HISTORY_TURNS:] if turn.get("answer")]
        if turns:
            conversation = ("EARLIER IN THIS CONVERSATION (context only; cite only the passages):\n"
                            + "\n\n".join(turns) + "\n\n")

    return (
        "You are AfriSearch, a careful document research assistant.\n"
        "Answer using only the source passages. Cite supported claims with labels such as [S1]. "
        "If the evidence does not answer the question, clearly say that the available documents "
        "do not provide enough information. Do not invent facts, numbers, or citations.\n\n"
        f"{conversation}SOURCE PASSAGES:\n{evidence}\n\nQUESTION: {question}\n\n"
        f"{language_instruction(question)} "
        # Small models otherwise tend to echo a source header instead of answering.
        "Write the answer in full sentences, each followed by the label of the passage "
        'that supports it, e.g. "... once a year [S1]."'
    )


def generate_answer(
    question: str, sources: list[dict[str, Any]], provider: str, history: list[dict[str, str]] | None = None,
) -> str:
    if not sources:
        return NO_SOURCES_ANSWER
    if not is_covered(sources):
        return NOT_COVERED_ANSWER
    return llm.generate(provider, SYSTEM_PROMPT, build_prompt(question, sources, history))


def source_payload(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "label": f"S{i}",
            "source_id": item["source_id"],
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
