"""
PitchBook Importer — reads CSV/XLSX exports from PitchBook's Deal or Company
search and imports them into the dental PE tracker database.

Usage:
    python3 scrapers/pitchbook_importer.py                # interactive import
    python3 scrapers/pitchbook_importer.py --auto          # skip confirmation
    python3 scrapers/pitchbook_importer.py --preview       # show first 10 rows only
"""

import argparse
import os
import re
import shutil
import sys
from datetime import date, datetime
from glob import glob

import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete
from scrapers.database import init_db, get_session, insert_deal

log = get_logger("pitchbook_importer")

RAW_DIR = os.path.expanduser("~/dental-pe-tracker/data/pitchbook/raw")
PROCESSED_DIR = os.path.expanduser("~/dental-pe-tracker/data/pitchbook/processed")

# ── Column Mapping ──────────────────────────────────────────────────────────

# Each target field → list of candidate column names (ranked by preference)
FIELD_CANDIDATES = {
    "deal_date": [
        "Deal Date", "Close Date", "Date", "Transaction Date",
        "Closed Date", "Completion Date", "Announced Date",
    ],
    "target_name": [
        "Company Name", "Company", "Target", "Target Company",
        "Target Name", "Portfolio Company", "Deal Target",
    ],
    "pe_sponsor": [
        "Investors", "Lead Investors", "Buyer", "Acquirer",
        "Primary Investor(s)", "Primary Investor", "Sponsor",
        "PE Sponsor", "Financial Sponsor", "Lead Investor",
    ],
    "deal_type_raw": [
        "Deal Type", "Deal Type 1", "Transaction Type",
        "Deal Type 2", "Type",
    ],
    "deal_size_raw": [
        "Deal Size", "Deal Size (million, USD)", "Deal Size (USD M)",
        "Deal Size ($M)", "Deal Value", "Enterprise Value", "EV (USD M)",
        "Deal Size (USDmm)", "Size (M)",
    ],
    "location_raw": [
        "Company State/Province", "Company Location", "HQ Location",
        "HQ State/Province", "Location", "Headquarters", "State",
        "HQ State", "Company HQ", "Target Location",
    ],
    "industry_raw": [
        "Sub-Industry", "Primary Industry", "Industry",
        "Sector", "Primary Industry Code", "Industry Group",
        "Vertical",
    ],
    "ebitda_multiple_raw": [
        "EBITDA Multiple", "EV/EBITDA", "EV / EBITDA",
        "Debt/EBITDA", "Entry Multiple", "Multiple",
    ],
    "platform_raw": [
        "Platform", "Platform Company", "Acquiror",
        "Acquiring Company", "Buyer Company",
    ],
    "ownership_raw": [
        "Ownership Status", "Ownership", "Status",
    ],
    "year_founded_raw": [
        "Year Founded", "Founded", "Founded Year",
    ],
    "employees_raw": [
        "# of Employees", "Employees", "Employee Count",
        "Number of Employees",
    ],
    "total_raised_raw": [
        "Total Raised", "Total Raised (USD M)", "Capital Raised",
    ],
}

# Deal type mapping
DEAL_TYPE_MAP = {
    "lbo": "buyout",
    "leveraged buyout": "buyout",
    "buyout": "buyout",
    "platform": "buyout",
    "add-on": "add-on",
    "add on": "add-on",
    "bolt-on": "add-on",
    "bolt on": "add-on",
    "recap": "recapitalization",
    "recapitalization": "recapitalization",
    "growth/expansion": "growth",
    "growth equity": "growth",
    "growth": "growth",
    "expansion": "growth",
    "m&a": "other",
    "merger/acquisition": "other",
    "merger": "other",
    "acquisition": "add-on",
    "de novo": "de_novo",
    "partnership": "partnership",
}

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


# ── Column Detection ────────────────────────────────────────────────────────


def detect_column_mapping(df_columns):
    """Auto-detect which DataFrame columns map to our target fields.
    Returns dict of {target_field: df_column_name}."""
    mapping = {}
    used_cols = set()

    for field, candidates in FIELD_CANDIDATES.items():
        best_col = None
        best_score = 0

        for df_col in df_columns:
            if df_col in used_cols:
                continue
            df_col_str = str(df_col).strip()

            # Exact match first
            for cand in candidates:
                if df_col_str.lower() == cand.lower():
                    best_col = df_col
                    best_score = 100
                    break

            if best_score == 100:
                break

            # Fuzzy match
            for cand in candidates:
                score = fuzz.token_sort_ratio(df_col_str.lower(), cand.lower())
                if score > best_score and score >= 80:
                    best_col = df_col
                    best_score = score

        if best_col and best_score >= 80:
            mapping[field] = best_col
            used_cols.add(best_col)
            log.info("  Mapped '%s' → %s (score=%d)", best_col, field, best_score)

    return mapping


