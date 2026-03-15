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


# ── Entity Classification Constants ────────────────────────────────────────

NON_CLINICAL_KEYWORDS = [
    'LABORATORY', 'DENTAL LAB', ' LAB ', 'SUPPLY', 'PATTERSON', 'SCHEIN',
    'RESUME', 'STAFFING', 'BILLING SERVICE', 'MANAGEMENT GROUP',
    'CONSULTING', 'INSURANCE', 'DENTAL PLAN',
]

SPECIALIST_TAXONOMY_CODES = {
    '1223D0001X': 'Dental Public Health',
    '1223E0200X': 'Endodontics',
    # Note: '1223G0001X' is General Practice — NOT a specialist
    '1223P0106X': 'Oral and Maxillofacial Surgery',
    '1223P0221X': 'Pediatric Dentistry',
    '1223P0300X': 'Periodontics',
    '1223P0700X': 'Prosthodontics',
    '1223S0112X': 'Oral and Maxillofacial Surgery',
    '1223X0008X': 'Oral and Maxillofacial Radiology',
    '1223X0400X': 'Orthodontics and Dentofacial Orthopedics',
}
SPECIALIST_TAXONOMY_PREFIXES = ['1223D', '1223E', '1223P', '1223S', '1223X']

SPECIALIST_NAME_KEYWORDS = [
    'ORTHODONT', 'PERIODON', 'ENDODONT', 'ORAL SURG',
    'ORAL & MAXILLOFACIAL', 'MAXILLOFACIAL', 'PEDIATRIC DENT',
    'PEDODONT', 'PROSTHODONT', 'IMPLANT CENT',
]

CORPORATE_TERMS = [
    'HOLDINGS', 'MANAGEMENT', 'PARTNERS', 'GROUP', 'CAPITAL',
    'INVESTMENTS', 'EQUITY', 'VENTURES', 'ENTERPRISES',
]

FRANCHISE_SPECIALTY_SKIPLIST = {
    'general dentistry', 'orthodontics', 'endodontics',
    'oral surgery', 'periodontics', 'pedodontics',
    'prosthodontics', 'dental hygienist', 'dentist',
    'dentists office', "dentist's office", 'oral surgeon',
    'periodontist', 'endodontist', 'orthodontist',
    'pediatric dentist', 'pediatric dentistry',
}

GENERIC_BRAND_KEYWORDS = [
    'SMILE', 'SMILES', 'DENTAL CARE', 'FAMILY DENT', 'ADVANCED DENT',
    'PREMIER', 'GRAND DENTAL', 'VALLEY', 'PROFESSIONAL DENT',
    'COMPLETE DENT', 'PERFECT', 'IDEAL', 'MODERN DENT',
]

# Address abbreviations for enhanced normalization
ADDR_ABBREVS = {
    r"\bST\b": "STREET", r"\bDR\b": "DRIVE", r"\bAVE\b": "AVENUE",
    r"\bBLVD\b": "BOULEVARD", r"\bRD\b": "ROAD", r"\bLN\b": "LANE",
    r"\bCT\b": "COURT", r"\bPL\b": "PLACE", r"\bCIR\b": "CIRCLE",
    r"\bHWY\b": "HIGHWAY", r"\bPKY\b": "PARKWAY", r"\bPKWY\b": "PARKWAY",
    r"\bN\b": "NORTH", r"\bS\b": "SOUTH", r"\bE\b": "EAST", r"\bW\b": "WEST",
}


# ── Classification Logic ───────────────────────────────────────────────────


def classify_practice(practice_name, dba_name, entity_type=None,
                      franchise_name=None, parent_company=None):
    """Classify a practice based on its names, entity type, and corporate fields.
    Returns (status, dso_name, pe_sponsor, confidence, reason)."""
    if not practice_name and not dba_name:
        return "unknown", None, None, 0, "no name data"

    # Step -1: Franchise name is the strongest signal (Data Axle field)
    if franchise_name and franchise_name.strip():
        fn = franchise_name.strip().lower()
        # Skip generic specialty descriptions
        if fn not in ("general dentistry", "orthodontics", "endodontics",
                      "oral surgery", "periodontics", "pedodontics",
                      "prosthodontics", "dental hygienist"):
            sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
            for pattern, canonical_name, pe_sponsor in sorted_dsos:
                if pattern in fn:
                    status = "pe_backed" if pe_sponsor else "dso_affiliated"
                    return status, canonical_name, pe_sponsor, 95, f"Franchise match: {franchise_name} → {canonical_name}"
            # Franchise name doesn't match known DSOs but still indicates a chain
            return "dso_affiliated", franchise_name.strip(), None, 90, f"Franchise name: {franchise_name}"

    # Step -0.5: Parent company is a strong signal
    if parent_company and parent_company.strip():
        pc = parent_company.strip().lower()
        sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
        for pattern, canonical_name, pe_sponsor in sorted_dsos:
            if pattern in pc:
                status = "pe_backed" if pe_sponsor else "dso_affiliated"
                return status, canonical_name, pe_sponsor, 90, f"Parent company match: {parent_company} → {canonical_name}"
        # Parent company doesn't match known DSOs but still indicates corporate ownership
        return "dso_affiliated", parent_company.strip(), None, 85, f"Parent company: {parent_company}"

    names_to_check = []
    if practice_name:
        names_to_check.append(practice_name.lower())
    if dba_name:
        names_to_check.append(dba_name.lower())

    combined = " ".join(names_to_check)

    # Step 0: Entity-type-based classification for individuals
    # An individual NPI is almost certainly a solo practitioner UNLESS they
    # work under a known DSO name.
    if entity_type and entity_type.lower() == "individual":
        # First, check if this individual works for a known DSO
        sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
        for pattern, canonical_name, pe_sponsor in sorted_dsos:
            if pattern in combined:
                status = "pe_backed" if pe_sponsor else "dso_affiliated"
                return status, canonical_name, pe_sponsor, 95, f"Individual NPI — matches known DSO: {canonical_name}"
        # No DSO match → solo practitioner
        return "independent", None, None, 85, "Individual NPI — solo practitioner"

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

    # Step 4a: Organization with professional suffix → likely independent group
    # Professional entity suffixes (PC, PLLC, etc.) indicate a dentist-owned
    # practice entity rather than a corporate DSO structure.
    if entity_type and entity_type.lower() == "organization":
        _PROF_SUFFIX_RE = re.compile(
            r'\b(dmd\s+pc|dds\s+pc|pc|pllc|pa|psc|sc|llc)\s*[.,]?\s*$',
            re.IGNORECASE,
        )
        if practice_name and _PROF_SUFFIX_RE.search(practice_name):
            # Make sure there are no management/DSO keywords
            has_mgmt = any(kw in combined for kw in MGMT_KEYWORDS)
            if not has_mgmt:
                return ("independent", None, None, 65,
                        "Organization with professional suffix, no DSO signals")

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


