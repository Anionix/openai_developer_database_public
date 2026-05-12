#!/usr/bin/env python3
"""Public-safe lightweight retrieval primitives for generated official-doc chunks."""
from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from .common import ensure_dir, read_jsonl, stable_id, tokenize, utc_now, write_jsonl
except ImportError:  # script execution
    from common import ensure_dir, read_jsonl, stable_id, tokenize, utc_now, write_jsonl

DIM = 1536

INTENT_HINTS = {
    "responses": ["responses api", "response", "streaming responses", "migrate to responses"],
    "codex": ["codex", "code review", "mcp server", "cli", "ide"],
    "apps_sdk": ["apps sdk", "chatgpt app", "mcp app", "component"],
    "agents": ["agents sdk", "agent", "guardrail", "handoff"],
    "realtime": ["realtime", "webrtc", "websocket", "voice"],
    "tools": ["file search", "web search", "function calling", "mcp"],
    "embeddings": ["embedding", "vector", "semantic search"],
    "commerce": ["commerce", "checkout", "merchant", "product feed"],
    "ads": ["ads", "campaign", "conversion", "pixel"],
}


def hidx(term: str) -> int:
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest(), "little") % DIM


def hsign(term: str) -> float:
    return 1.0 if hashlib.blake2b(("s:" + term).encode("utf-8"), digest_size=1).digest()[0] & 1 else -1.0


