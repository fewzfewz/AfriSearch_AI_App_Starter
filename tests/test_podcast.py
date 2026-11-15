import pytest
from backend.podcast import (
    build_podcast_prompt,
    parse_podcast_script,
)


def test_build_podcast_prompt():
    doc_contexts = [
        {
            "source_id": "doc1",
            "source_name": "Annual_Report.pdf",
            "pages": 12,
            "outline": [{"title": "Overview", "page": 1}],
            "passages": [{"page": 2, "text": "Net income grew 30%."}],
        }
    ]
    sys_prompt, user_prompt = build_podcast_prompt(doc_contexts, tone="conversational", length="quick")
    assert "AfriSearch Deep Dive" in sys_prompt
    assert "Alex" in user_prompt
    assert "Sam" in user_prompt
    assert "Annual_Report.pdf" in user_prompt
    assert "Net income grew 30%" in user_prompt


def test_parse_podcast_script():
    sample_script = """
Alex: Welcome to today's deep dive. Today we're looking at the 2026 Annual Report.
Sam: Hey Alex! Yes, and honestly, the growth numbers on page 2 really surprised me.
Alex: Exactly, 30% net income growth is pretty remarkable given the inflation environment.
Sam: Right, and what's interesting is how they diversified foreign exchange risks.
"""
    turns = parse_podcast_script(sample_script)
    assert len(turns) == 4
    assert turns[0]["speaker"] == "Alex"
    assert "Annual Report" in turns[0]["text"]
    assert turns[1]["speaker"] == "Sam"
    assert "growth numbers" in turns[1]["text"]
    assert turns[2]["speaker"] == "Alex"
    assert turns[3]["speaker"] == "Sam"


def test_parse_podcast_script_markdown_formatting():
    sample_script = """
**Alex**: Welcome everyone to the show!
*Sam*: Thanks Alex, excited to dig into the methodology.
Alex: Let's start with page 1.
"""
    turns = parse_podcast_script(sample_script)
    assert len(turns) == 3
    assert turns[0]["speaker"] == "Alex"
    assert "Welcome everyone" in turns[0]["text"]
    assert turns[1]["speaker"] == "Sam"
    assert turns[2]["speaker"] == "Alex"
