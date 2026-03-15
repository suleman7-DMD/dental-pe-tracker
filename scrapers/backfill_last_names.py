"""
Backfill provider_last_name — one-time script to populate provider_last_name
for existing practices from NPPES data.

Strategy:
1. Check for raw NPPES dissemination file with Provider Last Name column.
2. If found: reads NPI + Provider Last Name, updates practices where entity_type='individual'.
3. If not found: uses last-token heuristic on practice_name — takes last whitespace-delimited
   word, strips common suffixes (DDS, DMD, PC, PLLC, LTD, INC, PA, LLC).
   This is approximate (~90% accurate) and will be replaced by clean data
   on the next monthly NPPES refresh.

Usage:
    python3 scrapers/backfill_last_names.py
    python3 scrapers/backfill_last_names.py --dry-run
"""

import argparse
import csv
import glob
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("backfill_last_names")

BASE_DIR = os.path.expanduser("~/dental-pe-tracker")
DB_PATH = os.path.join(BASE_DIR, "data", "dental_pe_tracker.db")
NPPES_DATA_DIR = os.path.join(BASE_DIR, "data", "nppes")

# Suffixes to strip when using the heuristic approach
STRIP_SUFFIXES = {
    "DDS", "DMD", "PC", "PLLC", "LTD", "INC", "PA", "LLC",
    "MD", "DO", "PHD", "MS", "BS", "JR", "SR", "II", "III", "IV",
    "DPH", "MPH", "MSD", "FAGD", "FICOI", "FICD", "FACD",
}


def find_raw_nppes_file():
    """Look for the raw NPPES CSV with Provider Last Name column.

    Checks data/nppes/tmp/ and data/nppes/ for npidata_*.csv files
    that contain the 'Provider Last Name (Legal Name)' column.
    """
    patterns = [
        os.path.join(NPPES_DATA_DIR, "tmp", "npidata_*.csv"),
        os.path.join(NPPES_DATA_DIR, "npidata_*.csv"),
        os.path.join(BASE_DIR, "data", "npidata_*.csv"),
    ]
    for pattern in patterns:
        files = glob.glob(pattern)
        for f in sorted(files, key=os.path.getmtime, reverse=True):
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    reader = csv.reader(fh)
                    header = next(reader)
                    if "Provider Last Name (Legal Name)" in header:
                        log.info("Found raw NPPES file with Provider Last Name: %s", f)
                        return f
            except Exception:
                continue
    return None


