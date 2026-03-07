---
name: debug-pipeline
description: Debug scraper failures, data quality issues, pipeline errors, and data integrity problems. Use when the user reports a scraper failing, data looking wrong, numbers not matching, pipeline events showing errors, log files showing warnings, or database issues. Trigger phrases include "debug", "error", "failing", "broken", "wrong numbers", "data issue", "log", "pipeline failed", "scraper error", "not working", "refresh failed".
---

# Pipeline Debugging Guide

## Step 1: Check the structured event log

```bash
cd ~/dental-pe-tracker && python3 -c "
from scrapers.pipeline_logger import get_recent_events
for e in get_recent_events(limit=20):
    ts=e['timestamp'][:19]; s=e.get('source','?'); st=e.get('status','')
    print(f\"{'OK' if st=='success' else 'ERR' if st=='error' else 'START'} {ts}  {s:25}  {e.get('summary','')[:60]}\")
"
```

Look for: events with no matching "complete" (crashed mid-run), error events, suspiciously low new_records counts.

## Step 2: Check raw log files

```bash
# Most recent log
cat ~/dental-pe-tracker/logs/$(ls -t ~/dental-pe-tracker/logs/*.log | head -1) | tail -50

# Specific scraper log
grep "ERROR\|WARNING" ~/dental-pe-tracker/logs/*.log | tail -20
```

## Step 3: Check cron

```bash
crontab -l    # Should show two entries: Sunday 8am refresh, first Sunday 6am NPPES
```

If cron isn't running: Mac may have gone to sleep. Check `logs/cron_refresh.log` for last execution.

## Common Issues

### "Scraper returns 0 new records"
- Website HTML structure changed → inspect the target page, update CSS selectors/regex
- Rate limited → check for 403/429 responses in logs
- Already have all data → not an error, just no new content

### "Market Intel shows wrong numbers"
- Check denominator: must be `total_practices`, not `classified_count`
- Run `merge_and_score.py` to recalculate ZIP scores
- Check `ownership_status` distribution: `SELECT ownership_status, COUNT(*) FROM practices GROUP BY ownership_status`

### "ADA HPI download fails with BadZipFile"
- ADA returns HTML error pages with HTTP 200 for missing years
- The downloader checks content-type headers to detect this
- Verify: `python3 scrapers/ada_hpi_downloader.py --dry-run`

### "Database is locked"
- Another process has the SQLite DB open
- Check: `lsof ~/dental-pe-tracker/data/dental_pe_tracker.db`
- Kill zombie processes if needed

### "Classifier finds 0 new classifications"
- Normal if all name-matchable practices were already classified in prior runs
- 352k+ unknowns are genuinely unclassifiable by name alone — need Data Axle data
- To force reclassify: `python3 scrapers/dso_classifier.py --force`

### "Streamlit Cloud shows stale data"
- Need to compress + push the DB: see deploy commands in dashboard-dev skill
- Check if git push succeeded: `git log --oneline -3`

## Data Integrity Checks

```sql
-- Ownership status distribution
SELECT ownership_status, COUNT(*) as cnt FROM practices GROUP BY ownership_status ORDER BY cnt DESC;

-- Practices with affiliated_dso but wrong status
SELECT COUNT(*) FROM practices WHERE affiliated_dso IS NOT NULL AND ownership_status = 'unknown';

-- Duplicate NPIs (should be 0)
SELECT npi, COUNT(*) FROM practices GROUP BY npi HAVING COUNT(*) > 1;

-- Deals without dates
SELECT COUNT(*) FROM deals WHERE deal_date IS NULL;

-- Recent pipeline events
-- (use pipeline_logger Python API, not SQL — events are in JSONL, not DB)
```

## Nuclear Options (use with caution)

```bash
# Restore from backup
cp ~/dental-pe-tracker/backups/$(ls -t ~/dental-pe-tracker/backups/ | head -1) \
   ~/dental-pe-tracker/data/dental_pe_tracker.db

# Full rebuild (wipes DB)
rm data/dental_pe_tracker.db
python3 -c "from scrapers.database import init_db; init_db()"
# Then re-run: nppes_downloader → dso_classifier → merge_and_score
```
