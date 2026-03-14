# Dental PE Intelligence Platform — Claude Code Guide

## What This Project Is

A data pipeline + Streamlit dashboard that tracks private equity consolidation in US dentistry. It scrapes deal announcements, monitors 400k+ dental practices from federal data, classifies who owns what, and scores markets for acquisition risk. Primary metro: Chicagoland (268 expanded ZIPs across 7 sub-zones). Secondary: Boston Metro (21 ZIPs).

**Live app:** suleman7-pe.streamlit.app
**Repo:** github.com/suleman7-DMD/dental-pe-tracker

## Architecture

```
scrapers/            Python scrapers + importers + classifiers (the data pipeline)
dashboard/app.py     Streamlit dashboard (2,583 lines, single file, 6 pages)
scrapers/database.py SQLAlchemy models + helpers (SQLite)
data/                SQLite DB (145 MB) + raw data files (CSV, XLSX)
logs/                Pipeline event log (JSONL) + per-run log files
pipeline_check.py    Diagnostic health check tool (540 lines)
```

No build system. Push to `main` → Streamlit Cloud auto-deploys in ~60s.

## Database (SQLite via SQLAlchemy)

Key tables: `deals`, `practices`, `practice_changes`, `watched_zips`, `zip_scores`, `dso_locations`, `ada_hpi_benchmarks`

- **practices**: 400k+ rows. Fields: npi (PK), practice_name, doing_business_as, address, city, state, zip, phone, entity_type, taxonomy_code, ownership_status, affiliated_dso, affiliated_pe_sponsor, buyability_score, classification_confidence, classification_reasoning, data_source, latitude, longitude, parent_company, ein, franchise_name, iusa_number, website, year_established, employee_count, estimated_revenue, num_providers, location_type, import_batch_id, data_axle_import_date
- **deals**: 2,500+ rows. PE dental deals from PESP, GDN, PitchBook
- **practice_changes**: Change log for name/address/ownership changes (acquisition detection). 5,100+ rows.
- **zip_scores**: Per-ZIP consolidation stats (290 scored ZIPs), recalculated by merge_and_score.py. One row per ZIP (deduped).
- **watched_zips**: 290 ZIPs (268 Chicagoland + 21 Boston + 1 other). Auto-backfilled by ensure_chicagoland_watched().
- **dso_locations**: 408 scraped DSO office locations from ADSO websites.
- **ada_hpi_benchmarks**: 918 rows. State-level DSO affiliation rates by career stage (2022-2024).

### Current Data Stats
- 400,962 practices (362k independent, 2.8k DSO-affiliated, 401 PE-backed, 35k unknown)
- 2,512 deals
- 2,992 Data Axle enriched practices (with lat/lon, revenue, employees, year established)
- 290 scored ZIPs

## Dashboard Pages (6 total)

| Page | What It Shows |
|------|---------------|
| **Deal Flow** | Every PE dental deal — charts by year, state, deal type, recent activity feed |
| **Market Intel** | Watched ZIPs — consolidation map, ownership breakdown, ZIP-level detail, practice changes |
| **Buyability** | Individual practice scoring — filters by ZIP, verdict categories, confidence ratings |
| **Job Market** | Post-graduation job hunting — practice density pydeck map, market overview, searchable directory, opportunity signals, ownership landscape, market analytics |
| **Research** | Deep dives — PE sponsor profiles, platform profiles, state analysis, SQL explorer |
| **System** | Data freshness, pipeline logs, manual data entry forms |

### Job Market Page Structure
- Living location selector: West Loop/South Loop (142 ZIPs), Woodridge (129 ZIPs), Bolingbrook (127 ZIPs), All Chicagoland (268 ZIPs)
- 6 KPI cards computed from practice data (not zip_scores): Total Practices, Independent %, Consolidated %, Avg Buyability, 10+ Staff, Retirement Risk
- Pydeck dual-density hexagon map: green = independent clusters, red/orange = consolidated clusters, individual practice dots via toggle
- Market Overview: consolidation by ZIP bar chart, ownership donut, practice age histogram with retirement risk line, top DSOs bar chart
- Searchable Practice Directory with ownership/source filters, sort options, CSV download
- Opportunity Signals tabs: Retirement Risk, High Buyability scatter, Recent Changes
- Ownership Landscape: status bar chart, size distribution, top DSOs table, DSO penetration by ZIP
- Market Analytics: dentist density by ZIP, consolidation breakdown stacked bar, competitive landscape (DSO market share, PE sponsors active)

