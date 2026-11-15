"""Executive Research Report & Dossier Generator for AfriSearch.

Synthesizes multiple documents or chat conversations into comprehensive, publication-grade
executive dossiers, briefings, and literature reviews with multi-format export
(Print-ready PDF layout, Word .docx via python-docx, and rich Markdown).
"""
from __future__ import annotations

import datetime
import io
import logging
import re
from typing import Any

from backend import compare, llm

logger = logging.getLogger("afrisearch.report")

REPORT_TEMPLATES = {
    "executive": {
        "label": "Executive Briefing Memo",
        "description": "High-impact, strategic briefing for decision-makers with key findings, risks, and actionable recommendations.",
        "target_words": 900,
    },
    "comprehensive": {
        "label": "Comprehensive Research Dossier",
        "description": "In-depth multi-section dossier with detailed thematic breakdown, comparative analysis, and evidence synthesis.",
        "target_words": 1600,
    },
    "review": {
        "label": "Document & Literature Review",
        "description": "Systematic review examining individual document theses, consensus vs divergence, and remaining knowledge gaps.",
        "target_words": 1200,
    },
}


def build_report_prompt(
    doc_contexts: list[dict[str, Any]] | None = None,
    chat_context: list[dict[str, Any]] | None = None,
    template: str = "executive",
    title: str | None = None,
    focus_prompt: str | None = None,
) -> tuple[str, str]:
    """Construct system prompt and user prompt for generating a formal research dossier."""
    system_prompt = (
        "You are AfriSearch, a world-class research director and chief intelligence analyst. "
        "Your task is to synthesize the provided document context and research findings into an "
        "authoritative, publication-grade executive dossier in clean GitHub-flavored Markdown. "
        "Be factual, rigorous, specific, and cite document names and page numbers in brackets (e.g. `[Document Name, p. 12]`). "
        "Do not invent facts not supported by the sources."
    )

    context_blocks: list[str] = []

    # 1. Document Contexts
    if doc_contexts:
        for i, ctx in enumerate(doc_contexts, start=1):
            name = ctx["source_name"]
            outline_str = "\n".join(f"  - {item['title']} (p. {item.get('page', 1)})" for item in ctx.get("outline", []))
            passages_str = "\n\n".join(
                f"  [Page {p.get('page', 1)}]: {p['text']}" for p in ctx.get("passages", [])
            )
            summary_str = ctx.get("summary") or ""
            if summary_str and len(summary_str) > 1000:
                summary_str = summary_str[:1000] + "..."

            block = (
                f"DOCUMENT {i}: \"{name}\" (Total Pages: {ctx.get('pages', 1)})\n"
                f"Summary: {summary_str or 'No summary'}\n"
                f"Outline:\n{outline_str or '  No outline'}\n"
                f"Key Passages & Evidence:\n{passages_str or '  No passages'}\n"
            )
            context_blocks.append(block)

    # 2. Chat / Dialogue Contexts
    if chat_context:
        chat_lines: list[str] = []
        for msg in chat_context:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            chat_lines.append(f"{role}: {content}")
            sources = msg.get("data", {}).get("sources", [])
            if sources:
                src_excerpts = [f"  - [{s.get('source_name', 'Source')} p.{s.get('page', 1)}]: {s.get('text', '')[:200]}" for s in sources[:5]]
                chat_lines.append("Cited Evidence:\n" + "\n".join(src_excerpts))
        context_blocks.append("CONVERSATION & RESEARCH FINDINGS:\n" + "\n\n".join(chat_lines))

    joined_context = "\n---\n".join(context_blocks)

    focus_instruction = f"\nSPECIAL FOCUS / CUSTOM INSTRUCTION: {focus_prompt.strip()}\n" if focus_prompt and focus_prompt.strip() else ""
    title_instruction = f"Report Title: '{title.strip()}'" if title and title.strip() else "Devise a professional, compelling title."

    if template == "comprehensive":
        template_guide = """
Follow this structural outline:
# [Report Title]

## 1. Executive Summary & Abstract
A 2-3 paragraph high-level synthesis of the primary research objective, central thesis, and main conclusions.

## 2. Introduction & Background Scope
Context, framework, and the scope of materials examined.

## 3. Thematic Analysis & Core Findings
Break down findings into 2-3 detailed thematic subsections with subheadings (`###`).
Incorporate specific numbers, evidence, and citations in format `[Document, p. X]`.

## 4. Cross-Document Comparative Evaluation
Synthesize where sources corroborate each other, where trade-offs emerge, or comparative metrics.
Include a Markdown Comparison Matrix Table where applicable.

## 5. Strategic Risks, Assumptions & Limitations
Key uncertainties, methodological constraints, or unaddressed vulnerabilities identified in the source material.

## 6. Strategic Recommendations & Action Roadmap
Actionable, numbered recommendations derived directly from the findings.

## 7. Evidence & Citation Summary
A summary table of the key cited evidence points with Source and Page references.
"""
    elif template == "review":
        template_guide = """
Follow this structural outline:
# [Report Title]

## 1. Executive Synthesis
Brief overview of the review's core scope and overarching evaluation.

## 2. Individual Source Profiles
For each document analyzed:
- **Title & Primary Thesis**
- **Methodology / Perspective**
- **Key Empirical Evidence & Claims**

## 3. Synthesis: Consensus vs. Contradictions
- **Points of Agreement**: Where the documents align.
- **Points of Divergence / Disagreement**: Where claims differ, conflict, or reflect divergent methodologies.
Include a Markdown Synthesis Table.

## 4. Critical Knowledge Gaps & Unanswered Questions
What questions remain unresolved? What data or angles are missing from the reviewed literature?

## 5. Concluding Assessment
Final takeaway on the state of knowledge and strategic takeaways.
"""
    else:  # executive
        template_guide = """
Follow this structural outline:
# [Report Title]

## 1. Executive Summary
A concise, punchy 2-paragraph briefing summarizing the core takeaway and strategic bottom line.

## 2. Key Findings & Empirical Evidence
- **[Finding 1 Title]**: Detailed finding with data points, metrics, and citation `[Document, p. X]`.
- **[Finding 2 Title]**: Detailed finding with data points, metrics, and citation `[Document, p. X]`.
- **[Finding 3 Title]**: Detailed finding with data points, metrics, and citation `[Document, p. X]`.
- **[Finding 4 Title]**: Detailed finding with data points, metrics, and citation `[Document, p. X]`.
(Provide 4 to 6 strong bullet points).

## 3. Strategic Implications & Risk Assessment
Analysis of what these findings mean in practice, including trade-offs and potential pitfalls.

## 4. Action Plan & Next Steps
Numbered, priority-ordered strategic recommendations:
1. **[Immediate Action]**: Description and rationale.
2. **[Medium-term Action]**: Description and rationale.
3. **[Long-term / Monitoring Action]**: Description and rationale.

## 5. Key Evidence Matrix
A Markdown table summarizing Key Claim | Supporting Document | Page Reference | Confidence / Impact.
"""

    user_prompt = (
        f"Generate a formal {REPORT_TEMPLATES.get(template, {}).get('label', 'Executive Research Dossier')}.\n"
        f"{title_instruction}\n"
        f"{focus_instruction}\n\n"
        f"SOURCE CONTEXT:\n{joined_context}\n\n"
        f"STRUCTURE REQUIREMENTS:\n{template_guide}\n\n"
        "Formatting Guidelines:\n"
        "- Use clean GitHub-flavored Markdown.\n"
        "- Emphasize key metrics, takeaways, and entities with **bold** text.\n"
        "- Cite sources accurately in square brackets: `[Document Name, p. X]`.\n"
        "- Maintain an authoritative, professional executive tone throughout.\n"
    )

    return system_prompt, user_prompt


