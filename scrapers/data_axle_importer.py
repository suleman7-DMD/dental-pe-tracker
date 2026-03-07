"""
Data Axle Reference Solutions Importer — imports dental practice CSV exports,
deduplicates records into unique "doors", classifies DSO affiliation, scores
buyability, and generates HTML debug reports.

Usage:
    python3 scrapers/data_axle_importer.py                    # import all CSVs
    python3 scrapers/data_axle_importer.py --preview           # parse + dedup + classify without DB writes
    python3 scrapers/data_axle_importer.py --instructions      # print Data Axle export guide
    python3 scrapers/data_axle_importer.py --auto              # skip column mapping confirmation
    python3 scrapers/data_axle_importer.py --zip-filter 60540  # only process one ZIP
    python3 scrapers/data_axle_importer.py --debug             # verbose logging
    python3 scrapers/data_axle_importer.py --force-reclassify  # re-classify existing DA records
"""

import argparse
import hashlib
import html as html_lib
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime
from glob import glob

import pandas as pd
from rapidfuzz import fuzz, process as rfprocess

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_session, get_engine, Practice, PracticeChange, WatchedZip,
    log_practice_change,
)

# Import DSO list from dso_classifier
try:
    from scrapers.dso_classifier import KNOWN_DSOS, MGMT_KEYWORDS, classify_practice
except ImportError:
    KNOWN_DSOS = []
    MGMT_KEYWORDS = []

    def classify_practice(practice_name, dba_name):
        return "unknown", None, None, 0, "dso_classifier not available"

log = get_logger("data_axle_importer")

# ── Paths ─────────────────────────────────────────────────────────────────────

RAW_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle")
PROCESSED_DIR = os.path.join(RAW_DIR, "processed")
DEBUG_DIR = os.path.join(RAW_DIR, "debug-reports")

# ── State Abbreviation Map ────────────────────────────────────────────────────

STATE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
VALID_ABBREVS = set(STATE_MAP.values())

# ── Known Column Name Variants ────────────────────────────────────────────────

FIELD_CANDIDATES = {
    "company_name": [
        "Company Name", "Company", "Business Name", "Organization Name",
    ],
    "dba_name": [
        "DBA Name", "DBA", "Trade Style", "Doing Business As", "Trade Name",
    ],
    "address": [
        "Address Line 1", "Address", "Street Address", "Physical Address",
    ],
    "city": [
        "City", "City Name", "Physical City",
    ],
    "state": [
        "State", "State Abbreviation", "State Code", "Physical State",
    ],
    "zip": [
        "ZIP Code", "ZIP", "Postal Code", "Zip Code",
    ],
    "zip4": [
        "ZIP+4", "Plus 4", "Zip Plus 4",
    ],
    "phone": [
        "Phone", "Phone Number", "Primary Phone", "Telephone",
    ],
    "sic_code": [
        "SIC Code", "SIC", "Primary SIC Code", "Primary SIC", "SIC 4",
    ],
    "sic_description": [
        "SIC Description", "SIC Code Description", "Primary SIC Description",
    ],
    "naics_code": [
        "Primary NAICS Code", "NAICS Code", "NAICS",
    ],
    "naics_description": [
        "NAICS Description", "Primary NAICS Description",
    ],
    "employee_range": [
        "Employee Size Range", "Employee Size", "Emp Size Range",
        "Number of Employees", "Employee Range",
    ],
    "employee_actual": [
        "Employee Size Actual", "Actual Employee Size", "Employee Count",
        "Actual Employees",
    ],
    "revenue": [
        "Annual Sales Volume", "Sales Volume", "Annual Revenue", "Revenue",
        "Sales Volume Range", "Estimated Revenue",
    ],
    "year_established": [
        "Year Established", "Year Started", "Year Founded", "Founded Year",
    ],
    "years_in_database": [
        "Years In Database",
    ],
    "ownership": [
        "Ownership", "Ownership Code", "Public/Private", "Ownership Type",
    ],
    "square_footage": [
        "Square Footage", "Sq Footage", "Sq Ft",
    ],
    "credit_score": [
        "Credit Score Range", "Credit Score",
    ],
    "contact_first": [
        "Contact First Name", "First Name", "Executive First Name",
    ],
    "contact_last": [
        "Contact Last Name", "Last Name", "Executive Last Name",
    ],
    "contact_title": [
        "Contact Title", "Title", "Executive Title",
    ],
    "location_type": [
        "Number of Locations", "Location Type", "Single/Branch/HQ",
        "Subsidiary Status", "Headquarters/Branch",
    ],
    "latitude": [
        "Latitude", "Lat",
    ],
    "longitude": [
        "Longitude", "Lng", "Long",
    ],
    "county": [
        "County", "County Name",
    ],
    "fips_code": [
        "FIPS Code", "County FIPS",
    ],
    "census_tract": [
        "Census Tract",
    ],
    "msa_code": [
        "MSA Code", "Metro Area", "Metropolitan Area",
    ],
}

EXPECTED_COLUMNS = [
    "company_name", "address", "city", "state", "zip", "phone",
    "sic_code", "employee_range", "revenue", "year_established",
]

# ── SIC / NAICS Filtering ─────────────────────────────────────────────────────

DENTAL_SICS = {"8021"}
DENTAL_NAICS = {"621210", "6212"}
EXCLUDE_SICS = {"8072", "8041", "5047", "7389", "8049"}
EXCLUDE_DESC_TERMS = [
    "lab", "laboratory", "equipment", "supplier", "supply",
    "billing", "insurance", "chiropract", "veterinar", "technician",
    "prosthetic", "denture lab",
]

# ── Address Abbreviations ─────────────────────────────────────────────────────

ADDR_ABBREVS = {
    r"\bST\b": "STREET", r"\bDR\b": "DRIVE", r"\bAVE\b": "AVENUE",
    r"\bBLVD\b": "BOULEVARD", r"\bRD\b": "ROAD", r"\bLN\b": "LANE",
    r"\bCT\b": "COURT", r"\bPL\b": "PLACE", r"\bCIR\b": "CIRCLE",
    r"\bHWY\b": "HIGHWAY", r"\bPKY\b": "PARKWAY", r"\bPKWY\b": "PARKWAY",
    r"\bN\b": "NORTH", r"\bS\b": "SOUTH", r"\bE\b": "EAST", r"\bW\b": "WEST",
}

# ── PE Sponsor Mapping (extends dso_classifier) ──────────────────────────────

PE_SPONSOR_MAP = {
    "Heartland Dental": "KKR",
    "MB2 Dental": "Charlesbank/KKR/Warburg Pincus",
    "Dental365": "The Jordan Company",
    "Specialized Dental Partners": "Quad-C Management",
    "Aspen Dental": "Leonard Green & Partners",
    "Great Expressions": "Shore Capital",
    "SALT Dental": "Latticework Capital/Resolute Capital",
    "Chord Specialty Dental Partners": "Rock Mountain Capital",
    "USOSM": "Oak Hill Capital",
    "Sage Dental": "Linden Capital Partners",
    "Parkview Dental Partners": "Cathay Capital",
    "Smile Partners USA": "Silver Oak Services Partners",
    "The Smilist": "Zenyth Partners",
    "MAX Surgical": "MedEquity Capital/RF Investment Partners",
    "Pacific Dental Services": "founder-owned (PE debt only)",
    "Western Dental": "formerly New Mountain Capital",
    "42 North Dental": "Berkshire Partners (historical)",
    "North American Dental Group": "Jacobs Holding",
    "Smile Brands": "Gryphon Investors",
    "Dental Care Alliance": "Harvest Partners",
}

PE_SPONSOR_NAMES = ["KKR", "Charlesbank", "Warburg Pincus", "Quad-C", "Oak Hill Capital"]


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — COLUMN DETECTION AND IMPORT
# ═══════════════════════════════════════════════════════════════════════════════


def normalize_state(val):
    """Convert state name or abbreviation to 2-letter code."""
    if not isinstance(val, str):
        return None
    v = val.strip()
    if len(v) == 2 and v.upper() in VALID_ABBREVS:
        return v.upper()
    low = v.lower()
    if low in STATE_MAP:
        return STATE_MAP[low]
    return None


def normalize_zip(val):
    """Extract 5-digit ZIP from various formats."""
    if pd.isna(val):
        return None
    s = str(val).strip().split("-")[0].split(" ")[0]
    m = re.search(r"(\d{5})", s)
    return m.group(1) if m else None


def normalize_phone(val):
    """Extract 10-digit phone number."""
    if pd.isna(val) or not val:
        return None
    digits = re.sub(r"\D", "", str(val))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def normalize_address(addr):
    """Normalize address for matching: uppercase, strip suite, expand abbreviations."""
    if not addr or pd.isna(addr):
        return ""
    a = str(addr).upper().strip()
    # Strip suite/unit/apt and everything after
    a = re.sub(r"\b(STE|SUITE|UNIT|APT|#|BLDG|FLOOR|FL)\s*\.?\s*\S*.*$", "", a)
    # Remove periods, commas
    a = a.replace(".", "").replace(",", "")
    # Expand abbreviations
    for pat, repl in ADDR_ABBREVS.items():
        a = re.sub(pat, repl, a)
    # Collapse whitespace
    a = re.sub(r"\s+", " ", a).strip()
    return a