def embed_text(text: str) -> np.ndarray:
    terms = tokenize(text)
    counts = collections.Counter(terms)
    vec = np.zeros(DIM, dtype=np.float32)
    max_tf = max(counts.values()) if counts else 1
    for term, tf in counts.items():
        vec[hidx(term)] += hsign(term) * (0.5 + 0.5 * tf / max_tf)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def ternary(vec: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    threshold = float(np.mean(np.abs(vec)) * alpha)
    out = np.zeros_like(vec, dtype=np.int8)
    out[vec > threshold] = 1
    out[vec < -threshold] = -1
    return out


def pack_2bit(matrix: np.ndarray) -> np.ndarray:
    packed = np.zeros((matrix.shape[0], (DIM + 3) // 4), dtype=np.uint8)
    for col in range(DIM):
        values = matrix[:, col]
        code = np.zeros(matrix.shape[0], dtype=np.uint8)
        code[values > 0] = 1
        code[values < 0] = 2
        packed[:, col // 4] |= code << ((col % 4) * 2)
    return packed


def unpack_2bit(packed: np.ndarray) -> np.ndarray:
    matrix = np.zeros((packed.shape[0], DIM), dtype=np.int8)
    for col in range(DIM):
        code = (packed[:, col // 4] >> ((col % 4) * 2)) & 3
        matrix[code == 1, col] = 1
        matrix[code == 2, col] = -1
    return matrix


def record_text(record: dict) -> str:
    return "\n".join(
        str(x)
        for x in [
            record.get("title"),
            " ".join(record.get("breadcrumb", []) or []),
            " ".join(record.get("heading_path", []) or []),
            record.get("product_area"),
            record.get("category"),
            record.get("chunk_text"),
        ]
        if x
    )


def records_from_pages(root: Path) -> list[dict]:
    pages = {p["canonical_url"]: p for p in read_jsonl(root / "normalized_pages.jsonl")}
    records = []
    for chunk in read_jsonl(root / "chunks.jsonl"):
        page = pages.get(chunk["page_url"], {})
        records.append(
            {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["page_url"],
                "url": chunk["page_url"],
                "title": chunk.get("title") or page.get("title"),
                "breadcrumb": page.get("breadcrumb", []),
                "heading_path": chunk.get("heading_path", []),
                "product_area": page.get("product_area", "unknown"),
                "category": page.get("category", "unknown"),
                "source_kind": page.get("source_kind", "docs"),
                "chunk_text": chunk.get("chunk_text", ""),
                "content_hash": chunk.get("content_hash"),
                "position": chunk.get("position", 0),
            }
        )
    return records


def build_assets(root: Path, alpha: float = 1.0) -> dict:
    rag_dir = root / "rag"
    ensure_dir(rag_dir)
    records = records_from_pages(root)
    if records:
        matrix = np.vstack([ternary(embed_text(record_text(record)), alpha=alpha) for record in records])
        packed = pack_2bit(matrix)
    else:
        packed = np.zeros((0, (DIM + 3) // 4), dtype=np.uint8)
    np.save(rag_dir / "dense_alpha1p0_2bit.npy", packed)
    write_jsonl(rag_dir / "embedding_records_official.jsonl", records)
    manifest = {
        "generated_at": utc_now(),
        "record_count": len(records),
        "dim": DIM,
        "alpha": alpha,
        "format": "2bit_ternary_hashing",
        "source": "06_official_docs/chunks.jsonl",
    }
    (rag_dir / "vector_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def bm25(query_terms: list[str], docs: list[tuple[dict, collections.Counter, int]]) -> dict[str, float]:
    df = collections.Counter()
    for _record, counts, _dl in docs:
        for term in counts:
            df[term] += 1
    avgdl = sum(dl for _record, _counts, dl in docs) / max(len(docs), 1)
    scores: dict[str, float] = {}
    for record, counts, dl in docs:
        score = 0.0
        for term in query_terms:
            if term not in counts:
                continue
            idf = math.log((len(docs) - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
            tf = counts[term]
            denom = tf + 1.35 * (1 - 0.70 + 0.70 * dl / max(avgdl, 1e-9))
            score += idf * (tf * 2.35 / max(denom, 1e-9))
        scores[record["chunk_id"]] = score
    return scores


def minmax(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {key: 0.0 for key in values}
    return {key: (value - lo) / (hi - lo) for key, value in values.items()}


def intent_score(query: str, record: dict) -> float:
    q = query.lower()
    product = str(record.get("product_area") or "").lower()
    category = str(record.get("category") or "").lower()
    score = 0.0
    for intent, hints in INTENT_HINTS.items():
        if any(hint in q for hint in hints):
            if intent in {product, category}:
                score += 0.35
            if intent == "responses" and "responses" in record["url"]:
                score += 0.40
            if intent == "tools" and ("tools" in record["url"] or "mcp" in record["url"]):
                score += 0.35
    return min(1.0, score)


def aggregate_chunks(query: str, chunk_rows: list[dict], top_k: int) -> list[dict]:
    by_doc: dict[str, list[dict]] = collections.defaultdict(list)
    for row in chunk_rows:
        by_doc[row["url"]].append(row)
    results = []
    for url, rows in by_doc.items():
        rows = sorted(rows, key=lambda r: r["score"], reverse=True)
        top = rows[0]
        top3 = rows[:3]
        score = 0.62 * top["score"] + 0.28 * (sum(r["score"] for r in top3) / len(top3)) + min(0.10, 0.02 * len(rows))
        results.append(
            {
                "url": url,
                "doc_id": url,
                "title": top.get("title"),
                "breadcrumb": top.get("breadcrumb", []),
                "product_area": top.get("product_area"),
                "category": top.get("category"),
                "score": float(score),
                "chunks": [
                    {
                        "chunk_id": r["chunk_id"],
                        "heading_path": r.get("heading_path", []),
                        "snippet": r.get("chunk_text", "")[:700],
                        "score": float(r["score"]),
                    }
                    for r in top3
                ],
            }
        )
    results.sort(key=lambda row: row["score"], reverse=True)
    for idx, row in enumerate(results[:top_k], start=1):
        row["rank"] = idx
    return results[:top_k]


def search(root: Path, query: str, top_k: int = 10, candidate_urls: set[str] | None = None) -> list[dict]:
    rag_dir = root / "rag"
    records_path = rag_dir / "embedding_records_official.jsonl"
    vector_path = rag_dir / "dense_alpha1p0_2bit.npy"
    records = list(read_jsonl(records_path)) if records_path.exists() else records_from_pages(root)
    if candidate_urls:
        records = [record for record in records if record.get("url") in candidate_urls]
    if not records:
        return []

    q_terms = tokenize(query)
    docs = [(record, collections.Counter(tokenize(record_text(record))), len(tokenize(record_text(record)))) for record in records]
    bm = minmax(bm25(q_terms, docs))

    vec_scores: dict[str, float] = {}
    if vector_path.exists() and records_path.exists() and not candidate_urls:
        matrix = unpack_2bit(np.load(vector_path)).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.where(norms > 0, norms, 1)
        qv = embed_text(query)
        raw = matrix @ qv
        vec_scores = {records[idx]["chunk_id"]: float(raw[idx]) for idx in range(len(records))}
        vec_scores = minmax(vec_scores)
    else:
        query_vec = embed_text(query)
        vec_scores = {record["chunk_id"]: float(embed_text(record_text(record)) @ query_vec) for record in records}
        vec_scores = minmax(vec_scores)

    chunk_rows = []
    for record in records:
        chunk_id = record["chunk_id"]
        score = 0.58 * bm.get(chunk_id, 0.0) + 0.32 * vec_scores.get(chunk_id, 0.0) + 0.10 * intent_score(query, record)
        row = dict(record)
        row["score"] = float(score)
        chunk_rows.append(row)
    chunk_rows.sort(key=lambda row: row["score"], reverse=True)
    return aggregate_chunks(query, chunk_rows[: max(60, top_k * 8)], top_k)


def rrf(results: Iterable[dict], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rank, row in enumerate(results, start=1):
        url = row.get("url") or row.get("doc_id")
        if url:
            scores[url] = max(scores.get(url, 0.0), 1.0 / (k + rank))
    if not scores:
        return {}
    top = max(scores.values())
    return {url: score / top for url, score in scores.items()}


def fuse_result_sets(fts: list[dict], rag: list[dict], top_k: int = 10) -> list[dict]:
    fts_scores = rrf(fts)
    rag_scores = rrf(rag)
    by_url = {row["url"]: dict(row) for row in fts}
    for row in rag:
        merged = by_url.setdefault(row["url"], dict(row))
        merged.setdefault("chunks", row.get("chunks", []))
        if row.get("chunks") and not merged.get("chunks"):
            merged["chunks"] = row["chunks"]
    fused = []
    for url, row in by_url.items():
        score = 0.46 * fts_scores.get(url, 0.0) + 0.54 * rag_scores.get(url, 0.0)
        row["score"] = float(score)
        row["components"] = {"fts_rrf": fts_scores.get(url, 0.0), "rag_rrf": rag_scores.get(url, 0.0)}
        fused.append(row)
    fused.sort(key=lambda row: row["score"], reverse=True)
    for idx, row in enumerate(fused[:top_k], start=1):
        row["rank"] = idx
    return fused[:top_k]


def answer_top3(query: str, results: list[dict]) -> dict:
    lines = [f"Question: {query}", "", "Top-3 official documentation evidence:"]
    citations = []
    for idx, row in enumerate(results[:3], start=1):
        lines.append(f"{idx}. {row.get('title') or row['url']}")
        lines.append(f"   {row['url']}")
        chunks = row.get("chunks") or []
        if chunks:
            lines.append(f"   {chunks[0].get('snippet', '')[:260]}")
        citations.append(row["url"])
    return {"query": query, "answer": "\n".join(lines), "top_docs": results[:3], "citations": sorted(set(citations))}
