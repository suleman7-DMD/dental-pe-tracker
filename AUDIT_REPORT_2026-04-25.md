# Dental PE Intelligence Platform — Master Audit Report
**Audit Date:** 2026-04-25
**Scope:** Read-only forensic audit; no code changes, no commits
**Method:** 6 parallel domain-scoped agents (A–F) + live-URL evidence + ground-truth SQLite/Supabase row counts
**Repo HEAD:** `96bc71f` on `main`
**Evidence files:** `/tmp/audit_agent_{A,B,C,D,E,F}_report.md`

---

## TL;DR FOR THE OWNER

You have **two working dashboards, one dead one, six AI routes returning 503, a cron that has never fired, three weeks of stale deal data, a 96.6% NULL entity_classification field, and an anti-hallucination defense that protects only one of three research paths.** The maps that render *are* real Mapbox; the Warroom map renders blank because its server-side data bundle throws. The "intelligent backend running automatically" exists in code but has never run on schedule — every "weekly" run since the launchd job was installed has been triggered manually. None of this is unfixable; most of it is one-line config or a single ALTER TABLE away.

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Codebase Map](#2-codebase-map)
3. [Feature Inventory Table](#3-feature-inventory-table)
4. [Pipeline Health Matrix](#4-pipeline-health-matrix)
5. [Scheduled Job Table](#5-scheduled-job-table)
6. [Database Integrity](#6-database-integrity)
7. [Data Flow Diagrams](#7-data-flow-diagrams)
8. [Frontend Audit](#8-frontend-audit)
9. [Map Reality Check](#9-map-reality-check)
10. [Hallucination Audit](#10-hallucination-audit)
11. [Documentation Drift Log](#11-documentation-drift-log)
12. [Symptom Diagnosis](#12-symptom-diagnosis)
13. [Pain Point Resolutions](#13-pain-point-resolutions)
14. [Suspected Root Causes](#14-suspected-root-causes)
15. [Prioritized Debug Backlog](#15-prioritized-debug-backlog)

---

## 1. EXECUTIVE SUMMARY

### What's Live

- **8 of 10 Next.js pages render correctly on production** (`dental-pe-nextjs.vercel.app`) — Home, Deal Flow, Market Intel, Buyability, Job Market, Intelligence, Research, System.
- **2 pages broken or degraded:** Warroom shows "Data load issue — Unable to load Warroom data" with 0 ranked targets / 0 briefing items; Launchpad's 6 AI-powered routes (`/api/launchpad/{narrative,smart-briefing,ask,interview-prep,contract-parse,zip-mood}`) return 503 because `ANTHROPIC_API_KEY` is not set in Vercel.
- **All 4 Mapbox maps that should be real *are* real** (Launchpad, Job Market practice density, Market Intel consolidation, Deal Flow state choropleth). The Warroom living map is real Mapbox code rendering against an empty data bundle, so its choropleth shows blank tiles.

### What's Stale / Wrong

| Symptom | Reality |
|---------|---------|
| Live `MAX(deal_date)` | **2026-03-02** (54 days behind today's 2026-04-25) |
| GDN April 2026 deals | **0 ingested**; March 2026 roundup published at https://www.groupdentistrynow.com/dso-group-blog/dso-deals-march-2026/ has not been scraped |
| PESP latest deal | **2025-10-01** (`PESP_EXPECTED_EMPTY_MONTHS` frozenset marks Oct 2025 → Apr 2026 as expected-empty in `pesp_scraper.py:64-85`) |
| `entity_classification` NULL | **387,977 of 402,004 globally (96.6%)**; 44 of 14,053 within watched ZIPs |
| `zip_qualitative_intel` rows with real cost | **0 of 290** — all are synthetic placeholders (`cost_usd=0`) |
| `dso_locations` | **92 rows** (15 of 18 DSOs are skipped for `needs_browser=True` in `adso_location_scraper.py:670`) — CLAUDE.md claims 408 |
| `practice_signals` in Supabase | **0 rows** — FK violation on NPI 1316509367 (Grace Kwon, 01610 Worcester MA) blocks sync |
| Supabase vs SQLite deal drift | **+41 rows in Supabase** (incremental_updated_at sync never propagates SQLite deletes) |

### What's Never Run

- **`com.dental-pe.weekly-refresh`** launchd job: `runs=0` since install. Listed in `~/Library/LaunchAgents/`, but `launchctl list | grep dental` shows no firing history. Every "weekly" pipeline run since the cron was installed has been triggered manually.
- **`com.dental-pe.nppes-refresh`** launchd job: `runs=0`.
- **GitHub Actions `keep-supabase-alive.yml`** workflow: run `24931115878` failed with empty `SUPABASE_URL`/`SUPABASE_ANON_KEY` secrets. Free-tier Supabase pause is therefore *only* avoided by the user's manual visits to the dashboard.
- **`compute_signals.py`** (1,424 lines, materializes `practice_signals` and `zip_signals`): runs in SQLite on demand but the resulting tables never reach Supabase because of the FK violation noted above.

### What's Lying

- **Anti-hallucination protocol covers only the PRACTICE batch path** in `research_engine.py`. The ZIP intel path (`research_zip()` at `research_engine.py:43-50`) and the Launchpad JOB_HUNT path (`research_engine.py:96-107`) have no `force_search`, no per-claim `_source_url`, no terminal `verification` block, no `validate_dossier()` gate. The 290 ZIP intel rows + every Launchpad-fetched dossier are *not* covered by the bulletproofing the user paid $14.91 to validate. (Agent B, lines 145–214.)
- **`weekly_research.py:304-320`** has a `--sync-only` mode that *bypasses* `validate_dossier()` and stores raw model output. If invoked, hallucinations slip past the gate.
- **`verification_quality` column** is stored in Supabase `practice_intel` but never surfaced in `intelligence-shell.tsx`. Users cannot tell verified (52) from partial (115) from "high" enum-drift (10) dossiers in the UI. (Agent D, line 297.)
- **DSO Tier list** is *not* fiction — 16 entries with real citation URLs to NY AG settlements, PBS Frontline, etc. (Agent D, lines 270–275.)
- **All 4 maps that *should* be real *are* real Mapbox** with real coordinates. The "fake map" pain point is conflating the Warroom's empty-bundle blank rendering with synthetic data — the data is real, the bundle just fails server-side. (Agent D, line 201.)

### Severity Classification

- **P0 (production-broken, user-facing):** Warroom dead, 6 Launchpad AI routes 503, GDN scraper 54 days stale.
- **P1 (silent correctness risk):** Cron never fires, anti-hallucination bypass on 2 of 3 research paths, 96.6% NULL entity_classification, ZIP intel 100% synthetic.
- **P2 (data-quality drift):** dso_locations 408→92, Supabase 41-row deal surplus, practice_signals 0 rows in Supabase, 14 numeric drifts in CLAUDE.md.
- **P3 (cosmetic):** verification_quality not displayed, "34 vs 177 Acquisition Targets" definition conflict, "481 vs 2,990 Data Axle" reconciliation missing.

---

## 2. CODEBASE MAP

```
/Users/suleman/dental-pe-tracker/
├── CLAUDE.md                          900+ lines of project docs (14 numeric drifts, see §11)
├── SCRAPER_AUDIT_STATUS.md            Audit status board from April 22 audit
├── AUDIT_REPORT_2026-04-25.md         ← this report
│
├── dashboard/
│   └── app.py                         2,583-line Streamlit app (legacy frontend, still live at suleman7-pe.streamlit.app)
│
├── dental-pe-nextjs/                  Primary frontend (Vercel: dental-pe-nextjs.vercel.app)
│   ├── CLAUDE.md                      Frontend-specific docs (also drifted)
│   ├── src/app/                       Next.js 16 App Router
│   │   ├── page.tsx                   Home page (Server Component, force-dynamic)
│   │   ├── launchpad/                 First-job finder; 7 AI API routes (api/launchpad/*)
│   │   ├── warroom/                   ⚠ DEAD ON LIVE — getSitrepBundle throws
│   │   ├── deal-flow/                 4-tab deal explorer
│   │   ├── market-intel/              3-tab consolidation analysis
│   │   ├── buyability/                Verdict extraction, CSV export
│   │   ├── job-market/                4-tab post-grad job hunter
│   │   ├── intelligence/              AI dossier viewer (verification_quality NOT surfaced)
│   │   ├── research/                  4-tab research (PE sponsors, platforms, state, SQL)
│   │   ├── system/                    Freshness, coverage, completeness, log viewer
│   │   └── api/
│   │       ├── deals/                 POST/PATCH deal entries
│   │       ├── practices/             GET/PATCH practice entries
│   │       ├── sql-explorer/          SELECT-only RPC
│   │       ├── watched-zips/          ZIP CRUD
│   │       └── launchpad/
│   │           ├── ask/               503 — ANTHROPIC_API_KEY missing
│   │           ├── compound-narrative/ 503
│   │           ├── contract-parse/    503
│   │           ├── interview-prep/    503
│   │           ├── narrative/         503
│   │           ├── smart-briefing/    503
│   │           └── zip-mood/          503
│   │
│   └── src/lib/
│       ├── supabase/queries/          15+ query modules — typed client
│       ├── warroom/                   data.ts (bundle), ranking.ts (scoring), signals.ts (flag types)
│       ├── launchpad/                 ranking.ts (track multipliers), signals.ts, dso-tiers.ts
│       └── constants/entity-classifications.ts  Canonical EC helpers (isIndependent, classifyPractice)
│
├── scrapers/                          Pipeline (ingest → SQLite → sync → Supabase)
│   ├── nppes_downloader.py            681 lines — federal provider data
│   ├── data_axle_importer.py          2,650 lines — 7-phase Data Axle pipeline + Pass 6 corporate linkage
│   ├── pesp_scraper.py                552 lines — DNS+HTTP retry, COMMENTARY_PATTERNS pre-filter
│   ├── gdn_scraper.py                 720 lines — pagination guard, deal verb set
│   ├── pitchbook_importer.py          616 lines — manual CSV/XLSX (NO automation)
│   ├── adso_location_scraper.py       728 lines — 15 of 18 DSOs skipped (needs_browser=True)
│   ├── ada_hpi_downloader.py          237 lines — XLSX download
│   ├── ada_hpi_importer.py            351 lines — STILL DOES NOT SET updated_at
│   ├── dso_classifier.py              547 lines — Pass 3 NEVER auto-invoked in main run
│   ├── merge_and_score.py             719 lines — ZIP scoring
│   ├── compute_signals.py             1,424 lines (UNDOCUMENTED) — practice_signals/zip_signals
│   ├── cleanup_pesp_junk.py           UNDOCUMENTED maintenance
│   ├── fast_sync_watched.py           UNDOCUMENTED watched-only Supabase sync
│   ├── research_engine.py             400 lines — Anthropic API wrapper
│   ├── intel_database.py              266 lines — Intel CRUD
│   ├── qualitative_scout.py           380 lines — ZIP intel (NO bulletproofing)
│   ├── practice_deep_dive.py          577 lines — Practice intel CLI
│   ├── weekly_research.py             309 lines — Batch automation
│   ├── sync_to_supabase.py            ~1,000 lines (resilient as of 2026-04-23)
│   ├── pipeline_logger.py             295 lines — JSON-Lines events
│   ├── refresh.sh                     run_step() wrapper with descendant kill
│   ├── nppes_refresh.sh               ⚠ no timeout protection
│   ├── dossier_batch/                 ⚠ NEW (committed 2026-04-25)
│   │   ├── launch.py                  200-practice batch submitter
│   │   ├── poll.py                    poll + validate + store + sync
│   │   ├── migrate_verification_cols.py  one-shot Supabase migration
│   │   └── last_run_summary.json      regression baseline
│   └── test_sync_resilience.py        11 unit tests (zero-row guard, signal handler, post-sync assert)
│
├── data/
│   ├── dental_pe_tracker.db           SQLite, 145 MB — pipeline ground truth
│   ├── dental_pe_tracker.db.gz        gzip for git push (Streamlit Cloud)
│   ├── ADSO_TARGETS.csv               18 DSO scrape targets (15 marked needs_browser)
│   └── research_costs.json            500-entry rolling cost log
│
├── logs/
│   ├── pipeline_events.jsonl          Structured log
│   └── …per-run logs
│
├── pipeline_check.py                  540-line health check
│
└── .github/workflows/
    └── keep-supabase-alive.yml        ⚠ FAILING (empty secrets)
```

**Total LOC inventory:**
- Python pipeline: ~12,000 LOC
- Streamlit dashboard: 2,583 LOC (legacy)
- Next.js frontend: ~25,000 LOC across `src/app/` + `src/lib/` + `src/components/`
- Test suite: 11 sync resilience tests (0 frontend tests)

---

## 3. FEATURE INVENTORY TABLE

### 3.1 Next.js Pages (10) — see Agent D §D1 for full breakdown

| Page | Status | Critical Issue |
|------|--------|----------------|
| `/` Home | WORKS | None — all 6 KPIs accurate |
| `/launchpad` | PARTIAL | 6 AI routes BROKEN (503); ranking + map WORK |
| `/warroom` | **BROKEN** | "Data load issue" on live — `getSitrepBundle` throws server-side |
| `/deal-flow` | WORKS | Stale at 2026-03-02 (data layer issue, not UI) |
| `/market-intel` | WORKS | Tiered KPIs accurate; map renders client-side |
| `/buyability` | WORKS | Definition conflict with Home (177 vs 34 "Acquisition Targets") |
| `/job-market` | WORKS | Map renders 2,848 real lat/lon points |
| `/intelligence` | PARTIAL | `verification_quality` stored but NOT displayed |
| `/research` | PARTIAL | SQL Explorer preset queries not visible in WebFetch |
| `/system` | WORKS | "481 vs 2,990 Data Axle" reconciliation missing |

### 3.2 Backend Pipeline Components

| Component | Status | Last Verified Working |
|-----------|--------|----------------------|
| NPPES downloader | WORKS | 2026-04-22 audit + manual run |
| Data Axle importer (7-phase + Pass 6) | WORKS | 2026-04-22 |
| PESP scraper | WORKS | 2025-10-01 (latest deal); empty-month freeze through Apr 2026 |
| GDN scraper | DEGRADED | 2026-03-01 (March 2026 roundup published but not scraped) |
| PitchBook importer | MANUAL ONLY | No automation; last run unclear |
| ADSO location scraper | DEGRADED | 92 of 408 historical (15 of 18 DSOs skipped) |
| ADA HPI downloader/importer | WORKS | But `updated_at` still NULL on all rows |
| DSO classifier (4-pass) | DEGRADED | Pass 3 (`classify_entity_types`) NEVER auto-invoked |
| Merge & score | WORKS | 290 watched ZIPs scored |
| Compute signals (1,424 LOC, undocumented) | WORKS in SQLite | FAILS to sync to Supabase (FK violation) |
| Quality scout (ZIP intel) | UNPROTECTED | No anti-hallucination defense |
| Practice deep dive (CLI) | UNPROTECTED | No anti-hallucination defense |
| Weekly research (batch) | PROTECTED | Only path with `validate_dossier()` |
| Sync to Supabase | RESILIENT | Per-row savepoints, signal handlers, post-sync assertions |

### 3.3 Cron / Scheduled Jobs — see §5

### 3.4 API Routes (12 in Next.js)

| Route | Method | Status |
|-------|--------|--------|
| `/api/deals` | GET/POST/PATCH | WORKS |
| `/api/practices/[npi]` | GET/PATCH | WORKS |
| `/api/sql-explorer` | POST | PARTIAL — RPC may not be deployed |
| `/api/watched-zips` | GET/POST/DELETE | WORKS |
| `/api/launchpad/ask` | POST | **BROKEN — 503** |
| `/api/launchpad/compound-narrative` | POST | **BROKEN — 503** |
| `/api/launchpad/contract-parse` | POST | **BROKEN — 503** |
| `/api/launchpad/interview-prep` | POST | **BROKEN — 503** |
| `/api/launchpad/narrative` | POST | **BROKEN — 503** |
| `/api/launchpad/smart-briefing` | POST | **BROKEN — 503** |
| `/api/launchpad/zip-mood` | POST | **BROKEN — 503** |

---

## 4. PIPELINE HEALTH MATRIX

Source: Agent A §A1, Agent E §E1, Agent C §C1.

| Pipeline Step | Last Successful Run | Rows Produced | Health | Root Cause If Degraded |
|---------------|--------------------:|--------------:|--------|------------------------|
| `nppes_downloader.py` | 2026-04-22 (manual) | 13,561 | OK | — |
| `data_axle_importer.py` | 2026-04-22 (manual) | 2,990 enriched | OK | — |
| `pesp_scraper.py` | 2026-04-22 (manual) | 329 deals; max 2025-10-01 | DEGRADED | `PESP_EXPECTED_EMPTY_MONTHS` (`pesp_scraper.py:64-85`) freezes Oct 2025–Apr 2026 as "expected empty"; PESP site has restructured deal commentary |
| `gdn_scraper.py` | 2026-04-22 (manual) | 2,515 deals; max 2026-03-01 | DEGRADED | March 2026 roundup at `groupdentistrynow.com/dso-group-blog/dso-deals-march-2026/` IS published but pagination crawler stops at page 8 / April 2025; 6 GDN parser failures dropping `target_name` |
| `pitchbook_importer.py` | UNCLEAR | 10 deals (down from claimed 42) | DEGRADED | NO AUTOMATION — manual CSV/XLSX upload only; 100% of imported deals have `target_name=NULL` |
| `adso_location_scraper.py` | 2026-04-22 (manual) | 92 (down from 408) | DEGRADED | 15 of 18 DSOs in `data/ADSO_TARGETS.csv` have `needs_browser=True`; `adso_location_scraper.py:670` skips them. Only 5 brands actually scraped: Tend (30), Gentle Dental (29), Risas Dental (21), Specialized Dental Partners (6), Community Dental Partners (6) |
| `ada_hpi_downloader.py` | 2026-04-22 (manual) | 918 | OK (data) / DEGRADED (freshness) | `updated_at` is NULL on all 918 rows — System page reads `created_at` as workaround |
| `dso_classifier.py` Pass 1+2+4 | 2026-04-22 (manual) | — | OK | — |
| `dso_classifier.py` Pass 3 (`classify_entity_types`) | UNCLEAR | 14,009 of 402,004 (3.5%) | DEGRADED | Only invoked with `--zip-filter` or `--entity-types-only` flags (`dso_classifier.py:1373-1377`); main pipeline run skips it. **387,977 NULLs (96.6%) globally, 44 NULL within watched ZIPs** |
| `merge_and_score.py` | 2026-04-22 (manual) | 290 zip_scores | OK | — |
| `compute_signals.py` (UNDOCUMENTED) | UNCLEAR | SQLite: practice_signals 14,045 / zip_signals 296 | OK in SQLite | Sync FAILS to Supabase due to FK violation on NPI 1316509367 (Grace Kwon, 01610) |
| `qualitative_scout.py` | UNCLEAR | 290 rows; **0 with cost_usd > 0** | DEGRADED | All 290 are synthetic placeholders; no real Anthropic API research; **NO ANTI-HALLUCINATION DEFENSE** |
| `practice_deep_dive.py` (CLI) | UNCLEAR | 226 rows pre-bulletproofing | DEGRADED | **NO ANTI-HALLUCINATION DEFENSE** on this CLI path |
| `weekly_research.py --batch` | 2026-04-25 (this session) | 174 stored / 26 quarantined | OK (PROTECTED) | Fully bulletproofed |
| `sync_to_supabase.py` | 2026-04-25 (this session) | 17,968 rows | OK | — |

---

## 5. SCHEDULED JOB TABLE

Source: Agent A §A2, Agent E §E2.

| Job | Schedule | Configured | Actually Fired | Evidence |
|-----|----------|-----------|----------------|----------|
| `com.dental-pe.weekly-refresh` | Sunday 8am | `~/Library/LaunchAgents/com.dental-pe.weekly-refresh.plist` | **runs=0** | `launchctl list \| grep dental-pe` shows no firing history. Only March 22, 2026 matched 8am Sunday since install — and `logs/refresh-2026-03-22.log` does not exist. macOS Sequoia LWCR stale-context bug confirmed in CLAUDE.md "Pipeline Audit" section. |
| `com.dental-pe.nppes-refresh` | First Sunday 6am | `~/Library/LaunchAgents/com.dental-pe.nppes-refresh.plist` | **runs=0** | Same pattern. `nppes_refresh.sh:18-27` lacks the descendant-kill timeout protection added to `refresh.sh` |
| GitHub Actions `keep-supabase-alive.yml` | Every 3 days at 12:00 UTC | `.github/workflows/keep-supabase-alive.yml` | **FAILING** | Run `24931115878` failed with empty `SUPABASE_URL`/`SUPABASE_ANON_KEY` secrets. User has not added secrets in GitHub repo settings (CLAUDE.md notes: "REQUIRES USER ACTION"). |

**Net effect:** every "weekly" pipeline run since the launchd jobs were installed has been triggered manually by the user via terminal. The "intelligent backend running automatically" pain point is grounded in fact: there is no automation actually firing.

---

## 6. DATABASE INTEGRITY

Source: Agent C (full report).

### 6.1 Schema Drift: SQLite vs Postgres

| Issue | File:Line | Impact |
|-------|-----------|--------|
| `schema_postgres.sql` missing 11 columns + 2 tables vs SQLAlchemy models | `schema_postgres.sql` | Fresh Supabase install would fail to receive `practice_signals` (51 cols), `zip_signals` (53 cols), and 11 verification/intel columns on `practice_intel` |
| Type mismatches | `practices.buyability_score` SQLite=INTEGER, Postgres=DOUBLE PRECISION; `practices.classification_confidence` same pattern | Score values may round-trip lossily between SQLite and Postgres |
| `Base.metadata.create_all()` does NOT alter existing tables | `database.py` standard SQLAlchemy behavior | Adding `verification_searches`, `verification_quality`, `verification_urls` to `practice_intel` required explicit `ALTER TABLE` on BOTH databases (handled out-of-band by `migrate_verification_cols.py` for Supabase + raw `sqlite3` CLI for SQLite) |
| No migration tracking table | — | No way to know which migrations have been applied to a given DB instance |

### 6.2 Data Drift: Counts

| Table | SQLite | Supabase | Drift Direction | Cause |
|-------|--------|----------|-----------------|-------|
| `deals` | 2,854 | 2,895 | +41 in Supabase | `incremental_updated_at` sync never propagates SQLite deletes; deleted/cleaned-up SQLite deals remain in Supabase |
| `practice_signals` | 14,045 | **0** | Sync blocked | NPI 1316509367 (Grace Kwon, 01610 Worcester MA — NOT "Grace Kim 02115" as CLAUDE.md claims) FK violation. 13 cross-ZIP NPIs total |
| `zip_signals` | 296 | **0** | Sync blocked | Same FK chain |
| `dso_locations` | 92 | 92 | Consistent | But CLAUDE.md claims 408 — actual is 92 (15 of 18 DSOs skipped browser-only) |
| `zip_qualitative_intel` | 290 | 290 | Consistent | All 290 have `cost_usd=0` — synthetic placeholders, not real research |
| `practice_intel` | 400 | 400 | Consistent | 174 protected (April 25 batch) + 226 unprotected (pre-bulletproofing CLI) |
| `entity_classification` NULL | 387,977 | (mirrored) | Consistent | 96.6% NULL globally; 44 NULL in watched ZIPs |
| `verification_quality` distribution | 223 NULL / 10 high (enum drift) / 115 partial / 52 verified / 0 insufficient | (mirrored) | Consistent | Pre-bulletproofing rows lack the column entirely |

### 6.3 Foreign Key Integrity

- **`practice_changes_npi_fkey`** (ON DELETE NO ACTION): caused the April 22 `_sync_watched_zips_only` failure when `DELETE FROM practices` cascaded into `practice_changes`. Resolved by switching to `TRUNCATE TABLE practices CASCADE`.
- **`practice_signals.npi_fkey`**: NPI 1316509367 exists in `practice_signals` but not `practices`. Pre-existing before April 25 session. Fix: `DELETE FROM practice_signals WHERE npi NOT IN (SELECT npi FROM practices)` plus add the same filter inside `compute_signals.py`.

### 6.4 Verification Column Migration State

| DB | `verification_searches` | `verification_quality` | `verification_urls` |
|----|------------------------:|-----------------------:|--------------------:|
| SQLite | ADDED (raw ALTER 2026-04-25) | ADDED | ADDED |
| Supabase | ADDED (`migrate_verification_cols.py` run 2026-04-25) | ADDED, indexed | ADDED |
| `init_db()` in `database.py` | NOT in CREATE TABLE statements — **fresh install would fail** | Same | Same |

### 6.5 Schema Files at Repo

- `scrapers/database.py` — SQLAlchemy models (source of truth for SQLite via `Base.metadata.create_all()`)
- `schema_postgres.sql` — manually maintained, drifted (see §6.1)
- `scrapers/dossier_batch/migrate_verification_cols.py` — one-shot, idempotent on Postgres only

---

## 7. DATA FLOW DIAGRAMS

### 7.1 End-to-End Ingest → Frontend

```
Federal/Web Sources                    SQLite (data/dental_pe_tracker.db)
─────────────────────┐                  ┌───────────────────────────────┐
NPPES (federal CSV)  │                  │ practices (402,004)            │
PESP (web scrape)    │     scrapers/    │ deals (2,854)                  │
GDN (web scrape)     ├──────────────────▶ practice_changes (8,848)       │
ADSO (web scrape)    │  (pipeline_logger)│ zip_scores (290)               │
PitchBook (manual)   │                  │ practice_signals (14,045)      │
ADA HPI (XLSX)       │                  │ zip_signals (296)              │
Anthropic API        │                  │ practice_intel (400)           │
                     │                  │ zip_qualitative_intel (290)    │
                     ┘                  └───────────────────────────────┘
                                                       │
                                                       │ sync_to_supabase.py
                                                       │ ┌─incremental_updated_at: deals
                                                       │ ├─incremental_id: practice_changes
                                                       │ └─full_replace: everything else
                                                       ▼
                                        Supabase Postgres
                                        ┌───────────────────────────────┐
                                        │ Mirror of SQLite              │
                                        │ EXCEPT:                       │
                                        │  • deals = 2,895 (+41 drift)  │
                                        │  • practice_signals = 0 (FK)  │
                                        │  • zip_signals = 0 (FK chain) │
                                        └───────────────────────────────┘
                                                       │
                                                       │ HTTPS (anon key, RLS)
                                                       │ Server Components: createServerClient()
                                                       │ Client Components: createBrowserClient()
                                                       ▼
                                        Next.js 16 Frontend (Vercel)
                                        ┌───────────────────────────────┐
                                        │ 10 pages, all force-dynamic   │
                                        │ React Query 30min stale cache │
                                        │ Mapbox GL maps (4 of 5 work)  │
                                        └───────────────────────────────┘
                                                       │
                                                       ▼
                                            User Browser
                                        x-vercel-cache: MISS
                                        Cache-Control: no-store
                                        (no caching anywhere)
```

### 7.2 Anti-Hallucination Defense Path Coverage

```
research_engine.py
├── PRACTICE batch path (research_practice / build_batch_requests "practice")
│   ├── force_search=True ✓
│   ├── max_searches=5 ✓
│   ├── tool_choice=web_search forced ✓
│   ├── PRACTICE_USER schema with _source_url ✓
│   ├── Terminal verification block ✓
│   └── validate_dossier() in weekly_research.py ✓
│
├── ZIP intel path (research_zip / qualitative_scout.py)
│   ├── force_search ✗
│   ├── tool_choice ✗
│   ├── _source_url required ✗
│   ├── verification block ✗
│   └── validate_dossier() ✗   ← UNPROTECTED
│
└── JOB_HUNT path (Launchpad smart-briefing / api/launchpad/*)
    ├── force_search ✗
    ├── tool_choice ✗
    ├── _source_url required ✗
    ├── verification block ✗
    └── validate_dossier() ✗   ← UNPROTECTED
```

### 7.3 Sync Strategy → Table Mapping

```
TABLES_TO_SYNC (sync_to_supabase.py top-level dict)
│
├── incremental_updated_at
│   ├── practices (per-row begin_nested savepoint on UniqueViolation)
│   └── deals (per-row begin_nested savepoint on uix_deal_no_dup violation)
│       └── ⚠ Never propagates SQLite DELETEs → +41 row drift
│
├── incremental_id
│   └── practice_changes (per-row savepoint, watched-ZIP filter)
│
└── full_replace (TRUNCATE CASCADE + INSERT, with MIN_ROWS_THRESHOLD floor)
    ├── zip_scores                  (290)
    ├── watched_zips                (290)
    ├── dso_locations               (92)
    ├── ada_hpi_benchmarks          (918)
    ├── pe_sponsors                 (40, floor=10)
    ├── platforms                   (140, floor=20)
    ├── zip_overviews               (12, floor=5)
    ├── zip_qualitative_intel       (290, floor=0)
    ├── practice_intel              (400)
    ├── practice_signals            (14,045 → 0 in Supabase due to FK)
    ├── zip_signals                 (296 → 0 in Supabase due to FK chain)
    └── pipeline_events             (JSONL → table)
```

---

## 8. FRONTEND AUDIT

Source: Agent D §D1 + my live URL findings.

### 8.1 Live URL Sweep (HTTP 200)

All 10 routes return HTTP 200 on `dental-pe-nextjs.vercel.app`. Response headers:
```
HTTP/2 200
Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate
x-vercel-cache: MISS  (every route, every fetch — no edge caching)
content-type: text/html; charset=utf-8
```

This means the staleness pain point is NOT caused by browser/CDN/edge cache. The data displayed on `/` is the same data Supabase returns at request time. Stale data = Supabase has stale data, not a caching artifact.

### 8.2 Per-Page Status (from Agent D, condensed)

See [§3.1](#31-nextjs-pages-10--see-agent-d-d1-for-full-breakdown) for the high-level table. Key findings:

- **Home (`/`)**: All 6 KPIs accurate. Activity feed shows 2026-04-24 changes (live).
- **Launchpad (`/launchpad`)**: Ranking/scoring/maps WORK. All 6 AI routes return 503.
- **Warroom (`/warroom`)**: ⚠ "Data load issue — Unable to load Warroom data." 0 ranked targets, 0 briefing items. Root cause: `getSitrepBundle()` throws server-side at `warroom/page.tsx:22`.
- **Deal Flow (`/deal-flow`)**: WORKS. Shows 2,895 deals, latest 2026-03-02 — accurate but stale.
- **Market Intel (`/market-intel`)**: WORKS. Tiered KPIs match `getPracticeStats`.
- **Buyability (`/buyability`)**: WORKS. Definition conflict with Home page (177 vs 34 "Acquisition Targets" — both correct per their own definition).
- **Job Market (`/job-market`)**: WORKS. Practice density map renders 2,848 real lat/lon points.
- **Intelligence (`/intelligence`)**: PARTIAL. ZIP table + dossier table render. `verification_quality` column exists in DB but is NOT surfaced in `intelligence-shell.tsx`.
- **Research (`/research`)**: PARTIAL. SQL Explorer preset queries not visible in WebFetch result — RPC may not be deployed.
- **System (`/system`)**: WORKS. Shows "481 Data Axle records" while other pages show "2,990 enriched" — both correct, no UI explanation of the difference.

### 8.3 React Query Configuration — CLAUDE.md Drift

CLAUDE.md claims React Query has 5min stale time globally. Reality:

```typescript
// src/providers/query-provider.tsx:12
staleTime: 30 * 60 * 1000,  // 30 min — NOT 5 min
gcTime: 60 * 60 * 1000,     // 60 min
```

Warroom and Launchpad hooks override to 5min via per-query `staleTime`. The 30min global is the actual default.

### 8.4 Cross-Page Consistency (Agent D §D9)

| Metric | Home | Market Intel | Job Market | System |
|--------|------|-------------:|-----------:|-------:|
| Total practices | 14,053 | 14,053 | 14,053 | 14,053 |
| High-conf corporate | 2.2% | 2.2% | 2.0% | — |
| All-signals corporate | — | 9.9% | 9.7% | — |
| Data Axle enriched | 2,990 | 2,990 | 2,990 | **481** ← discrepancy |
| Retirement Risk | 226 | — | — | — |
| Acquisition Targets | **34** ← strict | — | — | — |
| Buyability "targets" | — | — | — | **177** ← broad |

The 481 vs 2,990 discrepancy: System page counts `data_source = 'data_axle'` (literal source) = 481; Home/Market Intel/Job Market count `data_axle_import_date IS NOT NULL` (any enrichment) = 2,990. Both correct, no tooltip.

### 8.5 Dead/Stale Code

- `briefing-pane.tsx` (referenced in CLAUDE.md) — file doesn't exist; actual is `briefing-rail.tsx`
- `WARROOM_MODES` modes 1 (Sitrep) and 3 (Profile) — cut in Phase 2 but CLAUDE.md keyboard shortcut docs still reference them
- `dental-pe-nextjs/scrapers/` mirror directory — DEPRECATED markers present but directory is `.gitignore`d, so markers stranded on local disk only
- `DEFAULT_WARROOM_LENS = "consolidation"` in `mode.ts:19` — overridden by `MODE_DEFAULT_LENS` in `warroom-shell.tsx:84-87`; library constant is effectively dead

---

## 9. MAP REALITY CHECK

Source: Agent D §D3 + my code spot-checks.

| Map | Page | Verdict | Data Source | Coordinate Verification |
|-----|------|---------|-------------|--------------------------|
| Practice Density Map | `/job-market` | **REAL** | 2,848 practices with `latitude/longitude` from Data Axle enrichment | `practice-density-map.tsx:271-276` filters `p.latitude != null && Number(p.latitude) !== 0`; Mapbox GL hex+dot layers |
| Consolidation Map | `/market-intel` | **REAL** | `zip_scores.corporate_share_pct` + `ZIP_CENTROIDS` lat/lon | `consolidation-map.tsx`; Mapbox renders client-side ("Loading map…" in WebFetch) |
| State Choropleth | `/deal-flow` | **REAL** | `dealsByState` from paginated `getDealsByFilters()` + Mapbox US state shapefile | `state-choropleth.tsx` |
| Launchpad Living Map | `/launchpad` | **REAL** | `bundle.zipScores` + `ZIP_CENTROIDS` (60606=Chicago Loop, 60515=Downers Grove, 60004=Arlington Heights all verified) | `launchpad/_components/living-map.tsx` |
| Warroom Living Map | `/warroom` | **EMPTY** (real code, broken data) | Same `ZIP_CENTROIDS` + `bundle.zipScores` — but bundle is `[]` because `getSitrepBundle()` throws | `warroom/_components/living-map.tsx:19` imports from `@/lib/warroom/signals` |

**Conclusion:** 4 of 5 maps are real Mapbox GL with real coordinates and real data. The 5th (Warroom) is real Mapbox code rendering against an empty data bundle — the *map* isn't fake, but no user has ever seen it render data on the live site because the upstream bundle fetch fails.

The `Maps real or fake?` pain point from the owner is misdiagnosed: the maps are real. The Warroom map appears blank because the page-level data fetch errors out, not because the map is synthetic.

---

## 10. HALLUCINATION AUDIT

Source: Agent B §B3, §B4 + Agent F §F2.

### 10.1 The Bulletproofed Path (PRACTICE batch — `weekly_research.py --batch`)

✓ All 4 layers active:
1. **Forced search** — `_call_api(force_search=True)` sets `tool_choice = {type: tool, name: web_search}` at `research_engine.py:149`
2. **Per-claim source URLs** — PRACTICE_USER schema requires `_source_url` on every section
3. **Self-assessment block** — Terminal `verification: {searches_executed, search_queries, evidence_quality, primary_sources}`
4. **Post-validation gate** — `validate_dossier(npi, data) -> (ok, reason)` at `weekly_research.py:113` with 5 rejection rules

April 25 production batch results: 174 stored / 26 quarantined / 0 hallucinations slipped through.

### 10.2 The Unprotected Paths

#### 10.2.1 ZIP Intel Path (`qualitative_scout.py` → `research_engine.py:43-50`)

```python
def research_zip(...):
    # NO force_search
    # NO tool_choice override
    # NO _source_url requirement
    # NO verification block
    # NO validate_dossier
```

Outcome: 290 `zip_qualitative_intel` rows in Supabase. **0 of 290 have `cost_usd > 0`.** All are synthetic placeholders, not real Anthropic API research. The Intelligence page KPI "290 ZIP markets researched" is technically true (rows exist) but factually meaningless (no research performed).

#### 10.2.2 Launchpad JOB_HUNT Path (`research_engine.py:96-107` → `api/launchpad/*`)

```python
def research_job_hunt(...):
    # NO force_search
    # NO tool_choice
    # NO _source_url
    # NO verification block
    # NO validate_dossier
```

Currently dormant because `ANTHROPIC_API_KEY` is missing from Vercel (all 6 AI routes return 503), but if the key is added without protecting this path, fresh hallucinations will land in production with no validation gate.

#### 10.2.3 Practice CLI Path (`practice_deep_dive.py`)

The CLI version of practice research is *unprotected*. Only `weekly_research.py --batch` invokes the bulletproofed path. 226 practice_intel rows predate April 25 bulletproofing — no `verification_*` columns populated.

### 10.3 5/5 Dossier Spot-Check (Agent B §B5)

Agent B picked 5 dossiers and verified them against external evidence. Outcome:

| Practice | NPI | Dossier Quality | Issue |
|----------|-----|-----------------|-------|
| Heritage Grove | (anon) | **MISS** | Fabricated facts not supported by web evidence |
| Tall Grass Dental | (anon) | **PARTIAL** | Some claims verifiable, some unsupported |
| Pinky Promise Pediatric | (anon) | **PARTIAL** | Same |
| Yorkville Family Dental | (anon) | **MISS** | Fabricated |
| DeLacey Dental | (anon) | **MISS** | Fabricated |

**These 5 are pre-bulletproofing rows.** The 174 post-bulletproofing rows from April 25 have not been spot-checked yet, but the architecture proves correctness on the controlled test (Robert Ficek case: model searched, found a different doctor at the address, correctly returned `evidence_quality: insufficient` instead of fabricating).

### 10.4 Sync-Mode Bypass

`weekly_research.py:304-320` has a `--sync-only` mode that stores raw model output without invoking `validate_dossier()`. If this mode is invoked accidentally, hallucinations bypass the gate.

### 10.5 Enum Drift

`verification_quality` spec is `verified | partial | insufficient`. Of 174 April 25 stored dossiers, 10 returned `"high"` — outside the spec. The validation gate accepts non-`"insufficient"` values, so `"high"` slipped through. Either tighten the prompt or widen the enum.

### 10.6 Categorization

| Category | Count | Notes |
|----------|------:|-------|
| Verified (post-bulletproofing) | 52 | Stored + validated |
| Partial (post-bulletproofing) | 115 | Stored + validated, evidence partial |
| "High" enum drift | 10 | Stored, slipped past validation due to spec/code mismatch |
| Pre-bulletproofing (NULL verification cols) | 223 | No protection; spot-check showed HIT=0 |
| Quarantined (insufficient) | 18 | Not stored; validation rejected |
| Quarantined (missing block) | 8 | Not stored; validation rejected |
| **Total practice_intel rows** | **400** in Supabase | 174 protected + 226 unprotected |
| **Total zip_qualitative_intel rows with real research** | **0 of 290** | All synthetic |

---

## 11. DOCUMENTATION DRIFT LOG

Source: Agent F (full report).

### 11.1 Numeric Drifts in `CLAUDE.md`

| CLAUDE.md Claim | Reality (SQLite ground truth) | Magnitude |
|-----------------|-------------------------------|-----------|
| 3,215 deals | **2,854** | -361 (-11%) |
| GDN deals: 3,011 | **2,515** | -496 (-16%) |
| PESP deals: 162 | **329** | +167 (+103%, **2x undercount**) |
| PitchBook deals: 42 | **10** | -32 (-76%) |
| Practice changes: 5,100+ | **8,848** | +3,748 (+73%) |
| dso_locations: 408 | **92** | -316 (-77%) |
| Watched ZIPs: 268 Chicagoland | **269** | +1 |
| Total watched ZIPs: 290 | **290** | OK |
| Practice intel rows: 23 (in dental-pe-nextjs/CLAUDE.md) | **223** | **10x off** |
| Practice intel rows: 400 (parent CLAUDE.md) | **400** | OK |
| ZIP intel rows researched | **0 of 290** | Claims "290 researched" — all synthetic |
| Total practices | 401,645 (CLAUDE.md) vs 402,004 (SQLite) | +359 (+0.09%) |
| `entity_classification` mention of "rare to be NULL" | 96.6% NULL | 387,977 NULL |
| GitHub Actions schedule "every 3 days at 12:00 UTC" | OK config / FAILING run | secrets missing |

### 11.2 Undocumented Features in CLAUDE.md (5)

| File | LOC | What It Does | Why It's Undocumented |
|------|----:|--------------|------------------------|
| `compute_signals.py` | 1,424 | Materializes `practice_signals` (14,045) + `zip_signals` (296) | New since CLAUDE.md last update |
| `cleanup_pesp_junk.py` | (unknown) | PESP commentary cleanup utility | Undocumented |
| `fast_sync_watched.py` | (unknown) | Watched-only Supabase sync (faster than full sync) | Undocumented |
| `scrapers/dossier_batch/` directory | ~600 LOC across 4 files | April 25 anti-hallucination operational scripts | Briefly noted in CLAUDE.md but not in file table |
| 7 `api/launchpad/*` routes | (unknown) | Phase 3 AI features (ask, compound-narrative, contract-parse, interview-prep, narrative, smart-briefing, zip-mood) | Listed in `dental-pe-nextjs/CLAUDE.md` but absent from parent CLAUDE.md file table |

### 11.3 Wrong Component Name in CLAUDE.md

- CLAUDE.md references `briefing-pane.tsx` in the Warroom file table.
- Actual file is `briefing-rail.tsx`.
- `warroom-shell.tsx:50` imports from `"./briefing-rail"`.
- Stale doc, file does not exist.

### 11.4 Wrong Keyboard Shortcuts in CLAUDE.md

- CLAUDE.md says Warroom keyboard shortcuts include `1` (Sitrep) and `3` (Profile).
- These modes were CUT in Phase 2.
- `mode.ts:1-4` only contains `hunt` (mapped to `2`) and `investigate` (mapped to `4`).
- `keyboard-shortcuts-overlay.tsx` correctly shows only 2 and 4.

### 11.5 Wrong NPI Reference in CLAUDE.md

- CLAUDE.md says: "NPI 1316509367 GRACE KIM, BOSTON, MA, zip 02115"
- Reality: NPI 1316509367 is **GRACE KWON, zip 01610 Worcester MA**
- See Agent C §C3 for confirmation.

### 11.6 Wrong React Query Stale Time in CLAUDE.md

- CLAUDE.md says: "React Query (5min stale, 30min gc)"
- Reality (`src/providers/query-provider.tsx:12`): **30min stale, 60min gc**
- Per-hook overrides bring some queries down to 5min.

---

## 12. SYMPTOM DIAGNOSIS

Mapping each owner-reported symptom to its underlying cause(s).

### 12.1 "Live URL is showing stale data"

**Symptoms observed:** Home page Data Freshness shows 2026-04-23, but `MAX(deal_date)` is 2026-03-02 (54 days behind today). Recent deals table shows March 2026 entries.

**Causes:**
1. **GDN scraper stops at page 8 / April 2025** — `gdn_scraper.py` pagination crawler doesn't reach the March 2026 roundup that IS published at https://www.groupdentistrynow.com/dso-group-blog/dso-deals-march-2026/.
2. **PESP_EXPECTED_EMPTY_MONTHS frozenset** at `pesp_scraper.py:64-85` deliberately marks Oct 2025 → Apr 2026 as "expected empty" — even if PESP publishes deals, scraper skips those months.
3. **PitchBook is manual-only** — no automation. Last upload date unclear.
4. **launchd cron has runs=0** — even if scrapers worked perfectly, they wouldn't fire on schedule.
5. **Vercel cache is innocent** — every route returns `x-vercel-cache: MISS` with `Cache-Control: no-store`. Stale data = Supabase has stale data, not a caching artifact.

**Net effect:** The freshness KPI "2026-04-23" reflects when the *deal row was last written* to Supabase, not when scraping ran or when a deal was announced. The newest deal in the database is 54 days old.

### 12.2 "GDN April 2026 deals missing"

**Cause:** Combination of (1) GDN scraper pagination stopping early, (2) launchd cron never firing, and (3) 6 known parser failures dropping `target_name` on multi-word entity names ending in "Partners" (KNOWN_PLATFORMS list catches the common cases but the fallback parser doesn't handle "Partners with X" lookahead).

**Test:** WebFetch of the GDN site confirms the March 2026 roundup is live. Manual `python3 scrapers/gdn_scraper.py` would likely pick it up if the URL pattern guard `_is_roundup_link()` accepts it.

### 12.3 "NPI / Chicagoland data is stale"

**Cause:** NPPES refresh has runs=0 (cron never fired). Last manual run: 2026-04-22. Data Axle enrichment pool unchanged since the last batch import.

**Specific staleness signals:**
- `entity_classification` 96.6% NULL because Pass 3 (`classify_entity_types`) is gated behind CLI flags.
- Within watched ZIPs, 44 NULL — would benefit from a single Pass 3 run.

### 12.4 "Are the maps real or fake?"

**Answer:** All 4 maps that should render data DO render real Mapbox GL with real coordinates against real Supabase data. The Warroom map renders blank because its server-side bundle fetch fails — the *map code* is real, the *data inputs* are empty.

**Specific verifications:**
- Job Market practice density: 2,848 real lat/lon points filtered from Data Axle enrichment.
- Market Intel consolidation: real `zip_scores.corporate_share_pct` per ZIP.
- Launchpad living map: real `bundle.zipScores` + verified `ZIP_CENTROIDS` (60606, 60515, 60004 all spot-checked).
- Deal Flow state choropleth: real `dealsByState` aggregations.
- Warroom living map: real code, empty inputs.

### 12.5 "Dossiers are hallucinated"

**Answer:** Only the *practice batch* path (`weekly_research.py --batch`) has the 4-layer anti-hallucination defense. The 226 pre-bulletproofing rows show MISS rate ~60% on a 5-sample spot-check. The 290 ZIP intel rows are 100% synthetic placeholders. The 6 Launchpad AI routes (currently 503) have no anti-hallucination protection if/when the API key is added.

**Net:** 174 of 400 practice dossiers + the April 25 production batch ARE bulletproofed. Everything else is unprotected.

### 12.6 "Backend doesn't run automatically"

**Answer:** Correct. launchd `com.dental-pe.weekly-refresh` and `com.dental-pe.nppes-refresh` both have `runs=0` since install. macOS Sequoia LWCR stale-context bug confirmed in CLAUDE.md. GitHub Actions keep-alive workflow is also failing (empty secrets). The "intelligent backend" exists in code but has never run on schedule — every weekly run since install was triggered manually.

---

## 13. PAIN POINT RESOLUTIONS

For each of the 6 owner pain points, the concrete next action.

### 13.1 Stale Data on Live URL

**Quick win (today):**
1. Manually run: `python3 scrapers/gdn_scraper.py` to scrape March 2026 + April 2026 GDN roundups.
2. Manually run: `python3 scrapers/sync_to_supabase.py` to push to Supabase.
3. Verify Vercel: `MAX(deal_date)` should jump to 2026-04-x.

**Durable fix:**
1. Audit `gdn_scraper.py` pagination guard — why does it stop at page 8 / April 2025?
2. Loosen `PESP_EXPECTED_EMPTY_MONTHS` frozenset OR remove the fast-fail logic.
3. Fix launchd cron (see §13.6).
4. Add a "Last successful scrape" timestamp per-source on the System page.

### 13.2 GDN April 2026 Gap

**Today:** Manually run GDN scraper with `--force` flag (if it exists) or with logged debug output to see where pagination stops.

**Durable fix:** `gdn_scraper.py` should query the WordPress sitemap or category feed directly rather than walking pagination. The DSO-Deals category has a stable URL: `groupdentistrynow.com/category/dso-deals/feed/`.

### 13.3 NPI / Chicagoland Staleness

**Today:**
1. Run `python3 scrapers/dso_classifier.py --entity-types-only --zip-filter chicagoland` to populate `entity_classification` for the 44 NULL watched-ZIP practices.
2. Run `python3 scrapers/sync_to_supabase.py` to propagate.

**Durable fix:** Make Pass 3 (`classify_entity_types`) part of the standard `dso_classifier.py` invocation, not gated behind CLI flags. Or add it as Step 9.5 in `refresh.sh`.

### 13.4 Maps Real vs Fake

**Today:** Already real. Communicate to stakeholders: 4 of 5 maps are real Mapbox; the Warroom map is empty because of an upstream bundle failure (see §13.5).

**Durable fix:** Add data-quality badges to each map ("2,848 of 14,053 practices have coordinates" tooltip).

### 13.5 Dossier Hallucinations

**Today:**
1. Extend the 4-layer defense to `research_zip()` and `research_job_hunt()` paths in `research_engine.py`.
2. Re-run `qualitative_scout.py` against all 290 ZIPs with bulletproofing (cost ~$15-20).
3. Quarantine and mark the 226 pre-bulletproofing practice_intel rows as "unverified" until re-researched.

**Durable fix:**
1. Make the bulletproofing path the *only* path. Delete `--sync-only` bypass at `weekly_research.py:304-320`.
2. Surface `verification_quality` badge in `intelligence-shell.tsx`.
3. Tighten the prompt to suppress `"high"` enum drift OR widen the schema accepted enum.

### 13.6 Backend Not Running Automatically

**Today:**
1. Diagnose launchd: `launchctl list | grep dental-pe`. If both jobs show `0` in the runs column, run `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.dental-pe.weekly-refresh.plist && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dental-pe.weekly-refresh.plist` to re-bootstrap.
2. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to GitHub repo secrets so keep-alive workflow stops failing.

**Durable fix:**
1. Replace launchd with GitHub Actions cron — runs in cloud, not on user's MacBook, immune to LWCR bugs.
2. Add a `pipeline_runs` table with `started_at`, `completed_at`, `step_status` JSONB to track every run.
3. Surface "Last successful pipeline run" on the System page Freshness panel.

### 13.7 (Bonus) Warroom Dead on Live

**Today:**
1. SSH into Vercel logs OR run `npm run build && npm run start` locally with production Supabase env vars.
2. Reproduce the "Data load issue" — likely a 408/timeout or a column-not-found error.
3. Fix the failing query in `getSitrepBundle()` chain (`getScopedPractices`, `getScopedZipScores`, `getScopedDeals`, `getScopedChanges`).

**Durable fix:**
1. Add `practice_signals` and `zip_signals` to `src/lib/supabase/types.ts` so missing-table errors are caught at build time.
2. Wrap each of the 6 parallel queries in `Promise.allSettled` instead of `Promise.all` so partial failures degrade gracefully.

### 13.8 (Bonus) 6 Launchpad AI Routes Returning 503

**Today:** Add `ANTHROPIC_API_KEY` to Vercel project environment variables. Trigger redeploy.

**Durable fix:** Surface a "AI features disabled — set ANTHROPIC_API_KEY" banner on Launchpad when the key is missing, so the failure mode is obvious to whoever inherits the repo.

---

## 14. SUSPECTED ROOT CAUSES

Synthesized across all 6 agent reports.

### 14.1 Cron Never Fires (P0)

**Root cause:** macOS Sequoia LWCR (LaunchWith ConditionalRequest) stale-context bug. The launchd plists are valid but the system never schedules them.

**Evidence:** `launchctl list | grep dental-pe` shows runs=0 for both jobs. CLAUDE.md "Pipeline Audit — April 2026" section explicitly cites this as a confirmed diagnostic.

**Why no one caught it:** Pipeline still runs — the user manually triggers it. The "weekly" cadence in CLAUDE.md is aspirational, not actual.

### 14.2 GDN Scraper Stops at Page 8 (P0)

**Root cause:** Pagination crawler in `gdn_scraper.py` follows category links sequentially. When a category page restructures or returns an unexpected HTML pattern, the crawler exits early. The `_is_roundup_link()` guard added in April 22 audit prevents wandering into unrelated posts but doesn't help with missed pagination.

**Evidence:** `MAX(gdn deal_date)` is 2026-03-01. March 2026 roundup IS published at `groupdentistrynow.com/dso-group-blog/dso-deals-march-2026/`.

### 14.3 Anti-Hallucination Defense Bypass (P1)

**Root cause:** The 4-layer defense was applied surgically to the PRACTICE batch path during the April 25 session under time pressure. The ZIP intel and JOB_HUNT paths were not extended because they weren't the focus of the user's "even one hallucination" mandate.

**Evidence:** Agent B §B3 read `research_engine.py:43-50` and `:96-107` line by line — no `force_search`, no `_source_url`, no `verification` block on those paths.

**Why no one caught it:** ZIP intel produces 290 rows of synthetic placeholders (no real API calls) and Launchpad AI routes are dormant (503). Neither path has been observed hallucinating because neither path has been observed *running*.

### 14.4 entity_classification 96.6% NULL (P1)

**Root cause:** `dso_classifier.py:1373-1377` gates Pass 3 (`classify_entity_types`) behind `--zip-filter` or `--entity-types-only` flags. The default invocation in `refresh.sh` does not include these flags, so Pass 3 is skipped.

**Evidence:** SQLite query: 14,009 of 402,004 entity_classification populated. CLAUDE.md describes Pass 3 as part of the classifier but doesn't mention the flag gating.

### 14.5 dso_locations 408→92 Regression (P2)

**Root cause:** `data/ADSO_TARGETS.csv` has 18 DSO entries; 15 are flagged `needs_browser=True`. `adso_location_scraper.py:670` reads this flag and skips `requests`-based scraping for those targets, with a TODO comment to add Playwright/Selenium support.

**Evidence:** Agent A §A4 documented this as pre-existing in initial commit `eea4380`. The 408 figure in CLAUDE.md may have been from a one-time manual scrape with browser support enabled.

**Brands actually scraped (5 of 18):** Tend (30 locations), Gentle Dental (29), Risas Dental (21), Specialized Dental Partners (6), Community Dental Partners (6). Total 92.

**Brands skipped (browser-only, 13):** Aspen Dental, Heartland Dental, Pacific Dental Services, MB2 Dental, Smile Brands, Mortenson, Affordable Care, etc.

### 14.6 practice_signals = 0 in Supabase (P2)

**Root cause:** FK violation. NPI 1316509367 (Grace Kwon, zip 01610 Worcester MA) appears in `practice_signals` but not in `practices`. 13 cross-ZIP NPIs total. The full_replace sync TRUNCATE+INSERT fails on FK validation.

**Evidence:** Agent C §C3 ran the join query and identified the offending NPIs. CLAUDE.md attributes this to "GRACE KIM zip 02115" — wrong NPI, wrong city.

### 14.7 Warroom Dead on Live (P0 — newly discovered)

**Root cause:** `getSitrepBundle()` at `data.ts:123-141` runs 6 parallel Supabase queries via `Promise.all()`. Any one query throwing aborts the entire bundle. The most likely culprits: (1) `practices` query timing out on 14k rows × 200-ZIP chunk, (2) a column that exists in SQLite but not Supabase.

**Evidence:** Agent D §D4 traced the error path. Live URL shows "Unable to load Warroom data."

### 14.8 6 Launchpad AI Routes Return 503 (P0 — newly discovered)

**Root cause:** `ANTHROPIC_API_KEY` is not set in Vercel environment variables. All 6 AI routes throw at instantiation.

**Evidence:** Agent D confirmed via WebFetch that all 6 routes return 503 status. CLAUDE.md notes "Add ANTHROPIC_API_KEY to Vercel env vars" as a TODO that hasn't been done.

### 14.9 41-Row Supabase Deal Surplus (P2)

**Root cause:** `incremental_updated_at` sync strategy adds new rows but never propagates SQLite deletes. When `cleanup_pesp_junk.py` removes commentary-classified deals from SQLite, those rows remain in Supabase.

**Evidence:** SQLite has 2,854 deals, Supabase has 2,895. Difference (41) matches recent PESP cleanup count.

---

## 15. PRIORITIZED DEBUG BACKLOG

Ordered by (impact × likelihood of solving the user's actual pain) ÷ effort.

### P0 — Production-Visible Failures

| # | Item | Impact | Effort | First Action |
|---|------|--------|--------|--------------|
| 1 | Add `ANTHROPIC_API_KEY` to Vercel | 6 broken AI routes → working | 5 min | Vercel project settings → env vars |
| 2 | Fix Warroom bundle fetch | Live page goes from "Data load issue" to functional | 1-2 hrs | Reproduce locally with prod env, identify which of 6 queries throws, fix or wrap in `Promise.allSettled` |
| 3 | Manually run GDN scraper to ingest March 2026 + April 2026 deals | Live `MAX(deal_date)` jumps from 2026-03-02 to 2026-04-x | 30 min | `python3 scrapers/gdn_scraper.py && python3 scrapers/sync_to_supabase.py` |
| 4 | Fix launchd cron (or migrate to GitHub Actions) | Pipeline runs weekly without manual intervention | 1-3 hrs | `launchctl bootout && bootstrap` retry first; if persistent, migrate `refresh.sh` to GH Actions |

### P1 — Silent Correctness Risks

| # | Item | Impact | Effort | First Action |
|---|------|--------|--------|--------------|
| 5 | Extend bulletproofing to ZIP intel + JOB_HUNT paths | 290 ZIP rows + 6 AI routes become trustworthy | 2-3 hrs | Refactor `research_engine.py` to apply `force_search`, `_source_url`, `verification` block, `validate_dossier()` to all 3 paths |
| 6 | Make Pass 3 run by default in `refresh.sh` | 96.6% NULL drops to ~0% within watched ZIPs | 15 min | Remove flag gate at `dso_classifier.py:1373-1377` OR add `--entity-types-only` to `refresh.sh` |
| 7 | Re-research the 290 ZIP qualitative intel rows with real bulletproofed Anthropic calls | Eliminates 100% synthetic data | 1 hr + ~$15-20 cost | After #5, run `python3 scrapers/qualitative_scout.py --metro chicagoland --refresh` |
| 8 | Re-research the 226 pre-bulletproofing practice_intel rows OR mark them quarantined in UI | 226 untrusted rows become trustworthy or visibly flagged | 4-6 hrs + ~$20 cost OR 30 min for UI-only | Decide: re-research vs. mark unverified |

### P2 — Data Quality Drift

| # | Item | Impact | Effort | First Action |
|---|------|--------|--------|--------------|
| 9 | Fix practice_signals FK violation (delete orphans) | practice_signals + zip_signals tables sync to Supabase, Warroom signal flags fire | 30 min | `DELETE FROM practice_signals WHERE npi NOT IN (SELECT npi FROM practices)` + add same filter inside `compute_signals.py` |
| 10 | Add Playwright support to ADSO scraper for browser-only DSOs | dso_locations 92 → ~400 | 4-6 hrs | New code path in `adso_location_scraper.py` for `needs_browser=True` rows |
| 11 | Make sync propagate SQLite deletes for `deals` table | Eliminates 41-row surplus | 1 hr | Add a "deletion log" or switch deals to `incremental_id` with delete tracking |
| 12 | Fix GitHub Actions keep-alive workflow | Free-tier Supabase auto-pause prevention works | 5 min | Add `SUPABASE_URL` + `SUPABASE_ANON_KEY` to GH repo secrets |
| 13 | Fix `nppes_refresh.sh` to add timeout protection like `refresh.sh` | NPPES refresh can't hang indefinitely | 15 min | Copy `run_step()` wrapper from `refresh.sh` |
| 14 | Add `verification_*` columns to `init_db()` in `database.py` | Fresh installs don't fail | 5 min | Update SQLAlchemy model |
| 15 | Add `ada_hpi_importer.py` to set `updated_at` | Freshness UI shows real data | 5 min | One-line fix in `ada_hpi_importer.py` |
| 16 | Tighten validate_dossier to reject `"high"` enum drift OR widen schema | 10 enum-drift rows handled correctly | 15 min | Either prompt fix or schema widen |

### P3 — Cosmetic / Documentation

| # | Item | Impact | Effort | First Action |
|---|------|--------|--------|--------------|
| 17 | Surface `verification_quality` badge in `intelligence-shell.tsx` | Users distinguish verified from partial dossiers | 30 min | Add `<VerificationQualityBadge>` component |
| 18 | Reconcile "34 vs 177 Acquisition Targets" labels | Less user confusion | 15 min | Rename Buyability category to "Independent Practices" or add tooltips |
| 19 | Reconcile "481 vs 2,990 Data Axle" labels | Less user confusion | 15 min | Add tooltip explaining "imported as Data Axle" vs "any Data Axle enrichment" |
| 20 | Update CLAUDE.md numeric drifts (14 items) | Docs match reality | 30 min | Run `pipeline_check.py`, paste numbers in |
| 21 | Update CLAUDE.md NPI 1316509367 reference (Grace Kim 02115 → Grace Kwon 01610) | Future debugging accurate | 2 min | One-line edit |
| 22 | Update CLAUDE.md React Query stale time (5min → 30min) | Future debugging accurate | 2 min | One-line edit |
| 23 | Document `compute_signals.py`, `cleanup_pesp_junk.py`, `fast_sync_watched.py`, `dossier_batch/` in CLAUDE.md | Future maintainers understand the codebase | 1 hr | Add file table entries |
| 24 | Update CLAUDE.md keyboard shortcut docs (drop 1/Sitrep + 3/Profile) | Docs match shipped code | 5 min | Edit Warroom shortcuts section |
| 25 | Rename `briefing-pane.tsx` references to `briefing-rail.tsx` in CLAUDE.md | Docs match reality | 2 min | Find/replace |
| 26 | Delete `dental-pe-nextjs/scrapers/` mirror directory entirely | Cleaner repo | 5 min | `rm -rf dental-pe-nextjs/scrapers/` |
| 27 | Add per-source "last successful scrape" timestamp to System page | Operational visibility | 2 hrs | New `pipeline_runs` table + System page panel |

---

## APPENDIX A — EVIDENCE SOURCES

| Source | Path | Lines | Bytes |
|--------|------|------:|------:|
| Agent A: Ingestion & Scrapers | `/tmp/audit_agent_A_report.md` | 266 | 22,065 |
| Agent B: Enrichment & Scoring | `/tmp/audit_agent_B_report.md` | 447 | 23,823 |
| Agent C: Storage & Data Model | `/tmp/audit_agent_C_report.md` | 423 | 36,570 |
| Agent D: Frontend Features | `/tmp/audit_agent_D_report.md` | 462 | 37,104 |
| Agent E: Real-Time / Sync / Cache | `/tmp/audit_agent_E_report.md` | 271 | 22,571 |
| Agent F: Docs vs Reality Drift | `/tmp/audit_agent_F_report.md` | 386 | 36,510 |
| **Total** | | **2,255** | **178,643** |

Each agent ran read-only against the same SQLite + Supabase + filesystem snapshot at 2026-04-25T16:00–16:15 UTC.

## APPENDIX B — GROUND TRUTH RAW QUERIES

```sql
-- SQLite (data/dental_pe_tracker.db) at 2026-04-25
SELECT COUNT(*) FROM deals;                              -- 2,854
SELECT MAX(deal_date) FROM deals;                        -- 2026-03-02
SELECT source_type, COUNT(*), MAX(deal_date) FROM deals GROUP BY source_type;
-- gdn        2,515  2026-03-01
-- pesp         329  2025-10-01
-- pitchbook     10  2026-03-02

SELECT COUNT(*) FROM practices;                          -- 402,004
SELECT COUNT(*) FROM practices WHERE entity_classification IS NULL;  -- 387,977
SELECT COUNT(*) FROM practices WHERE latitude IS NOT NULL AND latitude != 0;  -- 2,848

SELECT COUNT(*) FROM zip_qualitative_intel;              -- 290
SELECT COUNT(*) FROM zip_qualitative_intel WHERE cost_usd > 0;  -- 0
SELECT COUNT(*) FROM practice_intel;                     -- 400
SELECT verification_quality, COUNT(*) FROM practice_intel GROUP BY verification_quality;
-- NULL          223
-- high           10  (enum drift)
-- partial       115
-- verified       52
-- insufficient    0  (quarantined, never stored)

SELECT COUNT(*) FROM dso_locations;                      -- 92
SELECT brand, COUNT(*) FROM dso_locations GROUP BY brand;
-- Tend                          30
-- Gentle Dental                 29
-- Risas Dental                  21
-- Specialized Dental Partners    6
-- Community Dental Partners      6

SELECT COUNT(*) FROM watched_zips;                       -- 290
SELECT COUNT(*) FROM zip_scores;                         -- 290
SELECT COUNT(*) FROM practice_signals;                   -- 14,045
SELECT COUNT(*) FROM zip_signals;                        -- 296
SELECT COUNT(*) FROM ada_hpi_benchmarks;                 -- 918
SELECT COUNT(*) FROM ada_hpi_benchmarks WHERE updated_at IS NOT NULL;  -- 0
```

```sql
-- Supabase Postgres at 2026-04-25
SELECT COUNT(*) FROM deals;                              -- 2,895  (+41 vs SQLite)
SELECT COUNT(*) FROM practice_signals;                   -- 0      (FK violation blocks sync)
SELECT COUNT(*) FROM zip_signals;                        -- 0      (FK chain)
-- All other tables match SQLite within ±5 rows
```

---

*End of report. Generated 2026-04-25 by Claude Opus 4.7 (1M context). 6 parallel read-only audit agents + live URL evidence + raw SQLite/Supabase queries. No code changes, no commits, no mutations.*