def parse_revenue(val):
    """Parse Data Axle revenue strings into integer dollars.

    Handles:
      "$500,000 to $999,999" -> 750000 (midpoint)
      "$500,000-999,999" -> 750000
      "Less than $500,000" -> 250000
      "$1,000,000 to $2,499,999" -> 1750000
      "$10,000,000+" -> 10000000
      "$1M" -> 1000000
      "1000000" -> 1000000
      "" or null -> None
    """
    if pd.isna(val) or not val:
        return None
    s = str(val).strip()
    if not s:
        return None

    # "$1M", "$2.5M"
    m = re.match(r"^\$?([\d.]+)\s*[Mm](?:illion)?$", s)
    if m:
        return int(float(m.group(1)) * 1_000_000)

    # "$1B"
    m = re.match(r"^\$?([\d.]+)\s*[Bb](?:illion)?$", s)
    if m:
        return int(float(m.group(1)) * 1_000_000_000)

    def _extract_num(part):
        cleaned = re.sub(r"[^\d.]", "", part)
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None

    # "Less than $X" or "Under $X"
    m = re.match(r"(?:less\s+than|under)\s+\$?([\d,]+)", s, re.IGNORECASE)
    if m:
        upper = _extract_num(m.group(1))
        return upper // 2 if upper else None

    # "$X+" or "Over $X" or "More than $X"
    m = re.match(r"(?:(?:over|more\s+than)\s+)?\$?([\d,]+)\s*\+?$", s, re.IGNORECASE)
    if m and ("+" in s or "over" in s.lower() or "more than" in s.lower()):
        return _extract_num(m.group(1))

    # Range: "$X to $Y" or "$X-$Y" or "$X - $Y"
    m = re.match(r"\$?([\d,]+)\s*(?:to|-|–)\s*\$?([\d,]+)", s, re.IGNORECASE)
    if m:
        lo = _extract_num(m.group(1))
        hi = _extract_num(m.group(2))
        if lo is not None and hi is not None:
            return (lo + hi) // 2
        return lo or hi

    # Plain number with possible $ and commas
    n = _extract_num(s)
    if n is not None and n > 0:
        return n

    log.warning("Could not parse revenue string: %r", s)
    return None


def _test_parse_revenue():
    """Inline tests for parse_revenue."""
    assert abs(parse_revenue("$500,000 to $999,999") - 750000) <= 1, parse_revenue("$500,000 to $999,999")
    assert parse_revenue("Less than $500,000") == 250000
    assert abs(parse_revenue("$1,000,000 to $2,499,999") - 1750000) <= 1
    assert abs(parse_revenue("$500,000-999,999") - 750000) <= 1
    assert parse_revenue("1000000") == 1000000
    assert parse_revenue("$1M") == 1000000
    assert parse_revenue("$2.5M") == 2500000
    assert parse_revenue("") is None
    assert parse_revenue(None) is None
    log.info("All parse_revenue tests passed")


def parse_employee_count(row, mapping):
    """Extract employee count from actual or range columns."""
    # Prefer actual count
    for field in ("employee_actual", "employee_range"):
        col = mapping.get(field)
        if not col:
            continue
        val = row.get(col)
        if pd.isna(val) or not val:
            continue
        s = str(val).strip()
        # Try plain number
        m = re.search(r"(\d+)", s)
        if m:
            return int(m.group(1))
    return None


def detect_columns(csv_columns):
    """Fuzzy-match CSV column headers against known variants.

    Returns: (mapping, details)
        mapping: {canonical_field: csv_column_name}
        details: [(csv_col, mapped_field, score)] for report
    """
    # Flatten all variants into list for matching
    all_variants = []
    for canonical, variants in FIELD_CANDIDATES.items():
        for v in variants:
            all_variants.append((v, canonical))

    variant_names = [v[0] for v in all_variants]
    mapping = {}
    details = []
    used_cols = set()

    for csv_col in csv_columns:
        result = rfprocess.extractOne(
            csv_col, variant_names, scorer=fuzz.token_sort_ratio, score_cutoff=80
        )
        if result:
            matched_variant, score, idx = result
            canonical = all_variants[idx][1]
            if canonical not in mapping:
                mapping[canonical] = csv_col
                used_cols.add(csv_col)
                details.append((csv_col, canonical, score))
            else:
                details.append((csv_col, f"(dup of {canonical})", score))
        else:
            details.append((csv_col, None, 0))

    return mapping, details


def print_column_mapping(details, mapping):
    """Print column mapping table to console."""
    print()
    header = f"  {'CSV Column':<40} {'Mapped To':<25} {'Confidence':>10}"
    print(header)
    print("  " + "-" * 77)
    for csv_col, mapped, score in sorted(details, key=lambda x: -(x[2] or 0)):
        mapped_str = mapped or "*** UNMAPPED ***"
        score_str = f"{score}%" if score else "—"
        marker = "" if mapped and not mapped.startswith("(") else " ⚠"
        print(f"  {csv_col:<40} {mapped_str:<25} {score_str:>10}{marker}")

    # Check for missing expected columns
    missing = [f for f in EXPECTED_COLUMNS if f not in mapping]
    if missing:
        print(f"\n  ⚠ Missing expected columns: {', '.join(missing)}")
    print()


def read_csv_file(filepath):
    """Read CSV with multiple encoding attempts."""
    filename = os.path.basename(filepath)
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(filepath, encoding=encoding, dtype=str, low_memory=False)
            log.info("Read %s with encoding %s: %d rows, %d columns",
                     filename, encoding, len(df), len(df.columns))
            return df, encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            log.error("Failed to read %s with %s: %s", filename, encoding, e)
            continue
    log.error("Could not read %s with any encoding", filename)
    return None, None


def is_dental_practice(row, mapping):
    """Check if record is a dental practice. Returns (is_dental, reason)."""
    sic = str(row.get(mapping.get("sic_code", ""), "") or "").strip()
    naics = str(row.get(mapping.get("naics_code", ""), "") or "").strip()
    sic_desc = str(row.get(mapping.get("sic_description", ""), "") or "").lower()
    naics_desc = str(row.get(mapping.get("naics_description", ""), "") or "").lower()
    combined_desc = sic_desc + " " + naics_desc

    # Exclusions first
    for exc_sic in EXCLUDE_SICS:
        if sic.startswith(exc_sic):
            return False, f"excluded SIC {sic}"
    for term in EXCLUDE_DESC_TERMS:
        if term in combined_desc:
            return False, f"excluded: description contains '{term}'"

    # Inclusions
    for dental_sic in DENTAL_SICS:
        if sic.startswith(dental_sic):
            return True, f"dental SIC {sic}"
    for dental_naics in DENTAL_NAICS:
        if naics.startswith(dental_naics):
            return True, f"dental NAICS {naics}"
    if "dentist" in combined_desc or "dental" in combined_desc:
        return True, "description mentions dental/dentist"

    return False, f"not dental (SIC={sic}, NAICS={naics})"


def validate_record(row, mapping, row_num):
    """Validate a single CSV row. Returns (is_valid, reason, parsed_record)."""
    # Company name or DBA required
    company = str(row.get(mapping.get("company_name", ""), "") or "").strip()
    dba = str(row.get(mapping.get("dba_name", ""), "") or "").strip()
    if not company and not dba:
        return False, "no company name or DBA", None

    # Address required
    address = str(row.get(mapping.get("address", ""), "") or "").strip()
    if not address:
        return False, "no address", None

    # Valid state
    state_raw = str(row.get(mapping.get("state", ""), "") or "").strip()
    state = normalize_state(state_raw)
    if not state:
        return False, f"invalid state: {state_raw!r}", None

    # Valid ZIP
    zip_raw = row.get(mapping.get("zip", ""), "")
    zip_code = normalize_zip(zip_raw)
    if not zip_code:
        return False, f"invalid ZIP: {zip_raw!r}", None

    # Dental practice check (only if SIC/NAICS columns exist)
    if mapping.get("sic_code") or mapping.get("naics_code"):
        is_dental, dental_reason = is_dental_practice(row, mapping)
        if not is_dental:
            return False, dental_reason, None

    # City
    city = str(row.get(mapping.get("city", ""), "") or "").strip()

    # Phone
    phone = normalize_phone(row.get(mapping.get("phone", ""), ""))

    # Employee count
    emp = parse_employee_count(row, mapping)

    # Revenue
    rev = parse_revenue(row.get(mapping.get("revenue", ""), ""))

    # Year established
    yr = None
    yr_raw = row.get(mapping.get("year_established", ""), "")
    if yr_raw and not pd.isna(yr_raw):
        m = re.search(r"(\d{4})", str(yr_raw))
        if m:
            yr = int(m.group(1))

    # Location type
    loc_raw = str(row.get(mapping.get("location_type", ""), "") or "").lower()
    loc_type = None
    if "single" in loc_raw or loc_raw == "1":
        loc_type = "single"
    elif "branch" in loc_raw:
        loc_type = "branch"
    elif "headquarter" in loc_raw or "hq" in loc_raw:
        loc_type = "hq"
    elif "subsidiary" in loc_raw:
        loc_type = "subsidiary"

    # Ownership
    own_raw = str(row.get(mapping.get("ownership", ""), "") or "").lower()

    # Contact name
    first = str(row.get(mapping.get("contact_first", ""), "") or "").strip()
    last = str(row.get(mapping.get("contact_last", ""), "") or "").strip()
    contact = f"{first} {last}".strip() if first or last else None

    # SIC/NAICS codes
    sic = str(row.get(mapping.get("sic_code", ""), "") or "").strip()
    naics = str(row.get(mapping.get("naics_code", ""), "") or "").strip()

    record = {
        "company_name": company,
        "dba_name": dba or None,
        "address": address,
        "normalized_address": normalize_address(address),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "sic_code": sic or None,
        "naics_code": naics or None,
        "employee_count": emp,
        "estimated_revenue": rev,
        "year_established": yr,
        "location_type": loc_type,
        "ownership_raw": own_raw,
        "contact_name": contact,
        "contact_first": first,
        "contact_last": last,
        "row_num": row_num,
    }
    return True, None, record


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — DEDUPLICATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class UnionFind:
    """Simple Union-Find for clustering record indices."""

    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py

    def groups(self):
        clusters = defaultdict(list)
        for i in range(len(self.parent)):
            clusters[self.find(i)].append(i)
        return clusters


