"""Score AfriSearch's search and answer models on questions with known answers.

Builds a temporary index of a document folder with the real pipeline (your
data/ folder is not touched), then for each question checks whether search
finds the right document and whether each answer model gets the facts right.

Examples, from the project root:
    python evaluation/run_eval.py --retrieval-only
    python evaluation/run_eval.py --retrieval-only --embedders sentence-transformers/all-MiniLM-L6-v2 intfloat/multilingual-e5-small
    python evaluation/run_eval.py --retrieval-only --modes semantic rerank
    python evaluation/run_eval.py --providers qwen-small
    python evaluation/run_eval.py --providers claude chatgpt gemini --top-k 6
    python evaluation/run_eval.py --corpus my_docs/ --questions my_questions.json --providers qwen-small
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import answers, config, llm, models  # noqa: E402  (config also sets HF_HOME)
from backend.store import DocumentStore  # noqa: E402
from backend.text import clean_citations  # noqa: E402
from evaluation.scoring import grade, retrieval_rank  # noqa: E402

HERE = Path(__file__).resolve().parent
MODES = ("semantic", "rerank")


def set_mode(mode: str, reranker_id: str | None) -> None:
    wanted = reranker_id if mode == "rerank" else ""
    if models.RERANKER_ID != wanted:
        models.set_reranker(wanted)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=HERE / "corpus", help="folder of PDF/TXT documents")
    parser.add_argument("--questions", type=Path, default=HERE / "questions.json")
    parser.add_argument("--embedders", nargs="+", default=[models.EMBEDDER_ID],
                        help="search models to compare (answers use the first one)")
    parser.add_argument("--modes", nargs="+", choices=MODES,
                        default=["rerank" if models.RERANKER_ID else "semantic"],
                        help="search modes to compare (answers use the first one); "
                             "rerank = semantic search reordered by the --reranker model")
    parser.add_argument("--reranker", default=models.RERANKER_ID or models.DEFAULT_RERANKER,
                        help="reranking model for the 'rerank' mode (default: AFRISEARCH_RERANKER)")
    parser.add_argument("--providers", nargs="*", default=[], help="answer models to score, e.g. qwen-small claude")
    parser.add_argument("--retrieval-only", action="store_true", help="score search only; no answer models")
    parser.add_argument("--top-k", type=int, default=4, help="passages retrieved per question")
    parser.add_argument("--limit", type=int, help="only use the first N questions")
    parser.add_argument("--output", type=Path, default=HERE / "results", help="where to save the JSON report")
    return parser.parse_args()


def build_index(corpus: Path, workdir: Path) -> DocumentStore:
    """Index the corpus into a temporary workspace with the real pipeline."""
    index = DocumentStore(workdir)
    files = sorted(p for p in corpus.iterdir() if p.suffix.lower() in config.ALLOWED_EXTENSIONS)
    if not files:
        sys.exit(f"No PDF, TXT or image files in {corpus}")
    for path in files:
        shutil.copy(path, index.upload_dir / path.name)
    result = index.rebuild(full=True)
    print(f"Indexed {len(files)} documents into {result['indexed_chunks']} chunks with {models.EMBEDDER_ID}")
    for failed in result["failed"]:
        print(f"  ! not indexed: {failed['filename']}: {failed['error']}")
    return index


def percent(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "n/a"


def suggest_cutoff(questions: list[dict[str, Any]], raw: dict[str, list]) -> dict[str, Any]:
    """Compare semantic scores of answerable vs off-topic questions (before any cutoff).

    Uses the best semantic score among the retrieved passages, since with a
    reranker the first passage is not always the highest scoring one.
    """
    answerable = [max(s["score"] for s in raw[q["id"]] if s["source_name"] == q["source"])
                  for q in questions
                  if q.get("source") and any(s["source_name"] == q["source"] for s in raw[q["id"]])]
    off_topic = [max(s["score"] for s in raw[q["id"]]) for q in questions if not q.get("source") and raw[q["id"]]]
    if not answerable or not off_topic:
        return {}
    lowest_answerable, highest_off_topic = min(answerable), max(off_topic)
    return {
        "lowest_answerable_top_score": round(lowest_answerable, 3),
        "highest_off_topic_top_score": round(highest_off_topic, 3),
        # Halfway between the two groups if they don't overlap.
        "suggested_min_score": round((lowest_answerable + highest_off_topic) / 2, 3)
        if lowest_answerable > highest_off_topic else None,
    }


def score_retrieval(questions: list[dict[str, Any]], retrieved: dict[str, list],
                    raw: dict[str, list], mode: str) -> dict[str, Any]:
    answerable = [q for q in questions if q.get("source")]
    unanswerable = [q for q in questions if not q.get("source")]
    ranks = {q["id"]: retrieval_rank(retrieved[q["id"]], q["source"]) for q in answerable}
    by_language: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for q in answerable:
        counts = by_language[q.get("lang", "en")]
        counts[0] += ranks[q["id"]] is not None
        counts[1] += 1
    return {
        "embedder": models.EMBEDDER_ID,
        "mode": mode,
        "reranker": models.RERANKER_ID or None,
        "min_score": models.MIN_SCORE,
        "answerable": len(answerable),
        "hit_at_1": sum(rank == 1 for rank in ranks.values()),
        "hit_at_k": sum(rank is not None for rank in ranks.values()),
        "mrr": round(sum(1 / r for r in ranks.values() if r) / len(answerable), 3) if answerable else 0.0,
        "unanswerable": len(unanswerable),
        "unanswerable_with_no_passages": sum(not retrieved[q["id"]] for q in unanswerable),
        "hit_at_k_by_language": {lang: {"hits": h, "total": t} for lang, (h, t) in sorted(by_language.items())},
        "cutoff": suggest_cutoff(questions, raw),
        "misses": [q["id"] for q in answerable if ranks[q["id"]] is None],
        "ranks": ranks,
    }


def score_provider(provider_id: str, questions: list[dict[str, Any]], retrieved: dict[str, list]) -> dict[str, Any]:
    rows = []
    for number, question in enumerate(questions, start=1):
        sources = retrieved[question["id"]]
        started = time.monotonic()
        error = None
        try:
            answer = answers.generate_answer(question["question"], sources, provider_id)
            answer, _ = clean_citations(answer, len(sources))
        except Exception as exc:  # keep going; a failed call counts as wrong
            answer, error = "", f"{type(exc).__name__}: {exc}"
        seconds = time.monotonic() - started
        row = {"id": question["id"], "lang": question.get("lang", "en"), "question": question["question"],
               "answer": answer, "seconds": round(seconds, 2), "error": error, **grade(question, answer, sources),
               "sources": [{"label": f"S{i}", "source_name": s["source_name"], "score": round(s["score"], 3)}
                           for i, s in enumerate(sources, start=1)]}
        if error:
            row["correct"] = False
        rows.append(row)
        mark = "✓" if row["correct"] else "✗"
        print(f"  [{number:>2}/{len(questions)}] {mark} {question['id']} ({seconds:.1f} s)", flush=True)

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    return {
        "provider": provider_id,
        "model": llm.PROVIDERS[provider_id].model,
        "correct": sum(r["correct"] for r in answerable),
        "cites_source": sum(bool(r["cites_source"]) for r in answerable),
        "answerable": len(answerable),
        "unanswerable_handled": sum(r["correct"] for r in unanswerable),
        "unanswerable": len(unanswerable),
        "errors": sum(r["error"] is not None for r in rows),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 2) if rows else 0,
        "rows": rows,
    }


def print_retrieval(retrievals: list[dict[str, Any]], top_k: int) -> None:
    print(f"\nSearch (top {top_k} passages)")
    languages = sorted({lang for r in retrievals for lang in r["hit_at_k_by_language"]})
    for r in retrievals:
        mode = f"rerank with {r['reranker']}" if r["reranker"] else r["mode"]
        print(f"\n  {r['embedder']} · {mode}  (relevance cutoff {r['min_score']})")
        lines = [
            ("right document ranked first", percent(r["hit_at_1"], r["answerable"])),
            (f"right document in top {top_k}", percent(r["hit_at_k"], r["answerable"])),
            ("mean reciprocal rank", f"{r['mrr']:.2f}"),
            ("off-topic questions with no passages", percent(r["unanswerable_with_no_passages"], r["unanswerable"])),
        ]
        for lang in languages:
            counts = r["hit_at_k_by_language"].get(lang, {"hits": 0, "total": 0})
            lines.append((f"  in top {top_k}, questions in '{lang}'", percent(counts["hits"], counts["total"])))
        cutoff = r["cutoff"]
        if cutoff:
            lines.append(("lowest score of a correct passage", f"{cutoff['lowest_answerable_top_score']:.3f}"))
            lines.append(("highest score of an off-topic passage", f"{cutoff['highest_off_topic_top_score']:.3f}"))
            lines.append(("suggested cutoff", str(cutoff["suggested_min_score"] or "none (scores overlap)")))
        for label, value in lines:
            print(f"    {label:<40} {value}")
        if r["misses"]:
            print(f"    missed: {', '.join(r['misses'])}")


def print_answers(providers: list[dict[str, Any]]) -> None:
    if not providers:
        return
    print("\nAnswers")
    print(f"  {'model':<34} {'correct':<14} {'cites right doc':<16} {'says not covered':<17} {'avg time':>8}")
    for p in providers:
        name = f"{p['provider']} ({p['model']})"[:34]
        print(f"  {name:<34} {percent(p['correct'], p['answerable']):<14} "
              f"{percent(p['cites_source'], p['answerable']):<16} "
              f"{percent(p['unanswerable_handled'], p['unanswerable']):<17} {p['avg_seconds']:>6.1f} s")
    for p in providers:
        wrong = [r for r in p["rows"] if not r["correct"]]
        if wrong:
            print(f"\n  {p['provider']}: {len(wrong)} wrong")
            for r in wrong:
                answer = (r["error"] or r["answer"]).replace("\n", " ")
                print(f"    - {r['id']}: {r['question']}\n      → {answer[:160]}")


def main_cli() -> None:
    args = parse_args()
    questions = json.loads(args.questions.read_text(encoding="utf-8"))[: args.limit]

    for provider_id in args.providers:
        if provider_id not in llm.PROVIDERS:
            sys.exit(f"Unknown provider '{provider_id}'. Choose from: {', '.join(llm.PROVIDERS)}")
    providers = [] if args.retrieval_only else args.providers
    if not args.retrieval_only and not providers:
        print("No --providers given; scoring search only.")

    retrievals, answer_results = [], []
    for position, embedder_id in enumerate(args.embedders):
        models.set_embedder(embedder_id)
        with tempfile.TemporaryDirectory(prefix="afrisearch-eval-") as workdir:
            index = build_index(args.corpus, Path(workdir))
            for mode_number, mode in enumerate(args.modes):
                set_mode(mode, args.reranker)
                retrieved = {q["id"]: index.retrieve(q["question"], args.top_k) for q in questions}
                raw = {q["id"]: index.retrieve(q["question"], args.top_k, min_score=-1.0) for q in questions}
                retrievals.append(score_retrieval(questions, retrieved, raw, mode))
                if mode_number == 0:
                    answer_sources = retrieved

            if position == 0:  # answer models use the first search model and mode
                for provider_id in providers:
                    reason = llm.PROVIDERS[provider_id].unavailable_reason()
                    if reason:
                        print(f"\nSkipping {provider_id}: {reason}")
                        continue
                    print(f"\nAsking {provider_id} ({llm.PROVIDERS[provider_id].model})...")
                    answer_results.append(score_provider(provider_id, questions, answer_sources))

    print_retrieval(retrievals, args.top_k)
    print_answers(answer_results)

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    report_path.write_text(json.dumps({
        "settings": {"corpus": str(args.corpus), "questions": str(args.questions), "top_k": args.top_k,
                     "embedders": args.embedders, "modes": args.modes, "reranker": args.reranker},
        "retrieval": retrievals,
        "providers": answer_results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull report: {report_path.relative_to(ROOT) if report_path.is_relative_to(ROOT) else report_path}")


if __name__ == "__main__":
    main_cli()
