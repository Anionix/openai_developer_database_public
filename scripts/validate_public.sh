#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${PYTHONPYCACHEPREFIX:-}" ]]; then
  if ! pycache_tmp="$(mktemp -d "${TMPDIR:-/tmp}/public-pycache.XXXXXX" 2>/dev/null)"; then
    pycache_tmp="$(mktemp -d "$ROOT_DIR/.public-validation-pycache.XXXXXX")"
  fi
  export PYTHONPYCACHEPREFIX="$pycache_tmp"
  trap 'rm -rf "$pycache_tmp"' EXIT
fi

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "missing required public file: $1" >&2
    exit 1
  fi
}

for path in \
  README.md \
  DISCLAIMER.md \
  NOTICE.md \
  LICENSE \
  DATA_LICENSE.md \
  PUBLIC_RELEASE_BOUNDARY.md \
  05_database/build_database.py \
  05_database/schema.sql \
  05_database/requirements.txt \
  05_database/requirements.lock.txt \
  flake.nix \
  .github/workflows/ci.yml \
  .github/workflows/dependency-review.yml \
  scripts/validate_public_negative.sh
do
  require_file "$path"
done

python -m py_compile 05_database/build_database.py tools/official_docs/*.py
bash -n scripts/validate_public.sh
bash -n scripts/validate_public_negative.sh
if [[ -n "${pycache_tmp:-}" ]]; then
  rm -rf "$pycache_tmp"
  trap - EXIT
fi

retired_boundary_file="PUBLIC_""PRI""VATE_SPLIT.md"
if [[ -e "$retired_boundary_file" ]]; then
  echo "retired boundary document is present in public repo" >&2
  exit 1
fi

expected_workflows=(
  ".github/workflows/ci.yml"
  ".github/workflows/dependency-review.yml"
)
while IFS= read -r workflow_file; do
  allowed_workflow=false
  for expected_workflow in "${expected_workflows[@]}"; do
    if [[ "$workflow_file" == "$expected_workflow" ]]; then
      allowed_workflow=true
      break
    fi
  done
  if [[ "$allowed_workflow" != true ]]; then
    echo "unexpected GitHub Actions workflow in public repo: $workflow_file" >&2
    exit 1
  fi
done < <(find .github/workflows -maxdepth 1 -type f | sort)

extract_workflow_uses() {
  sed -n -E "s/^[[:space:]]*uses:[[:space:]]*['\"]?([^'\"[:space:]]+)['\"]?.*/\1/p" .github/workflows/*.yml
}

while IFS= read -r action_ref; do
  case "$action_ref" in
    actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd|\
    actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294|\
    cachix/install-nix-action@9280e7aca88deada44c930f1e2c78e21c3ae3edd)
      ;;
    *)
      echo "unapproved GitHub Action reference in workflow: $action_ref" >&2
      exit 1
      ;;
  esac
done < <(extract_workflow_uses)

workflow_write_permission_pattern="^[[:space:]]*(pull-requests|contents|actions|checks|issues|statuses):[[:space:]]*write"
if grep -R -I -n -E "$workflow_write_permission_pattern" .github/workflows >/dev/null 2>&1; then
  echo "public workflow requests write permissions" >&2
  exit 1
fi

comment_summary_option="comment-summary-in-""pr"
if grep -R -I -n "$comment_summary_option" .github/workflows >/dev/null 2>&1; then
  echo "dependency review PR comment summary is disabled for minimum permissions" >&2
  exit 1
fi

if ! grep -q "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294" .github/workflows/dependency-review.yml; then
  echo "dependency review workflow is not pinned to the approved action SHA" >&2
  exit 1
fi

if ! grep -q "^[[:space:]]*pull_request:" .github/workflows/dependency-review.yml; then
  echo "dependency review workflow must run on pull_request" >&2
  exit 1
fi

if grep -n -E "^[[:space:]]*(push|workflow_dispatch|schedule):" .github/workflows/dependency-review.yml >/dev/null 2>&1; then
  echo "dependency review workflow has an unapproved trigger" >&2
  exit 1
fi

for excluded_path in \
  00_source_zips \
  01_math_model \
  02_bilingual_summary \
  03_graph_rag \
  04_indexes \
  06_official_docs \
  06_official_docs_scrapling \
  05_database/openai_developers.sqlite \
  05_database/openai_developers.duckdb \
  05_database/IMPORT_REPORT.md \
  docs/local-maintenance
do
  if [[ -e "$excluded_path" ]]; then
    echo "excluded path is present in public repo: $excluded_path" >&2
    exit 1
  fi
done

