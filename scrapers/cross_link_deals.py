"""Cross-link deals + affiliated_dso → practices.

Two corroboration passes — both extremely conservative.

Pass A (HIGH LEVERAGE):
  Find practices whose `affiliated_dso` already matches a known DSO brand
  but whose `ownership_status` was left as 'independent' or 'unknown' (Pass 1
  matched the name pattern but didn't flip status, usually due to confidence
  ceiling). Promote those rows to dso_affiliated and bump
  classification_confidence to 80 so the next classifier pass picks them up
  via Rule 3.

Pass B (LOW LEVERAGE — kept for completeness):
  For deals with a clean target_name and a deal platform_company that
  fuzzy-matches a practice in IL/MA, flip to pe_backed. Most deal target
  names refer to absorbed shell entities so this catches very few NPIs.

Conservative thresholds:
  - Pass A: token containment match against the canonical DSO brand list
  - Pass B: rapidfuzz token_sort_ratio >= 92 (raised from 88 after empirical
    testing — at 88 the only matches were lexical false positives like
    "Stillwater Dental Associates" → "Tower Dental Associates")
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

from rapidfuzz import fuzz, process

from scrapers.database import init_db, get_session
from scrapers.dso_classifier import KNOWN_DSOS
from scrapers.logger_config import get_logger

log = get_logger("cross_link_deals")

NAME_BLACKLIST_FRAGMENTS = (
    "specialty partners",
    "nate thompson",
    "carlo ronci",
    "tony reeder",
    "based on",
    "according to",
    "northeast to",
    "located",
    "which is",
    "the mid-atlantic",
    "select is",
    "dr. ",
    "dr ",
)
GENERIC_TOO_SHORT = ("dental", "dentistry", "smiles", "smile", "orthodontics")
MIN_LEN = 8


def _is_clean_target(name: str) -> bool:
    n = name.strip().lower()
    if len(n) < MIN_LEN:
        return False
    if n in GENERIC_TOO_SHORT:
        return False
    if any(frag in n for frag in NAME_BLACKLIST_FRAGMENTS):
        return False
    if re.match(r"^(dr\.|dr )", n):
        return False
    return True


def _normalize_practice_name(name: str) -> str:
    if not name:
        return ""
    n = name.upper()
    n = re.sub(r"\b(LLC|PC|LTD|INC|PLLC|DDS|DMD|MD|PA|CORP|CORPORATION)\b", "", n)
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def pass_a_reconcile_affiliated_dso(session) -> tuple[int, int]:
    """Promote practices where affiliated_dso matches known DSO but
    ownership_status wasn't updated.

    Returns (rows_examined, rows_flipped).
    """
    from sqlalchemy import text

    rows = session.execute(text(
        "SELECT npi, affiliated_dso, ownership_status, classification_confidence "
        "FROM practices "
        "WHERE zip IN (SELECT zip_code FROM watched_zips) "
        "AND affiliated_dso IS NOT NULL AND affiliated_dso != '' "
        "AND (ownership_status IS NULL "
        "     OR ownership_status IN ('independent','unknown'))"
    )).fetchall()
    log.info("Pass A: %d candidate rows where affiliated_dso is set but status is independent/unknown",
             len(rows))

    sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
    flipped = 0
    examples: list[tuple] = []

    for npi, dso_name, status, conf in rows:
        dso_lower = (dso_name or "").lower()
        matched_canonical = None
        matched_pe = None
        for pattern, canonical, pe_sponsor in sorted_dsos:
            if pattern in dso_lower:
                matched_canonical = canonical
                matched_pe = pe_sponsor
                break

        if not matched_canonical:
            try:
                for pattern, canonical, pe_sponsor in sorted_dsos:
                    if fuzz.token_sort_ratio(dso_lower, canonical.lower()) >= 90:
                        matched_canonical = canonical
                        matched_pe = pe_sponsor
                        break
            except Exception:
                pass

        if not matched_canonical:
            continue

        new_conf = max(conf or 0, 80)
        session.execute(
            text(
                "UPDATE practices SET "
                "ownership_status = CASE WHEN :pe IS NOT NULL THEN 'pe_backed' ELSE 'dso_affiliated' END, "
                "affiliated_pe_sponsor = COALESCE(affiliated_pe_sponsor, :pe), "
                "classification_confidence = :nc, "
                "classification_reasoning = COALESCE(classification_reasoning, '') || "
                "  ' | dso_xlink: affiliated_dso=' || :dso || ' matches known DSO ' || :canon "
                "WHERE npi = :npi"
            ),
            {
                "pe": matched_pe,
                "nc": new_conf,
                "dso": dso_name,
                "canon": matched_canonical,
                "npi": npi,
            },
        )
        flipped += 1
        if len(examples) < 10:
            examples.append((npi, dso_name, matched_canonical, matched_pe, status))

    log.info("Pass A: flipped %d practices", flipped)
    for ex in examples:
        log.info("  ex: npi=%s affiliated_dso='%s' → canonical='%s' pe='%s' (was %s)",
                 *ex)
    session.flush()
    return len(rows), flipped


def pass_b_deal_target_match(session) -> tuple[int, int]:
    """Conservative fuzzy-match of clean deal target_name → practice_name.

    Threshold raised to 92 to suppress lexical-only token-overlap matches
    like "Stillwater Dental Associates" → "Tower Dental Associates" (86).
    Returns (deals_matched, npis_flipped).
    """
    from sqlalchemy import text

    deals = session.execute(text(
        "SELECT id, target_name, target_state, platform_company, "
        "pe_sponsor, deal_date, source FROM deals "
        "WHERE target_state IN ('IL','MA') "
        "AND target_name IS NOT NULL AND LENGTH(target_name) >= 8 "
        "AND platform_company IS NOT NULL "
        "AND platform_company NOT IN ('Unknown', '')"
    )).fetchall()

    clean = []
    for d in deals:
        tn = d[1] or ""
        if _is_clean_target(tn):
            clean.append({
                "id": d[0], "target_name": tn, "state": d[2],
                "platform": d[3], "sponsor": d[4],
                "date": d[5], "source": d[6],
            })
    log.info("Pass B: %d/%d deals have clean targets", len(clean), len(deals))

    practices_by_state = defaultdict(list)
    rows = session.execute(text(
        "SELECT npi, practice_name, doing_business_as, state, zip "
        "FROM practices "
        "WHERE state IN ('IL','MA') "
        "AND zip IN (SELECT zip_code FROM watched_zips)"
    )).fetchall()
    for r in rows:
        npi, pn, dba, st, zp = r
        practices_by_state[st].append({
            "npi": npi,
            "name_norm": _normalize_practice_name(pn or ""),
            "dba_norm": _normalize_practice_name(dba or ""),
            "raw_name": pn,
            "raw_dba": dba,
            "zip": zp,
        })

    matches = []
    for d in clean:
        target_norm = _normalize_practice_name(d["target_name"])
        if len(target_norm) < MIN_LEN:
            continue
        pool = practices_by_state.get(d["state"], [])
        if not pool:
            continue

        best = None
        for p in pool:
            for fld_name, cand in (("name", p["name_norm"]), ("dba", p["dba_norm"])):
                if not cand:
                    continue
                score = fuzz.token_sort_ratio(target_norm, cand)
                if score >= 92 and (best is None or score > best[1]):
                    best = (p, score, fld_name)
        if best:
            p, score, fld_name = best
            matches.append({
                "deal_id": d["id"],
                "target_name": d["target_name"],
                "platform": d["platform"],
                "sponsor": d["sponsor"],
                "date": d["date"],
                "source": d["source"],
                "npi": p["npi"],
                "matched_name": p["raw_name"] or p["raw_dba"],
                "score": score,
                "matched_field": fld_name,
                "zip": p["zip"],
            })

    log.info("Pass B: %d high-confidence matches at score >= 92", len(matches))
    for m in matches:
        log.info("  '%s' → NPI %s '%s' (score=%d, field=%s, zip=%s, plat=%s)",
                 m["target_name"][:40], m["npi"],
                 (m["matched_name"] or "")[:40], m["score"],
                 m["matched_field"], m["zip"], m["platform"])

    flipped = 0
    npis_updated = set()
    for m in matches:
        if m["npi"] in npis_updated:
            continue
        npis_updated.add(m["npi"])
        session.execute(
            text(
                "UPDATE practices SET "
                "ownership_status='pe_backed', "
                "affiliated_pe_sponsor=COALESCE(affiliated_pe_sponsor, :sponsor, :platform), "
                "affiliated_dso=COALESCE(affiliated_dso, :platform), "
                "classification_confidence = CASE WHEN classification_confidence < 80 "
                "  THEN 80 ELSE classification_confidence END, "
                "classification_reasoning = COALESCE(classification_reasoning, '') || "
                "  ' | deal_xlink: matches target of ' || :platform || ' deal ' || :dt "
                "WHERE npi = :npi"
            ),
            {
                "sponsor": m["sponsor"] or m["platform"],
                "platform": m["platform"],
                "dt": str(m["date"] or ""),
                "npi": m["npi"],
            },
        )
        flipped += 1

    return len({m["deal_id"] for m in matches}), flipped


def cross_link():
    init_db()
    session = get_session()
    try:
        a_examined, a_flipped = pass_a_reconcile_affiliated_dso(session)
        b_deals, b_flipped = pass_b_deal_target_match(session)
        session.commit()
        log.info("=" * 60)
        log.info("DEAL CROSS-LINK COMPLETE")
        log.info("  Pass A (affiliated_dso reconciliation): %d/%d flipped",
                 a_flipped, a_examined)
        log.info("  Pass B (deal target_name fuzzy match): %d deals → %d NPIs flipped",
                 b_deals, b_flipped)
        log.info("  TOTAL: %d NPIs promoted to corporate", a_flipped + b_flipped)
        return a_flipped + b_flipped
    finally:
        session.close()


if __name__ == "__main__":
    n = cross_link()
    print(f"\nResult: {n} NPIs promoted to corporate")
    sys.exit(0)
