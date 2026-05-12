#!/usr/bin/env python3
"""Discover developers.openai.com URLs from robots, sitemaps, and top navigation."""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import DEFAULT_SITEMAP, PRIORITY_URLS, ROBOTS_URL, data_dir, normalize_url, open_text, utc_now, write_jsonl
else:
    from .common import DEFAULT_SITEMAP, PRIORITY_URLS, ROBOTS_URL, data_dir, normalize_url, open_text, utc_now, write_jsonl


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.links.append(href)


def verify_robots() -> str:
    text, _headers, status = open_text(ROBOTS_URL)
    if status != 200 or "Allow: /" not in text:
        raise RuntimeError("robots.txt did not confirm Allow: /")
    return text


def sitemap_urls(sitemap_url: str) -> list[dict]:
    text, _headers, _status = open_text(sitemap_url)
    root = ET.fromstring(text.encode("utf-8"))
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex"):
        rows: list[dict] = []
        for loc in root.findall(".//sm:sitemap/sm:loc", ns):
            if loc.text:
                rows.extend(sitemap_urls(loc.text))
        return rows
    rows = []
    for item in root.findall(".//sm:url", ns):
        loc = item.find("sm:loc", ns)
        lastmod = item.find("sm:lastmod", ns)
        url = normalize_url(loc.text if loc is not None else "")
        if url:
            rows.append({"url": url, "lastmod": lastmod.text if lastmod is not None else None, "source": "sitemap"})
    return rows


def top_nav_urls() -> list[dict]:
    text, _headers, _status = open_text("https://developers.openai.com/")
    parser = LinkParser()
    parser.feed(text)
    rows = []
    for href in parser.links:
        url = normalize_url(href)
        if url:
            rows.append({"url": url, "lastmod": None, "source": "top_nav"})
    return rows


def sort_key(row: dict) -> tuple[int, str]:
    priority = row.get("priority", 10000)
    url = row["url"]
    if re.search(r"/(api/reference/.*/methods|resources/.*/methods)/", url):
        priority += 2000
    return int(priority), url


def discover(limit: int | None = None) -> list[dict]:
    robots = verify_robots()
    sitemap_match = re.search(r"(?im)^Sitemap:\s*(\S+)", robots)
    sitemap = sitemap_match.group(1) if sitemap_match else DEFAULT_SITEMAP
    if sitemap.startswith("/"):
        sitemap = "https://developers.openai.com" + sitemap

    candidates: dict[str, dict] = {}
    for idx, url in enumerate(PRIORITY_URLS):
        normalized = normalize_url(url)
        if normalized:
            candidates[normalized] = {"url": normalized, "lastmod": None, "source": "priority", "priority": idx}

    for row in top_nav_urls():
        row["priority"] = min(candidates.get(row["url"], {}).get("priority", 1000), 100 + len(candidates))
        candidates.setdefault(row["url"], row)

    for idx, row in enumerate(sitemap_urls(sitemap)):
        row["priority"] = min(candidates.get(row["url"], {}).get("priority", 10000), 1000 + idx)
        candidates.setdefault(row["url"], row)

    rows = sorted(candidates.values(), key=sort_key)
    now = utc_now()
    for row in rows:
        row["discovered_at"] = now
    return rows[:limit] if limit else rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    root = data_dir(args.data_dir)
    output = Path(args.output) if args.output else root / "urls.jsonl"
    rows = discover(args.limit)
    write_jsonl(output, rows)
    print(f"discovered {len(rows)} URLs -> {output}")


if __name__ == "__main__":
    main()
