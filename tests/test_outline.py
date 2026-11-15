import pytest
from backend.outline import match_outline_target, _fill_page_ends


def test_match_outline_target():
    outline = [
        {"title": "1. HTML – Overview", "page": 17, "page_end": 22, "level": 1},
        {"title": "2. HTML – Basic Tags", "page": 23, "page_end": 28, "level": 1},
        {"title": "5. HTML – Formatting", "page": 34, "page_end": 41, "level": 1},
        {"title": "10. HTML – Tables", "page": 66, "page_end": 75, "level": 1},
        {"title": "Table Heading", "page": 68, "page_end": 70, "level": 2},
    ]

    # Test chapter number match
    hit = match_outline_target("What does Chapter 5 say about formatting?", outline)
    assert hit is not None
    assert hit["title"] == "5. HTML – Formatting"
    assert hit["page"] == 34
    assert hit["page_end"] == 41

    # Test ch prefix match
    hit2 = match_outline_target("Explain ch 10", outline)
    assert hit2 is not None
    assert hit2["title"] == "10. HTML – Tables"
    assert hit2["page"] == 66

    # Test topic title match
    hit3 = match_outline_target("How do I create tables in HTML?", outline)
    assert hit3 is not None
    assert hit3["page"] == 66

    # Test no match
    assert match_outline_target("How is the weather today?", outline) is None


def test_fill_page_ends():
    raw_outline = [
        {"title": "Chapter 1", "page": 1, "level": 1},
        {"title": "Section 1.1", "page": 3, "level": 2},
        {"title": "Section 1.2", "page": 5, "level": 2},
        {"title": "Chapter 2", "page": 10, "level": 1},
    ]
    filled = _fill_page_ends(raw_outline, total_pages=20)
    assert filled[0]["page_end"] == 9  # Chapter 1 spans until Chapter 2 starts at 10
    assert filled[1]["page_end"] == 4  # Section 1.1 spans until 1.2 starts at 5
    assert filled[2]["page_end"] == 9  # Section 1.2 spans until Chapter 2 starts at 10
    assert filled[3]["page_end"] == 20  # Chapter 2 spans to total_pages
