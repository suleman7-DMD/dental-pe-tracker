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

## Dashboard Pages (8 total, Next.js primary)

| Page | What It Shows |
|------|---------------|
| **Home** | KPI cards, nav cards, recent deals, data freshness |
| **Deal Flow** | Every PE dental deal — charts by year, state, deal type, recent activity feed |
| **Market Intel** | Watched ZIPs — consolidation map, ownership breakdown, ZIP-level detail, practice changes |
| **Buyability** | Individual practice scoring — filters by ZIP, verdict categories, confidence ratings |
| **Job Market** | Post-graduation job hunting — practice density map, market overview, searchable directory, opportunity signals, ownership landscape, market analytics |
| **Research** | Deep dives — PE sponsor profiles, platform profiles, state analysis, SQL explorer |
| **Intelligence** | AI qualitative research — ZIP market intel (10-signal reports), practice dossiers (readiness, confidence, flags), expandable detail panels |
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

## Entity Classification System

The `entity_classification` field on practices provides granular practice-type labels beyond `ownership_status`. Classifications are assigned by the DSO classifier's Pass 3 (`classify_entity_types()` in `dso_classifier.py`), using provider count at address, last name matching, taxonomy codes, corporate signals, and Data Axle enrichment data.

### All 11 Entity Classification Values
| Value | Definition |
|-------|-----------|
| `solo_established` | Single-provider practice, operating 20+ years or default for single providers with limited data |
| `solo_new` | Single-provider practice, established within last 10 years |
| `solo_inactive` | Single-provider practice, missing phone and website — likely retired or minimal activity |
| `solo_high_volume` | Single-provider with 5+ employees or $800k+ revenue — likely needs associate help |
| `family_practice` | 2+ providers at same address share a last name — internal succession likely |
| `small_group` | 2-3 providers at same address, different last names, not matching known DSO |
| `large_group` | 4+ providers at same address, not matching known DSO brand |
| `dso_regional` | Appears independent but shows corporate signals (parent company, shared EIN, franchise field, branch location type, generic brand + high provider count) |
| `dso_national` | Known national/regional DSO brand (Aspen, Heartland, etc.) matched with high confidence |
| `specialist` | Specialist practice (Ortho, Endo, Perio, OMS, Pedo) — identified by taxonomy code or practice name keywords |
| `non_clinical` | Dental lab, supply company, billing entity, staffing service |

Each classification stores its reasoning in `classification_reasoning` for auditability. First matching rule wins (priority: non_clinical > specialist > dso_national > corporate signals > family_practice > large_group > small_group > solo variants).

### Saturation Metrics (in zip_scores)
Computed by `merge_and_score.py`'s `compute_saturation_metrics()`:

- **DLD (Dentist Location Density):** `dld_gp_per_10k` = GP dental offices per 10,000 residents. National avg ~6.1. Lower = less competition.
- **Buyable Practice Ratio:** `buyable_practice_ratio` = % of GP offices classified as solo_established, solo_inactive, or solo_high_volume. Higher = more acquisition targets.
- **Corporate Share:** `corporate_share_pct` = % of GP offices classified as dso_regional or dso_national. Higher = more consolidated market.
- **Market Type:** `market_type` = computed classification based on combined metrics. Set to NULL when `metrics_confidence` is 'low' (data insufficient for reliable labeling).
- **People per GP Door:** `people_per_gp_door` = population / GP locations. Higher = fewer options per resident.

### Specialist Separation Methodology
A practice is classified as `specialist` if ANY of these conditions are met:
1. **Taxonomy code match** — NPPES taxonomy starts with specialist prefix (1223D, 1223E, 1223P, 1223S, 1223X). Excludes 1223G (General) and 122300 (General Dentist).
2. **Practice name keyword** — Name contains: ORTHODONT, PERIODON, ENDODONT, ORAL SURG, MAXILLOFACIAL, PEDIATRIC DENT, PEDODONT, PROSTHODONT, IMPLANT CENT.
3. A location (unique address) counts as GP if it has at least one non-specialist, non-clinical practice. Specialist-only locations are counted separately in `total_specialist_locations`.

### Confidence System
- **`metrics_confidence`** on zip_scores: 'high' (classification coverage >80% AND unknown ownership <20%), 'medium' (coverage >50% AND unknown <40%), 'low' (anything else).
- **`market_type_confidence`**: 'confirmed' (metrics_confidence is high), 'provisional' (medium), 'insufficient_data' (low — market_type set to NULL).
- **`classification_confidence`** on practices: 0-100 score from DSO name/pattern matching. Higher = more certain the ownership classification is correct.

### Market Type Values
Priority order (first match wins): `low_resident_commercial`, `high_saturation_corporate`, `corporate_dominant`, `family_concentrated`, `low_density_high_income`, `low_density_independent`, `growing_undersupplied`, `balanced_mixed`, `mixed` (default).

### Buyability Score Modifiers (Phase 5)
In addition to the base scoring in `compute_buyability()` (data_axle_importer.py), two ADDITIVE penalties are applied after entity classification:
- **Family practice penalty (-20):** `entity_classification == 'family_practice'` — shared last name at address suggests internal succession.
- **Multi-ZIP presence penalty (-15):** Same practice name or EIN appears in 3+ watched ZIPs — likely a chain entity.

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` when modifying the Streamlit app. Use `/data-axle-workflow` for Data Axle export/import tasks. Use `/debug-pipeline` when investigating scraper failures or data issues.
