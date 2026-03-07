"""
Data Axle Semi-Automated Export Tool

Automates the tedious parts of exporting dental practice data from Data Axle
Reference Solutions (via BU Library access). Handles:
  - 10-page batch download cycling (Data Axle's max selection limit)
  - Auto-navigation between pages
  - CAPTCHA detection + pause for manual solving
  - Auto-combining all batch CSVs into one file per metro
  - Progress tracking so you can resume if interrupted

YOU still handle:
  - BU SSO login (manual — credentials never stored)
  - Loading your saved search template
  - Setting ZIP codes for each metro
  - Solving CAPTCHAs when they appear

Usage:
    python3 scrapers/data_axle_automator.py                     # interactive mode
    python3 scrapers/data_axle_automator.py --metro chicagoland  # label output files
    python3 scrapers/data_axle_automator.py --combine-only       # just merge existing CSVs
    python3 scrapers/data_axle_automator.py --resume 11          # resume from page 11
"""

import argparse
import glob
import os
import re
import sys
import time
from datetime import datetime

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Config ────────────────────────────────────────────────────────────────────

DOWNLOAD_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle/batches")
COMBINED_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle")
RESULTS_PER_PAGE = 25
MAX_PAGES_PER_BATCH = 10  # Data Axle's hard limit on selectable pages

# ZIP codes for each metro (same as README)
METRO_ZIPS = {
    "chicagoland": "60491,60439,60441,60540,60564,60565,60563,60527,60515,60516,"
                   "60532,60559,60514,60521,60523,60148,60440,60490,60504,60502,"
                   "60431,60435,60586,60585,60503,60554,60543,60560",
    "boston": "02116,02115,02118,02119,02120,02215,02134,02135,02446,02445,"
             "02467,02459,02458,02453,02451,02138,02139,02140,02141,02142,02144",
}


def print_status(msg, style="info"):
    """Print colored status messages."""
    colors = {"info": "\033[36m", "ok": "\033[32m", "warn": "\033[33m",
              "err": "\033[31m", "bold": "\033[1m"}
    reset = "\033[0m"
    prefix = {"info": "[*]", "ok": "[+]", "warn": "[!]", "err": "[X]", "bold": "[>]"}
    print(f"{colors.get(style, '')}{prefix.get(style, '[*]')} {msg}{reset}")


def wait_for_captcha_clear(page, context="navigating"):
    """Check for CAPTCHA overlay and pause until user solves it."""
    captcha_selectors = [
        "iframe[src*='captcha']", "iframe[src*='recaptcha']",
        "#captcha", ".captcha", "[class*='captcha']",
        "iframe[src*='hcaptcha']", "#px-captcha",
        ".g-recaptcha", "[data-sitekey]",
    ]
    for sel in captcha_selectors:
        try:
            if page.query_selector(sel):
                print_status(f"CAPTCHA detected while {context}!", "warn")
                print_status("Solve the CAPTCHA in the browser, then press Enter here...", "bold")
                input("    >>> Press Enter after solving CAPTCHA... ")
                time.sleep(2)
                return True
        except Exception:
            pass

    # Also check for any modal/overlay that blocks the page
    try:
        body_text = page.inner_text("body", timeout=3000)
        if "verify you are human" in body_text.lower() or "security check" in body_text.lower():
            print_status(f"Security check detected while {context}!", "warn")
            print_status("Complete the verification in the browser, then press Enter here...", "bold")
            input("    >>> Press Enter after completing verification... ")
            time.sleep(2)
            return True
    except Exception:
        pass

    return False


def detect_total_results(page):
    """Try to read the total result count from the Data Axle results page."""
    selectors_to_try = [
        ".results-count", ".result-count", "#resultCount", "#totalResults",
        ".search-results-count", "[class*='result'] [class*='count']",
        ".paging-info", ".pagination-info",
    ]
    for sel in selectors_to_try:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text()
                numbers = re.findall(r'[\d,]+', text)
                if numbers:
                    return int(numbers[-1].replace(',', ''))
        except Exception:
            pass

    # Fallback: look for "of X" or "X results" in any visible text
    try:
        body = page.inner_text("body", timeout=3000)
        # "1-25 of 905" or "905 results" or "Results: 905"
        m = re.search(r'of\s+([\d,]+)', body)
        if m:
            return int(m.group(1).replace(',', ''))
        m = re.search(r'([\d,]+)\s+results?', body, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(',', ''))
    except Exception:
        pass

    return None


