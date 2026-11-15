import pytest
from backend.conversational import rewrite_conversational_query, extract_topic_entity


def test_extract_topic_entity():
    e1 = extract_topic_entity("What does Chapter 10 say about HTML tables?")
    assert "Chapter 10" in e1
    assert "HTML" in e1
    assert "tables" in e1

    e2 = extract_topic_entity("Explain solar panel maintenance procedures")
    assert "solar" in e2
    assert "panel" in e2


def test_rewrite_conversational_query_pronoun():
    history = [{"question": "What does Chapter 10 say about HTML tables?", "answer": "Tables are created with <table>."}]
    q = "How do I add borders to it?"
    rewritten = rewrite_conversational_query(q, history)
    assert "Chapter 10" in rewritten
    assert "HTML" in rewritten
    assert "tables" in rewritten
    assert "borders" in rewritten


def test_rewrite_conversational_query_opener():
    history = [{"question": "Tell me about solar panel maintenance.", "answer": "Clean panels monthly."}]
    q = "What about inverters?"
    rewritten = rewrite_conversational_query(q, history)
    assert "solar" in rewritten
    assert "inverters" in rewritten


def test_rewrite_conversational_query_independent():
    history = [{"question": "What is HTML?", "answer": "HyperText Markup Language."}]
    q = "What is the syntax of CSS?"
    rewritten = rewrite_conversational_query(q, history)
    # New topic question should remain untouched
    assert rewritten == q


def test_rewrite_conversational_query_no_history():
    q = "How do I create a table in HTML?"
    assert rewrite_conversational_query(q, []) == q
    assert rewrite_conversational_query(q, None) == q
