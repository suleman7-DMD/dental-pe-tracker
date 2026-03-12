# Dental PE Consolidation Intelligence Platform

A data-driven intelligence dashboard that tracks private equity activity in U.S. dentistry. It scrapes deal announcements, monitors practice ownership changes, scores markets for consolidation risk, and identifies acquisition targets — all in one place.

**Live Dashboard:** [suleman7-pe.streamlit.app](https://suleman7-pe.streamlit.app/)
**Repo:** [github.com/suleman7-DMD/dental-pe-tracker](https://github.com/suleman7-DMD/dental-pe-tracker)

---

## Table of Contents

1. [What This App Does](#what-this-app-does)
2. [Your Data Sources at a Glance](#your-data-sources-at-a-glance)
3. [How to Start the Dashboard](#how-to-start-the-dashboard)
4. [Weekly: Automated Refresh (Nothing To Do)](#weekly-automated-refresh-nothing-to-do)
5. [Monthly: NPPES Refresh](#monthly-nppes-refresh)
6. [ADSO Location Scraper (Automated)](#adso-location-scraper-automated)
7. [Quarterly: PitchBook Export](#quarterly-pitchbook-export)
8. [Quarterly: Data Axle Export](#quarterly-data-axle-export)
9. [ADA HPI Benchmark Update (Automated)](#ada-hpi-benchmark-update-automated)
10. [Pipeline Health Check](#pipeline-health-check)
11. [Dashboard Page Guide](#dashboard-page-guide)
12. [Useful SQL Queries](#useful-sql-queries)
13. [Feature Add-Ons via Claude Code](#feature-add-ons-via-claude-code)
14. [Quarterly System Health Check](#quarterly-system-health-check)
15. [Emergency: If Something Breaks](#emergency-if-something-breaks)
16. [Known Issues (Resolved)](#known-issues-resolved)
17. [Annual Maintenance Calendar](#annual-maintenance-calendar)
18. [Quick Command Cheat Sheet](#quick-command-cheat-sheet)

---

## What This App Does

This platform automatically collects data about dental practice acquisitions from multiple sources, then combines it all into an interactive dashboard. Think of it as a radar system for tracking which private equity firms are buying dental practices, where they're expanding, and which independent practices in your target neighborhoods might be next.

**The 5 dashboard pages:**

| Page | What It Shows |
|------|---------------|
| **Deal Flow** | Every PE dental deal we know about — charts by year, by state, by deal type, recent activity feed |
| **Market Intel** | Your watched ZIP codes — who owns what in Chicagoland and Boston Metro, consolidation percentages |
| **Buyability** | Scores individual practices on how "buyable" they are — filters by ZIP and category |
| **Research** | Deep dives — look up a specific PE sponsor, platform company, or state. Plus a SQL explorer for custom queries |
| **System** | Data freshness checks, completeness stats, and forms to manually add deals/practices |

---

## Your Data Sources at a Glance

The system pulls from 9 different data sources. Some run automatically, some need you to download a file once in a while.

| Source | What It Gives You | How Often | Your Effort | Runs Automatically? |
|--------|------------------|-----------|-------------|---------------------|
| **PESP** | PE deal announcements nationally | Weekly | None | Yes — runs via cron every Sunday |
| **GDN** | DSO deal roundups nationally | Weekly | None | Yes — runs via cron every Sunday |
| **NPPES** | Every dental practice in the US (name, address, NPI number, specialty) | Monthly | ~2 minutes | Semi-auto — cron tries first Sunday, manual backup if it fails |
| **PitchBook** | Deal sizes, EBITDA multiples, PE sponsor details, company profiles | Quarterly | ~5 minutes | Manual — you download from pitchbook.com and drop the file in a folder |
| **ADA HPI** | State-level DSO affiliation rates by career stage | Annually | None | Yes — auto-downloader checks weekly, grabs new files when ADA publishes them |
| **Data Axle** | Practice-level business data (revenue, employees, year established, ownership) | Quarterly | ~15 min (smart batch) / ~45 min (manual) | Semi-auto — smart batch exporter handles planning + file mgmt, you handle browser clicks + CAPTCHAs |
| **ADSO Scraper** | DSO office locations scraped from their websites | Weekly | None | Yes — runs via cron every Sunday |
| **DSO Classifier** | Tags each practice as independent, DSO-affiliated, or PE-backed | After any data load | None | Auto — runs as part of the pipeline |
| **Merge & Score** | Consolidation scores, opportunity scores, metro-level rollups | After any data load | None | Auto — runs as part of the pipeline |

**Why so many sources?** No single source has the full picture. PESP and GDN catch deal announcements but miss deal sizes. PitchBook has financials but misses smaller deals. NPPES has every practice but doesn't know who owns them. Data Axle has business details that help figure out ownership. Combining them all gives you the most complete view possible.

---

## How to Start the Dashboard

### Option A: Use the Live URL (Recommended)

Just visit [suleman7-pe.streamlit.app](https://suleman7-pe.streamlit.app/) in your browser. The dashboard is always running on Streamlit Cloud. No setup needed.

**Important:** The Cloud version uses a snapshot of the database from the last `git push`. To see the latest data after running scrapers locally, you need to re-compress and push the database (see [Quick Command Cheat Sheet](#quick-command-cheat-sheet)).

### Option B: Run Locally

Open Terminal and run:

```bash
bash ~/dental-pe-tracker/start_dashboard.sh
```

This starts the dashboard at [http://localhost:8051](http://localhost:8051). Use this when you want to see data immediately after running scrapers, without waiting for a push to GitHub.

---

## Weekly: Automated Refresh (Nothing To Do)

Your Mac has a cron job that runs every Sunday at 8:00 AM. It automatically:

1. **Backs up** the database
2. Scrapes **PESP** for new PE deal announcements
3. Scrapes **GDN** for new DSO deal roundups
4. Imports any **PitchBook** CSV/Excel files you dropped in the import folder
5. Scrapes **ADSO** DSO websites for office locations
6. Checks **ADA HPI** for new annual data files (auto-downloads when available)
7. Runs the **DSO classifier** to tag new practices
8. Recalculates **consolidation scores** for all ZIP codes
9. **Compresses DB + git pushes** to auto-deploy to Streamlit Cloud

Every step logs a structured event to `logs/pipeline_events.jsonl` with timestamp, duration, records processed, and a summary of what changed. View these on the **System Health** page under "Pipeline Activity Log".

**You don't need to do anything.** But if you want to verify it ran:

```bash
# Check the structured event log (recommended)
cd ~/dental-pe-tracker && python3 -c "
from scrapers.pipeline_logger import get_last_run_summary
for src, ev in sorted(get_last_run_summary().items()):
    ts = ev['timestamp'][:16]; s = ev.get('status','?')
    print(f\"{'✅' if s=='success' else '❌'} {src:25} {ts} {ev.get('summary','')[:60]}\")
"

# Or check the raw log file
cat ~/dental-pe-tracker/logs/refresh_$(date +%Y-%m-%d)*.log | tail -30
```

Look for `REFRESH COMPLETE` at the bottom. If you see it, everything worked.

### What if it didn't run or shows errors?

Open Claude Code and paste this prompt:

```
Read the most recent log file in ~/dental-pe-tracker/logs/
and tell me if there were any errors. If so, fix them and re-run
the refresh script at ~/dental-pe-tracker/scrapers/refresh.sh
```

---

## Monthly: NPPES Refresh

**When to do this:** First weekend of every month.

**What it does:** Downloads the latest update from CMS (the government agency that tracks healthcare providers). It finds new dental practices, detects name and address changes, and flags possible acquisitions. This is how you catch it when "Smith Family Dental" suddenly becomes "Heartland Dental LLC" in the federal records.

### Step-by-Step

**Step 1:** Check if the automatic cron job already handled it (it runs the first Sunday at 6 AM):

```bash
cat ~/dental-pe-tracker/logs/nppes_refresh_$(date +%Y-%m)*.log 2>/dev/null | tail -20
```

If you see `NPPES refresh complete` — you're done. Skip to Step 6.

**Step 2:** If it didn't run or had errors, run it manually:

```bash
cd ~/dental-pe-tracker && python3 scrapers/nppes_downloader.py
```

This downloads the monthly update file from CMS (it's a small incremental file, not the massive 10GB full database). Wait 2-5 minutes for it to finish.

**Step 3:** Run the DSO classifier on the new practices:

```bash
python3 scrapers/dso_classifier.py
```

This looks at each new practice and figures out if it's independent, part of a DSO, or PE-backed.

**Step 4:** Recalculate all the scores:

```bash
python3 scrapers/merge_and_score.py
```

This updates consolidation percentages, opportunity scores, and metro-level stats.

**Step 5:** (Optional) Push updated database to the cloud dashboard:

```bash
python3 -c "import gzip,shutil; open_ = open('data/dental_pe_tracker.db','rb'); gz = gzip.open('data/dental_pe_tracker.db.gz','wb',6); shutil.copyfileobj(open_,gz); gz.close(); open_.close()"
git add data/dental_pe_tracker.db.gz && git commit -m "Monthly NPPES refresh $(date +%Y-%m)" && git push
```

**Step 6:** Check for interesting changes. Open Claude Code and paste:

```
Connect to ~/dental-pe-tracker/data/dental_pe_tracker.db and show me
all practice_changes from the last 30 days where change_type = 'acquisition'
or where the field_changed = 'practice_name'. Sort by change_date desc.
Also show any changes in my watched ZIP codes (Chicagoland and Boston Metro).
```

---

## ADSO Location Scraper (Automated)

**Runs automatically** every Sunday as step [5/8] of the weekly refresh pipeline. No manual action needed.

**What it does:** Visits DSO websites and scrapes their "Locations" pages to find all their office addresses. Then it matches those addresses against your practice database to see which practices in your watched markets are DSO-affiliated. Currently scrapes 7 DSOs with static HTML pages; 13 more are flagged `needs_browser` (JS-rendered).

**To add a new DSO to track** (e.g., you hear about one at a conference), paste into Claude Code:

```
Add [DSO NAME] to the ADSO location scraper. Their website is [URL].
Check if their locations page is static HTML or needs JavaScript rendering.
If static, add a scraper for it. If JS, note it as needs_browser.
Run the scraper for just that DSO to test it.
```

---

## Quarterly: PitchBook Export

**When to do this:** First weekend of January, April, July, October — or whenever you remember. Quarterly is a guideline, not a hard deadline.

**What it does:** PitchBook is the gold standard for PE deal data. It gives you deal sizes, EBITDA multiples (how much they paid relative to earnings), PE sponsor details, and catches deals that PESP and GDN missed.

### Step-by-Step

**Step 1:** Open your browser. Go to [pitchbook.com](https://pitchbook.com). Log in with your BU credentials.

**Step 2: Export dental buyouts**

1. Click **Deals** in the top navigation bar
2. Click the **filter/funnel icon**
3. Set these filters **exactly**:
   - **Industry Vertical** — type "dental" — select "Dental" under Healthcare
   - **Deal Type** — select **"LBO/Buyout"**
   - **Deal Status** — select **"Completed"**
   - **Deal Date** — set start date to the **first day of last quarter**
     (Example: if it's April, set start date to January 1)
     Set end date to **today**
   - **Geography** — select **"United States"**
4. Click **Apply/Search**
5. Click the **Export/Download icon** (top-right of results table)
6. Select **"Excel"** or **"CSV"**
7. **Check all available columns** — the more data, the better
8. Download and save to your Downloads folder

**Step 3: Export dental add-ons** (bolt-on acquisitions to existing platforms)

Same as above, but change Deal Type to **"Add-on"**. Export.

**Step 4: Export dental recaps/growth** (refinancings and expansions)

Same filters, but Deal Type — select both **"Recap/Recapitalization"** AND **"Growth/Expansion"**. Export.

**Step 5: Export PE-backed dental companies** (do this once a year)

1. Click **Companies** in top nav
2. Filter: Industry Vertical → "Dental", Ownership → "PE-Backed" or "Sponsor-Backed", Geography → "United States"
3. Export

**Step 6: Move the downloaded files into the import folder**

```bash
mv ~/Downloads/*itchbook* ~/dental-pe-tracker/data/pitchbook/raw/ 2>/dev/null
mv ~/Downloads/*itchBook* ~/dental-pe-tracker/data/pitchbook/raw/ 2>/dev/null
mv ~/Downloads/*PITCHBOOK* ~/dental-pe-tracker/data/pitchbook/raw/ 2>/dev/null
ls ~/dental-pe-tracker/data/pitchbook/raw/
```

You should see your files listed.

**Step 7: Preview the import** (check that column mapping looks right before committing)

```bash
cd ~/dental-pe-tracker && python3 scrapers/pitchbook_importer.py --preview
```

Look at the column mapping output. If everything looks right, proceed.

**Step 8: Run the actual import**

```bash
python3 scrapers/pitchbook_importer.py --auto
```

**Step 9: Recalculate scores**

```bash
python3 scrapers/merge_and_score.py
```

**Step 10: Check what's new.** Open Claude Code and paste:

```
Connect to ~/dental-pe-tracker/data/dental_pe_tracker.db. Show me all
deals from PitchBook source that were just imported (created_at in last 24 hours).
How many had deal_size_mm populated? What's the average EBITDA multiple?
Were any of these deals in Illinois or Massachusetts?
```

### PitchBook Pro Tips

**Companies to follow in PitchBook** (they appear on your landing page feed):
- Heartland Dental, MB2 Dental Solutions, Pacific Dental Services, Dental365
- Specialized Dental Partners, Aspen Dental (TAG), U.S. Oral Surgery Management
- SALT Dental Collective, Sage Dental Management, Southern Orthodontic Partners

**PE firms to follow:**
- KKR (Heartland), Charlesbank Capital Partners (MB2), Quad-C Management (Specialized)
- The Jordan Company (Dental365), Oak Hill Capital (USOSM), Linden Capital Partners (Sage)
- Rock Mountain Capital (Chord)

---

## Quarterly: Data Axle Export

**When to do this:** Same weekend as PitchBook (January, April, July, October).

**What it does:** Data Axle is a business database you access through BU's library. It has ground-truth data on every dental practice in your target ZIP codes — revenue, employee count, year established, ownership type, contact info. This is what powers the buyability scoring (figuring out which practices are most likely to sell) and stealth DSO detection (catching practices that look independent but are actually DSO-owned).

**Why this data is critical:** Without Data Axle, the Market Intel and Buyability pages are running blind. NPPES tells you *where* practices are, but Data Axle tells you *how big they are*, *how old they are*, *who runs them*, and *how much revenue they generate*. That's the difference between "there's a dental office at 123 Main St" and "there's a 30-year-old solo practice with $600K revenue that's ripe for acquisition."

**Coverage:** The expanded 6-zone system covers **289 total ZIPs** (268 Chicagoland + 21 Boston Metro) within a 1-hour commute radius from West Loop, Woodridge, and Bolingbrook:

| Zone | Flag | ZIPs | Area |
|------|------|------|------|
| Original Chicagoland | `--metro chicagoland` | 28 | Naperville/DuPage/Will corridor |
| Chi North | `--metro chi-north` | 37 | Evanston, Skokie, Wilmette, Highland Park |
| Chi City | `--metro chi-city` | 56 | Chicago city proper (Loop, North/South/West Side) |
| Chi South | `--metro chi-south` | 53 | Orland Park, Tinley Park, Homewood, Lansing |
| Chi West | `--metro chi-west` | 49 | Oak Park, Berwyn, Cicero, Elmhurst |
| Chi Far West | `--metro chi-far-west` | 32 | Aurora, Elgin, Batavia, Geneva, St. Charles |
| Chi Far South | `--metro chi-far-south` | 14 | Joliet extended, Frankfort, Manhattan |
| **All Chicago** | **`--metro chi-all`** | **268** | **All 7 zones combined (deduped)** |
| Boston Metro | `--metro boston` | 21 | Boston, Brookline, Newton, Cambridge, Somerville |
| **Everything** | **`--metro all`** | **49** | **Original Chicagoland + Boston (legacy)** |

### The Problem: Data Axle is Tedious

Data Axle's export interface is deliberately painful:

- **250 records max per download** — you can't select more than ~10 pages at once
- After downloading, you must **go back to the homepage, re-run your search**, then navigate to where you left off
- Every **5 page flips** triggers a **CAPTCHA** you have to solve manually
- For all 28 Chicagoland ZIPs in one search: ~900 results, ~37 pages, **4 re-navigation cycles, 7+ CAPTCHAs, ~45 minutes**
- Doing both metros manually = **60-90 minutes of tedious repetitive clicking**

### The Solution: Smart ZIP Batching

Instead of dumping all ZIPs into one search and fighting the 250-record limit, we split ZIPs into small batches (4 per search). Each batch yields ~100-140 results — fits in **one download, no re-navigation, minimal CAPTCHAs**.

| | Manual (all ZIPs at once) | Smart Batching (4 ZIPs/search) |
|--|---|---|
| Chicagoland | 37 pages, 4 download cycles, ~7 CAPTCHAs, ~41 min | 7 searches, ~2 CAPTCHAs, ~14 min |
| Boston Metro | ~21 pages, 3 download cycles, ~4 CAPTCHAs, ~27 min | 6 searches, ~2 CAPTCHAs, ~12 min |

### Option A: Smart Batch Exporter (Recommended)

An interactive terminal script that manages all the bookkeeping — you handle the browser clicks, it handles the batch planning, clipboard, file naming, progress tracking, and CSV combination.

**Step 1: See the plan** (no browser needed)

```bash
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --plan --metro boston
```

**Step 2: Run the exporter**

```bash
python3 scrapers/data_axle_exporter.py --metro boston
```

The script will:
1. Show you the batch plan (6 batches of 4 ZIPs each for Boston)
2. **Copy ZIP codes to your clipboard** for each batch — just Cmd+V to paste
3. Tell you exactly what to click: paste ZIPs → View Results → Select All → Download → CSV → All Fields
4. Wait for you to confirm the download is done
5. **Auto-detect and rename** the downloaded CSV
6. **Save progress** after each batch (resume if interrupted)
7. After all batches: **auto-combine and deduplicate** all CSVs into one file

**Useful flags:**

| Flag | What It Does |
|------|-------------|
| `--metro boston` | Export Boston Metro ZIPs |
| `--metro chicagoland` | Export original 28 Chicagoland ZIPs |
| `--metro chi-all` | Export all 268 expanded Chicagoland ZIPs (all 7 zones) |
| `--metro chi-north` | North Shore + North suburbs (37 ZIPs) |
| `--metro chi-city` | Chicago city proper (56 ZIPs) |
| `--metro chi-south` | South suburbs (53 ZIPs) |
| `--metro chi-west` | Inner west suburbs (49 ZIPs) |
| `--metro chi-far-west` | Far west — Aurora, Elgin, etc. (32 ZIPs) |
| `--metro chi-far-south` | Far south Will County (14 ZIPs) |
| `--metro all` | Original Chicagoland + Boston (legacy, 49 ZIPs) |
| `--batch-size 3` | Fewer ZIPs per search = fewer results = safer if hitting 250 limit |
| `--resume 5` | Resume from batch 5 (if interrupted) |
| `--skip-done` | Skip ZIPs that already have data in existing CSVs |
| `--zips 33901,33907 --label fortmyers` | Custom ZIPs for scouting new markets |
| `--combine` | Just combine existing CSVs (no browser needed) |

**Step 3: Import the downloaded CSVs**

```bash
python3 scrapers/data_axle_importer.py --preview   # Check column mapping first
python3 scrapers/data_axle_importer.py --auto       # Import for real
python3 scrapers/dso_classifier.py                  # Classify new practices
python3 scrapers/merge_and_score.py                 # Recalculate scores
```

### Option B: Playwright Browser Automation (Faster but Fragile)

If the smart batch exporter feels too manual, there are two Playwright scripts that try to automate the browser clicks directly. These are **faster when they work** but break whenever Data Axle changes their UI.

```bash
# Install Playwright (one-time)
pip install playwright && python -m playwright install chromium

# Option B1: ZIP-batch approach (auto-fills SIC + ZIPs, clicks Search/Download)
python3 scrapers/data_axle_scraper.py --metro boston

# Option B2: All-at-once approach (you do the search, script handles pagination)
python3 scrapers/data_axle_automator.py --metro boston
```

Both still require you to handle BU SSO login and CAPTCHAs. Use these if Option A feels slow — but fall back to Option A if selectors break.

### Option C: WRDS Bulk Download (No CAPTCHAs, No Pagination)

BU has access to [WRDS (Wharton Research Data Services)](https://wrds-www.wharton.upenn.edu/), which hosts the same underlying InfoGroup/Data Axle business database in bulk-downloadable form. **No CAPTCHAs, no pagination, no 250-record limits.**

**When to use this:** If you need a massive initial load (thousands of records) or Data Axle's web interface is being particularly hostile.

**Step 1:** Go to [wrds-www.wharton.upenn.edu](https://wrds-www.wharton.upenn.edu/) and register with your BU email (takes up to 48 hours first time).

**Step 2:** Navigate to Subscribers → Data Axle (Infogroup) → Business Academic → Query Form.

**Step 3:** Filter by:
- SIC Code: `802100` (WRDS uses 6-digit SIC codes)
- State: IL, MA
- Date range: Most recent year available

**Step 4:** Select all available fields and submit. Download as CSV.

**Caveats:**
- WRDS data may lag 6-12 months behind the live Reference Solutions data
- Field names differ slightly (you may need to adjust the importer's column mapping)
- Registration takes up to 48 hours — plan ahead

**Step 5:** Import the same way:
```bash
mv ~/Downloads/wrds_*.csv ~/dental-pe-tracker/data/data-axle/
python3 scrapers/data_axle_importer.py --preview
python3 scrapers/data_axle_importer.py --auto
```

### Option D: Manual Export (Last Resort)

If all automation options fail, here's the fully manual process.

**Step 0:** Print the built-in instructions:

```bash
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --instructions
```

**Step 1:** Go to [bu.edu/library](https://bu.edu/library)
- If you're off campus, **connect to BU VPN first**
- Search for **"Data Axle Reference Solutions"** or **"ReferenceUSA"**
- Click through to access the database
- Select the **"U.S. Businesses"** database

**Step 2: Search for Chicagoland dental practices**

> **Note:** This covers only the original 28 ZIPs (Naperville/DuPage/Will corridor). For the full 268-ZIP expanded coverage, use the Smart Batch Exporter with `--metro chi-all`.

1. Under Keyword/SIC/NAICS, enter SIC code: **8021** (this is the code for dental offices)
2. Under Geography, select **ZIP Code**, then paste this entire line:

```
60491,60439,60441,60540,60564,60565,60563,60527,60515,60516,60532,60559,60514,60521,60523,60148,60440,60490,60504,60502,60431,60435,60586,60585,60503,60554,60543,60560
```

3. Click **View Results**
4. You'll get ~900 results across ~37 pages. Data Axle limits selection to 10 pages at a time, so:
   - Select pages 1-10, click Download/Export, choose CSV, check all fields, download
   - Go back to results, select pages 11-20, download again
   - Repeat for pages 21-30, then 31-37
   - **Expect a CAPTCHA every ~5 page flips** — just solve it and continue
5. **Check every field checkbox** on the first export (subsequent exports remember your selection):
   - Company Name + DBA Name
   - Full Address, City, State, ZIP
   - Phone Number
   - SIC Code + NAICS Code + Descriptions
   - Employee Size (both range AND actual number)
   - Annual Sales Volume / Sales Volume Range
   - Year Established
   - Ownership (Public/Private)
   - Number of Locations / Location Type
   - Contact First Name, Last Name, Title
   - Latitude, Longitude
6. Save files as `data_axle_chicagoland_2026_Q2_batch1.csv`, etc.

**Step 3: Search for Boston Metro dental practices**

Same process as above, but change the ZIP codes to:

```
02116,02115,02118,02119,02120,02215,02134,02135,02446,02445,02467,02459,02458,02453,02451,02138,02139,02140,02141,02142,02144
```

**Step 4: Move files to the import folder**

```bash
mv ~/Downloads/data_axle*.csv ~/dental-pe-tracker/data/data-axle/
ls ~/dental-pe-tracker/data/data-axle/
```

**Step 5: Preview, import, and score**

```bash
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --preview
python3 scrapers/data_axle_importer.py --auto
python3 scrapers/dso_classifier.py
python3 scrapers/merge_and_score.py
```

### How Buyability Scoring Works

Every Data Axle practice gets a **buyability score (0-100)** — "how likely is this practice to be acquirable by PE/DSO?" Higher = more buyable. Each score comes with a **confidence rating (1-5 stars)** based on how many real data fields we have.

**What Data Axle gives us that NPPES can't:**
- Revenue (PE sweet spot: $800K-$3M)
- Employee count (dental context: 5-15 = solid single-location practice)
- Year established (30+ years = owner likely retiring = #1 acquisition driver)
- Location type (single location vs. branch/subsidiary)
- Ownership type (private vs. public/government)

**Scoring weights (from heaviest to lightest):**

| Signal | Max Points | Logic |
|--------|-----------|-------|
| Retirement risk | +25 | Practice 35+ years old with solo owner = prime succession target |
| Revenue sweet spot | +15 | $800K-$1.5M revenue = profitable, small enough for PE |
| Practice size | +15 | 3-5 employees = ideal single-location practice |
| Solo practitioner | +15 | 1 provider = succession vulnerability |
| Retirement combo | +10 | Solo + 25yr+ practice = strongest signal in dentistry |
| Single location | +10 | Not already a chain |
| Independence | +10 | Confirmed independent (not unknown) |
| Name signal | +5 | Dentist name in practice (personal brand = solo) |
| **Disqualifiers** | **-30 to -50** | **Subsidiary, publicly traded, government, corporate name** |

**Confidence stars:**
- ***** (5 stars): Has year, employees, revenue, location type, providers — score is reliable
- *** (3 stars): Has some fields but missing key data — directional only
- * (1 star): Basically just NPPES name + entity type — treat with caution

**Why 87% of practices have no score:** Buyability scoring requires Data Axle data. NPPES only gives us name and address — not enough for a meaningful score. The more Data Axle exports you do, the more practices get scored.

### Reviewing the Import

After importing (via either method), check the debug report:

```bash
open ~/dental-pe-tracker/data/data-axle/debug-reports/
```

Double-click the most recent HTML file. Key sections to check:

- **Section 3 (Dedup Detail)** — Were practices correctly collapsed? (e.g., "Smith DDS" and "Smith Dental" at the same address should merge)
- **Section 5 (Stealth DSO Suspects)** — Practices that look independent but show signs of DSO ownership. Review these manually.
- **Section 6 (Buyability Ranking)** — Your top acquisition targets, ranked by score
- **Section 8 (Change Detection)** — If this isn't your first import, check for name changes (possible acquisitions)

If the debug report shows issues, open Claude Code:

```
Read the Data Axle debug report at
~/dental-pe-tracker/data/data-axle/debug-reports/[filename].html
and tell me about any issues. Specifically:
1. Any stealth DSO suspects that look like real DSOs I should add to the list
2. Any dedup clusters that look wrong (merged two different practices,
   or missed a merge)
3. Any practices scored as highly buyable that are actually DSO-affiliated
Fix whatever you find and re-run with --force.
```

### Expanding Your Search Area

When you want to scout a new market (say you're considering Fort Myers for externship research), open Claude Code:

```
Add these ZIP codes to the watched_zips table for a new metro area
called "Fort Myers":
33901 Fort Myers FL Fort Myers
33907 Fort Myers FL Fort Myers
[...more ZIPs...]

Then tell me the Data Axle ZIP code string I should paste into my
next Data Axle search to cover this new area.
```

---

## ADA HPI Benchmark Update (Automated)

**Runs automatically** every Sunday as step [6/8] of the weekly refresh pipeline. The `ada_hpi_downloader.py` checks whether the ADA has published new XLSX files for years not yet downloaded. When a new file appears, it downloads it and runs the importer automatically.

**Current data:** 2022, 2023, 2024 (2025 not yet published by ADA as of March 2026).

**What it does:** The ADA Health Policy Institute publishes state-level data on what percentage of dentists are DSO-affiliated, broken down by career stage. This gives you the official "how consolidated is this state" benchmarks to compare against your practice-level data.

**How the auto-download works:** The ADA publishes XLSX files at predictable URLs (`hpidata_dentist_practice_modalities_YYYY.xlsx`). The downloader checks content-type headers to distinguish real XLSX files from HTML error pages (the ADA returns HTTP 200 with HTML for missing years instead of a 404). When a real file is detected, it downloads it, runs the importer, and logs the event to the pipeline log.

**To verify what's available:**

```bash
cd ~/dental-pe-tracker && python3 scrapers/ada_hpi_downloader.py --dry-run
```

**To check current data:** Open Claude Code:

```
Show me the ADA HPI benchmark data for Illinois and Massachusetts for
all available years. How has DSO affiliation changed year over year?
What's the trend for early career dentists specifically?
```

---

## Pipeline Health Check

A single command to verify that all pipeline stages are healthy — data freshness, file existence, database integrity, and scraper status.

```bash
cd ~/dental-pe-tracker && python3 pipeline_check.py
```

This checks:
- Whether each data source has been refreshed recently
- Database table row counts and freshness
- Missing or stale CSV/export files
- Cron job status

To see suggested fix commands for any issues:

```bash
python3 pipeline_check.py --fix
```

The output shows a status line for each step:
- **CSV Download** — stale CSVs in ~/Downloads/ that weren't moved
- **CSV Import** — unprocessed CSVs in data/data-axle/
- **DB Import** — latest import timestamp vs latest CSV dates
- **Classification** — whether classifier has run after latest import
- **ZIP Scoring** — whether merge_and_score has run after latest import
- **DB Compression** — whether .db.gz is current (needed for deployment)
- **Git Push** — whether local commits have been pushed

---

## Dashboard Page Guide

Here are common tasks and which page to use:

| I want to... | Go to... | Then... |
|--------------|----------|---------|
| See how consolidated my target market is | **Market Intel** | Select "Chicagoland" or "Boston Metro" and read the consolidation percentage |
| Find buyable practices in Homer Glen | **Buyability** | Filter to ZIP 60491, sort by score descending |
| See what Specialized Dental Partners is doing | **Research** | PE Sponsor Profile → "Quad-C Management" or Platform Profile → "Specialized Dental Partners" |
| View all deals in Illinois this year | **Deal Flow** | Sidebar: State = IL, Date = 2026-01-01 to today |
| Check for acquisitions in my ZIPs | **Market Intel** | Scroll to "Recent Practice Changes" section, filter to your metro |
| Run a custom database query | **Research** | SQL Explorer tab — write your query or use a template |

---

## Useful SQL Queries

You can run these in the **Research** page's **SQL Explorer** tab, or in Claude Code by asking it to query the database.

### Practices in a specific ZIP with buyability scores

```sql
SELECT practice_name, address, city, ownership_status, affiliated_dso,
       buyability_score, year_established, employee_count
FROM practices
WHERE zip = '60491'
ORDER BY buyability_score DESC
```

### Recent acquisitions in your watched ZIPs

```sql
SELECT pc.change_date, pc.npi, p.practice_name, pc.field_changed,
       pc.old_value, pc.new_value, p.city, p.zip
FROM practice_changes pc
JOIN practices p ON pc.npi = p.npi
WHERE p.zip IN (SELECT zip_code FROM watched_zips)
  AND pc.change_type = 'acquisition'
ORDER BY pc.change_date DESC
LIMIT 20
```

### DSO market share by metro area

```sql
SELECT wz.metro_area, p.affiliated_dso, COUNT(*) as practice_count
FROM practices p
JOIN watched_zips wz ON p.zip = wz.zip_code
WHERE p.ownership_status IN ('dso_affiliated', 'pe_backed')
GROUP BY wz.metro_area, p.affiliated_dso
ORDER BY wz.metro_area, practice_count DESC
```

### Deals in your states by quarter

```sql
SELECT strftime('%Y-Q' || ((CAST(strftime('%m', deal_date) AS INT)-1)/3+1), deal_date) as quarter,
       target_state, COUNT(*) as deals,
       GROUP_CONCAT(DISTINCT platform_company) as platforms
FROM deals
WHERE target_state IN ('IL', 'MA')
GROUP BY quarter, target_state
ORDER BY quarter DESC
```

### Practices that changed names recently (acquisition signals)

```sql
SELECT pc.change_date, p.practice_name, pc.old_value as old_name,
       pc.new_value as new_name, p.address, p.city, p.state, p.zip
FROM practice_changes pc
JOIN practices p ON pc.npi = p.npi
WHERE pc.field_changed = 'practice_name'
  AND pc.change_date > date('now', '-90 days')
ORDER BY pc.change_date DESC
```

---

## Feature Add-Ons via Claude Code

These are copy-paste prompts you can drop into Claude Code to extend the system. No coding knowledge needed — just paste and let Claude do the work.

### Add a new metro area to track

```
I want to start tracking dental practices in [CITY/AREA NAME].
Find the main ZIP codes for this area (residential suburbs where
dental practices would be, not just downtown). Add them to the
watched_zips table with metro_area = "[AREA NAME]". Then run the
DSO classifier and merge_and_score.py for just those ZIPs. Show me
the consolidation summary for the new area.
```

### Add a new DSO to the classifier

```
I learned about a new DSO called [DSO NAME]. They are backed by
[PE SPONSOR or "unknown"]. Add them to the known DSO list in
dso_classifier.py and to the PE sponsor mapping. Then re-run the
classifier with --force flag to reclassify all practices. Show me
how many practices were reclassified.
```

### Deep dive on a specific practice

```
Tell me everything we know about the dental practice at [ADDRESS]
in [CITY, STATE ZIP]. Check the practices table, practice_changes,
deals table (any deals mentioning this practice or its DSO), and
dso_locations. If we have Data Axle data, show revenue, employees,
year established, and buyability score. Give me your assessment of
whether this practice is a realistic acquisition target.
```

### Export a market report

```
Generate a comprehensive market report for [Chicagoland/Boston Metro/etc]
as a PDF or HTML file. Include:
1. Market overview (total practices, consolidation rate, trend)
2. Top DSOs by practice count in this market
3. Recent deal activity in the state
4. ZIP-level consolidation heat map data
5. Top 20 buyable practices with scores
6. Comparison to ADA HPI state benchmarks
7. Quarter-over-quarter changes
Save it to ~/dental-pe-tracker/reports/[area]_market_report_[date].html
```

### Monitor a specific DSO's expansion

```
Show me everything about [DSO NAME]'s activity:
1. All deals involving them from the deals table
2. All practices affiliated with them from practices table
3. All locations from dso_locations table
4. Their geographic footprint (which states/ZIPs)
5. Their deal velocity (deals per quarter over time)
6. Which PE sponsor backs them and when they invested
Present this as a company profile brief.
```

### Compare two markets

```
Give me a side-by-side comparison of [MARKET A] vs [MARKET B]:
- Total practices
- Consolidation % (with confidence level)
- PE penetration %
- Top 3 DSOs in each market
- Average buyability score of independent practices
- Number of practices established before 2000 (retirement wave candidates)
- Recent acquisition activity (last 6 months)
- ADA HPI benchmark for each state
Which market has more opportunity for independent practice ownership?
```

### Add Google Maps to the dashboard

```
Add a new section to the Market Intel page of the dashboard that
shows an interactive map using plotly mapbox. Plot every practice in the
selected metro area as a dot, color-coded by ownership status:
- Green = independent
- Yellow = dso_affiliated
- Red = pe_backed
- Gray = unknown
Size the dots by buyability_score if available (bigger = more buyable).
On hover, show practice name, address, classification, and score.
Use the latitude/longitude from the practices table if available,
otherwise geocode from address.
```

### Add email alerts for acquisitions

```
Build a script at ~/dental-pe-tracker/scrapers/alert_checker.py that:
1. Runs after every refresh
2. Checks practice_changes for any changes in watched ZIPs in the last 7 days
3. Checks for new deals in IL or MA in the last 7 days
4. If anything found, compose a summary and send it to my email
   using the Gmail MCP connection
5. Subject: "Dental PE Tracker Alert — [X] changes detected"
Add this to the refresh.sh pipeline as step 7.
```

---

## Quarterly System Health Check

Every quarter, spend 15 minutes making sure everything is running clean.

**Step 1: Verify cron jobs are active**

```bash
crontab -l
```

You should see two lines — one for the weekly refresh (Sunday 8 AM) and one for monthly NPPES (first Sunday 6 AM).

**Step 2: Check recent logs for errors.** Open Claude Code:

```
Read all log files in ~/dental-pe-tracker/logs/ from the last 30 days.
Summarize: how many successful refreshes, any errors or warnings that
need attention, any scrapers that have been consistently failing.
```

**Step 3: Check data freshness**

Open the dashboard and go to the **System** page. Verify all sources show green status indicators.

**Step 4: Check backups**

```bash
ls -la ~/dental-pe-tracker/backups/ | tail -5
```

You should see recent `.db` backup files.

**Step 5: Check database size**

```bash
du -sh ~/dental-pe-tracker/data/dental_pe_tracker.db
```

Should be under 500MB. If it's growing fast, the `practice_changes` table might need pruning.

**Step 6: Run a manual full refresh to test everything end-to-end**

```bash
cd ~/dental-pe-tracker && bash scrapers/refresh.sh
```

---

## Emergency: If Something Breaks

### "The dashboard won't start"

```bash
cd ~/dental-pe-tracker && streamlit run dashboard/app.py 2>&1 | head -30
```

Copy the error output. Open Claude Code and paste: `Fix this dashboard error: [paste error here]`

### "A scraper stopped working"

Websites change their HTML structure periodically. Open Claude Code:

```
The [PESP/GDN/ADSO] scraper at ~/dental-pe-tracker/scrapers/[name].py
is failing. Read the most recent log, visit the website to see if the
HTML structure changed, and update the scraper to match the new format.
Run it with --dry-run to verify the fix.
```

### "I want to start completely fresh"

This wipes the database and rebuilds from scratch. Only do this if something is seriously broken:

```bash
cd ~/dental-pe-tracker
cp data/dental_pe_tracker.db backups/pre_reset_$(date +%Y%m%d).db
rm data/dental_pe_tracker.db
python3 -c "from scrapers.database import init_db; init_db()"
```

Then re-run: NPPES downloader, DSO classifier, and refresh.sh to repopulate.

### "The database is corrupted"

Restore from the most recent backup:

```bash
cp ~/dental-pe-tracker/backups/$(ls -t ~/dental-pe-tracker/backups/ | head -1) \
   ~/dental-pe-tracker/data/dental_pe_tracker.db
```

---

## Known Issues (Resolved)

### Duplicate zip_scores rows inflating practice counts

**Symptom:** The Market Intel page showed ~3,500 total practices in Chicagoland when the actual count was ~1,894. Consolidation percentages looked plausible but were computed over inflated denominators.

**Root cause:** `merge_and_score.py` was inserting a new `zip_scores` row keyed on `(zip_code, score_date)`. Running the script on different dates created duplicate rows for the same ZIP code — one per date it was run. Dashboard queries that summed across `zip_scores` would double- or triple-count practices.

**Fix:** Changed the upsert logic to filter by `zip_code` only (not `zip_code + score_date`). When an existing row is found, it updates all fields in place and sets `score_date` to today. New rows are only inserted for ZIPs that have never been scored before. This ensures exactly one row per ZIP code at all times.

**Verification:** After running `python3 scrapers/merge_and_score.py`, check:
```sql
SELECT COUNT(*), COUNT(DISTINCT zip_code) FROM zip_scores;
-- These two numbers should be equal
```

---

## Annual Maintenance Calendar

| Month | What To Do |
|-------|-----------|
| **January** | Quarterly PitchBook + Data Axle exports. Check ADA HPI for new data. |
| **February** | Let auto-refresh run. Review dashboard for Q4 trends. |
| **March** | Monthly NPPES check. Review practice changes in watched ZIPs. |
| **April** | Quarterly PitchBook + Data Axle exports. Major scoring refresh. |
| **May** | Monthly NPPES. Start tracking new markets for externship/job search. |
| **June** | Check ADA HPI for new annual data release. Monthly NPPES. |
| **July** | Quarterly PitchBook + Data Axle. Mid-year market assessment. |
| **August** | Monthly NPPES. Review year-to-date deal trends. |
| **September** | Monthly NPPES. Prep for fall job/residency search season. |
| **October** | Quarterly PitchBook + Data Axle. Generate market reports for target areas. |
| **November** | Monthly NPPES. Review Q3 activity. Conference season intel. |
| **December** | Monthly NPPES. Year-end review. Export annual summary report. |

---

## Quick Command Cheat Sheet

Copy-paste any of these into Terminal.

```bash
# ── Dashboard ──────────────────────────────────────────────
# Start the dashboard locally
bash ~/dental-pe-tracker/start_dashboard.sh

# ── Full Pipeline ──────────────────────────────────────────
# Manual full refresh (PESP + GDN + PitchBook + classify + score)
cd ~/dental-pe-tracker && bash scrapers/refresh.sh

# ── Health Check ───────────────────────────────────────────
# Check pipeline status (all data sources, freshness, integrity)
cd ~/dental-pe-tracker && python3 pipeline_check.py

# Show fix commands for any issues
cd ~/dental-pe-tracker && python3 pipeline_check.py --fix

# ── NPPES ──────────────────────────────────────────────────
# NPPES monthly update
cd ~/dental-pe-tracker && python3 scrapers/nppes_downloader.py

# ── Classification & Scoring ──────────────────────────────
# Run DSO classifier
cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py

# Run DSO classifier (force reclassify all, including already-classified)
cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py --force

# Recalculate consolidation scores
cd ~/dental-pe-tracker && python3 scrapers/merge_and_score.py

# ── PitchBook ─────────────────────────────────────────────
# Import PitchBook files (after dropping in /data/pitchbook/raw/)
cd ~/dental-pe-tracker && python3 scrapers/pitchbook_importer.py --preview
cd ~/dental-pe-tracker && python3 scrapers/pitchbook_importer.py --auto

# ── Data Axle Export (6-zone system, 289 total ZIPs) ──────
# See batch plan for all expanded Chicago zones (268 ZIPs)
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --plan --metro chi-all

# See batch plan for a single zone
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --plan --metro chi-north

# Export a specific zone interactively
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --metro chi-north

# Export Boston Metro (21 ZIPs)
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --metro boston

# Export original 28 Chicagoland ZIPs
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --metro chicagoland

# Skip ZIPs that already have data in existing CSVs
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --metro chi-all --skip-done

# Combine existing CSVs (no browser needed)
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --combine

# Custom ZIPs (e.g., scouting Fort Myers)
cd ~/dental-pe-tracker && python3 scrapers/data_axle_exporter.py --zips 33901,33907,33908 --label fortmyers

# ── Data Axle Import + Score (after exporting) ────────────
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --preview
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --auto
cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py
cd ~/dental-pe-tracker && python3 scrapers/merge_and_score.py

# Print Data Axle manual export instructions
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --instructions

# ── Other Importers ───────────────────────────────────────
# Import ADA HPI files (after dropping in /data/ada-hpi/)
cd ~/dental-pe-tracker && python3 scrapers/ada_hpi_importer.py

# Run ADSO location scraper
cd ~/dental-pe-tracker && python3 scrapers/adso_location_scraper.py

# ── Logs & Monitoring ─────────────────────────────────────
# View pipeline activity log (structured events from all scrapers)
cd ~/dental-pe-tracker && python3 -c "
from scrapers.pipeline_logger import get_recent_events
for e in get_recent_events(limit=15):
    ts=e['timestamp'][:19]; s=e.get('source','?'); st=e.get('status','')
    print(f\"{'✅' if st=='success' else '❌' if st=='error' else '🔵'} {ts}  {s:25}  {e.get('summary','')[:60]}\")
"

# Check recent logs
ls -lt ~/dental-pe-tracker/logs/ | head -5
cat ~/dental-pe-tracker/logs/$(ls -t ~/dental-pe-tracker/logs/ | head -1) | tail -30

# ── Database ──────────────────────────────────────────────
# Database backup
cd ~/dental-pe-tracker && python3 -c "from scrapers.database import backup_database; backup_database()"

# Check database size and record counts
du -sh ~/dental-pe-tracker/data/dental_pe_tracker.db
cd ~/dental-pe-tracker && python3 -c "
from scrapers.database import get_session, Deal, Practice
s = get_session()
print(f'Deals: {s.query(Deal).count():,}')
print(f'Practices: {s.query(Practice).count():,}')
s.close()
"

# ── Deploy to Streamlit Cloud ─────────────────────────────
# Re-compress DB and push
cd ~/dental-pe-tracker && gzip -kf data/dental_pe_tracker.db
git add data/dental_pe_tracker.db.gz && git commit -m "DB update $(date +%Y-%m-%d)" && git push
```

---

*Built by Sully | BU Goldman School of Dental Medicine '27*
