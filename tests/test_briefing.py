import pytest
from backend.briefing import (
    build_briefing_prompt,
    extract_sample_passages,
    parse_briefing_markdown,
)


def test_extract_sample_passages():
    passages = [{"page": i, "text": f"Passage {i}"} for i in range(1, 20)]
    sampled = extract_sample_passages(passages, max_count=6)
    assert len(sampled) <= 8
    # Should include first and last
    pages = [p["page"] for p in sampled]
    assert 1 in pages
    assert 19 in pages


def test_build_briefing_prompt():
    outline = [{"title": "Introduction", "page": 1}, {"title": "Revenue", "page": 4}]
    passages = [{"page": 1, "text": "Company overview"}, {"page": 4, "text": "Generated $5M"}]
    sys_prompt, user_prompt = build_briefing_prompt("Q3_Financials.pdf", outline, passages, total_pages=10)

    assert "AfriSearch" in sys_prompt
    assert "Q3_Financials.pdf" in user_prompt
    assert "Executive Headline" in user_prompt
    assert "Key Takeaways & Core Findings" in user_prompt
    assert "Suggested Questions to Ask" in user_prompt


def test_parse_briefing_markdown():
    sample_md = """
# Executive Headline
Quarterly revenue surged 45% led by enterprise cloud adoption in Sub-Saharan Africa.

# Executive Summary
The document presents an in-depth operational review for Q3 2026. Growth was predominantly driven by accelerated enterprise adoption across Kenya, Nigeria, and South Africa. Operational expenditures remained constrained, yielding higher margin efficiency.

# Key Takeaways & Core Findings
- **45% Revenue Surge**: Total ARR exceeded $12.5M. [p. 3]
- **Market Expansion**: Kenya operations expanded by 60% YoY. [p. 7]
- **Risk Mitigation**: Foreign exchange exposure reduced by 18%. [p. 12]

# Structure & Core Themes
- Section 1: Executive Overview (pp. 1-3)
- Section 2: Regional Performance (pp. 4-8)
- Section 3: Financial & Risk Analysis (pp. 9-14)

# Suggested Questions to Ask
- What are the main drivers of the 45% revenue surge?
- How did foreign exchange hedging impact operating margins?
- Which regions are projected to grow fastest in Q4?
"""

    parsed = parse_briefing_markdown(sample_md)
    assert "Quarterly revenue surged 45%" in parsed["headline"]
    assert "operational review for Q3 2026" in parsed["summary"]
    assert len(parsed["takeaways"]) == 3
    assert "45% Revenue Surge" in parsed["takeaways"][0]
    assert len(parsed["structure"]) == 3
    assert len(parsed["suggested_questions"]) == 3
    assert parsed["suggested_questions"][0].startswith("What are the main drivers")
