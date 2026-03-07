# Dental PE Intelligence Platform — Claude Code Guide

## What This Project Is

A data pipeline + Streamlit dashboard that tracks private equity consolidation in US dentistry. It scrapes deal announcements, monitors 400k+ dental practices from federal data, classifies who owns what, and scores markets for acquisition risk. Two target metros: Chicagoland (35 ZIPs) and Boston (21 ZIPs).

**Live app:** suleman7-pe.streamlit.app
**Repo:** github.com/suleman7-DMD/dental-pe-tracker

## Architecture

```
scrapers/          Python scrapers + importers + classifiers (the data pipeline)
dashboard/app.py   Streamlit dashboard (1,277 lines, single file)
scrapers/database.py  SQLAlchemy models + helpers (SQLite)
data/              SQLite DB + raw data files (CSV, XLSX)
logs/              Pipeline event log (JSONL) + per-run log files
```

No build system. Push to `main` → Streamlit Cloud auto-deploys in ~60s.

## Database (SQLite via SQLAlchemy)

Key tables: `deals`, `practices`, `practice_changes`, `watched_zips`, `zip_scores`, `dso_locations`, `ada_hpi_benchmarks`

- **practices**: 400k+ rows. Fields: npi (PK), practice_name, doing_business_as, address, city, state, zip, phone, entity_type, taxonomy_code, ownership_status, affiliated_dso, affiliated_pe_sponsor, buyability_score, data_source
- **deals**: 2,500+ rows. PE dental deals from PESP, GDN, PitchBook
- **practice_changes**: Change log for name/address/ownership changes (acquisition detection)
- **zip_scores**: Per-ZIP consolidation stats, recalculated by merge_and_score.py

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
- Never delete from `practices` table — only update ownership_status

### Streamlit Cloud constraints
- DB must be gzipped for git push (`data/dental_pe_tracker.db.gz`)
- App decompresses on first load via `_ensure_db_decompressed()`
- Keep `dashboard/app.py` imports inside functions where possible (cold start speed)

## File Quick Reference

| File | Lines | What It Does |
|------|-------|-------------|
| `dashboard/app.py` | 1,277 | Full Streamlit dashboard — 5 pages: Deal Flow, Market Intel, Buyability, Research, System Health |
| `scrapers/database.py` | 495 | SQLAlchemy models, init_db(), helpers |
| `scrapers/nppes_downloader.py` | 681 | Downloads + imports federal dental provider data |
| `scrapers/data_axle_importer.py` | 2,153 | Imports Data Axle CSVs with 7-phase processing pipeline |
| `scrapers/merge_and_score.py` | 585 | Dedup deals, score ZIPs, export combined data |
| `scrapers/dso_classifier.py` | 431 | Name pattern matching + location matching to classify ownership |
| `scrapers/pesp_scraper.py` | ~200 | Scrapes PE deal announcements |
| `scrapers/gdn_scraper.py` | ~200 | Scrapes DSO deal roundups |
| `scrapers/adso_location_scraper.py` | ~300 | Scrapes DSO office locations from websites |
| `scrapers/ada_hpi_downloader.py` | ~230 | Auto-downloads ADA benchmark XLSX files |
| `scrapers/pipeline_logger.py` | ~300 | Structured JSON-Lines event logger |
| `scrapers/data_axle_exporter.py` | ~380 | Interactive ZIP-batch export tool |

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` when modifying the Streamlit app. Use `/data-axle-workflow` for Data Axle export/import tasks. Use `/debug-pipeline` when investigating scraper failures or data issues.
