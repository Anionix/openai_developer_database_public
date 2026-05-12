CREATE TABLE IF NOT EXISTS official_doc_pages (
  url TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  breadcrumb_json TEXT NOT NULL,
  product_area TEXT NOT NULL,
  category TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  lastmod TEXT,
  fetched_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status INTEGER NOT NULL,
  chunk_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS official_doc_chunks (
  chunk_id TEXT PRIMARY KEY,
  page_url TEXT NOT NULL,
  title TEXT NOT NULL,
  heading_path_json TEXT NOT NULL,
  chunk_text TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  language TEXT NOT NULL,
  position INTEGER NOT NULL,
  FOREIGN KEY(page_url) REFERENCES official_doc_pages(canonical_url)
);

CREATE TABLE IF NOT EXISTS official_doc_crawl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  requested_count INTEGER NOT NULL,
  changed_count INTEGER NOT NULL,
  unchanged_count INTEGER NOT NULL,
  error_count INTEGER NOT NULL,
  errors_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS official_doc_embeddings (
  chunk_id TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  embedding_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(chunk_id) REFERENCES official_doc_chunks(chunk_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS official_doc_chunks_fts USING fts5(
  chunk_id UNINDEXED,
  page_url UNINDEXED,
  title,
  breadcrumb,
  heading_path,
  chunk_text
);
