#!/usr/bin/env python3
"""
Pipeline Health Check — one-command diagnostic for the dental-pe-tracker
data pipeline.

Checks every stage from CSV download through git push and prints a clear
pass/fail status report.

Usage:
    python3 pipeline_check.py          # status report
    python3 pipeline_check.py --fix    # status report + fix commands
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, date
from glob import glob
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
DATA_AXLE_DIR = os.path.join(PROJECT_DIR, "data", "data-axle")
PROCESSED_DIR = os.path.join(DATA_AXLE_DIR, "processed")
DB_PATH = os.path.join(PROJECT_DIR, "data", "dental_pe_tracker.db")
DB_GZ_PATH = DB_PATH + ".gz"
PIPELINE_LOG = os.path.join(PROJECT_DIR, "logs", "pipeline_events.jsonl")

# ── ANSI Colors ───────────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PASS = f"{GREEN}\u2713{RESET}"
FAIL = f"{RED}\u2717{RESET}"
WARN = f"{YELLOW}\u26a0{RESET}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _file_mtime(path):
    """Return mtime as datetime, or None if file doesn't exist."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def _db_query(query, params=None):
    """Run a read-only query against the DB. Returns rows or None on error."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params or ())
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return None


def _git(*args):
    """Run a git command in the project directory and return stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", 1


