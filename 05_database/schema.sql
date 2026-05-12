-- OpenAI Developers normalized database schema.
-- Sections are consumed by build_database.py:
--   core   = common relational schema for SQLite and DuckDB
--   sqlite = SQLite-only extensions
--   duckdb = DuckDB-only extensions

-- @section core
CREATE TABLE datasets (
  dataset_id TEXT PRIMARY KEY,
  dataset_name TEXT NOT NULL,
  version TEXT,
  created_at TEXT,
  source TEXT,
  languages_json TEXT,
  source_path TEXT NOT NULL,
  raw_json TEXT NOT NULL
);

CREATE TABLE import_manifest (
  file_role TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  imported_at TEXT NOT NULL
);

CREATE TABLE languages (
  language_code TEXT PRIMARY KEY,
  language_name TEXT NOT NULL,
  script TEXT,
  direction TEXT NOT NULL DEFAULT 'ltr'
);

CREATE TABLE sources (
  source_uuid TEXT PRIMARY KEY,
  source_id TEXT UNIQUE NOT NULL,
  citation_key TEXT UNIQUE,
  title TEXT,
  url TEXT,
  description TEXT,
  topic_family TEXT,
  source_authority TEXT,
  source_granularity TEXT,
  checked_at TEXT,
  content_role TEXT,
  stable_id TEXT,
  versioned_uuid TEXT,
  content_hash TEXT,
  dataset_version TEXT,
  schema_version TEXT,
  created_at TEXT,
  updated_at TEXT,
  raw_json TEXT NOT NULL
);

CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  document_uuid TEXT UNIQUE NOT NULL,
  stable_id TEXT,
  versioned_uuid TEXT,
  title_en TEXT,
  title_ja TEXT,
  category TEXT,
  summary_en TEXT,
  summary_ja TEXT,
  source TEXT,
  source_type TEXT,
  source_url TEXT,
  primary_source_id TEXT,
  primary_source_uuid TEXT,
  language TEXT,
  language_profile TEXT,
  file_path TEXT,
  owner TEXT,
  access_group TEXT,
  status TEXT,
  confidence TEXT,
  embedding_ready INTEGER,
  citation_ready INTEGER,
  retrieval_version TEXT,
  dataset_version TEXT,
  schema_version TEXT,
  created_at TEXT,
  updated_at TEXT,
  effective_date TEXT,
  content_hash TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (primary_source_uuid) REFERENCES sources(source_uuid)
);

CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  chunk_uuid TEXT UNIQUE NOT NULL,
  doc_id TEXT NOT NULL,
  document_uuid TEXT,
  stable_id TEXT,
  versioned_uuid TEXT,
  title_en TEXT,
  title_ja TEXT,
  section_en TEXT,
  section_ja TEXT,
  category TEXT,
  topic_family TEXT,
  text_en TEXT,
  text_ja TEXT,
  combined_text TEXT,
  retrieval_text TEXT,
  retrieval_text_v3 TEXT,
  retrieval_text_v4 TEXT,
  primary_source_id TEXT,
  primary_source_uuid TEXT,
  primary_source_url TEXT,
  primary_source_title TEXT,
  support_level TEXT,
  source_risk TEXT,
  verification_status TEXT,
  source_anchor TEXT,
  source_section_url TEXT,
  citation_ready INTEGER,
  embedding_ready INTEGER,
  char_count INTEGER,
  estimated_tokens INTEGER,
  evidence_confidence REAL,
  content_hash TEXT,
  content_hash_v4 TEXT,
  dataset_version TEXT,
  schema_version TEXT,
  created_at TEXT,
  updated_at TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
  FOREIGN KEY (document_uuid) REFERENCES documents(document_uuid),
  FOREIGN KEY (primary_source_uuid) REFERENCES sources(source_uuid)
);

CREATE TABLE citations (
  citation_uuid TEXT PRIMARY KEY,
  citation_id TEXT UNIQUE,
  citation_key TEXT UNIQUE,
  source_uuid TEXT,
  source_id TEXT,
  source_url TEXT,
  source_title TEXT,
  linked_chunk_count INTEGER,
  content_hash TEXT,
  dataset_version TEXT,
  schema_version TEXT,
  created_at TEXT,
  updated_at TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (source_uuid) REFERENCES sources(source_uuid)
);

