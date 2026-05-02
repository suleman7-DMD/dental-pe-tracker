# Dental PE Tracker — Full Stack Audit (2026-04-26)

User reports: Dashboard, Launchpad, and Warroom show stale/wrong data. Multiple days of debugging. No trust left in "all is good" claims.

## Phase 1 — Investigation (read-only, no code changes)

| Agent | Surface | Output file |
|-------|---------|-------------|
| @triage | Data freshness: SQLite vs Supabase row counts, sync timestamps, last successful pipeline run | `01-triage.md` |
| @audit-home | `/` Home dashboard — every KPI, deals feed, activity feed, freshness bar | `02-home.md` |
| @audit-launchpad | `/launchpad` — track scoring, dossiers, compound narrative, all 6 dossier tabs | `03-launchpad.md` |
| @audit-warroom | `/warroom` — sitrep KPIs, Living Map, target list, dossier drawer, signal overlays | `04-warroom.md` |
| @audit-pipeline | Scraper logs, recent runs, sync errors, log files for failures | `05-pipeline.md` |
| @playwright-setup | Install Playwright, take baseline screenshots of all 11 routes (production URL) | `06-playwright-setup.md` + `screenshots/` |

## Required evidence per finding

Every bug claim must include:
1. **What the UI shows** (screenshot path or quoted text)
2. **What the DB says** (SQL query + result)
3. **Severity** (P0=user-blocking, P1=wrong number, P2=cosmetic)
4. **Suspected file:line** (best guess root cause)

## Phase 2 — Fix dispatch (parallel by surface)

After phase 1, fix agents are dispatched one per surface, each given:
- Findings from their auditor
- Cross-references to other agents' findings (shared concerns)
- Mandate to prove the fix with a re-query and a screenshot

## Phase 3 — QA verification

@qa-verifier runs after every fix:
- Vitest (`src/__tests__/classification-primary.test.ts`)
- `npm run build` in `dental-pe-nextjs/`
- Playwright re-screenshot of every changed page
- Diff vs baseline screenshots
- Reject any fix that produces a regression
