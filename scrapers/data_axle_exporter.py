#!/usr/bin/env python3
"""
Data Axle Reference Solutions — Smart Batch Exporter (v3 FINAL)

The fundamental problem with Data Axle:
  - 250 records max per download
  - CAPTCHAs every ~5 page flips
  - Can't select all results at once for large result sets
  - Must restart search between download batches

Our solution: split ZIPs into small batches (3-4 per search) so each search
yields ~75-120 results that fit in ONE download. No pagination cycling, no
multi-batch downloads, minimal CAPTCHAs.

The script handles ALL bookkeeping:
  - Batch planning (which ZIPs go in which search)
  - Progress tracking (resume if interrupted)
  - File naming and organization
  - CSV combination and deduplication
  - Time estimates and status reporting

YOU handle the browser interactions:
  - BU SSO login (once)
  - Loading your saved search template (once)
  - Pasting ZIP codes (script tells you exactly what to paste)
  - Clicking View Results, Select All, Download (script tells you when)
  - Solving CAPTCHAs if they appear
  - Navigating back to search between batches

This is a CLIPBOARD + TERMINAL GUIDE approach — no fragile DOM selectors.

USAGE:
  # See the full batch plan without doing anything
  python3 scrapers/data_axle_exporter.py --plan

  # Run interactively for Boston (your biggest gap — 0 records)
  python3 scrapers/data_axle_exporter.py --metro boston

  # Run for Chicagoland
  python3 scrapers/data_axle_exporter.py --metro chicagoland

  # Run for both metros
  python3 scrapers/data_axle_exporter.py --metro all

  # Resume from batch 5 if interrupted
  python3 scrapers/data_axle_exporter.py --metro boston --resume 5

  # Custom ZIPs (e.g., scouting Fort Myers)
  python3 scrapers/data_axle_exporter.py --zips 33901,33907,33908 --label fortmyers

  # Just combine + deduplicate existing CSVs (no browser needed)
  python3 scrapers/data_axle_exporter.py --combine

  # Adjust batch size (fewer ZIPs per search = fewer results = safer)
  python3 scrapers/data_axle_exporter.py --metro boston --batch-size 3

AFTER EXPORTING:
  python3 scrapers/data_axle_importer.py --preview   # sanity check
  python3 scrapers/data_axle_importer.py --auto       # import to DB
  python3 scrapers/dso_classifier.py                  # classify practices
  python3 scrapers/merge_and_score.py                 # recalculate scores
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from glob import glob

try:
    import pandas as pd
except ImportError:
    pd = None

# ── ZIP Code Definitions ─────────────────────────────────────────────────────
# Coverage: 1-hour commute from West Loop Chicago, Woodridge, and Bolingbrook

# Original 28 ZIPs (Naperville/DuPage/Will corridor)
CHICAGOLAND_ZIPS = [
    "60491", "60439", "60441", "60540", "60564", "60565", "60563", "60527",
    "60515", "60516", "60532", "60559", "60514", "60521", "60523", "60148",
    "60440", "60490", "60504", "60502", "60431", "60435", "60586", "60585",
    "60503", "60554", "60543", "60560",
]

# ── Expanded Chicagoland: 1-hr commute radius zones ─────────────────────────
# Use --metro chi-north, chi-city, chi-south, chi-west, chi-far-west, chi-far-south
# or --metro chi-all for the full expanded set

# North Shore + North suburbs (Evanston, Skokie, Wilmette, Highland Park, etc.)
CHI_NORTH_ZIPS = [
    "60004", "60005", "60007", "60008", "60010", "60015", "60016", "60017",
    "60018", "60022", "60025", "60026", "60035", "60037", "60038", "60040",
    "60045", "60053", "60056", "60061", "60062", "60067", "60068", "60069",
    "60070", "60074", "60076", "60077", "60089", "60090", "60091", "60093",
    "60201", "60202", "60203", "60712", "60714",
]

# Chicago city proper (Loop, North Side, South Side, West Side)
CHI_CITY_ZIPS = [
    "60601", "60602", "60603", "60604", "60605", "60606", "60607", "60608",
    "60609", "60610", "60611", "60612", "60613", "60614", "60615", "60616",
    "60617", "60618", "60619", "60620", "60621", "60622", "60623", "60624",
    "60625", "60626", "60628", "60629", "60630", "60631", "60632", "60633",
    "60634", "60636", "60637", "60638", "60639", "60640", "60641", "60642",
    "60643", "60644", "60645", "60646", "60647", "60649", "60651", "60652",
    "60653", "60654", "60655", "60656", "60657", "60659", "60660", "60661",
]

# South suburbs (Orland Park, Tinley Park, Homewood, Lansing, etc.)
CHI_SOUTH_ZIPS = [
    "60406", "60409", "60411", "60412", "60415", "60418", "60419", "60422",
    "60423", "60425", "60426", "60428", "60429", "60430", "60438", "60442",
    "60443", "60445", "60449", "60452", "60453", "60454", "60455", "60456",
    "60457", "60458", "60459", "60461", "60462", "60463", "60464", "60465",
    "60466", "60467", "60468", "60469", "60471", "60472", "60473", "60475",
    "60476", "60477", "60478", "60480", "60481", "60482", "60484", "60487",
    "60501", "60803", "60804", "60805", "60827",
]

# Inner west suburbs (Oak Park, Berwyn, Cicero, Maywood, Elmhurst, etc.)
CHI_WEST_ZIPS = [
    "60101", "60103", "60104", "60106", "60107", "60108", "60126", "60130",
    "60131", "60133", "60137", "60138", "60139", "60143", "60153", "60154",
    "60155", "60160", "60161", "60162", "60163", "60164", "60165", "60171",
    "60176", "60181", "60187", "60188", "60189", "60190", "60191", "60193",
    "60194", "60195", "60301", "60302", "60304", "60305", "60402", "60501",
    "60513", "60525", "60526", "60534", "60546", "60555", "60558", "60706",
    "60707",
]

# Far west (Aurora, Elgin, Batavia, Geneva, St. Charles, etc.)
CHI_FAR_WEST_ZIPS = [
    "60110", "60118", "60119", "60120", "60121", "60122", "60123", "60124",
    "60134", "60144", "60151", "60172", "60173", "60174", "60175", "60185",
    "60186", "60505", "60506", "60510", "60511", "60512", "60519", "60536",
    "60537", "60538", "60539", "60541", "60542", "60544", "60545", "60548",
]

# Far south Will County (Joliet extended, Frankfort, Manhattan, etc.)
CHI_FAR_SOUTH_ZIPS = [
    "60403", "60404", "60410", "60416", "60421", "60432", "60433", "60434",
    "60436", "60446", "60447", "60448", "60450", "60451",
]

# All expanded Chicago = original + all zones
CHI_ALL_EXPANDED = (
    CHICAGOLAND_ZIPS + CHI_NORTH_ZIPS + CHI_CITY_ZIPS + CHI_SOUTH_ZIPS +
    CHI_WEST_ZIPS + CHI_FAR_WEST_ZIPS + CHI_FAR_SOUTH_ZIPS
)
# Deduplicate while preserving order
_seen = set()
CHI_ALL_EXPANDED = [z for z in CHI_ALL_EXPANDED if not (z in _seen or _seen.add(z))]

BOSTON_ZIPS = [
    "02116", "02115", "02118", "02119", "02120", "02215", "02134", "02135",
    "02446", "02445", "02467", "02459", "02458", "02453", "02451", "02138",
    "02139", "02140", "02141", "02142", "02144",
]

# ~25-35 practices per suburban ZIP, 25 results per page, 250 per download.
# 4 ZIPs ≈ 100-140 results ≈ 4-6 pages → fits in one download every time.
# Use 3 if you're hitting >250 results per batch.
DEFAULT_BATCH_SIZE = 4

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle")
STATE_FILE = os.path.join(BASE_DIR, ".exporter_progress.json")


def get_existing_zips():
    """Scan existing CSVs to find ZIPs that already have data."""
    if pd is None:
        return set()
    existing = set()
    for f in glob(os.path.join(BASE_DIR, "*.csv")):
        if "combined" in os.path.basename(f).lower():
            continue
        try:
            df = pd.read_csv(f, dtype=str, usecols=["ZIP Code"], low_memory=False)
            existing.update(df["ZIP Code"].dropna().unique())
        except Exception:
            pass
    return existing

# ── Terminal Colors ───────────────────────────────────────────────────────────

class C:
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def info(msg):    print(f"{C.CYAN}[*]{C.RESET} {msg}")
def ok(msg):      print(f"{C.GREEN}[+]{C.RESET} {msg}")
def warn(msg):    print(f"{C.YELLOW}[!]{C.RESET} {msg}")
def err(msg):     print(f"{C.RED}[X]{C.RESET} {msg}")
def bold(msg):    print(f"{C.BOLD}[>]{C.RESET} {C.BOLD}{msg}{C.RESET}")
def dim(msg):     print(f"{C.DIM}    {msg}{C.RESET}")
def divider():    print(f"\n{C.DIM}{'─'*60}{C.RESET}")


# ── Batch Planning ────────────────────────────────────────────────────────────

def make_batches(zips, batch_size):
    """Split ZIP list into batches."""
    return [zips[i:i + batch_size] for i in range(0, len(zips), batch_size)]


def estimate_results(num_zips, metro):
    """Rough estimate of results for a set of ZIPs."""
    # Based on actual data: Chicagoland 28 ZIPs → 905 results ≈ 32/ZIP
    # Boston is denser, estimate ~25/ZIP
    per_zip = 32 if metro == "chicagoland" else 25
    return num_zips * per_zip


def show_plan(batches, metro_label, batch_size):
    """Display the full batch plan."""
    total_zips = sum(len(b) for b in batches)
    est_total = estimate_results(total_zips, metro_label)

    print()
    bold(f"EXPORT PLAN: {metro_label.upper()}")
    print()
    info(f"Total ZIPs:       {total_zips}")
    info(f"Batch size:       {batch_size} ZIPs per search")
    info(f"Total batches:    {len(batches)}")
    info(f"Est. total records: ~{est_total}")
    print()

    # Without batching comparison
    est_pages_unbatched = math.ceil(est_total / 25)
    est_download_cycles = math.ceil(est_pages_unbatched / 10)
    est_captchas_unbatched = est_pages_unbatched // 5

    print(f"  {'':>20} {'Manual (all ZIPs)':>22}  {'Batched':>20}")
    print(f"  {'─'*20} {'─'*22}  {'─'*20}")
    print(f"  {'Searches':>20} {'1':>22}  {len(batches):>20}")
    print(f"  {'Pages to flip':>20} {f'~{est_pages_unbatched}':>22}  {f'~{len(batches)*4}':>20}")
    print(f"  {'Download cycles':>20} {est_download_cycles:>22}  {len(batches):>20}")
    print(f"  {'CAPTCHAs (est.)':>20} {f'~{est_captchas_unbatched}':>22}  {f'~{len(batches)//3} or fewer':>20}")
    print(f"  {'Time estimate':>20} {f'~{est_captchas_unbatched * 3 + est_download_cycles * 5} min':>22}"
          f"  {f'~{len(batches) * 2} min':>20}")
    print()

    # Show existing data inventory
    existing = get_existing_zips()
    if existing:
        all_batch_zips = [z for b in batches for z in b]
        already_done = [z for z in all_batch_zips if z in existing]
        still_needed = [z for z in all_batch_zips if z not in existing]
        info(f"Already have data: {len(already_done)} ZIPs ({','.join(sorted(already_done)[:5])}{'...' if len(already_done) > 5 else ''})")
        info(f"Still needed:      {len(still_needed)} ZIPs")
        if already_done and still_needed:
            dim("TIP: Use --skip-done to skip ZIPs with existing data")
        print()

    bold("BATCH DETAILS:")
    for i, batch in enumerate(batches):
        est = estimate_results(len(batch), metro_label)
        est_pg = math.ceil(est / 25)
        zip_str = ",".join(batch)
        status = f"~{est} results, ~{est_pg} pages"
        print(f"  Batch {i+1:2d}/{len(batches):2d}: {zip_str}")
        dim(status)


# ── Progress Tracking ─────────────────────────────────────────────────────────

def save_progress(metro_label, batch_index, downloaded_files):
    """Save progress for resume capability."""
    state = {
        "metro": metro_label,
        "last_completed_batch": batch_index,
        "downloaded_files": downloaded_files,
        "timestamp": datetime.now().isoformat(),
    }
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_progress(metro_label):
    """Load saved progress. Returns (batch_index, downloaded_files) or (0, [])."""
    if not os.path.exists(STATE_FILE):
        return 0, []
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        if state.get("metro") == metro_label:
            return state.get("last_completed_batch", 0), state.get("downloaded_files", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return 0, []


def clear_progress():
    """Remove progress file after successful completion."""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


# ── Clipboard Helper ──────────────────────────────────────────────────────────

def copy_to_clipboard(text):
    """Copy text to system clipboard (macOS)."""
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        return True
    except FileNotFoundError:
        # Not macOS or pbcopy not available
        try:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE
            )
            process.communicate(text.encode("utf-8"))
            return True
        except FileNotFoundError:
            return False


# ── CSV Combination ───────────────────────────────────────────────────────────

def combine_csvs(metro_label=None, only_files=None):
    """Combine batch CSVs into a single deduplicated file.

    Args:
        metro_label: Metro name for output filename.
        only_files: If provided, combine only these specific files instead of globbing.
    """
    if pd is None:
        err("pandas not installed. Run: pip install pandas")
        return None

    if only_files:
        # Use the exact files we downloaded this session
        csv_files = sorted([f for f in only_files if os.path.exists(f)])
    else:
        # Glob for files — but only match files for THIS metro label
        patterns = []
        if metro_label:
            patterns.append(os.path.join(BASE_DIR, f"data_axle_{metro_label}*.csv"))
        # Also catch Detail*.csv but ONLY if no metro-labeled files exist
        patterns.append(os.path.join(BASE_DIR, "Detail*.csv"))
        patterns.append(os.path.join(BASE_DIR, "batch_*.csv"))

        all_files = set()
        for pat in patterns:
            all_files.update(glob(pat))

        # Exclude already-combined files
        csv_files = sorted([
            f for f in all_files
            if "combined" not in os.path.basename(f).lower()
            and "debug" not in f
        ])

    if not csv_files:
        err(f"No CSV files found in {BASE_DIR}")
        return None

    bold(f"Combining {len(csv_files)} CSV files...")
    dfs = []
    total_rows = 0
    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype=str, low_memory=False)
            dfs.append(df)
            total_rows += len(df)
            ok(f"  {os.path.basename(f)}: {len(df)} rows, {len(df.columns)} cols")
        except Exception as e:
            err(f"  {os.path.basename(f)}: FAILED - {e}")

    if not dfs:
        return None

    combined = pd.concat(dfs, ignore_index=True)

    # Deduplicate on Company Name + Address + ZIP Code
    dedup_cols = [c for c in ["Company Name", "Address", "ZIP Code"] if c in combined.columns]
    if dedup_cols:
        before = len(combined)
        combined = combined.drop_duplicates(subset=dedup_cols, keep="first")
        dupes = before - len(combined)
        if dupes > 0:
            info(f"  Removed {dupes} duplicate rows")

    timestamp = datetime.now().strftime("%Y%m%d")
    label = metro_label or "combined"
    out_path = os.path.join(BASE_DIR, f"data_axle_{label}_{timestamp}_combined.csv")
    combined.to_csv(out_path, index=False)

    print()
    ok(f"Combined: {len(combined)} unique rows → {out_path}")
    ok(f"  Columns: {len(combined.columns)}")
    if "ZIP Code" in combined.columns:
        zip_counts = combined["ZIP Code"].value_counts()
        ok(f"  ZIP codes covered: {len(zip_counts)}")
        for z, cnt in zip_counts.head(5).items():
            dim(f"{z}: {cnt} practices")
        if len(zip_counts) > 5:
            dim(f"... and {len(zip_counts) - 5} more")

    return out_path


# ── File Detection ────────────────────────────────────────────────────────────

def find_new_csv(before_files, search_dirs=None):
    """Find newly downloaded CSV files by comparing directory snapshots."""
    if search_dirs is None:
        search_dirs = [
            BASE_DIR,
            os.path.expanduser("~/Downloads"),
        ]

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        current = set(os.listdir(d))
        # If this is our base dir, compare against before_files
        if d == BASE_DIR:
            new = current - before_files
        else:
            # For ~/Downloads, look for recent Data Axle files
            new = set()
            for f in current:
                if f.lower().endswith(".csv") and "detail" in f.lower():
                    fpath = os.path.join(d, f)
                    # Created in last 5 minutes
                    if time.time() - os.path.getmtime(fpath) < 300:
                        new.add(f)

        csv_new = [f for f in new if f.lower().endswith(".csv")
                    and not f.startswith(".")]
        if csv_new:
            return os.path.join(d, csv_new[0])

    return None


# ── Interactive Export Loop ───────────────────────────────────────────────────

def run_export(metro_label, batches, start_batch=0, downloaded_files=None):
    """Main interactive export loop."""
    if downloaded_files is None:
        downloaded_files = []

    os.makedirs(BASE_DIR, exist_ok=True)
    total_batches = len(batches)

    # ── Intro ─────────────────────────────────────────────────────────────
    print()
    bold("=" * 58)
    bold("  DATA AXLE SMART BATCH EXPORTER")
    bold("=" * 58)
    print()

    if start_batch == 0:
        bold("SETUP (one time):")
        print("""
   1. Open your browser
   2. Go to bu.edu/library
   3. Search for "Data Axle Reference Solutions"
   4. Click through to access the database
   5. Select "U.S. Businesses"
   6. Load your saved search template (SIC 8021 dental)
   7. CLEAR the ZIP code field (script will tell you what to paste)
