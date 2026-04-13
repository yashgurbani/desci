from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "source_registry.json"
OUTPUT_PATH = ROOT / "research_graph.json"
TIMEOUT = 18
MAX_WORKERS = 8
USER_AGENT = "DeSciMapResearchGraph/1.0 (+https://github.com/yashgurbani/desci)"


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
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_json(url: str, headers: dict[str, str] | None = None) -> tuple[bool, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, {"error": str(exc), "url": url}


def openalex_people_query(name: str) -> tuple[bool, Any]:
    url = "https://api.openalex.org/authors?search=" + urllib.parse.quote(name) + "&per-page=3"
    return fetch_json(url)


def openalex_org_query(name: str) -> tuple[bool, Any]:
    url = "https://api.openalex.org/institutions?search=" + urllib.parse.quote(name) + "&per-page=3"
    return fetch_json(url)


def openalex_works_query(query: str) -> tuple[bool, Any]:
    url = (
        "https://api.openalex.org/works?search="
        + urllib.parse.quote(query)
        + "&per-page=5&filter=from_publication_date:2023-01-01"
    )
    return fetch_json(url)


def crossref_works_query(query: str) -> tuple[bool, Any]:
    url = "https://api.crossref.org/works?query.bibliographic=" + urllib.parse.quote(query) + "&rows=5"
    return fetch_json(url)


def optional_orcid_search(name: str) -> tuple[bool, Any]:
    client_id = os.environ.get("ORCID_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ORCID_CLIENT_SECRET", "").strip()
    if not (client_id and client_secret):
        return False, {"error": "missing ORCID credentials", "query": name}
    token_body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public",
        }
    ).encode("utf-8")
    token_req = urllib.request.Request(
        "https://orcid.org/oauth/token",
        data=token_body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(token_req, timeout=TIMEOUT) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("access_token", "")
        if not token:
            return False, {"error": "no ORCID token", "query": name}
        url = "https://pub.orcid.org/v3.0/expanded-search/?q=" + urllib.parse.quote(f'given-and-family-names:"{name}"')
        return fetch_json(url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
    except Exception as exc:
        return False, {"error": str(exc), "query": name}


def simplify_openalex_author(row: dict[str, Any]) -> dict[str, Any]:
    institutions = [
        {"id": inst.get("id"), "display_name": inst.get("display_name")}
        for inst in row.get("last_known_institutions", []) or []
        if isinstance(inst, dict)
    ]
    return {
        "id": row.get("id"),
        "display_name": row.get("display_name"),
        "orcid": row.get("orcid"),
        "works_count": row.get("works_count"),
        "cited_by_count": row.get("cited_by_count"),
        "institutions": institutions,
    }


def simplify_openalex_institution(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "display_name": row.get("display_name"),
        "country_code": row.get("country_code"),
        "works_count": row.get("works_count"),
        "cited_by_count": row.get("cited_by_count"),
        "type": row.get("type"),
    }


def simplify_openalex_work(row: dict[str, Any]) -> dict[str, Any]:
    concepts = [c.get("display_name") for c in row.get("concepts", []) or [] if isinstance(c, dict) and c.get("display_name")]
    authors = []
    for authorship in row.get("authorships", []) or []:
        author = (authorship or {}).get("author", {}) or {}
        if author.get("display_name"):
            authors.append(author.get("display_name"))
    return {
        "id": row.get("id"),
        "title": row.get("display_name"),
        "publication_date": row.get("publication_date"),
        "publication_year": row.get("publication_year"),
        "doi": row.get("doi"),
        "cited_by_count": row.get("cited_by_count"),
        "primary_location": ((row.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "concepts": concepts[:8],
        "authors": authors[:8],
    }


def simplify_crossref_work(row: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in row.get("author", []) or []:
        parts = [clean_text(author.get("given")), clean_text(author.get("family"))]
        name = " ".join(part for part in parts if part)
        if name:
            authors.append(name)
    title = ""
    if row.get("title"):
        title = clean_text((row.get("title") or [""])[0])
    published = row.get("published-print") or row.get("published-online") or row.get("issued") or {}
    date_parts = ((published.get("date-parts") or [[None]])[0])[:3]
    date_text = "-".join(str(x) for x in date_parts if x)
    return {
        "doi": row.get("DOI"),
        "title": title,
        "url": row.get("URL"),
        "publisher": row.get("publisher"),
        "published": date_text,
        "authors": authors[:8],
        "subjects": row.get("subject", [])[:8],
    }


def work_topics(openalex_rows: list[dict[str, Any]], crossref_rows: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for row in openalex_rows:
        for topic in row.get("concepts", []) or []:
            if topic:
                counter[str(topic)] += 1
    for row in crossref_rows:
        for topic in row.get("subjects", []) or []:
            if topic:
                counter[str(topic)] += 1
    return [topic for topic, _ in counter.most_common(12)]


def collect_person(person: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(person.get("name"))
    org_names = [clean_text(org.get("name")) for org in (person.get("organizations", []) or []) if clean_text(org.get("name"))]
    research_focus = " ".join([name, *org_names[:2]]).strip()
    ok_authors, openalex_authors = openalex_people_query(name)
    ok_works, openalex_works = openalex_works_query(name)
    ok_crossref, crossref = crossref_works_query(research_focus or name)
    ok_orcid, orcid = optional_orcid_search(name)
    oa_authors = [simplify_openalex_author(row) for row in (openalex_authors.get("results", []) or [])][:3] if ok_authors else []
    oa_works = [simplify_openalex_work(row) for row in (openalex_works.get("results", []) or [])][:5] if ok_works else []
    cf_works = [simplify_crossref_work(row) for row in ((crossref.get("message") or {}).get("items", []) or [])][:5] if ok_crossref else []
    return {
        "id": person.get("id"),
        "name": name,
        "role": person.get("role", ""),
        "organizations": person.get("organizations", []),
        "openalex_authors": oa_authors,
        "openalex_works": oa_works,
        "crossref_works": cf_works,
        "orcid_search": orcid if ok_orcid else [],
        "topics": work_topics(oa_works, cf_works),
        "provider_status": {
            "openalex_authors": ok_authors,
            "openalex_works": ok_works,
            "crossref": ok_crossref,
            "orcid": ok_orcid,
        },
    }


def collect_org(org: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(org.get("name"))
    ok_inst, institutions = openalex_org_query(name)
    ok_works, openalex_works = openalex_works_query(name)
    ok_crossref, crossref = crossref_works_query(name)
    oa_inst = [simplify_openalex_institution(row) for row in (institutions.get("results", []) or [])][:3] if ok_inst else []
    oa_works = [simplify_openalex_work(row) for row in (openalex_works.get("results", []) or [])][:5] if ok_works else []
    cf_works = [simplify_crossref_work(row) for row in ((crossref.get("message") or {}).get("items", []) or [])][:5] if ok_crossref else []
    return {
        "id": org.get("id"),
        "name": name,
        "stack": org.get("stack", ""),
        "type": org.get("type", ""),
        "openalex_institutions": oa_inst,
        "openalex_works": oa_works,
        "crossref_works": cf_works,
        "topics": work_topics(oa_works, cf_works),
        "provider_status": {
            "openalex_institutions": ok_inst,
            "openalex_works": ok_works,
            "crossref": ok_crossref,
        },
    }


def collect_all(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collector = collect_person if kind == "person" else collect_org
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(rows)))) as pool:
        futures = {pool.submit(collector, row): row for row in rows}
        for future in as_completed(futures):
            try:
                out.append(future.result())
            except Exception as exc:
                row = futures[future]
                out.append({"id": row.get("id"), "name": row.get("name"), "error": str(exc)})
    sort_key = {row.get("id"): idx for idx, row in enumerate(rows)}
    out.sort(key=lambda row: sort_key.get(row.get("id"), 9999))
    return out


def analytics(people: list[dict[str, Any]], organizations: list[dict[str, Any]]) -> dict[str, Any]:
    topic_counter: Counter[str] = Counter()
    venue_counter: Counter[str] = Counter()
    for row in [*people, *organizations]:
        for topic in row.get("topics", []) or []:
            topic_counter[topic] += 1
        for work in row.get("openalex_works", []) or []:
            if work.get("primary_location"):
                venue_counter[str(work["primary_location"])] += 1
    return {
        "top_topics": [{"topic": topic, "count": count} for topic, count in topic_counter.most_common(20)],
        "top_venues": [{"venue": venue, "count": count} for venue, count in venue_counter.most_common(15)],
        "people_with_openalex_matches": sum(1 for row in people if row.get("openalex_authors")),
        "orgs_with_openalex_matches": sum(1 for row in organizations if row.get("openalex_institutions")),
    }


def main() -> int:
    registry = load_json(REGISTRY_PATH, {})
    if not registry:
        print(f"Missing or unreadable registry: {REGISTRY_PATH}")
        return 1
    people = list(registry.get("people", []))[:16]
    organizations = list(registry.get("organizations", []))[:18]
    people_rows = collect_all("person", people)
    org_rows = collect_all("organization", organizations)
    works = []
    seen = set()
    for row in [*people_rows, *org_rows]:
        for work in [*(row.get("openalex_works", []) or []), *(row.get("crossref_works", []) or [])]:
            key = work.get("doi") or work.get("id") or work.get("url") or work.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            works.append(work)
    payload = {
        "generatedAt": now_iso(),
        "registryPath": REGISTRY_PATH.name,
        "people": people_rows,
        "organizations": org_rows,
        "works": works[:250],
        "analytics": analytics(people_rows, org_rows),
        "provider_status": {
            "openalex": True,
            "crossref": True,
            "orcid_requires_credentials": not (os.environ.get("ORCID_CLIENT_ID") and os.environ.get("ORCID_CLIENT_SECRET")),
        },
    }
    save_json(OUTPUT_PATH, payload)
    print(f"Wrote {OUTPUT_PATH}")
    print(
        "Summary:",
        {
            "people": len(people_rows),
            "organizations": len(org_rows),
            "works": len(payload["works"]),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
