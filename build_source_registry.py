from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data.json"
SIGNALS_CONFIG_PATH = ROOT / "signals_config.json"
OUTPUT_PATH = ROOT / "source_registry.json"

CORE_TOPICS = [
    "desci",
    "decentralized science",
    "decentralized peer review",
    "open science",
    "open science infrastructure",
    "science publishing",
    "scientific publishing",
    "metascience",
    "research integrity",
    "reproducibility",
    "research credibility",
    "ai for science",
    "ai and science",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_http_url(raw: Any) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    if re.match(r"^https?://", s, re.I):
        return s
    if s.lower().startswith("www."):
        return "https://" + s
    return ""


def normalize_twitter_handle(raw: Any) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    if s.startswith("@"):
        s = s[1:]
    if re.match(r"^https?://", s, re.I):
        try:
            parsed = urlparse(s)
            s = parsed.path.strip("/").split("/")[0]
        except Exception:
            return ""
    return s if re.fullmatch(r"[A-Za-z0-9_]{1,15}", s or "") else ""


def github_repo(raw: Any) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s):
        return s
    url = normalize_http_url(s)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
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
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def entity_aliases(name: str) -> list[str]:
    raw = clean_text(name)
    if not raw:
        return []
    out = [raw]
    out.extend(part.strip() for part in raw.split("/") if part.strip())
    stripped = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    if stripped:
        out.append(stripped)
    return list(dict.fromkeys(out))


def infer_rss_candidates(urls: list[str]) -> list[str]:
    out: list[str] = []
    suffixes = ["/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/blog/feed", "/news/feed"]
    for raw in urls:
        url = normalize_http_url(raw)
        if not url:
            continue
        try:
            parsed = urlparse(url)
            stem = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            roots = [f"{parsed.scheme}://{parsed.netloc}"]
            if stem and stem not in roots and not re.search(r"\.[a-z0-9]{2,6}$", stem, re.I):
                roots.insert(0, stem)
            for base in roots:
                for suffix in suffixes:
                    candidate = re.sub(r"(?<!:)//+", "/", (base.rstrip("/") + suffix))
                    if candidate not in out:
                        out.append(candidate)
        except Exception:
            continue
    return out[:12]


def weight_for_node(node: dict[str, Any]) -> float:
    return float(node.get("overlapScore", 0)) * 1.06 + float(node.get("credScore", 0)) * 1.14 + float(node.get("decen", 0)) * 0.25


