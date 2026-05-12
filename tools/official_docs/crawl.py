#!/usr/bin/env python3
"""Fetch discovered official docs pages with conservative rate limiting."""
from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import append_jsonl, data_dir, ensure_dir, load_json, normalize_url, open_text, raw_paths, read_jsonl, save_json, sha256_text, utc_now
else:
    from .common import append_jsonl, data_dir, ensure_dir, load_json, normalize_url, open_text, raw_paths, read_jsonl, save_json, sha256_text, utc_now


def crawl(root: Path, limit: int | None = None, sleep_seconds: float = 1.0) -> dict:
    urls_path = root / "urls.jsonl"
    rows = list(read_jsonl(urls_path))
    if limit:
        rows = rows[:limit]
    ensure_dir(root / "raw_pages")

    started = utc_now()
    run = {
        "run_id": sha256_text(f"{started}:{len(rows)}")[:16],
        "started_at": started,
        "finished_at": None,
        "requested_count": len(rows),
        "changed_count": 0,
        "unchanged_count": 0,
        "error_count": 0,
        "errors": [],
    }

    for index, row in enumerate(rows):
        original_url = row.get("url", "")
        url = normalize_url(original_url)
        if not url:
            run["error_count"] += 1
            run["errors"].append({"url": original_url, "error": "URL rejected by developers.openai.com policy"})
            print(f"[{index + 1}/{len(rows)}] skipped non-developers URL: {original_url}", flush=True)
            if sleep_seconds > 0 and index != len(rows) - 1:
                time.sleep(sleep_seconds)
            continue
        print(f"[{index + 1}/{len(rows)}] {url}", flush=True)
        html_path, meta_path = raw_paths(root, url)
        previous = load_json(meta_path, {})
        try:
            html, headers, status = open_text(url)
            content_hash = sha256_text(html)
            if previous.get("content_hash") == content_hash:
                run["unchanged_count"] += 1
            else:
                html_path.write_text(html, encoding="utf-8")
                save_json(
                    meta_path,
                    {
                        "url": url,
                        "status": status,
                        "content_hash": content_hash,
                        "content_type": headers.get("content-type"),
                        "etag": headers.get("etag"),
                        "last_modified": headers.get("last-modified"),
                        "fetched_at": utc_now(),
                    },
                )
                run["changed_count"] += 1
        except Exception as exc:  # network smoke should continue and report errors
            run["error_count"] += 1
            run["errors"].append({"url": url, "error": str(exc)[:500]})
        if sleep_seconds > 0 and index != len(rows) - 1:
            time.sleep(sleep_seconds)

    run["finished_at"] = utc_now()
    append_jsonl(root / "crawl_runs.jsonl", run)
    return run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    run = crawl(data_dir(args.data_dir), limit=args.limit, sleep_seconds=args.sleep)
    print(
        "crawl "
        f"changed={run['changed_count']} unchanged={run['unchanged_count']} "
        f"errors={run['error_count']} run_id={run['run_id']}"
    )


if __name__ == "__main__":
    main()
