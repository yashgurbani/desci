from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signals_collector import (
    fetch_best_effort_x_handle,
    fetch_feed,
    fetch_google_news,
    filtered_rank_items,
    github_atom_urls,
    load_json,
    normalize_twitter_handle,
    now_iso,
    save_json,
    site_feed_candidates,
)

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "source_registry.json"
SIGNALS_CONFIG_PATH = ROOT / "signals_config.json"
OUTPUT_PATH = ROOT / "entity_intel.json"
TIMEOUT = 10


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def rank_for_entity(name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    intents = {clean_text(name).lower()}
    return filtered_rank_items(rows, intents, 12, min_hits=0, include_topic_hits=True, max_age_days=365)


def collect_org(org: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(org.get("name"))
    blog_rows: list[dict[str, Any]] = []
    for url in (org.get("rss_candidates", []) or [])[:6]:
        rows = fetch_feed(url, name + " blog", name, "blogs", TIMEOUT, 3)
        if rows:
            blog_rows.extend(rows)
            break
    github_rows: list[dict[str, Any]] = []
    for repo in (org.get("github_repos", []) or [])[:2]:
        for atom in github_atom_urls(repo):
            github_rows.extend(fetch_feed(atom, "github", name, "github", TIMEOUT, 3))
    x_rows: list[dict[str, Any]] = []
    for handle in (org.get("x_handles", []) or [])[:1]:
        x_rows.extend(fetch_best_effort_x_handle(handle, config, TIMEOUT, 3))
    news_rows = fetch_google_news(f'"{name}"', TIMEOUT, 4, "news")
    combined = rank_for_entity(name, [*blog_rows, *github_rows, *x_rows, *news_rows])
    return {
        "id": org.get("id"),
        "kind": "organization",
        "name": name,
        "signals": combined,
        "counts": {
            "blog": len(blog_rows),
            "github": len(github_rows),
            "x": len(x_rows),
            "news": len(news_rows),
            "total_ranked": len(combined),
        },
    }


def collect_person(person: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(person.get("name"))
    x_rows: list[dict[str, Any]] = []
    for handle in (person.get("x_handles", []) or [])[:1]:
        x_rows.extend(fetch_best_effort_x_handle(handle, config, TIMEOUT, 3))
    news_rows = fetch_google_news(f'"{name}"', TIMEOUT, 4, "news")
    combined = rank_for_entity(name, [*x_rows, *news_rows])
    return {
        "id": person.get("id"),
        "kind": "person",
        "name": name,
        "signals": combined,
        "counts": {
            "x": len(x_rows),
            "news": len(news_rows),
            "total_ranked": len(combined),
        },
    }


def collect_parallel(kind: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    fn = collect_person if kind == "person" else collect_org
    out: list[dict[str, Any]] = []
    order = {row.get("id"): idx for idx, row in enumerate(rows)}
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(rows)))) as pool:
        futures = {pool.submit(fn, row, config): row for row in rows}
        for future in as_completed(futures):
            try:
                out.append(future.result())
            except Exception as exc:
                row = futures[future]
                out.append({"id": row.get("id"), "name": row.get("name"), "kind": kind, "error": str(exc), "signals": [], "counts": {}})
    out.sort(key=lambda row: order.get(row.get("id"), 9999))
    return out


def analytics(people: list[dict[str, Any]], organizations: list[dict[str, Any]]) -> dict[str, Any]:
    source_counter: Counter[str] = Counter()
    entity_counter: list[dict[str, Any]] = []
    for row in [*people, *organizations]:
        entity_counter.append({"id": row.get("id"), "name": row.get("name"), "kind": row.get("kind"), "signal_count": len(row.get("signals", []) or [])})
        for signal in row.get("signals", []) or []:
            source = clean_text(signal.get("source") or "unknown")
            if source:
                source_counter[source] += 1
    entity_counter.sort(key=lambda row: row["signal_count"], reverse=True)
    return {
        "top_sources": [{"source": source, "count": count} for source, count in source_counter.most_common(15)],
        "top_entities": entity_counter[:20],
        "people_with_signals": sum(1 for row in people if row.get("signals")),
        "orgs_with_signals": sum(1 for row in organizations if row.get("signals")),
    }


def main() -> int:
    registry = load_json(REGISTRY_PATH, {})
    config = load_json(SIGNALS_CONFIG_PATH, {})
    if not registry:
        print(f"Missing or unreadable registry: {REGISTRY_PATH}")
        return 1
    organizations = list(registry.get("organizations", []))[:18]
    people = list(registry.get("people", []))[:20]
    org_rows = collect_parallel("organization", organizations, config)
    people_rows = collect_parallel("person", people, config)
    payload = {
        "generatedAt": now_iso(),
        "registryPath": REGISTRY_PATH.name,
        "organizations": org_rows,
        "people": people_rows,
        "analytics": analytics(people_rows, org_rows),
    }
    save_json(OUTPUT_PATH, payload)
    print(f"Wrote {OUTPUT_PATH}")
    print(
        "Summary:",
        {
            "organizations": len(org_rows),
            "people": len(people_rows),
            "orgs_with_signals": payload["analytics"]["orgs_with_signals"],
            "people_with_signals": payload["analytics"]["people_with_signals"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
