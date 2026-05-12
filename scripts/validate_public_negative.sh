#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_parent="${TMPDIR:-/tmp}"
mkdir -p "$tmp_parent"
tmp="$(mktemp -d "$tmp_parent/openai-public-negative.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

copy_repo() {
  local copy="$1"
  mkdir -p "$copy"
  (
    cd "$ROOT_DIR"
    tar \
      --exclude './.git' \
      --exclude './.direnv' \
      --exclude './.venv-nix' \
      --exclude './.venv-scrapling' \
      -cf - .
  ) | tar -xf - -C "$copy"
}

expect_rejected() {
  local case_name="$1"
  local setup_fn="$2"
  local copy="$tmp/$case_name/repo"
  local output
  local status

  copy_repo "$copy"
  "$setup_fn" "$copy"

  set +e
  output="$(cd "$copy" && bash scripts/validate_public.sh 2>&1)"
  status=$?
  set -e

  if [[ "$status" -eq 0 ]]; then
    echo "negative validation failed for case: $case_name" >&2
    echo "$output" >&2
    exit 1
  fi

  echo "negative case rejected: $case_name"
}

setup_generated_db() {
  local copy="$1"
  printf 'excluded sqlite placeholder\n' > "$copy/leaked.sqlite"
}

setup_official_docs_artifacts() {
  local copy="$1"
  mkdir -p "$copy/raw_pages"
  printf '<html>excluded official docs cache</html>\n' > "$copy/raw_pages/sample.html"
  printf '{"url":"https://developers.openai.com/"}\n' > "$copy/urls.jsonl"
  printf '# Import report\n' > "$copy/OFFICIAL_DOCS_IMPORT_REPORT.md"
}

setup_vector_manifest() {
  local copy="$1"
  printf '{}\n' > "$copy/vector_manifest.json"
}

setup_scrapling_files() {
  local copy="$1"
  mkdir -p "$copy/.scrapling_cache" "$copy/.scrapling_crawl"
  printf 'excluded cache placeholder\n' > "$copy/.scrapling_cache/state"
  printf 'excluded checkpoint placeholder\n' > "$copy/.scrapling_crawl/state"
  printf 'scrapling[fetchers]==0.4.8\n' > "$copy/requirements-scrapling.in"
}

setup_tools_allowlist_violation() {
  local copy="$1"
  printf 'scratch\n' > "$copy/tools/official_docs/some_generated.json"
}

setup_dummy_secret() {
  local copy="$1"
  printf '%s: placeholder\n' "Pass""word" > "$copy/SECRET_SAMPLE.txt"
}

setup_local_path() {
  local copy="$1"
  printf 'path=%s\n' "/Users""/alice/project" > "$copy/LOCAL_PATH_SAMPLE.txt"
}

setup_boundary_wording() {
  local copy="$1"
  printf 'boundary=%s\n' "pri""vate" > "$copy/BOUNDARY_WORD_SAMPLE.txt"
}

setup_retired_boundary_file() {
  local copy="$1"
  printf '# retired boundary placeholder\n' > "$copy/PUBLIC_""PRI""VATE_SPLIT.md"
}

setup_extra_workflow() {
  local copy="$1"
  printf 'name: Extra workflow\non: push\njobs:\n  extra:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n' > "$copy/.github/workflows/semgrep.yml"
}

setup_tag_pinned_action() {
  local copy="$1"
  perl -0pi -e 's|actions/checkout\@93cb6efe18208431cddfb8368fd83d5badbf9bfd|actions/checkout\@v5|' "$copy/.github/workflows/ci.yml"
}

setup_unapproved_action() {
  local copy="$1"
  cat >> "$copy/.github/workflows/ci.yml" <<'EOF'

      - name: Unapproved action
        uses: semgrep/semgrep-action@713efdd345f3035192eaa63f56867b88e63e4e5d
EOF
}

