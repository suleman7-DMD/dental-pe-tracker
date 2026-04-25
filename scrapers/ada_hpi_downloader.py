"""
ADA HPI Downloader — automatically checks for and downloads the latest
ADA Health Policy Institute XLSX files (DSO affiliation by state/career stage).

The ADA publishes XLSX files at predictable URLs:
  https://www.ada.org/-/media/project/ada-organization/ada/ada-org/files/
    resources/research/hpi/hpidata_dentist_practice_modalities_YYYY.xlsx

This script:
  1. Checks years 2022 through the current year
  2. Skips files already present in ~/dental-pe-tracker/data/ada-hpi/
  3. Downloads any new files found
  4. Runs the ada_hpi_importer after downloading new data
  5. Logs all activity via the standard project logger

Usage:
    python3 scrapers/ada_hpi_downloader.py              # check & download
    python3 scrapers/ada_hpi_downloader.py --dry-run     # show what would be downloaded
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime

import requests

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("ada_hpi_downloader")

DATA_DIR = os.path.expanduser("~/dental-pe-tracker/data/ada-hpi")

BASE_URL = (
    "https://www.ada.org/-/media/project/ada-organization/ada/ada-org/"
    "files/resources/research/hpi/hpidata_dentist_practice_modalities_{year}.xlsx"
)

HEADERS = {"User-Agent": "DentalPETracker/1.0 (academic research)"}

# Lowered from 2022 to 2018 on 2026-04-25 — verified via HEAD probe that ADA
# publishes hpidata_dentist_practice_modalities_YYYY.xlsx for 2018, 2019, 2020,
# 2021 (all 200 OK). Without this lower bound the scraper silently skipped 4
# years of historical benchmark data. The dry-run logs each year as
# AVAILABLE/Not available so missing years remain visible.
START_YEAR = 2018


def get_existing_years(data_dir):
    """Scan the data directory for already-downloaded XLSX files and return
    a dict mapping year (int) -> filename."""
    existing = {}
    if not os.path.isdir(data_dir):
        return existing

    for fname in os.listdir(data_dir):
        if not fname.lower().endswith(".xlsx"):
            continue
        m = re.search(r"(20[12]\d)", fname)
        if m:
            year = int(m.group(1))
            existing[year] = fname
    return existing


def check_url(url):
    """Send a HEAD request to check if a URL exists and is actually an XLSX file.
    ADA returns HTTP 200 with text/html for missing files, so we check Content-Type."""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            log.debug("URL returns HTML, not XLSX: %s", url)
            return False
        return True
    except requests.RequestException as exc:
        log.debug("HEAD request failed for %s: %s", url, exc)
        return False


def download_file(url, dest_path):
    """Download a file from url to dest_path. Returns True on success."""
    try:
        log.info("Downloading: %s", url)
        resp = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        resp.raise_for_status()

        if len(resp.content) < 1000:
            log.warning("Downloaded file is suspiciously small (%d bytes), skipping",
                        len(resp.content))
            return False

        # ADA returns HTML error pages with HTTP 200 — check content type and magic bytes
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type or resp.content[:15].startswith(b"<!DOCTYPE"):
            log.warning("[%s] Server returned HTML page instead of XLSX (content-type: %s), skipping",
                        url.split("/")[-1], content_type)
            return False

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(resp.content)

        size_kb = len(resp.content) / 1024
        log.info("Saved: %s (%.1f KB)", dest_path, size_kb)
        return True

    except requests.RequestException as exc:
        log.error("Download failed for %s: %s", url, exc)
        return False


def run_importer():
    """Shell out to ada_hpi_importer.py to process newly downloaded files."""
    importer_path = os.path.expanduser("~/dental-pe-tracker/scrapers/ada_hpi_importer.py")

    if not os.path.isfile(importer_path):
        log.error("Importer not found at %s", importer_path)
        return False

    log.info("Running importer: %s", importer_path)
    try:
        subprocess.run(
            [sys.executable, importer_path],
            check=True,
        )
        log.info("Importer completed successfully")
        return True
    except subprocess.CalledProcessError as exc:
        log.error("Importer failed with return code %d", exc.returncode)
        return False


def run(dry_run=False):
    _t0 = log_scrape_start("ada_hpi_downloader")
    current_year = datetime.now().year
    years_to_check = list(range(START_YEAR, current_year + 1))

    log.info("=" * 60)
    log.info("ADA HPI Downloader starting (dry_run=%s)", dry_run)
    log.info("Checking years: %s", years_to_check)
    log.info("Data directory: %s", DATA_DIR)
    log.info("=" * 60)

    existing = get_existing_years(DATA_DIR)
    log.info("Already have files for years: %s",
             sorted(existing.keys()) if existing else "(none)")

    checked = 0
    skipped = 0
    new_downloads = []
    failed = []

    for year in years_to_check:
        checked += 1
        url = BASE_URL.format(year=year)

        if year in existing:
            log.info("[%d] Already have: %s — skipping", year, existing[year])
            skipped += 1
            continue

        log.info("[%d] Checking: %s", year, url)

        if dry_run:
            available = check_url(url)
            if available:
                log.info("[%d] AVAILABLE — would download (dry run)", year)
                new_downloads.append(year)
            else:
                log.info("[%d] Not available at ADA (HTTP != 200)", year)
            continue

        # Real download
        dest_filename = f"HPIData_Dentist_Practice_Modalities_{year}.xlsx"
        dest_path = os.path.join(DATA_DIR, dest_filename)

        if download_file(url, dest_path):
            new_downloads.append(year)
        else:
            # Could be a 404 (not published yet) — only warn, don't treat as error
            log.info("[%d] Not available or download failed", year)
            failed.append(year)

    # Run importer if we downloaded new files
    import_status = "skipped"
    if new_downloads and not dry_run:
        log.info("New files downloaded for years: %s — running importer", new_downloads)
        success = run_importer()
        import_status = "success" if success else "failed"
    elif new_downloads and dry_run:
        import_status = "dry_run"
    else:
        log.info("No new files to import")

    # Summary
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("  Years checked:  %d (%d–%d)", checked, START_YEAR, current_year)
    log.info("  Already had:    %d", skipped)
    log.info("  New downloads:  %d %s", len(new_downloads),
             new_downloads if new_downloads else "")
    log.info("  Failed/absent:  %d %s", len(failed),
             failed if failed else "")
    log.info("  Import status:  %s", import_status)
    log.info("=" * 60)

    if not dry_run:
        log_scrape_complete("ada_hpi_downloader", _t0, new_records=len(new_downloads),
                            summary=f"ADA HPI: {len(new_downloads)} new files downloaded ({new_downloads}), import={import_status}",
                            extra={"years_checked": checked, "already_had": skipped, "import_status": import_status})

    print(f"\n{'DRY RUN — ' if dry_run else ''}ADA HPI Downloader Summary:")
    print(f"  Years checked:  {checked} ({START_YEAR}–{current_year})")
    print(f"  Already had:    {skipped}")
    print(f"  New downloads:  {len(new_downloads)} {new_downloads if new_downloads else ''}")
    print(f"  Import status:  {import_status}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check for and download new ADA HPI XLSX files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scrapers/ada_hpi_downloader.py              # download new files\n"
            "  python3 scrapers/ada_hpi_downloader.py --dry-run     # preview only\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check availability without downloading; show what would be fetched",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