# ── Batch DB helpers ──────────────────────────────────────────────────────


def _flush_updates(session, pending_updates, pending_changes):
    """Write pending classification updates to DB via raw SQL (fast).

    Using raw SQL UPDATE instead of ORM attribute mutation avoids the
    expire_on_commit penalty that makes ORM-based updates on 350k+ rows
    take hours instead of seconds.
    """
    from sqlalchemy import text

    for upd in pending_updates:
        fields = {k: v for k, v in upd.items() if k != "npi"}
        if not fields:
            continue
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        params = dict(fields)
        params["npi"] = upd["npi"]
        session.execute(
            text(f"UPDATE practices SET {set_clause} WHERE npi = :npi"),
            params,
        )

    if pending_changes:
        session.bulk_save_objects(pending_changes)

    session.commit()


# ── Entity Classification Engine (Phase 2) ─────────────────────────────────


def _normalize_address_for_grouping(addr):
    """Address normalization for entity classification grouping.

    Standardizes abbreviations but PRESERVES suite/unit numbers so that
    separate practices in the same building are not merged.
    """
    if not addr:
        return ""
    a = str(addr).upper().strip()
    # Remove periods, commas
    a = a.replace(".", "").replace(",", "")
    # Expand abbreviations (but keep suite/unit info)
    for pat, repl in ADDR_ABBREVS.items():
        a = re.sub(pat, repl, a)
    # Collapse whitespace
    a = re.sub(r"\s+", " ", a).strip()
    return a


