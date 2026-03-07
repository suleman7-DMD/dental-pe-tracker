"""
NPPES Downloader — downloads CMS NPPES data and imports dental practices.

First run:  downloads full dissemination file, filters to dental taxonomy codes,
            inserts all dental practices into the database.
Subsequent: downloads monthly update file, detects changes, updates database.

Usage:
    python3 scrapers/nppes_downloader.py                  # full or update (auto-detect)
    python3 scrapers/nppes_downloader.py --watched-only   # only watched ZIP codes
    python3 scrapers/nppes_downloader.py --dry-run        # download & parse but don't insert
"""

import argparse
import csv
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_session, Practice, PracticeChange, WatchedZip,
    insert_or_update_practice, log_practice_change,
)

log = get_logger("nppes_downloader")

HEADERS = {"User-Agent": "DentalPETracker/1.0 (academic research)"}
NPPES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"

DATA_DIR = os.path.expanduser("~/dental-pe-tracker/data/nppes")
SNAPSHOTS_DIR = os.path.join(DATA_DIR, "snapshots")
TEMP_DIR = os.path.join(DATA_DIR, "tmp")

# Dental taxonomy codes all start with "12"
DENTAL_TAXONOMY_PREFIX = "12"

# Specific dental taxonomy codes for reference
DENTAL_TAXONOMIES = {
    "1223G0001X": "general",
    "122300000X": "general",
    "1223D0001X": "general",        # Dental Public Health
    "1223E0200X": "endodontics",
    "1223X0008X": "oral_surgery",   # Oral & Maxillofacial Pathology
    "1223D0008X": "oral_surgery",   # Oral & Maxillofacial Radiology
    "1223S0112X": "oral_surgery",   # Oral & Maxillofacial Surgery
    "1223X0400X": "orthodontics",
    "1223P0221X": "pediatric",
    "1223P0300X": "periodontics",
    "1223P0700X": "prosthodontics",
}

# NPPES CSV column names we care about
COL_NPI = "NPI"
COL_ENTITY_TYPE = "Entity Type Code"
COL_ORG_NAME = "Provider Organization Name (Legal Business Name)"
COL_ORG_OTHER = "Provider Other Organization Name"
COL_LAST_NAME = "Provider Last Name (Legal Name)"
COL_FIRST_NAME = "Provider First Name"
COL_ADDRESS = "Provider First Line Business Practice Location Address"
COL_CITY = "Provider Business Practice Location Address City Name"
COL_STATE = "Provider Business Practice Location Address State Name"
COL_ZIP = "Provider Business Practice Location Address Postal Code"
COL_PHONE = "Provider Business Practice Location Address Telephone Number"
COL_ENUM_DATE = "Provider Enumeration Date"
COL_LAST_UPDATE = "Last Update Date"
# Taxonomy columns: "Healthcare Provider Taxonomy Code_1" through _15
TAXONOMY_COL_PREFIX = "Healthcare Provider Taxonomy Code_"

# Fields to track for changes
TRACKED_FIELDS = {
    "practice_name": COL_ORG_NAME,
    "doing_business_as": COL_ORG_OTHER,
    "address": COL_ADDRESS,
    "city": COL_CITY,
    "state": COL_STATE,
    "zip": COL_ZIP,
    "phone": COL_PHONE,
}


# ── URL Discovery ───────────────────────────────────────────────────────────