# ── Field Parsing ───────────────────────────────────────────────────────────


def parse_deal_date(val):
    """Parse various date formats into a date object."""
    if pd.isna(val):
        return None
    if isinstance(val, (datetime, date)):
        if isinstance(val, datetime):
            return val.date()
        return val
    s = str(val).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%b-%Y",
                "%b %d, %Y", "%B %d, %Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Try pandas
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def parse_deal_type(val):
    """Map PitchBook deal type to our schema."""
    if pd.isna(val):
        return "other"
    s = str(val).strip().lower()
    for key, mapped in DEAL_TYPE_MAP.items():
        if key in s:
            return mapped
    return "other"


def parse_deal_size(val):
    """Parse deal size in millions. PitchBook exports values already in $M."""
    if pd.isna(val):
        return None
    s = str(val).strip().replace("$", "").replace(",", "").replace("M", "").replace("m", "").strip()
    try:
        f = float(s)
        if f <= 0:
            return None
        # If value > 1000, it's likely in thousands not millions (e.g., "12500" = $12.5M)
        # PitchBook typically exports in millions, so values > 5000 are suspicious
        if f > 5000:
            return round(f / 1000, 2)
        return round(f, 2)
    except ValueError:
        return None


def parse_ebitda_multiple(val):
    """Parse EBITDA multiple."""
    if pd.isna(val):
        return None
    s = str(val).strip().replace("x", "").replace("X", "").replace(",", "")
    try:
        f = float(s)
        return round(f, 1) if 0 < f < 100 else None
    except ValueError:
        return None


def parse_state(val):
    """Extract 2-letter state code from location string."""
    if pd.isna(val):
        return None
    s = str(val).strip()

    # Try to find 2-letter code
    for m in re.finditer(r'\b([A-Z]{2})\b', s):
        if m.group(1) in VALID_ABBREVS:
            return m.group(1)

    # Try full state name
    s_lower = s.lower()
    for name, abbrev in STATE_MAP.items():
        if name in s_lower:
            return abbrev

    # Try "City, ST" pattern
    m = re.search(r',\s*([A-Z]{2})\b', s)
    if m and m.group(1) in VALID_ABBREVS:
        return m.group(1)

    return None


