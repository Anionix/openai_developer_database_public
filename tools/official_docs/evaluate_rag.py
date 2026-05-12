#!/usr/bin/env python3
"""Evaluate official docs hybrid search against URL-prefix smoke cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import data_dir, ensure_dir, read_jsonl, utc_now
    from search import search_documents
else:
    from .common import data_dir, ensure_dir, read_jsonl, utc_now
    from .search import search_documents


def evaluate(root: Path, top_k: int = 5) -> dict:
    eval_path = root / "rag" / "evals" / "official_retrieval_eval.jsonl"
    cases = list(read_jsonl(eval_path))
    results = []
    passed = 0
    evaluated = 0
    for case in cases:
        query = case.get("query")
        expected = case.get("expected_url_prefix")
        if not query or not expected:
            continue
        evaluated += 1
        docs = search_documents(root, query, mode="hybrid", top_k=top_k)
        top_urls = [doc["url"] for doc in docs]
        ok = any(url.startswith(expected) for url in top_urls)
        passed += int(ok)
        results.append(
            {
                "query": query,
                "expected_url_prefix": expected,
                "passed": ok,
                "top_urls": top_urls,
            }
        )
    return {
        "generated_at": utc_now(),
        "top_k": top_k,
        "evaluated": evaluated,
        "passed": passed,
        "top_k_accuracy": passed / evaluated if evaluated else 0.0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    root = data_dir(args.data_dir)
    report = evaluate(root, top_k=args.top_k)
    output = Path(args.out) if args.out else root / "rag" / "reports" / "official_rag_eval.json"
    ensure_dir(output.parent)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    if report["passed"] != report["evaluated"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