## Automated Pipeline

Cron runs every Sunday 8am (`scrapers/refresh.sh`):
1. Backup DB → 2. PESP scraper → 3. GDN scraper → 4. PitchBook importer → 5. ADSO scraper → 6. ADA HPI downloader → 7. DSO classifier → 8. Merge & score → 9. Compress DB + git push

Monthly NPPES refresh (first Sunday 6am): downloads federal provider data updates.

Every step logs structured events to `logs/pipeline_events.jsonl` via `scrapers/pipeline_logger.py`.

## Critical Rules

### Don't break the pipeline
- ALL scrapers import from `scrapers.pipeline_logger` — keep `log_scrape_start()` and `log_scrape_complete()` calls in every scraper's `run()` function
- ALL scrapers import from `scrapers.logger_config` — use `get_logger("scraper_name")`
- `database.py` auto-decompresses `.db.gz` on Streamlit Cloud — never remove that logic
- `refresh.sh` uses `run_step()` wrapper — errors in one step don't kill the pipeline

### Market Intel transparency
- Consolidation percentages MUST use total practices as denominator (conservative)
- Never use `classified_count` as denominator for headline KPIs — that inflates numbers
- Always show unknown count when >30% of practices are unclassified
- Labels must say "Known Consolidated" not just "Consolidated"

### Data integrity
- `insert_or_update_practice()` and `insert_deal()` handle dedup — use them, don't raw INSERT
- NPPES data uses NPI as unique key (10-digit number)
- PitchBook dedup uses fuzzy matching on company name + date
- Data Axle dedup uses address normalization + fuzzy name matching
- Data Axle importer has Pass 6: Corporate Linkage Detection (parent company fuzzy match, EIN clustering, IUSA parent linkage, franchise field)
- Never delete from `practices` table — only update ownership_status

### Streamlit Cloud constraints
- DB must be gzipped for git push (`data/dental_pe_tracker.db.gz`)
- App decompresses on first load via `_ensure_db_decompressed()`
- Keep `dashboard/app.py` imports inside functions where possible (cold start speed)

## File Quick Reference

| File | Lines | What It Does |
|------|-------|-------------|
| `dashboard/app.py` | 2,583 | Full Streamlit dashboard — 6 pages |
| `scrapers/database.py` | 542 | SQLAlchemy models, init_db(), helpers |
| `scrapers/nppes_downloader.py` | 681 | Downloads + imports federal dental provider data |
| `scrapers/data_axle_importer.py` | 2,650 | Imports Data Axle CSVs with 7-phase pipeline + Pass 6 corporate linkage |
| `scrapers/merge_and_score.py` | 719 | Dedup deals, score ZIPs, ensure_chicagoland_watched() |
| `scrapers/dso_classifier.py` | 547 | Name pattern matching + location matching to classify ownership |
| `scrapers/pesp_scraper.py` | 552 | Scrapes PE deal announcements |
| `scrapers/gdn_scraper.py` | 711 | Scrapes DSO deal roundups |
| `scrapers/adso_location_scraper.py` | 728 | Scrapes DSO office locations from websites |
| `scrapers/ada_hpi_downloader.py` | 237 | Auto-downloads ADA benchmark XLSX files |
| `scrapers/ada_hpi_importer.py` | 351 | Parses ADA HPI XLSX by state/career stage |
| `scrapers/pitchbook_importer.py` | 616 | CSV/XLSX import from PitchBook deal/company search |
| `scrapers/data_axle_exporter.py` | 805 | Interactive ZIP-batch export tool (7 Chicagoland zones + Boston) |
| `scrapers/pipeline_logger.py` | 295 | Structured JSON-Lines event logger |
| `pipeline_check.py` | 540 | Diagnostic health check tool |

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` when modifying the Streamlit app. Use `/data-axle-workflow` for Data Axle export/import tasks. Use `/debug-pipeline` when investigating scraper failures or data issues.
