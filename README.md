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
6. [Monthly: ADSO Location Scraper](#monthly-adso-location-scraper)
7. [Quarterly: PitchBook Export](#quarterly-pitchbook-export)
8. [Quarterly: Data Axle Export](#quarterly-data-axle-export)
9. [Annually: ADA HPI Benchmark Update](#annually-ada-hpi-benchmark-update)
10. [Dashboard Page Guide](#dashboard-page-guide)
11. [Useful SQL Queries](#useful-sql-queries)
12. [Feature Add-Ons via Claude Code](#feature-add-ons-via-claude-code)
13. [Quarterly System Health Check](#quarterly-system-health-check)
14. [Emergency: If Something Breaks](#emergency-if-something-breaks)
15. [Annual Maintenance Calendar](#annual-maintenance-calendar)
16. [Quick Command Cheat Sheet](#quick-command-cheat-sheet)

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
| **ADA HPI** | State-level DSO affiliation rates by career stage | Annually | ~2 minutes | Manual — download one Excel file from ada.org once a year |
| **Data Axle** | Practice-level business data (revenue, employees, year established, ownership) | Quarterly | ~10 min (automated) / ~45 min (manual) | Semi-auto — Playwright script handles most clicks, you handle SSO login + CAPTCHAs |
| **ADSO Scraper** | DSO office locations scraped from their websites | Monthly | ~1 minute | Claude Code prompt — paste and run |
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

1. Scrapes **PESP** for new PE deal announcements
2. Scrapes **GDN** for new DSO deal roundups
3. Imports any **PitchBook** CSV/Excel files you dropped in the import folder
4. Runs the **DSO classifier** to tag new practices
5. Recalculates **consolidation scores** for all ZIP codes

**You don't need to do anything.** But if you want to verify it ran:

```bash
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

## Monthly: ADSO Location Scraper

**When to do this:** Same weekend as the NPPES refresh.

**What it does:** Visits DSO websites and scrapes their "Locations" pages to find all their office addresses. Then it matches those addresses against your practice database to see which practices in your watched markets are DSO-affiliated.

### Step-by-Step

**Step 1:** Open Claude Code and paste:

```
Run the ADSO location scraper at ~/dental-pe-tracker/scrapers/adso_location_scraper.py
to get fresh DSO office location data. Show me the summary and specifically
any new locations found in Illinois or Massachusetts since last scrape.
```

**Step 2:** (Optional) If you want to add a new DSO to track (maybe you heard about one at a conference), paste into Claude Code:

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

### The Problem: Data Axle is Tedious

Data Axle's export interface is deliberately painful:

- You **cannot select all results at once** if there are more than 10 pages (250 results)
- You can only select **10 pages maximum** per download batch
- After downloading, you have to **navigate back to the homepage** and re-run your search to get the next batch
- Every **5 page flips** triggers an annoying **CAPTCHA** you have to solve manually
- For 28 Chicagoland ZIPs alone, that's ~900 results across ~37 pages = **4 download cycles with 7+ CAPTCHAs**

Doing this manually for both Chicagoland and Boston Metro takes 45-60 minutes of tedious clicking.

### Option A: Automated Export (Recommended)

We built a Playwright script that handles most of the tedium. It splits your ZIPs into small batches (4 ZIPs per search = ~4 pages = fits in one download), so you never hit the 10-page limit. You only need to handle BU SSO login and the occasional CAPTCHA.

**Step 1: Install Playwright** (one-time setup)

```bash
pip install playwright && python -m playwright install chromium
```

**Step 2: Dry run** (see the batch plan without launching a browser)

```bash
cd ~/dental-pe-tracker && python3 scrapers/data_axle_scraper.py --dry-run
```

This shows you exactly how the ZIPs will be split and how many searches are needed.

**Step 3: Run the exporter**

```bash
python3 scrapers/data_axle_scraper.py
```

The script will:
1. Open a browser window and navigate to BU Library
2. **Pause for you** to log in via BU SSO and get to the Data Axle search page
3. Automatically fill in SIC code and ZIP codes for each batch
4. Click Search, Select All, Export, select CSV, check all field boxes
5. **Pause for you** if it hits a CAPTCHA
6. Download each CSV to `data/data-axle/` with batch numbering
7. Navigate back to search and repeat for the next batch
8. Save progress after each batch (resumable if interrupted)

**Useful flags:**

| Flag | What It Does |
|------|-------------|
| `--metro chicagoland` | Only export Chicagoland ZIPs |
| `--metro boston` | Only export Boston Metro ZIPs |
| `--batch-size 3` | Use 3 ZIPs per search instead of 4 (smaller batches = fewer pages) |
| `--resume 5` | Resume from batch 5 (if interrupted) |
| `--zips 60491,60439` | Export specific ZIPs only |

**Step 4: Import the downloaded CSVs**

```bash
python3 scrapers/data_axle_importer.py --preview   # Check column mapping first
python3 scrapers/data_axle_importer.py --auto       # Import for real
python3 scrapers/dso_classifier.py                  # Classify new practices
python3 scrapers/merge_and_score.py                 # Recalculate scores
```

### Option B: Manual Export (Fallback)

If the Playwright script breaks (Data Axle changes their UI, etc.), here's the manual process.

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
Fix whatever you find and re-run with --force-reclassify.
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

## Annually: ADA HPI Benchmark Update

**When to do this:** Check in June/July when the ADA publishes new data.

**What it does:** The ADA Health Policy Institute publishes state-level data on what percentage of dentists are DSO-affiliated, broken down by career stage. This gives you the official "how consolidated is this state" benchmarks to compare against your practice-level data.

### Step-by-Step

**Step 1:** Visit the ADA HPI data page:

```
ada.org/resources/research/health-policy-institute/dental-practice-research/practice-modalities-among-us-dentists
```

**Step 2:** Check if there's a new year's Excel file (e.g., "2025 Distribution of Dentists..."). If yes, download it.

**Step 3:** Move it to the import folder:

```bash
mv ~/Downloads/HPIData*.xlsx ~/dental-pe-tracker/data/ada-hpi/
```

**Step 4:** Run the importer:

```bash
cd ~/dental-pe-tracker && python3 scrapers/ada_hpi_importer.py
```

**Step 5:** Verify the update. Open Claude Code:

```
Show me the ADA HPI benchmark data for Illinois and Massachusetts for
all available years. How has DSO affiliation changed year over year?
What's the trend for early career dentists specifically?
```

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
# Start the dashboard locally
bash ~/dental-pe-tracker/start_dashboard.sh

# Manual full refresh (PESP + GDN + PitchBook + classify + score)
cd ~/dental-pe-tracker && bash scrapers/refresh.sh

# NPPES monthly update
cd ~/dental-pe-tracker && python3 scrapers/nppes_downloader.py

# Run DSO classifier
cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py

# Recalculate consolidation scores
cd ~/dental-pe-tracker && python3 scrapers/merge_and_score.py

# Import PitchBook files (after dropping in /data/pitchbook/raw/)
cd ~/dental-pe-tracker && python3 scrapers/pitchbook_importer.py --auto

# Import Data Axle files (after dropping in /data/data-axle/)
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --auto

# Import ADA HPI files (after dropping in /data/ada-hpi/)
cd ~/dental-pe-tracker && python3 scrapers/ada_hpi_importer.py

# Run ADSO location scraper
cd ~/dental-pe-tracker && python3 scrapers/adso_location_scraper.py

# Print Data Axle export instructions
cd ~/dental-pe-tracker && python3 scrapers/data_axle_importer.py --instructions

# Check recent logs
ls -lt ~/dental-pe-tracker/logs/ | head -5
cat ~/dental-pe-tracker/logs/$(ls -t ~/dental-pe-tracker/logs/ | head -1) | tail -30

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

# Re-compress DB and push to Streamlit Cloud
cd ~/dental-pe-tracker && python3 -c "
import gzip, shutil
with open('data/dental_pe_tracker.db','rb') as f:
    with gzip.open('data/dental_pe_tracker.db.gz','wb',6) as gz:
        shutil.copyfileobj(f, gz)
print('Compressed.')
"
git add data/dental_pe_tracker.db.gz && git commit -m "DB update $(date +%Y-%m-%d)" && git push
```

---

*Built by Sully | BU Goldman School of Dental Medicine '27*
