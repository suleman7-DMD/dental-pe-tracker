"""
dedup_practice_locations.py — Canonical practice-location deduplication pipeline.

Collapses NPI rows from `practices` (NPI-2 orgs + NPI-1 individuals) into a
single `practice_locations` row per physical address.  The resulting table is
the source-of-truth for location-based counts (Job Market KPI, Market Intel
saturation, density maps) and is kept in sync with Supabase via full_replace.

Spec: /tmp/dedup_design.md  (Schema Architect deliverable, ULTRA-FIX dedup)

Usage:
    python3 scrapers/dedup_practice_locations.py
    python3 scrapers/dedup_practice_locations.py --dry-run
    python3 scrapers/dedup_practice_locations.py --watched-only   # default
    python3 scrapers/dedup_practice_locations.py --all-practices
"""

import argparse
import hashlib
import json
import re
import sys
import os
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Importable helpers (other agents import these)
# ---------------------------------------------------------------------------

_STREET_ABBREV = {
    "street": "st", "avenue": "ave", "boulevard": "blvd",
    "road": "rd", "drive": "dr", "lane": "ln", "court": "ct",
    "place": "pl", "parkway": "pkwy", "highway": "hwy",
    "circle": "cir", "square": "sq", "terrace": "ter",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}


def normalize_address(addr: str) -> str:
    """Canonical address normalizer. Used by all agents.

    Spec: /tmp/dedup_design.md §Address normalization.
    Order matters — apply in sequence:
      1. Strip whitespace
      2. Lowercase
      3. Remove apt/suite/unit/floor/room/bldg suffixes (incl. "#108", "Suite 200")
      4. Strip punctuation (commas, periods)
      5. Abbreviate street suffixes
      6. Collapse whitespace
    """
    if not addr:
        return ""
    a = addr.strip().lower()
    # Remove apt/suite/unit/floor/room/building/# suffixes (incl. "#108")
    a = re.sub(
        r"\b(?:apt|apartment|suite|ste|unit|fl|floor|rm|room|bldg|building)\s*\.?\s*[\w-]+",
        "", a
    )
    a = re.sub(r"#\s*[\w-]+", "", a)
    # Strip punctuation that varies (commas and periods only — don't strip hyphens)
    a = re.sub(r"[.,]", "", a)
    # Standardize street suffixes word-by-word
    parts = a.split()
    parts = [_STREET_ABBREV.get(p, p) for p in parts]
    a = " ".join(parts)
    # Collapse whitespace
    a = re.sub(r"\s+", " ", a).strip()
    return a


def location_id(normalized_address: str, zip_code: str) -> str:
    """Stable hash key for a location. sha1(addr|zip)[:16].

    Spec: /tmp/dedup_design.md §location_id.
    """
    raw = f"{normalized_address}|{(zip_code or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Specialist taxonomy detection
# ---------------------------------------------------------------------------

# GP / general dentist taxonomy codes — NOT specialist
_GP_TAXONOMY_PREFIXES = {"122300000X", "1223G0001X"}

# Specialist taxonomy CODE prefixes (4-char prefix match from NPPES spec)
_SPECIALIST_TAXONOMY_PREFIXES = {"1223D", "1223E", "1223P", "1223S", "1223X"}

# Keywords in practice names that indicate specialist
_SPECIALIST_NAME_KEYWORDS = [
    "ORTHODONT", "PERIODON", "ENDODONT", "ORAL SURG", "MAXILLOFACIAL",
    "PEDIATRIC DENT", "PEDODONT", "PROSTHODONT", "IMPLANT CENT",
]

# Keywords that indicate non-clinical entity
_NON_CLINICAL_KEYWORDS = [
    "LABORATORY", "DENTAL LAB", " LAB ", "SUPPLY", "BILLING",
    "STAFFING", "MANAGEMENT GROUP", "MANAGEMENT COMPANY",
    "MANAGEMENT SERVICES", "INSURANCE", "DENTURE CLINIC",
]
# These are unambiguous non-clinical even without context
_NON_CLINICAL_HARD = ["LABORATORY", " LAB ", "SUPPLY", "BILLING", "STAFFING"]


def _is_specialist_taxonomy(code: str) -> bool:
    """Return True if taxonomy code indicates specialist practice."""
    if not code:
        return False
    # Exact GP codes — not specialist
    if code in _GP_TAXONOMY_PREFIXES:
        return False
    # Check specialist prefix
    for prefix in _SPECIALIST_TAXONOMY_PREFIXES:
        if code.startswith(prefix):
            return True
    return False