def weight_for_person(person: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> float:
    score = 0.0
    for org_id in person.get("orgs", []) or []:
        node = node_by_id.get(org_id) or {}
        score += weight_for_node(node)
    if normalize_twitter_handle(person.get("twitter")):
        score += 14.0
    if clean_text(person.get("orcid")):
        score += 10.0
    if clean_text(person.get("github")):
        score += 8.0
    return score


def top_opportunity_topics(nodes: list[dict[str, Any]]) -> list[str]:
    weights: dict[str, float] = {}
    for node in nodes:
        node_weight = max(1.0, weight_for_node(node))
        for raw in [node.get("type"), node.get("stack"), *(node.get("tags", []) or []), *(node.get("overlapTags", []) or [])]:
            term = clean_text(raw).lower().replace("_", " ").replace("-", " ")
            if not term or term in {"infrastructure", "application", "governance"}:
                continue
            weights[term] = weights.get(term, 0.0) + node_weight
    return [term for term, _ in sorted(weights.items(), key=lambda item: item[1], reverse=True)[:20]]


def build_registry() -> dict[str, Any]:
    data = load_json(DATA_PATH, {"nodes": [], "edges": [], "people": []})
    config = load_json(SIGNALS_CONFIG_PATH, {})
    nodes = list(data.get("nodes", []))
    people = list(data.get("people", []))
    node_by_id = {node.get("id"): node for node in nodes}
    people_by_org: dict[str, list[dict[str, Any]]] = {}
    for person in people:
        for org_id in person.get("orgs", []) or []:
            people_by_org.setdefault(org_id, []).append(person)

    organizations = []
    for node in sorted(nodes, key=weight_for_node, reverse=True):
        urls = [normalize_http_url(node.get("web")), normalize_http_url(node.get("wp")), normalize_http_url(node.get("paper"))]
        prov = node.get("provenance", {}) or {}
        for src in prov.get("sources", []) or []:
            urls.append(normalize_http_url(src.get("url")))
        urls = [url for url in urls if url]
        domains = list(dict.fromkeys(url_domain(url) for url in urls if url_domain(url)))
        handles = [normalize_twitter_handle(node.get("twitter"))]
        repos = [github_repo(node.get("git"))]
        organizations.append(
            {
                "id": node.get("id"),
                "kind": "organization",
                "name": node.get("name"),
                "aliases": entity_aliases(node.get("name", "")),
                "stack": node.get("stack", ""),
                "type": node.get("type", ""),
                "tags": list(dict.fromkeys((node.get("tags", []) or []) + (node.get("overlapTags", []) or []))),
                "watch_priority": round(weight_for_node(node), 2),
                "scores": {
                    "overlap": float(node.get("overlapScore", 0)),
                    "credibility": float(node.get("credScore", 0)),
                    "decentralization": float(node.get("decen", 0)),
                    "open_science_fit": float(node.get("openScienceScore", 0) or (node.get("financials", {}) or {}).get("openScienceCompatibilityScore", 0)),
                },
                "official_urls": list(dict.fromkeys(urls)),
                "domains": domains,
                "rss_candidates": infer_rss_candidates(urls),
                "x_handles": [h for h in dict.fromkeys(handles) if h],
                "github_repos": [r for r in dict.fromkeys(repos) if r],
                "paper_urls": [u for u in [normalize_http_url(node.get("paper")), normalize_http_url(node.get("wp"))] if u],
                "linked_people": [
                    {
                        "id": person.get("id"),
                        "name": person.get("name"),
                        "role": person.get("role", ""),
                        "x_handle": normalize_twitter_handle(person.get("twitter")),
                    }
                    for person in people_by_org.get(node.get("id"), [])
                ],
                "provenance_urls": [normalize_http_url(src.get("url")) for src in prov.get("sources", []) or [] if normalize_http_url(src.get("url"))],
            }
        )

    people_rows = []
    for person in sorted(people, key=lambda row: weight_for_person(row, node_by_id), reverse=True):
        handles = [normalize_twitter_handle(person.get("twitter"))]
        urls = [normalize_http_url(person.get("linkedin")), normalize_http_url(person.get("website")), normalize_http_url(person.get("orcid"))]
        repos = [github_repo(person.get("github"))]
        linked_orgs = []
        for org_id in person.get("orgs", []) or []:
            node = node_by_id.get(org_id)
            if not node:
                continue
            linked_orgs.append({"id": org_id, "name": node.get("name"), "stack": node.get("stack", ""), "type": node.get("type", "")})
        people_rows.append(
            {
                "id": person.get("id"),
                "kind": "person",
                "name": person.get("name"),
                "aliases": entity_aliases(person.get("name", "")),
                "role": person.get("role", ""),
                "watch_priority": round(weight_for_person(person, node_by_id), 2),
                "x_handles": [h for h in dict.fromkeys(handles) if h],
                "github_repos": [r for r in dict.fromkeys(repos) if r],
                "official_urls": [u for u in dict.fromkeys(urls) if u],
                "orcid": normalize_http_url(person.get("orcid")),
                "notes": clean_text(person.get("notes")),
                "open_source_info": clean_text(person.get("openSourceInfo")),
                "org_ids": [org.get("id") for org in linked_orgs],
                "organizations": linked_orgs,
            }
        )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataPath": DATA_PATH.name,
        "signalsConfigPath": SIGNALS_CONFIG_PATH.name,
        "tracked_topics": list(dict.fromkeys(CORE_TOPICS + top_opportunity_topics(nodes))),
        "watchlists": {
            "x_handles": list(dict.fromkeys(config.get("x_handles", []))),
            "rss_feeds": list(config.get("rss_feeds", [])),
            "manual_entity_queries": list(dict.fromkeys(config.get("manual_entity_queries", []))),
            "blocked_domains": list(dict.fromkeys(config.get("blocked_domains", []))),
            "blocked_terms": list(dict.fromkeys(config.get("blocked_terms", []))),
        },
        "organizations": organizations,
        "people": people_rows,
        "summary": {
            "organization_count": len(organizations),
            "people_count": len(people_rows),
            "high_priority_orgs": len([row for row in organizations if row["watch_priority"] >= 120]),
            "high_priority_people": len([row for row in people_rows if row["watch_priority"] >= 80]),
        },
    }


def main() -> int:
    payload = build_registry()
    save_json(OUTPUT_PATH, payload)
    print(f"Wrote {OUTPUT_PATH}")
    print(
        "Summary:",
        {
            "organizations": payload["summary"]["organization_count"],
            "people": payload["summary"]["people_count"],
            "topics": len(payload["tracked_topics"]),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
