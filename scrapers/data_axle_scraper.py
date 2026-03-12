"""
Data Axle Reference Solutions — Semi-Automated Playwright Exporter

Automates the tedious CSV export from Data Axle (via BU Library) by splitting
ZIP codes into small batches (3-5 ZIPs per search) to stay under 10 pages of
results, then auto-navigating, selecting, and downloading each batch.

STRATEGY:
  Data Axle caps page selection at 10 pages and triggers CAPTCHA every ~5 page
  flips. By keeping each search to 3-5 ZIPs we get ~3-5 pages of results (25/page),
  so we can select all pages in one shot — no re-navigation, minimal CAPTCHAs.

HUMAN-IN-THE-LOOP:
  1. BU SSO login — you log in manually, script waits
  2. CAPTCHAs — script pauses, you solve, press Enter to continue
  3. Field checkbox selection — done once at the first export, then memorized

USAGE:
  # Full run — all Chicagoland + Boston ZIPs
  python3 scrapers/data_axle_scraper.py

  # Only Chicagoland
  python3 scrapers/data_axle_scraper.py --metro chicagoland

  # Only Boston
  python3 scrapers/data_axle_scraper.py --metro boston

  # Custom ZIPs (overrides metro)
  python3 scrapers/data_axle_scraper.py --zips 60491,60439,60441

  # Custom batch size (default 4)
  python3 scrapers/data_axle_scraper.py --batch-size 3

  # Resume from batch N (if interrupted)
  python3 scrapers/data_axle_scraper.py --resume 5

  # Dry run — show batches without launching browser
  python3 scrapers/data_axle_scraper.py --dry-run

OUTPUT:
  Downloads CSVs to ~/dental-pe-tracker/data/data-axle/
  Ready for: python3 scrapers/data_axle_importer.py --auto
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    print("ERROR: Playwright not installed. Run:")
    print("  pip install playwright && python -m playwright install chromium")
    sys.exit(1)

# ── ZIP Code Batches ─────────────────────────────────────────────────────────

CHICAGOLAND_ZIPS = [
    "60491", "60439", "60441", "60540", "60564", "60565", "60563", "60527",
    "60515", "60516", "60532", "60559", "60514", "60521", "60523", "60148",
    "60440", "60490", "60504", "60502", "60431", "60435", "60586", "60585",
    "60503", "60554", "60543", "60560",
]

BOSTON_ZIPS = [
    "02116", "02115", "02118", "02119", "02120", "02215", "02134", "02135",
    "02446", "02445", "02467", "02459", "02458", "02453", "02451", "02138",
    "02139", "02140", "02141", "02142", "02144",
]

# Average ~25 results per page. Target <=5 pages per batch = ~125 results.
# Rough estimate: ~25-35 dental practices per ZIP in suburban Chicagoland,
# ~15-30 in Boston Metro. So 4 ZIPs ≈ 100-140 results ≈ 4-6 pages.
DEFAULT_BATCH_SIZE = 4

# ── Paths ────────────────────────────────────────────────────────────────────

DOWNLOAD_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle")
STATE_FILE = os.path.join(DOWNLOAD_DIR, ".scraper_state.txt")

# ── Data Axle URL ────────────────────────────────────────────────────────────
# BU Library proxy to Data Axle Reference Solutions (U.S. Businesses)
DATA_AXLE_URL = "https://www.referenceusa.com/UsBusiness/Search/Custom/f5a0b7d1e4fc4bfcad8fb1e7b1c9d2a3"
# Fallback: go through BU Library search
BU_LIBRARY_URL = "https://www.bu.edu/library/"

# ── SIC Code ─────────────────────────────────────────────────────────────────
SIC_CODE = "8021"  # Offices and clinics of dentists

# ── Export Fields to Select ──────────────────────────────────────────────────
# These are the field labels to check in the export dialog.
# The script will try to check all of them. If a label isn't found, it skips it.
EXPORT_FIELDS = [
    "Company Name", "DBA Name", "Doing Business As",
    "Address", "Address Line 1", "Street Address",
    "City", "State", "ZIP Code", "ZIP+4", "Plus 4",
    "Phone", "Phone Number",
    "SIC Code", "Primary SIC Code", "SIC Description",
    "NAICS Code", "Primary NAICS Code", "NAICS Description",
    "Employee Size Range", "Employee Size Actual", "Actual Employee Size",
    "Annual Sales Volume", "Sales Volume", "Sales Volume Range",
    "Year Established",
    "Ownership", "Ownership Code",
    "Number of Locations", "Location Type",
    "Contact First Name", "Contact Last Name", "Contact Title",
    "First Name", "Last Name", "Title",
    "Latitude", "Longitude",
    "County", "FIPS Code", "Census Tract", "MSA Code",
    "Square Footage", "Credit Score Range",
    "Years In Database",
]


def make_batches(zips, batch_size):
    """Split ZIP list into batches of batch_size."""
    return [zips[i:i + batch_size] for i in range(0, len(zips), batch_size)]


def human_pause(message):
    """Pause for human intervention (CAPTCHA, login, etc.)."""
    print(f"\n{'='*60}")
    print(f"  HUMAN ACTION NEEDED: {message}")
    print(f"{'='*60}")
    input("  Press ENTER when done... ")
    print()


def save_progress(batch_index, metro_label):
    """Save current batch index so we can resume on interruption."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(f"{metro_label}:{batch_index}")


