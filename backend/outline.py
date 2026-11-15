"""Hierarchical document outline and Table of Contents extraction for books and large reports."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("afrisearch.outline")


def extract_outline(
    path: Path | None,
    pages: list[tuple[int | None, str]],
) -> list[dict[str, Any]]:
    """Extract or detect the hierarchical chapter outline of a document.

    Checks:
    1. Native PDF bookmarks/outline (via pypdfium2 if available).
    2. Printed Table of Contents pages near the start of the document (with offset calibration).
    3. Structural chapter heading regex patterns throughout the pages.
    """
    total_pages = len(pages)
    if total_pages == 0:
        return []

    # 1. Native PDF outline (bookmarks)
    if path and path.suffix.lower() == ".pdf":
        try:
            import pypdfium2
            pdf = pypdfium2.PdfDocument(str(path))
            toc = list(pdf.get_toc())
            outline = []
            if toc:
                for item in toc:
                    title = (item.title or "").strip()
                    if title and item.page_index is not None:
                        outline.append({
                            "title": title,
                            "page": item.page_index + 1,  # 1-indexed PDF page
                            "level": getattr(item, "level", 1) + 1,
                        })
            pdf.close()
            if outline:
                return _fill_page_ends(outline, total_pages)
        except Exception as exc:
            logger.debug("Native PDF TOC extraction skipped: %s", exc)

    # 2. Printed Table of Contents pages (with multi-page continuation)
    toc_text = ""
    toc_start_idx = -1
    toc_end_idx = -1
    in_toc = False

    for idx, (p_num, text) in enumerate(pages[:40]):
        text_clean = text.replace("\r", "")
        text_lower = text_clean.lower()
        has_toc_heading = "table of contents" in text_lower or (idx < 10 and "contents" in text_lower[:80])
        has_dot_leaders = "....." in text_clean or "......." in text_clean

        if has_toc_heading:
            in_toc = True
            toc_start_idx = idx if toc_start_idx == -1 else toc_start_idx
            toc_end_idx = idx
            toc_text += "\n" + text_clean
        elif in_toc and has_dot_leaders:
            toc_end_idx = idx
            toc_text += "\n" + text_clean
        elif in_toc and not has_dot_leaders and idx > (toc_end_idx + 1):
            break

    if toc_text:
        raw_items: list[dict[str, Any]] = []
        pattern = re.compile(
            r"^\s*([^\r\n]{2,100}?)\s*\.{2,}\s*([0-9]{1,5})\s*$",
            re.MULTILINE,
        )
        for match in pattern.finditer(toc_text):
            title = match.group(1).strip()
            try:
                page_target = int(match.group(2).strip())
            except ValueError:
                continue

            if len(title) >= 2 and not title.isdigit():
                title = re.sub(r"[\s.]+$", "", title)
                level = 1 if re.match(r"^(?:[0-9]+[.)]|chapter\b|part\b)", title, re.IGNORECASE) else 2
                raw_items.append({
                    "title": title,
                    "printed_page": page_target,
                    "level": level,
                })

        if raw_items:
            # Calibrate offset between printed pages and PDF pages
            offset = _calibrate_page_offset(raw_items, pages, toc_end_idx)
            outline: list[dict[str, Any]] = []
            for item in raw_items:
                actual_page = min(total_pages, max(1, item["printed_page"] + offset))
                outline.append({
                    "title": item["title"],
                    "page": actual_page,
                    "level": item["level"],
                })
            return _fill_page_ends(outline, total_pages)

    # 3. Chapter heading heuristics across pages
    outline = []
    chapter_pattern = re.compile(
        r"^\s*(chapter\s+[0-9ivxlcdm]+[:\s–—-]+[^\r\n]{3,60}|[0-9]{1,2}\.\s+[A-Z][A-Za-z0-9\s–—]{3,50})\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    for p_num, text in pages:
        clean_text = text.replace("\r", "")
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
        for line in lines[:4]:
            match = chapter_pattern.match(line)
            if match:
                title = match.group(1).strip()
                if not any(item["title"].lower() == title.lower() for item in outline):
                    outline.append({
                        "title": title,
                        "page": p_num or 1,
                        "level": 1,
                    })
                break

    return _fill_page_ends(outline, total_pages)


def _calibrate_page_offset(
    raw_items: list[dict[str, Any]],
    pages: list[tuple[int | None, str]],
    toc_end_idx: int,
) -> int:
    """Find the offset between printed page numbers in TOC and 1-indexed document pages."""
    if not raw_items or not pages:
        return 0

    first_item = raw_items[0]
    printed_page = first_item["printed_page"]
    title_words = [w.lower() for w in re.findall(r"\w+", first_item["title"]) if len(w) > 3]

    search_start = max(0, toc_end_idx)
    search_end = min(len(pages), search_start + 25)

    for idx in range(search_start, search_end):
        p_num, text = pages[idx]
        text_lower = text.lower()
        if title_words and sum(1 for w in title_words if w in text_lower) >= max(1, len(title_words) // 2):
            actual_pdf_page = idx + 1
            calculated_offset = actual_pdf_page - printed_page
            if 0 <= calculated_offset < len(pages):
                return calculated_offset

    if toc_end_idx > 0 and printed_page == 1:
        return toc_end_idx

    return 0


def _fill_page_ends(outline: list[dict[str, Any]], total_pages: int) -> list[dict[str, Any]]:
    """Sort outline by page number and compute page_end for each entry considering hierarchy."""
    if not outline:
        return []

    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for item in outline:
        key = (item["title"].lower(), item["page"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    deduped.sort(key=lambda x: (x["page"], x.get("level", 1)))

    for i in range(len(deduped)):
        current_level = deduped[i].get("level", 1)
        current_page = deduped[i]["page"]

        found_end = False
        # Look ahead for next item of same or higher hierarchy (level <= current_level)
        for j in range(i + 1, len(deduped)):
            next_item = deduped[j]
            if next_item.get("level", 1) <= current_level and next_item["page"] > current_page:
                deduped[i]["page_end"] = next_item["page"] - 1
                found_end = True
                break

        if not found_end:
            # Look ahead for any next item with a greater page
            for j in range(i + 1, len(deduped)):
                if deduped[j]["page"] > current_page:
                    deduped[i]["page_end"] = deduped[j]["page"] - 1
                    found_end = True
                    break

        if not found_end:
            deduped[i]["page_end"] = total_pages

    return deduped


def match_outline_target(
    question: str,
    outline: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Check if the question specifically references an outline chapter or section.

    Examples:
    - "What does Chapter 5 say?" -> matches "5. HTML – FORMATTING"
    - "Explain the section on HTML tables" -> matches "10. HTML – TABLES"
    """
    if not outline:
        return None

    q_lower = question.lower()

    # 1. Direct Chapter number match: e.g. "chapter 5", "ch 5", "section 10"
    num_match = re.search(r"\b(?:chapter|ch\.?|section|sec\.?)\s*([0-9]+)\b", q_lower)
    if num_match:
        target_num = num_match.group(1)
        for item in outline:
            if re.match(rf"^(?:chapter\s+)?{target_num}[.:\s]", item["title"], re.IGNORECASE):
                return item

    # 2. Topic / title keyword match
    best_item = None
    best_score = 0
    q_words = set(re.findall(r"\w+", q_lower))

    for item in outline:
        title_words = set(re.findall(r"\w+", item["title"].lower()))
        significant = {w for w in title_words if len(w) > 3 and w not in {"html", "page", "section", "chapter", "tutorial"}}
        if significant and significant.issubset(q_words):
            if len(significant) > best_score:
                best_score = len(significant)
                best_item = item

    return best_item
