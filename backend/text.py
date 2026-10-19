"""Pure text helpers: sentence splitting, chunking, citations and page labels."""
from __future__ import annotations

import re

from backend import config

# Latin punctuation plus the Ethiopic full stop (።) and question mark (፧). Two
# Ethiopic wordspaces (፡፡) look identical to ። and are common in typed text and OCR output.
SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?።፧])|(?<=፡፡))\s+")
CITATION_GROUP = re.compile(r"\[\s*(S\d+(?:\s*,\s*S\d+)*)\s*\]")
ETHIOPIC = re.compile(r"[ሀ-፿]")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_BOUNDARY.split(text) if s.strip()]


def chunk_document(
    pages: list[tuple[int | None, str]],
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
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


def page_range(first: int | None, last: int | None) -> set[int | None]:
    return {None} if first is None else set(range(first, (last or first) + 1))


def is_ethiopic(text: str) -> bool:
    """True when most letters are Ethiopic script (Amharic, Tigrinya, ...)."""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(bool(ETHIOPIC.match(c)) for c in letters) / len(letters) > 0.5
