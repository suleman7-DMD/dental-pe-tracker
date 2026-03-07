"""
DSO Classifier — identifies which NPPES practices are DSO-affiliated
based on practice names, known DSO names, and management keywords.

Usage:
    python3 scrapers/dso_classifier.py                    # classify all practices
    python3 scrapers/dso_classifier.py --zip-filter       # only watched ZIP codes
    python3 scrapers/dso_classifier.py --force             # overwrite existing classifications
    python3 scrapers/dso_classifier.py --dry-run           # show classifications without saving
"""

import argparse
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_session, Practice, WatchedZip, DSOLocation,
    log_practice_change, table_exists,
)
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("dso_classifier")

# ── Known DSO Names → PE Sponsor Mapping ────────────────────────────────────

# (dso_name_pattern, canonical_dso_name, pe_sponsor_or_None)
# Sorted longest-first at runtime to avoid partial matches
KNOWN_DSOS = [
    ("heartland dental", "Heartland Dental", "KKR"),
    ("aspen dental", "Aspen Dental", "Leonard Green & Partners"),
    ("tag - the aspen group", "Aspen Dental", "Leonard Green & Partners"),
    ("pacific dental services", "Pacific Dental Services", None),
    ("pds health", "Pacific Dental Services", None),
    ("mb2 dental", "MB2 Dental", "Charlesbank Capital Partners"),
    ("dental365", "Dental365", "The Jordan Company"),
    ("dental 365", "Dental365", "The Jordan Company"),
    ("specialized dental partners", "Specialized Dental Partners", "Quad-C Management"),
    ("great expressions", "Great Expressions", None),
    ("affordable care", "Affordable Care", None),
    ("affordable dentures", "Affordable Care", None),
    ("benevis", "Benevis", None),
    ("kool smiles", "Benevis", None),
    ("interdent", "InterDent", None),
    ("western dental", "Western Dental", None),
    ("sonrava health", "Western Dental", None),
    ("sonrava", "Western Dental", None),
    ("dental care alliance", "Dental Care Alliance", "Harvest Partners"),
    ("42 north dental", "42 North Dental", None),
    ("tend dental", "Tend", None),
    ("mortenson dental", "Mortenson Dental Partners", None),
    ("community dental partners", "Community Dental Partners", None),
    ("risas dental", "Risas Dental", None),
    ("sage dental", "Sage Dental", "Linden Capital Partners"),
    ("lightwave dental", "Lightwave Dental", None),
    ("smile brands", "Smile Brands", "Gryphon Investors"),
    ("gentle dental", "Gentle Dental", None),
    ("comfort dental", "Comfort Dental", None),
    ("brident dental", "Brident", None),
    ("brident", "Brident", None),
    ("monarch dental", "Monarch Dental", None),
    ("castle dental", "Castle Dental", None),
    ("familia dental", "Familia Dental", None),
    ("ideal dental", "Ideal Dental", None),
    ("jefferson dental", "Jefferson Dental", None),
    ("smile design dentistry", "Smile Design Dentistry", None),
    ("rodeo dental", "Rodeo Dental", None),
    ("d4c dental", "D4C Dental Brands", None),
    ("southern orthodontic partners", "Southern Orthodontic Partners", "Shore Capital Partners"),
    ("us oral surgery management", "USOSM", "Oak Hill Capital"),
    ("u.s. oral surgery management", "USOSM", "Oak Hill Capital"),
    ("usosm", "USOSM", "Oak Hill Capital"),
    ("salt dental", "SALT Dental", "Latticework Capital"),
    ("chord specialty", "Chord Specialty Dental Partners", "Rock Mountain Capital"),
    ("max surgical", "MAX Surgical", "MedEquity Capital"),
    ("smile partners", "Smile Partners USA", "Silver Oak Services Partners"),
    ("smilist", "The Smilist", None),
    ("parkview dental partners", "Parkview Dental Partners", "Cathay Capital"),
    ("t management", "T Management", "Georgia Oak Partners"),
    ("silver creek dental", "Silver Creek Dental Partners", None),
    ("elevate dental", "Elevate Dental", None),
    ("peak dental", "Peak Dental", None),
    ("dental one partners", "Dental One Partners", None),
    ("dentalone", "Dental One Partners", None),
    ("dentalcorp", "Dentalcorp", None),
    ("careington", "Careington", None),
    ("access dental", "Access Dental", None),
    ("birner dental", "Birner Dental", None),
    ("corus orthodontist", "Corus Orthodontists", None),
    ("orthosynetics", "OrthoSynetics", None),
    ("north american dental group", "North American Dental Group", "Jacobs Holding"),
    ("nadg", "North American Dental Group", "Jacobs Holding"),
    ("midwest dental", "Midwest Dental", None),
    ("dental associates group", "Dental Associates Group", None),
    ("oms360", "OMS360", None),
    ("oral surgery partners", "Oral Surgery Partners", None),
    ("us endo partners", "US Endo Partners", None),
    ("endodontic practice partners", "Endodontic Practice Partners", None),
    ("archway dental", "Archway Dental Partners", "Martis Capital"),
    ("vision dental partners", "Vision Dental Partners", None),
    ("apex dental partners", "Apex Dental Partners", None),
    ("blue sea dental", "Blue Sea Dental", None),
    ("motor city dental", "Motor City Dental Partners", None),
    ("pearl street dental", "Pearl Street Dental Partners", None),
    ("bebright", "beBright", "InTandem Capital Partners"),
    ("imagen dental", "Imagen Dental Partners", None),
    ("lumio dental", "Lumio Dental", None),
    ("straine dental", "Straine Dental Management", None),
    ("shared practices", "Shared Practices Group", None),
    ("choice dental", "Choice Dental Group", None),
    ("pepperpointe", "PepperPointe Partnerships", None),
    ("riccobene", "Riccobene Associates", "Comvest Partners"),
]