def load_progress(metro_label):
    """Load last completed batch index for resume."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            content = f.read().strip()
            if content.startswith(f"{metro_label}:"):
                return int(content.split(":")[1])
    return 0



def run_scraper(args):
    """Main scraper logic."""

    # ── Determine ZIPs ───────────────────────────────────────────────────
    if args.zips:
        all_zips = [z.strip() for z in args.zips.split(",") if z.strip()]
        metro_label = "custom"
    elif args.metro == "chicagoland":
        all_zips = CHICAGOLAND_ZIPS
        metro_label = "chicagoland"
    elif args.metro == "boston":
        all_zips = BOSTON_ZIPS
        metro_label = "boston"
    else:
        all_zips = CHICAGOLAND_ZIPS + BOSTON_ZIPS
        metro_label = "all"

    batches = make_batches(all_zips, args.batch_size)
    total_batches = len(batches)
    total_zips = len(all_zips)

    print(f"\nData Axle Exporter")
    print(f"  Metro:      {metro_label}")
    print(f"  Total ZIPs: {total_zips}")
    print(f"  Batch size: {args.batch_size} ZIPs per search")
    print(f"  Batches:    {total_batches}")
    print(f"  Output:     {DOWNLOAD_DIR}")
    print()

    # Show batch plan
    for i, batch in enumerate(batches):
        marker = " <-- resume" if i == args.resume else ""
        print(f"  Batch {i+1:2d}: {','.join(batch)}{marker}")
    print()

    if args.dry_run:
        est_pages = math.ceil(total_zips * 28 / 25)  # ~28 practices/ZIP, 25/page
        print(f"Estimated total results: ~{total_zips * 28}")
        print(f"Estimated total pages:   ~{est_pages}")
        print(f"Without batching: {math.ceil(est_pages / 10)} re-navigation cycles, "
              f"~{est_pages // 5} CAPTCHAs")
        print(f"With batching:    {total_batches} searches, "
              f"~{total_batches} CAPTCHAs (one per search, maybe zero)")
        print("\nDry run complete. Remove --dry-run to launch browser.")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    start_batch = args.resume

    # ── Launch Browser ───────────────────────────────────────────────────
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,  # Must be visible for SSO login + CAPTCHAs
            downloads_path=DOWNLOAD_DIR,
            slow_mo=300,  # Slow enough to look human, fast enough to save time
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # ── Step 1: Navigate to Data Axle via BU Library ─────────────
        print("Step 1: Navigating to BU Library...")
        page.goto(BU_LIBRARY_URL, wait_until="domcontentloaded", timeout=30000)

        human_pause(
            "Log into BU Library, navigate to Data Axle Reference Solutions,\n"
            "  select 'U.S. Businesses' database, and get to the search page.\n"
            "  (If you have a saved search template, load it now — just clear\n"
            "  the ZIP code field so the script can fill it.)\n\n"
            "  The script will handle everything from the search page onward."
        )

        # ── Step 2: Process each batch ───────────────────────────────
        downloaded_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        for batch_idx in range(start_batch, total_batches):
            batch = batches[batch_idx]
            batch_num = batch_idx + 1
            zip_str = ",".join(batch)

            print(f"\n{'─'*60}")
            print(f"Batch {batch_num}/{total_batches}: ZIPs {zip_str}")
            print(f"{'─'*60}")

            # ── 2a: Enter search criteria ────────────────────────────
            # Try to find and fill the SIC code field
            try:
                sic_input = page.locator(
                    'input[name*="sic" i], input[name*="SIC" i], '
                    'input[placeholder*="SIC" i], input[id*="sic" i]'
                ).first
                if sic_input.is_visible(timeout=3000):
                    sic_input.clear()
                    sic_input.fill(SIC_CODE)
                    print(f"  Filled SIC code: {SIC_CODE}")
            except (PwTimeout, Exception):
                print("  SIC field not found — may already be set from template")

            # Try to find and fill the ZIP code field
            try:
                zip_input = page.locator(
                    'input[name*="zip" i], input[name*="ZIP" i], '
                    'input[placeholder*="ZIP" i], input[id*="zip" i], '
                    'textarea[name*="zip" i], textarea[id*="zip" i]'
                ).first
                if zip_input.is_visible(timeout=3000):
                    zip_input.clear()
                    zip_input.fill(zip_str)
                    print(f"  Filled ZIP codes: {zip_str}")
                else:
                    raise Exception("ZIP field not visible")
            except (PwTimeout, Exception):
                human_pause(
                    f"Could not auto-fill ZIP codes. Please manually enter:\n"
                    f"  SIC: {SIC_CODE}\n"
                    f"  ZIPs: {zip_str}\n"
                    f"  Then click 'View Results' / 'Search'"
                )

            # ── 2b: Click Search / View Results ──────────────────────
            try:
                search_btn = page.locator(
                    'button:has-text("View Results"), button:has-text("Search"), '
                    'input[type="submit"][value*="Search" i], '
                    'input[type="submit"][value*="View" i], '
                    'a:has-text("View Results")'
                ).first
                if search_btn.is_visible(timeout=3000):
                    search_btn.click()
                    print("  Clicked Search/View Results")
                    page.wait_for_load_state("networkidle", timeout=30000)
                else:
                    raise Exception("Search button not visible")
            except (PwTimeout, Exception):
                human_pause(
                    "Could not find Search button.\n"
                    "  Please click 'View Results' or 'Search' manually."
                )

            # Wait for results to load
            time.sleep(2)

            # ── 2c: Check for CAPTCHA ────────────────────────────────
            if _check_captcha(page):
                human_pause("CAPTCHA detected! Please solve it.")

            # ── 2d: Get result count ─────────────────────────────────
            try:
                result_text = page.locator(
                    'text=/\\d+\\s*(results?|records?|entries)/i'
                ).first.text_content(timeout=5000)
                print(f"  Results: {result_text.strip()}")
            except (PwTimeout, Exception):
                print("  Could not read result count")

            # ── 2e: Select all records on all pages ──────────────────
            try:
                select_all = page.locator(
                    'a:has-text("Select All"), button:has-text("Select All"), '
                    'input[type="checkbox"][id*="select" i], '
                    'a:has-text("all on all pages"), '
                    'label:has-text("Select All")'
                ).first
                if select_all.is_visible(timeout=5000):
                    select_all.click()
                    print("  Clicked Select All")
                    time.sleep(1)
                else:
                    raise Exception("Select All not visible")
            except (PwTimeout, Exception):
                # Try selecting pages individually (up to 10)
                print("  Select All not found, trying page-by-page selection...")
                _select_pages_individually(page)

            # ── 2f: Click Download/Export ─────────────────────────────
            try:
                export_btn = page.locator(
                    'a:has-text("Download"), button:has-text("Download"), '
                    'a:has-text("Export"), button:has-text("Export"), '
                    'a[title*="Download" i], a[title*="Export" i]'
                ).first
                if export_btn.is_visible(timeout=5000):
                    export_btn.click()
                    print("  Clicked Download/Export")
                    time.sleep(2)
                else:
                    raise Exception("Export button not visible")
            except (PwTimeout, Exception):
                human_pause(
                    "Could not find Download/Export button.\n"
                    "  Please click it manually."
                )

            # ── 2g: Select CSV format ────────────────────────────────
            try:
                csv_option = page.locator(
                    'input[value*="CSV" i], label:has-text("CSV"), '
                    'option:text("CSV"), a:text("CSV")'
                ).first
                if csv_option.is_visible(timeout=3000):
                    csv_option.click()
                    print("  Selected CSV format")
                    time.sleep(1)
            except (PwTimeout, Exception):
                print("  CSV format option not found — may already be default")

            # ── 2h: Select export fields ─────────────────────────────
            if batch_idx == start_batch:
                # First batch — try to check all fields
                _select_export_fields(page)
                human_pause(
                    "Please verify all export fields are checked:\n"
                    "  Company Name, DBA, Address, City, State, ZIP, Phone,\n"
                    "  SIC, NAICS, Employees, Revenue, Year Est., Ownership,\n"
                    "  Location Type, Contact Name, Lat/Long, County.\n\n"
                    "  The script will remember these settings for subsequent batches."
                )
            else:
                print("  Using same field selection as first batch")

            # ── 2i: Trigger the download ─────────────────────────────
            try:
                download_btn = page.locator(
                    'button:has-text("Download"), input[type="submit"][value*="Download" i], '
                    'a:has-text("Download Records"), button:has-text("Export")'
                ).first

                if download_btn.is_visible(timeout=3000):
                    # Start waiting for download BEFORE clicking
                    with page.expect_download(timeout=120000) as dl_info:
                        download_btn.click()
                        print("  Downloading...")

                    download = dl_info.value
                    # Name it with batch info
                    filename = f"data_axle_{metro_label}_batch{batch_num:02d}_{timestamp}.csv"
                    dest = os.path.join(DOWNLOAD_DIR, filename)
                    download.save_as(dest)
                    downloaded_files.append(dest)
                    print(f"  Saved: {filename}")
                else:
                    raise Exception("Download button not visible")
            except (PwTimeout, Exception) as e:
                human_pause(
                    f"Auto-download failed ({e}).\n"
                    f"  Please manually download the CSV.\n"
                    f"  Save it to: {DOWNLOAD_DIR}"
                )
                # Check if file appeared in download dir
                _check_manual_download(batch_num, timestamp, metro_label, downloaded_files)

            # ── 2j: Save progress ────────────────────────────────────
            save_progress(batch_idx + 1, metro_label)
            print(f"  Progress saved: batch {batch_num}/{total_batches} complete")

            # ── 2k: Navigate back to search for next batch ───────────
            if batch_idx < total_batches - 1:
                try:
                    # Try clicking "New Search" or "Modify Search"
                    new_search = page.locator(
                        'a:has-text("New Search"), a:has-text("Modify Search"), '
                        'a:has-text("Back to Search"), button:has-text("New Search")'
                    ).first
                    if new_search.is_visible(timeout=5000):
                        new_search.click()
                        page.wait_for_load_state("networkidle", timeout=15000)
                        print("  Navigated back to search page")
                    else:
                        page.go_back()
                        page.go_back()
                        page.wait_for_load_state("networkidle", timeout=15000)
                except (PwTimeout, Exception):
                    human_pause(
                        "Could not navigate back to search page.\n"
                        "  Please navigate back to the search form."
                    )

                # Check for CAPTCHA after navigation
                time.sleep(1)
                if _check_captcha(page):
                    human_pause("CAPTCHA detected! Please solve it.")

        # ── Done ─────────────────────────────────────────────────────
        browser.close()

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  EXPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Batches completed: {total_batches - start_batch}")
    print(f"  Files downloaded:  {len(downloaded_files)}")
    for f in downloaded_files:
        size = os.path.getsize(f) if os.path.exists(f) else 0
        print(f"    {os.path.basename(f)} ({size:,} bytes)")
    print()
    print("Next steps:")
    print(f"  1. Preview:  python3 scrapers/data_axle_importer.py --preview")
    print(f"  2. Import:   python3 scrapers/data_axle_importer.py --auto")
    print(f"  3. Classify: python3 scrapers/dso_classifier.py")
    print(f"  4. Score:    python3 scrapers/merge_and_score.py")

    # Clean up state file on success
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def _check_captcha(page):
    """Check if a CAPTCHA is present on the page."""
    captcha_selectors = [
        'iframe[src*="captcha"]', 'iframe[src*="recaptcha"]',
        'div[class*="captcha" i]', 'div[id*="captcha" i]',
        'img[alt*="captcha" i]', 'text=/verify.*human/i',
        'text=/captcha/i', 'div.g-recaptcha',
    ]
    for sel in captcha_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=1000):
                return True
        except (PwTimeout, Exception):
            continue
    return False


def _select_pages_individually(page):
    """Try to select pages 1 through 10 individually via checkboxes."""
    selected = 0
    for pg_num in range(1, 11):
        try:
            checkbox = page.locator(
                f'input[type="checkbox"][value="{pg_num}"], '
                f'input[type="checkbox"][data-page="{pg_num}"], '
                f'label:has-text("Page {pg_num}") input[type="checkbox"]'
            ).first
            if checkbox.is_visible(timeout=1000):
                if not checkbox.is_checked():
                    checkbox.check()
                selected += 1
        except (PwTimeout, Exception):
            break
    if selected > 0:
        print(f"    Selected {selected} pages individually")
    else:
        human_pause(
            "Could not select pages automatically.\n"
            "  Please select all available pages manually (up to 10)."
        )


def _select_export_fields(page):
    """Try to check all desired export field checkboxes."""
    checked = 0
    for field in EXPORT_FIELDS:
        try:
            # Try label text match first
            checkbox = page.locator(
                f'label:has-text("{field}") input[type="checkbox"]'
            ).first
            if checkbox.is_visible(timeout=500):
                if not checkbox.is_checked():
                    checkbox.check()
                checked += 1
                continue
        except (PwTimeout, Exception):
            pass

        try:
            # Try checkbox with matching value or name
            checkbox = page.locator(
                f'input[type="checkbox"][value*="{field}" i]'
            ).first
            if checkbox.is_visible(timeout=500):
                if not checkbox.is_checked():
                    checkbox.check()
                checked += 1
        except (PwTimeout, Exception):
            pass

    print(f"  Auto-checked {checked} export fields")

    # Also try "Select All Fields" if available
    try:
        select_all_fields = page.locator(
            'a:has-text("Select All"), label:has-text("Select All Fields"), '
            'input[type="checkbox"][id*="all" i]'
        ).first
        if select_all_fields.is_visible(timeout=2000):
            select_all_fields.click()
            print("  Clicked 'Select All Fields'")
    except (PwTimeout, Exception):
        pass


def _check_manual_download(batch_num, timestamp, metro_label, downloaded_files):
    """Check if user manually downloaded a file."""
    # Look for any new CSV in the download dir
    before = set(os.listdir(DOWNLOAD_DIR))
    human_pause(
        "After saving the file, press Enter.\n"
        "  (The script will look for new CSV files in the data-axle folder.)"
    )
    after = set(os.listdir(DOWNLOAD_DIR))
    new_files = after - before
    csv_files = [f for f in new_files if f.lower().endswith(".csv")]
    if csv_files:
        for f in csv_files:
            path = os.path.join(DOWNLOAD_DIR, f)
            downloaded_files.append(path)
            print(f"  Found manually downloaded file: {f}")
    else:
        print("  WARNING: No new CSV files detected. You may need to re-export this batch.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Semi-automated Data Axle CSV exporter using Playwright"
    )
    parser.add_argument(
        "--metro", choices=["chicagoland", "boston", "all"], default="all",
        help="Which metro area to export (default: all)"
    )
    parser.add_argument(
        "--zips", type=str, default=None,
        help="Comma-separated ZIP codes (overrides --metro)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"ZIPs per search batch (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--resume", type=int, default=0,
        help="Resume from batch N (0-indexed, default: 0)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show batch plan without launching browser"
    )
    args = parser.parse_args()

    # Auto-resume from saved state
    if args.resume == 0:
        metro_label = args.metro if not args.zips else "custom"
        saved = load_progress(metro_label)
        if saved > 0:
            print(f"Found saved progress: batch {saved}. Resuming...")
            print("(Use --resume 0 explicitly to restart from scratch)")
            args.resume = saved

    run_scraper(args)


if __name__ == "__main__":
    main()
