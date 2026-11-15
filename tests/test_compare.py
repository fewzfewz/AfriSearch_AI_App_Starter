import pytest
from backend.compare import (
    build_compare_prompt,
    collect_comparison_context,
    extract_matrix_table,
    markdown_table_to_csv,
)


class MockStore:
    def passages(self, sid: str):
        if sid == "doc1":
            return [
                {"source_name": "Report_2025.pdf", "page": 1, "text": "Annual report summary 2025."},
                {"source_name": "Report_2025.pdf", "page": 2, "text": "Financial revenue was $10M."},
                {"source_name": "Report_2025.pdf", "page": 3, "text": "Risk of inflation is moderate."},
            ]
        elif sid == "doc2":
            return [
                {"source_name": "Forecast_2026.pdf", "page": 1, "text": "Market forecast for 2026."},
                {"source_name": "Forecast_2026.pdf", "page": 4, "text": "Expected revenue is $15M."},
                {"source_name": "Forecast_2026.pdf", "page": 8, "text": "High competition risk."},
            ]
        return []

    def get_document_outline(self, sid: str):
        if sid == "doc1":
            return [{"title": "Introduction", "page": 1}, {"title": "Financials", "page": 2}]
        return [{"title": "Forecast", "page": 1}]

    def get_document_summary(self, sid: str):
        return "Executive brief for " + sid

    def retrieve(self, question: str, top_k: int = 5, min_score: float = 0.15, rerank: bool = False, source_ids: list[str] | None = None):
        return [{"source_name": "Report_2025.pdf", "page": 2, "text": "Financial revenue was $10M."}]


def test_collect_comparison_context():
    store = MockStore()
    contexts = collect_comparison_context(store, ["doc1", "doc2"], focus="financials")
    assert len(contexts) == 2
    assert contexts[0]["source_name"] == "Report_2025.pdf"
    assert contexts[1]["source_name"] == "Forecast_2026.pdf"
    assert len(contexts[0]["passages"]) >= 2
    assert len(contexts[1]["passages"]) >= 2


def test_build_compare_prompt():
    contexts = [
        {
            "source_id": "d1",
            "source_name": "PolicyA.pdf",
            "pages": 10,
            "outline": [{"title": "Scope", "page": 1}],
            "summary": "Summary of A",
            "passages": [{"page": 1, "text": "Policy rules"}],
        },
        {
            "source_id": "d2",
            "source_name": "PolicyB.pdf",
            "pages": 15,
            "outline": [{"title": "Overview", "page": 1}],
            "summary": "Summary of B",
            "passages": [{"page": 2, "text": "Different rules"}],
        },
    ]
    sys_prompt, user_prompt = build_compare_prompt(contexts, focus="Compare rule enforcement")
    assert "AfriSearch" in sys_prompt
    assert "PolicyA.pdf" in user_prompt
    assert "PolicyB.pdf" in user_prompt
    assert "Comparison Matrix" in user_prompt
    assert "Contradictions & Divergent Claims" in user_prompt


def test_extract_matrix_table_and_csv():
    sample_markdown = """
Here is the comparison:

## Comparison Matrix

| Dimension | Doc A | Doc B | Synthesis |
| :--- | :--- | :--- | :--- |
| Revenue | $10M [DocA p.2] | $15M [DocB p.4] | Doc B forecasts 50% growth |
| Risk | Moderate [DocA p.3] | High [DocB p.8] | Divergent risk outlook |

## In-Depth Analysis
More details here...
"""
    table = extract_matrix_table(sample_markdown)
    assert table.startswith("| Dimension")
    assert "Divergent risk outlook" in table

    csv_data = markdown_table_to_csv(table)
    lines = csv_data.strip().splitlines()
    assert len(lines) == 3
    assert "Dimension,Doc A,Doc B,Synthesis" in lines[0]
    assert "$10M [DocA p.2]" in lines[1]