# Management/corporate keywords that suggest DSO affiliation
MGMT_KEYWORDS = [
    "dental management",
    "dental partners",
    "dental group management",
    "oral surgery management",
    "dental support",
    "practice management",
    "dental services organization",
    "management services",
    " dso",  # space before to avoid matching "windsor" etc.
]

# Patterns that suggest a normal (non-DSO) independent practice
INDEPENDENT_PATTERNS = [
    r"^dr\.?\s+\w",                           # "Dr. Smith"
    r"\b(dds|dmd|dmd pc|dds pc|dds pllc)\b",  # Dentist credentials
    r"family dent",                            # "Family Dentistry"
    r"pediatric dent",                         # unless matched by DSO name
    r"orthodontic",                            # generic ortho practice
    r"^[a-z]+ [a-z]+ (dental|dentistry)$",    # "First Last Dental"
    r"(dental|dentistry) (of|at|in) \w+",     # "Dentistry of Naperville"
]


# ── Classification Logic ───────────────────────────────────────────────────


def classify_practice(practice_name, dba_name):
    """Classify a practice based on its names.
    Returns (status, dso_name, pe_sponsor, confidence, reason)."""
    if not practice_name and not dba_name:
        return "unknown", None, None, 0, "no name data"

    names_to_check = []
    if practice_name:
        names_to_check.append(practice_name.lower())
    if dba_name:
        names_to_check.append(dba_name.lower())

    combined = " ".join(names_to_check)

    # Step 1: Check against known DSO names (sorted longest first)
    sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
    for pattern, canonical_name, pe_sponsor in sorted_dsos:
        if pattern in combined:
            status = "pe_backed" if pe_sponsor else "dso_affiliated"
            return status, canonical_name, pe_sponsor, 95, f"matches known DSO: {canonical_name}"

    # Step 2: Check management keywords
    for kw in MGMT_KEYWORDS:
        if kw in combined:
            return "dso_affiliated", None, None, 70, f"contains management keyword: '{kw.strip()}'"

    # Step 3: Corporate patterns suggesting DSO
    # "Holdings" or "Management" in legal name (not DBA)
    if practice_name:
        pn = practice_name.lower()
        if re.search(r'\bholdings?\b', pn) and re.search(r'\bdental\b', pn):
            return "dso_affiliated", None, None, 60, "corporate structure: dental holdings"
        # Multiple LLCs or complex corporate names
        if re.search(r'\bmanagement\b.*\b(llc|inc|corp)\b', pn):
            return "dso_affiliated", None, None, 55, "corporate structure: management entity"

    # Step 4: Check for independent practice patterns
    for pat in INDEPENDENT_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return "independent", None, None, 50, f"matches independent pattern"

    # Step 5: Default — if entity is an organization with a generic dental name
    return "unknown", None, None, 0, "no matching patterns"


