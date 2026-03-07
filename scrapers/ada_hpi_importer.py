"""
ADA HPI Importer — imports ADA Health Policy Institute XLSX files with
DSO affiliation data by state and career stage.

Usage:
    python3 scrapers/ada_hpi_importer.py              # import all XLSX files
    python3 scrapers/ada_hpi_importer.py --preview     # show parsed data without inserting
    python3 scrapers/ada_hpi_importer.py --help        # download instructions
"""

import argparse
import os
import re
import sys
from glob import glob

import pandas as pd

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete
from scrapers.database import init_db, get_session, ADAHPIBenchmark

log = get_logger("ada_hpi_importer")

DATA_DIR = os.path.expanduser("~/dental-pe-tracker/data/ada-hpi")

STATE_NAMES_TO_ABBREV = {
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
VALID_ABBREVS = set(STATE_NAMES_TO_ABBREV.values())

# Maps header text substrings to canonical career stage keys
HEADER_TO_CAREER_STAGE = [
    ("all dentists",    "all"),
    ("0 to 5",          "early_career_0_5"),
    ("6 to 10",         "early_career_6_10"),
    ("up to 10",        "early_career_lt10"),
    ("11 to 25",        "mid_career_11_25"),
    ("more than 25",    "late_career_gt25"),
]


def detect_year_from_filename(filepath):
    """Try to extract the data year from the filename."""
    base = os.path.basename(filepath).lower()
    m = re.search(r'(20[12]\d)', base)
    if m:
        return int(m.group(1))
    return None


def normalize_state(val):
    """Convert a state name or abbreviation to 2-letter code."""
    if not isinstance(val, str):
        return None
    v = val.strip()
    if len(v) == 2 and v.upper() in VALID_ABBREVS:
        return v.upper()
    v_lower = v.lower()
    if v_lower in STATE_NAMES_TO_ABBREV:
        return STATE_NAMES_TO_ABBREV[v_lower]
    return None


def safe_float(val):
    """Convert a value to float percentage, handling %, NaN, etc."""
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        if 0 <= f <= 1.0:
            return round(f * 100, 1)
        return round(f, 1)
    s = str(val).strip().replace("%", "").replace(",", "")
    try:
        f = float(s)
        if 0 <= f <= 1.0:
            return round(f * 100, 1)
        return round(f, 1)
    except ValueError:
        return None


def safe_int(val):
    """Convert a value to integer count."""
    if pd.isna(val):
        return None
    try:
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def process_xlsx(filepath):
    """Process a single ADA HPI XLSX file.

    The "DSO Affiliation - State Data" sheet has a merged-cell layout:
      Row 0-3: title / metadata
      Row 4:   headers — col 0 blank (states), col 1 "All Dentists",
               col 2 NaN spacer, cols 3-7 career stage labels
      Row 5+:  state name in col 0, DSO % (0-1 float) in cols 1,3-7

    Returns list of parsed benchmark dicts.
    """
    filename = os.path.basename(filepath)
    data_year = detect_year_from_filename(filepath)
    log.info("Processing: %s (detected year: %s)", filename, data_year)

    xls = pd.ExcelFile(filepath, engine="openpyxl")
    log.info("  Sheets: %s", xls.sheet_names)

    # Find the DSO Affiliation state sheet
    dso_sheet = None
    for sn in xls.sheet_names:
        if "dso" in sn.lower() and "state" in sn.lower():
            dso_sheet = sn
            break

    if not dso_sheet:
        log.warning("No 'DSO Affiliation - State Data' sheet found in %s", filename)
        return []

    log.info("  Reading sheet: '%s'", dso_sheet)
    df = pd.read_excel(xls, sheet_name=dso_sheet, header=None)
    if df.empty:
        log.warning("  Sheet is empty")
        return []

    # Find the header row by looking for "All Dentists"
    header_idx = None
    for i in range(min(15, len(df))):
        for val in df.iloc[i]:
            if pd.notna(val) and "all dentists" in str(val).strip().lower():
                header_idx = i
                break
        if header_idx is not None:
            break

    if header_idx is None:
        log.warning("  Could not find header row containing 'All Dentists'")
        return []

    # Map column indices to career stages using header text
    headers = df.iloc[header_idx]
    col_career_map = {}
    for col_idx, val in enumerate(headers):
        if pd.isna(val):
            continue
        val_lower = str(val).strip().lower()
        for substring, stage in HEADER_TO_CAREER_STAGE:
            if substring in val_lower:
                col_career_map[col_idx] = stage
                break

    log.info("  Header at row %d, career stage columns: %s", header_idx, col_career_map)

    if not col_career_map:
        log.warning("  No career stage columns detected")
        return []

    # Parse data rows
    all_records = []
    for i in range(header_idx + 1, len(df)):
        state = normalize_state(df.iloc[i, 0])
        if not state:
            continue

        for col_idx, career_stage in col_career_map.items():
            pct = safe_float(df.iloc[i, col_idx])
            if pct is None:
                continue

            all_records.append({
                "data_year": data_year,
                "state": state,
                "career_stage": career_stage,
                "total_dentists": None,
                "pct_dso_affiliated": pct,
                "pct_solo_practice": None,
                "pct_group_practice": None,
                "pct_large_group_10plus": None,
                "source_file": filename,
            })

    log.info("Parsed %d records from %s", len(all_records), filename)
    return all_records


def insert_records(session, records):
    """Upsert records into ada_hpi_benchmarks."""
    inserted = 0
    updated = 0
    for r in records:
        existing = session.query(ADAHPIBenchmark).filter_by(
            data_year=r["data_year"],
            state=r["state"],
            career_stage=r["career_stage"],
        ).first()
        if existing:
            for key in ("total_dentists", "pct_dso_affiliated", "pct_solo_practice",
                        "pct_group_practice", "pct_large_group_10plus", "source_file"):
                if r[key] is not None:
                    setattr(existing, key, r[key])
            updated += 1
        else:
            session.add(ADAHPIBenchmark(**r))
            inserted += 1
    session.commit()
    return inserted, updated


def print_preview(records):
    """Print parsed records as a formatted table."""
    if not records:
        print("\n  No records parsed.\n")
        return

    print()
    header = f"{'Year':>4}  {'ST':2}  {'Career Stage':20}  {'DSO%':>6}  {'Solo%':>6}  {'Group%':>7}  {'10+%':>6}  {'Count':>6}"
    print(header)
    print("-" * len(header))
    for r in records:
        print(
            f"{r['data_year'] or '?':>4}  "
            f"{r['state']:2}  "
            f"{r['career_stage']:20}  "
            f"{r['pct_dso_affiliated'] or '—':>6}  "
            f"{r['pct_solo_practice'] or '—':>6}  "
            f"{r['pct_group_practice'] or '—':>7}  "
            f"{r['pct_large_group_10plus'] or '—':>6}  "
            f"{r['total_dentists'] or '—':>6}"
        )
    print(f"\nTotal: {len(records)} record(s)\n")


def print_state_summary(session, states=("IL", "MA")):
    """Print DSO affiliation summary for specific states."""
    print("\n" + "=" * 60)
    print("DSO AFFILIATION SUMMARY")
    print("=" * 60)
    for st in states:
        rows = session.query(ADAHPIBenchmark).filter_by(state=st).order_by(
            ADAHPIBenchmark.data_year, ADAHPIBenchmark.career_stage
        ).all()
        if not rows:
            print(f"\n  {st}: No data available")
            continue
        print(f"\n  {st}:")
        for r in rows:
            print(f"    {r.data_year} | {r.career_stage:20} | DSO: {r.pct_dso_affiliated or '—':>5}%"
                  f" | Solo: {r.pct_solo_practice or '—':>5}%"
                  f" | 10+: {r.pct_large_group_10plus or '—':>5}%"
                  f" | n={r.total_dentists or '—'}")
    print()


DOWNLOAD_INSTRUCTIONS = """
Download the ADA HPI XLSX files from:
  https://www.ada.org/resources/research/health-policy-institute/dental-practice-research/practice-modalities-among-us-dentists

Download all available years (2022, 2023, 2024).
Save them to: ~/dental-pe-tracker/data/ada-hpi/

Rename them to include the year, e.g.:
  ada_hpi_2022.xlsx
  ada_hpi_2023.xlsx
  ada_hpi_2024.xlsx

Then run:
  python3 scrapers/ada_hpi_importer.py
  python3 scrapers/ada_hpi_importer.py --preview  # preview without inserting
"""


def run(preview=False):
    _t0 = log_scrape_start("ada_hpi_importer")
    log.info("=" * 60)
    log.info("ADA HPI Importer starting (preview=%s)", preview)
    log.info("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)

    xlsx_files = sorted(glob(os.path.join(DATA_DIR, "*.xlsx")))
    if not xlsx_files:
        print(f"\nNo XLSX files found in {DATA_DIR}")
        print(DOWNLOAD_INSTRUCTIONS)
        return

    log.info("Found %d XLSX files", len(xlsx_files))

    all_records = []
    for filepath in xlsx_files:
        records = process_xlsx(filepath)
        all_records.extend(records)

    if not all_records:
        print("\nNo records parsed from XLSX files.")
        print("Check the log for column detection issues.")
        return

    if preview:
        print_preview(all_records)
        # Show IL and MA specifically
        il_records = [r for r in all_records if r["state"] == "IL"]
        ma_records = [r for r in all_records if r["state"] == "MA"]
        if il_records or ma_records:
            print("\n--- Illinois & Massachusetts ---")
            print_preview(il_records + ma_records)
        return

    # Insert into database
    init_db()
    session = get_session()
    inserted, updated = insert_records(session, all_records)

    log.info("Inserted: %d, Updated: %d", inserted, updated)
    print(f"\nInserted: {inserted}, Updated: {updated}")

    log_scrape_complete("ada_hpi_importer", _t0, new_records=inserted,
                        summary=f"ADA HPI: {inserted} inserted, {updated} updated from {len(xlsx_files)} files",
                        extra={"updated": updated, "total_records": len(all_records)})

    # Summary for IL and MA
    print_state_summary(session, ("IL", "MA"))
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import ADA HPI DSO affiliation data from XLSX files",
        epilog=DOWNLOAD_INSTRUCTIONS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--preview", action="store_true",
                        help="Show parsed data without inserting into database")
    args = parser.parse_args()
    run(preview=args.preview)