def _last_pipeline_event(source):
    """Return the most recent pipeline event for a given source."""
    if not os.path.exists(PIPELINE_LOG):
        return None
    latest = None
    try:
        with open(PIPELINE_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("source") == source and record.get("event") in (
                    "scrape_complete", "scrape_error",
                ):
                    latest = record
    except OSError:
        pass
    return latest


# ── Check Functions ───────────────────────────────────────────────────────────
# Each returns (symbol, label, detail, fix_command_or_None)

def check_csv_downloads():
    """1. Scan ~/Downloads/ for stale Data Axle CSVs not yet moved."""
    patterns = [
        os.path.join(DOWNLOADS_DIR, "Detail*.csv"),
        os.path.join(DOWNLOADS_DIR, "data_axle*.csv"),
    ]
    stale = []
    for pat in patterns:
        stale.extend(glob(pat))

    if not stale:
        return PASS, "CSV Download", "No stale CSVs in ~/Downloads/", None

    names = [os.path.basename(f) for f in stale]
    detail = f"{len(stale)} CSV(s) in ~/Downloads/ not moved: {', '.join(names[:5])}"
    if len(names) > 5:
        detail += f" (+{len(names) - 5} more)"

    fix = (
        "# Move Data Axle CSVs to the import directory:\n"
        f"mv ~/Downloads/Detail*.csv ~/Downloads/data_axle*.csv {DATA_AXLE_DIR}/"
    )
    return FAIL, "CSV Download", detail, fix


def check_unprocessed_csvs():
    """2. Scan data/data-axle/ for CSVs not yet in processed/ subfolder."""
    if not os.path.isdir(DATA_AXLE_DIR):
        return WARN, "CSV Import", "data/data-axle/ directory not found", None

    csvs = glob(os.path.join(DATA_AXLE_DIR, "*.csv"))
    if not csvs:
        return PASS, "CSV Import", "No unprocessed CSVs in data/data-axle/", None

    names = [os.path.basename(f) for f in csvs]
    detail = f"{len(csvs)} CSV(s) in data/data-axle/ not yet processed"

    fix = (
        "# Preview first, then import:\n"
        "cd ~/dental-pe-tracker\n"
        "python3 scrapers/data_axle_importer.py --preview\n"
        "python3 scrapers/data_axle_importer.py --auto"
    )
    return FAIL, "CSV Import", detail, fix


def check_db_import_freshness():
    """3. Check the latest import timestamp in the DB."""
    if not os.path.exists(DB_PATH):
        return FAIL, "DB Import", "Database not found", None

    rows = _db_query("SELECT MAX(data_axle_import_date) AS latest FROM practices")
    if not rows or rows[0]["latest"] is None:
        return WARN, "DB Import", "No Data Axle imports found in DB", None

    latest_import = rows[0]["latest"]

    # Compare to newest CSV in processed/
    processed_csvs = glob(os.path.join(PROCESSED_DIR, "*.csv"))
    if processed_csvs:
        newest_csv_time = max(os.path.getmtime(f) for f in processed_csvs)
        newest_csv_date = datetime.fromtimestamp(newest_csv_time).strftime("%Y-%m-%d")
        if newest_csv_date > latest_import:
            detail = (
                f"CSV newer than import (CSV: {newest_csv_date}, import: {latest_import})"
            )
            fix = (
                "# Re-run the importer — a processed CSV is newer than the DB:\n"
                "cd ~/dental-pe-tracker\n"
                "python3 scrapers/data_axle_importer.py --auto"
            )
            return FAIL, "DB Import", detail, fix

    # Also check pipeline log for last successful run
    event = _last_pipeline_event("data_axle_importer")
    extra = ""
    if event:
        ts = event.get("timestamp", "")[:10]
        extra = f" (last run: {ts})"

    return PASS, "DB Import", f"Latest import: {latest_import}{extra}", None


def check_scoring_freshness():
    """4. Check if scoring is current relative to the latest import."""
    if not os.path.exists(DB_PATH):
        return FAIL, "ZIP Scoring", "Database not found", None

    import_rows = _db_query("SELECT MAX(data_axle_import_date) AS latest FROM practices")
    score_rows = _db_query("SELECT MAX(score_date) AS latest FROM zip_scores")

    if not score_rows or score_rows[0]["latest"] is None:
        return WARN, "ZIP Scoring", "No ZIP scores found — scoring never run", (
            "cd ~/dental-pe-tracker && python3 scrapers/merge_and_score.py"
        )

    latest_score = score_rows[0]["latest"]
    latest_import = import_rows[0]["latest"] if import_rows and import_rows[0]["latest"] else None

    if latest_import and latest_score < latest_import:
        detail = f"Scoring stale (last: {latest_score}, import: {latest_import})"
        fix = (
            "# Re-score after new imports:\n"
            "cd ~/dental-pe-tracker\n"
            "python3 scrapers/dso_classifier.py\n"
            "python3 scrapers/merge_and_score.py"
        )
        return FAIL, "ZIP Scoring", detail, fix

    # Check pipeline log for timing
    event = _last_pipeline_event("merge_and_score")
    extra = ""
    if event:
        ts = event.get("timestamp", "")[:10]
        extra = f" (last run: {ts})"

    return PASS, "ZIP Scoring", f"Latest score: {latest_score}{extra}", None


def check_db_compression():
    """5. Check if .db.gz is newer than .db."""
    if not os.path.exists(DB_PATH):
        return FAIL, "DB Compression", "Database file not found", None

    if not os.path.exists(DB_GZ_PATH):
        fix = (
            "# Compress the database for deployment:\n"
            "cd ~/dental-pe-tracker\n"
            "python3 -c \"\n"
            "import gzip, shutil\n"
            "with open('data/dental_pe_tracker.db','rb') as f:\n"
            "    with gzip.open('data/dental_pe_tracker.db.gz','wb',6) as gz:\n"
            "        shutil.copyfileobj(f, gz)\n"
            "print('Compressed.')\n"
            "\""
        )
        return FAIL, "DB Compression", ".db.gz not found — deployment will have no data", fix

    db_mtime = os.path.getmtime(DB_PATH)
    gz_mtime = os.path.getmtime(DB_GZ_PATH)

    if db_mtime > gz_mtime:
        age_seconds = db_mtime - gz_mtime
        if age_seconds < 60:
            units = f"{int(age_seconds)}s"
        elif age_seconds < 3600:
            units = f"{int(age_seconds / 60)}m"
        else:
            units = f"{age_seconds / 3600:.1f}h"

        fix = (
            "# Compress the database for deployment:\n"
            "cd ~/dental-pe-tracker\n"
            "python3 -c \"\n"
            "import gzip, shutil\n"
            "with open('data/dental_pe_tracker.db','rb') as f:\n"
            "    with gzip.open('data/dental_pe_tracker.db.gz','wb',6) as gz:\n"
            "        shutil.copyfileobj(f, gz)\n"
            "print('Compressed.')\n"
            "\""
        )
        return FAIL, "DB Compression", f".db.gz is {units} behind .db — deployment stale", fix

    return PASS, "DB Compression", ".db.gz is current", None


def check_git_push():
    """6. Check if latest local commits have been pushed."""
    # First check if there are uncommitted changes to .db.gz
    status_out, rc = _git("status", "--porcelain", "data/dental_pe_tracker.db.gz")
    uncommitted_gz = bool(status_out.strip()) if rc == 0 else False

    # Check commits ahead of remote
    ahead_out, rc = _git("rev-list", "--count", "origin/main..HEAD")
    if rc != 0:
        # Maybe remote not fetched — try fetch first
        _git("fetch", "--quiet", "origin")
        ahead_out, rc = _git("rev-list", "--count", "origin/main..HEAD")
        if rc != 0:
            return WARN, "Git Push", "Could not determine push status (fetch failed)", None

    try:
        ahead = int(ahead_out)
    except ValueError:
        return WARN, "Git Push", "Could not parse commit count", None

    if uncommitted_gz:
        fix = (
            "# Commit compressed DB and push:\n"
            "cd ~/dental-pe-tracker\n"
            "git add data/dental_pe_tracker.db.gz\n"
            f"git commit -m \"Update DB {date.today()}\"\n"
            "git push"
        )
        return FAIL, "Git Push", ".db.gz has uncommitted changes — deployment stale", fix

    if ahead > 0:
        fix = "cd ~/dental-pe-tracker && git push"
        return FAIL, "Git Push", f"{ahead} commit(s) ahead of origin/main — push needed", fix

    return PASS, "Git Push", "Up to date with origin/main", None


def check_classification_freshness():
    """Bonus: Check if DSO classifier has run after latest import."""
    event = _last_pipeline_event("dso_classifier")
    import_event = _last_pipeline_event("data_axle_importer")

    if not event:
        return WARN, "Classification", "DSO classifier has never run (per pipeline log)", (
            "cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py"
        )

    if import_event:
        import_ts = import_event.get("timestamp", "")
        classify_ts = event.get("timestamp", "")
        if import_ts > classify_ts:
            detail = f"Classifier stale (last: {classify_ts[:10]}, import: {import_ts[:10]})"
            fix = "cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py"
            return FAIL, "Classification", detail, fix

    ts = event.get("timestamp", "")[:10]
    status = event.get("status", "success")
    if status == "error":
        return FAIL, "Classification", f"Last run ({ts}) ended with error", (
            "cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py"
        )

    return PASS, "Classification", f"Last run: {ts}", None


# ── DB Stats (bonus info) ────────────────────────────────────────────────────

def get_db_stats():
    """Grab quick counts for the summary footer."""
    stats = {}
    if not os.path.exists(DB_PATH):
        return stats

    for label, query in [
        ("practices", "SELECT COUNT(*) FROM practices"),
        ("data_axle", "SELECT COUNT(*) FROM practices WHERE data_source = 'data_axle'"),
        ("classified", "SELECT COUNT(*) FROM practices WHERE ownership_status != 'unknown' AND ownership_status IS NOT NULL"),
        ("deals", "SELECT COUNT(*) FROM deals"),
        ("zip_scores", "SELECT COUNT(*) FROM zip_scores"),
    ]:
        rows = _db_query(query)
        if rows:
            stats[label] = rows[0][0]

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline health check for dental-pe-tracker"
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Show suggested fix commands for failing checks"
    )
    args = parser.parse_args()

    checks = [
        check_csv_downloads,
        check_unprocessed_csvs,
        check_db_import_freshness,
        check_classification_freshness,
        check_scoring_freshness,
        check_db_compression,
        check_git_push,
    ]

    results = []
    for check_fn in checks:
        try:
            result = check_fn()
            results.append(result)
        except Exception as e:
            results.append((WARN, check_fn.__name__, f"Check failed: {e}", None))

    # ── Print Report ──────────────────────────────────────────────────────

    print()
    print(f"{BOLD}Pipeline Health Check{RESET}")
    print("\u2501" * 60)

    fail_count = 0
    warn_count = 0
    fixes = []

    for symbol, label, detail, fix in results:
        print(f"  {symbol}  {label:<18} {DIM}\u2192{RESET} {detail}")
        if symbol == FAIL:
            fail_count += 1
            if fix:
                fixes.append((label, fix))
        elif symbol == WARN:
            warn_count += 1

    print("\u2501" * 60)

    # DB stats footer
    stats = get_db_stats()
    if stats:
        parts = []
        if "practices" in stats:
            parts.append(f"{stats['practices']:,} practices")
        if "data_axle" in stats:
            parts.append(f"{stats['data_axle']:,} Data Axle")
        if "classified" in stats:
            parts.append(f"{stats['classified']:,} classified")
        if "deals" in stats:
            parts.append(f"{stats['deals']:,} deals")
        if "zip_scores" in stats:
            parts.append(f"{stats['zip_scores']:,} scored ZIPs")
        print(f"  {DIM}DB: {' | '.join(parts)}{RESET}")

    # Overall verdict
    if fail_count == 0 and warn_count == 0:
        print(f"\n  {GREEN}{BOLD}All clear — pipeline is healthy.{RESET}")
    elif fail_count == 0:
        print(f"\n  {YELLOW}{BOLD}{warn_count} warning(s), no failures.{RESET}")
    else:
        print(f"\n  {RED}{BOLD}{fail_count} step(s) need attention.{RESET}", end="")
        if warn_count:
            print(f" {YELLOW}({warn_count} warning(s)){RESET}", end="")
        print()

    # Fix suggestions
    if args.fix and fixes:
        print()
        print(f"{BOLD}Suggested Fixes{RESET}")
        print("\u2500" * 60)
        for label, fix in fixes:
            print(f"\n  {RED}\u2717{RESET} {BOLD}{label}{RESET}:")
            for line in fix.split("\n"):
                print(f"    {line}")
        print()
    elif fixes and not args.fix:
        print(f"\n  {DIM}Run with --fix to see suggested commands.{RESET}")

    print()
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
