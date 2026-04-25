# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

**One-week mark.** This is the most comprehensive of the daily probes. Today's emphasis: **end-to-end coverage of the original 27-item Prioritized Debug Backlog** from `AUDIT_REPORT_2026-04-25.md`. For each backlog item, verify whether it's been resolved, partially resolved, untouched, or regressed.

## Inputs

Same as prior days, plus: `FIX_REPORT_2026-04-25.md` if it exists. Use it to determine which backlog items the user *intended* to fix versus which were left for later.

## Full sweep + Backlog walkthrough

### Standard 10 (carry over)

### Backlog walkthrough — all 27 items

For each item in the baseline's "Prioritized Debug Backlog" section, verify status:

**P0 (Critical) items — Cron + Sync**
1. Weekly cron firing
2. Monthly cron firing
3. Sync FK orphan (`practice_signals` NPI 1316509367)
4. `verification_quality` enum drift
5. `_sync_watched_zips_only` TRUNCATE CASCADE behavior in production
6. Warroom living-map blank
7. 6 Launchpad AI routes returning 503

**P1 (High) items — Data quality**
8. 258 synthetic ZIP intel placeholders
9. Apostrophe normalization in deal names
10. GDN "Partners" ambiguity in fallback parser
11. SQLite ALTER TABLE idempotency
12. `/tmp/full_batch_id.txt` cross-process handoff fragility
13. Hardcoded $11 cost cap in `launch.py`
14. `ada_hpi_benchmarks.updated_at` always NULL
15. Mirror scrapers in `dental-pe-nextjs/scrapers/` deprecated but stranded

**P2 (Medium) items — UX + observability**
16. Verification-quality column stored but never displayed in UI
17. KPI subtitle layout inconsistencies
18. Documentation drift (CLAUDE.md vs. live behavior)
19. Pipeline event log rotation
20. Batch ID via `/tmp` not survivable

**P3 (Low) items — Hygiene**
21. Linting / TypeScript warnings
22. Unused imports
23. Dead components
24. Backlog of weekly research not yet enqueued
25. Boston Metro intel coverage (~zero)
26. Chicagoland practice intel backfill (~8,559 remaining)
27. Documentation: re-audit cadence

For each, set status to one of: `✅ Closed` / `🟡 Partial` / `⏳ Open` / `🚨 Regressed`.

### Sanity probes

**S1 — Build passes**
Note: do NOT run `npm run build` (mutating). Instead, inspect the most recent Vercel deploy status via the homepage HTML (look for build manifest hashes that indicate a successful production build).

**S2 — Read-only contract sanity**
Verify `git status --short` shows nothing unexpected at start of run.

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Week-1 verdict: <Healthy | Mostly fixed | Mixed | Concerning | Regressed>
- Closed items: <N of 27>
- Open critical items: <list P0/P1>

## Standard 10-check drift table

## Backlog walkthrough (27 rows)
| # | Severity | Item | Status | Evidence |

## New findings since baseline

## Sanity probes

## Recommended next actions (max 5)

## Raw evidence
```

Max 1000 lines (this is the one comprehensive prompt).

## Hard rules

Standard. Do not edit, commit, push, or spend. Do not modify the backlog itself; only report on it. If you cannot verify a specific item from CI alone (e.g., requires local launchctl), mark it `❓ Requires local check` and note exactly which command would resolve.
