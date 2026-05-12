#!/usr/bin/env python3
"""Search official docs with SQLite FTS, RAG lite rerank, or hybrid fusion."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import data_dir, tokenize
    from rag_lite_core import answer_top3, fuse_result_sets, search as rag_search
else:
    from .common import data_dir, tokenize
    from .rag_lite_core import answer_top3, fuse_result_sets, search as rag_search


def fts_match_query(query: str) -> str:
    terms = []
    seen = set()
    for term in tokenize(query):
        term = term.replace('"', " ").strip()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(f'"{term}"')
    return " OR ".join(terms) if terms else '"openai"'


def aggregate_fts(rows: list[sqlite3.Row], top_k: int) -> list[dict]:
    by_url: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_url.setdefault(row["page_url"], []).append(row)
    results = []
    for url, group in by_url.items():
        group = sorted(group, key=lambda row: row["rank_score"])
        best = group[0]
        score = 1.0 / (1.0 + max(0.0, float(best["rank_score"])))
        chunks = []
        for row in group[:3]:
            chunks.append(
                {
                    "chunk_id": row["chunk_id"],
                    "heading_path": json.loads(row["heading_path_json"] or "[]"),
                    "snippet": row["chunk_text"][:700],
                    "score": 1.0 / (1.0 + max(0.0, float(row["rank_score"]))),
                }
            )
        results.append(
            {
                "url": url,
                "doc_id": url,
                "title": best["title"],
                "breadcrumb": json.loads(best["breadcrumb_json"] or "[]"),
                "product_area": best["product_area"],
                "category": best["category"],
                "score": score,
                "chunks": chunks,
                "source": "fts",
            }
        )
    results.sort(key=lambda row: row["score"], reverse=True)
    for idx, row in enumerate(results[:top_k], start=1):
        row["rank"] = idx
    return results[:top_k]


def search_fts(root: Path, query: str, top_k: int = 10, chunk_limit: int = 80) -> list[dict]:
    db_path = root / "official_docs.sqlite"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              f.chunk_id,
              f.page_url,
              c.title,
              c.heading_path_json,
              c.chunk_text,
              p.breadcrumb_json,
              p.product_area,
              p.category,
              bm25(official_doc_chunks_fts) AS rank_score
            FROM official_doc_chunks_fts AS f
            JOIN official_doc_chunks AS c ON c.chunk_id = f.chunk_id
            LEFT JOIN official_doc_pages AS p ON p.canonical_url = f.page_url OR p.url = f.page_url
            WHERE official_doc_chunks_fts MATCH ?
            ORDER BY rank_score
            LIMIT ?
            """,
            (fts_match_query(query), chunk_limit),
        ).fetchall()
    finally:
        conn.close()
    return aggregate_fts(rows, top_k)


def search_documents(root: Path, query: str, mode: str = "hybrid", top_k: int = 10) -> list[dict]:
    if mode == "fts":
        return search_fts(root, query, top_k=top_k)
    if mode == "rag":
        return rag_search(root, query, top_k=top_k)
    fts_results = search_fts(root, query, top_k=max(30, top_k * 4))
    candidate_urls = {row["url"] for row in fts_results[:50]}
    rag_results = rag_search(root, query, top_k=max(30, top_k * 4), candidate_urls=candidate_urls or None)
    if not rag_results:
        return fts_results[:top_k]
    if not fts_results:
        return rag_results[:top_k]
    return fuse_result_sets(fts_results, rag_results, top_k=top_k)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--mode", choices=["fts", "rag", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--answer", action="store_true")
    args = parser.parse_args()

    root = data_dir(args.data_dir)
    results = search_documents(root, args.query, mode=args.mode, top_k=args.top_k)
    output = answer_top3(args.query, results) if args.answer else {"query": args.query, "mode": args.mode, "results": results}
    if args.json or args.answer:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for row in results:
            print(f"#{row['rank']} {row['score']:.4f} {row.get('title') or row['url']}")
            print(f"  {row['url']}")


if __name__ == "__main__":
    main()