setup_write_permission() {
  local copy="$1"
  cat >> "$copy/.github/workflows/dependency-review.yml" <<'EOF'

permissions:
  pull-requests: write
EOF
}

setup_comment_summary_option() {
  local copy="$1"
  cat >> "$copy/.github/workflows/dependency-review.yml" <<'EOF'

with:
  comment-summary-in-pr: always
EOF
}

setup_combined_artifacts() {
  local copy="$1"
  mkdir -p \
    "$copy/06_official_docs/raw_pages" \
    "$copy/06_official_docs/rag" \
    "$copy/.scrapling_cache" \
    "$copy/.scrapling_crawl" \
    "$copy/tools/official_docs"

  printf '<html>excluded official docs cache</html>\n' > "$copy/06_official_docs/raw_pages/sample.html"
  printf 'excluded sqlite placeholder\n' > "$copy/06_official_docs/official_docs.sqlite"
  printf 'excluded duckdb placeholder\n' > "$copy/06_official_docs/official_docs.duckdb"
  printf 'excluded vector placeholder\n' > "$copy/06_official_docs/rag/dense_alpha1p0_2bit.npy"
  printf '{}\n' > "$copy/06_official_docs/rag/vector_manifest.json"
  printf '{"url":"https://developers.openai.com/"}\n' > "$copy/06_official_docs/urls.jsonl"
  printf '{}\n' > "$copy/06_official_docs/OFFICIAL_DOCS_IMPORT_REPORT.json"
  printf '# Import report\n' > "$copy/06_official_docs/OFFICIAL_DOCS_IMPORT_REPORT.md"
  printf 'excluded cache placeholder\n' > "$copy/.scrapling_cache/state"
  printf 'excluded checkpoint placeholder\n' > "$copy/.scrapling_crawl/state"
  printf 'scrapling[fetchers]==0.4.8\n' > "$copy/tools/official_docs/requirements-scrapling.txt"
  printf 'scrapling[fetchers]==0.4.8\n' > "$copy/tools/official_docs/requirements-scrapling.in"
  printf '# excluded lock placeholder\n' > "$copy/tools/official_docs/requirements-scrapling.lock.txt"
  printf 'raise SystemExit("excluded adapter placeholder")\n' > "$copy/tools/official_docs/scrapling_adapter.py"
  printf '{}\n' > "$copy/06_official_docs/scrapling_backend_comparison.json"
  printf 'scratch\n' > "$copy/tools/official_docs/some_generated.json"
  printf '%s=%s%splaceholder\n' "OPENAI_""API_KEY" "sk-""proj-" "negative-" > "$copy/SECRET_SAMPLE.txt"
  printf 'path=%s\n' "/Users""/alice/project" > "$copy/LOCAL_PATH_SAMPLE.txt"
  printf 'boundary=%s\n' "pri""vate" > "$copy/BOUNDARY_WORD_SAMPLE.txt"
  printf '# retired boundary placeholder\n' > "$copy/PUBLIC_""PRI""VATE_SPLIT.md"
}

expect_rejected generated-db setup_generated_db
expect_rejected official-docs-artifacts setup_official_docs_artifacts
expect_rejected vector-manifest setup_vector_manifest
expect_rejected scrapling-files setup_scrapling_files
expect_rejected tools-allowlist setup_tools_allowlist_violation
expect_rejected dummy-secret setup_dummy_secret
expect_rejected local-path setup_local_path
expect_rejected boundary-wording setup_boundary_wording
expect_rejected retired-boundary-file setup_retired_boundary_file
expect_rejected extra-workflow setup_extra_workflow
expect_rejected tag-pinned-action setup_tag_pinned_action
expect_rejected unapproved-action setup_unapproved_action
expect_rejected write-permission setup_write_permission
expect_rejected comment-summary-option setup_comment_summary_option
expect_rejected combined-artifacts setup_combined_artifacts

echo "Public negative validation passed."
