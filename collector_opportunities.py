from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "source_registry.json"
OUTPUT_PATH = ROOT / "opportunity_intel.json"
TIMEOUT = 20
USER_AGENT = "DeSciMapOpportunityCollector/1.0 (+https://github.com/yashgurbani/desci)"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[bool, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, {"error": str(exc), "url": url, "payload": payload}


def get_json(url: str, headers: dict[str, str] | None = None) -> tuple[bool, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, {"error": str(exc), "url": url}


def grants_gov_search(keyword: str) -> tuple[bool, Any]:
    payload = {
        "rows": 10,
        "keyword": keyword,
        "oppNum": "",
        "eligibilities": "",
        "agencies": "",
        "oppStatuses": "forecasted|posted",
        "aln": "",
        "fundingCategories": "",
    }
    return post_json("https://api.grants.gov/v1/api/search2", payload)


def gdelt_articles(query: str) -> tuple[bool, Any]:
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + urllib.parse.quote(query)
        + "&mode=ArtList&maxrecords=10&format=json&sort=DateDesc"
    )
    return get_json(url)


def nih_reporter_search(query: str) -> tuple[bool, Any]:
    payload = {
        "criteria": {
            "advanced_text_search": {
                "operator": "and",
                "search_text": query,
            },
            "include_active_projects": True,
        },
        "offset": 0,
        "limit": 10,
        "sort_field": "project_start_date",
        "sort_order": "desc",
    }
    return post_json("https://api.reporter.nih.gov/v2/projects/search", payload)


def optional_cordis_search(query: str) -> tuple[bool, Any]:
    base = os.environ.get("CORDIS_DET_URL", "").strip()
    api_key = os.environ.get("CORDIS_API_KEY", "").strip()
    if not (base and api_key):
        return False, {"error": "missing CORDIS credentials", "query": query}
    url = base.rstrip("/") + "?q=" + urllib.parse.quote(query)
    return get_json(url, headers={"X-API-KEY": api_key, "Accept": "application/json"})


def simplify_grants_gov(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "number": row.get("number"),
        "title": clean_text(row.get("title")),
        "agency_code": row.get("agencyCode"),
        "agency_name": row.get("agencyName"),
        "open_date": row.get("openDate"),
        "close_date": row.get("closeDate"),
        "status": row.get("oppStatus"),
        "doc_type": row.get("docType"),
        "aln": row.get("alnist", []),
        "keyword": keyword,
        "source": "Grants.gov",
    }


def simplify_nih(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    org = row.get("organization") or {}
    return {
        "appl_id": row.get("appl_id"),
        "title": clean_text(row.get("project_title")),
        "agency": row.get("agency_ic_fundings", []),
        "org_name": org.get("org_name"),
        "org_city": org.get("org_city"),
        "org_country": org.get("org_country"),
        "project_num": row.get("project_num"),
        "opportunity_number": row.get("opportunity_number"),
        "award_amount": row.get("award_amount"),
        "project_start_date": row.get("project_start_date"),
        "project_end_date": row.get("project_end_date"),
        "keyword": keyword,
        "source": "NIH RePORTER",
    }


def simplify_gdelt(row: dict[str, Any], keyword: str) -> dict[str, Any]:
    return {
        "title": clean_text(row.get("title")),
        "url": row.get("url"),
        "domain": row.get("domain"),
        "seendate": row.get("seendate"),
        "language": row.get("language"),
        "sourcecountry": row.get("sourcecountry"),
        "keyword": keyword,
        "source": "GDELT",
    }


def collect_keyword(keyword: str) -> dict[str, Any]:
    ok_grants, grants = grants_gov_search(keyword)
    ok_nih, nih = nih_reporter_search(keyword)
    ok_gdelt, gdelt = gdelt_articles(f'"{keyword}"')
    ok_cordis, cordis = optional_cordis_search(keyword)
    return {
        "keyword": keyword,
        "grants_gov": [simplify_grants_gov(row, keyword) for row in ((grants.get("data") or {}).get("oppHits", []) or [])] if ok_grants else [],
        "nih_projects": [simplify_nih(row, keyword) for row in (nih.get("results", []) or [])] if ok_nih else [],
        "gdelt_news": [simplify_gdelt(row, keyword) for row in (gdelt.get("articles", []) or [])] if ok_gdelt else [],
        "cordis": cordis if ok_cordis else [],
        "provider_status": {
            "grants_gov": ok_grants,
            "nih_reporter": ok_nih,
            "gdelt": ok_gdelt,
            "cordis": ok_cordis,
        },
        "errors": {
            "grants_gov": None if ok_grants else grants,
            "nih_reporter": None if ok_nih else nih,
            "gdelt": None if ok_gdelt else gdelt,
            "cordis": None if ok_cordis else cordis,
        },
    }


def analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grants = []
    nih_projects = []
    news = []
    agency_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    for row in rows:
        grants.extend(row.get("grants_gov", []))
        nih_projects.extend(row.get("nih_projects", []))
        news.extend(row.get("gdelt_news", []))
        keyword_counter[row.get("keyword", "")] += len(row.get("grants_gov", [])) + len(row.get("nih_projects", [])) + len(row.get("gdelt_news", []))
        for item in row.get("grants_gov", []):
            if item.get("agency_name"):
                agency_counter[str(item["agency_name"])] += 1
    return {
        "top_agencies": [{"agency": agency, "count": count} for agency, count in agency_counter.most_common(20)],
        "top_keywords": [{"keyword": keyword, "count": count} for keyword, count in keyword_counter.most_common(20) if keyword],
        "grants_gov_hits": len(grants),
        "nih_project_hits": len(nih_projects),
        "gdelt_hits": len(news),
    }


def main() -> int:
    registry = load_json(REGISTRY_PATH, {})
    if not registry:
        print(f"Missing or unreadable registry: {REGISTRY_PATH}")
        return 1
    keywords = list(dict.fromkeys((registry.get("tracked_topics", []) or [])[:10] + ["scientific publishing", "open science", "decentralized science"]))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(keywords))) as pool:
        futures = {pool.submit(collect_keyword, keyword): keyword for keyword in keywords}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as exc:
                keyword = futures[future]
                rows.append({"keyword": keyword, "grants_gov": [], "nih_projects": [], "gdelt_news": [], "cordis": [], "provider_status": {}, "errors": {"collector": str(exc)}})
    rows.sort(key=lambda row: keywords.index(row.get("keyword")))
    payload = {
        "generatedAt": now_iso(),
        "registryPath": REGISTRY_PATH.name,
        "keywords": keywords,
        "queries": rows,
        "analytics": analytics(rows),
        "provider_status": {
            "grants_gov": any(row.get("provider_status", {}).get("grants_gov") for row in rows),
            "nih_reporter": any(row.get("provider_status", {}).get("nih_reporter") for row in rows),
            "gdelt": any(row.get("provider_status", {}).get("gdelt") for row in rows),
            "cordis_optional": bool(os.environ.get("CORDIS_DET_URL") and os.environ.get("CORDIS_API_KEY")),
        },
    }
    save_json(OUTPUT_PATH, payload)
    print(f"Wrote {OUTPUT_PATH}")
    print("Summary:", payload["analytics"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
