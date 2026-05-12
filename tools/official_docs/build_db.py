#!/usr/bin/env python3
"""Build SQLite FTS and DuckDB analysis databases for official docs."""
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
    from common import data_dir, read_jsonl, save_json, utc_now
else:
    from .common import data_dir, read_jsonl, save_json, utc_now


def schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema.sql"


def build_sqlite(root: Path) -> dict:
    db_path = root / "official_docs.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(schema_path().read_text(encoding="utf-8"))

    pages = list(read_jsonl(root / "normalized_pages.jsonl"))
    chunks = []
    seen_chunk_ids = set()
    for chunk in read_jsonl(root / "chunks.jsonl"):
        if chunk["chunk_id"] in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk["chunk_id"])
        chunks.append(chunk)
    runs = list(read_jsonl(root / "crawl_runs.jsonl"))
    with conn:
        conn.executemany(
            """
            INSERT INTO official_doc_pages
            (url, canonical_url, title, breadcrumb_json, product_area, category, source_kind,
             lastmod, fetched_at, content_hash, status, chunk_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    p["url"],
                    p["canonical_url"],
                    p["title"],
                    json.dumps(p.get("breadcrumb", []), ensure_ascii=False),
                    p["product_area"],
                    p["category"],
                    p["source_kind"],
                    p.get("lastmod"),
                    p["fetched_at"],
                    p["content_hash"],
                    int(p["status"]),
                    int(p.get("chunk_count", 0)),
                )
                for p in pages
            ],
        )
        conn.executemany(
            """
            INSERT INTO official_doc_chunks
            (chunk_id, page_url, title, heading_path_json, chunk_text, token_estimate,
             content_hash, language, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c["chunk_id"],
                    c["page_url"],
                    c["title"],
                    json.dumps(c.get("heading_path", []), ensure_ascii=False),
                    c["chunk_text"],
                    int(c.get("token_estimate", 0)),
                    c["content_hash"],
                    c.get("language") or "en",
                    int(c.get("position", 0)),
                )
                for c in chunks
            ],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO official_doc_crawl_runs
            (run_id, started_at, finished_at, requested_count, changed_count,
             unchanged_count, error_count, errors_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r["run_id"],
                    r["started_at"],
                    r.get("finished_at"),
                    int(r.get("requested_count", 0)),
                    int(r.get("changed_count", 0)),
                    int(r.get("unchanged_count", 0)),
                    int(r.get("error_count", 0)),
                    json.dumps(r.get("errors", []), ensure_ascii=False),
                )
                for r in runs
            ],
        )
        conn.executemany(
            """
            INSERT INTO official_doc_chunks_fts
            (chunk_id, page_url, title, breadcrumb, heading_path, chunk_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c["chunk_id"],
                    c["page_url"],
                    c["title"],
                    " > ".join(next((p.get("breadcrumb", []) for p in pages if p["canonical_url"] == c["page_url"]), [])),
                    " > ".join(c.get("heading_path", [])),
                    c["chunk_text"],
                )
                for c in chunks
            ],
        )
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    return {"sqlite_path": str(db_path), "pages": len(pages), "chunks": len(chunks), "crawl_runs": len(runs), "integrity": integrity}


def quote_sql(value: str) -> str:
    return value.replace("'", "''")


def build_duckdb(root: Path) -> dict:
    duckdb_bin = shutil.which("duckdb")
    db_path = root / "official_docs.duckdb"
    if db_path.exists():
        db_path.unlink()
    if not duckdb_bin:
        return {"duckdb_path": str(db_path), "status": "skipped", "reason": "duckdb CLI not found"}

    pages = quote_sql(str((root / "normalized_pages.jsonl").resolve()))
    chunks = quote_sql(str((root / "chunks.jsonl").resolve()))
    runs = quote_sql(str((root / "crawl_runs.jsonl").resolve()))
    sql = f"""
CREATE TABLE official_doc_pages AS SELECT * FROM read_json_auto('{pages}', format='newline_delimited');
CREATE TABLE official_doc_chunks AS SELECT * FROM read_json_auto('{chunks}', format='newline_delimited');
CREATE TABLE official_doc_crawl_runs AS SELECT * FROM read_json_auto('{runs}', format='newline_delimited');
CREATE OR REPLACE VIEW official_doc_page_counts AS
SELECT product_area, category, count(*) AS page_count
FROM official_doc_pages
GROUP BY product_area, category
ORDER BY page_count DESC, product_area, category;
"""
    subprocess.run([duckdb_bin, str(db_path), "-c", sql], check=True)
    return {"duckdb_path": str(db_path), "status": "built"}


def write_report(root: Path, sqlite_report: dict, duckdb_report: dict) -> None:
    report = {
        "generated_at": utc_now(),
        "sqlite": sqlite_report,
        "duckdb": duckdb_report,
        "embeddings": {"status": "empty_without_openai_api_key", "rows": 0},
    }
    save_json(root / "OFFICIAL_DOCS_IMPORT_REPORT.json", report)
    lines = [
        "# Official Docs Import Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- SQLite pages: `{sqlite_report['pages']}`",
        f"- SQLite chunks: `{sqlite_report['chunks']}`",
        f"- SQLite integrity: `{sqlite_report['integrity']}`",
        f"- DuckDB status: `{duckdb_report['status']}`",
        "- Embeddings: empty unless explicitly generated with an API key.",
        "",
    ]
    (root / "OFFICIAL_DOCS_IMPORT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--with-embeddings", action="store_true", help="Reserved optional path; no-op unless an API key env var is configured.")
    args = parser.parse_args()
    root = data_dir(args.data_dir)
    sqlite_report = build_sqlite(root)
    duckdb_report = build_duckdb(root)
    write_report(root, sqlite_report, duckdb_report)
    print(json.dumps({"sqlite": sqlite_report, "duckdb": duckdb_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