def discover_nppes_urls():
    """Parse the NPPES download page to find file URLs."""
    log.info("Fetching NPPES download page...")
    try:
        resp = requests.get(NPPES_PAGE, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch NPPES page: %s", e)
        return None, None

    soup = BeautifulSoup(resp.text, "lxml")
    full_url = None
    weekly_urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()

        if ".zip" not in href_lower:
            continue
        if "deactivat" in href_lower:
            continue

        # Normalize relative URL
        clean_href = href.lstrip("./")
        abs_url = f"https://download.cms.gov/nppes/{clean_href}"

        # Full file: "NPPES_Data_Dissemination_<MonthName>_<Year>_V2.zip"
        # Has a month NAME (not date digits), no "Weekly" in the name
        if re.search(r'NPPES_Data_Dissemination_[A-Za-z]+_\d{4}', href) and "weekly" not in href_lower:
            full_url = abs_url
            log.info("Found full file: %s", full_url)

        # Weekly update: contains date ranges and "Weekly"
        if "weekly" in href_lower:
            weekly_urls.append(abs_url)
            log.info("Found weekly update: %s", abs_url)

    # Use the most recent weekly update (last one on page)
    update_url = weekly_urls[-1] if weekly_urls else None
    if update_url:
        log.info("Using latest weekly update: %s", update_url)

    return full_url, update_url


def download_file(url, dest_path):
    """Download a file with progress reporting."""
    log.info("Downloading: %s", url)
    log.info("Destination: %s", dest_path)

    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Download failed: %s", e)
        return False

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    last_report = 0

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            f.write(chunk)
            downloaded += len(chunk)
            # Report every 50MB
            if total > 0 and downloaded - last_report > 50 * 1024 * 1024:
                pct = (downloaded / total) * 100
                log.info("  Downloaded %.0f MB / %.0f MB (%.1f%%)",
                         downloaded / 1024 / 1024, total / 1024 / 1024, pct)
                last_report = downloaded

    size_mb = os.path.getsize(dest_path) / 1024 / 1024
    log.info("Download complete: %.1f MB", size_mb)
    return True


def extract_zip(zip_path, extract_to):
    """Extract ZIP file, return path to the main CSV."""
    log.info("Extracting: %s", zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_files = [n for n in zf.namelist() if n.endswith(".csv") and "pl_pfile" not in n.lower()]
        log.info("  ZIP contents: %s", zf.namelist())
        for name in csv_files:
            zf.extract(name, extract_to)
            log.info("  Extracted: %s", name)

    # Find the main NPI data CSV (largest one, not the endpoint or other file)
    extracted = []
    for name in csv_files:
        path = os.path.join(extract_to, name)
        if os.path.exists(path):
            extracted.append((path, os.path.getsize(path)))

    if not extracted:
        log.error("No CSV files found in ZIP")
        return None

    # Return the largest CSV (the main data file)
    extracted.sort(key=lambda x: x[1], reverse=True)
    main_csv = extracted[0][0]
    log.info("Main CSV: %s (%.1f MB)", main_csv, extracted[0][1] / 1024 / 1024)
    return main_csv


# ── Row Parsing ─────────────────────────────────────────────────────────────


def is_dental_row(row):
    """Check if any taxonomy code column starts with '12' (dental)."""
    for i in range(1, 16):
        col = f"{TAXONOMY_COL_PREFIX}{i}"
        val = row.get(col, "")
        if val and str(val).startswith(DENTAL_TAXONOMY_PREFIX):
            return True
    return False


def get_primary_taxonomy(row):
    """Get the first dental taxonomy code."""
    for i in range(1, 16):
        col = f"{TAXONOMY_COL_PREFIX}{i}"
        val = row.get(col, "")
        if val and str(val).startswith(DENTAL_TAXONOMY_PREFIX):
            return str(val).strip()
    return None


def get_taxonomy_specialty(code):
    """Map taxonomy code to specialty name."""
    if not code:
        return None
    return DENTAL_TAXONOMIES.get(code, "general" if code.startswith("12") else None)


def parse_nppes_row(row):
    """Parse an NPPES CSV row into our practice fields."""
    npi = str(row.get(COL_NPI, "")).strip()
    if not npi or len(npi) != 10:
        return None

    entity_code = str(row.get(COL_ENTITY_TYPE, "")).strip()
    entity_type = "organization" if entity_code == "2" else "individual"

    # For organizations, use org name; for individuals, combine first+last
    if entity_type == "organization":
        practice_name = str(row.get(COL_ORG_NAME, "")).strip() or None
    else:
        first = str(row.get(COL_FIRST_NAME, "")).strip()
        last = str(row.get(COL_LAST_NAME, "")).strip()
        practice_name = f"{first} {last}".strip() or None

    dba = str(row.get(COL_ORG_OTHER, "")).strip() or None
    address = str(row.get(COL_ADDRESS, "")).strip() or None
    city = str(row.get(COL_CITY, "")).strip() or None
    state = str(row.get(COL_STATE, "")).strip() or None
    raw_zip = str(row.get(COL_ZIP, "")).strip()
    zip_code = raw_zip[:5] if raw_zip and len(raw_zip) >= 5 else None
    phone = str(row.get(COL_PHONE, "")).strip() or None
    if phone and len(phone) == 10:
        phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"

    taxonomy_code = get_primary_taxonomy(row)
    taxonomy_desc = get_taxonomy_specialty(taxonomy_code)

    enum_date = _parse_date(row.get(COL_ENUM_DATE))
    last_updated = _parse_date(row.get(COL_LAST_UPDATE))

    return {
        "npi": npi,
        "practice_name": practice_name,
        "doing_business_as": dba,
        "entity_type": entity_type,
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "taxonomy_code": taxonomy_code,
        "taxonomy_description": taxonomy_desc,
        "enumeration_date": enum_date,
        "last_updated": last_updated,
        "ownership_status": "unknown",
        "data_source": "nppes",
    }


def _parse_date(val):
    """Parse MM/DD/YYYY date from NPPES."""
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Full File Processing ────────────────────────────────────────────────────


def process_full_file(csv_path, session, watched_zips=None, dry_run=False):
    """Process the full NPPES dissemination file. Returns stats dict."""
    log.info("Processing full NPPES file: %s", csv_path)

    stats = {"total_rows": 0, "dental_rows": 0, "inserted": 0,
             "skipped_zip": 0, "errors": 0}
    dental_rows_for_snapshot = []
    start_time = time.time()

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        # Strip whitespace from column headers (NPPES CSVs sometimes have trailing spaces)
        if reader.fieldnames:
            reader.fieldnames = [name.strip() for name in reader.fieldnames]

        for row in reader:
            stats["total_rows"] += 1

            # Progress every 100k rows
            if stats["total_rows"] % 100_000 == 0:
                elapsed = time.time() - start_time
                rate = stats["total_rows"] / elapsed
                log.info("  Processed %dk rows (%.0f rows/sec) — %d dental found",
                         stats["total_rows"] // 1000, rate, stats["dental_rows"])

            # Filter: dental taxonomy
            if not is_dental_row(row):
                continue

            stats["dental_rows"] += 1
            parsed = parse_nppes_row(row)
            if not parsed:
                stats["errors"] += 1
                continue

            # Filter: watched ZIPs only
            if watched_zips and parsed["zip"] not in watched_zips:
                stats["skipped_zip"] += 1
                continue

            dental_rows_for_snapshot.append(parsed)

            if not dry_run:
                try:
                    insert_or_update_practice(session, **parsed)
                    stats["inserted"] += 1
                except Exception as e:
                    log.warning("Insert error NPI %s: %s", parsed["npi"], e)
                    stats["errors"] += 1
            else:
                stats["inserted"] += 1

    elapsed = time.time() - start_time
    log.info("Full file processing complete in %.1f seconds", elapsed)

    # Save snapshot
    snapshot_path = _save_snapshot(dental_rows_for_snapshot, "nppes_dental")
    stats["snapshot_path"] = snapshot_path

    return stats


# ── Monthly Update Processing ──────────────────────────────────────────────


def process_update_file(csv_path, session, watched_zips=None, dry_run=False):
    """Process a monthly NPPES update file. Returns stats dict."""
    log.info("Processing NPPES update file: %s", csv_path)

    stats = {"total_rows": 0, "dental_rows": 0, "new_practices": 0,
             "updated_practices": 0, "changes_logged": 0,
             "skipped_zip": 0, "errors": 0}
    dental_rows_for_snapshot = []
    start_time = time.time()

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            reader.fieldnames = [name.strip() for name in reader.fieldnames]

        for row in reader:
            stats["total_rows"] += 1

            if stats["total_rows"] % 100_000 == 0:
                elapsed = time.time() - start_time
                rate = stats["total_rows"] / elapsed if elapsed > 0 else 0
                log.info("  Processed %dk rows (%.0f rows/sec) — %d dental found",
                         stats["total_rows"] // 1000, rate, stats["dental_rows"])

            if not is_dental_row(row):
                continue

            stats["dental_rows"] += 1
            parsed = parse_nppes_row(row)
            if not parsed:
                stats["errors"] += 1
                continue

            if watched_zips and parsed["zip"] not in watched_zips:
                stats["skipped_zip"] += 1
                continue

            dental_rows_for_snapshot.append(parsed)

            if dry_run:
                continue

            # Check if practice exists
            existing = session.query(Practice).filter_by(npi=parsed["npi"]).first()

            if existing:
                # Detect and log changes
                changes_found = _detect_changes(existing, parsed, session)
                if changes_found:
                    stats["changes_logged"] += changes_found

                # Update fields
                for key, value in parsed.items():
                    if key != "npi" and value is not None:
                        # Don't overwrite manual ownership classifications
                        if key == "ownership_status" and existing.ownership_status not in ("unknown", None):
                            continue
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                session.commit()
                stats["updated_practices"] += 1
            else:
                # New practice
                try:
                    insert_or_update_practice(session, **parsed)
                    stats["new_practices"] += 1
                except Exception as e:
                    log.warning("Insert error NPI %s: %s", parsed["npi"], e)
                    stats["errors"] += 1

    elapsed = time.time() - start_time
    log.info("Update file processing complete in %.1f seconds", elapsed)

    snapshot_path = _save_snapshot(dental_rows_for_snapshot, "nppes_dental_update")
    stats["snapshot_path"] = snapshot_path

    return stats


def _detect_changes(existing, parsed, session):
    """Compare existing practice with parsed data, log any changes."""
    changes = 0
    today = date.today()

    field_map = {
        "practice_name": "practice_name",
        "doing_business_as": "doing_business_as",
        "address": "address",
        "city": "city",
        "state": "state",
        "zip": "zip",
        "phone": "phone",
    }

    for db_field, parsed_field in field_map.items():
        old_val = getattr(existing, db_field, None)
        new_val = parsed.get(parsed_field)

        if new_val is None:
            continue
        if old_val == new_val:
            continue
        if old_val is None and new_val:
            continue  # Don't log filling in blank fields

        # Determine change type
        change_type = "unknown"
        if db_field in ("practice_name", "doing_business_as"):
            change_type = _classify_name_change(old_val, new_val)
        elif db_field == "address":
            change_type = "relocation"
        else:
            change_type = "unknown"

        try:
            log_practice_change(
                session,
                npi=existing.npi,
                change_date=today,
                field_changed=db_field,
                old_value=str(old_val) if old_val else None,
                new_value=str(new_val) if new_val else None,
                change_type=change_type,
            )
            changes += 1
        except Exception as e:
            log.warning("Failed to log change for NPI %s: %s", existing.npi, e)

    return changes


def _classify_name_change(old_name, new_name):
    """Try to classify a practice name change."""
    if not old_name or not new_name:
        return "name_change"

    old_l = old_name.lower()
    new_l = new_name.lower()

    # Known DSO keywords that suggest acquisition
    dso_keywords = [
        "heartland", "aspen", "pacific dental", "mb2", "dental365",
        "specialized dental", "great expressions", "affordable care",
        "benevis", "western dental", "dental care alliance", "sage dental",
        "gentle dental", "tend dental", "mortenson", "community dental",
        "risas", "lightwave", "smile brands", "sonrava", "ideal dental",
    ]
    for kw in dso_keywords:
        if kw in new_l and kw not in old_l:
            return "acquisition"

    # Management/holdings keywords
    if any(kw in new_l and kw not in old_l for kw in
           ("management", "holdings", "partners", "dental group", "dso")):
        return "acquisition"

    return "name_change"


# ── Snapshot ────────────────────────────────────────────────────────────────


def _save_snapshot(dental_rows, prefix):
    """Save filtered dental rows as a CSV snapshot."""
    if not dental_rows:
        return None

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    month_str = datetime.now().strftime("%Y-%m")
    path = os.path.join(SNAPSHOTS_DIR, f"{prefix}_{month_str}.csv")

    keys = dental_rows[0].keys()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(dental_rows)

    log.info("Saved snapshot: %s (%d rows)", path, len(dental_rows))
    return path


# ── Main Orchestration ──────────────────────────────────────────────────────


def run(watched_only=False, dry_run=False):
    log.info("=" * 60)
    log.info("NPPES Downloader starting (watched_only=%s, dry_run=%s)", watched_only, dry_run)
    log.info("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

    # Initialize DB
    init_db()
    session = get_session()

    # Check if this is a first run
    practice_count = session.query(Practice).count()
    is_first_run = practice_count == 0
    log.info("Existing practices in DB: %d (first_run=%s)", practice_count, is_first_run)

    # Get watched ZIP codes
    watched_zips = None
    if watched_only:
        zips = session.query(WatchedZip.zip_code).all()
        watched_zips = {z[0] for z in zips}
        log.info("Filtering to %d watched ZIP codes", len(watched_zips))

    # Discover NPPES URLs
    full_url, update_url = discover_nppes_urls()

    if is_first_run and not full_url:
        log.error("Cannot find full NPPES file URL. Check %s manually.", NPPES_PAGE)
        session.close()
        return

    if not is_first_run and not update_url:
        log.warning("Cannot find monthly update URL. Trying full file instead.")
        if not full_url:
            log.error("No download URLs found at all.")
            session.close()
            return

    # Determine which file to download
    if is_first_run:
        target_url = full_url
        log.info("FIRST RUN — downloading full dissemination file")
    else:
        target_url = update_url or full_url
        log.info("UPDATE RUN — downloading %s", "monthly update" if update_url else "full file")

    # Download
    zip_filename = target_url.split("/")[-1]
    zip_path = os.path.join(TEMP_DIR, zip_filename)

    if not os.path.exists(zip_path):
        success = download_file(target_url, zip_path)
        if not success:
            session.close()
            return
    else:
        log.info("ZIP already exists, skipping download: %s", zip_path)

    # Extract
    csv_path = extract_zip(zip_path, TEMP_DIR)
    if not csv_path:
        session.close()
        return

    # Process
    if is_first_run or target_url == full_url:
        stats = process_full_file(csv_path, session, watched_zips, dry_run)
    else:
        stats = process_update_file(csv_path, session, watched_zips, dry_run)

    # Cleanup temp files
    log.info("Cleaning up temporary files...")
    try:
        os.remove(zip_path)
        log.info("  Removed: %s", zip_path)
    except OSError:
        pass
    try:
        os.remove(csv_path)
        log.info("  Removed: %s", csv_path)
    except OSError:
        pass
    # Remove any other extracted files in temp
    for f in os.listdir(TEMP_DIR):
        fpath = os.path.join(TEMP_DIR, f)
        if os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass

    # Summary
    print()
    log.info("=" * 60)
    log.info("NPPES DOWNLOADER SUMMARY")
    log.info("=" * 60)
    log.info("Total rows scanned:     %s", f"{stats['total_rows']:,}")
    log.info("Dental rows found:      %s", f"{stats['dental_rows']:,}")
    if "inserted" in stats:
        log.info("Practices inserted:     %s", f"{stats['inserted']:,}")
    if "new_practices" in stats:
        log.info("New practices:          %s", f"{stats['new_practices']:,}")
    if "updated_practices" in stats:
        log.info("Updated practices:      %s", f"{stats['updated_practices']:,}")
    if "changes_logged" in stats:
        log.info("Changes logged:         %s", f"{stats['changes_logged']:,}")
    if stats.get("skipped_zip"):
        log.info("Skipped (not watched):  %s", f"{stats['skipped_zip']:,}")
    if stats.get("errors"):
        log.info("Errors:                 %s", f"{stats['errors']:,}")
    if stats.get("snapshot_path"):
        log.info("Snapshot saved:         %s", stats["snapshot_path"])
    log.info("=" * 60)

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and import NPPES dental practice data")
    parser.add_argument("--watched-only", action="store_true",
                        help="Only process practices in watched ZIP codes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Download and parse but don't insert into database")
    args = parser.parse_args()
    run(watched_only=args.watched_only, dry_run=args.dry_run)