def parse_pe_sponsor(val):
    """Clean PE sponsor name."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "n/a", "-", "—", "none", "undisclosed"):
        return None
    # Take first sponsor if comma-separated
    first = s.split(",")[0].strip()
    # Remove common suffixes
    for suffix in (" LLC", " LP", " Inc.", " Inc", " Ltd.", " Ltd",
                   " Capital Partners", " Management"):
        if first.endswith(suffix) and len(first) > len(suffix) + 3:
            pass  # keep the full name for these — they're part of the firm name
    return first if len(first) > 1 else None


def is_dental_row(row, mapping):
    """Check if a row is related to dental industry."""
    dental_re = re.compile(
        r"dental|orthodont|endodont|periodont|oral\s+surg|dso\b|dentist|"
        r"dent\b|smile|tooth|teeth|pediatric dent"
    )
    industry_col = mapping.get("industry_raw")
    if industry_col:
        val = str(row.get(industry_col, "")).lower()
        if dental_re.search(val):
            return True

    # Check target name, sponsor, and description for dental keywords
    for field in ("target_name", "platform_raw", "pe_sponsor"):
        col = mapping.get(field)
        if col:
            val = str(row.get(col, "")).lower()
            if dental_re.search(val):
                return True

    # Also check Description column directly (PitchBook always has it)
    desc = str(row.get("Description", "")).lower()
    if dental_re.search(desc):
        return True

    # If no industry column, assume all rows are dental (user should only
    # export dental deals from PitchBook)
    if not industry_col:
        return True

    return False


# ── Row Processing ──────────────────────────────────────────────────────────


def process_row(row, mapping, filename):
    """Parse a single row into a deal dict. Returns dict or None."""
    # Check dental relevance
    if not is_dental_row(row, mapping):
        return None

    deal_date = None
    if "deal_date" in mapping:
        deal_date = parse_deal_date(row.get(mapping["deal_date"]))

    target_name = None
    if "target_name" in mapping:
        val = row.get(mapping["target_name"])
        if not pd.isna(val):
            target_name = str(val).strip() or None

    platform = None
    if "platform_raw" in mapping:
        val = row.get(mapping["platform_raw"])
        if not pd.isna(val):
            platform = str(val).strip() or None

    pe_sponsor = None
    if "pe_sponsor" in mapping:
        pe_sponsor = parse_pe_sponsor(row.get(mapping["pe_sponsor"]))

    deal_type = "other"
    if "deal_type_raw" in mapping:
        deal_type = parse_deal_type(row.get(mapping["deal_type_raw"]))

    deal_size = None
    if "deal_size_raw" in mapping:
        deal_size = parse_deal_size(row.get(mapping["deal_size_raw"]))

    ebitda_mult = None
    if "ebitda_multiple_raw" in mapping:
        ebitda_mult = parse_ebitda_multiple(row.get(mapping["ebitda_multiple_raw"]))

    state = None
    if "location_raw" in mapping:
        state = parse_state(row.get(mapping["location_raw"]))

    # Platform vs target: for add-ons, the "Company" is the target
    # For buyouts, the "Company" is the platform
    platform_company = platform or target_name or "Unknown"
    if deal_type == "add-on" and target_name and platform:
        platform_company = platform
    elif deal_type == "buyout" and target_name:
        platform_company = target_name

    # Build raw_text for debugging
    raw_parts = []
    for col in row.index:
        val = row[col]
        if not pd.isna(val):
            raw_parts.append(f"{col}: {val}")
    raw_text = " | ".join(raw_parts)

    # Build notes from extra fields
    notes_parts = []
    for extra in ("employees_raw", "total_raised_raw", "year_founded_raw"):
        if extra in mapping:
            val = row.get(mapping[extra])
            if not pd.isna(val):
                label = extra.replace("_raw", "").replace("_", " ")
                notes_parts.append(f"{label}: {val}")

    return {
        "deal_date": deal_date,
        "platform_company": platform_company,
        "pe_sponsor": pe_sponsor,
        "target_name": target_name if target_name != platform_company else None,
        "target_state": state,
        "deal_type": deal_type,
        "deal_size_mm": deal_size,
        "ebitda_multiple": ebitda_mult,
        "source": "pitchbook",
        "source_url": None,
        "notes": "; ".join(notes_parts) if notes_parts else None,
        "raw_text": raw_text[:2000],
    }


# ── File Processing ─────────────────────────────────────────────────────────


def _detect_header_row(raw_df):
    """Find the header row in a PitchBook export by looking for known column names."""
    for i, row in raw_df.iterrows():
        cell_vals = [str(v).strip() for v in row.values if pd.notna(v)]
        if any(v in ("Deal Date", "Company Name", "Deal ID", "Deal Type 1") for v in cell_vals):
            return i
    return 0


def read_file(filepath):
    """Read a CSV or XLSX file into a DataFrame."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        # PitchBook CSVs have the same metadata rows as XLSX exports.
        # Auto-detect the header row.
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                raw = pd.read_csv(filepath, encoding=enc, header=None, nrows=20)
                header_row = _detect_header_row(raw)
                if header_row > 0:
                    log.info("CSV: detected header row at index %d", header_row)
                return pd.read_csv(filepath, encoding=enc, header=header_row)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(filepath, encoding="utf-8", errors="replace")
    elif ext in (".xlsx", ".xls"):
        raw = pd.read_excel(filepath, engine="openpyxl", header=None, nrows=20)
        header_row = _detect_header_row(raw)
        if header_row > 0:
            log.info("XLSX: detected header row at index %d", header_row)
        return pd.read_excel(filepath, engine="openpyxl", header=header_row)
    else:
        log.warning("Unsupported file type: %s", ext)
        return None


