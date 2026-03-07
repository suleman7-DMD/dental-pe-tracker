---
name: scraper-dev
description: Develop, fix, or add scrapers and importers for the dental PE data pipeline. Use when modifying any file in scrapers/, adding new data sources, fixing scraper failures, or updating classification logic. Trigger phrases include "scraper", "importer", "classifier", "PESP", "GDN", "NPPES", "ADSO", "ADA HPI", "PitchBook", "Data Axle", "pipeline", "refresh", "cron", "taxonomy", "NPI", "DSO list", "known DSOs", "classification".
---

# Scraper Development Guide

## Pipeline Architecture

Every scraper follows the same pattern:

```python
sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("scraper_name")

def run(...):
    _t0 = log_scrape_start("scraper_name")
    # ... do work ...
    log_scrape_complete("scraper_name", _t0, new_records=N,
                        summary="Human-readable summary of what changed",
                        extra={"key": "value"})
```

## Scraper Registry

| Scraper | Source URL/Method | Schedule | Key Function |
|---------|-------------------|----------|-------------|
| `pesp_scraper.py` | HTTP scrape of PESP website | Weekly (cron) | `run()` |
| `gdn_scraper.py` | HTTP scrape of GDN website | Weekly (cron) | `run()` |
| `nppes_downloader.py` | CMS NPPES download page | Monthly (cron) | `run(watched_only, dry_run)` |
| `adso_location_scraper.py` | Individual DSO websites | Weekly (cron) | `run()` |
| `ada_hpi_downloader.py` | ADA predictable URL pattern | Weekly (cron) | `run(dry_run)` |
| `pitchbook_importer.py` | Manual CSV/XLSX drop | On demand | `run(auto, preview)` |
| `data_axle_importer.py` | Manual CSV drop | On demand | `run(preview, auto, ...)` |
| `dso_classifier.py` | Runs on DB data | After imports | `run(dry_run, force, zip_filter)` |
| `merge_and_score.py` | Runs on DB data | After imports | `run()` |

## Database Models (scrapers/database.py)

Key models and their primary keys:
- `Deal` — id (auto), deal_date, platform_company, pe_sponsor, target_state, deal_type, source
- `Practice` — npi (string, 10 digits), practice_name, ownership_status, affiliated_dso, data_source
- `PracticeChange` — id (auto), npi (FK), change_date, field_changed, old_value, new_value, change_type
- `WatchedZip` — zip_code (PK), city, state, metro_area
- `ZipScore` — id (auto), zip_code, score_date, consolidation_pct, opportunity_score
- `DSOLocation` — id (auto), dso_name, address, city, state, zip
- `ADAHPIBenchmark` — id (auto), data_year, state, career_stage, pct_dso_affiliated

Helper functions: `insert_or_update_practice()`, `insert_deal()`, `log_practice_change()`, `init_db()`, `get_session()`, `get_engine()`, `backup_database()`

## DSO Classifier Logic

Two passes:
1. **Name pattern matching** (`classify_practice(name, dba)`): checks against `KNOWN_DSOS` dict (DSO name → PE sponsor), `MGMT_KEYWORDS` list, and corporate structure patterns
2. **Location matching**: fuzzy-matches practice addresses against `dso_locations` table (score >= 85)

Ownership statuses: `pe_backed`, `dso_affiliated`, `independent`, `likely_independent`, `unknown`

To add a new DSO: add to `KNOWN_DSOS` dict in `dso_classifier.py` with `{"name_patterns": [...], "pe_sponsor": "..."}`. Then run with `--force` to reclassify.

## Common Patterns

### Adding a new scraper
1. Create `scrapers/new_scraper.py` following the pattern above
2. Add `run_step` line to `scrapers/refresh.sh`
3. Update step numbering in refresh.sh (e.g., [2/9] instead of [2/8])
4. Test: `python3 scrapers/new_scraper.py --dry-run`
5. Update CLAUDE.md file reference table

### Modifying database schema
1. Add column to model in `database.py`
2. Add migration in `init_db()` using `ALTER TABLE` with `try/except` for idempotency
3. Test: `python3 -c "from scrapers.database import init_db; init_db()"`

### Testing a scraper
```bash
cd ~/dental-pe-tracker
python3 -c "import ast; ast.parse(open('scrapers/FILE.py').read()); print('OK')"
python3 scrapers/FILE.py --dry-run   # most scrapers support this
```

## Checklist for Any Scraper Change

- [ ] `import ast` parse check passes
- [ ] `log_scrape_start()` called at top of `run()`
- [ ] `log_scrape_complete()` called at end with meaningful summary
- [ ] Uses `get_logger()` not `print()` for operational messages
- [ ] Uses `insert_or_update_practice()` / `insert_deal()` — not raw SQL INSERT
- [ ] Handles `requests.RequestException` with logging, doesn't crash pipeline
- [ ] Added to refresh.sh if it should run automatically
