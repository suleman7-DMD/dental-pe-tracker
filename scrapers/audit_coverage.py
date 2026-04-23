"""Phase 3.0 — exhaustive historical gap audit for GDN + PESP.

Run as a diagnostic BEFORE locking the override registry. For every month between
2020-10 and today that the local SQLite DB lacks deals from, this script:

    1. generates a wide set of plausible URL variants for the source;
    2. HEAD-probes each (keeps 200s);
    3. augments the probe set with every URL the Wayback Machine has ever
       captured on plausible path prefixes (catches slugs we didn't guess);
    4. fetches each surviving 200, parses its <h1>/<title> to extract a deal
       month/year, and reports which missing (year, month) each URL fills.

Output: a report on stdout listing
    - confirmed URLs to add to the override registry (with the month they cover)
    - months that remain unresolved after the probe + Wayback sweep
    - URLs that returned 200 but whose inferred month does NOT match a known gap
      (rare — worth eyeballing in case the scraper's title parser disagrees with
       ours).

No DB writes, no state changes. Safe to run any time.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import date
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from scrapers.database import Deal, get_session, init_db
from scrapers.logger_config import get_logger

log = get_logger("audit_coverage")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_NUM = {name: i + 1 for i, name in enumerate(MONTHS)}
# Extended lookup that also handles month abbreviations seen in production
# slugs ("oct-2025", "sept-2021", "dec-2025"). Keyed lowercase.
MONTH_WORDS = {
    **MONTH_NUM,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_WORD_RE = re.compile(
    r"(?<![a-z])(" + "|".join(sorted(MONTH_WORDS, key=len, reverse=True)) + r")[\s\-_]+(20\d{2})(?![0-9])",
    re.IGNORECASE,
)
Q_RE = re.compile(r"(?<![a-z])q([1-4])[\s\-_]+(20\d{2})(?![0-9])", re.IGNORECASE)
YEAR_RE = re.compile(r"(?<![0-9])(20\d{2})(?![0-9])")
EARLIEST = (2020, 10)
HEAD_DELAY_S = 0.25


# ── Inference ─────────────────────────────────────────────────────────────


def inferred_months(text: str) -> set[tuple[int, int]]:
    """Infer (year, month) tuples covered by a URL slug / page title / combo.

    Handles full month names + abbreviations, single quarters, combined
    quarters ("q4-2020-q1-2021"), and year-in-review / top-10 posts.
    Returns an empty set when no month signal is present.
    """
    if not text:
        return set()
    t = text.lower()
    covered: set[tuple[int, int]] = set()
    for m in MONTH_WORD_RE.finditer(t):
        covered.add((int(m.group(2)), MONTH_WORDS[m.group(1).lower()]))
    for m in Q_RE.finditer(t):
        q, y = int(m.group(1)), int(m.group(2))
        for dm in range(1, 4):
            covered.add((y, (q - 1) * 3 + dm))
    if re.search(r"year[\s\-]?in[\s\-]?review|year[\s\-]?end|top[\s\-]?10[\s\-]?dso", t):
        ym = YEAR_RE.search(t)
        if ym:
            yy = int(ym.group(1))
            for mm in range(1, 13):
                covered.add((yy, mm))
    return covered


# ── Missing-month computation ─────────────────────────────────────────────


def missing_months(session, source: str) -> list[tuple[int, int]]:
    """Gap list computed from (source_url → inferred months) with deal_date fallback.

    Must mirror the scraper's _missing_months semantics so the audit and the
    scraper-side coverage warning agree.
    """
    rows = session.query(Deal.source_url, Deal.deal_date).filter(
        Deal.source == source
    ).all()
    present: set[tuple[int, int]] = set()
    url_fallback: dict[str, set[tuple[int, int]]] = {}
    for src_url, dd in rows:
        if src_url:
            inf = inferred_months(src_url)
            if inf:
                present.update(inf)
            elif dd is not None:
                url_fallback.setdefault(src_url, set()).add((dd.year, dd.month))
        elif dd is not None:
            present.add((dd.year, dd.month))
    for months in url_fallback.values():
        present.update(months)
    today = date.today()
    out: list[tuple[int, int]] = []
    y, m = EARLIEST
    while (y, m) < (today.year, today.month):
        if (y, m) not in present:
            out.append((y, m))
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


# ── Candidate generation ──────────────────────────────────────────────────


def gdn_candidates(year: int, month: int) -> list[str]:
    mname = MONTHS[month - 1]
    base = "https://groupdentistrynow.com"
    blog = "https://www.groupdentistrynow.com/dso-group-blog"
    urls = [
        f"{base}/dso-deals-{mname}-{year}/",
        f"{base}/dso-deal-roundup-{mname}-{year}/",
        f"{base}/{mname}-{year}-dso-deals/",
        f"{base}/dso-deals-roundup-{mname}-{year}/",
        f"{base}/dso-deals-{mname}/",
        f"{base}/dso-deal-roundup-{mname}/",
        f"{blog}/dso-deal-roundup-{mname}-{year}/",
        f"{blog}/dso-deals-{mname}-{year}/",
        f"{blog}/{mname}-{year}-dso-deals/",
    ]
    # Quarterly + annual — emit only on quarter/year boundaries
    if month in (3, 6, 9, 12):
        q = (month - 1) // 3 + 1
        urls += [
            f"{base}/q{q}-{year}-dso-deals/",
            f"{base}/dso-deals-q{q}-{year}/",
            f"{blog}/q{q}-{year}-dso-deals/",
        ]
    if month == 12:
        urls += [
            f"{base}/dso-deals-{year}-year-in-review/",
            f"{base}/dso-deals-year-in-review-{year}/",
            f"{base}/top-10-dso-deals-{year}/",
            f"{blog}/dso-deals-{year}-year-in-review/",
        ]
    # The bare slug — worth probing once (we'll dedup outside this fn).
    urls.append(f"{base}/dso-deals/")
    return urls


def pesp_candidates(year: int, month: int) -> list[str]:
    mname = MONTHS[month - 1]
    base = "https://pestakeholder.org"
    urls = [
        f"{base}/news/private-equity-health-care-acquisitions-{mname}-{year}/",
        f"{base}/news/private-equity-healthcare-acquisitions-{mname}-{year}/",
        f"{base}/news/private-equity-healthcare-deals-{mname}-{year}/",
        f"{base}/news/private-equity-health-care-deals-{mname}-{year}/",
    ]
    if month in (3, 6, 9, 12):
        q = (month - 1) // 3 + 1
        urls += [
            f"{base}/reports/private-equity-healthcare-deals-q{q}-{year}/",
            f"{base}/reports/private-equity-health-care-deals-q{q}-{year}/",
        ]
    if month == 12:
        urls += [
            f"{base}/reports/healthcare-deals-{year}-in-review/",
            f"{base}/reports/pe-healthcare-deals-{year}-in-review/",
            f"{base}/reports/private-equity-healthcare-deals-{year}-in-review/",
        ]
    return urls


# ── HEAD probe ────────────────────────────────────────────────────────────


def head_probe(urls: Iterable[str]) -> dict[str, tuple[int, str]]:
    """HEAD-check with redirect-follow. Returns {url: (status, final_url)}."""
    out: dict[str, tuple[int, str]] = {}
    for i, url in enumerate(sorted(set(urls))):
        try:
            resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
            out[url] = (resp.status_code, resp.url or url)
        except requests.RequestException as e:
            out[url] = (0, str(e)[:120])
        time.sleep(HEAD_DELAY_S)
        if (i + 1) % 25 == 0:
            log.info("probed %d/%d", i + 1, len(set(urls)))
    return out


# ── Wayback Machine CDX ───────────────────────────────────────────────────


def wayback_cdx(url_pattern: str, limit: int = 2000) -> list[str]:
    """Hit the Wayback CDX API and return unique original URLs matching a path pattern.

    `url_pattern` is a host+path prefix with `*` wildcard, e.g.
    "groupdentistrynow.com/dso-deals*" or "pestakeholder.org/news/*acquisitions*".
    """
    endpoint = "http://web.archive.org/cdx/search/cdx"
    params = {
        "url": url_pattern,
        "output": "json",
        "limit": str(limit),
        "collapse": "urlkey",
        "fl": "original",
    }
    try:
        resp = requests.get(endpoint, params=params, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Wayback CDX failed for %s: %s", url_pattern, e)
        return []
    try:
        data = resp.json()
    except json.JSONDecodeError:
        log.warning("Wayback CDX returned non-JSON for %s", url_pattern)
        return []
    if not data:
        return []
    # First row is the header
    rows = data[1:] if isinstance(data[0], list) and data[0] and data[0][0] == "original" else data
    urls = set()
    for r in rows:
        if isinstance(r, list) and r:
            u = r[0]
            if u.startswith("http"):
                urls.add(u)
    return sorted(urls)


# ── Title → month extraction ──────────────────────────────────────────────


def infer_year_month_from_url(url: str) -> tuple[int, int] | None:
    """Fast path: infer from the slug itself."""
    m = re.search(r'\b(' + '|'.join(MONTHS) + r')-(\d{4})\b', url.lower())
    if m:
        return int(m.group(2)), MONTH_NUM[m.group(1)]
    m = re.search(r'\b(\d{4})-(' + '|'.join(MONTHS) + r')\b', url.lower())
    if m:
        return int(m.group(1)), MONTH_NUM[m.group(2)]
    m = re.search(r'\bq([1-4])-(\d{4})\b', url.lower())
    if m:
        q = int(m.group(1))
        return int(m.group(2)), (q - 1) * 3 + 1
    return None


def infer_year_month_from_page(url: str) -> tuple[int, int] | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.debug("fetch failed for %s: %s", url, e)
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        title = f"{title} | {h1.get_text(strip=True)}"
    t = title.lower()
    m = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(\d{4})\b', t)
    if m:
        return int(m.group(2)), MONTH_NUM[m.group(1)]
    m = re.search(r'\bq([1-4])\s+(\d{4})\b', t)
    if m:
        q = int(m.group(1))
        return int(m.group(2)), (q - 1) * 3 + 1
    m = re.search(r'\b(20\d{2})\b', t)
    if m and re.search(r'year\s*in\s*review|year-end', t):
        return int(m.group(1)), 12
    return None


# ── Main audit ────────────────────────────────────────────────────────────


def audit_source(session, source: str):
    log.info("=" * 70)
    log.info("Auditing source=%s", source)
    log.info("=" * 70)
    missing = missing_months(session, source)
    log.info("%d missing months in [%s .. today)", len(missing), "2020-10")
    for (y, m) in missing:
        log.info("  MISS %04d-%02d", y, m)

    # Build candidate set
    cand_fn = gdn_candidates if source == "gdn" else pesp_candidates
    cands: set[str] = set()
    for (y, m) in missing:
        cands.update(cand_fn(y, m))
    log.info("%d candidate URLs from patterns (dedup'd)", len(cands))

    # Wayback CDX augmentation
    if source == "gdn":
        patterns = [
            "groupdentistrynow.com/dso-deals*",
            "groupdentistrynow.com/dso-deal-roundup*",
            "groupdentistrynow.com/*dso-deals*",
            "www.groupdentistrynow.com/dso-group-blog/dso-deal*",
        ]
    else:
        patterns = [
            "pestakeholder.org/news/*acquisitions*",
            "pestakeholder.org/news/private-equity-health*",
            "pestakeholder.org/reports/*healthcare*",
        ]
    wb_urls: set[str] = set()
    for p in patterns:
        wb = wayback_cdx(p)
        log.info("Wayback CDX %s -> %d unique originals", p, len(wb))
        wb_urls.update(wb)
    # Filter Wayback URLs to within the missing-months year range to keep probe tractable.
    year_bounds = {y for (y, _) in missing}
    filtered_wb = []
    for u in wb_urls:
        ym = infer_year_month_from_url(u)
        if ym is None:
            filtered_wb.append(u)  # keep — we'll infer via the page
        elif ym[0] in year_bounds:
            filtered_wb.append(u)
    log.info("Wayback candidates retained (year-filter): %d", len(filtered_wb))
    cands.update(filtered_wb)

    log.info("Total HEAD candidates: %d", len(cands))
    results = head_probe(cands)
    alive = {u: final for u, (status, final) in results.items() if status == 200}
    log.info("Alive (HTTP 200): %d", len(alive))

    # Deduplicate by final URL (redirects can collapse multiple candidates)
    final_alive: dict[str, str] = {}  # final_url -> first source URL
    for src_url, final in alive.items():
        final_alive.setdefault(final, src_url)

    # Infer (year, month) set from each alive URL. Unlike the previous single-
    # tuple logic this correctly credits combined-quarter / year-in-review
    # posts for every month they cover, not just their earliest.
    covers: dict[tuple[int, int], list[str]] = defaultdict(list)
    unclassified: list[str] = []
    for final in final_alive:
        months = inferred_months(final)
        if not months:
            page_ym = infer_year_month_from_page(final)
            if page_ym is not None:
                months = {page_ym}
        if not months:
            unclassified.append(final)
        else:
            for ym in months:
                covers[ym].append(final)
    log.info("Classified URL→month bindings: %d", sum(len(v) for v in covers.values()))
    log.info("Unclassified URLs: %d", len(unclassified))

    # Report
    print()
    print("=" * 70)
    print(f"COVERAGE REPORT — {source.upper()}")
    print("=" * 70)
    print(f"Missing months: {len(missing)}")
    print()
    still_missing = []
    filled = []
    misaligned = []
    missing_set = set(missing)
    for (y, m) in missing:
        urls = covers.get((y, m), [])
        if urls:
            filled.append(((y, m), urls))
        else:
            still_missing.append((y, m))
    for ym, urls in sorted(covers.items()):
        if ym not in missing_set:
            misaligned.append((ym, urls))

    print(f"=== FILLED ({len(filled)}) ===")
    for (y, m), urls in filled:
        print(f"  {y:04d}-{m:02d}")
        for u in urls:
            print(f"    + {u}")
    print()
    print(f"=== STILL MISSING ({len(still_missing)}) ===")
    for (y, m) in still_missing:
        print(f"  {y:04d}-{m:02d}")
    print()
    print(f"=== URLS OUTSIDE MISSING SET ({len(misaligned)}) ===")
    for (y, m), urls in misaligned[:30]:
        print(f"  {y:04d}-{m:02d}")
        for u in urls:
            print(f"    ? {u}")
    print()
    print(f"=== UNCLASSIFIED 200s ({len(unclassified)}) ===")
    for u in unclassified[:30]:
        print(f"    ? {u}")
    return {
        "filled": filled,
        "still_missing": still_missing,
        "misaligned": misaligned,
        "unclassified": unclassified,
    }


def main(sources: list[str]):
    init_db()
    session = get_session()
    try:
        report = {}
        for src in sources:
            report[src] = audit_source(session, src)
        return report
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical coverage audit for GDN + PESP")
    parser.add_argument("--source", choices=["gdn", "pesp", "both"], default="both")
    args = parser.parse_args()
    srcs = ["gdn", "pesp"] if args.source == "both" else [args.source]
    main(srcs)
