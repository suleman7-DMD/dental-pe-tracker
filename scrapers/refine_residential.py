"""
refine_residential.py — Tighten the `is_likely_residential` flag in `practice_locations`.

The original residential rule (in `dedup_practice_locations.py`) was:
    no_org_npi AND solo AND no_website AND no_employees AND not_in_dso

This caught real home offices but ALSO over-flagged Boston dental-school
trainees, billing-aggregation addresses, and solo commercial dentists who
just don't list a website on NPPES. To reduce false positives, this script
re-evaluates each row and clears the flag unless ADDITIONAL evidence
supports a residential conclusion.

Refined rule (still operates on the existing `is_likely_residential=TRUE`
candidates — never raises the flag where it wasn't already):

    KEEP is_likely_residential=TRUE iff one of:
      (a) Address suffix is strongly residential (LN, CT, CIR, PL, TER, WAY)
      (b) No phone AND not data_axle_enriched (silent address — likely retired)
      (c) provider_count == 0 AND has_org_npi=FALSE (empty shell — orphan)
      (d) ZIP is a known dental school / academic medical center (trainees
          register NPIs at the school but don't run practices there — the
          flag's actual function is "exclude from practice counts")

    Otherwise: clear is_likely_residential to FALSE (these are likely
    real solo practices in commercial spaces).

Spec: handoff prompt §Step 2 — "Add bonus signals: street suffix patterns
(CT/CIR/LN/PL more residential), no Data Axle enrichment, taxonomy filter."

Usage:
    python3 scrapers/refine_residential.py
    python3 scrapers/refine_residential.py --dry-run
"""

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from sqlalchemy import text
from scrapers.database import get_session
from scrapers.logger_config import get_logger

log = get_logger("refine_residential")


_RESIDENTIAL_SUFFIX_PATTERNS = [
    re.compile(r"\b(ln|lane)$"),
    re.compile(r"\b(ct|court)$"),
    re.compile(r"\b(cir|circle)$"),
    re.compile(r"\b(pl|place)$"),
    re.compile(r"\b(ter|terrace)$"),
    re.compile(r"\b(way)$"),
]


def has_residential_suffix(normalized_address: str) -> bool:
    """Return True if address ends in a strongly residential street suffix."""
    if not normalized_address:
        return False
    a = normalized_address.strip().lower()
    return any(p.search(a) for p in _RESIDENTIAL_SUFFIX_PATTERNS)


def is_silent_address(phone: str, data_axle_enriched: int) -> bool:
    """No phone AND not enriched by Data Axle = invisible to commercial datasets."""
    no_phone = not (phone or "").strip()
    not_axle = not bool(data_axle_enriched)
    return no_phone and not_axle


def is_orphan_shell(provider_count: int, has_org_npi: int) -> bool:
    """Edge case: provider_count==0 AND no org NPI = nothing exists at this address."""
    return (provider_count or 0) == 0 and not bool(has_org_npi)


# ZIPs hosting a dental school or academic medical campus. NPIs registered
# here are usually trainees (students, residents, interns) who use the school
# address as their NPPES practice location but don't run a practice. Treating
# these as "residential" (= excluded from practice counts) is the correct
# behavior; the flag name is a misnomer but its function is "filter out".
_ACADEMIC_ZIPS = {
    "02111",  # Tufts School of Dental Medicine
    "02114",  # MGH / Beacon Hill academic medical campus
    "02115",  # Harvard SDM, Brigham, Longwood Medical Area
    "02118",  # BMC, BU School of Medicine
    "02134",  # Allston (BU)
    "02215",  # Fenway (BU campus)
    "60612",  # UIC College of Dentistry
    "60153",  # Loyola Medical Center / Stritch School
}


def in_academic_zip(zip_code: str) -> bool:
    """Return True if ZIP hosts a dental school / academic medical center."""
    return (zip_code or "").strip() in _ACADEMIC_ZIPS


def refined_residential(loc: dict) -> bool:
    """Apply refined residential rule to a single row."""
    # Only reconsider rows the basic rule already flagged.
    if not bool(loc.get("is_likely_residential")):
        return False

    norm_addr = loc.get("normalized_address") or ""
    phone = loc.get("phone")
    data_axle_enriched = loc.get("data_axle_enriched")
    provider_count = loc.get("provider_count")
    has_org_npi = loc.get("has_org_npi")

    # Bonus signals (only need ONE to keep the residential flag)
    if has_residential_suffix(norm_addr):
        return True
    if is_silent_address(phone, data_axle_enriched):
        return True
    if is_orphan_shell(provider_count, has_org_npi):
        return True
    if in_academic_zip(loc.get("zip")):
        return True

    return False


def run(session, dry_run: bool = False):
    log.info("Loading current practice_locations rows...")
    rows = session.execute(text(
        "SELECT location_id, normalized_address, phone, data_axle_enriched, "
        "       provider_count, has_org_npi, is_likely_residential, "
        "       practice_name, zip "
        "FROM practice_locations"
    )).fetchall()
    cols = ["location_id", "normalized_address", "phone", "data_axle_enriched",
            "provider_count", "has_org_npi", "is_likely_residential",
            "practice_name", "zip"]

    before_residential = 0
    after_residential = 0
    cleared = []
    kept = 0

    for r in rows:
        loc = dict(zip(cols, r))
        was = bool(loc["is_likely_residential"])
        will_be = refined_residential(loc)
        if was:
            before_residential += 1
        if will_be:
            after_residential += 1
            kept += 1
        elif was:
            cleared.append(loc)

    log.info("Residential count: BEFORE=%d, AFTER=%d, KEPT=%d, CLEARED=%d",
             before_residential, after_residential, kept, len(cleared))

    # Print sample of cleared rows for sanity check
    log.info("Sample of CLEARED (no longer residential) rows:")
    for c in cleared[:10]:
        log.info("  %s | %s | %s, %s",
                 c["practice_name"] or "<no name>",
                 c["normalized_address"],
                 c["phone"] or "<no phone>",
                 c["zip"])

    if dry_run:
        log.info("[DRY RUN] No changes written.")
        return before_residential, after_residential

    # Apply updates: clear flag for rows that no longer qualify
    log.info("Updating %d rows: clearing is_likely_residential...", len(cleared))
    now = datetime.utcnow().isoformat()
    for c in cleared:
        session.execute(
            text(
                "UPDATE practice_locations "
                "SET is_likely_residential = 0, updated_at = :now "
                "WHERE location_id = :lid"
            ),
            {"now": now, "lid": c["location_id"]},
        )
    session.commit()
    log.info("Done. is_likely_residential cleared for %d rows.", len(cleared))
    return before_residential, after_residential


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    session = get_session()
    try:
        before, after = run(session, dry_run=args.dry_run)
        print(f"\nRESIDENTIAL FILTER REFINEMENT:")
        print(f"  Before: {before}")
        print(f"  After:  {after}")
        print(f"  Cleared: {before - after}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
