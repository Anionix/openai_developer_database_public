#!/usr/bin/env python3
"""Build official docs RAG lite assets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import data_dir
    from rag_lite_core import build_assets
else:
    from .common import data_dir
    from .rag_lite_core import build_assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    manifest = build_assets(data_dir(args.data_dir))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
