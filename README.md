# OpenAI Developers Database Public Companion

Unofficial fan-made companion repository for the OpenAI Developers database package. This project is not affiliated with, endorsed by, or sponsored by OpenAI.

This repository intentionally excludes source exports, extracted artifact trees,
generated SQLite/DuckDB database files, copied documentation content, and
generated crawl outputs. It contains reproducible packaging code, schema, Nix
tooling, validation entrypoints, and public-facing documentation.

## What Is Included

- `05_database/build_database.py`: database builder for locally supplied artifact trees.
- `05_database/schema.sql`: normalized SQLite/DuckDB schema.
- `05_database/requirements*.txt`: Python DuckDB dependency pins.
- `flake.nix`: lightweight Nix development shell and public validation app.
- `scripts/validate_public.sh`: checks the public repository shape without requiring generated data.
- `scripts/validate_public_negative.sh`: injects excluded artifact patterns into a temporary copy and verifies that public validation rejects them.
- `tools/official_docs/`: public-safe crawler, normalizer, schema, SQLite FTS, DuckDB, and RAG-lite-style search code.
- `.github/workflows/ci.yml`: GitHub Actions validation for the public repo.
- `DISCLAIMER.md`, `NOTICE.md`, `LICENSE`, `DATA_LICENSE.md`, and `PUBLIC_RELEASE_BOUNDARY.md`.

## What Is Not Included

- Source ZIP exports.
- Extracted Graph-RAG, math model, or bilingual summary artifacts.
- Generated `openai_developers.sqlite` and `openai_developers.duckdb` databases.
- Generated official docs crawl cache, SQLite/DuckDB files, RAG vectors, evals, and reports under `06_official_docs/`.
- Optional generated-crawl adapters, dependency lock/input files, runtimes, caches, checkpoints, comparison scripts, workflows, and reports.
- Local maintenance reports.

Those files are intentionally excluded from this public release.

## Quickstart

```bash
git clone <public-repo-url>
cd openai_developer_database_public
nix flake check path:$PWD
nix run path:$PWD#validate-public
./scripts/validate_public_negative.sh
```

To rebuild databases locally, provide the expected artifact tree at
`03_graph_rag/v64_precision_full_archive/` before running the builder.

## Public Safety

This repo is safe to publish because it does not include data artifacts whose
redistribution rights may be uncertain. Do not publish generated data, source
exports, copied official documentation, local logs, credentials, or
machine-specific paths without review.
