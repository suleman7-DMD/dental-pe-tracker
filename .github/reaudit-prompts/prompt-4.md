# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

Day 4. Today's emphasis: **freshness drift**. By now any successful weekly cron run from the post-fix world should have populated new rows. If everything is still frozen at baseline, the cron really isn't firing and that's a 🚨.

## Inputs

Same as Day 3. Reference `AUDIT_REPORT_2026-04-25.md` Section "Pipeline Health Matrix" + "Suspected Root Causes".

## 10-Check Sweep + Freshness Focus

### Standard 10 (carry over)
Same as Day 1.

### Freshness probes

**F1 — Per-table updated_at distribution**
For each table that exposes `updated_at` or equivalent:
- `practices` — `MAX(updated_at)`. Baseline: ~April 2026 from Data Axle imports. Has it advanced?
- `deals` — `MAX(deal_date)` and `MAX(updated_at)` separately. Baseline `deal_date`: 2026-03-02.
- `practice_changes` — `MAX(detected_at)`. Should be < 7 days if cron is alive.
- `dso_locations` — `MAX(scraped_at)`. Baseline: stale.
- `ada_hpi_benchmarks.created_at` — was the workaround for NULL `updated_at`. Did anyone fix the underlying NULL?
- `practice_intel.research_date` — should advance only if a new batch was approved/spent.
- `zip_qualitative_intel.research_date` — same.

**F2 — Stale-row count buckets**
For `practices`:
- Rows with `updated_at` older than 30 days
- Rows older than 90 days
- Rows older than 365 days
Compare against baseline distribution if you can compute it from the local SQLite DB. Flag if 30-day-stale grew significantly.

**F3 — Pipeline event recency**
Tail `logs/pipeline_events.jsonl` if checked in. List all events from the last 7 days by `event_type`. Note any `error` or `timeout` events.

**F4 — Vercel deploy recency**
WebFetch `https://dental-pe-nextjs.vercel.app` and inspect HTML for any embedded build hash or revision. List any new deploys vs. baseline `dvqb3ym5z` from April 25.

**F5 — GitHub Actions run history**
If `gh` is available, list runs for the last week:
```
gh run list --workflow=keep-supabase-alive.yml --limit=5 --json databaseId,createdAt,conclusion
gh run list --workflow=reaudit.yml --limit=5 --json databaseId,createdAt,conclusion
```
Flag any failed runs.

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Freshness verdict: <ALIVE | DRIFT | DEAD>
- Most stale table: <name + age>
- Cron firing: <YES (evidence) | NO | UNKNOWN>

## Standard 10-check drift table

## Freshness probes (F1-F5)

## Backlog progress

## Recommended next actions (max 5)

## Raw evidence
```

Max 600 lines. Read-only. Done.

## Hard rules

Same as prior days. No edits. No commits. No spend. Do not retry beyond what each probe naturally requires.
