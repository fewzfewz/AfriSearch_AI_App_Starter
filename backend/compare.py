"""Document Compare & Cross-Analysis Matrix for AfriSearch.

Enables multi-document synthesis, cross-referencing, automated comparative
matrix tables, and contradiction/discrepancy detection across 2 or more documents.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from backend import models


def collect_comparison_context(
    store: Any,
    source_ids: list[str],
    focus: str | None = None,
) -> list[dict[str, Any]]:
    """Gather outlines, summaries, and relevant passages for each document to compare."""
    doc_contexts: list[dict[str, Any]] = []

    for sid in source_ids:
        all_passages = store.passages(sid)
        if not all_passages:
            continue

        doc_name = all_passages[0].get("source_name", sid)
        max_page = max((p.get("page") or 1 for p in all_passages), default=1)
        outline = store.get_document_outline(sid)
        summary = store.get_document_summary(sid)

        # Collect key passages:
        selected_passages: list[dict[str, Any]] = []
        if focus and focus.strip():
            # Retrieve targeted passages relevant to the comparison focus
            try:
                retrieved = store.retrieve(
                    question=focus.strip(),
                    top_k=5,
                    min_score=0.15,
                    rerank=False,
                    source_ids=[sid],
                )
                if retrieved:
                    selected_passages.extend(retrieved)
            except Exception:
                pass

        # If we have few or no focus-specific passages, sample representative sections
        if len(selected_passages) < 3:
            total = len(all_passages)
            mid = total // 2
            indices = {0, 1}
            if total > 4:
                indices.update({mid, mid + 1, total - 1})
            elif total > 2:
                indices.update({mid, total - 1})
            sampled = [all_passages[i] for i in sorted(indices) if i < total]
            # Avoid duplicate passages
            existing_texts = {p["text"] for p in selected_passages}
            for p in sampled:
                if p["text"] not in existing_texts:
                    selected_passages.append(p)
                    existing_texts.add(p["text"])

        doc_contexts.append(
            {
                "source_id": sid,
                "source_name": doc_name,
                "pages": max_page,
                "outline": outline[:20],  # up to top 20 chapters/sections
                "summary": summary,
                "passages": selected_passages[:8],
            }
        )

    return doc_contexts


def build_compare_prompt(
    doc_contexts: list[dict[str, Any]],
    focus: str | None = None,
) -> tuple[str, str]:
    """Build the system prompt and comparative user prompt for the LLM."""
    clean_focus = (focus or "").strip() or "Comprehensive Cross-Document Analysis (Key Objectives, Methodology, Findings, Metrics, and Conclusions)"

    doc_blocks: list[str] = []
    doc_titles: list[str] = []

    for i, ctx in enumerate(doc_contexts, start=1):
        name = ctx["source_name"]
        doc_titles.append(name)
        outline_str = "\n".join(f"  - {item['title']} (p. {item['page']})" for item in ctx["outline"])
        passages_str = "\n\n".join(
            f"  [p. {p.get('page', 1)}]: {p['text']}" for p in ctx["passages"]
        )

        block = (
            f"### DOCUMENT {i}: \"{name}\" (Total Pages: {ctx['pages']})\n"
            f"**Outline / Table of Contents:**\n{outline_str or '  No formal outline available.'}\n\n"
        )
        if ctx.get("summary"):
            block += f"**Existing Summary:**\n{ctx['summary']}\n\n"

        block += f"**Key Extracted Passages:**\n{passages_str or '  No extracted passages.'}\n"
        doc_blocks.append(block)

    docs_joined = "\n---\n\n".join(doc_blocks)
    names_joined = ", ".join(f'"{t}"' for t in doc_titles)

    system_prompt = (
        "You are AfriSearch, an expert research intelligence analyst specialized in comparative document synthesis. "
        "You analyze multiple documents side-by-side, extract structured comparison matrices, identify key divergences "
        "and contradictions, and provide rigorous evidence-backed conclusions."
    )

    user_prompt = (
        f"Perform a comprehensive comparative analysis of the following documents: {names_joined}.\n\n"
        f"COMPARISON FOCUS / OBJECTIVE:\n{clean_focus}\n\n"
        f"DOCUMENTS EVIDENCE & SECTIONS:\n\n{docs_joined}\n\n"
        "INSTRUCTIONS FOR YOUR RESPONSE:\n"
        "Provide your analysis in clean GitHub-flavored Markdown following this exact structure:\n\n"
        "## Executive Comparison Summary\n"
        "A concise, high-level summary contrasting the primary purpose, core thesis, and main differences across the documents.\n\n"
        "## Comparison Matrix\n"
        "Create a clean Markdown table comparing the documents across 5 to 7 key dimensions "
        "(such as Objectives, Methodology/Approach, Key Metrics & Findings, Costs/Pricing/Resources, Limitations & Risks, Recommendations). "
        "Every row MUST cite specific document page references where available in the format `[DocName p.X]`.\n"
        "Columns: `| Dimension | " + " | ".join(doc_titles) + " | Synthesis / Key Distinction |`\n\n"
        "## In-Depth Dimensional Breakdown\n"
        "Detailed comparison for each key dimension. Explicitly compare how each document addresses the topic, highlighting specifics with citations.\n\n"
        "## Contradictions & Divergent Claims\n"
        "Explicitly identify any contradictions, conflicting statistics, opposing conclusions, or divergent definitions between the documents. "
        "If there are no direct contradictions, explain where their assumptions or scopes diverge.\n\n"
        "## Strategic Takeaways & Verdict\n"
        "Actionable guidance: When to rely on each document, practical trade-offs, and final conclusions.\n\n"
        "Important: Ground your answers in the provided evidence and cite page numbers whenever possible (e.g., `[DocName p.4]`)."
    )

    return system_prompt, user_prompt


def extract_matrix_table(markdown_text: str) -> str:
    """Extract the first Markdown comparison table found in the text, if any."""
    table_lines: list[str] = []
    in_table = False

    for line in markdown_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            in_table = True
            table_lines.append(trimmed)
        elif in_table:
            # Table ended
            if len(table_lines) >= 3:
                break
            table_lines.clear()
            in_table = False

    return "\n".join(table_lines) if len(table_lines) >= 3 else ""


def markdown_table_to_csv(table_markdown: str) -> str:
    """Convert a Markdown table into an RFC 4180 CSV string for Excel/Sheets download."""
    lines = [line.strip() for line in table_markdown.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return ""

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    for i, line in enumerate(lines):
        # Strip outer pipes
        inner = line.strip().strip("|")
        # Check if delimiter separator line like | :--- | :--- |
        if i == 1 and all(re.match(r"^:?-+:?$", cell.strip()) for cell in inner.split("|")):
            continue

        row = [cell.strip() for cell in inner.split("|")]
        writer.writerow(row)

    return output.getvalue()