def deduplicate_records(records, debug=False):
    """Multi-pass deduplication engine.

    Returns: (doors, dedup_report)
    """
    n = len(records)
    if n == 0:
        return [], {"clusters": [], "answering_services": [], "fuzzy_matches": []}

    uf = UnionFind(n)
    dedup_report = {
        "clusters": [],
        "answering_services": [],
        "fuzzy_matches": [],
    }

    # ── PASS 1 + 2: Address clustering ────────────────────────────────────
    addr_groups = defaultdict(list)
    for i, rec in enumerate(records):
        key = (rec["normalized_address"], rec["zip"])
        addr_groups[key].append(i)

    for key, indices in addr_groups.items():
        if len(indices) > 1:
            for j in range(1, len(indices)):
                uf.union(indices[0], indices[j])
            if debug:
                log.debug("Address cluster %s: %d records", key, len(indices))

    # ── Phone clustering (with answering service protection) ──────────────
    zip_groups = defaultdict(list)
    for i, rec in enumerate(records):
        zip_groups[rec["zip"]].append(i)

    for zip_code, zip_indices in zip_groups.items():
        phone_addrs = defaultdict(set)
        phone_indices = defaultdict(list)
        for i in zip_indices:
            ph = records[i]["phone"]
            if ph:
                phone_addrs[ph].add(records[i]["normalized_address"])
                phone_indices[ph].append(i)

        for ph, addrs in phone_addrs.items():
            if len(addrs) > 5:
                log.info("Possible answering service: %s appears at %d addresses in ZIP %s",
                         ph, len(addrs), zip_code)
                dedup_report["answering_services"].append({
                    "phone": ph, "zip": zip_code, "address_count": len(addrs),
                })
                continue
            if len(addrs) >= 2:
                indices = phone_indices[ph]
                for j in range(1, len(indices)):
                    uf.union(indices[0], indices[j])
                if debug:
                    log.debug("Phone cluster %s in ZIP %s: %d records at %d addresses",
                              ph, zip_code, len(indices), len(addrs))

    # ── Fuzzy address matching within ZIP ─────────────────────────────────
    for zip_code, zip_indices in zip_groups.items():
        unique_addrs = {}
        for i in zip_indices:
            a = records[i]["normalized_address"]
            if a not in unique_addrs:
                unique_addrs[a] = []
            unique_addrs[a].append(i)

        addr_list = list(unique_addrs.keys())
        for ai in range(len(addr_list)):
            for bi in range(ai + 1, len(addr_list)):
                score = fuzz.ratio(addr_list[ai], addr_list[bi])
                if score >= 90:
                    idx_a = unique_addrs[addr_list[ai]][0]
                    idx_b = unique_addrs[addr_list[bi]][0]
                    uf.union(idx_a, idx_b)
                    dedup_report["fuzzy_matches"].append({
                        "addr_a": addr_list[ai], "addr_b": addr_list[bi],
                        "zip": zip_code, "score": score,
                    })
                    if debug:
                        log.debug("Fuzzy match in ZIP %s: %r ~ %r (score=%d)",
                                  zip_code, addr_list[ai], addr_list[bi], score)

    # ── PASS 3: Collapse clusters into doors ──────────────────────────────
    clusters = uf.groups()
    doors = []
    for root, indices in clusters.items():
        cluster_records = [records[i] for i in indices]
        door = _collapse_cluster(cluster_records)
        if len(indices) > 1:
            dedup_report["clusters"].append({
                "records": cluster_records,
                "door": door,
                "count": len(indices),
            })
        doors.append(door)

    log.info("Dedup: %d raw records -> %d unique doors (%.1f%% reduction)",
             n, len(doors), (1 - len(doors) / n) * 100 if n else 0)

    # ── PASS 4: Phone cross-reference ─────────────────────────────────────
    phone_doors = defaultdict(list)
    for i, door in enumerate(doors):
        if door["phone"]:
            phone_doors[door["phone"]].append(i)

    for ph, door_indices in phone_doors.items():
        if 2 <= len(door_indices) <= 4:
            for di in door_indices:
                doors[di]["phone_duplicate_review"] = True
                doors[di]["shared_phone_doors"] = len(door_indices)

    # ── PASS 5: Stealth DSO detection ─────────────────────────────────────
    _detect_stealth_dso(doors, phone_doors)

    return doors, dedup_report


def _collapse_cluster(cluster_records):
    """Merge a cluster of raw records into one door dict."""
    n = len(cluster_records)

    # Pick the most complete record as base (most non-None fields)
    def completeness(rec):
        return sum(1 for v in rec.values() if v is not None and v != "")
    base = max(cluster_records, key=completeness)

    # Name: prefer DBA over legal entity; prefer shorter clean name over "XYZ PC"
    names = set()
    dbas = set()
    for rec in cluster_records:
        if rec["company_name"]:
            names.add(rec["company_name"])
        if rec["dba_name"]:
            dbas.add(rec["dba_name"])

    # Use DBA if available, otherwise company name
    if dbas:
        practice_name = min(dbas, key=len)  # shortest DBA is usually cleanest
    elif names:
        # Prefer name without PC/LLC/PLLC/INC suffix
        clean = [n for n in names if not re.search(r"\b(PC|LLC|PLLC|INC|CORP|LTD)\b", n, re.IGNORECASE)]
        practice_name = min(clean, key=len) if clean else min(names, key=len)
    else:
        practice_name = ""

    # Collect providers
    providers = set()
    for rec in cluster_records:
        if rec.get("contact_name") and rec["contact_name"].strip():
            providers.add(rec["contact_name"].strip())

    # Merge fields
    door = {
        "practice_name": practice_name,
        "dba_name": next((d for d in dbas), None) if dbas else None,
        "raw_names": list(names | dbas),
        "address": base["address"],
        "normalized_address": base["normalized_address"],
        "city": base["city"],
        "state": base["state"],
        "zip": base["zip"],
        "phone": base["phone"],
        "sic_code": base.get("sic_code"),
        "naics_code": base.get("naics_code"),
        "employee_count": max((r["employee_count"] for r in cluster_records
                               if r["employee_count"] is not None), default=None),
        "estimated_revenue": max((r["estimated_revenue"] for r in cluster_records
                                  if r["estimated_revenue"] is not None), default=None),
        "year_established": min((r["year_established"] for r in cluster_records
                                 if r["year_established"] is not None), default=None),
        "location_type": base.get("location_type"),
        "ownership_raw": base.get("ownership_raw", ""),
        "providers": sorted(providers),
        "num_providers": len(providers),
        "raw_record_count": n,
        "raw_records": cluster_records,
        # Will be filled later
        "affiliated_dso": None,
        "affiliated_pe_sponsor": None,
        "ownership_status": "unknown",
        "classification_confidence": 0,
        "classification_reasoning": "",
        "buyability_score": 0,
        "stealth_dso_signals": [],
        "phone_duplicate_review": False,
        "shared_phone_doors": 0,
    }
    return door


def _detect_stealth_dso(doors, phone_doors):
    """Pass 5: Flag patterns suggesting hidden DSO affiliation."""
    # Index doors by contact last name
    contact_doors = defaultdict(list)
    for i, door in enumerate(doors):
        for rec in door["raw_records"]:
            last = rec.get("contact_last", "")
            if last and len(last) > 1:
                contact_doors[last.upper()].append(i)

    for i, door in enumerate(doors):
        signals = []
        name = (door["practice_name"] or "").lower()

        # Corporate keywords
        for kw in ["management", "partners", "holdings", "group"]:
            if kw in name and "dental" in name:
                signals.append(f"corporate keyword '{kw}' in name")

        # High employee count for single location
        if door["employee_count"] and door["employee_count"] >= 20:
            if door["location_type"] in ("single", None):
                signals.append(f"high employee count ({door['employee_count']}) for single location")

        # Branch/subsidiary
        if door["location_type"] in ("branch", "subsidiary"):
            signals.append(f"location type is '{door['location_type']}'")

        # Same contact across 3+ practice names
        for rec in door["raw_records"]:
            last = rec.get("contact_last", "")
            if last and len(last) > 1:
                all_doors_for_contact = set(contact_doors.get(last.upper(), []))
                if len(all_doors_for_contact) >= 3:
                    signals.append(f"contact '{last}' appears at {len(all_doors_for_contact)} practices")
                    break

        # Shared phone with 2-4 other doors
        if door["phone"] and door["phone"] in phone_doors:
            shared = phone_doors[door["phone"]]
            if 2 <= len(shared) <= 4:
                signals.append(f"shares phone with {len(shared)-1} other doors")

        door["stealth_dso_signals"] = signals


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — CLASSIFICATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