def backfill_from_raw_nppes(raw_file, conn, dry_run=False):
    """Read NPI + Provider Last Name from raw NPPES CSV, update practices table."""
    log.info("Backfilling from raw NPPES file: %s", raw_file)

    cursor = conn.cursor()
    updated = 0
    skipped = 0
    batch = []
    batch_size = 5000

    with open(raw_file, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            npi = row.get("NPI", "").strip()
            entity_type_code = row.get("Entity Type Code", "").strip()
            last_name = row.get("Provider Last Name (Legal Name)", "").strip()

            # Only individual providers (entity type 1)
            if entity_type_code != "1" or not npi or not last_name:
                continue

            batch.append((last_name.upper(), npi))

            if len(batch) >= batch_size:
                if not dry_run:
                    cursor.executemany(
                        "UPDATE practices SET provider_last_name = ? WHERE npi = ? AND entity_type = 'individual'",
                        batch
                    )
                    conn.commit()
                updated += len(batch)
                batch = []

    # Final batch
    if batch:
        if not dry_run:
            cursor.executemany(
                "UPDATE practices SET provider_last_name = ? WHERE npi = ? AND entity_type = 'individual'",
                batch
            )
            conn.commit()
        updated += len(batch)

    log.info("Updated %d practices from raw NPPES file", updated)
    return updated, "raw_nppes"


def backfill_from_heuristic(conn, dry_run=False):
    """Parse practice_name for entity_type='individual' records using last-token heuristic.

    Takes the last whitespace-delimited word from practice_name,
    strips common suffixes (DDS, DMD, PC, etc.).

    NOTE: This is approximate (~90% accurate). Will be replaced by clean
    data on the next monthly NPPES refresh.
    """
    log.info("Backfilling via last-token heuristic from practice_name...")

    cursor = conn.cursor()
    cursor.execute(
        "SELECT npi, practice_name FROM practices "
        "WHERE entity_type = 'individual' AND provider_last_name IS NULL "
        "AND practice_name IS NOT NULL"
    )

    updated = 0
    skipped = 0
    batch = []
    batch_size = 5000

    for npi, practice_name in cursor.fetchall():
        last_name = extract_last_name(practice_name)
        if last_name:
            batch.append((last_name, npi))
        else:
            skipped += 1

        if len(batch) >= batch_size:
            if not dry_run:
                conn.execute("BEGIN")
                for ln, n in batch:
                    conn.execute(
                        "UPDATE practices SET provider_last_name = ? WHERE npi = ?",
                        (ln, n)
                    )
                conn.commit()
            updated += len(batch)
            batch = []

    # Final batch
    if batch:
        if not dry_run:
            conn.execute("BEGIN")
            for ln, n in batch:
                conn.execute(
                    "UPDATE practices SET provider_last_name = ? WHERE npi = ?",
                    (ln, n)
                )
            conn.commit()
        updated += len(batch)

    log.info("Updated %d practices via heuristic, skipped %d", updated, skipped)
    return updated, skipped


def extract_last_name(practice_name):
    """Extract likely last name from 'First Last' pattern.

    Strips common suffixes (DDS, DMD, etc.) from the end.
    Returns uppercase last name or None.
    """
    if not practice_name:
        return None

    # Clean up the name
    name = practice_name.strip().upper()

    # Remove common credential suffixes from the end
    tokens = name.split()
    while tokens and tokens[-1].replace(",", "").replace(".", "") in STRIP_SUFFIXES:
        tokens.pop()

    if len(tokens) < 2:
        return None

    # Last token after stripping suffixes is likely the last name
    last = tokens[-1].replace(",", "").replace(".", "").strip()

    # Validate: must be at least 2 chars, alphabetic
    if len(last) < 2 or not re.match(r"^[A-Z'-]+$", last):
        return None

    return last


def run(dry_run=False):
    """Main entry point."""
    start_time = log_scrape_start("backfill_last_names")

    try:
        conn = sqlite3.connect(DB_PATH)

        # Check current state
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM practices WHERE entity_type = 'individual'")
        total_individual = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM practices WHERE provider_last_name IS NOT NULL")
        already_populated = cursor.fetchone()[0]

        log.info("Total individual practices: %d", total_individual)
        log.info("Already have provider_last_name: %d", already_populated)

        if already_populated >= total_individual * 0.95:
            log.info("Provider last names already >95%% populated, skipping backfill")
            log_scrape_complete("backfill_last_names", start_time,
                                summary=f"Already populated ({already_populated}/{total_individual})")
            conn.close()
            return

        # Try raw NPPES file first
        raw_file = find_raw_nppes_file()
        if raw_file:
            count, method = backfill_from_raw_nppes(raw_file, conn, dry_run)
            log.info("Backfilled %d from raw NPPES file", count)
        else:
            log.info("No raw NPPES file found, using heuristic approach")

        # Use heuristic for any remaining NULL records
        remaining_count, skip_count = backfill_from_heuristic(conn, dry_run)

        # Final stats
        cursor.execute("SELECT COUNT(*) FROM practices WHERE provider_last_name IS NOT NULL")
        final_count = cursor.fetchone()[0]

        method_str = "raw NPPES + heuristic fallback" if raw_file else "heuristic only"
        summary = (
            f"Backfill complete ({method_str}). "
            f"Total with last name: {final_count}/{total_individual} "
            f"({final_count / total_individual * 100:.1f}%)"
        )
        log.info(summary)

        prefix = "[DRY RUN] " if dry_run else ""
        log_scrape_complete("backfill_last_names", start_time,
                            new_records=final_count - already_populated,
                            summary=f"{prefix}{summary}")

        conn.close()

    except Exception as e:
        log.error("Backfill failed: %s", e)
        log_scrape_error("backfill_last_names", str(e), start_time)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill provider_last_name from NPPES data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
