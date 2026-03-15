"""
Census Data Loader — populates demographic columns in watched_zips.

Primary: Census Bureau ACS 5-year API (ZCTAs for IL and MA).
Fallback: Local CSV file (data/zip_demographics.csv).

Usage:
    python3 scrapers/census_loader.py              # Try API, fallback to CSV
    python3 scrapers/census_loader.py --csv-only   # Only use local CSV
    python3 scrapers/census_loader.py --dry-run    # Show what would be updated
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

import requests

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error
from scrapers.database import get_session, WatchedZip

log = get_logger("census_loader")

BASE_DIR = os.path.expanduser("~/dental-pe-tracker")
CSV_PATH = os.path.join(BASE_DIR, "data", "zip_demographics.csv")

# Census Bureau ACS 5-year estimates
# B01003_001E = Total Population
# B19013_001E = Median Household Income
# Note: 2022 is the latest stable ACS 5-year dataset
CENSUS_API_BASE = "https://api.census.gov/data/2022/acs/acs5"
CENSUS_VARIABLES = "B01003_001E,B19013_001E"


def fetch_census_data():
    """Fetch population and MHI from Census Bureau API for all ZCTAs.

    Note: ZCTAs (ZIP Code Tabulation Areas) approximate but do not perfectly
    align with USPS ZIP codes. Some ZIPs may not have a corresponding ZCTA.
    ZCTAs are a national-level geography — they don't nest under states.

    Returns dict: {zip_code: {"population": int, "mhi": int}}
    """
    results = {}

    url = (
        f"{CENSUS_API_BASE}?get={CENSUS_VARIABLES}"
        f"&for=zip%20code%20tabulation%20area:*"
    )
    log.info("Fetching Census data for all ZCTAs...")
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.warning("Census API request failed: %s", e)
        return results

    if not data or len(data) < 2:
        log.warning("No data returned from Census API")
        return results

    # First row is header: ['B01003_001E', 'B19013_001E', 'zip code tabulation area']
    header = data[0]
    pop_idx = header.index("B01003_001E")
    mhi_idx = header.index("B19013_001E")
    zcta_idx = header.index("zip code tabulation area")

    for row in data[1:]:
        zcta = row[zcta_idx]
        pop_val = row[pop_idx]
        mhi_val = row[mhi_idx]

        pop = int(pop_val) if pop_val and pop_val not in ("-666666666", "-999999999", "null") else None
        mhi = int(mhi_val) if mhi_val and mhi_val not in ("-666666666", "-999999999", "null") else None

        if pop is not None or mhi is not None:
            results[zcta] = {"population": pop, "mhi": mhi}

    log.info("Got Census data for %d ZCTAs total", len(results))
    return results


def load_csv_data():
    """Load demographic data from local CSV fallback.

    Returns dict: {zip_code: {"population": int, "mhi": int, "growth_pct": float}}
    """
    if not os.path.exists(CSV_PATH):
        log.warning("No CSV fallback file at %s", CSV_PATH)
        return {}

    results = {}
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zip_code = row.get("zip_code", "").strip()
            if not zip_code:
                continue
            pop = int(row["population"]) if row.get("population", "").strip() else None
            mhi = int(row["median_household_income"]) if row.get("median_household_income", "").strip() else None
            growth = float(row["population_growth_pct"]) if row.get("population_growth_pct", "").strip() else None
            if pop is not None or mhi is not None:
                results[zip_code] = {"population": pop, "mhi": mhi, "growth_pct": growth}

    log.info("Loaded %d ZIPs from CSV fallback", len(results))
    return results


def create_csv_template(session):
    """Create a template CSV with all watched ZIPs for manual filling."""
    watched = session.query(WatchedZip).all()
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["zip_code", "population", "median_household_income", "population_growth_pct"])
        for wz in sorted(watched, key=lambda x: x.zip_code):
            writer.writerow([wz.zip_code, "", "", ""])
    log.info("Created CSV template at %s with %d ZIPs", CSV_PATH, len(watched))


def update_demographics(session, demo_data, dry_run=False):
    """Update watched_zips with demographic data.

    Only updates when real values are available — never overwrites with NULL.

    Returns (updated_count, skipped_count, no_data_count).
    """
    watched = session.query(WatchedZip).all()
    watched_zips = {wz.zip_code: wz for wz in watched}

    updated = 0
    skipped = 0
    no_data = 0

    for zip_code, wz in watched_zips.items():
        data = demo_data.get(zip_code)
        if not data:
            no_data += 1
            continue

        changed = False
        pop = data.get("population")
        mhi = data.get("mhi")
        growth = data.get("growth_pct")

        if pop is not None:
            if not dry_run:
                wz.population = pop
            changed = True
        if mhi is not None:
            if not dry_run:
                wz.median_household_income = mhi
            changed = True
        if growth is not None:
            if not dry_run:
                wz.population_growth_pct = growth
            changed = True

        if changed:
            if not dry_run:
                wz.demographics_updated_at = datetime.now()
            updated += 1
        else:
            skipped += 1

    if not dry_run:
        session.commit()

    return updated, skipped, no_data


def run(csv_only=False, dry_run=False):
    """Main entry point."""
    start_time = log_scrape_start("census_loader")
    session = get_session()

    try:
        demo_data = {}

        # Try Census API first (unless csv_only)
        if not csv_only:
            log.info("Attempting Census Bureau API...")
            api_data = fetch_census_data()
            if api_data:
                demo_data.update(api_data)
                log.info("Census API returned data for %d ZCTAs", len(api_data))
            else:
                log.warning("Census API returned no usable data, falling back to CSV")

        # If API gave us nothing or csv_only, use CSV
        if not demo_data:
            csv_data = load_csv_data()
            if csv_data:
                demo_data.update(csv_data)
            else:
                # Create template for manual filling
                create_csv_template(session)
                log.warning("No demographic data available. Template CSV created at %s", CSV_PATH)
                log_scrape_complete("census_loader", start_time, summary="No data available; template created")
                return

        # Update the database
        prefix = "[DRY RUN] " if dry_run else ""
        updated, skipped, no_data = update_demographics(session, demo_data, dry_run=dry_run)

        summary = (
            f"{prefix}Updated {updated} ZIPs, "
            f"skipped {skipped} (no new values), "
            f"no data for {no_data} ZIPs"
        )
        log.info(summary)
        log_scrape_complete("census_loader", start_time, new_records=updated, summary=summary)

    except Exception as e:
        log.error("Census loader failed: %s", e)
        log_scrape_error("census_loader", str(e), start_time)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Census demographic data into watched_zips")
    parser.add_argument("--csv-only", action="store_true", help="Only use local CSV, skip API")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    args = parser.parse_args()
    run(csv_only=args.csv_only, dry_run=args.dry_run)