def _pe_sponsor_for_dso(dso_name):
    """Look up PE sponsor for a DSO name from the known mapping."""
    if not dso_name:
        return None
    dn = dso_name.lower()
    for pattern, canonical, pe in KNOWN_DSOS:
        if pattern in dn or dn in pattern:
            return pe
    return None


def _location_match_pass(session, practices, counts, dry_run, force, today):
    """Second pass: match practices against dso_locations by ZIP + address."""
    from rapidfuzz import fuzz
    from scrapers.database import PracticeChange

    # Build a lookup: zip → list of DSO locations
    all_locs = session.query(DSOLocation).all()
    zip_locs = {}
    for loc in all_locs:
        if loc.zip:
            zip_locs.setdefault(loc.zip, []).append(loc)

    # Filter practices to only those with ZIPs in dso_locations (avoid iterating all)
    dso_zips = set(zip_locs.keys())
    candidates = [p for p in practices
                  if p.zip and p.zip in dso_zips
                  and (force or p.ownership_status not in ("pe_backed", "dso_affiliated"))]

    upgrades = 0
    for practice in candidates:

        best_loc = None
        best_score = 0
        for loc in zip_locs[practice.zip]:
            if loc.address and practice.address:
                score = fuzz.token_sort_ratio(
                    loc.address.lower(), practice.address.lower()
                )
                if score >= 85 and score > best_score:
                    best_loc = loc
                    best_score = score

        if not best_loc:
            continue

        dso_name = best_loc.dso_name
        pe_sponsor = _pe_sponsor_for_dso(dso_name)
        new_status = "pe_backed" if pe_sponsor else "dso_affiliated"
        old_status = practice.ownership_status

        # Adjust counts: undo the pass-1 count, add new one
        if old_status in counts:
            counts[old_status] -= 1
        counts[new_status] += 1
        upgrades += 1

        if not dry_run:
            practice.ownership_status = new_status
            practice.affiliated_dso = dso_name
            if pe_sponsor:
                practice.affiliated_pe_sponsor = pe_sponsor

            if old_status not in ("pe_backed", "dso_affiliated"):
                session.add(PracticeChange(
                    npi=practice.npi,
                    change_date=today,
                    field_changed="ownership_status",
                    old_value=old_status or "unknown",
                    new_value=new_status,
                    change_type="acquisition",
                    notes=f"Location-matched to {dso_name} (addr score={best_score})",
                ))

    if not dry_run:
        session.commit()
    log.info("Pass 2: %d practices upgraded via location matching", upgrades)
    return upgrades


# ── Main ────────────────────────────────────────────────────────────────────