CREATE TABLE eval_cases (
  eval_case_uuid TEXT PRIMARY KEY,
  eval_id TEXT,
  id TEXT,
  stable_id TEXT,
  versioned_uuid TEXT,
  query TEXT,
  question TEXT,
  language TEXT,
  language_hint TEXT,
  question_type TEXT,
  expected_doc_id TEXT,
  expected_category TEXT,
  source TEXT,
  eval_source TEXT,
  combined_id TEXT,
  generation_eval_id TEXT,
  minimum_passing_score REAL,
  content_hash TEXT,
  dataset_version TEXT,
  schema_version TEXT,
  created_at TEXT,
  updated_at TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (expected_doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE eval_runs (
  eval_run_uuid TEXT PRIMARY KEY,
  eval_run_id TEXT UNIQUE,
  pipeline_version TEXT,
  source_report TEXT,
  content_hash TEXT,
  created_at TEXT,
  dataset_uuid TEXT,
  previous_dataset_uuid TEXT,
  summary_json TEXT,
  raw_json TEXT NOT NULL
);

CREATE TABLE search_runs (
  search_run_id TEXT PRIMARY KEY,
  search_run_uuid TEXT UNIQUE NOT NULL,
  timestamp TEXT,
  query TEXT NOT NULL,
  language_hint TEXT,
  clicked_doc_id TEXT,
  clicked_chunk_id TEXT,
  successful INTEGER,
  feedback TEXT,
  source TEXT,
  session_id TEXT,
  user_id_hash TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (clicked_doc_id) REFERENCES documents(doc_id),
  FOREIGN KEY (clicked_chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE retrieval_runs (
  retrieval_run_uuid TEXT PRIMARY KEY,
  answer_uuid TEXT,
  question TEXT,
  source_eval_id TEXT,
  pipeline_version TEXT,
  retrieval_config TEXT,
  created_at TEXT,
  input_eval_case_uuid TEXT,
  result_answer_uuid TEXT,
  raw_json TEXT NOT NULL,
  FOREIGN KEY (input_eval_case_uuid) REFERENCES eval_cases(eval_case_uuid)
);

CREATE TABLE document_localizations (
  doc_id TEXT NOT NULL,
  language_code TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  source_field_suffix TEXT NOT NULL,
  PRIMARY KEY (doc_id, language_code),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
  FOREIGN KEY (language_code) REFERENCES languages(language_code)
);

CREATE TABLE chunk_localizations (
  chunk_id TEXT NOT NULL,
  language_code TEXT NOT NULL,
  title TEXT,
  section TEXT,
  body_text TEXT,
  evidence_summary TEXT,
  source_section_title TEXT,
  citation_context TEXT,
  source_field_suffix TEXT NOT NULL,
  PRIMARY KEY (chunk_id, language_code),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (language_code) REFERENCES languages(language_code)
);

CREATE TABLE eval_case_texts (
  eval_case_uuid TEXT NOT NULL,
  text_role TEXT NOT NULL,
  language_code TEXT NOT NULL,
  text_value TEXT NOT NULL,
  PRIMARY KEY (eval_case_uuid, text_role),
  FOREIGN KEY (eval_case_uuid) REFERENCES eval_cases(eval_case_uuid),
  FOREIGN KEY (language_code) REFERENCES languages(language_code)
);

CREATE TABLE search_run_texts (
  search_run_id TEXT NOT NULL,
  text_role TEXT NOT NULL,
  language_code TEXT NOT NULL,
  text_value TEXT NOT NULL,
  PRIMARY KEY (search_run_id, text_role),
  FOREIGN KEY (search_run_id) REFERENCES search_runs(search_run_id),
  FOREIGN KEY (language_code) REFERENCES languages(language_code)
);

CREATE TABLE retrieval_run_texts (
  retrieval_run_uuid TEXT NOT NULL,
  text_role TEXT NOT NULL,
  language_code TEXT NOT NULL,
  text_value TEXT NOT NULL,
  PRIMARY KEY (retrieval_run_uuid, text_role),
  FOREIGN KEY (retrieval_run_uuid) REFERENCES retrieval_runs(retrieval_run_uuid),
  FOREIGN KEY (language_code) REFERENCES languages(language_code)
);

CREATE TABLE document_tags (
  doc_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (doc_id, position),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE document_keywords (
  doc_id TEXT NOT NULL,
  keyword_type TEXT NOT NULL,
  language TEXT NOT NULL,
  position INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  PRIMARY KEY (doc_id, keyword_type, language, position),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE document_aliases (
  doc_id TEXT NOT NULL,
  language TEXT NOT NULL,
  position INTEGER NOT NULL,
  alias TEXT NOT NULL,
  PRIMARY KEY (doc_id, language, position),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE chunk_tags (
  chunk_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (chunk_id, position),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE chunk_keywords (
  chunk_id TEXT NOT NULL,
  keyword_type TEXT NOT NULL,
  language TEXT NOT NULL,
  position INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  PRIMARY KEY (chunk_id, keyword_type, language, position),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE chunk_aliases (
  chunk_id TEXT NOT NULL,
  alias_type TEXT NOT NULL,
  language TEXT NOT NULL,
  position INTEGER NOT NULL,
  alias TEXT NOT NULL,
  PRIMARY KEY (chunk_id, alias_type, language, position),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE chunk_sources (
  chunk_id TEXT NOT NULL,
  role TEXT NOT NULL,
  position INTEGER NOT NULL,
  source_uuid TEXT,
  source_id TEXT,
  source_url TEXT,
  source_title TEXT,
  PRIMARY KEY (chunk_id, role, position),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (source_uuid) REFERENCES sources(source_uuid)
);

CREATE TABLE chunk_citations (
  chunk_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  citation_key TEXT NOT NULL,
  citation_uuid TEXT,
  source_uuid TEXT,
  PRIMARY KEY (chunk_id, position),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (citation_uuid) REFERENCES citations(citation_uuid),
  FOREIGN KEY (source_uuid) REFERENCES sources(source_uuid)
);

CREATE INDEX idx_documents_category ON documents(category);
CREATE INDEX idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX idx_chunks_category ON chunks(category);
CREATE INDEX idx_chunks_source_risk ON chunks(source_risk);
CREATE INDEX idx_sources_source_id ON sources(source_id);
CREATE INDEX idx_eval_cases_expected_doc ON eval_cases(expected_doc_id);
CREATE INDEX idx_eval_cases_source ON eval_cases(source);
CREATE INDEX idx_search_runs_clicked_doc ON search_runs(clicked_doc_id);
CREATE INDEX idx_retrieval_runs_source_eval ON retrieval_runs(source_eval_id);
CREATE INDEX idx_document_localizations_language ON document_localizations(language_code);
CREATE INDEX idx_chunk_localizations_language ON chunk_localizations(language_code);
CREATE INDEX idx_eval_case_texts_language ON eval_case_texts(language_code);
CREATE INDEX idx_search_run_texts_language ON search_run_texts(language_code);
CREATE INDEX idx_retrieval_run_texts_language ON retrieval_run_texts(language_code);
CREATE INDEX idx_chunk_sources_source_uuid ON chunk_sources(source_uuid);
CREATE INDEX idx_chunk_citations_citation_uuid ON chunk_citations(citation_uuid);
-- @endsection

-- @section sqlite
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  chunk_id UNINDEXED,
  text_en,
  text_ja,
  retrieval_text_v4,
  keywords
);

CREATE VIRTUAL TABLE chunk_multilingual_fts USING fts5(
  chunk_id UNINDEXED,
  language_code UNINDEXED,
  title,
  section,
  body_text,
  keywords
);
-- @endsection

-- @section duckdb
CREATE VIEW chunk_search_text AS
SELECT
  c.chunk_id,
  c.doc_id,
  c.title_en,
  c.title_ja,
  c.category,
  c.source_risk,
  concat_ws(
    '\n',
    coalesce(c.text_en, ''),
    coalesce(c.text_ja, ''),
    coalesce(c.retrieval_text_v4, ''),
    coalesce((SELECT string_agg(keyword, ' ') FROM chunk_keywords k WHERE k.chunk_id = c.chunk_id), '')
  ) AS search_text
FROM chunks c;

CREATE VIEW chunk_multilingual_search_text AS
SELECT
  l.chunk_id,
  l.language_code,
  c.doc_id,
  c.category,
  c.source_risk,
  l.title,
  l.section,
  concat_ws(
    '\n',
    coalesce(l.title, ''),
    coalesce(l.section, ''),
    coalesce(l.body_text, ''),
    coalesce(l.evidence_summary, ''),
    coalesce(l.citation_context, ''),
    coalesce((SELECT string_agg(keyword, ' ') FROM chunk_keywords k WHERE k.chunk_id = l.chunk_id AND k.language IN (l.language_code, 'mixed')), '')
  ) AS search_text
FROM chunk_localizations l
JOIN chunks c ON c.chunk_id = l.chunk_id;
-- @endsection
