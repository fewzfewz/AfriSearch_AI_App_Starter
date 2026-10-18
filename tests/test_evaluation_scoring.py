"""Grading rules used by evaluation/run_eval.py."""
import json
from pathlib import Path

import pytest

from evaluation.scoring import cited_source_names, contains_all, grade, is_refusal, retrieval_rank

SOURCES = [{"source_name": "water.txt"}, {"source_name": "grain.txt"}]


def test_contains_all_needs_one_wording_per_fact():
    facts = [["20", "twenty"], ["30", "thirty"]]
    assert contains_all("Losses of twenty to 30 percent.", facts)
    assert not contains_all("Losses of 20 percent.", facts)


def test_contains_all_ignores_case_and_spacing():
    assert contains_all("Boil for Three\n minutes.", [["three minutes"]])


@pytest.mark.parametrize("answer", [
    "The available documents do not provide enough information.",
    "The best fertilizer for teff is not explicitly mentioned in the given passages.",
    "The passages don't specifically address bank accounts.",
    "I cannot determine the exact distance from the given passages.",
    "The indexed documents do not contain passages relevant enough to answer this question.",
])
def test_refusals_are_recognised(answer):
    assert is_refusal(answer)


@pytest.mark.parametrize("answer", [
    "A 100-watt solar panel costs approximately $250. [S1]",
    "Boil the water for three minutes [S1].",
])
def test_answers_are_not_refusals(answer):
    assert not is_refusal(answer)


def test_cited_source_names_maps_labels_to_documents():
    assert cited_source_names("Boil it [S1]. Dry it [S1, S2]. Bogus [S9].", SOURCES) == {"water.txt", "grain.txt"}


def test_retrieval_rank():
    assert retrieval_rank(SOURCES, "grain.txt") == 2
    assert retrieval_rank(SOURCES, "solar.txt") is None


def test_grade_answerable_question():
    question = {"source": "water.txt", "must_include": [["three minutes", "3 minutes"]]}
    assert grade(question, "Boil for 3 minutes [S1].", SOURCES) == {
        "answerable": True, "correct": True, "cites_source": True,
    }
    assert grade(question, "Boil for 3 minutes.", SOURCES)["cites_source"] is False


def test_grade_unanswerable_question():
    question = {"source": None}
    assert grade(question, "Anything", sources=[])["correct"] is True  # nothing retrieved
    assert grade(question, "The documents do not mention prices.", SOURCES)["correct"] is True
    assert grade(question, "It costs $250 [S1].", SOURCES)["correct"] is False


def test_question_file_is_well_formed():
    root = Path(__file__).resolve().parents[1] / "evaluation"
    questions = json.loads((root / "questions.json").read_text(encoding="utf-8"))
    corpus = {path.name for path in (root / "corpus").iterdir()}
    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        if q["source"] is not None:
            assert q["source"] in corpus, q["id"]
            assert q["must_include"] and all(q["must_include"]), q["id"]