def _is_specialist_name(name: str) -> bool:
    """Return True if practice name contains specialist keyword."""
    if not name:
        return False
    n = name.upper()
    return any(kw in n for kw in _SPECIALIST_NAME_KEYWORDS)


def _is_non_clinical_name(name: str) -> bool:
    """Return True if practice name indicates non-clinical entity."""
    if not name:
        return False
    n = name.upper()
    # Hard non-clinical keywords always match
    for kw in _NON_CLINICAL_HARD:
        if kw in n:
            # Exception: skip if name also contains dental keywords
            if not any(dk in n for dk in ["DENTAL", "ORTHODONT", "IMPLANT"]):
                return True
    # Ambiguous keywords only match if no dental keywords present
    for kw in _NON_CLINICAL_KEYWORDS:
        if kw in n and not any(dk in n for dk in ["DENTAL", "ORTHODONT", "IMPLANT"]):
            return True
    return False


# ---------------------------------------------------------------------------
# Name-pattern detection (individual NPI name formats)
# ---------------------------------------------------------------------------

def _is_person_name(name: str) -> bool:
    """Heuristic: return True if name looks like 'FIRSTNAME LASTNAME' only (no practice keywords)."""
    if not name:
        return True
    n = name.upper()
    practice_keywords = ["DENTAL", "DDS", "DMD", "DENTISTRY", "ORTHO",
                         "PERIO", "ENDO", "ORAL", "IMPLANT", "SMILE",
                         "CARE", "CLINIC", "CENTER", "PRACTICE", "GROUP",
                         "ASSOCIATES", "PC", "LLC", "PLLC", "P.C.", "P.L.L.C."]
    return not any(kw in n for kw in practice_keywords)


# ---------------------------------------------------------------------------
# Known national DSO brands (for entity classification)
# ---------------------------------------------------------------------------

_KNOWN_NATIONAL_DSOS = [
    "ASPEN DENTAL", "HEARTLAND DENTAL", "PACIFIC DENTAL",
    "WESTERN DENTAL", "AMERITAS", "SMILE BRANDS", "SMILE DIRECT",
    "AFFORDABLE CARE", "SMILEDIRECTCLUB", "BIRNER DENTAL",
    "GREAT EXPRESSIONS", "DENTAL DREAMS", "CLEAR CHOICE",
    "COAST DENTAL", "GENTLE DENTAL", "KOOL SMILES",
    "MY FAMILY DENTAL", "COMFORT DENTAL", "DENTAL WORKS",
    "MIDWEST DENTAL", "DENTALWORKS", "DENTISTRY FOR CHILDREN",
    "TEND DENTAL", "TEND STUDIO",
]


def _is_national_dso(name: str) -> bool:
    """Return True if practice name matches a known national DSO."""
    if not name:
        return False
    n = name.upper()
    return any(dso in n for dso in _KNOWN_NATIONAL_DSOS)


# ---------------------------------------------------------------------------
# Main dedup function
# ---------------------------------------------------------------------------