def process_file(filepath, auto=False, preview=False):
    """Process a single PitchBook export file.
    Returns (deals_imported, duplicates, errors) or None if skipped."""
    filename = os.path.basename(filepath)
    log.info("=" * 50)
    log.info("Processing: %s", filename)

    df = read_file(filepath)
    if df is None or df.empty:
        log.warning("Could not read or empty: %s", filename)
        return None

    log.info("Rows: %d, Columns: %d", len(df), len(df.columns))
    log.info("Columns found: %s", list(df.columns))

    # Detect mapping
    mapping = detect_column_mapping(df.columns)

    if not mapping:
        log.warning("Could not map any columns for %s", filename)
        return None

    # Print mapping summary
    print(f"\n--- Column Mapping for {filename} ---")
    for field, col in sorted(mapping.items()):
        print(f"  {col:35} → {field}")
    unmapped = [f for f in ("deal_date", "target_name", "pe_sponsor") if f not in mapping]
    if unmapped:
        print(f"  WARNING: Missing mappings for: {', '.join(unmapped)}")

    # Confirm mapping
    if not auto and not preview:
        answer = input("\nDoes this mapping look right? (y/n): ").strip().lower()
        if answer != "y":
            log.info("Skipped %s — mapping rejected by user", filename)
            return None

    # Process rows
    deals = []
    errors = 0
    skipped_non_dental = 0

    for idx, row in df.iterrows():
        try:
            deal = process_row(row, mapping, filename)
            if deal is None:
                skipped_non_dental += 1
                continue
            deals.append(deal)
        except Exception as e:
            log.warning("Row %d parse error: %s — raw: %s", idx, e, dict(row))
            errors += 1

    log.info("Parsed %d dental deals (%d non-dental skipped, %d errors)",
             len(deals), skipped_non_dental, errors)

    if preview:
        _print_preview(deals[:10])
        return None

    # Insert
    session = get_session()
    imported = 0
    duplicates = 0
    for deal in deals:
        try:
            result = insert_deal(session, **deal)
            if result:
                imported += 1
            else:
                duplicates += 1
        except Exception as e:
            log.error("Insert error: %s", e)
            errors += 1

    session.close()

    # Move to processed
    timestamp = datetime.now().strftime("%Y-%m-%d")
    dest = os.path.join(PROCESSED_DIR, f"{timestamp}_{filename}")
    shutil.move(filepath, dest)
    log.info("Moved to: %s", dest)

    return imported, duplicates, errors


def _print_preview(deals):
    """Print deals as a formatted preview table."""
    if not deals:
        print("\n  No deals to preview.\n")
        return

    print()
    header = (f"{'#':>3}  {'Date':10}  {'Platform/Target':30}  {'PE Sponsor':25}  "
              f"{'ST':2}  {'Type':10}  {'Size$M':>7}  {'Mult':>5}")
    print(header)
    print("-" * len(header))
    for i, d in enumerate(deals, 1):
        size = f"{d['deal_size_mm']:.1f}" if d.get("deal_size_mm") else "—"
        mult = f"{d['ebitda_multiple']:.1f}" if d.get("ebitda_multiple") else "—"
        print(
            f"{i:>3}  "
            f"{str(d.get('deal_date') or '—'):10}  "
            f"{(d.get('platform_company') or '?')[:30]:30}  "
            f"{(d.get('pe_sponsor') or '—')[:25]:25}  "
            f"{(d.get('target_state') or '??'):2}  "
            f"{(d.get('deal_type') or '?')[:10]:10}  "
            f"{size:>7}  "
            f"{mult:>5}"
        )
    print(f"\nShowing {len(deals)} deal(s)\n")


# ── Main ────────────────────────────────────────────────────────────────────


def run(auto=False, preview=False):
    _t0 = log_scrape_start("pitchbook_importer")
    log.info("=" * 60)
    log.info("PitchBook Importer starting (auto=%s, preview=%s)", auto, preview)
    log.info("=" * 60)

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    files = sorted(
        glob(os.path.join(RAW_DIR, "*.csv"))
        + glob(os.path.join(RAW_DIR, "*.xlsx"))
        + glob(os.path.join(RAW_DIR, "*.xls"))
    )

    if not files:
        print("No PitchBook files to import.")
        print(f"Drop CSV or XLSX exports into: {RAW_DIR}")
        log_scrape_complete("pitchbook_importer", _t0, new_records=0,
                            summary="PitchBook: No files to import")
        return

    if not preview:
        init_db()

    total_imported = 0
    total_duplicates = 0
    total_errors = 0
    files_processed = 0

    for filepath in files:
        result = process_file(filepath, auto=auto, preview=preview)
        if result is not None:
            imported, dups, errs = result
            total_imported += imported
            total_duplicates += dups
            total_errors += errs
            files_processed += 1

    if not preview:
        print()
        log.info("=" * 60)
        log.info("PITCHBOOK IMPORTER SUMMARY")
        log.info("=" * 60)
        log.info("Files processed:        %d", files_processed)
        log.info("Deals imported:         %d", total_imported)
        log.info("Duplicates skipped:     %d", total_duplicates)
        log.info("Errors:                 %d", total_errors)
        log.info("=" * 60)
        log_scrape_complete("pitchbook_importer", _t0, new_records=total_imported,
                            summary=f"PitchBook: {total_imported} deals imported, {total_duplicates} dupes, {files_processed} files",
                            extra={"files_processed": files_processed, "duplicates": total_duplicates})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import PitchBook exports into dental PE tracker")
    parser.add_argument("--auto", action="store_true", help="Skip mapping confirmation prompts")
    parser.add_argument("--preview", action="store_true", help="Show first 10 rows without importing")
    args = parser.parse_args()
    run(auto=args.auto, preview=args.preview)
