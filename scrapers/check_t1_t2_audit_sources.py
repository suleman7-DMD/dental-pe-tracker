#!/usr/bin/env python3
"""Fetch cited URLs for the Lane A T1/T2 audit sample.

This is a lightweight source-integrity pass, not a new ownership adjudicator. It
checks whether sampled citations resolve and whether sampled pages contain obvious
corporate/MSO language that should be manually reviewed before DB write.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


BASE = Path("data/dso_research")
LANE = BASE / "_lane_a_20260702"
AUDIT = LANE / "audit_t1_t2_positive_proof_20260704.json"
CANDIDATE = BASE / "_census_candidate_lane_a_wave1_20260702.json"
TRIAGE = BASE / "_lane_a_triage_wave1_20260702.json"
OUT = LANE / "audit_t1_t2_source_check_20260704.json"
MAX_URLS_PER_ROW = 2
MAX_WORKERS = 16

CORPORATE_PATTERNS = re.compile(
    r"\b(supported by|management services|managed by|dental support organization|\bDSO\b|"
    r"Heartland Dental|Aspen Dental|MB2 Dental|North American Dental Group|NADG|"
    r"Dental Dreams|Smile Brands|Sonrava|DentalWorks|Elite Dental Partners|Imagen Dental|"
    r"Great Lakes Dental Partners|United Dental Partners|Affordable Care|ProSmile|"
    r"Private Equity|Warburg Pincus|KKR|Blackstone|Charlesbank|Harvest Partners)\b",
    re.I,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)[:200_000]


def fetch(url: str) -> dict[str, Any]:
    try:
        resp = requests.get(
            url,
            timeout=(3, 6),
            headers={"User-Agent": "Mozilla/5.0 dental-pe-tracker audit source check"},
            allow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001 - audit artifact wants the exact fetch failure
        return {"url": url, "ok": False, "error": type(exc).__name__, "detail": str(exc)[:240]}
    content_type = resp.headers.get("content-type", "")
    body = ""
    corp_hits: list[str] = []
    if "text" in content_type or "html" in content_type or not content_type:
        body = normalize_text(resp.text)
        corp_hits = sorted({m.group(0) for m in CORPORATE_PATTERNS.finditer(body)})[:12]
    return {
        "url": url,
        "ok": 200 <= resp.status_code < 400,
        "status_code": resp.status_code,
        "final_url": resp.url,
        "host": urlparse(resp.url).netloc.lower().removeprefix("www."),
        "content_type": content_type[:120],
        "bytes": len(resp.content or b""),
        "corporate_language_hits": corp_hits,
    }


def main() -> None:
    audit = json.loads(AUDIT.read_text())
    candidate_rows = json.loads(CANDIDATE.read_text()).get("classifications", [])
    triage_rows = json.loads(TRIAGE.read_text())
    by_id = {r.get("location_id"): r for r in candidate_rows}
    for r in triage_rows:
        by_id.setdefault(r.get("location_id"), r)

    jobs = []
    for sample in audit.get("sample", []):
        row = by_id.get(sample["location_id"], {})
        urls = [u for u in row.get("evidence_urls", []) if isinstance(u, str) and u.startswith("http")]
        for url in urls[:MAX_URLS_PER_ROW]:
            jobs.append((sample, url))

    checks_by_location: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(fetch, url): (sample, url) for sample, url in jobs}
        for fut in as_completed(futs):
            sample, url = futs[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001 - audit artifact wants failures
                result = {"url": url, "ok": False, "error": type(exc).__name__, "detail": str(exc)[:240]}
            checks_by_location.setdefault(sample["location_id"], []).append(result)

    checked = []
    for sample in audit.get("sample", []):
        url_checks = checks_by_location.get(sample["location_id"], [])
        checked.append({
            "location_id": sample["location_id"],
            "practice_name": sample.get("practice_name"),
            "assigned_tier": sample.get("assigned_tier"),
            "audit_action": sample.get("audit_action"),
            "sample_strata": sample.get("sample_strata", []),
            "urls_checked": sorted(url_checks, key=lambda c: c.get("url", "")),
            "any_url_ok": any(c.get("ok") for c in url_checks),
            "corporate_language_hits": sorted({
                hit for c in url_checks for hit in c.get("corporate_language_hits", [])
            }),
        })

    summary = {
        "generated_at": now_iso(),
        "sample_rows": len(checked),
        "rows_with_any_url_ok": sum(1 for r in checked if r["any_url_ok"]),
        "rows_with_corporate_language_hits": sum(1 for r in checked if r["corporate_language_hits"]),
        "audit_actions": dict(Counter(r["audit_action"] for r in checked)),
        "fetch_status_counts": dict(Counter(
            str(c.get("status_code") or c.get("error"))
            for r in checked for c in r["urls_checked"]
        )),
        "max_urls_per_row": MAX_URLS_PER_ROW,
        "max_workers": MAX_WORKERS,
        "note": "Corporate-language hits are review flags only; many directory or article pages mention DSO terms generically.",
    }
    OUT.write_text(json.dumps({"_meta": summary, "rows": checked}, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("source_check", OUT)


if __name__ == "__main__":
    main()
