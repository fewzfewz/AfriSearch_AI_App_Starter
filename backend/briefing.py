"""Executive Briefing & Smart Auto-Summarization for AfriSearch.

Produces a structured 1-page executive brief, key takeaways with page citations,
structural outline synthesis, and interactive suggested questions for any document.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

from backend import llm

logger = logging.getLogger("afrisearch.briefing")


def extract_sample_passages(passages: list[dict[str, Any]], max_count: int = 8) -> list[dict[str, Any]]:
    """Sample representative passages across beginning, middle, and end of the document."""
    if not passages:
        return []
    total = len(passages)
    if total <= max_count:
        return passages

    indices: set[int] = {0, 1}
    mid = total // 2
    indices.update({mid - 1, mid, mid + 1})
    indices.update({total - 2, total - 1})

    # Fill up to max_count with evenly spaced points
    step = total // (max_count + 1)
    if step > 0:
        for i in range(step, total, step):
            indices.add(i)
            if len(indices) >= max_count:
                break

    return [passages[i] for i in sorted(indices) if i < total]


def build_briefing_prompt(
    doc_name: str,
    outline: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    total_pages: int = 1,
) -> tuple[str, str]:
    """Construct system prompt and user prompt for generating an executive brief."""
    system_prompt = (
        "You are AfriSearch, an elite research analyst and intelligence briefing officer. "
        "Your task is to produce a high-impact, authoritative 1-page executive briefing for a document. "
        "Extract critical metrics, core takeaways with page citations, and insightful questions for discussion."
    )

    outline_lines = [f"- {item['title']} (page {item.get('page', 1)})" for item in outline[:25]]
    outline_text = "\n".join(outline_lines) if outline_lines else "No formal table of contents available."

    sample_passages = extract_sample_passages(passages, max_count=8)
    evidence_lines = [f"[Page {p.get('page', 1)}]: {p['text']}" for p in sample_passages]
    evidence_text = "\n\n".join(evidence_lines)

    user_prompt = (
        f"Generate an executive briefing for the document '{doc_name}' (Total Pages: {total_pages}).\n\n"
        f"CHAPTER OUTLINE:\n{outline_text}\n\n"
        f"KEY EXTRACTED EVIDENCE & PASSAGES:\n{evidence_text}\n\n"
        "Provide your briefing in clean GitHub-flavored Markdown following this exact structure:\n\n"
        "# Executive Headline\n"
        "One bold, authoritative sentence summarizing what this document is and its core significance.\n\n"
        "# Executive Summary\n"
        "A crisp, 2-paragraph overview synthesizing the purpose, key context, methodology or framework, and overall conclusions.\n\n"
        "# Key Takeaways & Core Findings\n"
        "- **[Finding 1 Title]**: Specific factual takeaway with numbers, dates, or data points where available. [p. X]\n"
        "- **[Finding 2 Title]**: Specific factual takeaway. [p. Y]\n"
        "- **[Finding 3 Title]**: Specific factual takeaway. [p. Z]\n"
        "(Include 4 to 6 high-impact bulleted takeaways, each citing the page number in format `[p. X]`)\n\n"
        "# Structure & Core Themes\n"
        "Brief breakdown of how the document is organized and its primary thematic sections.\n\n"
        "# Suggested Questions to Ask\n"
        "- [Question 1: a specific, insightful inquiry someone reading this document should ask]\n"
        "- [Question 2: another high-value inquiry]\n"
        "- [Question 3: another high-value inquiry]\n"
        "- [Question 4: another high-value inquiry]\n\n"
        "Important: Ground all claims in the provided evidence and format citations as `[p. X]`."
    )

    return system_prompt, user_prompt


def parse_briefing_markdown(markdown_text: str) -> dict[str, Any]:
    """Parse generated Markdown into structured executive brief fields."""
    result: dict[str, Any] = {
        "headline": "",
        "summary": "",
        "takeaways": [],
        "structure": [],
        "suggested_questions": [],
        "markdown": markdown_text.strip(),
    }

    # Split markdown by top-level headers (# or ##)
    sections = re.split(r"\n#{1,2}\s+", "\n" + markdown_text.strip())

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue

        lines = sec.splitlines()
        header = lines[0].strip().lower()
        body = "\n".join(lines[1:]).strip()

        if "headline" in header:
            # Clean headline of markdown asterisks/quotes
            clean_head = re.sub(r"^[\*\"#\s]+|[\*\"#\s]+$", "", body.strip())
            result["headline"] = clean_head.splitlines()[0] if clean_head else ""

        elif "summary" in header:
            result["summary"] = body

        elif "takeaway" in header or "finding" in header:
            takeaways = []
            for line in body.splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "•")) or re.match(r"^\d+\.", line):
                    cleaned = re.sub(r"^([-\*•]|\d+\.)\s*", "", line).strip()
                    if cleaned:
                        takeaways.append(cleaned)
            result["takeaways"] = takeaways

        elif "structure" in header or "theme" in header or "chapter" in header:
            structure_items = []
            for line in body.splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "•")) or re.match(r"^\d+\.", line):
                    cleaned = re.sub(r"^([-\*•]|\d+\.)\s*", "", line).strip()
                    if cleaned:
                        structure_items.append(cleaned)
                elif line:
                    structure_items.append(line)
            result["structure"] = structure_items

        elif "question" in header or "inquir" in header:
            questions = []
            for line in body.splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "•")) or re.match(r"^\d+\.", line) or line.endswith("?"):
                    cleaned = re.sub(r"^([-\*•]|\d+\.)\s*", "", line).strip()
                    cleaned = re.sub(r"^\[|\]$", "", cleaned).strip()
                    if cleaned and (cleaned.endswith("?") or len(cleaned) > 10):
                        if not cleaned.endswith("?"):
                            cleaned += "?"
                        questions.append(cleaned)
            result["suggested_questions"] = questions

    # Fallbacks if parsing produced empty values
    if not result["headline"] and result["summary"]:
        # Use first sentence of summary
        first_sentence = re.split(r"(?<=[.!?])\s+", result["summary"].strip())[0]
        result["headline"] = first_sentence

    if not result["suggested_questions"]:
        # Extract any lines ending with question mark
        any_q = [line.strip().lstrip("-*• 1234567890.") for line in markdown_text.splitlines() if line.strip().endswith("?")]
        result["suggested_questions"] = any_q[:4]

    return result


def generate_document_briefing(
    store: Any,
    source_id: str,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate and persist an executive briefing for a document."""
    passages = store.passages(source_id)
    if not passages:
        raise ValueError(f"No passages found for document {source_id}")

    doc_name = passages[0].get("source_name", source_id)
    total_pages = max((p.get("page") or 1 for p in passages), default=1)
    outline = store.get_document_outline(source_id)

    system_prompt, user_prompt = build_briefing_prompt(doc_name, outline, passages, total_pages=total_pages)

    prov = provider or llm.default_provider() or "qwen-small"
    summary_markdown = llm.generate(prov, system_prompt, user_prompt, model=model, api_key=api_key)

    parsed = parse_briefing_markdown(summary_markdown)
    parsed["source_id"] = source_id
    parsed["source_name"] = doc_name
    parsed["pages"] = total_pages
    parsed["provider"] = prov
    parsed["model"] = model
    parsed["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Store in summaries store
    store.set_document_summary(source_id, json.dumps(parsed, ensure_ascii=False))

    return parsed