def run(zip_filter=False, force=False, dry_run=False):
    _t0 = log_scrape_start("dso_classifier")
    log.info("=" * 60)
    log.info("DSO Classifier starting (zip_filter=%s, force=%s, dry_run=%s)",
             zip_filter, force, dry_run)
    log.info("=" * 60)

    init_db()
    session = get_session()

    # Build query
    query = session.query(Practice)

    if not force:
        # Only classify practices with unknown or null status
        query = query.filter(
            (Practice.ownership_status == "unknown") |
            (Practice.ownership_status.is_(None))
        )

    if zip_filter:
        watched = session.query(WatchedZip.zip_code).all()
        watched_zips = [z[0] for z in watched]
        query = query.filter(Practice.zip.in_(watched_zips))
        log.info("Filtering to %d watched ZIP codes", len(watched_zips))

    practices = query.all()
    total = len(practices)

    if total == 0:
        print("0 practices to classify.")
        session.close()
        return

    log.info("Classifying %d practices...", total)

    # Stats
    counts = {"pe_backed": 0, "dso_affiliated": 0, "independent": 0, "unknown": 0}
    changes_made = 0
    today = date.today()

    from scrapers.database import PracticeChange
    pending_changes = []

    for i, practice in enumerate(practices):
        if (i + 1) % 10_000 == 0:
            log.info("  Classified %dk / %dk...", (i + 1) // 1000, total // 1000)
            if not dry_run:
                session.bulk_save_objects(pending_changes)
                session.commit()
                pending_changes = []

        status, dso_name, pe_sponsor, confidence, reason = classify_practice(
            practice.practice_name, practice.doing_business_as
        )

        counts[status] += 1

        if dry_run:
            continue

        # Update practice
        old_status = practice.ownership_status
        if status != old_status:
            practice.ownership_status = status
            if dso_name:
                practice.affiliated_dso = dso_name
            if pe_sponsor:
                practice.affiliated_pe_sponsor = pe_sponsor

            # Queue change log (batch insert later)
            if old_status in ("unknown", None) and status in ("pe_backed", "dso_affiliated"):
                pending_changes.append(PracticeChange(
                    npi=practice.npi,
                    change_date=today,
                    field_changed="ownership_status",
                    old_value=old_status or "unknown",
                    new_value=status,
                    change_type="acquisition",
                    notes=f"Auto-classified: {reason}"
                    + (f" — DSO: {dso_name}" if dso_name else ""),
                ))

            changes_made += 1

    # Flush remaining
    if not dry_run and pending_changes:
        session.bulk_save_objects(pending_changes)
        session.commit()

    # ── Pass 2: Location-based matching against dso_locations ──
    location_upgrades = 0
    if table_exists("dso_locations"):
        loc_count = session.query(DSOLocation).count()
        if loc_count > 0:
            log.info("Pass 2: Matching against %d DSO locations...", loc_count)
            location_upgrades = _location_match_pass(
                session, practices, counts, dry_run, force, today
            )
        else:
            log.info("Pass 2: dso_locations table is empty, skipping.")
    else:
        log.info("Pass 2: dso_locations table does not exist, skipping.")

    if not dry_run:
        session.commit()

    # Summary
    print()
    log.info("=" * 60)
    log.info("DSO CLASSIFIER SUMMARY")
    log.info("=" * 60)
    log.info("Total practices examined:  %s", f"{total:,}")
    log.info("  PE-backed:               %s", f"{counts['pe_backed']:,}")
    log.info("  DSO-affiliated:          %s", f"{counts['dso_affiliated']:,}")
    log.info("  Independent:             %s", f"{counts['independent']:,}")
    log.info("  Unknown:                 %s", f"{counts['unknown']:,}")
    if not dry_run:
        log.info("Changes saved to DB:       %s", f"{changes_made:,}")
        log_scrape_complete("dso_classifier", _t0, new_records=changes_made,
                            summary=f"Classifier: {changes_made} changes — PE:{counts['pe_backed']}, DSO:{counts['dso_affiliated']}, Indep:{counts['independent']}, Unk:{counts['unknown']}",
                            extra={"pe_backed": counts["pe_backed"], "dso_affiliated": counts["dso_affiliated"],
                                   "independent": counts["independent"], "unknown": counts["unknown"],
                                   "location_upgrades": location_upgrades})
    log.info("Location-match upgrades:   %s", f"{location_upgrades:,}")
    log.info("=" * 60)

    # Show PE-backed breakdown if any found
    if counts["pe_backed"] > 0 and not dry_run:
        print("\nPE-backed practices by DSO:")
        dso_counts = {}
        pe_practices = session.query(Practice).filter_by(ownership_status="pe_backed").all()
        for p in pe_practices:
            dso = p.affiliated_dso or "Unknown DSO"
            dso_counts[dso] = dso_counts.get(dso, 0) + 1
        for dso, count in sorted(dso_counts.items(), key=lambda x: -x[1]):
            sponsor = None
            for _, canonical, pe in KNOWN_DSOS:
                if canonical == dso:
                    sponsor = pe
                    break
            sponsor_str = f" ({sponsor})" if sponsor else ""
            print(f"  {dso}{sponsor_str}: {count}")

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify dental practices as DSO-affiliated or independent")
    parser.add_argument("--zip-filter", action="store_true",
                        help="Only classify practices in watched ZIP codes")
    parser.add_argument("--force", action="store_true",
                        help="Reclassify all practices, including already-classified ones")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show classifications without saving to database")
    args = parser.parse_args()
    run(zip_filter=args.zip_filter, force=args.force, dry_run=args.dry_run)
