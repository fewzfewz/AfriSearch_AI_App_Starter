"""Tests for the Research Report and Dossier Generator."""
import io
import docx
import pytest
from unittest.mock import patch

from backend import report


def test_build_report_prompt():
    doc_contexts = [
        {
            "source_id": "doc1",
            "source_name": "Ethiopia_Renewable_Energy_Report.pdf",
            "pages": 24,
            "outline": [{"title": "Executive Summary", "page": 1}, {"title": "Solar Power", "page": 8}],
            "passages": [{"text": "Solar capacity grew by 45% in 2025 across the Great Rift Valley.", "page": 9}],
            "summary": "National overview of solar and geothermal expansion.",
        }
    ]

    system_prompt, user_prompt = report.build_report_prompt(
        doc_contexts=doc_contexts,
        template="executive",
        title="East Africa Energy Transition",
        focus_prompt="Focus on solar investments and grid stability",
    )

    assert "AfriSearch" in system_prompt
    assert "East Africa Energy Transition" in user_prompt
    assert "Ethiopia_Renewable_Energy_Report.pdf" in user_prompt
    assert "solar investments and grid stability" in user_prompt
    assert "Executive Summary" in user_prompt
    assert "Solar capacity grew by 45%" in user_prompt


def test_extract_report_metadata():
    md = """# Strategic AI Infrastructure in East Africa

## 1. Executive Summary
The rapid buildout of localized datacenters and regional compute clusters has lowered inference latency by 60%.

## 2. Key Findings & Empirical Evidence
- **Compute Capacity**: 12 new high-efficiency facilities launched in 2025. [Cloud Report, p. 14]
"""
    meta = report.extract_report_metadata(md)
    assert meta["title"] == "Strategic AI Infrastructure in East Africa"
    assert "inference latency by 60%" in meta["executive_summary"]
    assert meta["word_count"] > 20
    assert meta["reading_time_minutes"] >= 1


def test_markdown_to_docx():
    title = "East Africa Renewable Energy Briefing"
    md = """# East Africa Renewable Energy Briefing

## 1. Executive Summary
Renewable capacity has expanded across wind, solar, and geothermal sectors.

## 2. Empirical Findings
- **Geothermal**: 850 MW operational in Olkaria [Geothermal Report, p. 5].
- **Solar**: Over 300 MW installed capacity [Solar Report, p. 12].

> Energy storage remains the single most critical gating factor.

| Metric | 2024 Baseline | 2026 Target | Growth |
|---|---|---|---|
| Solar (MW) | 210 | 380 | +81% |
| Wind (MW) | 310 | 450 | +45% |

1. Immediate grid upgrades.
2. Cross-border power pool trading.
"""
    docs = [
        {"source_name": "Geothermal Report.pdf", "pages": 15, "passages_count": 8},
        {"source_name": "Solar Report.pdf", "pages": 22, "passages_count": 12},
    ]

    docx_stream = report.markdown_to_docx(title, md, documents=docs, metadata={"provider": "gemini"})
    assert isinstance(docx_stream, io.BytesIO)
    docx_bytes = docx_stream.getvalue()
    assert len(docx_bytes) > 5000

    # Ensure python-docx can open it back up without corruption
    opened_doc = docx.Document(io.BytesIO(docx_bytes))
    headings = [p.text for p in opened_doc.paragraphs if p.text]
    assert any("East Africa Renewable Energy Briefing" in h for h in headings)
    assert any("Executive Summary" in h for h in headings)
    assert len(opened_doc.tables) >= 2  # data table + appendix table


@patch("backend.llm.generate")
def test_generate_report(mock_generate):
    mock_generate.return_value = (
        "# Strategic Energy Dossier\n\n"
        "## 1. Executive Summary\n"
        "Clean power infrastructure continues accelerated expansion.\n\n"
        "## 2. Key Findings & Empirical Evidence\n"
        "- **Growth**: Tripled renewable deployment. [Energy Doc, p. 3]\n"
    )

    class MockStore:
        def passages(self, sid):
            return [{"source_name": f"{sid}.pdf", "page": 1, "text": "Sample energy passage"}]
        def get_document_outline(self, sid):
            return [{"title": "Overview", "page": 1}]
        def get_document_summary(self, sid):
            return "Sample summary"

    res = report.generate_report(
        store=MockStore(),
        source_ids=["energy_doc_1"],
        template="executive",
        provider="qwen-small",
    )

    assert res["title"] == "Strategic Energy Dossier"
    assert "Clean power infrastructure" in res["executive_summary"]
    assert res["template"] == "executive"
    assert res["provider"] == "qwen-small"
    assert len(res["documents"]) == 1
    assert mock_generate.called