def extract_report_metadata(markdown_text: str) -> dict[str, Any]:
    """Extract report title, executive summary snippet, and statistics."""
    title = "AfriSearch Research Dossier"
    title_match = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    # Extract first paragraph under Executive Summary or Abstract
    summary = ""
    summary_match = re.search(r"##\s*1\.\s*Executive Summary.*?\n+(.+?)(?=\n+##|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
    if summary_match:
        summary = summary_match.group(1).strip()
    elif len(markdown_text) > 100:
        lines = [line.strip() for line in markdown_text.splitlines() if line.strip() and not line.startswith("#")]
        if lines:
            summary = lines[0]

    words = len(markdown_text.split())
    # Standard adult reading speed: ~200-250 wpm
    reading_time = max(1, round(words / 220))

    return {
        "title": title,
        "executive_summary": summary,
        "word_count": words,
        "reading_time_minutes": reading_time,
    }


def generate_report(
    store: Any,
    source_ids: list[str] | None = None,
    chat_messages: list[dict[str, Any]] | None = None,
    template: str = "executive",
    title: str | None = None,
    focus_prompt: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive research dossier or briefing memo."""
    doc_contexts: list[dict[str, Any]] = []
    source_docs: list[dict[str, Any]] = []

    if source_ids:
        doc_contexts = compare.collect_comparison_context(store, source_ids, focus=focus_prompt)
        for ctx in doc_contexts:
            source_docs.append({
                "source_id": ctx["source_id"],
                "source_name": ctx["source_name"],
                "pages": ctx.get("pages", 1),
                "passages_count": len(ctx.get("passages", [])),
            })

    system_prompt, user_prompt = build_report_prompt(
        doc_contexts=doc_contexts,
        chat_context=chat_messages,
        template=template,
        title=title,
        focus_prompt=focus_prompt,
    )

    prov = provider or llm.default_provider() or "qwen-small"
    logger.info("Generating %s report with provider=%s model=%s (docs=%d)", template, prov, model, len(doc_contexts))

    raw_response = llm.generate(
        prov,
        system_prompt,
        user_prompt,
        model=model,
        api_key=api_key,
    )

    meta = extract_report_metadata(raw_response)

    return {
        "title": meta["title"],
        "template": template,
        "template_label": REPORT_TEMPLATES.get(template, {}).get("label", "Executive Briefing"),
        "markdown": raw_response,
        "executive_summary": meta["executive_summary"],
        "word_count": meta["word_count"],
        "reading_time_minutes": meta["reading_time_minutes"],
        "documents": source_docs,
        "source_ids": source_ids or [],
        "provider": prov,
        "model": model,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _add_markdown_runs(paragraph: Any, text: str) -> None:
    """Parse inline **bold** and `code` formatting into paragraph runs."""
    tokens = re.split(r"(\*\*.*?\*\*|`.*?`)", text)
    for token in tokens:
        if not token:
            continue
        if token.startswith("**") and token.endswith("**") and len(token) >= 4:
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("`") and token.endswith("`") and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Courier New"
        else:
            paragraph.add_run(token)


def markdown_to_docx(
    title: str,
    markdown_text: str,
    documents: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> io.BytesIO:
    """Convert generated markdown report into a native Microsoft Word (.docx) document."""
    import docx
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Inches, Pt, RGBColor

    doc = docx.Document()

    # Set 1-inch margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Document Header Title
    doc_title = title or "AfriSearch Research Dossier"
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_title = title_p.add_run(doc_title)
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(24)
    run_title.bold = True
    run_title.font.color.rgb = RGBColor(15, 23, 42)  # Dark slate

    # Subtitle Metadata Banner
    today_str = datetime.datetime.now().strftime("%B %d, %Y")
    prov_str = metadata.get("provider", "AfriSearch AI") if metadata else "AfriSearch AI"
    banner_p = doc.add_paragraph()
    banner_p.paragraph_format.space_after = Pt(18)
    run_sub = banner_p.add_run(f"Executive Intelligence Dossier  •  {today_str}  •  Prepared by AfriSearch via {prov_str}")
    run_sub.font.name = "Calibri"
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)  # Slate 500

    # Parse Markdown lines
    lines = markdown_text.splitlines()
    in_table = False
    table_lines: list[str] = []

    def flush_table(tbl_lines: list[str]) -> None:
        if not tbl_lines:
            return
        # Parse table rows
        rows: list[list[str]] = []
        for l in tbl_lines:
            cleaned = l.strip()
            if not cleaned or not cleaned.startswith("|"):
                continue
            cells = [c.strip() for c in cleaned.strip("|").split("|")]
            # Skip separator rows like |---|---|
            if cells and all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            rows.append(cells)

        if not rows:
            return

        col_count = max(len(r) for r in rows)
        if col_count == 0:
            return

        tbl = doc.add_table(rows=len(rows), cols=col_count)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = True

        for r_idx, row in enumerate(rows):
            for c_idx, cell_text in enumerate(row):
                if c_idx < col_count:
                    cell = tbl.cell(r_idx, c_idx)
                    cell.text = ""
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_before = Pt(2)
                    p.paragraph_format.space_after = Pt(2)
                    _add_markdown_runs(p, cell_text)
                    if r_idx == 0:
                        # Style header row
                        for run in p.runs:
                            run.bold = True
                        shading_elm = parse_xml(r'<w:shd {} w:fill="F1F5F9"/>'.format(nsdecls('w')))
                        cell._tc.get_or_add_tcPr().append(shading_elm)

        # Spacing after table
        after_p = doc.add_paragraph()
        after_p.paragraph_format.space_before = Pt(0)
        after_p.paragraph_format.space_after = Pt(6)

    for line in lines:
        stripped = line.strip()

        # Table handling
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            flush_table(table_lines)
            table_lines = []
            in_table = False

        if not stripped:
            continue

        # Skip top level # if it duplicates title
        if stripped.startswith("# ") and stripped[2:].strip().lower() == doc_title.lower():
            continue

        # Headings
        if stripped.startswith("### "):
            h = doc.add_heading(level=3)
            h.paragraph_format.space_before = Pt(12)
            h.paragraph_format.space_after = Pt(4)
            _add_markdown_runs(h, stripped[4:].strip())
        elif stripped.startswith("## "):
            h = doc.add_heading(level=2)
            h.paragraph_format.space_before = Pt(16)
            h.paragraph_format.space_after = Pt(6)
            _add_markdown_runs(h, stripped[3:].strip())
        elif stripped.startswith("# "):
            h = doc.add_heading(level=1)
            h.paragraph_format.space_before = Pt(20)
            h.paragraph_format.space_after = Pt(8)
            _add_markdown_runs(h, stripped[2:].strip())
        # Blockquote
        elif stripped.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            quote_text = stripped.lstrip(">").strip()
            _add_markdown_runs(p, quote_text)
            for run in p.runs:
                run.font.italic = True
                run.font.color.rgb = RGBColor(71, 85, 105)
        # Bullet list
        elif re.match(r"^[-*]\s+", stripped):
            bullet_text = re.sub(r"^[-*]\s+", "", stripped)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            _add_markdown_runs(p, bullet_text)
        # Numbered list
        elif re.match(r"^\d+\.\s+", stripped):
            num_text = re.sub(r"^\d+\.\s+", "", stripped)
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            _add_markdown_runs(p, num_text)
        # Regular paragraph
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.15
            _add_markdown_runs(p, stripped)

    if in_table:
        flush_table(table_lines)

    # Appendix: Source Documents
    if documents:
        doc.add_page_break()
        h_app = doc.add_heading("Appendix: Source Documents & Materials", level=1)
        h_app.paragraph_format.space_before = Pt(12)
        h_app.paragraph_format.space_after = Pt(8)

        app_p = doc.add_paragraph("This dossier was synthesized from the following indexed documents in the workspace:")
        app_p.paragraph_format.space_after = Pt(8)

        app_tbl = doc.add_table(rows=len(documents) + 1, cols=3)
        app_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        app_tbl.rows[0].cells[0].text = "Document Name"
        app_tbl.rows[0].cells[1].text = "Total Pages"
        app_tbl.rows[0].cells[2].text = "Indexed Passages"

        for c_idx in range(3):
            cell = app_tbl.rows[0].cells[c_idx]
            for p in cell.paragraphs:
                for run in p.runs:
                    run.bold = True
            shd = parse_xml(r'<w:shd {} w:fill="E2E8F0"/>'.format(nsdecls('w')))
            cell._tc.get_or_add_tcPr().append(shd)

        for i, d in enumerate(documents, start=1):
            app_tbl.rows[i].cells[0].text = d.get("source_name", "Untitled")
            app_tbl.rows[i].cells[1].text = str(d.get("pages", 1))
            app_tbl.rows[i].cells[2].text = str(d.get("passages_count", "–"))

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream
