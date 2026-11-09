"""Pure text helpers: sentence splitting, chunking, citations and page labels."""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend import config

# Latin punctuation plus the Ethiopic full stop (።) and question mark (፧). Two
# Ethiopic wordspaces (፡፡) look identical to ። and are common in typed text and OCR output.
SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?።፧])|(?<=፡፡))\s+")
CITATION_GROUP = re.compile(r"\[\s*(S\d+(?:\s*,\s*S\d+)*)\s*\]")
ETHIOPIC = re.compile(r"[ሀ-፿]")


def is_table_row(line: str) -> bool:
    """Return True if line is formatted as a Markdown table row."""
    s = line.strip()
    return bool(s.startswith("|") and (s.endswith("|") or "|" in s[1:]))


def is_table_separator(line: str) -> bool:
    """Return True if line is a Markdown table header-separator row (e.g. | --- | :---: |)."""
    s = line.strip()
    if not is_table_row(s):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return len(cells) > 0 and all(set(c).issubset({"-", ":", " "}) and "-" in c for c in cells)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences while treating Markdown table rows as atomic units."""
    if "|" not in text:
        return [s.strip() for s in SENTENCE_BOUNDARY.split(text) if s.strip()]

    results: list[str] = []
    lines = text.splitlines()
    prose_buffer: list[str] = []

    def flush_prose():
        if prose_buffer:
            combined = "\n".join(prose_buffer).strip()
            if combined:
                for s in SENTENCE_BOUNDARY.split(combined):
                    s_clean = s.strip()
                    if s_clean:
                        results.append(s_clean)
            prose_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_prose()
            continue
        if is_table_row(stripped):
            flush_prose()
            results.append(stripped)
        else:
            prose_buffer.append(line)

    flush_prose()
    return results


@dataclass
class _ChunkUnit:
    page: int | None
    words: list[str]
    table_header: tuple[str, str] | None = None
    is_table_header_or_sep: bool = False


def _join_units(units: list[_ChunkUnit]) -> str:
    """Join units into chunk text, using newlines around table rows and spaces between prose."""
    parts: list[str] = []
    for i, u in enumerate(units):
        text = " ".join(u.words)
        if i == 0:
            parts.append(text)
        else:
            prev = units[i - 1]
            if is_table_row(text) or is_table_row(" ".join(prev.words)):
                parts.append("\n" + text)
            else:
                parts.append(" " + text)
    return "".join(parts)


def chunk_document(
    pages: list[tuple[int | None, str]],
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> list[tuple[int | None, int | None, str]]:
    """Group sentences into ~chunk_size-word chunks that may span pages.

    Chunks end on sentence boundaries where possible, and each chunk repeats
    the last ~overlap words of whole sentences from the previous one. When a
    Markdown table spans multiple chunks, the table header and separator rows
    are preserved at the start of subsequent chunk segments.
    Returns (first_page, last_page, text) tuples.
    """
    units: list[_ChunkUnit] = []
    current_table_header: tuple[str, str] | None = None

    for page, text in pages:
        sentences = split_sentences(text)
        i = 0
        while i < len(sentences):
            sentence = sentences[i]
            # Detect table start: row followed by table separator
            if (
                is_table_row(sentence)
                and not is_table_separator(sentence)
                and (i + 1 < len(sentences))
                and is_table_separator(sentences[i + 1])
            ):
                current_table_header = (sentence, sentences[i + 1])
                # Add header row
                header_words = sentence.split()
                for start in range(0, len(header_words), chunk_size):
                    units.append(_ChunkUnit(page, header_words[start : start + chunk_size], current_table_header, is_table_header_or_sep=True))
                # Add separator row
                sep_words = sentences[i + 1].split()
                for start in range(0, len(sep_words), chunk_size):
                    units.append(_ChunkUnit(page, sep_words[start : start + chunk_size], current_table_header, is_table_header_or_sep=True))
                i += 2
                continue

            if is_table_row(sentence):
                is_sep = is_table_separator(sentence)
                words = sentence.split()
                for start in range(0, len(words), chunk_size):
                    units.append(_ChunkUnit(page, words[start : start + chunk_size], current_table_header, is_table_header_or_sep=is_sep))
            else:
                # Non-table prose resets current table context
                current_table_header = None
                words = sentence.split()
                for start in range(0, len(words), chunk_size):
                    units.append(_ChunkUnit(page, words[start : start + chunk_size], None, is_table_header_or_sep=False))
            i += 1

    result: list[tuple[int | None, int | None, str]] = []
    current: list[_ChunkUnit] = []
    current_words = 0
    has_new = False

    def flush() -> None:
        if not current:
            return
        result.append((
            current[0].page,
            current[-1].page,
            _join_units(current),
        ))

    for unit in units:
        if current and current_words + len(unit.words) > chunk_size:
            flush()
            # Carry trailing sentences (up to `overlap` words) into the next chunk.
            carried: list[_ChunkUnit] = []
            carried_words = 0
            for prev in reversed(current):
                if carried_words + len(prev.words) > overlap:
                    break
                carried.insert(0, prev)
                carried_words += len(prev.words)

            # Table Header Preservation:
            # If the next chunk continues a table whose header was left behind,
            # inject the table header rows at the start of the next chunk.
            active_header = unit.table_header or (carried[0].table_header if carried else None)
            if active_header:
                has_header_already = any(
                    u.is_table_header_or_sep and u.table_header == active_header
                    for u in carried
                )
                if not has_header_already:
                    h_row, sep_row = active_header
                    hdr_unit = _ChunkUnit(carried[0].page if carried else unit.page, h_row.split(), active_header, is_table_header_or_sep=True)
                    sep_unit = _ChunkUnit(carried[0].page if carried else unit.page, sep_row.split(), active_header, is_table_header_or_sep=True)
                    carried = [hdr_unit, sep_unit] + carried
                    carried_words += len(hdr_unit.words) + len(sep_unit.words)

            current, current_words = carried, carried_words
            has_new = False

        current.append(unit)
        current_words += len(unit.words)
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
