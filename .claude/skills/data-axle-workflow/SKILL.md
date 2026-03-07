---
name: data-axle-workflow
description: Guide the user through Data Axle exports, imports, and data enrichment. Use when the user mentions "Data Axle", "Reference Solutions", "business data", "buyability", "revenue", "employees", "export from library", "BU library", "WRDS", "smart batch", "ZIP batch", or wants to improve practice classification coverage.
---

# Data Axle Workflow

Data Axle (via BU Library's "Reference Solutions") provides ground-truth business data — revenue, employee count, year established, ownership type — for dental practices. This data powers buyability scoring and stealth DSO detection.

## Current State

- **Chicagoland**: 852 records imported
- **Boston Metro**: 0 records (biggest gap)
- **87.9% of practices are "unknown" ownership** — Data Axle is the primary way to improve this

## Export Options (fastest to slowest)

### Option A: Smart Batch Exporter (recommended)
```bash
python3 scrapers/data_axle_exporter.py --plan --metro boston   # see the plan
python3 scrapers/data_axle_exporter.py --metro boston           # interactive export
python3 scrapers/data_axle_exporter.py --combine               # combine CSVs after
```

The script manages clipboard, file naming, progress tracking. User handles browser + CAPTCHAs.

### Option B: WRDS Bulk Download (no CAPTCHAs)
BU has WRDS access. SIC code `802100` (6-digit). May lag 6-12 months.

### Option C: Manual Export
Print instructions: `python3 scrapers/data_axle_importer.py --instructions`

## Import Pipeline

After exporting CSVs:
```bash
mv ~/Downloads/data_axle*.csv ~/dental-pe-tracker/data/data-axle/
python3 scrapers/data_axle_importer.py --preview    # check column mapping
python3 scrapers/data_axle_importer.py --auto        # import
python3 scrapers/dso_classifier.py                   # classify new practices
python3 scrapers/merge_and_score.py                  # recalculate scores
```

## data_axle_importer.py Phases

The importer runs 7 phases on each batch:
1. **Import & validate** — read CSV, detect columns via fuzzy matching, filter to dental SIC
2. **Deduplicate** — normalize addresses, fuzzy-match names at same address → merge into "doors"
3. **Classify** — run `classify_practice()` on each door (name pattern + DBA matching)
4. **Buyability scoring** — age, revenue, employee count, ownership → 0-100 score
5. **Database integration** — fuzzy-match against existing NPPES practices, upsert
6. **Change detection** — compare against previous batch for acquisitions/closures
7. **Debug report** — generate HTML report in `data/data-axle/debug-reports/`

## Key Files

- `scrapers/data_axle_exporter.py` — interactive batch export assistant
- `scrapers/data_axle_importer.py` — 7-phase import pipeline (2,153 lines)
- `scrapers/data_axle_automator.py` — Playwright browser automation (fragile)
- `scrapers/data_axle_scraper.py` — Playwright ZIP-batch automation (fragile)
- `data/data-axle/` — raw CSVs go here
- `data/data-axle/processed/` — CSVs moved here after import
- `data/data-axle/debug-reports/` — HTML analysis reports

## Watched ZIP Codes

Chicagoland (35 ZIPs): 60491, 60439, 60441, 60540, 60564, 60565, ...
Boston Metro (21 ZIPs): 02116, 02115, 02118, 02119, 02120, 02215, ...

Full list: `SELECT zip_code, city, metro_area FROM watched_zips ORDER BY metro_area, zip_code`