def derive_practice_locations(session, watched_only: bool = True, dry_run: bool = False):
    """Collapse practices NPI rows into one row per physical location.

    Steps:
    1. SELECT practices (optionally filtered to watched ZIPs)
    2. Group by (normalize_address, zip)
    3. For each group: elect name, count providers, compute flags
    4. Upsert into practice_locations

    Returns: (total_input_rows, total_locations, skipped_blank_addr)
    """
    from scrapers.database import get_engine

    sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))
    from scrapers.logger_config import get_logger

    log = get_logger("dedup_practice_locations")

    # ------------------------------------------------------------------
    # 1. Fetch practices rows
    # ------------------------------------------------------------------
    log.info("Fetching practices rows (watched_only=%s)...", watched_only)

    if watched_only:
        # Get watched ZIP codes first
        watched_zips_rows = session.execute(
            __import__("sqlalchemy").text("SELECT zip_code FROM watched_zips")
        ).fetchall()
        watched_zip_set = {r[0] for r in watched_zips_rows}
        log.info("Loaded %d watched ZIPs", len(watched_zip_set))
    else:
        watched_zip_set = None

    # Load dso_locations for residential detection check
    dso_loc_rows = session.execute(
        __import__("sqlalchemy").text(
            "SELECT LOWER(TRIM(address)) || '|' || COALESCE(TRIM(zip), '') as addr_key "
            "FROM dso_locations WHERE address IS NOT NULL"
        )
    ).fetchall()
    dso_address_set = {r[0] for r in dso_loc_rows}
    log.info("Loaded %d DSO location addresses for residential detection", len(dso_address_set))

    # Fetch all relevant practice rows
    # SQLite does not support binding a tuple with IN :param — must expand placeholders manually.
    _SQL_COLS = (
        "SELECT npi, practice_name, doing_business_as, entity_type, "
        "address, city, state, zip, phone, taxonomy_code, "
        "entity_classification, ownership_status, "
        "affiliated_dso, affiliated_pe_sponsor, buyability_score, "
        "classification_confidence, classification_reasoning, "
        "latitude, longitude, year_established, employee_count, "
        "estimated_revenue, data_axle_import_date, parent_company, "
        "ein, franchise_name, iusa_number, website, data_source, "
        "provider_last_name, updated_at, enumeration_date, location_type "
        "FROM practices"
    )
    if watched_zip_set:
        zip_list = sorted(watched_zip_set)
        placeholders = ",".join(f":z{i}" for i in range(len(zip_list)))
        params = {f"z{i}": z for i, z in enumerate(zip_list)}
        practices = session.execute(
            __import__("sqlalchemy").text(
                f"{_SQL_COLS} WHERE zip IN ({placeholders})"
            ),
            params
        ).fetchall()
    else:
        practices = session.execute(
            __import__("sqlalchemy").text(
                """SELECT npi, practice_name, doing_business_as, entity_type,
                          address, city, state, zip, phone, taxonomy_code,
                          entity_classification, ownership_status,
                          affiliated_dso, affiliated_pe_sponsor, buyability_score,
                          classification_confidence, classification_reasoning,
                          latitude, longitude, year_established, employee_count,
                          estimated_revenue, data_axle_import_date, parent_company,
                          ein, franchise_name, iusa_number, website, data_source,
                          provider_last_name, updated_at, enumeration_date, location_type
                   FROM practices"""
            )
        ).fetchall()

    total_input = len(practices)
    log.info("Loaded %d practice NPI rows", total_input)

    # Column index helpers (match SELECT order above)
    COL = {
        "npi": 0, "practice_name": 1, "doing_business_as": 2, "entity_type": 3,
        "address": 4, "city": 5, "state": 6, "zip": 7, "phone": 8,
        "taxonomy_code": 9, "entity_classification": 10, "ownership_status": 11,
        "affiliated_dso": 12, "affiliated_pe_sponsor": 13, "buyability_score": 14,
        "classification_confidence": 15, "classification_reasoning": 16,
        "latitude": 17, "longitude": 18, "year_established": 19,
        "employee_count": 20, "estimated_revenue": 21, "data_axle_import_date": 22,
        "parent_company": 23, "ein": 24, "franchise_name": 25,
        "iusa_number": 26, "website": 27, "data_source": 28,
        "provider_last_name": 29, "updated_at": 30, "enumeration_date": 31,
        "location_type": 32,
    }

    def get(row, col):
        return row[COL[col]]

    # ------------------------------------------------------------------
    # 2. Group by (normalized_address, zip)
    # ------------------------------------------------------------------
    groups = defaultdict(list)  # key -> [rows]
    skipped_blank = 0
    skipped_npis = []

    for row in practices:
        addr = get(row, "address") or ""
        zip_code = get(row, "zip") or ""
        npi = get(row, "npi") or ""

        if not addr.strip():
            skipped_blank += 1
            skipped_npis.append(npi)
            log.warning(
                "Skipping NPI %s (%s) — blank address (zip=%s)",
                npi, get(row, "practice_name") or "unnamed", zip_code
            )
            continue

        norm_addr = normalize_address(addr)
        if not norm_addr:
            skipped_blank += 1
            skipped_npis.append(npi)
            log.warning(
                "Skipping NPI %s (%s) — address normalized to empty string (raw=%r)",
                npi, get(row, "practice_name") or "unnamed", addr
            )
            continue

        key = (norm_addr, zip_code)
        groups[key].append(row)

    log.info(
        "Grouped %d input rows → %d unique address+zip combinations (%d skipped blank address)",
        total_input, len(groups), skipped_blank
    )

    if skipped_blank > 0:
        log.warning(
            "BLANK ADDRESS SUMMARY: %d NPI rows skipped. First 10 NPIs: %s",
            skipped_blank, skipped_npis[:10]
        )

    # ------------------------------------------------------------------
    # 2b. Cross-zip merge: NPPES sometimes has a typo zip on the org NPI.
    # Strategy: if two groups share the same normalized_address AND city
    # but different zips, AND one group has only an org row (no individuals)
    # while the other has only individual rows, merge the org into the
    # individuals group (which has the authoritative mailing zip).
    # Only merge when the city field on both groups matches.
    # ------------------------------------------------------------------
    # Build a lookup: norm_addr -> list of (norm_addr, zip) keys
    addr_to_keys = defaultdict(list)
    for (na, z) in list(groups.keys()):
        addr_to_keys[na].append((na, z))

    merge_count = 0
    for na, keys in addr_to_keys.items():
        if len(keys) < 2:
            continue
        # Check if any key is an org-only group
        for key_a in keys:
            rows_a = groups.get(key_a, [])
            if not rows_a:
                continue
            org_only_a = all((get(r, "entity_type") or "").lower() == "organization" for r in rows_a)
            if not org_only_a:
                continue
            # key_a is org-only — find a sibling key with individuals and same city
            city_a = (get(rows_a[0], "city") or "").strip().lower()
            for key_b in keys:
                if key_b == key_a:
                    continue
                rows_b = groups.get(key_b, [])
                if not rows_b:
                    continue
                city_b = (get(rows_b[0], "city") or "").strip().lower()
                if city_a and city_b and city_a == city_b:
                    # Merge rows_a (org) into rows_b (individuals)
                    log.info(
                        "Cross-zip merge: org NPI %s (zip=%s) → individuals group (zip=%s) [addr=%s]",
                        get(rows_a[0], "npi"), key_a[1], key_b[1], na
                    )
                    groups[key_b].extend(rows_a)
                    del groups[key_a]
                    merge_count += 1
                    break  # only merge once per org-only group

    if merge_count > 0:
        log.info("Cross-zip merge: %d org-only groups absorbed into matching sibling groups", merge_count)

    # ------------------------------------------------------------------
    # 3. For each group, build a practice_locations row
    # ------------------------------------------------------------------
    engine = get_engine()
    now = datetime.utcnow().isoformat()
    upserted = 0
    locations_built = []

    for (norm_addr, zip_code), rows in groups.items():
        loc_id = location_id(norm_addr, zip_code)

        # Separate org (NPI-2) and individual (NPI-1) rows
        org_rows = [r for r in rows if (get(r, "entity_type") or "").lower() == "organization"]
        ind_rows = [r for r in rows if (get(r, "entity_type") or "").lower() != "organization"]

        # ------ Practice name election (spec §Practice name election) ------
        if len(org_rows) == 1:
            name_row = org_rows[0]
            org_npi = get(name_row, "npi")
            primary_npi = org_npi
            has_org_npi = True
            elected_name = get(name_row, "practice_name") or get(name_row, "doing_business_as")
        elif len(org_rows) > 1:
            # Multiple orgs — pick most recently updated
            def _updated_key(r):
                v = get(r, "updated_at") or ""
                return str(v)
            name_row = max(org_rows, key=_updated_key)
            org_npi = get(name_row, "npi")
            primary_npi = org_npi
            has_org_npi = True
            elected_name = get(name_row, "practice_name") or get(name_row, "doing_business_as")
        else:
            # Zero org rows
            org_npi = None
            has_org_npi = False
            name_row = None

            # Try doing_business_as from any individual
            dba_candidates = [
                r for r in ind_rows
                if (get(r, "doing_business_as") or "").strip()
            ]
            if dba_candidates:
                elected_name = get(dba_candidates[0], "doing_business_as").strip()
                name_row = dba_candidates[0]
            else:
                # Try practice_name that looks like a business (not just "FIRSTNAME LASTNAME")
                biz_candidates = [
                    r for r in ind_rows
                    if (get(r, "practice_name") or "").strip()
                    and not _is_person_name(get(r, "practice_name") or "")
                ]
                if biz_candidates:
                    elected_name = get(biz_candidates[0], "practice_name").strip()
                    name_row = biz_candidates[0]
                else:
                    # Construct "{Lastname} Dental" from oldest NPI-1
                    def _enum_key(r):
                        v = get(r, "enumeration_date") or ""
                        return str(v)
                    oldest = min(ind_rows, key=_enum_key) if ind_rows else rows[0]
                    last_name = get(oldest, "provider_last_name") or ""
                    if not last_name:
                        # Fall back to first word of practice_name
                        pn = get(oldest, "practice_name") or ""
                        last_name = pn.split()[0] if pn.split() else "Unknown"
                    elected_name = f"{last_name.title()} Dental"
                    name_row = oldest

            # primary_npi = oldest NPI-1
            def _enum_key2(r):
                v = get(r, "enumeration_date") or ""
                return str(v)
            primary_npi = get(min(ind_rows, key=_enum_key2), "npi") if ind_rows else get(rows[0], "npi")

        # ------ Provider count: distinct NPI-1s ------
        provider_npis = list({get(r, "npi") for r in ind_rows})
        provider_count = len(provider_npis)

        # ------ Taxonomy codes ------
        all_taxonomies = list({
            get(r, "taxonomy_code")
            for r in rows
            if get(r, "taxonomy_code")
        })

        # ------ Specialist-only flag ------
        is_specialist_only = False
        if all_taxonomies:
            non_gp = [t for t in all_taxonomies if t not in _GP_TAXONOMY_PREFIXES]
            has_specialist = any(_is_specialist_taxonomy(t) for t in all_taxonomies)
            has_gp = any(t in _GP_TAXONOMY_PREFIXES for t in all_taxonomies)
            # Specialist-only: all taxonomies are specialist, no GP taxonomy present
            if has_specialist and not has_gp:
                is_specialist_only = True
        # Also check practice name for specialist signal
        if elected_name and _is_specialist_name(elected_name):
            is_specialist_only = True

        # ------ Coordinates: prefer org row, then any row with coords ------
        lat, lon = None, None
        coord_candidates = (org_rows or []) + ind_rows
        for r in coord_candidates:
            if get(r, "latitude") is not None and get(r, "longitude") is not None:
                lat = get(r, "latitude")
                lon = get(r, "longitude")
                break

        # ------ Data Axle enrichment ------
        data_axle_enriched = any(
            get(r, "data_axle_import_date") is not None for r in rows
        )

        # ------ Aggregate numeric fields (max employee/revenue, min year) ------
        year_established = None
        yrs = [get(r, "year_established") for r in rows if get(r, "year_established") is not None]
        if yrs:
            year_established = min(yrs)  # oldest founding

        employee_count = None
        emps = [get(r, "employee_count") for r in rows if get(r, "employee_count") is not None]
        if emps:
            employee_count = max(emps)

        estimated_revenue = None
        revs = [get(r, "estimated_revenue") for r in rows if get(r, "estimated_revenue") is not None]
        if revs:
            estimated_revenue = max(revs)

        # ------ Data sources and geography from representative rows ------
        sources = list({
            get(r, "data_source") for r in rows if get(r, "data_source")
        })
        data_sources = ",".join(sorted(sources))

        # Use org row or first row for city/state
        ref_row = org_rows[0] if org_rows else rows[0]
        city = get(ref_row, "city")
        state = get(ref_row, "state")
        phone = next((get(r, "phone") for r in rows if get(r, "phone")), None)
        website = next((get(r, "website") for r in rows if get(r, "website")), None)
        doing_business_as = next((get(r, "doing_business_as") for r in rows if get(r, "doing_business_as")), None)

        # Carry forward corporate linkage from any row that has them
        parent_company = next((get(r, "parent_company") for r in rows if get(r, "parent_company")), None)
        ein = next((get(r, "ein") for r in rows if get(r, "ein")), None)
        franchise_name = next((get(r, "franchise_name") for r in rows if get(r, "franchise_name")), None)
        iusa_number = next((get(r, "iusa_number") for r in rows if get(r, "iusa_number")), None)

        # ------ Residential detection (spec §Residential detection) ------
        # A location is likely residential iff ALL of:
        # 1. has_org_npi = FALSE
        # 2. provider_count <= 1
        # 3. website is null/empty
        # 4. employee_count is null or <= 1
        # 5. not in dso_locations
        addr_key = norm_addr + "|" + zip_code
        in_dso_locations = addr_key in dso_address_set

        is_likely_residential = (
            not has_org_npi
            and provider_count <= 1
            and not (website or "").strip()
            and (employee_count is None or employee_count <= 1)
            and not in_dso_locations
        )

        # ------ Entity classification: carry forward most authoritative ------
        # NPI-2 first, then any row with entity_classification, else None
        # Classifier-fixer will recompute; this seeds initial data.
        ec = None
        ec_confidence = None
        ec_reasoning = None
        ownership_st = None
        affiliated_dso_val = None
        affiliated_pe_val = None
        buyability = None

        if org_rows:
            ec = get(org_rows[0], "entity_classification")
            ec_confidence = get(org_rows[0], "classification_confidence")
            ec_reasoning = get(org_rows[0], "classification_reasoning")
            ownership_st = get(org_rows[0], "ownership_status")
            affiliated_dso_val = get(org_rows[0], "affiliated_dso")
            affiliated_pe_val = get(org_rows[0], "affiliated_pe_sponsor")
            buyability = get(org_rows[0], "buyability_score")

        if ec is None:
            # Fall back to first row that has one
            for r in rows:
                if get(r, "entity_classification"):
                    ec = get(r, "entity_classification")
                    ec_confidence = get(r, "classification_confidence")
                    ec_reasoning = get(r, "classification_reasoning")
                    ownership_st = get(r, "ownership_status")
                    affiliated_dso_val = get(r, "affiliated_dso")
                    affiliated_pe_val = get(r, "affiliated_pe_sponsor")
                    buyability = get(r, "buyability_score")
                    break

        # If still None, do a quick inline classification based on location-level signals
        # (full recomputation is the classifier-fixer agent's job, but we seed reasonable values)
        if ec is None and elected_name:
            name_upper = elected_name.upper()
            if _is_non_clinical_name(elected_name):
                ec = "non_clinical"
            elif is_specialist_only:
                ec = "specialist"
            elif _is_national_dso(elected_name):
                ec = "dso_national"
            elif parent_company or franchise_name or iusa_number:
                ec = "dso_regional"
            elif provider_count >= 4:
                ec = "large_group" if has_org_npi else "large_group"
            elif provider_count >= 2:
                ec = "small_group" if has_org_npi else "small_group"
            elif employee_count is not None and employee_count >= 5:
                ec = "solo_high_volume"
            elif estimated_revenue is not None and estimated_revenue >= 800000:
                ec = "solo_high_volume"
            elif not phone and not website:
                ec = "solo_inactive"
            elif year_established is not None and year_established >= 2016:
                ec = "solo_new"
            else:
                ec = "solo_established"

        loc = {
            "location_id": loc_id,
            "normalized_address": norm_addr,
            "zip": zip_code,
            "city": city,
            "state": state,
            "practice_name": elected_name,
            "doing_business_as": doing_business_as,
            "primary_npi": primary_npi,
            "org_npi": org_npi,
            "provider_npis": json.dumps(provider_npis),
            "provider_count": provider_count,
            "has_org_npi": 1 if has_org_npi else 0,
            "is_specialist_only": 1 if is_specialist_only else 0,
            "is_likely_residential": 1 if is_likely_residential else 0,
            "entity_classification": ec,
            "ownership_status": ownership_st,
            "affiliated_dso": affiliated_dso_val,
            "affiliated_pe_sponsor": affiliated_pe_val,
            "buyability_score": int(buyability) if buyability is not None else None,
            "classification_confidence": int(ec_confidence) if ec_confidence is not None else None,
            "classification_reasoning": ec_reasoning,
            "latitude": lat,
            "longitude": lon,
            "year_established": year_established,
            "employee_count": employee_count,
            "estimated_revenue": int(estimated_revenue) if estimated_revenue is not None else None,
            "data_axle_enriched": 1 if data_axle_enriched else 0,
            "parent_company": parent_company,
            "ein": ein,
            "website": website,
            "phone": phone,
            "data_sources": data_sources,
            "taxonomy_codes": json.dumps(all_taxonomies),
            "created_at": now,
            "updated_at": now,
        }
        locations_built.append(loc)

    log.info("Built %d location rows from %d input NPI rows", len(locations_built), total_input)

    # ------------------------------------------------------------------
    # 4. Upsert into practice_locations
    # ------------------------------------------------------------------
    if dry_run:
        log.info("[DRY RUN] Would upsert %d rows into practice_locations. No DB changes made.", len(locations_built))
        _log_summary_stats(locations_built, log, watched_zip_set)
        return total_input, len(locations_built), skipped_blank

    # Use raw SQLite for a full replace (TRUNCATE + INSERT).
    # We truncate first to ensure idempotency: the cross-zip merge step can change
    # which location_id a row belongs to between runs (e.g., org-only group absorbed
    # into an individual group on re-run), leaving stale orphan rows if we only INSERT OR REPLACE.
    import sqlite3 as _sqlite3
    from scrapers.database import DB_PATH

    conn = _sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM practice_locations")
    conn.commit()
    log.info("Truncated practice_locations before re-insert (idempotent full replace)")

    UPSERT_SQL = """
    INSERT OR REPLACE INTO practice_locations (
        location_id, normalized_address, zip, city, state,
        practice_name, doing_business_as, primary_npi, org_npi,
        provider_npis, provider_count, has_org_npi, is_specialist_only,
        is_likely_residential, entity_classification, ownership_status,
        affiliated_dso, affiliated_pe_sponsor, buyability_score,
        classification_confidence, classification_reasoning,
        latitude, longitude, year_established, employee_count,
        estimated_revenue, data_axle_enriched, parent_company, ein,
        website, phone, data_sources, taxonomy_codes, created_at, updated_at
    ) VALUES (
        :location_id, :normalized_address, :zip, :city, :state,
        :practice_name, :doing_business_as, :primary_npi, :org_npi,
        :provider_npis, :provider_count, :has_org_npi, :is_specialist_only,
        :is_likely_residential, :entity_classification, :ownership_status,
        :affiliated_dso, :affiliated_pe_sponsor, :buyability_score,
        :classification_confidence, :classification_reasoning,
        :latitude, :longitude, :year_established, :employee_count,
        :estimated_revenue, :data_axle_enriched, :parent_company, :ein,
        :website, :phone, :data_sources, :taxonomy_codes, :created_at, :updated_at
    )
    """

    BATCH_SIZE = 500
    for i in range(0, len(locations_built), BATCH_SIZE):
        batch = locations_built[i : i + BATCH_SIZE]
        cur.executemany(UPSERT_SQL, batch)
        conn.commit()
        upserted += len(batch)
        log.info("Upserted %d/%d locations...", upserted, len(locations_built))

    conn.close()
    log.info("Complete: %d locations upserted into practice_locations", upserted)

    _log_summary_stats(locations_built, log, watched_zip_set)

    return total_input, upserted, skipped_blank


