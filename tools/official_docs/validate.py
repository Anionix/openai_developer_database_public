#!/usr/bin/env python3
"""Validate generated official docs DB and RAG lite assets."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import data_dir, read_jsonl
    from search import search_documents
else:
    from .common import data_dir, read_jsonl
    from .search import search_documents

SMOKE_QUERIES = ["Responses API", "Codex", "Apps SDK", "MCP"]


def require(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"missing required official docs artifact: {path}")


def validate_sqlite(root: Path) -> dict:
    db_path = root / "official_docs.sqlite"
    require(db_path)
    conn = sqlite3.connect(db_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        pages = conn.execute("SELECT count(*) FROM official_doc_pages").fetchone()[0]
        chunks = conn.execute("SELECT count(*) FROM official_doc_chunks").fetchone()[0]
        fts = conn.execute("SELECT count(*) FROM official_doc_chunks_fts").fetchone()[0]
        embeddings = conn.execute("SELECT count(*) FROM official_doc_embeddings").fetchone()[0]
    finally:
        conn.close()
    if integrity != "ok":
        raise SystemExit(f"SQLite integrity failed: {integrity}")
    if pages <= 0 or chunks <= 0 or fts <= 0:
        raise SystemExit(f"empty official docs DB: pages={pages} chunks={chunks} fts={fts}")
    return {"integrity": integrity, "pages": pages, "chunks": chunks, "fts": fts, "embeddings": embeddings}


def validate_duckdb(root: Path) -> dict:
    db_path = root / "official_docs.duckdb"
    require(db_path)
    duckdb_bin = shutil.which("duckdb")
    if not duckdb_bin:
        raise SystemExit("duckdb CLI not found")
    result = subprocess.run(
        [duckdb_bin, str(db_path), "-json", "-c", "SELECT product_area, category, count(*) AS page_count FROM official_doc_pages GROUP BY 1,2 ORDER BY page_count DESC LIMIT 10"],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(result.stdout or "[]")
    if not rows:
        raise SystemExit("DuckDB product/category aggregation returned no rows")
    return {"groups": rows}


def validate_search(root: Path) -> dict:
    query_counts = {}
    for query in SMOKE_QUERIES:
        results = search_documents(root, query, mode="hybrid", top_k=5)
        if not results:
            raise SystemExit(f"official docs search returned no results for: {query}")
        query_counts[query] = len(results)
    return query_counts


def validate_eval(root: Path) -> dict:
    eval_path = root / "rag" / "evals" / "official_retrieval_eval.jsonl"
    if not eval_path.exists():
        return {"status": "skipped", "reason": "no eval file"}
    evaluated = 0
    passed = 0
    failures = []
    for case in read_jsonl(eval_path):
        query = case.get("query")
        prefix = case.get("expected_url_prefix")
        if not query or not prefix:
            continue
        evaluated += 1
        results = search_documents(root, query, mode="hybrid", top_k=5)
        urls = [row["url"] for row in results]
        ok = any(url.startswith(prefix) for url in urls)
        passed += int(ok)
        if not ok:
            failures.append({"query": query, "expected_url_prefix": prefix, "top_urls": urls})
    if failures:
        raise SystemExit(json.dumps({"eval_failures": failures}, ensure_ascii=False, indent=2))
    return {"status": "passed", "evaluated": evaluated, "passed": passed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    root = data_dir(args.data_dir)

    for path in [
        root / "urls.jsonl",
        root / "normalized_pages.jsonl",
        root / "chunks.jsonl",
        root / "crawl_runs.jsonl",
        root / "rag" / "embedding_records_official.jsonl",
        root / "rag" / "dense_alpha1p0_2bit.npy",
        root / "rag" / "vector_manifest.json",
    ]:
        require(path)
    report = {
        "sqlite": validate_sqlite(root),
        "duckdb": validate_duckdb(root),
        "search": validate_search(root),
        "eval": validate_eval(root),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
