#!/usr/bin/env python3
"""Shared helpers for official docs discovery, crawl, normalization, and search."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

BASE_URL = "https://developers.openai.com"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
DEFAULT_SITEMAP = f"{BASE_URL}/sitemap-index.xml"
DEFAULT_DATA_DIR = Path("06_official_docs")
USER_AGENT = "openai-developer-database-official-docs/0.1 (+public tooling)"

PRIORITY_URLS = [
    f"{BASE_URL}/",
    f"{BASE_URL}/api/docs/",
    f"{BASE_URL}/api/docs/guides/migrate-to-responses/",
    f"{BASE_URL}/api/docs/guides/streaming-responses/",
    f"{BASE_URL}/api/docs/guides/agents/",
    f"{BASE_URL}/api/docs/guides/tools-file-search/",
    f"{BASE_URL}/api/docs/guides/embeddings/",
    f"{BASE_URL}/api/docs/guides/realtime/",
    f"{BASE_URL}/api/docs/mcp/",
    f"{BASE_URL}/api/docs/guides/tools-connectors-mcp/",
    f"{BASE_URL}/codex/",
    f"{BASE_URL}/codex/mcp/",
    f"{BASE_URL}/apps-sdk/",
    f"{BASE_URL}/apps-sdk/build/mcp-server/",
    f"{BASE_URL}/commerce/",
    f"{BASE_URL}/ads/",
    f"{BASE_URL}/learn/docs-mcp/",
    f"{BASE_URL}/cookbook/",
    f"{BASE_URL}/blog/",
]


def utc_now() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def data_dir(path: str | Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_DATA_DIR


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: object, length: int = 24) -> str:
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def normalize_url(url: str) -> str | None:
    if not url:
        return None
    url, _fragment = urldefrag(urljoin(BASE_URL, url.strip()))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc != "developers.openai.com":
        return None
    path = parsed.path or "/"
    if not path.endswith("/") and "." not in Path(path).name:
        path += "/"
    return parsed._replace(scheme="https", netloc="developers.openai.com", path=path, params="", query="").geturl()


def open_text(url: str, timeout: int = 30) -> tuple[str, dict[str, str], int]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/plain,*/*"})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, "replace")
        headers = {k.lower(): v for k, v in response.headers.items()}
        return text, headers, int(response.status)


def read_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path, row: dict) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def raw_paths(root: Path, url: str) -> tuple[Path, Path]:
    digest = stable_id(url, length=32)
    return root / "raw_pages" / f"{digest}.html", root / "raw_pages" / f"{digest}.json"


def classify_url(url: str) -> dict[str, str]:
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    first = parts[0] if parts else "home"
    second = parts[1] if len(parts) > 1 else ""
    product_area = {
        "api": "api",
        "codex": "codex",
        "apps-sdk": "apps_sdk",
        "commerce": "commerce",
        "ads": "ads",
        "cookbook": "cookbook",
        "blog": "blog",
        "learn": "learn",
        "resources": "resources",
    }.get(first, first or "home")
    if first == "api" and second == "reference":
        category = "api_reference"
        source_kind = "reference"
    elif first == "api" and second == "docs":
        category = "api_docs"
        source_kind = "docs"
    elif first == "blog":
        category = "blog"
        source_kind = "blog"
    elif first == "cookbook":
        category = "cookbook"
        source_kind = "cookbook"
    elif first == "learn":
        category = "learn"
        source_kind = "learn"
    elif first == "home":
        category = "home"
        source_kind = "landing"
    else:
        category = first.replace("-", "_") if first else "home"
        source_kind = "docs"
    return {"product_area": product_area, "category": category, "source_kind": source_kind}


def breadcrumb_from_url(url: str) -> list[str]:
    path = urlparse(url).path.strip("/")
    if not path:
        return ["OpenAI Developers"]
    names = ["OpenAI Developers"]
    for part in path.split("/"):
        if part:
            names.append(part.replace("-", " ").replace("_", " ").title())
    return names


def tokenize(text: str) -> list[str]:
    base = re.findall(r"[a-z0-9_.-]+|[\u3040-\u30ff\u3400-\u9fff]+", (text or "").lower())
    terms: list[str] = []
    for token in base:
        terms.append(token)
        if len(token) >= 5 and re.search(r"[\u3040-\u30ff\u3400-\u9fff]", token):
            for n in (2, 3):
                terms.extend(token[i : i + n] for i in range(len(token) - n + 1))
    terms.extend(f"{a}_{b}" for a, b in zip(base, base[1:]))
    return terms
