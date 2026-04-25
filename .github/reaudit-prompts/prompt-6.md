# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

Day 6. Today is the **month boundary** (April → May 2026). Watch for fence-post bugs in monthly cron logic and any reset behavior:
- Monthly NPPES refresh is supposed to fire on first Sunday at 6am — did it?
- ADA HPI publication month rolling over — does the importer recognize 2026-05?
- Any code path that uses `datetime.now().month` for partitioning or scoring?

## Inputs

Same as prior days.

## 10-Check Sweep + Month-Boundary Probes

### Standard 10 (carry over)

### Month-boundary probes

**M1 — NPPES monthly cron status**
Look for evidence the monthly refresh fired. Check `data/dental_pe_tracker.db` (if local) for `practices.updated_at >= 2026-05-01`. If 0 rows, monthly cron likely also dead (LWCR bug from baseline applied to weekly + monthly).

**M2 — ADA HPI freshness**
```
GET ${SUPABASE_URL}/rest/v1/ada_hpi_benchmarks?select=created_at&order=created_at.desc&limit=1
```
Most recent benchmark created_at. Baseline: pre-April. If no May benchmarks, the auto-downloader either didn't run or the publication month logic missed.

**M3 — `deal_date` distribution**
Compare deal_date histogram by month for last 6 months. Flag if any month is unexpectedly empty given prior cadence (~10-30 deals/month). Look specifically at April 2026 → May 2026 transition.

**M4 — Vercel build cache validity at month change**
WebFetch `https://dental-pe-nextjs.vercel.app/api/system/freshness` if such a route exists, otherwise inspect `/system` page for any freshness indicators showing "Last sync: X days ago" where X has crossed a threshold.

**M5 — `data/research_costs.json` rollover**
If file is committed, inspect last 50 entries to see if any month-to-month comparison broke (e.g., budgets carrying forward when they shouldn't, or month-summary aggregation skipping the month change).

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Month-rollover health: <Clean | Drift | Bug detected>
- Monthly NPPES refresh: <FIRED | NOT FIRED | UNKNOWN>

## Standard 10-check drift table

## Month-boundary probes (M1-M5)

## Backlog progress

## Recommended next actions (max 5)

## Raw evidence
```

Max 600 lines. Read-only.

## Hard rules

Standard. No edits. No commits. No spend.
