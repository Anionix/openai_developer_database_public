# Public Release Boundary

This repository is intended to contain only publishable code, schema, validation
tooling, public documentation, notices, and license files. This document defines
what belongs in the public release and what must be excluded.

## Public-Safe Contents

These paths are intended for public use:

- `05_database/build_database.py`
- `05_database/schema.sql`
- `05_database/requirements.txt`
- `05_database/requirements.lock.txt`
- `flake.nix`
- `scripts/validate_public.sh`
- `scripts/validate_public_negative.sh`
- `tools/official_docs/` crawler, normalization, schema, search, and validation code only. Optional generated-crawl runtime adapters are excluded.
- `.github/workflows/ci.yml`
- `.github/workflows/dependency-review.yml`
- Public docs and notice/license files.

## Do Not Publish

Do not add files that match these categories or path patterns:

- Source exports, source archives, extracted data trees, generated indexes, or
  local maintenance notes.
- Generated database files, including `*.sqlite`, `*.duckdb`, and database
  import reports.
- Generated official-docs crawl state or content, including `raw_pages/`,
  `urls.jsonl`, `normalized_pages.jsonl`, `chunks.jsonl`, `crawl_runs.jsonl`,
  `OFFICIAL_DOCS_IMPORT_REPORT.*`, `official_docs.sqlite`, and
  `official_docs.duckdb`.
- Generated official-docs RAG assets, including `rag/*.npy`, `rag/evals/`,
  `rag/reports/`, `vector_manifest.json`, `embedding_records_official.jsonl`,
  and `official_rag_eval.json`.
- Optional generated-crawl runtime, cache, dependency, comparison, and workflow
  files, including `.venv-scrapling/`, `.scrapling_cache/`,
  `.scrapling_crawl/`, `requirements-scrapling.*`, `scrapling_adapter.py`,
  `compare_crawl_backends.py`, `run_scrapling_full_crawl_comparison.sh`,
  `lock_scrapling_requirements.sh`, `scrapling-full-crawl.yml`, and
  `scrapling_backend_comparison.json`.
- Local virtualenv, build, and cache directories such as `.venv-nix/`,
  `.direnv/`, `result*`, and `__pycache__/`.
- Local absolute paths, credentials, tokens, or machine-specific logs.
- Unapproved workflow files, mutable GitHub Action tag refs, workflow write
  permissions, or pull request comment-summary settings that require broader
  permissions.

The validation scripts enforce these rules with concrete deny-list checks and a
negative test that injects excluded file patterns into a temporary copy.

## Release Rule

Do not publish files that contain copied data, generated database content, local
absolute paths, credentials, or content with uncertain redistribution rights.
Pattern checks cannot prove that arbitrary prose files are free of copied
documentation or restricted text. Review changed text files before release, even
when automated validation passes.