def detect_current_page(page):
    """Try to detect current page number from the pagination UI."""
    selectors = [
        ".pagination .active", ".paging .current", "input[name*='page']",
        ".page-current", "[class*='current-page']", ".paginator .selected",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text() if el.inner_text().strip() else el.get_attribute("value")
                if text and text.strip().isdigit():
                    return int(text.strip())
        except Exception:
            pass
    return None


def navigate_to_page(page, target_page):
    """Navigate to a specific page number in Data Axle results."""
    # Try direct page input first
    page_inputs = page.query_selector_all("input[type='text'][name*='page'], input[type='number'][name*='page']")
    for inp in page_inputs:
        try:
            inp.fill(str(target_page))
            inp.press("Enter")
            time.sleep(3)
            wait_for_captcha_clear(page, f"navigating to page {target_page}")
            return True
        except Exception:
            pass

    # Try clicking page number link
    try:
        page.click(f"a:text-is('{target_page}')", timeout=3000)
        time.sleep(3)
        wait_for_captcha_clear(page, f"navigating to page {target_page}")
        return True
    except Exception:
        pass

    # Try "Go to page" type inputs
    goto_inputs = page.query_selector_all("input[placeholder*='page'], input[title*='page']")
    for inp in goto_inputs:
        try:
            inp.fill(str(target_page))
            inp.press("Enter")
            time.sleep(3)
            wait_for_captcha_clear(page, f"navigating to page {target_page}")
            return True
        except Exception:
            pass

    return False


def click_next_page(page):
    """Click the 'Next' button to go to the next page."""
    next_selectors = [
        "a:text-is('Next')", "a:text-is('>')", "a:text-is('>>')",
        ".next a", ".pagination .next", "a[aria-label='Next']",
        "button:text-is('Next')", "[class*='next']",
        "a:text-is('next')", "a[title='Next']",
    ]
    for sel in next_selectors:
        try:
            page.click(sel, timeout=3000)
            time.sleep(2)
            wait_for_captcha_clear(page, "clicking Next")
            return True
        except Exception:
            pass
    return False


def select_all_on_page(page):
    """Click 'Select All' checkbox on the current page."""
    selectors = [
        "input[type='checkbox'][name*='selectAll']",
        "input[type='checkbox'][id*='selectAll']",
        "input[type='checkbox'][id*='SelectAll']",
        "#selectAll", "#select-all", ".select-all input",
        "th input[type='checkbox']",  # header checkbox
        "input[type='checkbox'][title*='Select All']",
        "input[type='checkbox'][aria-label*='Select All']",
        "label:text-is('Select All')",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                time.sleep(1)
                return True
        except Exception:
            pass
    return False


def click_download_csv(page):
    """Find and click the Download/Export CSV button."""
    # This is highly site-specific — try common patterns
    download_selectors = [
        "a:text-is('Download')", "button:text-is('Download')",
        "a:text-is('Export')", "button:text-is('Export')",
        "a:text-is('CSV')", "a[href*='download']", "a[href*='export']",
        "[class*='download']", "[class*='export']",
        "a:text-is('Download Selected')", "button:text-is('Download Selected')",
    ]
    for sel in download_selectors:
        try:
            page.click(sel, timeout=5000)
            time.sleep(2)
            return True
        except Exception:
            pass
    return False


def wait_for_download(download_dir, before_files, timeout=60):
    """Wait for a new file to appear in the download directory."""
    start = time.time()
    while time.time() - start < timeout:
        current = set(os.listdir(download_dir))
        new_files = current - before_files
        # Filter out partial downloads (.crdownload, .part, .tmp)
        complete = [f for f in new_files
                    if not f.endswith(('.crdownload', '.part', '.tmp', '.download'))]
        if complete:
            return complete[0]
        time.sleep(1)
    return None


def combine_csvs(metro_name, batch_dir=DOWNLOAD_DIR, output_dir=COMBINED_DIR):
    """Combine all batch CSVs into a single file for a metro area."""
    pattern = os.path.join(batch_dir, f"*{metro_name}*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        # Also try Detail*.csv pattern (Data Axle default naming)
        pattern = os.path.join(batch_dir, "Detail*.csv")
        files = sorted(glob.glob(pattern))

    if not files:
        print_status(f"No CSV files found for '{metro_name}' in {batch_dir}", "err")
        return None

    print_status(f"Combining {len(files)} CSV files for {metro_name}...", "info")
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, low_memory=False)
            dfs.append(df)
            print_status(f"  {os.path.basename(f)}: {len(df)} rows", "ok")
        except Exception as e:
            print_status(f"  {os.path.basename(f)}: ERROR - {e}", "err")

    if not dfs:
        return None

    combined = pd.concat(dfs, ignore_index=True)
    # Dedup on Company Name + Address + ZIP Code
    before = len(combined)
    dedup_cols = [c for c in ["Company Name", "Address", "ZIP Code"] if c in combined.columns]
    if dedup_cols:
        combined = combined.drop_duplicates(subset=dedup_cols, keep="first")
    after = len(combined)

    timestamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(output_dir, f"data_axle_{metro_name}_{timestamp}.csv")
    combined.to_csv(out_path, index=False)
    print_status(f"Combined: {after} unique rows (deduped {before - after}) -> {out_path}", "ok")
    return out_path


def run_automated_export(metro_name=None, resume_from_page=None):
    """Main automation loop."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    print_status("=" * 60, "bold")
    print_status("DATA AXLE SEMI-AUTOMATED EXPORT TOOL", "bold")
    print_status("=" * 60, "bold")
    print()

    if metro_name and metro_name in METRO_ZIPS:
        print_status(f"Metro: {metro_name.upper()}", "info")
        print_status(f"ZIP codes to paste: {METRO_ZIPS[metro_name]}", "info")
        print()

    print_status("STEP 1: Browser will open. You need to:", "bold")
    print("   1. Log into Data Axle via BU Library (SSO)")
    print("   2. Load your saved search template (SIC 8021 dental)")
    print("   3. Paste the ZIP codes for this metro")
    print("   4. Click 'View Results'")
    print("   5. Once you see results, come back here and press Enter")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            downloads_path=DOWNLOAD_DIR,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
        )
        # Set download path
        page = context.new_page()

        # Navigate to BU Library
        print_status("Opening BU Library...", "info")
        page.goto("https://www.bu.edu/library/")
        print()
        print_status("Complete steps 1-4 above in the browser window.", "bold")
        print_status("When you can see the results table, press Enter here.", "bold")
        input("    >>> Press Enter when results are visible... ")

        # Detect total results
        total = detect_total_results(page)
        if total:
            total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
            print_status(f"Detected: {total} results across {total_pages} pages", "ok")
        else:
            print_status("Could not auto-detect total results.", "warn")
            total_input = input("    Enter total number of results (e.g., 905): ").strip()
            total = int(total_input) if total_input.isdigit() else 0
            total_pages = (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
            print_status(f"OK: {total} results across {total_pages} pages", "info")

        if total_pages == 0:
            print_status("No results to export.", "err")
            browser.close()
            return

        # Calculate batches
        start_page = resume_from_page if resume_from_page else 1
        batches = []
        p_start = start_page
        while p_start <= total_pages:
            p_end = min(p_start + MAX_PAGES_PER_BATCH - 1, total_pages)
            batches.append((p_start, p_end))
            p_start = p_end + 1

        print()
        print_status(f"Export plan: {len(batches)} batches of up to {MAX_PAGES_PER_BATCH} pages each", "info")
        for i, (ps, pe) in enumerate(batches, 1):
            records = (pe - ps + 1) * RESULTS_PER_PAGE
            if pe == total_pages:
                records = total - (ps - 1) * RESULTS_PER_PAGE
            print(f"    Batch {i}: pages {ps}-{pe} (~{records} records)")
        print()

        batch_files = []
        for batch_idx, (batch_start, batch_end) in enumerate(batches, 1):
            print_status(f"{'='*50}", "bold")
            print_status(f"BATCH {batch_idx}/{len(batches)}: Pages {batch_start}-{batch_end}", "bold")
            print_status(f"{'='*50}", "bold")

            if batch_idx > 1:
                print()
                print_status("DATA AXLE BATCH RESET REQUIRED", "warn")
                print("   Data Axle requires you to restart the search between batches.")
                print("   In the browser:")
                print("   1. Go back to the search page (click 'New Search' or similar)")
                print("   2. Load your saved search template again")
                print("   3. Same ZIP codes should still be there (if not, re-paste them)")
                print("   4. Click 'View Results'")
                print(f"   5. Navigate to page {batch_start}")
                print()
                print_status(f"When you're on page {batch_start} of results, press Enter.", "bold")
                input(f"    >>> Press Enter when on page {batch_start}... ")

                # Verify we're on the right page
                wait_for_captcha_clear(page, "resuming batch")

            # Now select pages in this batch
            print_status(f"Selecting entries on pages {batch_start}-{batch_end}...", "info")

            current = batch_start
            pages_in_batch = 0

            while current <= batch_end:
                pages_in_batch += 1

                # Check for CAPTCHA (happens every ~5 pages)
                wait_for_captcha_clear(page, f"page {current}")

                # Try to select all on current page
                if select_all_on_page(page):
                    print_status(f"  Page {current}/{total_pages}: Selected all entries", "ok")
                else:
                    print_status(f"  Page {current}/{total_pages}: Could not auto-select.", "warn")
                    print(f"    Manually select all entries on this page, then press Enter.")
                    input("    >>> Press Enter after selecting... ")

                # Navigate to next page (unless this is the last in the batch)
                if current < batch_end:
                    time.sleep(1.5 + (pages_in_batch % 3) * 0.5)  # Vary timing slightly

                    if not click_next_page(page):
                        print_status(f"  Could not auto-click Next after page {current}.", "warn")
                        print(f"    Click 'Next' manually in the browser, then press Enter.")
                        input("    >>> Press Enter after clicking Next... ")

                    # Brief pause for page load
                    time.sleep(2)

                current += 1

            # All pages in batch selected — now download
            print()
            print_status(f"All {batch_end - batch_start + 1} pages selected. Starting download...", "info")

            before_files = set(os.listdir(DOWNLOAD_DIR))

            # Try auto-clicking download
            if not click_download_csv(page):
                print_status("Could not find Download button automatically.", "warn")
                print("   Click 'Download' or 'Export' in the browser.")
                print("   Choose CSV format and check all field boxes.")

            # Handle the export dialog (field selection, format, etc.)
            print()
            print_status("EXPORT DIALOG", "bold")
            print("   If an export dialog appeared:")
            print("   1. Select CSV format")
            print("   2. Check ALL field checkboxes")
            print("   3. Click Download/Export")
            print()
            print_status("Press Enter AFTER the file has finished downloading.", "bold")
            input("    >>> Press Enter when download is complete... ")

            # Check for the new file
            new_file = wait_for_download(DOWNLOAD_DIR, before_files, timeout=10)
            if new_file:
                # Rename with batch info
                metro_tag = metro_name or "export"
                new_name = f"data_axle_{metro_tag}_batch{batch_idx}_pg{batch_start}-{batch_end}.csv"
                src = os.path.join(DOWNLOAD_DIR, new_file)
                dst = os.path.join(DOWNLOAD_DIR, new_name)
                os.rename(src, dst)
                batch_files.append(dst)
                row_count = sum(1 for _ in open(dst)) - 1
                print_status(f"Downloaded: {new_name} ({row_count} rows)", "ok")
            else:
                # File might have gone to ~/Downloads instead
                print_status("File not detected in batch folder.", "warn")
                print(f"   Check ~/Downloads/ for the latest Detail*.csv file.")
                print(f"   If found, move it to: {DOWNLOAD_DIR}")
                dl_file = input("   Enter filename (or press Enter to skip): ").strip()
                if dl_file:
                    for search_dir in [os.path.expanduser("~/Downloads"), DOWNLOAD_DIR]:
                        candidate = os.path.join(search_dir, dl_file)
                        if os.path.exists(candidate):
                            metro_tag = metro_name or "export"
                            new_name = f"data_axle_{metro_tag}_batch{batch_idx}_pg{batch_start}-{batch_end}.csv"
                            dst = os.path.join(DOWNLOAD_DIR, new_name)
                            os.rename(candidate, dst)
                            batch_files.append(dst)
                            print_status(f"Moved and renamed: {new_name}", "ok")
                            break

            print()

        # Done with all batches
        print_status("=" * 60, "bold")
        print_status("ALL BATCHES COMPLETE", "ok")
        print_status("=" * 60, "bold")
        print()

        browser.close()

    # Combine all batch files
    if batch_files:
        metro_tag = metro_name or "combined"
        combined_path = combine_csvs(metro_tag, DOWNLOAD_DIR, COMBINED_DIR)
        if combined_path:
            print()
            print_status("NEXT STEPS:", "bold")
            print(f"   1. Verify the combined file: {combined_path}")
            print(f"   2. Run the importer:")
            print(f"      cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --auto")
            print(f"   3. Recalculate scores:")
            print(f"      python3 scrapers/merge_and_score.py")
    else:
        print_status("No batch files collected. Check ~/Downloads/ for any CSVs.", "warn")


def main():
    parser = argparse.ArgumentParser(description="Data Axle Semi-Automated Export Tool")
    parser.add_argument("--metro", choices=["chicagoland", "boston"],
                        help="Metro area label (prints ZIP codes to paste)")
    parser.add_argument("--resume", type=int, default=None,
                        help="Resume from this page number (e.g., --resume 11)")
    parser.add_argument("--combine-only", action="store_true",
                        help="Just combine existing batch CSVs without scraping")
    parser.add_argument("--list-zips", action="store_true",
                        help="Print ZIP codes for each metro and exit")
    args = parser.parse_args()

    if args.list_zips:
        for metro, zips in METRO_ZIPS.items():
            print(f"\n{metro.upper()}:")
            print(f"  {zips}")
        return

    if args.combine_only:
        metro = args.metro or "combined"
        combine_csvs(metro, DOWNLOAD_DIR, COMBINED_DIR)
        return

    run_automated_export(metro_name=args.metro, resume_from_page=args.resume)


if __name__ == "__main__":
    main()
