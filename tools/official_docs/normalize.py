#!/usr/bin/env python3
"""Normalize fetched official docs HTML into pages and chunks JSONL."""
from __future__ import annotations

import argparse
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (
        breadcrumb_from_url,
        classify_url,
        data_dir,
        load_json,
        raw_paths,
        normalize_url,
        read_jsonl,
        stable_id,
        tokenize,
        utc_now,
        write_jsonl,
    )
else:
    from .common import (
        breadcrumb_from_url,
        classify_url,
        data_dir,
        load_json,
        raw_paths,
        normalize_url,
        read_jsonl,
        stable_id,
        tokenize,
        utc_now,
        write_jsonl,
    )


class ContentParser(HTMLParser):
    block_tags = {"p", "li", "pre", "code", "td", "th", "blockquote"}
    heading_tags = {"h1", "h2", "h3", "h4"}
    skip_tags = {"script", "style", "svg", "noscript", "template", "header", "footer", "nav", "aside"}

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.in_title = False
        self.skip_depth = 0
        self.current_tag: str | None = None
        self.current_text: list[str] = []
        self.blocks: list[dict] = []
        self.heading_path: list[str] = []
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs}
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if tag == "title":
            self.in_title = True
        if tag == "link" and (attrs_dict.get("rel") or "").lower() == "canonical":
            self.canonical = attrs_dict.get("href")
        if tag in self.block_tags or tag in self.heading_tags:
            self.flush()
            self.current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "title":
            self.in_title = False
        if tag == self.current_tag:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.current_tag:
            self.current_text.append(data)

    def flush(self) -> None:
        if not self.current_tag:
            return
        text = clean_text(" ".join(self.current_text))
        tag = self.current_tag
        self.current_text = []
        self.current_tag = None
        if not text:
            return
        if tag in self.heading_tags:
            level = int(tag[1])
            self.heading_path = self.heading_path[: max(0, level - 1)]
            self.heading_path.append(text[:160])
        elif len(text) >= 20:
            self.blocks.append({"text": text, "heading_path": list(self.heading_path)})

    @property
    def title(self) -> str:
        return clean_title(" ".join(self.title_parts))


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    noise = {
        "Skip to content",
        "Search",
        "Navigation",
        "Copy page",
        "On this page",
        "Was this page useful?",
    }
    return "" if text in noise else text


def clean_title(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"\s*\|\s*OpenAI Developers\s*$", "", text)
    return text or "OpenAI Developers"


def chunk_blocks(url: str, page_title: str, blocks: list[dict], target_terms: int = 420) -> list[dict]:
    chunks: list[dict] = []
    current: list[str] = []
    heading_path: list[str] = []
    position = 0

    def emit() -> None:
        nonlocal current, heading_path, position
        text = "\n".join(current).strip()
        if not text:
            return
        position += 1
        content_hash = stable_id(url, text, length=40)
        chunks.append(
            {
                "chunk_id": stable_id(url, position, text),
                "page_url": url,
                "title": page_title,
                "heading_path": heading_path,
                "chunk_text": text,
                "token_estimate": len(tokenize(text)),
                "content_hash": content_hash,
                "language": "en",
                "position": position,
            }
        )
        current = []
        heading_path = []

    for block in blocks:
        block_terms = len(tokenize(block["text"]))
        if current and len(tokenize(" ".join(current))) + block_terms > target_terms:
            emit()
        if not heading_path:
            heading_path = block.get("heading_path") or []
        current.append(block["text"])
    emit()
    if not chunks:
        chunks.append(
            {
                "chunk_id": stable_id(url, 1, page_title),
                "page_url": url,
                "title": page_title,
                "heading_path": [],
                "chunk_text": page_title,
                "token_estimate": len(tokenize(page_title)),
                "content_hash": stable_id(url, page_title, length=40),
                "language": "en",
                "position": 1,
            }
        )
    return chunks


def normalize(root: Path) -> tuple[list[dict], list[dict]]:
    pages: list[dict] = []
    chunks: list[dict] = []
    fetched_at = utc_now()
    for row in read_jsonl(root / "urls.jsonl"):
        url = row["url"]
        html_path, meta_path = raw_paths(root, url)
        if not html_path.exists():
            continue
        parser = ContentParser()
        parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))
        parser.flush()
        meta = load_json(meta_path, {})
        page_url = normalize_url(parser.canonical or url) or url
        classes = classify_url(page_url)
        title = parser.title
        page_chunks = chunk_blocks(page_url, title, parser.blocks)
        page = {
            "url": url,
            "canonical_url": page_url,
            "title": title,
            "breadcrumb": breadcrumb_from_url(page_url),
            "product_area": classes["product_area"],
            "category": classes["category"],
            "source_kind": classes["source_kind"],
            "lastmod": row.get("lastmod"),
            "fetched_at": meta.get("fetched_at") or fetched_at,
            "content_hash": meta.get("content_hash") or stable_id(page_url, title, length=40),
            "status": int(meta.get("status") or 200),
            "chunk_count": len(page_chunks),
        }
        pages.append(page)
        chunks.extend(page_chunks)
    write_jsonl(root / "normalized_pages.jsonl", pages)
    write_jsonl(root / "chunks.jsonl", chunks)
    return pages, chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    pages, chunks = normalize(data_dir(args.data_dir))
    print(f"normalized pages={len(pages)} chunks={len(chunks)}")


if __name__ == "__main__":
    main()