""")
        bold("Press Enter when you're on the Data Axle search page...")
        input("    >>> ")
        print()
    else:
        info(f"Resuming from batch {start_batch + 1}/{total_batches}")
        info(f"Already downloaded: {len(downloaded_files)} files")
        print()

    # ── Process each batch ────────────────────────────────────────────────
    for batch_idx in range(start_batch, total_batches):
        batch = batches[batch_idx]
        batch_num = batch_idx + 1
        zip_str = ",".join(batch)
        est = estimate_results(len(batch), metro_label)

        divider()
        bold(f"BATCH {batch_num}/{total_batches}")
        info(f"ZIPs: {zip_str}")
        info(f"Expected: ~{est} results (~{math.ceil(est/25)} pages)")
        print()

        # Copy ZIPs to clipboard
        if copy_to_clipboard(zip_str):
            ok(f"ZIP codes copied to clipboard! Just paste (Cmd+V) into the ZIP field.")
        else:
            warn("Could not copy to clipboard. Copy this manually:")
            print(f"\n    {zip_str}\n")

        # Instructions for this batch
        if batch_idx == start_batch and start_batch == 0:
            bold("In the browser:")
            print(f"   1. Paste the ZIP codes into the ZIP/Geography field")
            print(f"   2. Make sure SIC code is 8021")
            print(f"   3. Click 'View Results'")
        else:
            bold("In the browser:")
            print(f"   1. Click 'New Search' or 'Modify Search'")
            print(f"   2. Clear the old ZIP codes")
            print(f"   3. Paste the new ZIP codes (already on clipboard)")
            print(f"   4. Click 'View Results'")

        print()
        bold("Press Enter when you see the results...")
        input("    >>> ")

        # Check result count
        print()
        result_input = input(f"    How many results? (press Enter to skip, or type number): ").strip()
        is_overflow = False
        if result_input.isdigit():
            result_count = int(result_input)
            pages = math.ceil(result_count / 25)
            if result_count > 250:
                is_overflow = True
                num_downloads = math.ceil(result_count / 250)
                warn(f"{result_count} results > 250 limit!")
                ok(f"No worries — you'll do {num_downloads} downloads for this batch.")
                ok(f"Download records 1-250 first, then 251-{result_count}.")
            else:
                ok(f"{result_count} results across {pages} pages — fits in one download!")
        print()

        # Select and download
        bold("Now in the browser:")
        print(f"   1. Select ALL results (checkbox by 'Company Name' on each page,")
        print(f"      or 'Select All on All Pages' if available)")
        print(f"   2. Click 'Download'")
        print(f"   3. Format: CSV (or Excel)")
        if batch_idx == start_batch:
            print(f"   4. Detail level: 'Custom' — CHECK ALL FIELDS")
            print(f"      (Company, DBA, Address, City, State, ZIP, Phone, SIC,")
            print(f"       NAICS, Employees, Revenue, Year Est., Ownership,")
            print(f"       Locations, Contact Name, Lat/Long, County)")
            print(f"   5. Click 'Download Records'")
        else:
            print(f"   4. Same fields as before (should be remembered)")
            print(f"   5. Click 'Download Records'")

        # Determine how many download passes for this batch
        download_passes = (math.ceil(result_count / 250) if is_overflow else 1)

        for dl_pass in range(download_passes):
            pass_label = f" (part {dl_pass + 1}/{download_passes})" if download_passes > 1 else ""

            if dl_pass > 0:
                divider()
                bold(f"OVERFLOW DOWNLOAD — part {dl_pass + 1}/{download_passes}")
                ok(f"Download the next 250 records (or remaining) for this same batch.")
                bold("Press Enter AFTER the file has finished downloading...")
                input("    >>> ")
            else:
                # Snapshot the directory before download
                print()
                bold(f"Press Enter AFTER the file has finished downloading{pass_label}...")
                input("    >>> ")

            before_files = set(os.listdir(BASE_DIR))

            # Try to find the new file
            new_file = find_new_csv(before_files)
            if new_file:
                # Rename with meaningful name
                ext = os.path.splitext(new_file)[1]
                part_suffix = f"_p{dl_pass + 1}" if download_passes > 1 else ""
                new_name = f"data_axle_{metro_label}_batch{batch_num:02d}{part_suffix}_{datetime.now().strftime('%Y%m%d')}{ext}"
                dest = os.path.join(BASE_DIR, new_name)

                # Don't overwrite if dest exists
                if os.path.exists(dest):
                    new_name = f"data_axle_{metro_label}_batch{batch_num:02d}{part_suffix}_{datetime.now().strftime('%Y%m%d_%H%M')}{ext}"
                    dest = os.path.join(BASE_DIR, new_name)

                shutil.move(new_file, dest)
                downloaded_files.append(dest)

                # Count rows
                try:
                    with open(dest) as fh:
                        row_count = sum(1 for _ in fh) - 1
                    ok(f"Saved: {new_name} ({row_count} rows)")
                except Exception:
                    ok(f"Saved: {new_name}")
            else:
                warn("Could not auto-detect downloaded file.")
                print(f"    Check ~/Downloads/ for the latest Detail*.csv")
                manual = input(f"    Enter filename (or press Enter to skip): ").strip()
                if manual:
                    for search_dir in [os.path.expanduser("~/Downloads"), BASE_DIR]:
                        candidate = os.path.join(search_dir, manual)
                        if os.path.exists(candidate):
                            part_suffix = f"_p{dl_pass + 1}" if download_passes > 1 else ""
                            new_name = f"data_axle_{metro_label}_batch{batch_num:02d}{part_suffix}_{datetime.now().strftime('%Y%m%d')}.csv"
                            dest = os.path.join(BASE_DIR, new_name)
                            shutil.move(candidate, dest)
                            downloaded_files.append(dest)
                            ok(f"Moved: {new_name}")
                            break
                    else:
                        warn(f"File not found: {manual}")
                else:
                    warn("Skipped. You can re-export this batch later with --resume")

        # Save progress
        save_progress(metro_label, batch_idx + 1, downloaded_files)

        # Status update
        remaining = total_batches - batch_num
        if remaining > 0:
            info(f"Progress: {batch_num}/{total_batches} batches done, {remaining} remaining")
            est_minutes = remaining * 2
            dim(f"~{est_minutes} minutes remaining")

    # ── All batches complete ──────────────────────────────────────────────
    divider()
    print()
    bold("=" * 58)
    ok(f"ALL {total_batches} BATCHES COMPLETE!")
    bold("=" * 58)
    print()
    ok(f"Downloaded {len(downloaded_files)} files to {BASE_DIR}")
    for f in downloaded_files:
        dim(os.path.basename(f))

    # Auto-combine — only the files from this session
    print()
    bold("Combining CSVs...")
    combined = combine_csvs(metro_label, only_files=downloaded_files)

    # Clean up progress
    clear_progress()

    # Next steps
    print()
    bold("NEXT STEPS:")
    print(f"   1. Preview import:  python3 scrapers/data_axle_importer.py --preview")
    print(f"   2. Import to DB:    python3 scrapers/data_axle_importer.py --auto")
    print(f"   3. Classify DSOs:   python3 scrapers/dso_classifier.py")
    print(f"   4. Score practices: python3 scrapers/merge_and_score.py")
    print()

    return downloaded_files


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Data Axle Smart Batch Exporter — clipboard-guided interactive export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  %(prog)s --plan                     Show batch plan (no browser needed)
  %(prog)s --metro boston              Export Boston Metro ZIPs
  %(prog)s --metro chicagoland        Export Chicagoland ZIPs
  %(prog)s --metro all                Export both metros
  %(prog)s --metro boston --resume 5   Resume Boston from batch 5
  %(prog)s --combine                  Just combine existing CSVs
  %(prog)s --zips 33901,33907 --label fortmyers   Custom ZIPs
        """,
    )
    parser.add_argument(
        "--metro", choices=[
            "chicagoland", "boston", "all",
            "chi-north", "chi-city", "chi-south", "chi-west",
            "chi-far-west", "chi-far-south", "chi-all",
        ],
        help="Metro area to export (chi-* for expanded Chicago zones)"
    )
    parser.add_argument(
        "--zips", type=str, default=None,
        help="Comma-separated ZIP codes (overrides --metro)"
    )
    parser.add_argument(
        "--label", type=str, default="custom",
        help="Label for custom ZIP exports (used in filenames)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"ZIPs per search batch (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--resume", type=int, default=None,
        help="Resume from batch N (1-indexed)"
    )
    parser.add_argument(
        "--plan", action="store_true",
        help="Show batch plan without exporting"
    )
    parser.add_argument(
        "--combine", action="store_true",
        help="Just combine existing CSVs without exporting"
    )
    parser.add_argument(
        "--skip-done", action="store_true",
        help="Skip ZIPs that already have data in existing CSVs"
    )
    args = parser.parse_args()

    # ── Combine-only mode ─────────────────────────────────────────────────
    if args.combine:
        label = args.metro or args.label or None
        combine_csvs(label)
        return

    # ── Determine ZIPs ────────────────────────────────────────────────────
    METRO_MAP = {
        "chicagoland": ("chicagoland", CHICAGOLAND_ZIPS),
        "boston": ("boston", BOSTON_ZIPS),
        "all": ("all", CHICAGOLAND_ZIPS + BOSTON_ZIPS),
        "chi-north": ("chi_north", CHI_NORTH_ZIPS),
        "chi-city": ("chi_city", CHI_CITY_ZIPS),
        "chi-south": ("chi_south", CHI_SOUTH_ZIPS),
        "chi-west": ("chi_west", CHI_WEST_ZIPS),
        "chi-far-west": ("chi_far_west", CHI_FAR_WEST_ZIPS),
        "chi-far-south": ("chi_far_south", CHI_FAR_SOUTH_ZIPS),
        "chi-all": ("chi_all", CHI_ALL_EXPANDED),
    }

    if args.zips:
        all_zips = [z.strip() for z in args.zips.split(",") if z.strip()]
        metro_label = args.label
    elif args.metro in METRO_MAP:
        metro_label, all_zips = METRO_MAP[args.metro]
    else:
        # Default: show help
        parser.print_help()
        print()
        bold("TIP: Start with --plan to see the batch plan, then --metro boston")
        return

    # ── Skip ZIPs with existing data ──────────────────────────────────────
    if args.skip_done:
        existing = get_existing_zips()
        before_count = len(all_zips)
        skipped = [z for z in all_zips if z in existing]
        all_zips = [z for z in all_zips if z not in existing]
        if skipped:
            info(f"Skipping {len(skipped)} ZIPs with existing data: {','.join(skipped)}")
            info(f"Remaining: {len(all_zips)} of {before_count} ZIPs")
        if not all_zips:
            ok("All ZIPs already have data! Nothing to export.")
            return

    batches = make_batches(all_zips, args.batch_size)

    # ── Plan-only mode ────────────────────────────────────────────────────
    if args.plan:
        show_plan(batches, metro_label, args.batch_size)
        return

    # ── Resume logic ──────────────────────────────────────────────────────
    start_batch = 0
    downloaded_files = []

    if args.resume is not None:
        start_batch = max(0, args.resume - 1)  # Convert 1-indexed to 0-indexed
        info(f"Resuming from batch {args.resume}")
    else:
        # Check for saved progress
        saved_batch, saved_files = load_progress(metro_label)
        if saved_batch > 0:
            warn(f"Found saved progress: {saved_batch}/{len(batches)} batches completed")
            choice = input(f"    Resume from batch {saved_batch + 1}? [Y/n]: ").strip().lower()
            if choice != "n":
                start_batch = saved_batch
                downloaded_files = saved_files
                ok(f"Resuming from batch {start_batch + 1}")
            else:
                info("Starting fresh")

    # ── Show plan then run ────────────────────────────────────────────────
    show_plan(batches, metro_label, args.batch_size)

    print()
    bold("Ready to start exporting?")
    confirm = input("    Press Enter to begin (or 'q' to quit): ").strip().lower()
    if confirm == "q":
        info("Cancelled.")
        return

    run_export(metro_label, batches, start_batch, downloaded_files)


if __name__ == "__main__":
    main()