def _log_summary_stats(locations: list, log, watched_zip_set=None):
    """Log detailed summary statistics for audit/verification by other agents."""
    total = len(locations)
    has_org = sum(1 for l in locations if l.get("has_org_npi"))
    residential = sum(1 for l in locations if l.get("is_likely_residential"))
    specialist = sum(1 for l in locations if l.get("is_specialist_only"))
    has_coords = sum(1 for l in locations if l.get("latitude") is not None)
    data_axle = sum(1 for l in locations if l.get("data_axle_enriched"))

    log.info("=" * 60)
    log.info("PRACTICE LOCATIONS SUMMARY")
    log.info("=" * 60)
    log.info("Total locations:        %d", total)
    log.info("Has org NPI (NPI-2):    %d (%.1f%%)", has_org, 100 * has_org / max(total, 1))
    log.info("Likely residential:     %d (%.1f%%)", residential, 100 * residential / max(total, 1))
    log.info("Specialist-only:        %d (%.1f%%)", specialist, 100 * specialist / max(total, 1))
    log.info("Has coordinates:        %d (%.1f%%)", has_coords, 100 * has_coords / max(total, 1))
    log.info("Data Axle enriched:     %d (%.1f%%)", data_axle, 100 * data_axle / max(total, 1))

    # Entity classification breakdown
    ec_counts = defaultdict(int)
    for l in locations:
        ec_counts[l.get("entity_classification") or "NULL"] += 1
    log.info("Entity classification breakdown:")
    for ec, cnt in sorted(ec_counts.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", ec, cnt)

    # Per-watched-ZIP stats (top 20 by count)
    if watched_zip_set:
        zip_counts = defaultdict(int)
        for l in locations:
            if l["zip"] in watched_zip_set:
                zip_counts[l["zip"]] += 1
        log.info("Per-ZIP location counts (top 20 by count):")
        for z, cnt in sorted(zip_counts.items(), key=lambda x: -x[1])[:20]:
            log.info("  ZIP %-8s  %d locations", z, cnt)
        log.info("  ... (%d total watched ZIPs with locations)", len(zip_counts))

    log.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dedup practices NPI rows into practice_locations table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute without writing to DB. Logs stats only.",
    )
    parser.add_argument(
        "--watched-only",
        action="store_true",
        default=True,
        help="Only process practices in watched ZIPs (default: True).",
    )
    parser.add_argument(
        "--all-practices",
        action="store_true",
        help="Process all 400k+ practices globally (ignores --watched-only).",
    )
    args = parser.parse_args()

    watched_only = not args.all_practices

    import sys
    import os
    sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

    from scrapers.database import get_session, init_db
    from scrapers.logger_config import get_logger

    log = get_logger("dedup_practice_locations")

    # Ensure practice_locations table exists
    log.info("Initializing database (ensuring practice_locations table exists)...")
    init_db()

    session = get_session()
    try:
        total_in, total_out, skipped = derive_practice_locations(
            session, watched_only=watched_only, dry_run=args.dry_run
        )
        log.info(
            "FINAL: input=%d output=%d skipped_blank=%d", total_in, total_out, skipped
        )
    except Exception as e:
        log.error("Dedup pipeline failed: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Unit tests (run with: python3 scrapers/dedup_practice_locations.py --test)
# ---------------------------------------------------------------------------

def _run_tests():
    """Assert all normalize_address test cases from /tmp/dedup_design.md pass."""
    import sys
    failures = []

    tests = [
        # Test case 1: various spellings of 1048 104th St should normalize identically
        (normalize_address("1048 104TH STREET"),    "1048 104th st",  "1048 104TH STREET"),
        (normalize_address("1048 104th St"),         "1048 104th st",  "1048 104th St"),
        (normalize_address("1048 104TH ST"),         "1048 104th st",  "1048 104TH ST"),
        (normalize_address("1048 104TH STREET#108"), "1048 104th st",  "1048 104TH STREET#108 (hash strip)"),
        # Test case 2: Suite and North abbreviations
        (normalize_address("123 N Main St, Suite 200"), "123 n main st", "123 N Main St, Suite 200"),
        (normalize_address("123 North Main Street #200"), "123 n main st", "123 North Main Street #200"),
    ]

    for actual, expected, label in tests:
        if actual != expected:
            failures.append(f"FAIL [{label}]: got {repr(actual)!s}, expected {repr(expected)!s}")
        else:
            print(f"PASS [{label}]: {repr(actual)}")

    # Extra cross-equality tests (spec says these must all be equal)
    equals_group_1 = [
        normalize_address("1048 104TH STREET"),
        normalize_address("1048 104th St"),
        normalize_address("1048 104TH ST"),
        normalize_address("1048 104TH STREET#108"),
    ]
    for i, a in enumerate(equals_group_1):
        for j, b in enumerate(equals_group_1):
            if a != b:
                failures.append(
                    f"FAIL [cross-equality group 1, idx {i} vs {j}]: {repr(a)} != {repr(b)}"
                )
    if len(set(equals_group_1)) == 1:
        print(f"PASS [cross-equality group 1]: all 4 variants equal {repr(equals_group_1[0])}")

    equals_group_2 = [
        normalize_address("123 N Main St, Suite 200"),
        normalize_address("123 North Main Street #200"),
    ]
    if len(set(equals_group_2)) == 1:
        print(f"PASS [cross-equality group 2]: both variants equal {repr(equals_group_2[0])}")
    else:
        failures.append(
            f"FAIL [cross-equality group 2]: {repr(equals_group_2[0])} != {repr(equals_group_2[1])}"
        )

    # location_id determinism test
    lid1 = location_id("1048 104th st", "60564")
    lid2 = location_id("1048 104th st", "60564")
    if lid1 == lid2 and len(lid1) == 16:
        print(f"PASS [location_id determinism]: {lid1}")
    else:
        failures.append(f"FAIL [location_id]: got {lid1} / {lid2}")

    # location_id length test
    if len(lid1) == 16:
        print(f"PASS [location_id length=16]: {len(lid1)}")
    else:
        failures.append(f"FAIL [location_id length]: expected 16, got {len(lid1)}")

    # Empty address test
    if normalize_address("") == "":
        print("PASS [empty address]: returns empty string")
    else:
        failures.append("FAIL [empty address]")

    if normalize_address(None) == "":
        print("PASS [None address]: returns empty string")
    else:
        failures.append("FAIL [None address]")

    print()
    if failures:
        print(f"FAILURES: {len(failures)}")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        print(f"ALL TESTS PASSED ({len(tests) + 4} assertions)")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _run_tests()
    else:
        main()