def classify_door(door, all_doors=None):
    """Classify a door with confidence score and reasoning.

    Returns: (ownership_status, dso_name, pe_sponsor, confidence, reasoning)
    """
    name = door["practice_name"] or ""
    dba = door.get("dba_name") or ""

    # ── Rule 1: Direct DSO name match (confidence 95%) ────────────────────
    status, dso_name, pe_sponsor, conf, reason = classify_practice(name, dba)
    if status in ("pe_backed", "dso_affiliated"):
        # Supplement PE sponsor from our extended map
        if dso_name and not pe_sponsor:
            pe_sponsor = PE_SPONSOR_MAP.get(dso_name)
            if pe_sponsor:
                status = "pe_backed"
        return status, dso_name, pe_sponsor, conf, reason

    # Check all raw names too
    for raw_name in door.get("raw_names", []):
        status2, dso2, pe2, conf2, reason2 = classify_practice(raw_name, "")
        if status2 in ("pe_backed", "dso_affiliated"):
            if dso2 and not pe2:
                pe2 = PE_SPONSOR_MAP.get(dso2)
                if pe2:
                    status2 = "pe_backed"
            return status2, dso2, pe2, conf2, f"{reason2} (from raw name: {raw_name})"

    # Check for PE sponsor names directly in company name
    combined = f"{name} {dba}".lower()
    for pe_name in PE_SPONSOR_NAMES:
        if pe_name.lower() in combined:
            return "pe_backed", None, pe_name, 90, f"PE sponsor name '{pe_name}' in company name"

    # ── Rule 2: Stealth DSO signals (confidence 60-80%) ───────────────────
    signals = door.get("stealth_dso_signals", [])
    if signals:
        # Confidence based on strongest signal
        conf = 60
        if any("corporate keyword" in s for s in signals):
            conf = max(conf, 70)
        if any("location type" in s for s in signals):
            conf = max(conf, 65)
        if any("employee count" in s for s in signals):
            conf = max(conf, 60)
        if any("shares phone" in s for s in signals):
            conf = max(conf, 80)
        if door["employee_count"] and door["employee_count"] >= 50:
            conf = max(conf, 60)
        return "dso_affiliated", None, None, conf, f"Stealth DSO signals: {'; '.join(signals)}"

    # ── Rule 3: Independent signals (confidence 70-90%) ───────────────────
    independent_signals = []
    ind_conf = 70

    # Doctor name pattern
    if re.search(r"(?:^dr\.?\s+\w|dds|dmd|d\.d\.s|d\.m\.d)", combined, re.IGNORECASE):
        independent_signals.append("doctor name pattern")
        ind_conf = max(ind_conf, 85)

    # Single location + private + small
    if door["location_type"] in ("single", None):
        independent_signals.append("single location")
        ind_conf = max(ind_conf, 70)
        if "private" in door.get("ownership_raw", ""):
            independent_signals.append("private ownership")
            ind_conf = max(ind_conf, 80)
            if door["employee_count"] and door["employee_count"] <= 9:
                independent_signals.append(f"small staff ({door['employee_count']})")
                ind_conf = 90
            elif door["employee_count"] is None:
                ind_conf = max(ind_conf, 80)

    if independent_signals:
        return "independent", None, None, ind_conf, \
            f"Independent signals: {'; '.join(independent_signals)}"

    # ── Rule 4: Unknown ───────────────────────────────────────────────────
    return "unknown", None, None, 0, "Insufficient signals for classification"


def classify_all_doors(doors):
    """Run classification on all doors."""
    summary = {"pe_backed": 0, "dso_affiliated": 0, "independent": 0, "unknown": 0}
    for door in doors:
        status, dso_name, pe_sponsor, conf, reasoning = classify_door(door, doors)
        door["ownership_status"] = status
        door["affiliated_dso"] = dso_name
        door["affiliated_pe_sponsor"] = pe_sponsor
        door["classification_confidence"] = conf
        door["classification_reasoning"] = reasoning
        summary[status] = summary.get(status, 0) + 1

    log.info("Classification: %s", ", ".join(f"{k}={v}" for k, v in summary.items()))
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# PART 4 — BUYABILITY SCORING
# ═══════════════════════════════════════════════════════════════════════════════


def compute_buyability(door):
    """Compute buyability score (0-100) with detailed breakdown."""
    if door["ownership_status"] in ("dso_affiliated", "pe_backed"):
        door["buyability_score"] = 0
        door["buyability_breakdown"] = [("DSO/PE classified", -50, "score forced to 0")]
        return 0

    score = 50
    breakdown = [("base", 50, "starting score")]

    # Year established
    yr = door.get("year_established")
    if yr:
        if yr < 1990:
            adj, reason = 20, f"established {yr} (very mature)"
        elif yr < 2000:
            adj, reason = 15, f"established {yr}"
        elif yr <= 2005:
            adj, reason = 10, f"established {yr}"
        elif yr <= 2010:
            adj, reason = 5, f"established {yr}"
        elif yr <= 2015:
            adj, reason = 0, f"established {yr} (neutral)"
        elif yr <= 2020:
            adj, reason = -5, f"established {yr} (newer)"
        else:
            adj, reason = -10, f"established {yr} (very new)"
        if adj != 0:
            score += adj
            breakdown.append(("year_established", adj, reason))

    # Employee count
    emp = door.get("employee_count")
    if emp is not None:
        if emp <= 2:
            adj, reason = 15, f"{emp} employees (true solo)"
        elif emp <= 4:
            adj, reason = 12, f"{emp} employees"
        elif emp <= 9:
            adj, reason = 5, f"{emp} employees"
        elif emp <= 19:
            adj, reason = -5, f"{emp} employees"
        elif emp <= 49:
            adj, reason = -15, f"{emp} employees"
        else:
            adj, reason = -25, f"{emp} employees (large)"
        score += adj
        breakdown.append(("employee_count", adj, reason))

    # Location type
    lt = door.get("location_type")
    if lt == "single":
        score += 10
        breakdown.append(("location_type", 10, "single location"))
    elif lt == "branch":
        score -= 15
        breakdown.append(("location_type", -15, "branch"))
    elif lt == "hq":
        score -= 20
        breakdown.append(("location_type", -20, "headquarters"))
    elif lt == "subsidiary":
        score -= 25
        breakdown.append(("location_type", -25, "subsidiary"))

    # Ownership
    own = door.get("ownership_raw", "")
    if "private" in own:
        score += 5
        breakdown.append(("ownership", 5, "private"))
    elif "public" in own:
        score -= 25
        breakdown.append(("ownership", -25, "public"))
    elif "government" in own:
        score -= 50
        breakdown.append(("ownership", -50, "government"))

    # Classification
    if door["ownership_status"] == "independent":
        score += 10
        breakdown.append(("classification", 10, "likely independent"))

    # Practice name signals
    pname = (door["practice_name"] or "").lower()
    if re.search(r"(?:^dr\.?\s|\bdds\b|\bdmd\b)", pname):
        score += 5
        breakdown.append(("name_pattern", 5, "doctor name in practice"))
    elif re.search(r"\b(?:llc|inc|corp|management|partners)\b", pname):
        score -= 5
        breakdown.append(("name_pattern", -5, "corporate-sounding name"))

    # Provider count
    np_ = door.get("num_providers", 0)
    if np_ == 1:
        score += 10
        breakdown.append(("providers", 10, "1 provider (true solo)"))
    elif np_ == 2:
        score += 5
        breakdown.append(("providers", 5, "2 providers"))
    elif 3 <= np_ <= 4:
        pass  # neutral
    elif np_ >= 5:
        score -= 10
        breakdown.append(("providers", -10, f"{np_} providers"))

    # Revenue
    rev = door.get("estimated_revenue")
    if rev is not None:
        if rev < 500_000:
            adj, reason = 5, f"revenue ${rev:,} (small)"
        elif rev < 1_000_000:
            adj, reason = 10, f"revenue ${rev:,} (ideal)"
        elif rev < 2_000_000:
            adj, reason = 5, f"revenue ${rev:,}"
        else:
            adj, reason = -5, f"revenue ${rev:,} (large)"
        score += adj
        breakdown.append(("revenue", adj, reason))

    # Clamp
    score = max(0, min(100, score))
    door["buyability_score"] = score
    door["buyability_breakdown"] = breakdown
    return score


# ═══════════════════════════════════════════════════════════════════════════════
# PART 5 — DATABASE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════


