# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

You are running in **GitHub Actions headless mode** (no interactive user). Be terse, decisive, and finish in a single pass. No clarifying questions; pick the most reasonable interpretation and proceed.

## Mission

Compare the **live state** of the dental-pe-tracker production stack to the baseline captured in `AUDIT_REPORT_2026-04-25.md` (committed at repo root). Detect drift, regression, and improvements. Save findings to `{{REPORT_PATH}}`.

This is a **READ-ONLY** sweep. Do not edit any files in the repo. Do not commit. Do not push. Do not modify Supabase rows. The only file you may write is `{{REPORT_PATH}}`.

## Inputs available to you

- Repo working tree (already checked out at the current directory)
- `AUDIT_REPORT_2026-04-25.md` — baseline (973 lines, the "before" picture)
- `FIX_REPORT_2026-04-25.md` — may or may not exist; if present, treat its claims as the "intended after" picture
- `CLAUDE.md` — project guide
- Environment vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ANTHROPIC_API_KEY`
- Live frontend: `https://dental-pe-nextjs.vercel.app` (use WebFetch)
- Local SQLite DB: `data/dental_pe_tracker.db` (decompressed if `.db.gz` was bundled; otherwise rely on Supabase REST)

You do **NOT** have:
- macOS `launchctl` (this runs on Linux). Skip the launchd cron check entirely; document this gap.
- Anthropic console access for batch-API health beyond what the API key can fetch.

## 10-Check Sweep

For each check, record: **Status** (✅ Healthy / ⚠️ Drift / 🚨 Regression / ➖ Skipped), **Baseline value** (from audit report), **Current value**, and one-line **Notes**.

### Check 1 — Live Vercel page health (10 routes)

WebFetch these URLs in parallel. For each, capture HTTP status + a 5-word qualitative note (e.g. "renders KPIs and table", "sidebar only, content blank"):
- `/`
- `/launchpad`
- `/warroom`
- `/deal-flow`
- `/market-intel`
- `/buyability`
- `/job-market`
- `/research`
- `/intelligence`
- `/system`

Compare against baseline section "Frontend Audit". The Warroom was dead on April 25 (3 critical failures); has it been fixed?

### Check 2 — Supabase row counts vs. baseline

Query Supabase REST API:
```
GET ${SUPABASE_URL}/rest/v1/<table>?select=count
   -H "apikey: ${SUPABASE_ANON_KEY}"
   -H "Prefer: count=exact"
```
Tables to check (all must match or exceed baseline):
- `practices` (baseline: 401,645)
- `deals` (baseline: 3,215)
- `practice_changes` (baseline: 5,100+)
- `zip_scores` (baseline: 290)
- `watched_zips` (baseline: 290)
- `dso_locations` (baseline: 408)
- `ada_hpi_benchmarks` (baseline: 918)
- `practice_intel` (baseline: 400 verified rows)
- `zip_qualitative_intel` (baseline: 290 rows, 258 synthetic placeholders)

A **decrease** without a known reason is a 🚨 Regression.

### Check 3 — Latest deal date

```
GET ${SUPABASE_URL}/rest/v1/deals?select=deal_date&order=deal_date.desc&limit=1
```
Baseline: `2026-03-02` (stale by 8 weeks at audit time). Has the GDN/PESP scraper produced anything newer?

### Check 4 — Pipeline event log freshness

If `data/dental_pe_tracker.db` exists, query: `SELECT MAX(timestamp) FROM pipeline_events`.
Otherwise check `logs/pipeline_events.jsonl` (tail last 5 lines). Baseline: last successful weekly run was prior to 2026-04-25; cron was confirmed dead due to launchd LWCR bug.

### Check 5 — Practice intel verification stats

```
GET ${SUPABASE_URL}/rest/v1/practice_intel?select=verification_quality
```
Aggregate counts by `verification_quality`. Baseline:
- verified: 52
- partial: 115
- insufficient: 0 (validate_dossier rejects them before storage)
- high (enum drift): 10
- NULL: ~226 (rows from before the verification gate shipped)

### Check 6 — ZIP intel synthetic placeholder count

Query for synthetic placeholders. Baseline says 258/290 rows are synthetic (research_method matches `seed%` or `placeholder%`):
```
SELECT COUNT(*) FROM zip_qualitative_intel WHERE research_method ILIKE 'seed%' OR research_method ILIKE 'placeholder%';
```
Run via Supabase REST equivalent (filter on research_method).

### Check 7 — Map render check

WebFetch `/warroom`, `/market-intel`, `/job-market`, `/launchpad`, `/deal-flow`. For each, search HTML for `mapboxgl-canvas` or `class="mapboxgl-map"` indicators. Baseline:
- 4 maps render (Job Market, Market Intel, Launchpad, Deal Flow choropleth)
- 1 map blank (Warroom living-map — bundle failure on April 25)

### Check 8 — Launchpad AI route health

Probe these 6 routes (POST or GET as appropriate, expect HTTP 200 OR documented 503 fallback):
- `/api/launchpad/ai/<route>` — list whatever exists by enumerating from `dental-pe-nextjs/src/app/api/launchpad/`
Baseline: 6 routes returned 503 due to missing API auth wiring.

### Check 9 — Documentation drift

`git log --since=2026-04-25 --oneline -- CLAUDE.md SCRAPER_AUDIT_STATUS.md AUDIT_REPORT_2026-04-25.md FIX_REPORT_2026-04-25.md`. List any commits that landed since the baseline. Note any new top-level Markdown files in the repo root.

### Check 10 — Commit drift on main

`git log --since=2026-04-25 --oneline | head -50`. Summarize the themes (fix vs. feat vs. docs vs. wip). Baseline ends at `96bc71f docs(phase3): rewrite resume checkpoint as debug-friendly status board`.

### Cron status (skipped on Linux)

Document explicitly: "launchctl unavailable on GitHub-hosted runner; weekly + monthly cron status must be re-checked locally". This is the documented gap.

## Output format

Write to `{{REPORT_PATH}}`. Structure:

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Overall: <Healthy | Drift detected | Regression detected>
- Highest-severity finding: <one sentence>
- Pace of repair vs. baseline: <ahead | on track | behind | unchanged>

## Drift table (10 checks)
| # | Check | Baseline | Current | Status | Notes |

## New findings since {{TARGET_DATE}}
<bulleted list of anything not present in AUDIT_REPORT_2026-04-25.md>

## Recommended next actions (max 5)
<ordered, each with a single concrete command or file edit>

## Raw evidence
<URLs hit, queries run, row counts returned>
```

Keep total length under 600 lines. Do not paste full HTML responses — extract the signal.

## Hard rules

1. **Read-only.** Do not run `git commit`, `git push`, `npm run build`, or any DB-mutating Supabase call.
2. **No `sudo`, no destructive Bash.** No `rm -rf`. No `pkill`. No log rotations.
3. If `WebFetch` returns a 5xx for a Vercel route, retry once after 30s, then mark the route status accordingly.
4. If you genuinely cannot answer a check (missing creds, missing data), mark it `➖ Skipped` with a reason — do not fabricate.
5. Stop at one full pass. Do not loop. Do not schedule follow-ups. Do not request more turns than necessary.
6. The single output file is `{{REPORT_PATH}}`. Do not write anywhere else in the repo.

When the report is written, your job is done. Exit cleanly.
