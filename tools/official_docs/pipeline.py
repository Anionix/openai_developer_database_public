#!/usr/bin/env python3
"""Orchestrate official docs discovery, crawl, and normalization."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import data_dir, write_jsonl
    from crawl import crawl
    from discover import discover
    from normalize import normalize
else:
    from .common import data_dir, write_jsonl
    from .crawl import crawl
    from .discover import discover
    from .normalize import normalize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    root = data_dir(args.data_dir)
    rows = discover(limit=args.limit)
    write_jsonl(root / "urls.jsonl", rows)
    run = crawl(root, limit=args.limit, sleep_seconds=args.sleep)
    pages, chunks = normalize(root)
    print(
        "official docs pipeline "
        f"urls={len(rows)} changed={run['changed_count']} unchanged={run['unchanged_count']} "
        f"errors={run['error_count']} pages={len(pages)} chunks={len(chunks)}"
    )


if __name__ == "__main__":
    main()
