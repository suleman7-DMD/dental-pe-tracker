"""Cross-link dso_locations → practices.

For each scraped DSO office in dso_locations whose ZIP falls within
watched_zips, find practices at the same physical address and flip their
ownership_status to dso_affiliated. Address normalization strips suite
numbers, expands directionals, and normalizes common abbreviations so a
clinic at "320 Washington St. Suite 100" matches "320 WASHINGTON STREET".

Conservative: requires (zip, normalized_street) exact match. Falls back
to high-confidence (>= 92) fuzzy match on street if exact fails — only
catches cases like "Newbury Street" vs "Newbury St" that survive normalization.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

from rapidfuzz import fuzz

from scrapers.database import init_db, get_session
from scrapers.dso_classifier import (
    KNOWN_DSOS,
    _normalize_address_for_grouping,
    _strip_suite_for_location_key,
)
from scrapers.logger_config import get_logger

log = get_logger("cross_link_dso_locations")


def _norm_street(addr: str) -> str:
    if not addr:
        return ""
    a = _normalize_address_for_grouping(addr)
    a = _strip_suite_for_location_key(a)
    a = re.sub(r"\.", "", a)
    a = re.sub(r"\s+", " ", a)
    return a.strip().upper()


def cross_link():
    init_db()
    session = get_session()
    try:
        from sqlalchemy import text

        dso_locs = session.execute(text(
            "SELECT id, dso_name, address, city, state, zip "
            "FROM dso_locations "
            "WHERE zip IN (SELECT zip_code FROM watched_zips) "
            "AND address IS NOT NULL AND address != ''"
        )).fetchall()
        log.info("Loaded %d dso_locations rows in watched ZIPs", len(dso_locs))
        if not dso_locs:
            return 0

        practices_by_zip: dict[str, list[dict]] = defaultdict(list)
        rows = session.execute(text(
            "SELECT npi, practice_name, address, city, state, zip, "
            "ownership_status, affiliated_dso, classification_confidence "
            "FROM practices "
            "WHERE zip IN (SELECT zip_code FROM watched_zips) "
            "AND address IS NOT NULL AND address != ''"
        )).fetchall()
        for r in rows:
            npi, pn, addr, city, st, zp, status, aff, conf = r
            practices_by_zip[zp].append({
                "npi": npi,
                "name": pn,
                "addr_norm": _norm_street(addr),
                "addr_raw": addr,
                "city": city,
                "state": st,
                "zip": zp,
                "ownership_status": status,
                "affiliated_dso": aff,
                "conf": conf,
            })
        log.info("Loaded %d watched-ZIP practices", sum(len(v) for v in practices_by_zip.values()))

        sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)

        flipped = 0
        examples: list[tuple] = []
        npis_seen = set()

        for loc in dso_locs:
            loc_id, dso_name, loc_addr, loc_city, loc_state, loc_zip = loc
            loc_norm = _norm_street(loc_addr)
            if not loc_norm:
                continue

            dso_lower = (dso_name or "").lower()
            matched_pe = None
            matched_canonical = dso_name
            for pattern, canonical, pe_sponsor in sorted_dsos:
                if pattern in dso_lower:
                    matched_canonical = canonical
                    matched_pe = pe_sponsor
                    break

            pool = practices_by_zip.get(loc_zip, [])
            if not pool:
                continue

            for p in pool:
                if p["npi"] in npis_seen:
                    continue
                if not p["addr_norm"]:
                    continue
                exact = p["addr_norm"] == loc_norm
                fuzzy_score = (
                    0
                    if exact
                    else fuzz.token_sort_ratio(p["addr_norm"], loc_norm)
                )
                if not (exact or fuzzy_score >= 92):
                    continue

                npis_seen.add(p["npi"])
                new_conf = max(p["conf"] or 0, 85)
                session.execute(
                    text(
                        "UPDATE practices SET "
                        "ownership_status = CASE WHEN :pe IS NOT NULL THEN 'pe_backed' ELSE 'dso_affiliated' END, "
                        "affiliated_dso = COALESCE(affiliated_dso, :canon), "
                        "affiliated_pe_sponsor = COALESCE(affiliated_pe_sponsor, :pe), "
                        "classification_confidence = :nc, "
                        "classification_reasoning = COALESCE(classification_reasoning, '') || "
                        "  ' | dsoloc_xlink: address matches ' || :canon || ' location at ' || :loc_addr "
                        "WHERE npi = :npi"
                    ),
                    {
                        "pe": matched_pe,
                        "canon": matched_canonical,
                        "nc": new_conf,
                        "loc_addr": loc_addr,
                        "npi": p["npi"],
                    },
                )
                flipped += 1
                if len(examples) < 12:
                    examples.append((
                        p["npi"], p["name"][:40] if p["name"] else "",
                        loc_addr[:30], dso_name,
                        "exact" if exact else f"fuzzy={fuzzy_score}",
                    ))

        session.commit()
        log.info("=" * 60)
        log.info("DSO LOCATIONS CROSS-LINK COMPLETE: %d practices flipped", flipped)
        for ex in examples:
            log.info("  npi=%s '%s' addr='%s' dso=%s match=%s", *ex)
        return flipped
    finally:
        session.close()


if __name__ == "__main__":
    n = cross_link()
    print(f"\nResult: {n} NPIs flipped via dso_locations cross-link")
    sys.exit(0)