def ensure_data_axle_columns(engine):
    """Add Data Axle columns to practices table if missing."""
    from sqlalchemy import text
    new_cols = [
        ("year_established", "INTEGER"),
        ("employee_count", "INTEGER"),
        ("estimated_revenue", "INTEGER"),
        ("num_providers", "INTEGER"),
        ("location_type", "TEXT"),
        ("buyability_score", "INTEGER"),
        ("classification_confidence", "INTEGER"),
        ("classification_reasoning", "TEXT"),
        ("data_axle_raw_name", "TEXT"),
        ("data_axle_import_date", "DATE"),
        ("raw_record_count", "INTEGER"),
        ("import_batch_id", "TEXT"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE practices ADD COLUMN {col_name} {col_type}"))
                conn.commit()
                log.info("Added column practices.%s", col_name)
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    log.debug("Column practices.%s already exists", col_name)
                else:
                    log.warning("Failed to add column practices.%s: %s", col_name, e)


def generate_synthetic_npi(door):
    """Generate deterministic synthetic NPI for Data Axle records."""
    name = (door.get("practice_name") or "").upper().strip()
    key = f"{door['normalized_address']}|{door['zip']}|{name}"
    h = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"DA_{h}"


def match_existing_practice(session, door):
    """Try to match a door to an existing practice.

    Returns: (practice_or_None, match_method, match_score)
    """
    zip_code = door["zip"]
    candidates = session.query(Practice).filter(Practice.zip == zip_code).all()
    if not candidates:
        return None, None, 0

    best_match = None
    best_score = 0
    best_method = None

    for prac in candidates:
        # Phone match
        if door["phone"] and prac.phone:
            prac_phone = normalize_phone(prac.phone)
            if prac_phone and prac_phone == door["phone"]:
                return prac, "phone", 100

        # Address similarity
        prac_addr = normalize_address(prac.address or "")
        if prac_addr and door["normalized_address"]:
            addr_score = fuzz.token_sort_ratio(door["normalized_address"], prac_addr)
            if addr_score >= 85 and addr_score > best_score:
                best_match = prac
                best_score = addr_score
                best_method = "address"

        # Name similarity
        door_name = (door["practice_name"] or "").lower()
        prac_name = (prac.practice_name or "").lower()
        prac_dba = (prac.doing_business_as or "").lower()
        if door_name:
            for compare_name in (prac_name, prac_dba):
                if compare_name:
                    name_score = fuzz.token_sort_ratio(door_name, compare_name)
                    if name_score >= 80 and name_score > best_score:
                        best_match = prac
                        best_score = name_score
                        best_method = "name"

    if best_match and best_score >= 80:
        return best_match, best_method, best_score
    return None, None, 0


def upsert_doors_to_db(session, engine, doors, batch_id, today):
    """Insert or update doors in the practices table."""
    from sqlalchemy import text
    stats = {"matched": 0, "new": 0, "errors": 0}
    match_details = []

    for i, door in enumerate(doors):
        try:
            matched, method, score = match_existing_practice(session, door)

            if matched:
                # Enrich existing practice — don't overwrite NPPES core fields
                npi = matched.npi
                updates = {}
                if door["employee_count"] is not None:
                    updates["employee_count"] = door["employee_count"]
                if door["estimated_revenue"] is not None:
                    updates["estimated_revenue"] = door["estimated_revenue"]
                if door["year_established"] is not None:
                    updates["year_established"] = door["year_established"]
                if door["num_providers"]:
                    updates["num_providers"] = door["num_providers"]
                if door["location_type"]:
                    updates["location_type"] = door["location_type"]
                updates["buyability_score"] = door["buyability_score"]
                updates["classification_confidence"] = door["classification_confidence"]
                updates["classification_reasoning"] = door["classification_reasoning"]
                updates["data_axle_raw_name"] = door["practice_name"]
                updates["data_axle_import_date"] = today.isoformat()
                updates["raw_record_count"] = door["raw_record_count"]
                updates["import_batch_id"] = batch_id

                # Update ownership if Data Axle is more specific
                if (door["ownership_status"] in ("dso_affiliated", "pe_backed") and
                        matched.ownership_status in ("unknown", None)):
                    updates["ownership_status"] = door["ownership_status"]
                    if door["affiliated_dso"]:
                        updates["affiliated_dso"] = door["affiliated_dso"]
                    if door["affiliated_pe_sponsor"]:
                        updates["affiliated_pe_sponsor"] = door["affiliated_pe_sponsor"]

                if updates:
                    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                    updates["npi"] = npi
                    session.execute(
                        text(f"UPDATE practices SET {set_clauses} WHERE npi = :npi"),
                        updates
                    )

                stats["matched"] += 1
                match_details.append({
                    "door": door, "npi": npi, "method": method,
                    "score": score, "action": "enriched",
                })

            else:
                # Insert new practice with synthetic NPI
                npi = generate_synthetic_npi(door)

                # Check if synthetic NPI already exists (re-import)
                existing = session.query(Practice).filter_by(npi=npi).first()
                if existing:
                    # Update existing DA record
                    updates = {
                        "practice_name": door["practice_name"],
                        "doing_business_as": door.get("dba_name"),
                        "address": door["address"],
                        "city": door["city"],
                        "state": door["state"],
                        "zip": door["zip"],
                        "phone": door["phone"],
                        "ownership_status": door["ownership_status"],
                        "affiliated_dso": door["affiliated_dso"],
                        "affiliated_pe_sponsor": door["affiliated_pe_sponsor"],
                        "employee_count": door["employee_count"],
                        "estimated_revenue": door["estimated_revenue"],
                        "year_established": door["year_established"],
                        "num_providers": door["num_providers"],
                        "location_type": door["location_type"],
                        "buyability_score": door["buyability_score"],
                        "classification_confidence": door["classification_confidence"],
                        "classification_reasoning": door["classification_reasoning"],
                        "data_axle_raw_name": door["practice_name"],
                        "data_axle_import_date": today.isoformat(),
                        "raw_record_count": door["raw_record_count"],
                        "import_batch_id": batch_id,
                    }
                    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                    updates["npi"] = npi
                    session.execute(
                        text(f"UPDATE practices SET {set_clauses} WHERE npi = :npi"),
                        updates
                    )
                    stats["matched"] += 1
                    match_details.append({
                        "door": door, "npi": npi, "method": "synthetic_npi",
                        "score": 100, "action": "updated",
                    })
                else:
                    # Fresh insert
                    session.execute(
                        text("""INSERT INTO practices
                            (npi, practice_name, doing_business_as, address, city,
                             state, zip, phone, ownership_status, affiliated_dso,
                             affiliated_pe_sponsor, data_source, employee_count,
                             estimated_revenue, year_established, num_providers,
                             location_type, buyability_score, classification_confidence,
                             classification_reasoning, data_axle_raw_name,
                             data_axle_import_date, raw_record_count, import_batch_id)
                            VALUES
                            (:npi, :practice_name, :dba, :address, :city,
                             :state, :zip, :phone, :ownership_status, :affiliated_dso,
                             :pe_sponsor, :data_source, :employee_count,
                             :estimated_revenue, :year_established, :num_providers,
                             :location_type, :buyability_score, :classification_confidence,
                             :classification_reasoning, :data_axle_raw_name,
                             :import_date, :raw_record_count, :import_batch_id)"""),
                        {
                            "npi": npi,
                            "practice_name": door["practice_name"],
                            "dba": door.get("dba_name"),
                            "address": door["address"],
                            "city": door["city"],
                            "state": door["state"],
                            "zip": door["zip"],
                            "phone": door["phone"],
                            "ownership_status": door["ownership_status"],
                            "affiliated_dso": door["affiliated_dso"],
                            "pe_sponsor": door["affiliated_pe_sponsor"],
                            "data_source": "data_axle",
                            "employee_count": door["employee_count"],
                            "estimated_revenue": door["estimated_revenue"],
                            "year_established": door["year_established"],
                            "num_providers": door["num_providers"],
                            "location_type": door["location_type"],
                            "buyability_score": door["buyability_score"],
                            "classification_confidence": door["classification_confidence"],
                            "classification_reasoning": door["classification_reasoning"],
                            "data_axle_raw_name": door["practice_name"],
                            "import_date": today.isoformat(),
                            "raw_record_count": door["raw_record_count"],
                            "import_batch_id": batch_id,
                        }
                    )
                    stats["new"] += 1
                    match_details.append({
                        "door": door, "npi": npi, "method": None,
                        "score": 0, "action": "inserted",
                    })

            door["_npi"] = npi

        except Exception as e:
            log.error("Error upserting door %d (%s): %s",
                      i, door.get("practice_name", "?"), e)
            stats["errors"] += 1

    session.commit()
    log.info("DB upsert: %d matched, %d new, %d errors", stats["matched"], stats["new"], stats["errors"])
    return stats, match_details


# ═══════════════════════════════════════════════════════════════════════════════
# PART 6 — CHANGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════════


def detect_changes(session, doors, batch_id, today):
    """Compare current batch vs previous Data Axle imports."""
    from sqlalchemy import text
    changes = {
        "new_practices": [],
        "possible_closures": [],
        "field_changes": [],
        "acquisition_signals": [],
    }

    # Get all watched ZIPs
    watched = session.query(WatchedZip.zip_code).all()
    watched_zips = {z[0] for z in watched}

    # Get previous DA records in watched ZIPs
    prev_records = session.execute(
        text("""SELECT npi, practice_name, address, zip, import_batch_id
                FROM practices
                WHERE data_source = 'data_axle'
                AND import_batch_id != :batch_id
                AND zip IN :zips"""),
        {"batch_id": batch_id, "zips": tuple(watched_zips) if watched_zips else ("",)}
    ).fetchall() if watched_zips else []

    # Build lookup of current doors by (normalized_address, zip)
    current_keys = set()
    for door in doors:
        if door["zip"] in watched_zips:
            current_keys.add((door["normalized_address"], door["zip"]))

    # Check for closures
    for row in prev_records:
        prev_npi, prev_name, prev_addr, prev_zip, prev_batch = row
        prev_norm = normalize_address(prev_addr or "")
        if (prev_norm, prev_zip) not in current_keys:
            changes["possible_closures"].append({
                "npi": prev_npi, "name": prev_name,
                "address": prev_addr, "zip": prev_zip,
                "prev_batch": prev_batch,
            })
            try:
                log_practice_change(
                    session, npi=prev_npi, change_date=today,
                    field_changed="presence",
                    old_value=f"found in batch {prev_batch}",
                    new_value=f"NOT found in batch {batch_id}",
                    change_type="closure",
                    notes=f"Not found in Data Axle export {batch_id} — possible closure",
                )
            except Exception as e:
                log.warning("Could not log closure for %s: %s", prev_npi, e)

    # Check for acquisition signals (name changes)
    for door in doors:
        npi = door.get("_npi")
        if not npi:
            continue
        prev = session.execute(
            text("SELECT practice_name, data_axle_raw_name FROM practices WHERE npi = :npi"),
            {"npi": npi}
        ).fetchone()
        if not prev:
            changes["new_practices"].append(door)
            continue

        old_name = prev[1] or prev[0] or ""
        new_name = door["practice_name"] or ""
        if old_name and new_name and old_name.lower() != new_name.lower():
            change = {
                "npi": npi, "old_name": old_name, "new_name": new_name,
                "address": door["address"], "zip": door["zip"],
            }
            changes["field_changes"].append(change)

            # Check if this is an acquisition (personal name -> DSO)
            old_looks_personal = bool(re.search(
                r"(?:^dr\.?\s|\bdds\b|\bdmd\b|\bfamily\b)", old_name, re.IGNORECASE
            ))
            new_status, new_dso, _, _, _ = classify_practice(new_name, "")
            if old_looks_personal and new_status in ("dso_affiliated", "pe_backed"):
                log.info("ACQUISITION DETECTED: %s -> %s at %s %s",
                         old_name, new_name, door["address"], door["zip"])
                changes["acquisition_signals"].append(change)
                try:
                    log_practice_change(
                        session, npi=npi, change_date=today,
                        field_changed="practice_name",
                        old_value=old_name, new_value=new_name,
                        change_type="acquisition",
                        notes=f"Name changed to DSO: {new_dso or new_name}",
                    )
                except Exception as e:
                    log.warning("Could not log acquisition for %s: %s", npi, e)

    log.info("Changes: %d new, %d possible closures, %d field changes, %d acquisitions",
             len(changes["new_practices"]), len(changes["possible_closures"]),
             len(changes["field_changes"]), len(changes["acquisition_signals"]))
    return changes


# ═══════════════════════════════════════════════════════════════════════════════
# PART 7 — HTML DEBUG REPORT
# ═══════════════════════════════════════════════════════════════════════════════


def _esc(val):
    """HTML-escape a value."""
    return html_lib.escape(str(val)) if val else ""


def _color_class(score):
    """Return CSS class based on confidence/score."""
    if score >= 80:
        return "green"
    elif score >= 50:
        return "yellow"
    return "red"


def generate_html_report(report_data, output_path):
    """Generate self-contained HTML debug report."""

    batch_id = report_data.get("batch_id", "N/A")
    timestamp = report_data.get("timestamp", "")
    import_stats = report_data.get("import_stats", {})
    col_details = report_data.get("column_details", [])
    dedup_report = report_data.get("dedup_report", {})
    doors = report_data.get("doors", [])
    classification_summary = report_data.get("classification_summary", {})
    match_details = report_data.get("match_details", [])
    changes = report_data.get("changes", {})
    source_files = report_data.get("source_files", [])

    stealth = [d for d in doors if d.get("stealth_dso_signals")]
    top_buyable = sorted(
        [d for d in doors if d["buyability_score"] > 0],
        key=lambda d: -d["buyability_score"]
    )[:30]

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Data Axle Import Report — {_esc(batch_id)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; color: #1a1a1a; max-width: 1400px; }}
h1 {{ font-size: 22px; }}
h2 {{ color: #333; border-bottom: 2px solid #ddd; padding-bottom: 6px; margin-top: 40px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f5f5f5; font-weight: 600; }}
tr:nth-child(even) {{ background: #fafafa; }}
.green {{ background: #d4edda; }}
.yellow {{ background: #fff3cd; }}
.red {{ background: #f8d7da; }}
.toc {{ background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 24px; }}
.toc a {{ display: block; margin: 4px 0; color: #0366d6; text-decoration: none; }}
.stat {{ display: inline-block; background: #f0f0f0; padding: 8px 16px; margin: 4px; border-radius: 6px; text-align: center; }}
.stat b {{ font-size: 20px; display: block; }}
.mono {{ font-family: 'SF Mono', monospace; font-size: 12px; }}
</style></head><body>
<h1>Data Axle Import Debug Report</h1>
<p>Batch: <b>{_esc(batch_id)}</b> | Generated: {_esc(timestamp)}</p>
<p>Source files: {_esc(', '.join(source_files))}</p>
""")

    # Table of contents
    html_parts.append("""<div class="toc"><b>Table of Contents</b>
<a href="#s1">1. Import Summary</a>
<a href="#s2">2. Column Mapping</a>
<a href="#s3">3. Dedup Detail</a>
<a href="#s4">4. Classification Detail</a>
<a href="#s5">5. Stealth DSO Suspects</a>
<a href="#s6">6. Buyability Ranking</a>
<a href="#s7">7. NPPES Match Results</a>
<a href="#s8">8. Change Detection</a>
</div>""")

    # ── Section 1: Import Summary ─────────────────────────────────────────
    raw_total = import_stats.get("raw_total", 0)
    valid = import_stats.get("valid", 0)
    skipped = import_stats.get("skipped", 0)
    non_dental = import_stats.get("non_dental", 0)
    html_parts.append(f"""<h2 id="s1">1. Import Summary</h2>
<div>
<span class="stat"><b>{raw_total}</b>Raw Records</span>
<span class="stat"><b>{valid}</b>Valid Dental</span>
<span class="stat"><b>{skipped}</b>Skipped</span>
<span class="stat"><b>{non_dental}</b>Non-Dental</span>
<span class="stat"><b>{len(doors)}</b>Unique Doors</span>
</div>""")

    skip_reasons = import_stats.get("skip_reasons", {})
    if skip_reasons:
        html_parts.append("<h3>Skip Reasons</h3><table><tr><th>Reason</th><th>Count</th></tr>")
        for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1]):
            html_parts.append(f"<tr><td>{_esc(reason)}</td><td>{count}</td></tr>")
        html_parts.append("</table>")

    # ── Section 2: Column Mapping ─────────────────────────────────────────
    html_parts.append('<h2 id="s2">2. Column Mapping</h2>')
    if col_details:
        html_parts.append("<table><tr><th>CSV Column</th><th>Mapped To</th><th>Confidence</th></tr>")
        for csv_col, mapped, score in sorted(col_details, key=lambda x: -(x[2] or 0)):
            cls = _color_class(score) if mapped and not str(mapped).startswith("(") else "yellow"
            mapped_str = mapped or "UNMAPPED"
            html_parts.append(f'<tr class="{cls}"><td>{_esc(csv_col)}</td>'
                              f'<td>{_esc(mapped_str)}</td><td>{score}%</td></tr>')
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No CSV files processed.</p>")

    # ── Section 3: Dedup Detail ───────────────────────────────────────────
    clusters = dedup_report.get("clusters", [])
    fuzzy = dedup_report.get("fuzzy_matches", [])
    answering = dedup_report.get("answering_services", [])
    html_parts.append(f"""<h2 id="s3">3. Dedup Detail</h2>
<p>{raw_total} raw records &rarr; {len(doors)} unique doors
({len(clusters)} clusters collapsed)</p>""")

    if clusters:
        html_parts.append(f"<h3>Collapsed Clusters (showing up to 50)</h3>")
        for ci, cl in enumerate(clusters[:50]):
            recs = cl["records"]
            door = cl["door"]
            html_parts.append(f'<details><summary>Cluster {ci+1}: {cl["count"]} records '
                              f'&rarr; <b>{_esc(door["practice_name"])}</b> '
                              f'({_esc(door["address"])}, {_esc(door["zip"])})</summary>')
            html_parts.append('<table><tr><th>Company</th><th>DBA</th><th>Address</th>'
                              '<th>Phone</th><th>Contact</th></tr>')
            for rec in recs:
                html_parts.append(
                    f'<tr><td>{_esc(rec.get("company_name"))}</td>'
                    f'<td>{_esc(rec.get("dba_name"))}</td>'
                    f'<td>{_esc(rec.get("address"))}</td>'
                    f'<td>{_esc(rec.get("phone"))}</td>'
                    f'<td>{_esc(rec.get("contact_name"))}</td></tr>'
                )
            html_parts.append("</table></details>")

    if fuzzy:
        html_parts.append(f"<h3>Fuzzy Address Matches ({len(fuzzy)})</h3>")
        html_parts.append("<table><tr><th>Address A</th><th>Address B</th>"
                          "<th>ZIP</th><th>Score</th></tr>")
        for fm in fuzzy[:30]:
            html_parts.append(f'<tr class="yellow"><td>{_esc(fm["addr_a"])}</td>'
                              f'<td>{_esc(fm["addr_b"])}</td>'
                              f'<td>{fm["zip"]}</td><td>{fm["score"]}%</td></tr>')
        html_parts.append("</table>")

    if answering:
        html_parts.append(f"<h3>Possible Answering Services ({len(answering)})</h3>")
        html_parts.append("<table><tr><th>Phone</th><th>ZIP</th><th>Addresses</th></tr>")
        for a in answering:
            html_parts.append(f'<tr><td>{_esc(a["phone"])}</td>'
                              f'<td>{a["zip"]}</td><td>{a["address_count"]}</td></tr>')
        html_parts.append("</table>")

    # ── Section 4: Classification Detail ──────────────────────────────────
    html_parts.append(f'<h2 id="s4">4. Classification Detail</h2>')
    html_parts.append("<div>")
    for status, count in sorted(classification_summary.items()):
        html_parts.append(f'<span class="stat"><b>{count}</b>{_esc(status)}</span>')
    html_parts.append("</div>")

    # Show all doors sorted by confidence ascending
    sorted_doors = sorted(doors, key=lambda d: d["classification_confidence"])
    html_parts.append(f"<h3>All Doors by Confidence (lowest first, showing up to 100)</h3>")
    html_parts.append("<table><tr><th>Practice</th><th>Address</th><th>ZIP</th>"
                      "<th>Status</th><th>Confidence</th><th>Reasoning</th></tr>")
    for door in sorted_doors[:100]:
        cls = _color_class(door["classification_confidence"])
        html_parts.append(
            f'<tr class="{cls}"><td>{_esc(door["practice_name"])}</td>'
            f'<td>{_esc(door["address"])}</td><td>{door["zip"]}</td>'
            f'<td>{_esc(door["ownership_status"])}</td>'
            f'<td>{door["classification_confidence"]}%</td>'
            f'<td class="mono">{_esc(door["classification_reasoning"])}</td></tr>'
        )
    html_parts.append("</table>")

    # ── Section 5: Stealth DSO Suspects ───────────────────────────────────
    html_parts.append(f'<h2 id="s5">5. Stealth DSO Suspects ({len(stealth)})</h2>')
    if stealth:
        html_parts.append("<table><tr><th>Practice</th><th>Address</th><th>ZIP</th>"
                          "<th>Employees</th><th>Signals</th></tr>")
        for door in sorted(stealth, key=lambda d: -len(d["stealth_dso_signals"])):
            html_parts.append(
                f'<tr class="yellow"><td>{_esc(door["practice_name"])}</td>'
                f'<td>{_esc(door["address"])}</td><td>{door["zip"]}</td>'
                f'<td>{door.get("employee_count") or "—"}</td>'
                f'<td class="mono">{_esc("; ".join(door["stealth_dso_signals"]))}</td></tr>'
            )
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No stealth DSO suspects found.</p>")

    # ── Section 6: Buyability Ranking ─────────────────────────────────────
    html_parts.append(f'<h2 id="s6">6. Buyability Ranking (Top 30)</h2>')
    if top_buyable:
        html_parts.append("<table><tr><th>#</th><th>Score</th><th>Practice</th>"
                          "<th>Address</th><th>ZIP</th><th>Est.</th><th>Emp</th>"
                          "<th>Revenue</th><th>Breakdown</th></tr>")
        for rank, door in enumerate(top_buyable, 1):
            rev_str = f"${door['estimated_revenue']:,}" if door.get("estimated_revenue") else "—"
            bd = "; ".join(f"{f}: {a:+d}" for f, a, _ in door.get("buyability_breakdown", [])
                          if f != "base")
            html_parts.append(
                f'<tr><td>{rank}</td><td><b>{door["buyability_score"]}</b></td>'
                f'<td>{_esc(door["practice_name"])}</td>'
                f'<td>{_esc(door["address"])}</td><td>{door["zip"]}</td>'
                f'<td>{door.get("year_established") or "—"}</td>'
                f'<td>{door.get("employee_count") or "—"}</td>'
                f'<td>{rev_str}</td>'
                f'<td class="mono">{_esc(bd)}</td></tr>'
            )
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No buyable doors scored.</p>")

    # ── Section 7: NPPES Match Results ────────────────────────────────────
    html_parts.append(f'<h2 id="s7">7. NPPES Match Results</h2>')
    if match_details:
        matched = [m for m in match_details if m["method"]]
        unmatched = [m for m in match_details if not m["method"]]
        html_parts.append(f"<p>Matched to existing NPPES: <b>{len(matched)}</b> | "
                          f"New (Data Axle only): <b>{len(unmatched)}</b></p>")

        # Method breakdown
        methods = defaultdict(int)
        for m in matched:
            methods[m["method"]] += 1
        if methods:
            html_parts.append("<h3>Match Methods</h3><table><tr><th>Method</th><th>Count</th></tr>")
            for method, count in sorted(methods.items()):
                html_parts.append(f"<tr><td>{_esc(method)}</td><td>{count}</td></tr>")
            html_parts.append("</table>")

        # Show matched details
        if matched:
            html_parts.append(f"<h3>Matched Doors (showing up to 50)</h3>")
            html_parts.append("<table><tr><th>Practice</th><th>NPI</th><th>Method</th>"
                              "<th>Score</th><th>Action</th></tr>")
            for m in matched[:50]:
                cls = _color_class(m["score"])
                html_parts.append(
                    f'<tr class="{cls}"><td>{_esc(m["door"]["practice_name"])}</td>'
                    f'<td class="mono">{_esc(m["npi"])}</td>'
                    f'<td>{_esc(m["method"])}</td><td>{m["score"]}%</td>'
                    f'<td>{_esc(m["action"])}</td></tr>'
                )
            html_parts.append("</table>")
    else:
        html_parts.append("<p>No database matching performed (preview mode).</p>")

    # ── Section 8: Change Detection ───────────────────────────────────────
    html_parts.append(f'<h2 id="s8">8. Change Detection</h2>')
    if changes:
        new = changes.get("new_practices", [])
        closures = changes.get("possible_closures", [])
        field_ch = changes.get("field_changes", [])
        acquisitions = changes.get("acquisition_signals", [])
        html_parts.append(f"<div>"
                          f'<span class="stat"><b>{len(new)}</b>New Practices</span>'
                          f'<span class="stat"><b>{len(closures)}</b>Possible Closures</span>'
                          f'<span class="stat"><b>{len(field_ch)}</b>Field Changes</span>'
                          f'<span class="stat"><b>{len(acquisitions)}</b>Acquisitions</span>'
                          f"</div>")

        if acquisitions:
            html_parts.append('<h3>Acquisition Signals</h3>')
            html_parts.append('<table><tr><th>Old Name</th><th>New Name</th>'
                              '<th>Address</th><th>ZIP</th></tr>')
            for a in acquisitions:
                html_parts.append(
                    f'<tr class="red"><td>{_esc(a["old_name"])}</td>'
                    f'<td>{_esc(a["new_name"])}</td>'
                    f'<td>{_esc(a["address"])}</td><td>{a["zip"]}</td></tr>'
                )
            html_parts.append("</table>")

        if closures:
            html_parts.append(f'<h3>Possible Closures ({len(closures)}, showing up to 30)</h3>')
            html_parts.append('<table><tr><th>Name</th><th>Address</th>'
                              '<th>ZIP</th><th>Last Batch</th></tr>')
            for c in closures[:30]:
                html_parts.append(
                    f'<tr class="yellow"><td>{_esc(c["name"])}</td>'
                    f'<td>{_esc(c["address"])}</td>'
                    f'<td>{c["zip"]}</td><td>{_esc(c["prev_batch"])}</td></tr>'
                )
            html_parts.append("</table>")
    else:
        html_parts.append("<p>No previous import to compare against.</p>")

    html_parts.append("</body></html>")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    log.info("Debug report: %s", output_path)
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# PART 8 — INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


DOWNLOAD_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════╗
║          HOW TO EXPORT FROM DATA AXLE REFERENCE SOLUTIONS       ║
╚══════════════════════════════════════════════════════════════════╝

Step 1: Access Data Axle
  - Go to bu.edu/library
  - Search for 'Data Axle Reference Solutions' or 'ReferenceUSA'
  - Click through to access (you may need BU VPN if off campus)
  - Select 'U.S. Businesses' database

Step 2: Set up your search
  - Under 'Keyword/SIC/NAICS':
    Enter SIC code: 8021
    OR enter NAICS code: 621210
    (Both mean 'Offices of Dentists')

  - Under 'Geography' select 'ZIP Code' and enter your target ZIPs.

    CHICAGOLAND (copy-paste this entire line):
    60491,60439,60441,60540,60564,60565,60563,60527,60515,60516,60532,60559,60514,60521,60523,60148,60440,60490,60504,60502,60431,60435,60586,60585,60503,60554,60543,60560

    BOSTON METRO (copy-paste this entire line):
    02116,02115,02118,02119,02120,02215,02134,02135,02446,02445,02467,02459,02458,02453,02451,02138,02139,02140,02141,02142,02144

    TIP: You may need to run Chicagoland and Boston as two separate
    searches if the system has a ZIP code limit.

Step 3: Export
  - Click 'View Results'
  - Select ALL records (check 'Select All' or 'Select All on All Pages')
  - Click 'Download' or 'Export'
  - Choose CSV format
  - IMPORTANT: Select ALL available fields. Check every checkbox.
    The more fields you export, the better the analysis will be.
    Specifically make sure these are checked if available:
    * Company Name and DBA Name
    * Full Address including City State ZIP
    * Phone Number
    * SIC and NAICS codes and descriptions
    * Employee Size (both range and actual if available)
    * Annual Sales Volume or Sales Volume Range
    * Year Established
    * Ownership type (Public/Private)
    * Number of Locations or Location Type
    * Contact Name and Title
    * Latitude and Longitude (for future mapping)
  - Download the CSV

Step 4: Import
  - Save the CSV file to: ~/dental-pe-tracker/data/data-axle/
  - Open Terminal
  - Run: cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py
  - Review the debug report in ~/dental-pe-tracker/data/data-axle/debug-reports/
  - Check Section 3 (Dedup) and Section 5 (Stealth DSO Suspects) for errors
  - If anything looks wrong, tell Claude Code to fix it

Step 5: Re-export quarterly
  - Run the same Data Axle search every 3 months
  - Drop new CSV into the same folder
  - The importer will detect changes since last import and flag them
  - Watch for Section 8 (Change Detection) in the debug report —
    name changes at the same address = possible acquisitions
"""


def print_instructions():
    print(DOWNLOAD_INSTRUCTIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def run(preview=False, auto=False, instructions=False, zip_filter=None,
        debug=False, force_reclassify=False):
    """Main entry point."""

    if instructions:
        print_instructions()
        return

    log.info("=" * 60)
    log.info("Data Axle Importer starting (preview=%s, auto=%s, debug=%s)",
             preview, auto, debug)
    log.info("=" * 60)

    # Set debug logging if requested
    if debug:
        import logging
        for handler in log.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG)

    # Ensure directories
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)

    now = datetime.now()
    batch_id = f"DA_{now.strftime('%Y%m%d_%H%M')}"
    today = date.today()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Run inline tests
    try:
        _test_parse_revenue()
    except AssertionError as e:
        log.error("Revenue parsing test failed: %s", e)
        return

    # ── Handle --force-reclassify ─────────────────────────────────────────
    if force_reclassify:
        log.info("Force reclassify mode: re-classifying all Data Axle records")
        init_db()
        engine = get_engine()
        ensure_data_axle_columns(engine)
        session = get_session()

        da_practices = session.query(Practice).filter(
            Practice.data_source == "data_axle"
        ).all()
        log.info("Found %d Data Axle records to reclassify", len(da_practices))

        from sqlalchemy import text
        reclassified = 0
        for prac in da_practices:
            status, dso, pe, conf, reasoning = classify_practice(
                prac.practice_name, prac.doing_business_as
            )
            if pe and not dso:
                pe = PE_SPONSOR_MAP.get(dso)
            session.execute(
                text("""UPDATE practices SET
                    ownership_status = :status,
                    affiliated_dso = :dso,
                    affiliated_pe_sponsor = :pe,
                    classification_confidence = :conf,
                    classification_reasoning = :reasoning
                    WHERE npi = :npi"""),
                {"status": status, "dso": dso, "pe": pe, "conf": conf,
                 "reasoning": reasoning, "npi": prac.npi}
            )
            reclassified += 1

        session.commit()
        log.info("Reclassified %d Data Axle records", reclassified)
        session.close()
        return

    # ── Find CSV files ────────────────────────────────────────────────────
    csv_files = sorted(glob(os.path.join(RAW_DIR, "*.csv")))
    if not csv_files:
        log.info("No CSV files found in %s", RAW_DIR)
        print(f"\nNo CSV files found in {RAW_DIR}")
        print("Run with --instructions for export guide.")

        # Generate empty report
        report_path = os.path.join(DEBUG_DIR, f"data_axle_report_{batch_id}.html")
        generate_html_report({
            "batch_id": batch_id, "timestamp": timestamp,
            "import_stats": {"raw_total": 0, "valid": 0, "skipped": 0,
                             "non_dental": 0, "skip_reasons": {}},
            "column_details": [], "dedup_report": {},
            "doors": [], "classification_summary": {},
            "match_details": [], "changes": {}, "source_files": [],
        }, report_path)
        return

    log.info("Found %d CSV files", len(csv_files))

    # ── Phase 1: Import and validate ──────────────────────────────────────
    all_records = []
    all_col_details = []
    import_stats = {
        "raw_total": 0, "valid": 0, "skipped": 0,
        "non_dental": 0, "skip_reasons": defaultdict(int),
    }
    source_files = []

    for filepath in csv_files:
        filename = os.path.basename(filepath)
        source_files.append(filename)
        log.info("Processing: %s", filename)

        try:
            df, encoding = read_csv_file(filepath)
            if df is None:
                log.error("Failed to read %s", filename)
                continue

            # Detect columns
            mapping, details = detect_columns(list(df.columns))
            all_col_details.extend(details)

            print(f"\n{'='*60}")
            print(f"File: {filename} ({len(df)} rows, encoding: {encoding})")
            print_column_mapping(details, mapping)

            # Confirmation prompt (unless --auto)
            if not auto and not preview:
                try:
                    resp = input("  Proceed with this mapping? [Y/n] ").strip().lower()
                    if resp in ("n", "no"):
                        log.info("Skipping %s per user", filename)
                        continue
                except EOFError:
                    pass

            # Validate and parse rows
            for row_num, (_, row) in enumerate(df.iterrows(), start=2):
                import_stats["raw_total"] += 1
                try:
                    valid, reason, record = validate_record(row, mapping, row_num)
                    if not valid:
                        import_stats["skipped"] += 1
                        import_stats["skip_reasons"][reason] += 1
                        if "not dental" in (reason or "") or "excluded" in (reason or ""):
                            import_stats["non_dental"] += 1
                        if debug:
                            log.debug("Row %d skipped: %s", row_num, reason)
                        elif import_stats["skipped"] <= 20:
                            log.warning("Row %d skipped: %s", row_num, reason)
                        continue

                    # Apply ZIP filter
                    if zip_filter and record["zip"] != zip_filter:
                        continue

                    all_records.append(record)
                    import_stats["valid"] += 1

                    if import_stats["valid"] % 100 == 0:
                        log.info("  Processed %d valid records...", import_stats["valid"])

                except Exception as e:
                    log.error("Row %d error: %s", row_num, e)
                    import_stats["skipped"] += 1
                    import_stats["skip_reasons"]["parse_error"] += 1

        except Exception as e:
            log.error("Failed to process %s: %s", filename, e)

    log.info("Import phase: %d raw, %d valid, %d skipped (%d non-dental)",
             import_stats["raw_total"], import_stats["valid"],
             import_stats["skipped"], import_stats["non_dental"])

    if not all_records:
        log.info("No valid records to process")
        print("\nNo valid dental records found in CSV files.")
        report_path = os.path.join(DEBUG_DIR, f"data_axle_report_{batch_id}.html")
        generate_html_report({
            "batch_id": batch_id, "timestamp": timestamp,
            "import_stats": dict(import_stats),
            "column_details": all_col_details, "dedup_report": {},
            "doors": [], "classification_summary": {},
            "match_details": [], "changes": {}, "source_files": source_files,
        }, report_path)
        return

    # ── Phase 2: Deduplicate ──────────────────────────────────────────────
    log.info("Starting deduplication of %d records...", len(all_records))
    doors, dedup_report = deduplicate_records(all_records, debug=debug)

    # ── Phase 3: Classify ─────────────────────────────────────────────────
    log.info("Classifying %d doors...", len(doors))
    classification_summary = classify_all_doors(doors)

    # ── Phase 4: Buyability scoring ───────────────────────────────────────
    log.info("Computing buyability scores...")
    for door in doors:
        compute_buyability(door)

    # ── Preview mode: show results, generate report, exit ─────────────────
    if preview:
        _print_preview(doors)

        report_path = os.path.join(DEBUG_DIR, f"data_axle_report_{batch_id}.html")
        generate_html_report({
            "batch_id": batch_id, "timestamp": timestamp,
            "import_stats": dict(import_stats),
            "column_details": all_col_details,
            "dedup_report": dedup_report,
            "doors": doors,
            "classification_summary": classification_summary,
            "match_details": [],
            "changes": {},
            "source_files": source_files,
        }, report_path)
        print(f"\nDebug report: {report_path}")
        return

    # ── Phase 5: Database integration ─────────────────────────────────────
    log.info("Starting database integration...")
    init_db()
    engine = get_engine()
    ensure_data_axle_columns(engine)
    session = get_session()

    db_stats, match_details = upsert_doors_to_db(session, engine, doors, batch_id, today)

    # ── Phase 6: Change tracking ──────────────────────────────────────────
    log.info("Running change detection...")
    changes = detect_changes(session, doors, batch_id, today)

    session.close()

    # ── Phase 7: Debug report ─────────────────────────────────────────────
    report_path = os.path.join(DEBUG_DIR, f"data_axle_report_{batch_id}.html")
    generate_html_report({
        "batch_id": batch_id, "timestamp": timestamp,
        "import_stats": dict(import_stats),
        "column_details": all_col_details,
        "dedup_report": dedup_report,
        "doors": doors,
        "classification_summary": classification_summary,
        "match_details": match_details,
        "changes": changes,
        "source_files": source_files,
    }, report_path)

    # ── Move processed CSVs ──────────────────────────────────────────────
    for filepath in csv_files:
        filename = os.path.basename(filepath)
        dest = os.path.join(PROCESSED_DIR,
                            f"{now.strftime('%Y%m%d_%H%M')}_{filename}")
        try:
            shutil.move(filepath, dest)
            log.info("Moved %s -> processed/", filename)
        except Exception as e:
            log.warning("Could not move %s: %s", filename, e)

    # ── Final summary ─────────────────────────────────────────────────────
    print()
    log.info("=" * 60)
    log.info("DATA AXLE IMPORT COMPLETE")
    log.info("=" * 60)
    log.info("Batch ID:            %s", batch_id)
    log.info("Raw records:         %d", import_stats["raw_total"])
    log.info("Valid dental:        %d", import_stats["valid"])
    log.info("Skipped:             %d (non-dental: %d)",
             import_stats["skipped"], import_stats["non_dental"])
    log.info("Unique doors:        %d", len(doors))
    log.info("DB matched:          %d", db_stats["matched"])
    log.info("DB new inserts:      %d", db_stats["new"])
    log.info("DB errors:           %d", db_stats["errors"])
    log.info("Change detection:    %d new, %d closures, %d acquisitions",
             len(changes.get("new_practices", [])),
             len(changes.get("possible_closures", [])),
             len(changes.get("acquisition_signals", [])))
    log.info("Classification:      %s", classification_summary)
    log.info("Debug report:        %s", report_path)
    log.info("=" * 60)


def _print_preview(doors):
    """Print preview of deduped, classified, scored doors."""
    print(f"\n{'='*80}")
    print(f"  PREVIEW: {len(doors)} unique doors")
    print(f"{'='*80}\n")

    header = (f"  {'Practice Name':<35} {'Address':<25} {'ZIP':5} "
              f"{'Status':<15} {'Conf':>4} {'Buy':>3} {'Emp':>3} {'Rev':>10}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for door in sorted(doors, key=lambda d: -d["buyability_score"])[:50]:
        rev = f"${door['estimated_revenue']:,}" if door.get("estimated_revenue") else "—"
        emp = str(door.get("employee_count") or "—")
        name = (door["practice_name"] or "")[:35]
        addr = (door["address"] or "")[:25]
        print(f"  {name:<35} {addr:<25} {door['zip']:5} "
              f"{door['ownership_status']:<15} {door['classification_confidence']:>4} "
              f"{door['buyability_score']:>3} {emp:>3} {rev:>10}")

    print(f"\n  Showing top 50 by buyability score. Full details in debug report.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import Data Axle Reference Solutions dental practice CSV exports",
        epilog="Run with --instructions for step-by-step Data Axle export guide.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--preview", action="store_true",
                        help="Parse, dedup, classify, score — but don't write to database")
    parser.add_argument("--auto", action="store_true",
                        help="Skip column mapping confirmation prompt")
    parser.add_argument("--instructions", action="store_true",
                        help="Print Data Axle export instructions and exit")
    parser.add_argument("--zip-filter", type=str, metavar="XXXXX",
                        help="Only process records in this ZIP code")
    parser.add_argument("--debug", action="store_true",
                        help="Extra verbose logging (every dedup decision, classification rule)")
    parser.add_argument("--force-reclassify", action="store_true",
                        help="Re-run classification on all existing Data Axle records in DB")
    args = parser.parse_args()
    run(preview=args.preview, auto=args.auto, instructions=args.instructions,
        zip_filter=args.zip_filter, debug=args.debug,
        force_reclassify=args.force_reclassify)
