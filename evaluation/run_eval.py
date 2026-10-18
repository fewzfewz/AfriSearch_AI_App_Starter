"""Score AfriSearch's search and answer models on questions with known answers.

Builds a temporary index of a document folder with the real pipeline (your
data/ folder is not touched), then for each question checks whether search
finds the right document and whether each answer model gets the facts right.

Examples, from the project root:
    python evaluation/run_eval.py --retrieval-only
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
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import llm  # noqa: E402
from backend import main  # noqa: E402  (also sets HF_HOME)
from evaluation.scoring import grade, retrieval_rank  # noqa: E402

HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=HERE / "corpus", help="folder of PDF/TXT documents")
    parser.add_argument("--questions", type=Path, default=HERE / "questions.json")
    parser.add_argument("--providers", nargs="*", default=[], help="answer models to score, e.g. qwen-small claude")
    parser.add_argument("--retrieval-only", action="store_true", help="score search only; no answer models")
    parser.add_argument("--top-k", type=int, default=4, help="passages retrieved per question")
    parser.add_argument("--limit", type=int, help="only use the first N questions")
    parser.add_argument("--output", type=Path, default=HERE / "results", help="where to save the JSON report")
    return parser.parse_args()


def build_index(corpus: Path, workdir: Path) -> None:
    """Index the corpus into a temporary data directory with the real pipeline."""
    main.DATA_DIR = workdir
    main.UPLOAD_DIR = workdir / "uploads"
    main.INDEX_PATH = workdir / "index.json"
    main.EMBEDDINGS_PATH = workdir / "embeddings.npy"
    main.MANIFEST_PATH = workdir / "manifest.json"
    main.UPLOAD_DIR.mkdir(parents=True)
    main.chunks, main.chunk_embeddings = [], None

    files = sorted(p for p in corpus.iterdir() if p.suffix.lower() in main.ALLOWED_EXTENSIONS)
    if not files:
        sys.exit(f"No PDF or TXT files in {corpus}")
    for path in files:
        shutil.copy(path, main.UPLOAD_DIR / path.name)
    result = main.rebuild_index(full=True)
    print(f"Indexed {len(files)} documents into {result['indexed_chunks']} chunks with {main.EMBEDDER_ID}")
    for failed in result["failed"]:
        print(f"  ! not indexed: {failed['filename']}: {failed['error']}")


def percent(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "n/a"


def score_retrieval(questions: list[dict[str, Any]], retrieved: dict[str, list]) -> dict[str, Any]:
    answerable = [q for q in questions if q.get("source")]
    unanswerable = [q for q in questions if not q.get("source")]
    ranks = {q["id"]: retrieval_rank(retrieved[q["id"]], q["source"]) for q in answerable}
    hits_at_1 = sum(rank == 1 for rank in ranks.values())
    hits_at_k = sum(rank is not None for rank in ranks.values())
    mrr = sum(1 / rank for rank in ranks.values() if rank) / len(answerable) if answerable else 0.0
    empty_for_unanswerable = sum(not retrieved[q["id"]] for q in unanswerable)
    return {
        "answerable": len(answerable),
        "hit_at_1": hits_at_1,
        "hit_at_k": hits_at_k,
        "mrr": round(mrr, 3),
        "unanswerable": len(unanswerable),
        "unanswerable_with_no_passages": empty_for_unanswerable,
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
            answer = main.generate_answer(question["question"], sources, provider_id)
            answer, _ = main.clean_citations(answer, len(sources))
        except Exception as exc:  # keep going; a failed call counts as wrong
            answer, error = "", f"{type(exc).__name__}: {exc}"
        seconds = time.monotonic() - started
        row = {"id": question["id"], "question": question["question"], "answer": answer,
               "seconds": round(seconds, 2), "error": error, **grade(question, answer, sources),
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


def print_report(retrieval: dict[str, Any], providers: list[dict[str, Any]], top_k: int) -> None:
    print(f"\nSearch (top {top_k} passages)")
    lines = [
        ("right document ranked first", percent(retrieval["hit_at_1"], retrieval["answerable"])),
        (f"right document in top {top_k}", percent(retrieval["hit_at_k"], retrieval["answerable"])),
        ("mean reciprocal rank", f"{retrieval['mrr']:.2f}"),
        ("off-topic questions with no passages",
         percent(retrieval["unanswerable_with_no_passages"], retrieval["unanswerable"])),
    ]
    for label, value in lines:
        print(f"  {label:<38} {value}")
    if retrieval["misses"]:
        print(f"  missed: {', '.join(retrieval['misses'])}")

    if not providers:
        return
    print("\nAnswers")
    header = f"  {'model':<34} {'correct':<14} {'cites right doc':<16} {'says not covered':<17} {'avg time':>8}"
    print(header)
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

    with tempfile.TemporaryDirectory(prefix="afrisearch-eval-") as workdir:
        build_index(args.corpus, Path(workdir))
        retrieved = {q["id"]: main.retrieve(q["question"], args.top_k) for q in questions}
        retrieval = score_retrieval(questions, retrieved)

        results = []
        for provider_id in providers:
            reason = llm.PROVIDERS[provider_id].unavailable_reason()
            if reason:
                print(f"\nSkipping {provider_id}: {reason}")
                continue
            print(f"\nAsking {provider_id} ({llm.PROVIDERS[provider_id].model})...")
            results.append(score_provider(provider_id, questions, retrieved))

    print_report(retrieval, results, args.top_k)

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    report_path.write_text(json.dumps({
        "settings": {"corpus": str(args.corpus), "questions": str(args.questions), "top_k": args.top_k,
                     "embedder": main.EMBEDDER_ID, "min_score": main.MIN_SCORE},
        "retrieval": retrieval,
        "providers": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull report: {report_path.relative_to(ROOT) if report_path.is_relative_to(ROOT) else report_path}")


if __name__ == "__main__":
    main_cli()
