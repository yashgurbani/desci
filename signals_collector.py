#!/usr/bin/env python
"""
Local signals collector for the DeSci Map dashboard.

It fetches targeted signals from:
- Google News RSS
- curated RSS/blog feeds
- Reddit RSS (subreddits + keyword search)
- X/Twitter best-effort public RSS adapters (Nitter / RSSHub)
- GitHub Atom feeds for mapped technical projects

The output is written to `signals_feed.json` and can be loaded by the
Signals tab and Home widget through `D.signalCollectorUrl`.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import email.utils
import html
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "signals_config.json"
DATA_PATH = ROOT / "data.json"
DEFAULT_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 DeSciMapSignalsCollector/1.0"
)
SOCIAL_QUERY_BLOCKLIST = {
    "doi",
    "crossref",
    "crossref / doi",
    "orcid",
    "review commons",
    "peer community in",
    "peer community in pci",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def shorten(text: str, limit: int = 220) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def normalize_http_url(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if re.match(r"^https?://", s, re.I):
        return s
    if s.lower().startswith("www."):
        return "https://" + s
    return ""


def normalize_twitter_handle(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s.startswith("@"):
        s = s[1:]
    if re.match(r"^https?://", s, re.I):
        try:
            parsed = urllib.parse.urlparse(s)
            s = parsed.path.strip("/").split("/")[0]
        except Exception:
            return ""
    return s if re.fullmatch(r"[A-Za-z0-9_]{1,15}", s or "") else ""


def github_repo(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s):
        return s
    url = normalize_http_url(s)
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.lower().replace("www.", "") != "github.com":
            return ""
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) < 2:
            return ""
        return f"{parts[0]}/{parts[1]}"
    except Exception:
        return ""


def url_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def entity_aliases(name: str) -> list[str]:
    raw = clean_text(name)
    if not raw:
        return []
    out = [raw]
    out.extend([part.strip() for part in raw.split("/") if part.strip()])
    stripped = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    if stripped:
        out.append(stripped)
    deduped = []
    seen = set()
    for item in out:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def to_iso_date(raw: Any) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for candidate in (s.replace("Z", "+00:00"), s):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return ""


def iso_to_ts(raw: str) -> float:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def fetch_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def find_text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if child is node:
            continue
        if local_name(child.tag) in names:
            text = clean_text(child.text)
            if text:
                return text
    return ""


def find_link(node: ET.Element) -> str:
    for child in node.iter():
        if child is node:
            continue
        if local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href.startswith("http"):
            return href
        text = clean_text(child.text)
        if text.startswith("http"):
            return text
    ident = find_text(node, {"id"})
    return ident if ident.startswith("http") else ""


def parse_feed(xml_text: str, source: str, topic: str, section: str, limit: int) -> list[dict[str, Any]]:
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []
    items = []
    for elem in root.iter():
        if local_name(elem.tag) not in {"item", "entry"}:
            continue
        title = find_text(elem, {"title"})
        link = find_link(elem)
        if not title or not link.startswith("http"):
            continue
        pub_date = to_iso_date(find_text(elem, {"pubDate", "updated", "published"}))
        summary = shorten(find_text(elem, {"description", "summary", "content", "encoded"}), 220)
        items.append(
            {
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "source": source,
                "topic": topic,
                "summary": summary,
                "section": section,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_feed(url: str, source: str, topic: str, section: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    try:
        return parse_feed(fetch_text(url, timeout), source, topic, section, limit)
    except Exception:
        return []


def google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )


def fetch_google_news(query: str, timeout: int, limit: int, section: str = "news") -> list[dict[str, Any]]:
    return fetch_feed(google_news_url(query), "Google News", query, section, timeout, limit)


def reddit_subreddit_url(subreddit: str) -> str:
    sub = subreddit.replace("r/", "").strip()
    return f"https://www.reddit.com/r/{sub}/new.rss"


def reddit_search_url(query: str) -> str:
    return "https://www.reddit.com/search.rss?q=" + urllib.parse.quote(query) + "&sort=new"


def fetch_reddit_subreddit(subreddit: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    sub = subreddit.replace("r/", "").strip()
    return fetch_feed(reddit_subreddit_url(sub), "reddit", f"r/{sub}", "reddit", timeout, limit)


def fetch_reddit_search(query: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    return fetch_feed(reddit_search_url(query), "reddit", query, "reddit", timeout, limit)


def fetch_nitter_handle(instance: str, handle: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    url = instance.rstrip("/") + "/" + urllib.parse.quote(handle) + "/rss"
    return fetch_feed(url, "x", f"@{handle}", "x", timeout, limit)


def fetch_nitter_search(instance: str, query: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    url = instance.rstrip("/") + "/search/rss?f=tweets&q=" + urllib.parse.quote(query)
    return fetch_feed(url, "x", query, "x", timeout, limit)


def fetch_rsshub_handle(instance: str, handle: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    url = instance.rstrip("/") + "/twitter/user/" + urllib.parse.quote(handle)
    return fetch_feed(url, "x", f"@{handle}", "x", timeout, limit)


def fetch_rsshub_keyword(instance: str, query: str, timeout: int, limit: int) -> list[dict[str, Any]]:
    url = instance.rstrip("/") + "/twitter/keyword/" + urllib.parse.quote(query, safe="")
    return fetch_feed(url, "x", query, "x", timeout, limit)


def github_atom_urls(repo: str) -> list[str]:
    return [
        f"https://github.com/{repo}/commits.atom",
        f"https://github.com/{repo}/releases.atom",
    ]


def site_feed_candidates(site_url: str) -> list[str]:
    url = normalize_http_url(site_url)
    if not url:
        return []
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return []
    stems = [f"{parsed.scheme}://{parsed.netloc}"]
    path = parsed.path.rstrip("/")
    if path and "." not in path.rsplit("/", 1)[-1]:
        stems.insert(0, f"{parsed.scheme}://{parsed.netloc}{path}")
    suffixes = [
        "/feed",
        "/rss",
        "/rss.xml",
        "/feed.xml",
        "/atom.xml",
        "/blog/feed",
        "/blog/rss.xml",
        "/news/feed",
        "/news/rss.xml",
        "/updates/feed",
    ]
    out = []
    seen = set()
    for stem in stems:
        for suffix in suffixes:
            cand = stem.rstrip("/") + suffix
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


def uniq_by_link(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        link = str(item.get("link", "")).strip()
        if not link or link in seen:
            continue
        seen.add(link)
        out.append(item)
    return out


def score_item(item: dict[str, Any], intents: list[str]) -> float:
    text = " ".join(
        [
            clean_text(item.get("title")),
            clean_text(item.get("topic")),
            clean_text(item.get("summary")),
            clean_text(item.get("source")),
        ]
    ).lower()
    score = 0.0
    for term in intents:
        low = term.lower().strip()
        if low and low in text:
            score += 2.4 if " " in low else 0.8
    source = str(item.get("source", "")).lower()
    link = str(item.get("link", "")).lower()
    if "google news" in source or "news" in source:
        score += 1.2
    if "blog" in source or "feed" in source:
        score += 1.1
    if "reddit" in source:
        score += 0.8
    if "x" in source or "nitter" in link or "twitter" in link:
        score += 0.8
    ts = iso_to_ts(str(item.get("pubDate", "")))
    if ts:
        age_days = max(0.0, (time.time() - ts) / 86400.0)
        score += max(0.0, 4.0 - age_days / 10.0)
    return score


def relevance_hits(item: dict[str, Any], intents: list[str], include_topic: bool = True) -> int:
    parts = [clean_text(item.get("title")), clean_text(item.get("summary"))]
    if include_topic:
        parts.append(clean_text(item.get("topic")))
    text = " ".join(parts).lower()
    hits = 0
    for term in intents:
        low = term.lower().strip()
        if low and low in text:
            hits += 1
    return hits


def rank_items(items: list[dict[str, Any]], intents: list[str], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        uniq_by_link(items),
        key=lambda item: (score_item(item, intents), iso_to_ts(str(item.get("pubDate", "")))),
        reverse=True,
    )
    return ranked[:limit]


def passes_manual_filters(item: dict[str, Any], config: dict[str, Any]) -> bool:
    blocked_domains = {clean_text(x).lower() for x in config.get("blocked_domains", []) if clean_text(x)}
    blocked_terms = {clean_text(x).lower() for x in config.get("blocked_terms", []) if clean_text(x)}
    link = str(item.get("link", "")).strip()
    domain = url_domain(link)
    if domain and any(domain == blocked or domain.endswith("." + blocked) for blocked in blocked_domains):
        return False
    text = " ".join(
        [
            clean_text(item.get("title")),
            clean_text(item.get("summary")),
            clean_text(item.get("topic")),
            clean_text(item.get("source")),
        ]
    ).lower()
    if any(term in text for term in blocked_terms):
        return False
    return True


def apply_manual_filters(items: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in items if passes_manual_filters(item, config)]


def recent_enough(item: dict[str, Any], max_age_days: float | None) -> bool:
    if max_age_days is None:
        return True
    ts = iso_to_ts(str(item.get("pubDate", "")))
    if not ts:
        return True
    age_days = max(0.0, (time.time() - ts) / 86400.0)
    return age_days <= max_age_days


def filtered_rank_items(
    items: list[dict[str, Any]],
    intents: list[str],
    limit: int,
    *,
    min_hits: int = 1,
    include_topic_hits: bool = True,
    max_age_days: float | None = None,
) -> list[dict[str, Any]]:
    filtered = [
        item
        for item in uniq_by_link(items)
        if relevance_hits(item, intents, include_topic=include_topic_hits) >= min_hits
        and recent_enough(item, max_age_days)
    ]
    ranked = sorted(
        filtered,
        key=lambda item: (score_item(item, intents), iso_to_ts(str(item.get("pubDate", "")))),
        reverse=True,
    )
    return ranked[:limit]


def blend_sections(section_map: dict[str, list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    order = ["news", "x", "blogs", "github", "reddit"]
    caps = {"news": 18, "x": 10, "blogs": 10, "github": 6, "reddit": 6}
    pools = {key: list(section_map.get(key, []))[: caps.get(key, limit)] for key in order}
    seen = set()
    out: list[dict[str, Any]] = []
    while len(out) < limit and any(pools.get(key) for key in order):
        advanced = False
        for key in order:
            pool = pools.get(key) or []
            while pool:
                item = pool.pop(0)
                link = str(item.get("link", "")).strip()
                if link and link not in seen:
                    seen.add(link)
                    out.append(item)
                    advanced = True
                    break
            if len(out) >= limit:
                break
        if not advanced:
            break
    return out[:limit]


def top_nodes(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    nodes = list(data.get("nodes", []))
    nodes.sort(key=lambda n: (float(n.get("overlapScore", 0)) * 1.06) + (float(n.get("credScore", 0)) * 1.14), reverse=True)
    return nodes[:limit]


def top_people(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    by_id = {n.get("id"): n for n in data.get("nodes", [])}
    scored = []
    for person in data.get("people", []):
        score = 0.0
        for org_id in person.get("orgs", []) or []:
            node = by_id.get(org_id) or {}
            score += float(node.get("overlapScore", 0)) + float(node.get("credScore", 0)) * 1.15
        if normalize_twitter_handle(person.get("twitter")):
            score += 18.0
        scored.append((score, person))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [person for _, person in scored[:limit]]


def collect_registry(config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    registry = {
        "keywords": list(config.get("general_keywords", [])),
        "news_keywords": list(config.get("news_keywords", config.get("general_keywords", []))),
        "x_keywords": list(config.get("x_keywords", [])),
        "reddit_keywords": list(config.get("reddit_keywords", [])),
        "x_handles": list(config.get("x_handles", [])),
        "reddit_subreddits": list(config.get("reddit_subreddits", [])),
        "rss_feeds": list(config.get("rss_feeds", [])),
        "entity_queries": list(config.get("manual_entity_queries", [])),
        "site_urls": [],
        "site_domains": [],
        "github_repos": [],
        "key_nodes": [],
        "key_people": [],
    }
    include_nodes = bool(config.get("include_map_nodes", config.get("include_map_entities", True)))
    include_people = bool(config.get("include_map_people", False if config.get("strict_curated_mode", True) else config.get("include_map_entities", True)))
    if not include_nodes and not include_people:
        return registry

    top_n = top_nodes(data, int(config.get("map_top_nodes", 12))) if include_nodes else []
    top_p = top_people(data, int(config.get("map_top_people", 8))) if include_people else []
    site_urls = []
    domains = []
    handles = []
    repos = []
    entity_queries = registry["entity_queries"]

    for node in top_n:
        registry["key_nodes"].append(node.get("name", ""))
        for alias in entity_aliases(node.get("name", "")):
            entity_queries.append(alias)
        for raw in [node.get("web"), node.get("wp")]:
            url = normalize_http_url(raw)
            if url:
                site_urls.append(url)
                domain = url_domain(url)
                if domain:
                    domains.append(domain)
        handle = normalize_twitter_handle(node.get("twitter"))
        if handle:
            handles.append(handle)
        repo = github_repo(node.get("git"))
        if repo:
            repos.append(repo)
        provenance = node.get("provenance", {}) or {}
        for src in provenance.get("sources", []) or []:
            url = normalize_http_url(src.get("url"))
            if not url:
                continue
            host = url_domain(url)
            if host and host not in {"twitter.com", "x.com", "github.com", "reddit.com"}:
                site_urls.append(url)
                domains.append(host)

    for person in top_p:
        registry["key_people"].append(person.get("name", ""))
        for alias in entity_aliases(person.get("name", "")):
            entity_queries.append(alias)
        handle = normalize_twitter_handle(person.get("twitter"))
        if handle:
            handles.append(handle)

    registry["x_handles"] = sorted({h for h in handles + registry["x_handles"] if h})
    registry["entity_queries"] = sorted({q for q in entity_queries if q})
    registry["site_urls"] = sorted({u for u in site_urls if u})
    registry["site_domains"] = sorted({d for d in domains if d})
    registry["github_repos"] = sorted({r for r in repos if r})
    return registry


def social_entity_queries(registry: dict[str, Any]) -> list[str]:
    safe = []
    seen = set()
    for query in registry.get("entity_queries", []):
        q = clean_text(query)
        low = q.lower()
        if not q or low in SOCIAL_QUERY_BLOCKLIST:
            continue
        if "/" in q:
            continue
        if len(low) < 6:
            continue
        if q.count(" ") == 0 and low not in {
            "researchhub",
            "openreview",
            "openalex",
            "orvium",
            "prereview",
            "labdao",
            "vitadao",
            "molecule",
            "nobleblocks",
            "episteme",
            "talentdao",
        }:
            continue
        if low not in seen:
            seen.add(low)
            safe.append(q)
    return safe


def fetch_best_effort_x_handle(handle: str, config: dict[str, Any], timeout: int, limit: int) -> list[dict[str, Any]]:
    for inst in config.get("nitter_instances", []):
        rows = fetch_nitter_handle(inst, handle, timeout, limit)
        if rows:
            return rows
    for inst in config.get("rsshub_instances", []):
        rows = fetch_rsshub_handle(inst, handle, timeout, limit)
        if rows:
            return rows
    return fetch_google_news(f'site:x.com "@{handle}"', timeout, limit, "x")


def fetch_best_effort_x_keyword(query: str, config: dict[str, Any], timeout: int, limit: int) -> list[dict[str, Any]]:
    for inst in config.get("nitter_instances", []):
        rows = fetch_nitter_search(inst, query, timeout, limit)
        if rows:
            return rows
    for inst in config.get("rsshub_instances", []):
        rows = fetch_rsshub_keyword(inst, query, timeout, limit)
        if rows:
            return rows
    return fetch_google_news(f'site:x.com "{query}"', timeout, limit, "x")


def flatten(results: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, list):
            out.extend(result)
    return out


def run_parallel(jobs: list[tuple], max_workers: int = 12) -> list[Any]:
    if not jobs:
        return []
    out: list[Any] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(jobs))) as pool:
        futures = [pool.submit(fn, *args) for fn, args in jobs]
        for future in concurrent.futures.as_completed(futures):
            try:
                out.append(future.result())
            except Exception:
                out.append([])
    return out


def collect(config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    timeout = int(config.get("timeout_seconds", DEFAULT_TIMEOUT))
    per_feed = int(config.get("max_items_per_feed", 6))
    registry = collect_registry(config, data)
    safe_social_entities = social_entity_queries(registry)
    people_lows = {clean_text(name).lower() for name in registry.get("key_people", []) if clean_text(name)}
    news_entity_queries = [q for q in safe_social_entities if clean_text(q).lower() not in people_lows]
    intents = sorted(
        {
            *(clean_text(x).lower() for x in registry.get("keywords", [])),
            *(clean_text(x).lower() for x in registry.get("entity_queries", [])),
            *(clean_text(x).lower() for x in registry.get("key_nodes", [])),
            *(clean_text(x).lower() for x in registry.get("key_people", [])),
        }
    )

    rss_jobs = []
    for spec in config.get("rss_feeds", []):
        rss_jobs.append(
            (
                fetch_feed,
                (
                    spec.get("url", ""),
                    spec.get("source", "rss"),
                    spec.get("topic", ""),
                    spec.get("section", "blogs"),
                    timeout,
                    per_feed,
                ),
            )
        )
    for site in registry.get("site_urls", [])[:8]:
        for candidate in site_feed_candidates(site)[:6]:
            rss_jobs.append((fetch_feed, (candidate, url_domain(site) or "blog", site, "blogs", timeout, 3)))

    news_queries = list(registry.get("news_keywords", config.get("general_keywords", [])))[:10]
    news_queries.extend([f'"{q}"' for q in news_entity_queries[:10]])
    news_queries.extend([f"site:{d}" for d in registry.get("site_domains", [])[:6]])
    news_jobs = [(fetch_google_news, (query, timeout, per_feed, "news")) for query in news_queries]

    x_jobs = []
    for handle in registry.get("x_handles", [])[:14]:
        x_jobs.append((fetch_best_effort_x_handle, (handle, config, timeout, per_feed)))
    if config.get("enable_x_keyword_search", False):
        for query in list(config.get("x_keywords", []))[:10] + safe_social_entities[:4]:
            x_jobs.append((fetch_best_effort_x_keyword, (query, config, timeout, per_feed)))

    reddit_jobs = []
    for sub in registry.get("reddit_subreddits", [])[:10]:
        reddit_jobs.append((fetch_reddit_subreddit, (sub, timeout, per_feed)))
    if config.get("enable_reddit_search", False):
        for query in list(config.get("reddit_keywords", []))[:10] + safe_social_entities[:6]:
            reddit_jobs.append((fetch_reddit_search, (query, timeout, per_feed)))

    github_jobs = []
    for repo in registry.get("github_repos", [])[:10]:
        for atom_url in github_atom_urls(repo):
            github_jobs.append((fetch_feed, (atom_url, "github", repo, "github", timeout, 3)))

    rss_rows = flatten(run_parallel(rss_jobs))
    news = flatten(run_parallel(news_jobs))
    x_rows = flatten(run_parallel(x_jobs))
    reddit = flatten(run_parallel(reddit_jobs))
    github = flatten(run_parallel(github_jobs))

    blogs = apply_manual_filters([item for item in rss_rows if str(item.get("section", "")).lower() == "blogs"], config)
    rss_news = apply_manual_filters([item for item in rss_rows if str(item.get("section", "")).lower() == "news"], config)
    news = apply_manual_filters(rss_news + news, config)
    x_rows = apply_manual_filters(x_rows, config)
    reddit = apply_manual_filters(reddit, config)
    github = apply_manual_filters(github, config)

    sections = {
        "news": filtered_rank_items(news, intents, 40, min_hits=1, include_topic_hits=True, max_age_days=90),
        "blogs": filtered_rank_items(blogs, intents, 40, min_hits=1, include_topic_hits=True, max_age_days=180),
        "x": filtered_rank_items(x_rows, intents, 40, min_hits=1, include_topic_hits=False, max_age_days=45),
        "reddit": filtered_rank_items(reddit, intents, 40, min_hits=1, include_topic_hits=False, max_age_days=45),
        "github": filtered_rank_items(github, intents, 30, min_hits=0, include_topic_hits=True, max_age_days=180),
    }
    sections["all"] = blend_sections(sections, 80)

    return {
        "generatedAt": now_iso(),
        "configPath": str(CONFIG_PATH.name),
        "registry": registry,
        "sections": sections,
        "items": sections["all"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect targeted DeSci dashboard signals.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to signals_config.json")
    parser.add_argument("--output", default="", help="Override output JSON path")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path, {})
    if not config:
        print(f"Could not load config: {config_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output).resolve() if args.output else (ROOT / str(config.get("output_path", "signals_feed.json"))).resolve()
    data = load_json(DATA_PATH, {"nodes": [], "edges": [], "people": []})
    payload = collect(config, data)
    save_json(output_path, payload)
    print(f"Wrote {output_path}")
    print(
        "Counts:",
        {
            key: len(payload.get("sections", {}).get(key, []))
            for key in ("all", "news", "blogs", "x", "reddit", "github")
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