if find . -type f ! -path './.git/*' \( \
  -name '*.sqlite' -o \
  -name '*.duckdb' -o \
  -name '*.npy' -o \
  -name 'normalized_pages.jsonl' -o \
  -name 'chunks.jsonl' -o \
  -name 'crawl_runs.jsonl' -o \
  -name 'urls.jsonl' -o \
  -name 'vector_manifest.json' -o \
  -name 'OFFICIAL_DOCS_IMPORT_REPORT.json' -o \
  -name 'OFFICIAL_DOCS_IMPORT_REPORT.md' -o \
  -name 'embedding_records_official.jsonl' -o \
  -name 'official_rag_eval.json' -o \
  -name 'scrapling_backend_comparison.json' -o \
  -name 'requirements-scrapling.txt' -o \
  -name 'requirements-scrapling.in' -o \
  -name 'requirements-scrapling.lock.txt' -o \
  -name 'scrapling_adapter.py' -o \
  -name 'compare_crawl_backends.py' -o \
  -name 'run_scrapling_full_crawl_comparison.sh' -o \
  -name 'lock_scrapling_requirements.sh' -o \
  -name 'scrapling-full-crawl.yml' \
\) | grep -q .; then
  echo "public repo contains generated official-docs data, database, or vector artifacts" >&2
  exit 1
fi

if find . -type d ! -path './.git/*' \( \
  -name raw_pages -o \
  -name .venv-scrapling -o \
  -name .scrapling_cache -o \
  -name .scrapling_crawl -o \
  -path '*/rag/evals' -o \
  -path '*/rag/reports' \
\) | grep -q .; then
  echo "public repo contains excluded official-docs cache/eval/report directories" >&2
  exit 1
fi

while IFS= read -r tool_file; do
  case "$tool_file" in
    tools/official_docs/*.py|tools/official_docs/*.sql|tools/official_docs/README.md)
      ;;
    *)
      echo "tools/official_docs contains a non-code public file: $tool_file" >&2
      exit 1
      ;;
  esac
done < <(find tools/official_docs -type f ! -path '*/__pycache__/*' | sort)

local_path_pattern="(/Users""/|/home""/|/Volumes""/|C:\\\\Users\\\\|/tmp""/[^[:space:]]*open""ai)"
if command -v rg >/dev/null 2>&1; then
  disallowed_boundary_word="pri""vate"
  if rg --hidden -i \
    --glob '!.git/**' \
    --glob '!.venv-nix/**' \
    --glob '!.direnv/**' \
    --glob '!__pycache__/**' \
    "$disallowed_boundary_word" . >/dev/null 2>&1; then
    echo "public repo contains disallowed repository-boundary wording" >&2
    exit 1
  fi
  secret_patterns=(
    "sk-""proj-"
    "sk-""[A-Za-z0-9_-]{20,}"
    "OPENAI_""API_KEY"
    "Bear""er [A-Za-z0-9._-]+"
    "AWS_""ACCESS_KEY_ID"
    "AWS_""SECRET_ACCESS_KEY"
    "GITHUB_""TOKEN"
    "pass""word[[:space:]]*="
    "sec""ret[[:space:]]*="
    "tok""en[[:space:]]*="
  )
  for secret_pattern in "${secret_patterns[@]}"; do
    if rg --hidden -n \
      --glob '!.git/**' \
      --glob '!.venv-nix/**' \
      --glob '!.direnv/**' \
      --glob '!__pycache__/**' \
      "$secret_pattern" . >/dev/null 2>&1; then
      echo "public repo contains a secret-looking value or assignment" >&2
      exit 1
    fi
  done
  generic_secret_assignment_pattern="(pass(word)?|sec""ret|tok""en|api[_-]?key)[[:space:]]*[:=]"
  if rg --hidden -i -n \
    --glob '!.git/**' \
    --glob '!.venv-nix/**' \
    --glob '!.direnv/**' \
    --glob '!__pycache__/**' \
    "$generic_secret_assignment_pattern" . >/dev/null 2>&1; then
    echo "public repo contains a generic secret-looking assignment" >&2
    exit 1
  fi
  if rg --hidden -n \
    --glob '!.git/**' \
    --glob '!.venv-nix/**' \
    --glob '!.direnv/**' \
    --glob '!__pycache__/**' \
    "$local_path_pattern" . >/dev/null 2>&1; then
    echo "public repo contains a local absolute path" >&2
    exit 1
  fi
else
  disallowed_boundary_word="pri""vate"
  if grep -R -I -i \
    --exclude-dir=.git \
    --exclude-dir=.venv-nix \
    --exclude-dir=.direnv \
    --exclude-dir=__pycache__ \
    -E "$disallowed_boundary_word" . >/dev/null 2>&1; then
    echo "public repo contains disallowed repository-boundary wording" >&2
    exit 1
  fi
  generic_secret_assignment_pattern="(pass(word)?|sec""ret|tok""en|api[_-]?key)[[:space:]]*[:=]"
  if grep -R -I -i \
    --exclude-dir=.git \
    --exclude-dir=.venv-nix \
    --exclude-dir=.direnv \
    --exclude-dir=__pycache__ \
    -E "$generic_secret_assignment_pattern" . >/dev/null 2>&1; then
    echo "public repo contains a generic secret-looking assignment" >&2
    exit 1
  fi
  if grep -R -I \
    --exclude-dir=.git \
    --exclude-dir=.venv-nix \
    --exclude-dir=.direnv \
    --exclude-dir=__pycache__ \
    -E "$local_path_pattern" . >/dev/null 2>&1; then
    echo "public repo contains a local absolute path" >&2
    exit 1
  fi
fi

echo "Public repository validation passed."
