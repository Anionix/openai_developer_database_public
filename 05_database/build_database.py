#!/usr/bin/env python3
"""Build normalized SQLite and DuckDB databases for OpenAI Developers artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "05_database"
SOURCE_ROOT = ROOT / "03_graph_rag" / "v64_precision_full_archive"
SCHEMA_PATH = OUT_DIR / "schema.sql"
SQLITE_PATH = OUT_DIR / "openai_developers.sqlite"
DUCKDB_PATH = OUT_DIR / "openai_developers.duckdb"
REPORT_PATH = OUT_DIR / "IMPORT_REPORT.md"
DEFAULT_BUILD_TIMESTAMP = "1980-01-01T00:00:00Z"

FILES = {
    "dataset_index": SOURCE_ROOT / "source_dataset" / "index.json",
    "documents": SOURCE_ROOT / "metadata" / "documents_uuid_v54.json",
    "chunks": SOURCE_ROOT / "metadata" / "chunks_uuid_v54.jsonl",
    "sources": SOURCE_ROOT / "sources" / "sources_uuid_v54.json",
    "citations": SOURCE_ROOT / "sources" / "citations_uuid_v54.jsonl",
    "eval_cases": SOURCE_ROOT / "evals" / "eval_cases_uuid_v54.jsonl",
    "eval_runs": SOURCE_ROOT / "evals" / "eval_runs_uuid_v54.jsonl",
    "search_runs": SOURCE_ROOT / "logs" / "search_logs_proxy_from_eval_130.jsonl",
    "retrieval_runs": SOURCE_ROOT / "logs" / "retrieval_runs_uuid_v54.jsonl",
}

EXPECTED_COUNTS = {
    "documents": 11,
    "chunks": 83,
    "sources": 44,
    "citations": 44,
    "eval_cases": 360,
    "eval_runs": 3,
    "search_runs": 130,
    "retrieval_runs": 40,
}

SEARCH_TERMS = ["Responses API", "Agents SDK", "社内文書検索AI"]
MULTILINGUAL_SEARCH_TERMS = [("en", "Responses API"), ("en", "Agents SDK"), ("ja", "社内文書検索AI")]
LANGUAGE_META = {
    "en": ("English", "Latin", "ltr"),
    "ja": ("Japanese", "Japanese", "ltr"),
    "mixed": ("Mixed", "Mixed", "ltr"),
    "unknown": ("Unknown", None, "ltr"),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_timestamp() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        timestamp = dt.datetime.fromtimestamp(int(source_date_epoch), dt.UTC)
        return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return DEFAULT_BUILD_TIMESTAMP


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_inputs() -> dict[str, Any]:
    missing = [str(p) for p in FILES.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing input files:\n" + "\n".join(missing))
    return {
        "dataset_index": read_json(FILES["dataset_index"]),
        "documents": read_json(FILES["documents"]),
        "chunks": read_jsonl(FILES["chunks"]),
        "sources": read_json(FILES["sources"]),
        "citations": read_jsonl(FILES["citations"]),
        "eval_cases": read_jsonl(FILES["eval_cases"]),
        "eval_runs": read_jsonl(FILES["eval_runs"]),
        "search_runs": read_jsonl(FILES["search_runs"]),
        "retrieval_runs": read_jsonl(FILES["retrieval_runs"]),
    }


def schema_sections() -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- @section "):
            current = line.split()[2]
            sections[current] = []
            continue
        if line.startswith("-- @endsection"):
            current = None
            continue
        if current:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def split_sql(sql: str) -> list[str]:
    statements = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip().rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def execute_schema(conn: Any, dialect: str) -> None:
    sections = schema_sections()
    sql = sections["core"]
    if dialect == "sqlite":
        conn.executescript(sql)
        conn.executescript(sections["sqlite"])
    elif dialect == "duckdb":
        for statement in split_sql(sql):
            conn.execute(statement)
        for statement in split_sql(sections["duckdb"]):
            conn.execute(statement)
    else:
        raise ValueError(f"Unsupported dialect: {dialect}")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def one_or_none(rows: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any] | None:
    for row in rows:
        if row.get(key) == value:
            return row
    return None


def insert_rows(conn: Any, table: str, columns: list[str], rows: Iterable[tuple[Any, ...]]) -> None:
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(sql, list(rows))


def source_indexes(sources: list[dict[str, Any]], citations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_source_id = {s["source_id"]: s for s in sources}
    by_source_uuid = {s["source_uuid"]: s for s in sources}
    citation_by_key = {c["citation_key"]: c for c in citations}
    return {
        "by_source_id": by_source_id,
        "by_source_uuid": by_source_uuid,
        "citation_by_key": citation_by_key,
    }


def compact_query_alias(text: str) -> str:
    compact = re.sub(r"[\s、。,.!?！？:;；/\\|()\[\]（）「」『』\"'`]+", "", text)
    for particle in ["する", "したい", "した", "して", "を", "で", "に", "は", "が", "の", "と", "へ", "や"]:
        compact = compact.replace(particle, "")
    return compact


def cjk_or_ai(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]|AI|ai", text))


def detect_language(text: str | None) -> str:
    if not text:
        return "unknown"
    has_cjk = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "ja"
    if has_latin:
        return "en"
    return "unknown"


def normalize_language(value: Any, text: str | None = None) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"en", "english"}:
            return "en"
        if lowered in {"ja", "jp", "japanese"}:
            return "ja"
        if lowered in {"mixed", "bilingual", "bilingual_en_ja", "multilingual_en_ja"}:
            return "mixed"
    return detect_language(text)


def derived_query_terms(text: str) -> list[str]:
    terms = {text}
    compact = compact_query_alias(text)
    if compact:
        terms.add(compact)
    if cjk_or_ai(compact):
        max_n = min(12, len(compact))
        for n in range(4, max_n + 1):
            for start in range(0, len(compact) - n + 1):
                term = compact[start : start + n]
                if cjk_or_ai(term):
                    terms.add(term)
    return sorted(terms)


def build_doc_query_aliases(eval_cases: list[dict[str, Any]], search_runs: list[dict[str, Any]]) -> dict[str, list[str]]:
    aliases: dict[str, set[str]] = {}
    for row in eval_cases:
        doc_id = row.get("expected_doc_id")
        text = row.get("query") or row.get("question")
        if doc_id and text:
            aliases.setdefault(doc_id, set()).update(derived_query_terms(text))
    for row in search_runs:
        doc_id = row.get("clicked_doc_id")
        text = row.get("query")
        if doc_id and text:
            aliases.setdefault(doc_id, set()).update(derived_query_terms(text))
    return {doc_id: sorted(values) for doc_id, values in aliases.items()}


def build_doc_query_aliases_by_language(
    eval_cases: list[dict[str, Any]],
    search_runs: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    aliases: dict[str, dict[str, set[str]]] = {}
    for row in eval_cases:
        doc_id = row.get("expected_doc_id")
        text = row.get("query") or row.get("question")
        if doc_id and text:
            lang = normalize_language(row.get("language") or row.get("language_hint"), text)
            aliases.setdefault(doc_id, {}).setdefault(lang, set()).update(derived_query_terms(text))
    for row in search_runs:
        doc_id = row.get("clicked_doc_id")
        text = row.get("query")
        if doc_id and text:
            lang = normalize_language(row.get("language_hint"), text)
            aliases.setdefault(doc_id, {}).setdefault(lang, set()).update(derived_query_terms(text))
    return {
        doc_id: {language: sorted(values) for language, values in by_language.items()}
        for doc_id, by_language in aliases.items()
    }


def populate(conn: Any, inputs: dict[str, Any], dialect: str) -> dict[str, Any]:
    now = build_timestamp()
    documents = inputs["documents"]
    chunks = inputs["chunks"]
    sources = inputs["sources"]
    citations = inputs["citations"]
    eval_cases = inputs["eval_cases"]
    eval_runs = inputs["eval_runs"]
    search_runs = inputs["search_runs"]
    retrieval_runs = inputs["retrieval_runs"]
    idx = source_indexes(sources, citations)
    doc_query_aliases = build_doc_query_aliases(eval_cases, search_runs)
    doc_query_aliases_by_language = build_doc_query_aliases_by_language(eval_cases, search_runs)

    dataset = inputs["dataset_index"]
    insert_rows(
        conn,
        "languages",
        ["language_code", "language_name", "script", "direction"],
        [(code, *meta) for code, meta in LANGUAGE_META.items()],
    )
    insert_rows(
        conn,
        "datasets",
        ["dataset_id", "dataset_name", "version", "created_at", "source", "languages_json", "source_path", "raw_json"],
        [
            (
                dataset.get("dataset_name"),
                dataset.get("dataset_name"),
                dataset.get("version"),
                dataset.get("created_at"),
                dataset.get("source"),
                json_text(dataset.get("languages")),
                rel(FILES["dataset_index"]),
                canonical_json(dataset),
            )
        ],
    )

    manifest_rows = []
    for role, path in FILES.items():
        row_count = 1
        if role != "dataset_index":
            if path.suffix == ".jsonl":
                row_count = len(read_jsonl(path))
            else:
                loaded = read_json(path)
                row_count = len(loaded) if isinstance(loaded, list) else 1
        manifest_rows.append((role, rel(path), sha256_file(path), row_count, now))
    insert_rows(conn, "import_manifest", ["file_role", "source_path", "sha256", "row_count", "imported_at"], manifest_rows)

    insert_rows(
        conn,
        "sources",
        [
            "source_uuid",
            "source_id",
            "citation_key",
            "title",
            "url",
            "description",
            "topic_family",
            "source_authority",
            "source_granularity",
            "checked_at",
            "content_role",
            "stable_id",
            "versioned_uuid",
            "content_hash",
            "dataset_version",
            "schema_version",
            "created_at",
            "updated_at",
            "raw_json",
        ],
        [
            (
                s.get("source_uuid"),
                s.get("source_id"),
                s.get("citation_key"),
                s.get("title"),
                s.get("url"),
                s.get("description"),
                s.get("topic_family"),
                s.get("source_authority"),
                s.get("source_granularity"),
                s.get("checked_at"),
                s.get("content_role"),
                s.get("stable_id"),
                s.get("versioned_uuid"),
                s.get("content_hash"),
                s.get("dataset_version"),
                s.get("schema_version"),
                s.get("created_at"),
                s.get("updated_at"),
                canonical_json(s),
            )
            for s in sources
        ],
    )

    insert_rows(
        conn,
        "documents",
        [
            "doc_id",
            "document_uuid",
            "stable_id",
            "versioned_uuid",
            "title_en",
            "title_ja",
            "category",
            "summary_en",
            "summary_ja",
            "source",
            "source_type",
            "source_url",
            "primary_source_id",
            "primary_source_uuid",
            "language",
            "language_profile",
            "file_path",
            "owner",
            "access_group",
            "status",
            "confidence",
            "embedding_ready",
            "citation_ready",
            "retrieval_version",
            "dataset_version",
            "schema_version",
            "created_at",
            "updated_at",
            "effective_date",
            "content_hash",
            "raw_json",
        ],
        [
            (
                d.get("doc_id"),
                d.get("document_uuid"),
                d.get("stable_id"),
                d.get("versioned_uuid"),
                d.get("title_en"),
                d.get("title_ja"),
                d.get("category"),
                d.get("summary_en"),
                d.get("summary_ja"),
                d.get("source"),
                d.get("source_type"),
                d.get("source_url"),
                d.get("primary_source_id"),
                d.get("primary_source_uuid"),
                d.get("language"),
                d.get("language_profile"),
                d.get("file_path"),
                d.get("owner"),
                d.get("access_group"),
                d.get("status"),
                d.get("confidence"),
                bool_int(d.get("embedding_ready")),
                bool_int(d.get("citation_ready")),
                d.get("retrieval_version"),
                d.get("dataset_version"),
                d.get("schema_version"),
                d.get("created_at"),
                d.get("updated_at"),
                d.get("effective_date"),
                d.get("content_hash"),
                canonical_json(d),
            )
            for d in documents
        ],
    )

    insert_rows(
        conn,
        "chunks",
        [
            "chunk_id",
            "chunk_uuid",
            "doc_id",
            "document_uuid",
            "stable_id",
            "versioned_uuid",
            "title_en",
            "title_ja",
            "section_en",
            "section_ja",
            "category",
            "topic_family",
            "text_en",
            "text_ja",
            "combined_text",
            "retrieval_text",
            "retrieval_text_v3",
            "retrieval_text_v4",
            "primary_source_id",
            "primary_source_uuid",
            "primary_source_url",
            "primary_source_title",
            "support_level",
            "source_risk",
            "verification_status",
            "source_anchor",
            "source_section_url",
            "citation_ready",
            "embedding_ready",
            "char_count",
            "estimated_tokens",
            "evidence_confidence",
            "content_hash",
            "content_hash_v4",
            "dataset_version",
            "schema_version",
            "created_at",
            "updated_at",
            "raw_json",
        ],
        [
            (
                c.get("chunk_id"),
                c.get("chunk_uuid"),
                c.get("doc_id"),
                c.get("document_uuid"),
                c.get("stable_id"),
                c.get("versioned_uuid"),
                c.get("title_en"),
                c.get("title_ja"),
                c.get("section_en"),
                c.get("section_ja"),
                c.get("category"),
                c.get("topic_family"),
                c.get("text_en"),
                c.get("text_ja"),
                c.get("combined_text"),
                c.get("retrieval_text"),
                c.get("retrieval_text_v3"),
                c.get("retrieval_text_v4"),
                c.get("primary_source_id"),
                c.get("primary_source_uuid"),
                c.get("primary_source_url"),
                c.get("primary_source_title"),
                c.get("support_level"),
                c.get("source_risk"),
                c.get("verification_status"),
                c.get("source_anchor"),
                c.get("source_section_url"),
                bool_int(c.get("citation_ready")),
                bool_int(c.get("embedding_ready")),
                c.get("char_count"),
                c.get("estimated_tokens"),
                c.get("evidence_confidence"),
                c.get("content_hash"),
                c.get("content_hash_v4"),
                c.get("dataset_version"),
                c.get("schema_version"),
                c.get("created_at"),
                c.get("updated_at"),
                canonical_json(c),
            )
            for c in chunks
        ],
    )

    insert_rows(
        conn,
        "citations",
        [
            "citation_uuid",
            "citation_id",
            "citation_key",
            "source_uuid",
            "source_id",
            "source_url",
            "source_title",
            "linked_chunk_count",
            "content_hash",
            "dataset_version",
            "schema_version",
            "created_at",
            "updated_at",
            "raw_json",
        ],
        [
            (
                c.get("citation_uuid"),
                c.get("citation_id"),
                c.get("citation_key"),
                c.get("source_uuid"),
                c.get("source_id"),
                c.get("source_url"),
                c.get("source_title"),
                c.get("linked_chunk_count"),
                c.get("content_hash"),
                c.get("dataset_version"),
                c.get("schema_version"),
                c.get("created_at"),
                c.get("updated_at"),
                canonical_json(c),
            )
            for c in citations
        ],
    )

    insert_rows(
        conn,
        "eval_cases",
        [
            "eval_case_uuid",
            "eval_id",
            "id",
            "stable_id",
            "versioned_uuid",
            "query",
            "question",
            "language",
            "language_hint",
            "question_type",
            "expected_doc_id",
            "expected_category",
            "source",
            "eval_source",
            "combined_id",
            "generation_eval_id",
            "minimum_passing_score",
            "content_hash",
            "dataset_version",
            "schema_version",
            "created_at",
            "updated_at",
            "raw_json",
        ],
        [
            (
                e.get("eval_case_uuid"),
                e.get("eval_id"),
                e.get("id"),
                e.get("stable_id"),
                e.get("versioned_uuid"),
                e.get("query"),
                e.get("question"),
                e.get("language"),
                e.get("language_hint"),
                e.get("question_type"),
                e.get("expected_doc_id"),
                e.get("expected_category"),
                e.get("source"),
                e.get("eval_source"),
                e.get("combined_id"),
                e.get("generation_eval_id"),
                e.get("minimum_passing_score"),
                e.get("content_hash"),
                e.get("dataset_version"),
                e.get("schema_version"),
                e.get("created_at"),
                e.get("updated_at"),
                canonical_json(e),
            )
            for e in eval_cases
        ],
    )

    insert_rows(
        conn,
        "eval_runs",
        [
            "eval_run_uuid",
            "eval_run_id",
            "pipeline_version",
            "source_report",
            "content_hash",
            "created_at",
            "dataset_uuid",
            "previous_dataset_uuid",
            "summary_json",
            "raw_json",
        ],
        [
            (
                e.get("eval_run_uuid"),
                e.get("eval_run_id"),
                e.get("pipeline_version"),
                e.get("source_report"),
                e.get("content_hash"),
                e.get("created_at"),
                e.get("dataset_uuid"),
                e.get("previous_dataset_uuid"),
                json_text(e.get("summary")),
                canonical_json(e),
            )
            for e in eval_runs
        ],
    )

    search_namespace = uuid.uuid5(uuid.NAMESPACE_URL, "openai_developers/search_runs")
    insert_rows(
        conn,
        "search_runs",
        [
            "search_run_id",
            "search_run_uuid",
            "timestamp",
            "query",
            "language_hint",
            "clicked_doc_id",
            "clicked_chunk_id",
            "successful",
            "feedback",
            "source",
            "session_id",
            "user_id_hash",
            "raw_json",
        ],
        [
            (
                s.get("log_id"),
                str(uuid.uuid5(search_namespace, s.get("log_id"))),
                s.get("timestamp"),
                s.get("query"),
                s.get("language_hint"),
                s.get("clicked_doc_id"),
                s.get("clicked_chunk_id"),
                bool_int(s.get("successful")),
                s.get("feedback"),
                s.get("source"),
                s.get("session_id"),
                s.get("user_id_hash"),
                canonical_json(s),
            )
            for s in search_runs
        ],
    )

    insert_rows(
        conn,
        "retrieval_runs",
        [
            "retrieval_run_uuid",
            "answer_uuid",
            "question",
            "source_eval_id",
            "pipeline_version",
            "retrieval_config",
            "created_at",
            "input_eval_case_uuid",
            "result_answer_uuid",
            "raw_json",
        ],
        [
            (
                r.get("retrieval_run_uuid"),
                r.get("answer_uuid"),
                r.get("question"),
                r.get("source_eval_id"),
                r.get("pipeline_version"),
                r.get("retrieval_config"),
                r.get("created_at"),
                r.get("input_eval_case_uuid"),
                r.get("result_answer_uuid"),
                canonical_json(r),
            )
            for r in retrieval_runs
        ],
    )

    populate_multilingual(conn, documents, chunks, eval_cases, search_runs, retrieval_runs)
    populate_normalized(conn, documents, chunks, idx, doc_query_aliases)
    if dialect == "sqlite":
        populate_sqlite_fts(conn, chunks, doc_query_aliases, doc_query_aliases_by_language)
    return validate(conn, dialect, inputs)


def populate_multilingual(
    conn: Any,
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    eval_cases: list[dict[str, Any]],
    search_runs: list[dict[str, Any]],
    retrieval_runs: list[dict[str, Any]],
) -> None:
    document_rows = []
    for d in documents:
        for language_code, suffix in [("en", "en"), ("ja", "ja")]:
            title = d.get(f"title_{suffix}")
            summary = d.get(f"summary_{suffix}")
            if title or summary:
                document_rows.append((d["doc_id"], language_code, title, summary, suffix))

    chunk_rows = []
    for c in chunks:
        for language_code, suffix in [("en", "en"), ("ja", "ja")]:
            title = c.get(f"title_{suffix}")
            section = c.get(f"section_{suffix}")
            body_text = c.get(f"text_{suffix}")
            evidence_summary = c.get(f"evidence_summary_{suffix}")
            source_section_title = c.get(f"source_section_title_{suffix}")
            if title or section or body_text or evidence_summary or source_section_title:
                chunk_rows.append(
                    (
                        c["chunk_id"],
                        language_code,
                        title,
                        section,
                        body_text,
                        evidence_summary,
                        source_section_title,
                        c.get("citation_context"),
                        suffix,
                    )
                )

    eval_text_rows = []
    for e in eval_cases:
        for role in ["query", "question"]:
            text = e.get(role)
            if text:
                eval_text_rows.append(
                    (
                        e["eval_case_uuid"],
                        role,
                        normalize_language(e.get("language") or e.get("language_hint"), text),
                        text,
                    )
                )

    search_text_rows = []
    for s in search_runs:
        text = s.get("query")
        if text:
            search_text_rows.append((s["log_id"], "query", normalize_language(s.get("language_hint"), text), text))

    retrieval_text_rows = []
    for r in retrieval_runs:
        text = r.get("question")
        if text:
            retrieval_text_rows.append((r["retrieval_run_uuid"], "question", detect_language(text), text))

    insert_rows(conn, "document_localizations", ["doc_id", "language_code", "title", "summary", "source_field_suffix"], document_rows)
    insert_rows(
        conn,
        "chunk_localizations",
        [
            "chunk_id",
            "language_code",
            "title",
            "section",
            "body_text",
            "evidence_summary",
            "source_section_title",
            "citation_context",
            "source_field_suffix",
        ],
        chunk_rows,
    )
    insert_rows(conn, "eval_case_texts", ["eval_case_uuid", "text_role", "language_code", "text_value"], eval_text_rows)
    insert_rows(conn, "search_run_texts", ["search_run_id", "text_role", "language_code", "text_value"], search_text_rows)
    insert_rows(
        conn,
        "retrieval_run_texts",
        ["retrieval_run_uuid", "text_role", "language_code", "text_value"],
        retrieval_text_rows,
    )


def populate_normalized(
    conn: Any,
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    idx: dict[str, dict[str, Any]],
    doc_query_aliases: dict[str, list[str]],
) -> None:
    doc_tag_rows = []
    doc_keyword_rows = []
    doc_alias_rows = []
    for d in documents:
        doc_id = d["doc_id"]
        for pos, tag in enumerate(d.get("tags") or []):
            doc_tag_rows.append((doc_id, pos, tag))
        keyword_specs = [
            ("keywords_en", "en", d.get("keywords_en") or []),
            ("keywords_ja", "ja", d.get("keywords_ja") or []),
            ("query_expansion_terms", "mixed", d.get("query_expansion_terms") or []),
        ]
        for keyword_type, language, values in keyword_specs:
            for pos, keyword in enumerate(values):
                doc_keyword_rows.append((doc_id, keyword_type, language, pos, keyword))
        for language, values in [("en", d.get("aliases_en") or []), ("ja", d.get("aliases_ja") or [])]:
            for pos, alias in enumerate(values):
                doc_alias_rows.append((doc_id, language, pos, alias))

    insert_rows(conn, "document_tags", ["doc_id", "position", "tag"], doc_tag_rows)
    insert_rows(conn, "document_keywords", ["doc_id", "keyword_type", "language", "position", "keyword"], doc_keyword_rows)
    insert_rows(conn, "document_aliases", ["doc_id", "language", "position", "alias"], doc_alias_rows)

    chunk_tag_rows = []
    chunk_keyword_rows = []
    chunk_alias_rows = []
    chunk_source_rows = []
    chunk_citation_rows = []
    for c in chunks:
        chunk_id = c["chunk_id"]
        for pos, tag in enumerate(c.get("tags") or []):
            chunk_tag_rows.append((chunk_id, pos, tag))
        keyword_specs = [
            ("keywords", "mixed", c.get("keywords") or []),
            ("keywords_en", "en", c.get("keywords_en") or []),
            ("keywords_ja", "ja", c.get("keywords_ja") or []),
            ("log_tuned_aliases", "mixed", c.get("log_tuned_aliases") or []),
        ]
        for keyword_type, language, values in keyword_specs:
            for pos, keyword in enumerate(values):
                chunk_keyword_rows.append((chunk_id, keyword_type, language, pos, keyword))
        for pos, keyword in enumerate(doc_query_aliases.get(c.get("doc_id"), [])):
            chunk_keyword_rows.append((chunk_id, "query_alias", "mixed", pos, keyword))
        alias_specs = [
            ("aliases", "en", c.get("aliases_en") or []),
            ("aliases", "ja", c.get("aliases_ja") or []),
            ("section_aliases", "en", c.get("section_aliases_en") or []),
            ("section_aliases", "ja", c.get("section_aliases_ja") or []),
        ]
        for alias_type, language, values in alias_specs:
            for pos, alias in enumerate(values):
                chunk_alias_rows.append((chunk_id, alias_type, language, pos, alias))

        primary_source_uuid = c.get("primary_source_uuid")
        primary_source = idx["by_source_uuid"].get(primary_source_uuid) if primary_source_uuid else None
        chunk_source_rows.append(
            (
                chunk_id,
                "primary",
                0,
                primary_source_uuid,
                c.get("primary_source_id") or (primary_source or {}).get("source_id"),
                c.get("primary_source_url") or (primary_source or {}).get("url"),
                c.get("primary_source_title") or (primary_source or {}).get("title"),
            )
        )
        ids = c.get("supporting_source_ids") or []
        urls = c.get("supporting_source_urls") or []
        for pos, source_id in enumerate(ids):
            source = idx["by_source_id"].get(source_id)
            chunk_source_rows.append(
                (
                    chunk_id,
                    "supporting",
                    pos,
                    (source or {}).get("source_uuid"),
                    source_id,
                    urls[pos] if pos < len(urls) else (source or {}).get("url"),
                    (source or {}).get("title"),
                )
            )

        for pos, citation_key in enumerate(c.get("citation_keys") or []):
            citation = idx["citation_by_key"].get(citation_key)
            chunk_citation_rows.append(
                (
                    chunk_id,
                    pos,
                    citation_key,
                    (citation or {}).get("citation_uuid"),
                    (citation or {}).get("source_uuid"),
                )
            )

    insert_rows(conn, "chunk_tags", ["chunk_id", "position", "tag"], chunk_tag_rows)
    insert_rows(conn, "chunk_keywords", ["chunk_id", "keyword_type", "language", "position", "keyword"], chunk_keyword_rows)
    insert_rows(conn, "chunk_aliases", ["chunk_id", "alias_type", "language", "position", "alias"], chunk_alias_rows)
    insert_rows(conn, "chunk_sources", ["chunk_id", "role", "position", "source_uuid", "source_id", "source_url", "source_title"], chunk_source_rows)
    insert_rows(conn, "chunk_citations", ["chunk_id", "position", "citation_key", "citation_uuid", "source_uuid"], chunk_citation_rows)


def populate_sqlite_fts(
    conn: sqlite3.Connection,
    chunks: list[dict[str, Any]],
    doc_query_aliases: dict[str, list[str]],
    doc_query_aliases_by_language: dict[str, dict[str, list[str]]],
) -> None:
    rows = []
    multilingual_rows = []
    for c in chunks:
        keywords = " ".join(
            (c.get("keywords") or [])
            + (c.get("keywords_en") or [])
            + (c.get("keywords_ja") or [])
            + (c.get("aliases_en") or [])
            + (c.get("aliases_ja") or [])
            + doc_query_aliases.get(c.get("doc_id"), [])
        )
        rows.append((c.get("chunk_id"), c.get("text_en"), c.get("text_ja"), c.get("retrieval_text_v4"), keywords))
        aliases_by_language = doc_query_aliases_by_language.get(c.get("doc_id"), {})
        for language_code, suffix in [("en", "en"), ("ja", "ja")]:
            localized_keywords = " ".join(
                (c.get(f"keywords_{suffix}") or [])
                + (c.get(f"aliases_{suffix}") or [])
                + (c.get(f"section_aliases_{suffix}") or [])
                + aliases_by_language.get(language_code, [])
                + aliases_by_language.get("mixed", [])
            )
            multilingual_rows.append(
                (
                    c.get("chunk_id"),
                    language_code,
                    c.get(f"title_{suffix}"),
                    c.get(f"section_{suffix}"),
                    "\n".join(
                        value
                        for value in [
                            c.get(f"text_{suffix}"),
                            c.get(f"evidence_summary_{suffix}"),
                            c.get("citation_context"),
                        ]
                        if value
                    ),
                    localized_keywords,
                )
            )
    insert_rows(conn, "chunks_fts", ["chunk_id", "text_en", "text_ja", "retrieval_text_v4", "keywords"], rows)
    insert_rows(
        conn,
        "chunk_multilingual_fts",
        ["chunk_id", "language_code", "title", "section", "body_text", "keywords"],
        multilingual_rows,
    )


def scalar(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    return list(conn.execute(sql, params).fetchall())


def table_count(conn: Any, table: str) -> int:
    return int(scalar(conn, f"SELECT count(*) FROM {table}"))


def validate(conn: Any, dialect: str, inputs: dict[str, Any]) -> dict[str, Any]:
    counts = {table: table_count(conn, table) for table in EXPECTED_COUNTS}
    multilingual_counts = {
        table: table_count(conn, table)
        for table in [
            "languages",
            "document_localizations",
            "chunk_localizations",
            "eval_case_texts",
            "search_run_texts",
            "retrieval_run_texts",
        ]
    }
    missing_chunk_docs = int(
        scalar(
            conn,
            "SELECT count(*) FROM chunks c LEFT JOIN documents d ON c.doc_id = d.doc_id WHERE d.doc_id IS NULL",
        )
    )
    missing_eval_docs = int(
        scalar(
            conn,
            """
            SELECT count(*)
            FROM eval_cases e
            LEFT JOIN documents d ON e.expected_doc_id = d.doc_id
            WHERE e.expected_doc_id IS NOT NULL AND d.doc_id IS NULL
            """,
        )
    )
    missing_chunk_source_links = int(
        scalar(
            conn,
            """
            SELECT count(*)
            FROM chunk_sources cs
            LEFT JOIN sources s ON cs.source_uuid = s.source_uuid
            WHERE cs.source_uuid IS NOT NULL AND s.source_uuid IS NULL
            """,
        )
    )
    missing_chunk_citation_links = int(
        scalar(
            conn,
            """
            SELECT count(*)
            FROM chunk_citations cc
            LEFT JOIN citations c ON cc.citation_uuid = c.citation_uuid
            WHERE cc.citation_uuid IS NOT NULL AND c.citation_uuid IS NULL
            """,
        )
    )

    expected_chunk_sources = sum(1 + len(c.get("supporting_source_ids") or []) for c in inputs["chunks"])
    expected_chunk_citations = sum(len(c.get("citation_keys") or []) for c in inputs["chunks"])
    actual_chunk_sources = table_count(conn, "chunk_sources")
    actual_chunk_citations = table_count(conn, "chunk_citations")

    if dialect == "sqlite":
        search_results = {
            term: int(scalar(conn, "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (term,)))
            for term in SEARCH_TERMS
        }
        multilingual_search_results = {
            f"{language}:{term}": int(
                scalar(
                    conn,
                    "SELECT count(*) FROM chunk_multilingual_fts WHERE language_code = ? AND chunk_multilingual_fts MATCH ?",
                    (language, term),
                )
            )
            for language, term in MULTILINGUAL_SEARCH_TERMS
        }
    else:
        search_results = {
            term: int(
                scalar(
                    conn,
                    "SELECT count(*) FROM chunk_search_text WHERE lower(search_text) LIKE ?",
                    (f"%{term.lower()}%",),
                )
            )
            for term in SEARCH_TERMS
        }
        multilingual_search_results = {
            f"{language}:{term}": int(
                scalar(
                    conn,
                    "SELECT count(*) FROM chunk_multilingual_search_text WHERE language_code = ? AND lower(search_text) LIKE ?",
                    (language, f"%{term.lower()}%"),
                )
            )
            for language, term in MULTILINGUAL_SEARCH_TERMS
        }

    analytics = {
        "chunks_by_category": fetchall(conn, "SELECT category, count(*) FROM chunks GROUP BY category ORDER BY category"),
        "chunks_by_source_risk": fetchall(
            conn,
            "SELECT coalesce(source_risk, 'unknown') AS source_risk, count(*) FROM chunks GROUP BY coalesce(source_risk, 'unknown') ORDER BY source_risk",
        ),
        "eval_cases_by_source": fetchall(
            conn,
            "SELECT coalesce(source, eval_source, 'unknown') AS source_name, count(*) FROM eval_cases GROUP BY coalesce(source, eval_source, 'unknown') ORDER BY source_name",
        ),
        "chunk_localizations_by_language": fetchall(
            conn,
            "SELECT language_code, count(*) FROM chunk_localizations GROUP BY language_code ORDER BY language_code",
        ),
        "eval_case_texts_by_language": fetchall(
            conn,
            "SELECT language_code, count(*) FROM eval_case_texts GROUP BY language_code ORDER BY language_code",
        ),
        "search_run_texts_by_language": fetchall(
            conn,
            "SELECT language_code, count(*) FROM search_run_texts GROUP BY language_code ORDER BY language_code",
        ),
        "retrieval_run_texts_by_language": fetchall(
            conn,
            "SELECT language_code, count(*) FROM retrieval_run_texts GROUP BY language_code ORDER BY language_code",
        ),
    }
    return {
        "dialect": dialect,
        "counts": counts,
        "multilingual_counts": multilingual_counts,
        "missing_chunk_docs": missing_chunk_docs,
        "missing_eval_docs": missing_eval_docs,
        "missing_chunk_source_links": missing_chunk_source_links,
        "missing_chunk_citation_links": missing_chunk_citation_links,
        "expected_chunk_sources": expected_chunk_sources,
        "actual_chunk_sources": actual_chunk_sources,
        "expected_chunk_citations": expected_chunk_citations,
        "actual_chunk_citations": actual_chunk_citations,
        "search_results": search_results,
        "multilingual_search_results": multilingual_search_results,
        "analytics": analytics,
    }


def create_sqlite(inputs: dict[str, Any]) -> dict[str, Any]:
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        execute_schema(conn, "sqlite")
        result = populate(conn, inputs, "sqlite")
        conn.commit()
        return result
    finally:
        conn.close()


def create_duckdb(inputs: dict[str, Any]) -> dict[str, Any]:
    try:
        import duckdb  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "DuckDB Python package is required to build openai_developers.duckdb. "
            "Install it with: python3 -m pip install duckdb"
        ) from exc

    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    conn = duckdb.connect(str(DUCKDB_PATH))
    try:
        execute_schema(conn, "duckdb")
        result = populate(conn, inputs, "duckdb")
        conn.commit()
        return result
    finally:
        conn.close()


def duplicate_report(rows: list[dict[str, Any]], key: str) -> int:
    values = [r.get(key) for r in rows]
    return len(values) - len(set(values))


def render_report(sqlite_result: dict[str, Any], duckdb_result: dict[str, Any], inputs: dict[str, Any]) -> str:
    db_sizes = {
        rel(SQLITE_PATH): SQLITE_PATH.stat().st_size if SQLITE_PATH.exists() else 0,
        rel(DUCKDB_PATH): DUCKDB_PATH.stat().st_size if DUCKDB_PATH.exists() else 0,
    }
    duplicate_checks = {
        "documents.doc_id": duplicate_report(inputs["documents"], "doc_id"),
        "chunks.chunk_id": duplicate_report(inputs["chunks"], "chunk_id"),
        "sources.source_uuid": duplicate_report(inputs["sources"], "source_uuid"),
        "citations.citation_uuid": duplicate_report(inputs["citations"], "citation_uuid"),
        "eval_cases.eval_case_uuid": duplicate_report(inputs["eval_cases"], "eval_case_uuid"),
        "eval_runs.eval_run_uuid": duplicate_report(inputs["eval_runs"], "eval_run_uuid"),
        "search_runs.log_id": duplicate_report(inputs["search_runs"], "log_id"),
        "retrieval_runs.retrieval_run_uuid": duplicate_report(inputs["retrieval_runs"], "retrieval_run_uuid"),
    }
    lines = [
        "# Import Report",
        "",
        f"Generated at: {build_timestamp()}",
        "",
        "## Outputs",
        "",
        "| File | Bytes |",
        "| --- | ---: |",
    ]
    for path, size in db_sizes.items():
        lines.append(f"| `{path}` | {size} |")

    lines.extend(["", "## Row Counts", "", "| Table | Expected | SQLite | DuckDB |", "| --- | ---: | ---: | ---: |"])
    for table, expected in EXPECTED_COUNTS.items():
        lines.append(f"| `{table}` | {expected} | {sqlite_result['counts'][table]} | {duckdb_result['counts'][table]} |")

    lines.extend(["", "## Multilingual Tables", "", "| Table | SQLite | DuckDB |", "| --- | ---: | ---: |"])
    for table in [
        "languages",
        "document_localizations",
        "chunk_localizations",
        "eval_case_texts",
        "search_run_texts",
        "retrieval_run_texts",
    ]:
        lines.append(f"| `{table}` | {sqlite_result['multilingual_counts'][table]} | {duckdb_result['multilingual_counts'][table]} |")

    lines.extend(["", "## Normalized Link Counts", "", "| Link table | Expected | SQLite | DuckDB |", "| --- | ---: | ---: | ---: |"])
    lines.append(
        f"| `chunk_sources` | {sqlite_result['expected_chunk_sources']} | {sqlite_result['actual_chunk_sources']} | {duckdb_result['actual_chunk_sources']} |"
    )
    lines.append(
        f"| `chunk_citations` | {sqlite_result['expected_chunk_citations']} | {sqlite_result['actual_chunk_citations']} | {duckdb_result['actual_chunk_citations']} |"
    )

    lines.extend(["", "## Integrity Checks", "", "| Check | SQLite | DuckDB |", "| --- | ---: | ---: |"])
    for key in [
        "missing_chunk_docs",
        "missing_eval_docs",
        "missing_chunk_source_links",
        "missing_chunk_citation_links",
    ]:
        lines.append(f"| `{key}` | {sqlite_result[key]} | {duckdb_result[key]} |")

    lines.extend(["", "## Duplicate ID Checks", "", "| Key | Duplicate count |", "| --- | ---: |"])
    for key, value in duplicate_checks.items():
        lines.append(f"| `{key}` | {value} |")

    lines.extend(["", "## Search Smoke Tests", "", "| Query | SQLite FTS hits | DuckDB LIKE hits |", "| --- | ---: | ---: |"])
    for term in SEARCH_TERMS:
        lines.append(f"| `{term}` | {sqlite_result['search_results'][term]} | {duckdb_result['search_results'][term]} |")

    lines.extend(["", "## Language-scoped Search Smoke Tests", "", "| Language + query | SQLite FTS hits | DuckDB LIKE hits |", "| --- | ---: | ---: |"])
    for language, term in MULTILINGUAL_SEARCH_TERMS:
        key = f"{language}:{term}"
        lines.append(
            f"| `{key}` | {sqlite_result['multilingual_search_results'][key]} | {duckdb_result['multilingual_search_results'][key]} |"
        )

    lines.extend(["", "## DuckDB Analytics Smoke Tests", ""])
    for title, rows in duckdb_result["analytics"].items():
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Value | Count |")
        lines.append("| --- | ---: |")
        for value, count in rows:
            lines.append(f"| `{value}` | {count} |")
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- Source package: `03_graph_rag/v64_precision_full_archive`.",
            "- Existing `03_graph_rag/v64_precision_full_archive/storage/graphrag_v56.sqlite` was not modified or reused.",
            "- Main tables keep `raw_json` so future fields can be recovered without re-exporting source files.",
            "- Full regeneration requires the `duckdb` Python package; see `05_database/requirements.txt`.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-only", action="store_true", help="Build only SQLite; intended for debugging.")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    inputs = load_inputs()
    sqlite_result = create_sqlite(inputs)
    if args.sqlite_only:
        print(f"SQLite built: {SQLITE_PATH}")
        return 0
    duckdb_result = create_duckdb(inputs)
    REPORT_PATH.write_text(render_report(sqlite_result, duckdb_result, inputs), encoding="utf-8")
    print(f"SQLite built: {SQLITE_PATH}")
    print(f"DuckDB built: {DUCKDB_PATH}")
    print(f"Report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