def _precompute_address_groups(rows):
    """Group practice rows by (zip, normalized_address).

    Only counts providers as co-located (same practice) when:
    - At least one organization NPI exists at the address, OR
    - Multiple individual NPIs share a phone number or DBA name
    If ALL NPIs at the address are individuals with different phones/DBAs,
    they are likely separate practices sharing a building — each gets
    a group size of 1 for classification purposes.

    Returns: dict mapping (zip, normalized_addr, city) → [row_dicts]
    Also sets row["_effective_group_size"] for each row.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        addr = _normalize_address_for_grouping(r["address"])
        city = (r["city"] or "").upper().strip()
        key = (r["zip"], addr, city)
        groups[key].append(r)

    # Determine effective group sizes.
    # Count individual NPIs only — org NPIs are legal wrappers, not
    # additional providers. An address with 1 individual + 1 org = 1 provider.
    for key, members in groups.items():
        individual_count = sum(
            1 for m in members if m.get("entity_type") == "individual"
        )
        # Effective size = number of individual providers at address
        # (minimum 1 so org-only addresses still get classified)
        eff_size = max(individual_count, 1)
        for m in members:
            m["_effective_group_size"] = eff_size

    return groups


def _precompute_shared_eins(session, zip_codes):
    """Find EINs shared by 2+ practices in the given ZIPs.

    Returns: {ein: set_of_npis}
    """
    from sqlalchemy import text
    placeholders = ", ".join(f":z{i}" for i in range(len(zip_codes)))
    params = {f"z{i}": z for i, z in enumerate(zip_codes)}
    rows = session.execute(
        text(f"SELECT ein, GROUP_CONCAT(npi) as npis, COUNT(*) as cnt "
             f"FROM practices WHERE zip IN ({placeholders}) "
             f"AND ein IS NOT NULL AND ein != '' "
             f"GROUP BY ein HAVING COUNT(*) >= 2"),
        params,
    ).fetchall()
    result = {}
    for ein, npis_str, cnt in rows:
        result[ein] = set(npis_str.split(","))
    return result


def _precompute_shared_phones(practice_dicts):
    """Find phones shared across 3+ DIFFERENT normalized addresses.

    Same-address phone sharing is just a group practice (handled by Rules 5-7).
    Cross-address phone sharing across different ZIPs or buildings is a true
    corporate signal.

    Computed in Python using normalized addresses to avoid address string
    variations causing false "different addresses."
    Returns: {phone: set_of_npis}
    """
    from collections import defaultdict

    # Group by phone → set of (zip, normalized_addr)
    phone_addrs = defaultdict(lambda: {"npis": set(), "locations": set()})
    for r in practice_dicts:
        phone = r.get("phone") or ""
        if not phone or phone == "Not Available":
            continue
        norm_addr = _normalize_address_for_grouping(r["address"])
        city = (r["city"] or "").upper().strip()
        phone_addrs[phone]["npis"].add(r["npi"])
        phone_addrs[phone]["locations"].add((r["zip"], norm_addr, city))

    result = {}
    for phone, data in phone_addrs.items():
        n_locations = len(data["locations"])
        n_npis = len(data["npis"])
        # 3+ distinct locations, but not institutional (50+)
        if n_locations >= 3 and n_npis < 50:
            result[phone] = data["npis"]
    return result


def _check_family_signal(row, addr_group):
    """Check if this address has a family practice signal.

    Returns (has_signal, description_string) for dual-tagging on specialists.
    """
    from collections import Counter
    last_names = [
        r["provider_last_name"].upper().strip()
        for r in addr_group
        if r.get("provider_last_name")
        and r.get("entity_type") == "individual"
    ]
    if len(last_names) < 2:
        return False, ""
    name_counts = Counter(last_names)
    shared = {n: c for n, c in name_counts.items()
              if c >= 2 and n not in ("", "DDS", "DMD", "PC", "LTD", "INC", "LLC")}
    if shared:
        names_str = ", ".join(f"{n}({c}x)" for n, c in shared.items())
        addr_str = row.get("address", "")
        return True, f"family signal — {names_str} at {addr_str}"
    return False, ""


def _classify_single_entity(row, addr_group, shared_eins, shared_phones):
    """Classify a single practice into entity_classification.

    Returns (entity_classification, reasoning).
    Priority order: first match wins.
    """
    import datetime

    name_upper = (row.get("practice_name") or "").upper()
    dba_upper = (row.get("doing_business_as") or "").upper()
    combined = f"{name_upper} {dba_upper}"

    # ── Rule 1: Non-clinical ──
    for kw in NON_CLINICAL_KEYWORDS:
        if kw in combined:
            return ("non_clinical",
                    f"Non-clinical: name contains '{kw}'. "
                    f"Name: {row.get('practice_name')}")

    # ── Rule 2: Specialist ──
    taxonomy = row.get("taxonomy_code") or ""
    specialist_result = None
    if taxonomy:
        for prefix in SPECIALIST_TAXONOMY_PREFIXES:
            if taxonomy.startswith(prefix):
                spec_name = SPECIALIST_TAXONOMY_CODES.get(taxonomy, "Unknown Specialty")
                specialist_result = (
                    "specialist",
                    f"Specialist: taxonomy {taxonomy} ({spec_name}). "
                    f"Name: {row.get('practice_name')}")
                break
    if not specialist_result:
        for kw in SPECIALIST_NAME_KEYWORDS:
            if kw in name_upper:
                specialist_result = (
                    "specialist",
                    f"Specialist: name contains '{kw}'. "
                    f"Name: {row.get('practice_name')}. Taxonomy: {taxonomy or 'N/A'}")
                break

    if specialist_result:
        # Dual-tag: append family signal if applicable
        has_family, family_desc = _check_family_signal(row, addr_group)
        if has_family:
            return (specialist_result[0],
                    f"{specialist_result[1]}. Also: {family_desc}")
        return specialist_result

    # ── Rule 3: Known DSO national brand ──
    ownership = row.get("ownership_status")
    confidence = row.get("classification_confidence") or 0
    dso_name = row.get("affiliated_dso")
    if ownership in ("pe_backed", "dso_affiliated") and confidence >= 80:
        return ("dso_national",
                f"DSO National: status={ownership}, dso={dso_name}, "
                f"confidence={confidence}.")

    # Rule 3b: affiliated_dso matches known DSO even if ownership_status
    # wasn't updated (e.g., Pass 2 location match set affiliated_dso
    # but left ownership_status as 'independent')
    if dso_name and confidence >= 80:
        sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
        dso_lower = dso_name.lower()
        for pattern, canonical, pe_sponsor in sorted_dsos:
            if pattern in dso_lower or dso_lower in pattern:
                return ("dso_national",
                        f"DSO National: affiliated_dso='{dso_name}' matches "
                        f"known DSO '{canonical}', confidence={confidence}. "
                        f"(ownership_status={ownership} not updated by location match)")

    # ── Rule 4: Corporate signals (aggressive for Data Axle enriched) ──
    parent_co = row.get("parent_company") or ""
    franchise = row.get("franchise_name") or ""
    loc_type = row.get("location_type") or ""
    ein = row.get("ein") or ""
    phone = row.get("phone") or ""
    is_data_axle = row.get("data_axle_import_date") is not None
    existing_reasoning = row.get("classification_reasoning") or ""

    # 4a: parent_company fuzzy-matches known DSO → dso_national
    if parent_co:
        pc_lower = parent_co.lower()
        sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
        for pattern, canonical, pe_sponsor in sorted_dsos:
            if pattern in pc_lower:
                return ("dso_national",
                        f"DSO National: parent_company='{parent_co}' "
                        f"matches known DSO '{canonical}'.")
        # Try fuzzy match
        try:
            from rapidfuzz import fuzz
            for pattern, canonical, pe_sponsor in sorted_dsos:
                if fuzz.token_sort_ratio(pc_lower, canonical.lower()) >= 80:
                    return ("dso_national",
                            f"DSO National: parent_company='{parent_co}' "
                            f"fuzzy-matches known DSO '{canonical}'.")
        except ImportError:
            pass

        # 4b: parent_company with corporate terms → dso_regional
        pc_upper = parent_co.upper()
        for term in CORPORATE_TERMS:
            if term in pc_upper:
                return ("dso_regional",
                        f"DSO Regional: parent_company='{parent_co}' "
                        f"contains corporate term '{term}'.")

        # parent_company populated but didn't match anything above
        # Still a corporate signal for Data Axle enriched practices
        if is_data_axle:
            return ("dso_regional",
                    f"DSO Regional: parent_company='{parent_co}' "
                    f"(unrecognized corporate parent).")

    # 4c: Shared EIN with 2+ practices → dso_regional
    if ein and ein in shared_eins:
        peer_npis = shared_eins[ein]
        return ("dso_regional",
                f"DSO Regional: EIN={ein} shared with {len(peer_npis)} practices.")

    # 4d: franchise_name is a real franchise → dso_regional
    if franchise:
        fn_lower = franchise.strip().lower()
        if fn_lower not in FRANCHISE_SPECIALTY_SKIPLIST:
            # Check if it matches a known DSO
            sorted_dsos = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)
            for pattern, canonical, pe_sponsor in sorted_dsos:
                if pattern in fn_lower:
                    return ("dso_national",
                            f"DSO National: franchise_name='{franchise}' "
                            f"matches known DSO '{canonical}'.")
            return ("dso_regional",
                    f"DSO Regional: franchise_name='{franchise}' "
                    f"(not a specialty description).")

    # 4e: location_type = branch/subsidiary → dso_regional
    if loc_type.lower() in ("branch", "subsidiary"):
        return ("dso_regional",
                f"DSO Regional: location_type='{loc_type}'.")

    # 4f: Existing stealth DSO signals from Data Axle import
    if is_data_axle and existing_reasoning:
        reason_lower = existing_reasoning.lower()
        stealth_triggers = [
            "stealth dso", "corporate keyword", "corporate_parent",
            "ein_cluster", "shared_contact", "shared_phone",
        ]
        for trigger in stealth_triggers:
            if trigger in reason_lower:
                return ("dso_regional",
                        f"DSO Regional: Data Axle stealth signal detected "
                        f"('{trigger}' in classification_reasoning).")

    # 4g: Shared phone with 3-49 practices → dso_regional
    if phone and phone in shared_phones:
        peer_npis = shared_phones[phone]
        return ("dso_regional",
                f"DSO Regional: phone={phone} shared with "
                f"{len(peer_npis)} practices.")

    # ── Rule 5: Family practice ──
    providers_at_addr = row.get("_effective_group_size", len(addr_group))
    if providers_at_addr >= 2:
        has_family, family_desc = _check_family_signal(row, addr_group)
        if has_family:
            return ("family_practice",
                    f"Family practice: {providers_at_addr} providers at address, "
                    f"{family_desc}.")

    # ── Rule 6: Large group (4+ providers) ──
    if providers_at_addr >= 4:
        is_generic = any(kw in name_upper for kw in GENERIC_BRAND_KEYWORDS)
        if is_generic and providers_at_addr >= 5:
            return ("dso_regional",
                    f"DSO Regional: generic brand + {providers_at_addr} providers. "
                    f"Name: {row.get('practice_name')}.")
        return ("large_group",
                f"Large group: {providers_at_addr} providers at address. "
                f"Name: {row.get('practice_name')}.")

    # ── Rule 7: Small group (2-3 providers, different names) ──
    if providers_at_addr in (2, 3):
        return ("small_group",
                f"Small group: {providers_at_addr} providers at address. "
                f"Name: {row.get('practice_name')}.")

    # ── Rule 8: Solo classifications ──
    emp_count = row.get("employee_count")
    revenue = row.get("estimated_revenue")
    year_est = row.get("year_established")
    website = row.get("website") or ""

    # 8a: Solo high-volume
    if (emp_count and emp_count >= 5) or (revenue and revenue >= 800000):
        vol_parts = []
        if emp_count:
            vol_parts.append(f"employees={emp_count}")
        if revenue:
            vol_parts.append(f"revenue=${revenue:,.0f}")
        return ("solo_high_volume",
                f"Solo high-volume: {', '.join(vol_parts)}. "
                f"Name: {row.get('practice_name')}.")

    # 8b: Solo inactive
    has_no_contact = (
        (not phone or phone in ("Not Available", ""))
        and not website
    )
    if has_no_contact:
        return ("solo_inactive",
                f"Solo inactive: no phone and no website. "
                f"Name: {row.get('practice_name')}.")

    # 8c: Solo established (20+ years)
    current_year = datetime.datetime.now().year
    if year_est and (current_year - year_est) >= 20:
        age = current_year - year_est
        return ("solo_established",
                f"Solo established: {age} years (est. {year_est}). "
                f"Name: {row.get('practice_name')}.")

    # 8d: Solo new (< 10 years)
    if year_est and (current_year - year_est) < 10:
        return ("solo_new",
                f"Solo new: est. {year_est} ({current_year - year_est} years). "
                f"Name: {row.get('practice_name')}.")

    # 8e: Default solo
    return ("solo_established",
            f"Solo practice (default): limited enrichment data. "
            f"Name: {row.get('practice_name')}.")


def classify_entity_types(session, zip_codes=None, force=False, dry_run=False):
    """Second-pass classification: assigns entity_classification to practices.

    Runs AFTER the existing DSO classifier. Does NOT modify ownership_status.
    entity_classification is an additional layer providing fine-grained types.

    Args:
        session: SQLAlchemy session
        zip_codes: list of ZIPs to classify. If None, uses all watched ZIPs.
        force: reclassify even if entity_classification already set.
        dry_run: compute classifications without writing to DB.

    Returns: dict with classification counts.
    """
    from sqlalchemy import text
    from collections import Counter

    # Load watched ZIPs if none provided
    if zip_codes is None:
        watched = session.query(WatchedZip.zip_code).all()
        zip_codes = [z[0] for z in watched]

    log.info("=" * 60)
    log.info("ENTITY CLASSIFICATION (Pass 3) — %d ZIPs", len(zip_codes))
    log.info("=" * 60)

    # Pre-compute shared EIN lookup (phone computed after loading practices)
    shared_eins = _precompute_shared_eins(session, zip_codes)

    # Load all practices in watched ZIPs
    placeholders = ", ".join(f":z{i}" for i in range(len(zip_codes)))
    params = {f"z{i}": z for i, z in enumerate(zip_codes)}

    force_clause = "" if force else " AND entity_classification IS NULL"

    rows = session.execute(
        text(f"SELECT npi, practice_name, doing_business_as, entity_type, "
             f"address, city, zip, phone, taxonomy_code, "
             f"ownership_status, affiliated_dso, affiliated_pe_sponsor, "
             f"classification_confidence, classification_reasoning, "
             f"provider_last_name, "
             f"parent_company, ein, franchise_name, location_type, "
             f"data_axle_import_date, employee_count, year_established, "
             f"estimated_revenue, website "
             f"FROM practices "
             f"WHERE zip IN ({placeholders}){force_clause}"),
        params,
    ).fetchall()

    total = len(rows)
    if total == 0:
        log.info("No practices to classify.")
        return {}

    log.info("Classifying %d practices...", total)

    # Convert to list of dicts for easier access
    col_names = [
        "npi", "practice_name", "doing_business_as", "entity_type",
        "address", "city", "zip", "phone", "taxonomy_code",
        "ownership_status", "affiliated_dso", "affiliated_pe_sponsor",
        "classification_confidence", "classification_reasoning",
        "provider_last_name",
        "parent_company", "ein", "franchise_name", "location_type",
        "data_axle_import_date", "employee_count", "year_established",
        "estimated_revenue", "website",
    ]
    practice_dicts = [dict(zip(col_names, r)) for r in rows]

    # Pre-compute shared phones using normalized addresses
    shared_phones = _precompute_shared_phones(practice_dicts)
    log.info("Pre-computed: %d shared EINs, %d shared phones",
             len(shared_eins), len(shared_phones))

    # Build address groups
    addr_groups = _precompute_address_groups(practice_dicts)
    log.info("Address groups: %d unique locations from %d practices",
             len(addr_groups), total)

    # Classify each practice
    counts = Counter()
    pending_updates = []
    BATCH_SIZE = 5_000

    for i, prac in enumerate(practice_dicts):
        if (i + 1) % BATCH_SIZE == 0:
            log.info("  Classified %dk / %dk...", (i + 1) // 1000, total // 1000)
            if not dry_run and pending_updates:
                _flush_updates(session, pending_updates, [])
                pending_updates = []

        # Find this practice's address group
        addr_key = (
            prac["zip"],
            _normalize_address_for_grouping(prac["address"]),
            (prac["city"] or "").upper().strip(),
        )
        group = addr_groups.get(addr_key, [prac])

        classification, reasoning = _classify_single_entity(
            prac, group, shared_eins, shared_phones
        )

        counts[classification] += 1

        if not dry_run:
            pending_updates.append({
                "npi": prac["npi"],
                "entity_classification": classification,
                "classification_reasoning": reasoning,
            })

    # Flush remaining
    if not dry_run and pending_updates:
        _flush_updates(session, pending_updates, [])

    # Summary
    log.info("=" * 60)
    log.info("ENTITY CLASSIFICATION SUMMARY")
    log.info("=" * 60)
    for cls, cnt in counts.most_common():
        pct = cnt / total * 100
        log.info("  %-25s %6d  (%5.1f%%)", cls or "NULL", cnt, pct)
    log.info("  %-25s %6d", "TOTAL", total)

    # ── Buyability score adjustments based on entity classification ──
    if not dry_run:
        adjust_buyability_for_classification(session, zip_codes)

    return dict(counts)


def adjust_buyability_for_classification(session, zip_codes=None):
    """Adjust buyability scores for family practices and multi-ZIP entities.

    Applies ADDITIVE modifiers to existing buyability_score:
    - family_practice: -20 points (internal succession likely)
    - multi-ZIP presence (3+ ZIPs): -15 points (likely a chain)

    Only adjusts practices that have a buyability_score (Data Axle enriched).
    """
    from sqlalchemy import text

    if zip_codes is None:
        watched = session.query(WatchedZip.zip_code).all()
        zip_codes = [z[0] for z in watched]

    placeholders = ", ".join(f":z{i}" for i in range(len(zip_codes)))
    params = {f"z{i}": z for i, z in enumerate(zip_codes)}

    # ── Family practice penalty (-20) ──
    result = session.execute(
        text(f"UPDATE practices SET "
             f"buyability_score = MAX(0, buyability_score - 20), "
             f"classification_reasoning = COALESCE(classification_reasoning, '') || "
             f"' | Buyability -20: Family practice detected, shared last name at address suggests internal succession' "
             f"WHERE zip IN ({placeholders}) "
             f"AND entity_classification = 'family_practice' "
             f"AND buyability_score IS NOT NULL "
             f"AND buyability_score > 0 "
             f"AND classification_reasoning NOT LIKE '%Buyability -20: Family practice%'"),
        params,
    )
    family_adjusted = result.rowcount
    log.info("Buyability adjusted: %d family practices (-20 points)", family_adjusted)

    # ── Multi-ZIP presence penalty (-15) ──
    # Find practice names appearing in 3+ watched ZIPs
    multi_zip_names = session.execute(
        text(f"SELECT practice_name, COUNT(DISTINCT zip) as zip_count "
             f"FROM practices "
             f"WHERE zip IN ({placeholders}) "
             f"AND practice_name IS NOT NULL AND practice_name != '' "
             f"GROUP BY practice_name "
             f"HAVING COUNT(DISTINCT zip) >= 3"),
        params,
    ).fetchall()

    multi_zip_adjusted = 0
    for name, zip_count in multi_zip_names:
        result = session.execute(
            text(f"UPDATE practices SET "
                 f"buyability_score = MAX(0, buyability_score - 15), "
                 f"classification_reasoning = COALESCE(classification_reasoning, '') || "
                 f"' | Buyability -15: Multi-location entity, appears in ' || :zip_count || ' ZIP codes' "
                 f"WHERE zip IN ({placeholders}) "
                 f"AND practice_name = :pname "
                 f"AND buyability_score IS NOT NULL "
                 f"AND buyability_score > 0 "
                 f"AND classification_reasoning NOT LIKE '%Buyability -15: Multi-location%'"),
            {**params, "pname": name, "zip_count": str(zip_count)},
        )
        multi_zip_adjusted += result.rowcount

    # Also check shared EINs across 3+ ZIPs
    multi_zip_eins = session.execute(
        text(f"SELECT ein, COUNT(DISTINCT zip) as zip_count "
             f"FROM practices "
             f"WHERE zip IN ({placeholders}) "
             f"AND ein IS NOT NULL AND ein != '' "
             f"GROUP BY ein "
             f"HAVING COUNT(DISTINCT zip) >= 3"),
        params,
    ).fetchall()

    for ein, zip_count in multi_zip_eins:
        result = session.execute(
            text(f"UPDATE practices SET "
                 f"buyability_score = MAX(0, buyability_score - 15), "
                 f"classification_reasoning = COALESCE(classification_reasoning, '') || "
                 f"' | Buyability -15: Multi-location entity (EIN), appears in ' || :zip_count || ' ZIP codes' "
                 f"WHERE zip IN ({placeholders}) "
                 f"AND ein = :ein_val "
                 f"AND buyability_score IS NOT NULL "
                 f"AND buyability_score > 0 "
                 f"AND classification_reasoning NOT LIKE '%Buyability -15: Multi-location%'"),
            {**params, "ein_val": ein, "zip_count": str(zip_count)},
        )
        multi_zip_adjusted += result.rowcount

    log.info("Buyability adjusted: %d multi-ZIP entities (-15 points)", multi_zip_adjusted)
    session.commit()


def verify_entity_classification(session, zip_codes=None):
    """Print comprehensive verification report for entity classification."""
    from sqlalchemy import text

    if zip_codes is None:
        watched = session.query(WatchedZip.zip_code).all()
        zip_codes = [z[0] for z in watched]

    placeholders = ", ".join(f":z{i}" for i in range(len(zip_codes)))
    params = {f"z{i}": z for i, z in enumerate(zip_codes)}

    print("\n" + "=" * 70)
    print("ENTITY CLASSIFICATION VERIFICATION REPORT")
    print("=" * 70)

    # 1. Full distribution
    print("\n── 1. Full Classification Distribution (all watched ZIPs) ──")
    rows = session.execute(
        text(f"SELECT entity_classification, COUNT(*) as cnt "
             f"FROM practices WHERE zip IN ({placeholders}) "
             f"GROUP BY entity_classification ORDER BY cnt DESC"),
        params,
    ).fetchall()
    total = sum(r[1] for r in rows)
    print(f"{'Classification':<25} {'Count':>8} {'Pct':>7}")
    print("-" * 42)
    for cls, cnt in rows:
        pct = cnt / total * 100
        print(f"{(cls or 'NULL'):<25} {cnt:>8,} {pct:>6.1f}%")
    print(f"{'TOTAL':<25} {total:>8,}")

    # 2. Data Axle enriched distribution
    print("\n── 2. Data Axle Enriched Practices Distribution ──")
    rows = session.execute(
        text(f"SELECT entity_classification, COUNT(*) as cnt "
             f"FROM practices WHERE zip IN ({placeholders}) "
             f"AND data_axle_import_date IS NOT NULL "
             f"GROUP BY entity_classification ORDER BY cnt DESC"),
        params,
    ).fetchall()
    da_total = sum(r[1] for r in rows)
    print(f"{'Classification':<25} {'Count':>8} {'Pct':>7}")
    print("-" * 42)
    for cls, cnt in rows:
        pct = cnt / da_total * 100 if da_total else 0
        print(f"{(cls or 'NULL'):<25} {cnt:>8,} {pct:>6.1f}%")
    print(f"{'TOTAL':<25} {da_total:>8,}")

    solo_count = sum(cnt for cls, cnt in rows
                     if cls and cls.startswith("solo_"))
    solo_pct = solo_count / da_total * 100 if da_total else 0
    if solo_pct > 90:
        print(f"\n⚠️  WARNING: {solo_pct:.1f}% of enriched practices are solo "
              f"categories. Corporate signal detection may need review.")

    # 3. Data Axle corporate signal breakdown
    print("\n── 3. Data Axle Corporate Signal Usage ──")
    rows = session.execute(
        text(f"SELECT "
             f"SUM(CASE WHEN classification_reasoning LIKE '%parent_company%' THEN 1 ELSE 0 END) as parent, "
             f"SUM(CASE WHEN classification_reasoning LIKE '%EIN=%' THEN 1 ELSE 0 END) as ein, "
             f"SUM(CASE WHEN classification_reasoning LIKE '%franchise_name%' THEN 1 ELSE 0 END) as franchise, "
             f"SUM(CASE WHEN classification_reasoning LIKE '%location_type%' THEN 1 ELSE 0 END) as loc_type, "
             f"SUM(CASE WHEN classification_reasoning LIKE '%stealth%' THEN 1 ELSE 0 END) as stealth, "
             f"SUM(CASE WHEN classification_reasoning LIKE '%phone=%' THEN 1 ELSE 0 END) as phone "
             f"FROM practices "
             f"WHERE zip IN ({placeholders}) "
             f"AND data_axle_import_date IS NOT NULL "
             f"AND entity_classification IN ('dso_national', 'dso_regional')"),
        params,
    ).fetchall()
    if rows:
        r = rows[0]
        print(f"  parent_company matches:   {r[0] or 0}")
        print(f"  EIN cluster matches:      {r[1] or 0}")
        print(f"  franchise_name matches:   {r[2] or 0}")
        print(f"  location_type matches:    {r[3] or 0}")
        print(f"  stealth DSO signals:      {r[4] or 0}")
        print(f"  shared phone matches:     {r[5] or 0}")

    # Raw corporate signal counts
    print("\n── 3b. Raw Corporate Signal Availability (Data Axle enriched) ──")
    rows = session.execute(
        text(f"SELECT "
             f"SUM(CASE WHEN parent_company IS NOT NULL AND parent_company != '' THEN 1 ELSE 0 END) as has_parent, "
             f"SUM(CASE WHEN ein IS NOT NULL AND ein != '' THEN 1 ELSE 0 END) as has_ein, "
             f"SUM(CASE WHEN franchise_name IS NOT NULL AND franchise_name != '' THEN 1 ELSE 0 END) as has_franchise, "
             f"SUM(CASE WHEN location_type IN ('branch', 'subsidiary') THEN 1 ELSE 0 END) as is_branch "
             f"FROM practices "
             f"WHERE zip IN ({placeholders}) "
             f"AND data_axle_import_date IS NOT NULL"),
        params,
    ).fetchall()
    if rows:
        r = rows[0]
        print(f"  Practices with parent_company:  {r[0] or 0}")
        print(f"  Practices with EIN:             {r[1] or 0}")
        print(f"  Practices with franchise_name:  {r[2] or 0}")
        print(f"  Practices as branch/subsidiary: {r[3] or 0}")

    # 4. Homer Glen (60491) specialists (Booth family)
    print("\n── 4. Homer Glen (60491) Specialist Audit ──")
    rows = session.execute(
        text("SELECT practice_name, taxonomy_code, entity_classification, "
             "classification_reasoning FROM practices "
             "WHERE zip = '60491' AND entity_classification = 'specialist' "
             "ORDER BY practice_name"),
        {},
    ).fetchall()
    for name, tax, cls, reason in rows:
        print(f"  {name:<45} {tax or 'N/A':<15} {reason[:80]}")

    # 5. Lemont (60439) family practices (Groselak)
    print("\n── 5. Lemont (60439) Family Practice Audit ──")
    rows = session.execute(
        text("SELECT practice_name, provider_last_name, entity_classification, "
             "classification_reasoning FROM practices "
             "WHERE zip = '60439' AND entity_classification = 'family_practice' "
             "ORDER BY provider_last_name"),
        {},
    ).fetchall()
    for name, last, cls, reason in rows:
        print(f"  {name:<40} {last or 'N/A':<15} {reason[:80]}")

    # Also check Homer Glen for family practices
    print("\n── 5b. Homer Glen (60491) Family Practice Audit ──")
    rows = session.execute(
        text("SELECT practice_name, provider_last_name, entity_classification, "
             "classification_reasoning FROM practices "
             "WHERE zip = '60491' AND entity_classification = 'family_practice' "
             "ORDER BY provider_last_name"),
        {},
    ).fetchall()
    if rows:
        for name, last, cls, reason in rows:
            print(f"  {name:<40} {last or 'N/A':<15} {reason[:80]}")
    else:
        print("  (none — Booth family classified as specialist with family dual-tag)")

    # 6. Lockport (60441) DSO verification
    print("\n── 6. Lockport (60441) DSO Verification ──")
    rows = session.execute(
        text("SELECT practice_name, affiliated_dso, entity_classification, "
             "classification_reasoning FROM practices "
             "WHERE zip = '60441' AND entity_classification IN ('dso_national', 'dso_regional') "
             "ORDER BY practice_name"),
        {},
    ).fetchall()
    for name, dso, cls, reason in rows:
        print(f"  {name:<40} {dso or 'N/A':<20} {cls:<15} {reason[:60]}")

    # 7. NULL count
    print("\n── 7. NULL Entity Classification Count ──")
    rows = session.execute(
        text(f"SELECT COUNT(*) FROM practices "
             f"WHERE zip IN ({placeholders}) AND entity_classification IS NULL"),
        params,
    ).fetchall()
    null_count = rows[0][0]
    print(f"  Practices with NULL entity_classification: {null_count}")
    if null_count > 0:
        print(f"  ({null_count / total * 100:.1f}% of total)")

    print("\n" + "=" * 70)


# ── Main ────────────────────────────────────────────────────────────────────


def run(zip_filter=False, force=False, dry_run=False):
    _t0 = log_scrape_start("dso_classifier")
    log.info("=" * 60)
    log.info("DSO Classifier starting (zip_filter=%s, force=%s, dry_run=%s)",
             zip_filter, force, dry_run)
    log.info("=" * 60)

    init_db()
    session = get_session()

    # ── Load practices as lightweight tuples instead of ORM objects ──
    # Loading 350k+ ORM objects into the session causes catastrophic
    # performance: every session.commit() expires all objects (default
    # expire_on_commit=True), and subsequent attribute access triggers
    # individual SELECT per row, turning a 30-second job into hours.
    from sqlalchemy import text

    where_clauses = []
    params = {}

    if not force:
        where_clauses.append(
            "(ownership_status = 'unknown' OR ownership_status IS NULL)"
        )

    if zip_filter:
        watched = session.query(WatchedZip.zip_code).all()
        watched_zips = [z[0] for z in watched]
        placeholders = ", ".join(f":z{i}" for i in range(len(watched_zips)))
        where_clauses.append(f"zip IN ({placeholders})")
        for i, z in enumerate(watched_zips):
            params[f"z{i}"] = z
        log.info("Filtering to %d watched ZIP codes", len(watched_zips))

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = session.execute(
        text(f"SELECT npi, practice_name, doing_business_as, entity_type, "
             f"ownership_status, franchise_name, parent_company"
             f" FROM practices{where_sql}"),
        params,
    ).fetchall()
    total = len(rows)

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
    pending_updates = []
    BATCH_SIZE = 10_000

    for i, row in enumerate(rows):
        if (i + 1) % BATCH_SIZE == 0:
            log.info("  Classified %dk / %dk...", (i + 1) // 1000, total // 1000)
            if not dry_run and pending_updates:
                _flush_updates(session, pending_updates, pending_changes)
                pending_updates = []
                pending_changes = []

        npi, practice_name, dba_name, entity_type, old_status, franchise, parent_co = row

        status, dso_name, pe_sponsor, confidence, reason = classify_practice(
            practice_name, dba_name, entity_type=entity_type,
            franchise_name=franchise, parent_company=parent_co,
        )

        counts[status] += 1

        if dry_run:
            continue

        # Build update dict for this practice
        update = {
            "npi": npi,
            "classification_confidence": confidence,
            "classification_reasoning": reason,
        }

        if status != old_status:
            update["ownership_status"] = status
            if dso_name:
                update["affiliated_dso"] = dso_name
            if pe_sponsor:
                update["affiliated_pe_sponsor"] = pe_sponsor

            # Queue change log for new acquisitions
            if old_status in ("unknown", None) and status in ("pe_backed", "dso_affiliated"):
                pending_changes.append(PracticeChange(
                    npi=npi,
                    change_date=today,
                    field_changed="ownership_status",
                    old_value=old_status or "unknown",
                    new_value=status,
                    change_type="acquisition",
                    notes=f"Auto-classified: {reason}"
                    + (f" — DSO: {dso_name}" if dso_name else ""),
                ))

            changes_made += 1

        pending_updates.append(update)

    # Flush remaining
    if not dry_run and pending_updates:
        _flush_updates(session, pending_updates, pending_changes)

    # ── Pass 2: Location-based matching against dso_locations ──
    # Only load practices in ZIPs that have DSO locations (much smaller set)
    location_upgrades = 0
    if table_exists("dso_locations"):
        loc_count = session.query(DSOLocation).count()
        if loc_count > 0:
            log.info("Pass 2: Matching against %d DSO locations...", loc_count)
            dso_zips = [z[0] for z in session.query(DSOLocation.zip).distinct().all() if z[0]]
            practices_for_loc = session.query(Practice).filter(
                Practice.zip.in_(dso_zips)
            ).all() if (not dry_run and dso_zips) else []
            log.info("Pass 2: %d practices in DSO-location ZIPs", len(practices_for_loc))
            location_upgrades = _location_match_pass(
                session, practices_for_loc, counts, dry_run, force, today
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

    # ── Pass 3: Entity type classification ──
    if zip_filter:
        log.info("Pass 3: Entity type classification for watched ZIPs...")
        entity_counts = classify_entity_types(session, force=force, dry_run=dry_run)
    else:
        log.info("Pass 3: Skipping entity classification (use --zip-filter to enable)")

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify dental practices as DSO-affiliated or independent")
    parser.add_argument("--zip-filter", action="store_true",
                        help="Only classify practices in watched ZIP codes")
    parser.add_argument("--force", action="store_true",
                        help="Reclassify all practices, including already-classified ones")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show classifications without saving to database")
    parser.add_argument("--entity-types-only", action="store_true",
                        help="Only run entity type classification (Pass 3)")
    parser.add_argument("--verify", action="store_true",
                        help="Print verification report for entity classification")
    args = parser.parse_args()

    if args.verify:
        init_db()
        session = get_session()
        verify_entity_classification(session)
        session.close()
    elif args.entity_types_only:
        init_db()
        session = get_session()
        classify_entity_types(session, force=args.force, dry_run=args.dry_run)
        session.close()
    else:
        run(zip_filter=args.zip_filter, force=args.force, dry_run=args.dry_run)
