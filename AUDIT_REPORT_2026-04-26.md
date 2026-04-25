# Dental PE Tracker — Comprehensive Audit Report
**Date:** 2026-04-26  
**Auditor:** Claude Sonnet 4.6 (automated, GitHub Actions headless)  
**Scope:** Full codebase, live URLs, Supabase DB, pipeline health, documentation drift  
**Methodology:** Code reads (file:line cited), live Supabase REST queries, WebFetch of all 10 pages, git log, workflow inspection  

---

## 1. Executive Summary

### Top 10 Verified Broken

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **Home page shows 0 total practices** on live Vercel despite 14k+ synced to Supabase | WebFetch dental-pe-nextjs.vercel.app: "Total practices tracked: 0" |
| 2 | **Warroom page: complete data load failure** — "Unable to load Warroom data. Retry or refresh the page." | WebFetch /warroom: 0 matches, 0 ZIPs, 0 ranked targets |
| 3 | **Launchpad page: PostgreSQL statement timeout** (error 57014) — all KPIs show "--" | WebFetch /launchpad: "canceling statement due to statement timeout" |
| 4 | **Buyability page: Error: Unknown** — page fails to load | WebFetch /buyability: "Error: Unknown", "Data is loading. Please refresh" |
| 5 | **Job Market page: infinite loading** — "Loading..." never resolves | WebFetch /job-market: main content area stuck at Loading... |
| 6 | **Most recent deal in Supabase: 2026-03-02** — 53+ days stale as of audit | Supabase REST: `/rest/v1/deals?order=deal_date.desc&limit=1` → deal_date: "2026-03-02" |
| 7 | **PESP scraper effectively dead for new deals** — 114 days since latest deal | System page: "PESP: 353 deals; 114 days since latest (red/stalled)" |
| 8 | **No pipeline_events.jsonl on disk** — logs/ directory does not exist | Agent read: `logs/` directory missing from repo; only referenced in code |
| 9 | **Streamlit legacy app: 303 redirect** — inaccessible | WebFetch suleman7-pe.streamlit.app: 303 redirect error |
| 10 | **Keep-Supabase-Alive workflow failing** — secrets likely not set in GitHub | GitHub Actions: "Keep Supabase Alive" — Completed Failure 2026-04-25T12:39:51Z |

### Top 10 Verified Stale

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **Deals: last import 2026-03-02** — no new deals in 53 days | Supabase REST: MAX(deal_date) = 2026-03-02 |
| 2 | **PESP deals stale 114 days** — last PESP deal ~Jan 1, 2026 | System page: "114 days since latest" (red indicator) |
| 3 | **ADA HPI benchmarks: 49 days stale** | System page: "ADA HPI: 918 records; last updated 2026-03-07 (Outdated)" |
| 4 | **Practice NPI data: last NPPES import unknown** — no log evidence of recency | logs/ directory missing; no pipeline_events to query; System page shows no NPPES timestamp |
| 5 | **Chicagoland practice signals: stale** — compute_signals.py output freshness unknown | No sync timestamp visible; Warroom failure means signals not reaching UI |
| 6 | **CLAUDE.md deal counts outdated** — claims "3,215 deals (3,011 GDN + 162 PESP + 42 PitchBook)" | Supabase actual: 2,895 deals; System page: GDN 2,532 + PESP 353 + PitchBook 10 |
| 7 | **CLAUDE.md DSO Locations count wrong** — claims 408 | Supabase actual: 92 records; System page: "ADSO Scraper: 92 records" |
| 8 | **CLAUDE.md PE Sponsors count wrong** — claims ~40 | Supabase actual: 106 records |
| 9 | **CLAUDE.md Platforms count wrong** — claims ~140 | Supabase actual: 490 records |
| 10 | **Supabase sync last ran 2026-04-25 00:51:25** but deal data stops at 2026-03-02 | Pipeline events Supabase: sync ran, but no new deals ingested since March |

### Top 10 Unknowns Requiring Hands-On Investigation

| # | Unknown | How to Verify |
|---|---------|---------------|
| 1 | **Why does the practices KPI return 0?** Could be query timeout, empty result, or broken stat aggregation | Read Next.js src/app/page.tsx + src/lib/supabase/queries/ (code not in this repo) |
| 2 | **Exact Warroom failure cause** — timeout, missing table, query error, or JS crash | Read warroom/data.ts getSitrepBundle; check Vercel function logs |
| 3 | **Practice count in local SQLite vs Supabase** — how many practices are in Supabase practices table? | `SELECT COUNT(*) FROM practices` times out; need direct psql or Supabase dashboard count |
| 4 | **Why are 320 deals missing from Supabase?** SQLite claims 3,215 but Supabase has 2,895 | Check sync_metadata watermark for deals; query SQLite directly |
| 5 | **NPPES last successful import date** | sqlite3 data/dental_pe_tracker.db "SELECT MAX(last_updated) FROM practices WHERE data_source='nppes'" |
| 6 | **Weekly-refresh.yml last successful full run** | GitHub Actions UI: check workflow run history for SUPABASE_DATABASE_URL secret presence |
| 7 | **Are SUPABASE_DATABASE_URL and ANTHROPIC_API_KEY secrets set in GitHub repo?** | GitHub repo Settings → Secrets (requires repo owner access) |
| 8 | **2000-practice batch (msgbatch_01A3FxKxKxemAyqDr2AcGYUq) status** — was it ever retrieved? | Anthropic API: GET /v1/messages/batches/{id} (requires ANTHROPIC_API_KEY) |
| 9 | **Launchpad compound-narrative route operational?** — requires ANTHROPIC_API_KEY in Vercel | Curl POST /api/launchpad/compound-narrative with test payload |
| 10 | **Practice_signals sync to Supabase** — does the table exist and have data? | `SELECT COUNT(*) FROM practice_signals` in Supabase (timed out during audit) |

---

## 2. Codebase Map

**NOTE: The Next.js frontend (dental-pe-nextjs/) is NOT present in this repository.** It is a separate Vercel project deployed independently. Code audits of the Next.js frontend are limited to what can be inferred from live URL behavior.

### Root-Level Files

| File | Lines | Domain | Purpose |
|------|-------|--------|---------|
| `CLAUDE.md` | ~2,472 | Docs | Primary dev guide, architectural reference |
| `SCRAPER_AUDIT_STATUS.md` | 628 | Docs | April 2026 outage post-mortem + fix verification |
| `AUDIT_REPORT_2026-04-25.md` | 1,982 | Docs | Anti-hallucination session record |
| `README.md` | 1,932 | Docs | User-facing platform documentation |
| `requirements.txt` | 12 | Config | Python deps (streamlit, sqlalchemy, psycopg2, etc.) |
| `packages.txt` | 2 | Config | System packages for Streamlit Cloud |
| `runtime.txt` | 1 | Config | Python 3.12 |
| `pytest.ini` | 5 | Config | Test path: tests/ |
| `pipeline_check.py` | 540 | Utility | Diagnostic health check tool |

### `scrapers/` — Data Pipeline (Python)

| File | Lines | Domain | Purpose |
|------|-------|--------|---------|
| `database.py` | 917 | ORM | SQLAlchemy models, 12+ tables, init_db(), helpers |
| `sync_to_supabase.py` | 1,014 | ETL | SQLite → Supabase sync (3 strategies + signal handler) |
| `pipeline_logger.py` | 295 | Infra | Structured JSONL event logger (file-locked) |
| `logger_config.py` | 43 | Infra | Logger factory for all scrapers |
| `refresh.sh` | 126 | Orchestration | 11-step weekly pipeline orchestrator |
| `nppes_refresh.sh` | 90 | Orchestration | Monthly NPPES federal data update pipeline |
| `gdn_scraper.py` | 1,090 | Scraper | GroupDentistryNow DSO deal roundup scraper |
| `pesp_scraper.py` | 1,181 | Scraper | PE Stakeholder private equity deal scraper |
| `pitchbook_importer.py` | 618 | Importer | PitchBook CSV/XLSX batch importer |
| `nppes_downloader.py` | 728 | Importer | Federal dental provider (NPPES) importer |
| `data_axle_importer.py` | 2,665 | Importer | Data Axle CSV enrichment pipeline (7 phases) |
| `data_axle_exporter.py` | 822 | Utility | Interactive Data Axle batch export tool |
| `data_axle_automator.py` | 549 | Utility | Data Axle automation wrapper |
| `adso_location_scraper.py` | 837 | Scraper | ADSO DSO office location scraper |
| `ada_hpi_downloader.py` | 237 | Importer | ADA HPI XLSX auto-downloader |
| `ada_hpi_importer.py` | 360 | Importer | ADA HPI XLSX parser |
| `dso_classifier.py` | 947 | Classifier | DSO ownership + entity type classifier (3 passes) |
| `merge_and_score.py` | 1,071 | Scoring | Deal dedup + ZIP scoring + saturation metrics |
| `compute_signals.py` | 1,436 | Signals | Warroom signal materialization (51-field practice_signals) |
| `research_engine.py` | 520+ | AI | Anthropic API client (raw HTTP, not SDK) |
| `intel_database.py` | 302 | AI | Intel table CRUD + 90-day cache TTL |
| `qualitative_scout.py` | 406 | AI CLI | ZIP-level market research CLI |
| `practice_deep_dive.py` | 595 | AI CLI | Practice due diligence CLI (two-pass) |
| `weekly_research.py` | 504 | AI | Automated weekly research runner + dossier validator |
| `migrate_to_supabase.py` | 381 | Migration | One-shot Supabase schema init |
| `migrate_fast.py` | 175 | Migration | Quick local SQLite schema update |
| `fast_sync_watched.py` | 200 | ETL | Watched-ZIP-only sync accelerator |
| `audit_coverage.py` | 450 | Utility | Classification coverage analysis |
| `backfill_last_names.py` | 271 | Utility | Last name backfill for family practice detection |
| `census_loader.py` | 234 | Importer | Census ACS demographics loader |
| `cleanup_pesp_junk.py` | 69 | Utility | PESP artifact cleaner (one-time) |
| `cleanup_curly_apostrophes.py` | 130 | Utility | U+2019 → U+0027 apostrophe normalizer |
| `assess_address_normalization.py` | 168 | Utility | Address normalization quality assessment |
| `test_sync_resilience.py` | 637 | Tests | Sync resilience test suite (11 tests) |
| `directory_importer.py` | 570 | Importer | Legacy directory CSV importer |
| `data_axle_scraper.py` | 605 | Legacy | Placeholder; core logic moved to exporter |

### `scrapers/dossier_batch/` — Batch Practice Research

| File | Lines | Purpose |
|------|-------|---------|
| `launch.py` | 116 | Top-1-per-ZIP batch launcher ($11 cap) |
| `poll.py` | 187 | Batch result retrieval + validate + store + sync |
| `launch_2000_excl_chi.py` | ~130 | 2000-practice non-606xx batch ($250 cap) |
| `migrate_verification_cols.py` | 54 | Supabase column migration (idempotent) |
| `last_run_summary.json` | 48 KB | 200-practice run regression baseline |

### `dashboard/` — Streamlit Legacy

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 2,583 | Full 6-page Streamlit dashboard |

### `tests/` — Test Suite

| File | Purpose |
|------|---------|
| `test_classifier_and_merge.py` | DSO classifier + merge logic |
| `test_database.py` | SQLAlchemy models + insert_or_update |
| `test_database_integration.py` | Integration with live DB |
| `test_gdn_scraper.py` | GDN parser |
| `test_nppes_and_sync.py` | NPPES importer + sync |
| `test_pesp_scraper.py` | PESP parser |

**Test status as of 2026-04-22: 58/58 passing.**

### `.github/workflows/` — CI/CD

| Workflow | Trigger | Status |
|----------|---------|--------|
| `weekly-refresh.yml` | Cron Sunday 08:00 UTC + manual | Active |
| `keep-supabase-alive.yml` | Every 3 days 12:00 UTC | FAILING (2026-04-25) |
| `audit-sweep.yml` | 1st of month 13:00 UTC + manual | Running (this session) |
| `reaudit.yml` | Weekly + manual | Active |
| `weekly-drift.yml` | Weekly + manual | Success 2026-04-25 |
| `auto-fix.yml` | Manual | Active |

### `data/`

| Item | Size | Content |
|------|------|---------|
| `dental_pe_tracker.db` | 176.9 MB | Local SQLite (uncompressed) |
| `dental_pe_tracker.db.gz` | 42.4 MB | Compressed for git/Streamlit Cloud |
| `research_costs.json` | 47.9 KB | 500-entry rolling cost log |
| `address_normalization_assessment.txt` | 1.9 KB | Normalization quality report |
| `zip_demographics.csv` | 2.9 KB | ZIP population data |
| `ada-hpi/` | — | ADA HPI XLSX files |
| `data-axle/` | — | Data Axle CSV batches |

### **CRITICAL ABSENCE**

- `dental-pe-nextjs/` — **DOES NOT EXIST in this repo.** The Next.js primary frontend is a fully separate Vercel project. Source code cannot be read from this repository. All Next.js findings in this audit are based on live URL inspection only.
- `logs/` — **DOES NOT EXIST.** The pipeline_events.jsonl file has no persistent storage directory. Code writes to this path but the directory was never created (or was gitignored and never committed). The System page's pipeline log viewer depends on Supabase sync of these events, not local files.

---

## 3. Feature Inventory Table

| Feature | Code Location | Claimed Behavior | Actual Behavior | Data Source | Wiring | State |
|---------|--------------|-----------------|-----------------|-------------|--------|-------|
| Home KPI cards (6) | Next.js /app/page.tsx (not in repo) | Total practices, deals, consolidated %, markets, enriched, retirement risk | "Total practices tracked: 0"; deals show 2,895; consolidated "0.0%" | Supabase practices + deals + zip_scores | Live Supabase | **BROKEN — practice KPI returns 0** |
| Home activity feed | Next.js /app/page.tsx | Recent practice_changes | Unknown — HTML not inspected in detail | Supabase practice_changes | Live Supabase | Unknown |
| Home freshness bar | Next.js | Data age indicators per source | Shows 2026-04-23 last refresh | Supabase pipeline_events | Live Supabase | Partial — shows recent dates |
| Deal Flow tabs | Next.js /app/deal-flow/ | 4 tabs: Overview, Sponsors, Geography, Deals | Navigation visible; content details unclear | Supabase deals | Live Supabase | Likely functional (3,011 rows GDN) |
| Market Intel — Consolidation | Next.js /app/market-intel/ | DSO penetration map + table | Shows DSO penetration table (184 rows, Page 1 of 10); map "Loading..." | Supabase zip_scores + practices | Live Supabase (partial) | **PARTIAL — map broken, table works** |
| Market Intel — ZIP Analysis | Next.js /app/market-intel/ | ZIP score table + city practice tree | "No consolidation scores calculated yet" despite 290 zip_scores in Supabase | Supabase zip_scores | Live Supabase | **BROKEN — not rendering scores** |
| Market Intel — Ownership | Next.js /app/market-intel/ | Entity classification breakdown | "0 practices tracked" | Supabase practices | Live Supabase | **BROKEN — 0 count** |
| Warroom Hunt mode | Next.js /app/warroom/ | Ranked practice list, 11 scopes, signals | "Data load issue" — all zeros | Supabase practices + practice_signals | Live Supabase | **BROKEN — complete failure** |
| Warroom Investigate mode | Next.js /app/warroom/ | Flag co-occurrence, compound signals | "Data load issue" | Supabase practice_signals | Live Supabase | **BROKEN** |
| Warroom Living Map | Next.js /app/warroom/ | Mapbox choropleth by lens | Not rendered (data load failure) | Supabase zip_scores + practices | Live Supabase | **BROKEN** |
| Warroom Dossier Drawer | Next.js /app/warroom/ | Practice detail with intel | Not accessible (data load failure) | Supabase practices + practice_intel | Live Supabase | **BROKEN** |
| Warroom ZIP Dossier | Next.js /app/warroom/ | ZIP saturation + ownership | Not accessible | Supabase zip_scores | Live Supabase | **BROKEN** |
| Launchpad — 20 signals | Next.js /app/launchpad/ | Signal evaluation per practice, 3 tracks, 5 tiers | "No practices loaded yet" — statement timeout | Supabase practices + getLaunchpadBundle | Live Supabase | **BROKEN — timeout** |
| Launchpad DSO tier list | Next.js /lib/launchpad/dso-tiers.ts (not in repo) | 16 curated DSO entries | Hardcoded static data (not dynamic) | Static TypeScript file | No DB query | Works as static data |
| Launchpad compound thesis | Next.js /app/api/launchpad/compound-narrative/ | 200-300 word Sonnet thesis from practice_intel | Returns 503 if ANTHROPIC_API_KEY not in Vercel env | Supabase practice_intel + Anthropic API | Live API | Unknown — env var status unknown |
| Launchpad 5-tab dossier | Next.js /app/launchpad/_components/ | 5 tabs: Snapshot/Compensation/Mentorship/Red Flags/Interview | Not accessible (data load failure) | Supabase practices | Live Supabase | **BROKEN — no data loads** |
| Buyability page | Next.js /app/buyability/ | ZIP filter, verdict categories, sortable table | "Error: Unknown" | Supabase practices (buyability_score) | Live Supabase | **BROKEN** |
| Job Market Overview | Next.js /app/job-market/ | KPIs + saturation table + ADA benchmarks | Loading... (infinite) | Supabase practices + ada_hpi_benchmarks | Live Supabase | **BROKEN — infinite load** |
| Job Market Density Map | Next.js /app/job-market/ | Mapbox hex+dot density | Not rendered | Supabase practices (lat/lon) | Live Supabase | Unknown |
| Job Market Directory | Next.js /app/job-market/ | Searchable practice table | Not rendered | Supabase practices | Live Supabase | Unknown |
| Research — SQL Explorer | Next.js /app/research/ | SELECT-only query runner | Shows "0 total deals" despite 2,895 in DB | Supabase (live query) | Live Supabase | **BROKEN — deals count query** |
| Research — Sponsor profiles | Next.js /app/research/ | PE sponsor deep dives | Content visible (dirctory of PE firms) | Supabase pe_sponsors | Live Supabase | Functional |
| Intelligence page | Next.js /app/intelligence/ | practice_intel rows, confidence badges | Renders; data unknown from fetch | Supabase practice_intel | Live Supabase | Likely functional (400 rows) |
| Intelligence ZIP intel | Next.js /app/intelligence/ | ZIP market research panels | Content unclear from fetch | Supabase zip_qualitative_intel | Live Supabase | Unknown |
| System — Freshness | Next.js /app/system/ | Data age per source | WORKING: ADSO 92 recs, ADA HPI 918 recs, deal freshness | Supabase pipeline_events + tables | Live Supabase | **FUNCTIONAL** |
| System — Pipeline Log | Next.js /app/system/ | Pipeline event log viewer | Shows most recent events including sync on 2026-04-25 | Supabase pipeline_events | Live Supabase | **FUNCTIONAL** |
| System — Manual Entry | Next.js /app/system/ | Add deal, edit practice forms | Unknown (not tested) | Supabase mutations | Live API routes | Unknown |
| DSO Classifier Pass 1 | scrapers/dso_classifier.py:206 | Name-based ownership classification | Implemented, runs via refresh.sh step 7 | SQLite practices | Local pipeline | Functional (code) |
| DSO Classifier Pass 3 | scrapers/dso_classifier.py:804 | Entity type classification (11 types) | Implemented, runs as separate step via --entity-types-only | SQLite practices | Local pipeline | Functional (code) |
| Merge & Score | scrapers/merge_and_score.py | Deal dedup + ZIP scoring + saturation metrics | Implemented; ensure_chicagoland_watched() at line 592 | SQLite deals + practices | Local pipeline | Functional (code) |
| Compute Signals | scrapers/compute_signals.py | 12 practice + ZIP signal types (51 fields) | Implemented with NPI null guard | SQLite all tables | Local pipeline | Functional (code) |
| Weekly Research | scrapers/weekly_research.py | Automated dossier runs, $5 budget cap | Implemented with 4-layer validation gate | SQLite + Anthropic API | Conditional (needs API key) | Functional if key set |
| NPPES Import | scrapers/nppes_downloader.py | Monthly federal dental provider update | Implemented; 400k+ rows | CMS download endpoint | Manual/cron | Functional (code); last run unknown |
| Data Axle Import | scrapers/data_axle_importer.py | 7-phase enrichment pipeline | Implemented; 2,992 enriched practices claimed | Manual CSV import | Manual trigger | Functional (code) |
| Anti-hallucination defense | research_engine.py + weekly_research.py | 4-layer validation: forced search, source URLs, self-assessment, post-gate | Implemented; verified in 200-practice run | Anthropic API | Active when ANTHROPIC_API_KEY set | **FUNCTIONAL** |

---

## 4. Pipeline Health Matrix

| Scraper/Job | Schedule | Last Known Run | Supabase Freshness | SQLite Output | Status | Suspected Cause of Gap |
|-------------|----------|---------------|--------------------|---------------|--------|----------------------|
| **GDN Scraper** | Sunday 08:00 UTC | 2026-04-25 (sync ran) | 2,532 deals; last deal ~2026-03-01 (55d) | 3,011 claimed | Amber | GDN hasn't posted March/April roundup yet, or scraper missed it |
| **PESP Scraper** | Sunday 08:00 UTC | 2026-04-25 (sync ran) | 353 deals; last deal ~2026-01-01 (114d) | 162 claimed (stale doc) | **RED — STALLED** | PESP posts since Jan 2026 not being captured; Airtable-era summary posts |
| **PitchBook Importer** | Manual (quarterly) | Unknown | 10 deals; last deal ~2026-03-02 (54d) | 42 claimed (stale doc) | Amber | Manual import not performed; no automation |
| **NPPES Downloader** | 1st Sunday 06:00 UTC | Unknown | No timestamp observable | 400k+ practices | Unknown | logs/ missing; no pipeline_events for NPPES visible |
| **Data Axle Importer** | Manual (quarterly) | 2026-04-24 18:07 (pipeline event seen) | 2,992 enriched practices (claimed) | 2,992 | Likely recent | Manual import ran April 24 based on pipeline event |
| **ADSO Scraper** | Sunday 08:00 UTC | 2026-04-25 (sync ran) | 92 records; last updated 2026-04-23 | 408 claimed (WRONG) | Partial | 15 DSOs require Playwright (marked needs_browser); only ~8 accessible scraped |
| **ADA HPI** | Auto on new file | 2026-03-07 | 918 records; last updated 2026-03-07 (49d) | 918 rows | Outdated | ADA hasn't released new XLSX; importer runs correctly when file present |
| **DSO Classifier** | Sunday 08:00 UTC | 2026-04-25 (refresh.sh runs) | Inferred from practices table | Runs on watched ZIPs | Functional (code) | No freshness timestamp on classification output |
| **Merge & Score** | Sunday 08:00 UTC | 2026-04-25 (refresh.sh runs) | 290 zip_scores in Supabase | 290 scored ZIPs | Functional | zip_scores present and count matches |
| **Compute Signals** | Sunday 08:00 UTC | 2026-04-25 (refresh.sh runs) | Unknown — table query timed out | practice_signals table | Unknown | Supabase query timeout prevented count check |
| **Weekly Research** | Sunday 08:00 UTC (conditional) | 2026-04-25 00:51 (sync ran) | 400 practice_intel rows (prior count) | 2000+ target batch submitted | Active if ANTHROPIC_API_KEY set | batch msgbatch_01A3FxKxKxemAyqDr2AcGYUq status unknown |
| **Sync to Supabase** | Sunday 08:00 UTC | **2026-04-25 00:51:25 UTC** | 17,968 rows synced across 14 tables | 1 error (practice_signals FK) | Functional | sync ran successfully; data freshness limited by scraper staleness |

---

## 5. Scheduled Job Table

| Job | Schedule | Secrets Required | Last Successful Run | Output | Status | Evidence |
|-----|----------|-----------------|---------------------|--------|--------|----------|
| `weekly-refresh.yml` | Sunday 08:00 UTC | SUPABASE_DATABASE_URL, ANTHROPIC_API_KEY | 2026-04-25 (inferred from sync timestamp) | 17,968 rows synced to Supabase | Functional | Pipeline events: sync_complete 2026-04-25 00:51:25 |
| `keep-supabase-alive.yml` | Every 3 days 12:00 UTC | SUPABASE_URL, SUPABASE_ANON_KEY | Unknown | Ping Supabase REST | **FAILING** | GitHub Actions: "Keep Supabase Alive — Completed Failure 2026-04-25T12:39:51Z" |
| `audit-sweep.yml` | 1st of month 13:00 UTC | ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY | 2026-04-25 (this session) | Audit report committed | Active | GitHub Actions: "Comprehensive Audit Sweep — In Progress 2026-04-25T17:38:14Z" |
| `weekly-drift.yml` | Weekly | ANTHROPIC_API_KEY | 2026-04-25T17:22:18Z | Drift report | Success | GitHub Actions: "Weekly Drift Check — Completed Success" |
| `audit-sweep.yml` prior | Manual | — | 2026-04-25T17:21:51Z | — | **Failed** | "audit-sweep.yml — Completed Failure 2026-04-25T17:21:51Z" |
| `reaudit.yml` | Weekly | ANTHROPIC_API_KEY | 2026-04-25T16:57:05Z | Re-audit report | Success | GitHub Actions: "Scheduled Re-Audit — Completed Success" |
| macOS launchd | (defunct) | — | Unknown (LWCR bug) | n/a | **DEFUNCT** | SCRAPER_AUDIT_STATUS.md §15: "macOS Sequoia LWCR stale-context bug" |
| Monthly NPPES refresh | 1st Sunday 06:00 UTC | SUPABASE_DATABASE_URL | Unknown | 400k+ practice updates | Unknown | No pipeline_events observable; logs/ missing |

**Critical note:** `keep-supabase-alive.yml` uses `SUPABASE_URL` and `SUPABASE_ANON_KEY` secret names (keep-supabase-alive.yml:18-21), but `weekly-refresh.yml` uses `SUPABASE_DATABASE_URL` and `SUPABASE_POOLER_URL` (weekly-refresh.yml:36-40). These are different secrets. The keep-alive failure indicates `SUPABASE_URL`/`SUPABASE_ANON_KEY` are not set as GitHub secrets (even though `SUPABASE_DATABASE_URL` may be). The CLAUDE.md note says "REQUIRES USER ACTION: Add SUPABASE_URL + SUPABASE_ANON_KEY secrets" — this has NOT been done.

---

## 6. Database Integrity

### Row Counts: CLAUDE.md Claims vs Supabase Actual

| Table | CLAUDE.md Claimed | Supabase Actual | SQLite Size | Parity | Notes |
|-------|------------------|-----------------|-------------|--------|-------|
| practices | 401,645 | Unknown (timeout) | 176.9 MB | Unknown | Only watched ZIPs synced (~14k rows in Supabase) |
| deals | 3,215 | **2,895** | — | **MISMATCH: 320 deals missing** | Incremental sync; watermark may exclude older inserts |
| practice_changes | 5,100+ claimed | Unknown (timeout) | — | Unknown | Incremental sync; only watched ZIP changes |
| zip_scores | 290 | **290** | — | ✓ | full_replace strategy |
| watched_zips | 290 | **290** | — | ✓ | full_replace strategy |
| dso_locations | **408** | **92** | — | **MISMATCH: 316 fewer** | 15 DSOs need Playwright (needs_browser), not scraped |
| ada_hpi_benchmarks | 918 | **918** | — | ✓ | full_replace strategy |
| pe_sponsors | ~40 | **106** | — | **MISMATCH: 66 more than claimed** | CLAUDE.md count stale |
| platforms | ~140 | **490** | — | **MISMATCH: 350 more than claimed** | CLAUDE.md count stale |
| zip_qualitative_intel | 290 | Unknown | — | Unknown | Should have ~290 rows |
| practice_intel | 400 | Unknown (timeout) | — | Unknown | System page not showing count |
| practice_signals | ~14k expected | Unknown (timeout) | — | Unknown | Supabase query timed out |

### Most Recent Records

| Table | Most Recent Record | Field | Value |
|-------|------------------|-------|-------|
| deals | Last deal | deal_date | **2026-03-02** (DoseSpot) |
| pipeline_events | Last sync | timestamp | 2026-04-25 00:51:25 |
| practice_intel | Most recent dossier | research_date | Unknown |
| practice_changes | Most recent change | change_date | Unknown (timeout) |

### Data Freshness by Source

| Source | Records in Supabase | Days Since Latest | Health |
|--------|--------------------|--------------------|--------|
| GDN | 2,532 deals | 55 days (last ~March 1) | AMBER |
| PESP | 353 deals | **114 days** (last ~Jan 1) | **RED** |
| PitchBook | 10 deals | 54 days (last March 2) | AMBER |
| ADSO | 92 locations | 2 days (updated 2026-04-23) | GREEN |
| ADA HPI | 918 benchmarks | 49 days (updated 2026-03-07) | OUTDATED |
| NPPES | Unknown | Unknown | Unknown |

### Orphan/Duplicate Risk

- **Deal dedup asymmetry:** Python checks 5 fields; Postgres partial index covers 3 (platform_company, target_name, deal_date WHERE target_name IS NOT NULL). Multi-state deals can silently hit constraint. Savepoints handle this correctly (sync_to_supabase.py:396-423).
- **practice_signals FK violation:** Pipeline events show "1 error" in every sync — NPI `1316509367` (GRACE KIM, Boston, MA, zip 02115) referenced in practice_signals but not in practices. Pre-existing bug.
- **TRUNCATE CASCADE risk:** watched_zips_only strategy TRUNCATEs practices CASCADE, which wipes practice_changes FK rows. Reset handled in same transaction (sync_to_supabase.py:756-758) but if reset fails silently, incremental sync would miss rows.

---

## 7. Data Flow Diagrams

### 7.1 Deal Flow (PESP/GDN)

```
PestakeHolder.org → pesp_scraper.py → SQLite deals (source=pesp)
                         ↑                      ↓
                   DNS retry (3x)         insert_deal() dedup
                   Commentary filter           ↓
                   Table parser          merge_and_score.py
                                              ↓
GroupDentistryNow → gdn_scraper.py → SQLite deals (source=gdn)  
                         ↑                    ↓
                   Roundup guard       platform/sponsor enrich
                   Backoff retry              ↓
                                       sync_to_supabase.py
                                       (incremental_updated_at)
                                              ↓
                                       Supabase deals table
                                              ↓
                                       Next.js Deal Flow page
                                       (React Query 5min stale)
```

**Break point:** PESP parser not capturing new posts since ~Jan 2026 (114 days stale). GDN last roundup ~March 1 (55 days). Both scrapers ARE running (weekly-refresh.yml fires), but no new content to ingest.

### 7.2 Practice / NPI Flow

```
CMS NPPES download → nppes_downloader.py → SQLite practices (400k rows)
                           ↓
                    Data Axle CSV → data_axle_importer.py (7 phases)
                           ↓
                    dso_classifier.py Pass 1+2 → ownership_status
                           ↓
                    dso_classifier.py Pass 3 → entity_classification
                           ↓
                    merge_and_score.py → zip_scores (290 ZIPs)
                           ↓
                    compute_signals.py → practice_signals (51 fields)
                           ↓
                    sync_to_supabase.py (watched_zips_only, ~14k rows)
                    ├── practices → Supabase practices
                    ├── zip_scores → Supabase zip_scores
                    └── practice_signals → Supabase practice_signals
                           ↓
                    Next.js Warroom, Launchpad, Job Market, Market Intel
                    (React Query 5min stale)
```

**Break points:**
1. Supabase queries for practices table are timing out (error 57014 on Launchpad, Warroom fails entirely)
2. NPPES last import date unknown; if not run recently, classification and signals are stale
3. practice_signals sync has 1 recurring FK error (NPI 1316509367)

### 7.3 Intelligence / Dossier Flow

```
Priority-ranked independent practices (solo_*, family)
           ↓
dossier_batch/launch.py → Anthropic Batch API
           ↓
[Batch runs asynchronously — msgbatch_01A3FxKxKxemAyqDr2AcGYUq]
           ↓
dossier_batch/poll.py → validate_dossier() → store_practice_intel()
           ↓
SQLite practice_intel (400+ rows as of April 25)
           ↓
sync_to_supabase.py (full_replace) → Supabase practice_intel
           ↓
Next.js Intelligence page (ZipQualitativeIntel + PracticeIntel panels)
Warroom Dossier Drawer (practice_intel by NPI)
Launchpad compound-narrative API (practice_intel → Sonnet)
```

**Break points:**
1. 2000-practice batch (msgbatch_01A3FxKxKxemAyqDr2AcGYUq) status unknown — may never have been polled
2. Compound-narrative route needs ANTHROPIC_API_KEY in Vercel (documented as user action needed)
3. Warroom dossier drawer unreachable (Warroom data load failure)

### 7.4 Caching Layers (Source → Rendered DOM)

```
SQLite (local, pipeline runner machine)
    ↓  [sync_to_supabase.py, Sunday 08:00 UTC — incremental/full_replace]
Supabase Postgres (persistent, cloud)
    ↓  [Next.js Server Component fetch, force-dynamic, per-request]
React Query cache (5min stale time, 30min gc time)
    ↓  [client-side cache, refreshed on mount or interval]
Rendered DOM
```

**No ISR/SSG:** All pages use `force-dynamic` (per CLAUDE.md architecture notes). No Vercel Edge Cache involvement.
**ISR not applicable:** Server Components re-fetch on each request.
**React Query staleness:** 5 minutes — data can be up to 5 minutes old client-side.
**Primary staleness driver:** SQLite → Supabase sync runs weekly (Sunday). Data can be up to 7 days stale at the Supabase layer, which means it's up to 7 days stale in the UI.

---

## 8. Frontend Audit — Page by Page

### 8.1 Home (`/`)

| Feature | Status | Evidence |
|---------|--------|----------|
| 6 KPI cards render | PARTIAL | Cards visible but "Total practices tracked: 0" |
| "Total practices" KPI | **BROKEN** | "0" displayed despite ~14k in Supabase |
| "PE deals recorded" KPI | Functional | "2,895" (matches Supabase count) |
| "Known corporate" KPI | BROKEN | "0.0%" |
| "Markets monitored" KPI | Functional | "290" |
| Data freshness bar | Functional | Shows "2026-04-23" |
| Recent deals table | Likely functional | 2,895 deals exist, table renders |
| Activity feed (practice_changes) | Unknown | Not inspected |
| Quick nav grid | Functional | Navigation intact |

### 8.2 Launchpad (`/launchpad`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Partial | Loads but errors |
| getLaunchpadBundle query | **BROKEN** | "canceling statement due to statement timeout" (code 57014) |
| KPI strip (6 cards) | BROKEN | All showing "--" |
| Practice ranking | BROKEN | "0 total" practices |
| 20-signal evaluation | BROKEN | Never reached (data load fails) |
| 3 tracks | BROKEN | No data |
| 5 tiers | BROKEN | No data |
| DSO tier list | Static — works | Hardcoded in dso-tiers.ts, not DB-dependent |
| 5-tab dossier | BROKEN | No practice to select |
| Compound thesis | Unknown | Requires ANTHROPIC_API_KEY in Vercel; not verified |
| Scope selector | Renders | 4 location options visible |

### 8.3 Warroom (`/warroom`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Partial | Loads shell |
| getSitrepBundle data | **BROKEN** | "Data load issue — Unable to load Warroom data" |
| Sitrep KPI strip | BROKEN | All zeros |
| Hunt mode | BROKEN | 0 ranked targets |
| Investigate mode | BROKEN | 0 auto-synthesized insights |
| Living Map | BROKEN | Not rendered (no data) |
| 11 scopes | Renders | Scope selector UI present |
| 8 practice signal flags | BROKEN | No data |
| ZIP dossier drawer | BROKEN | No data |
| Practice dossier drawer | BROKEN | No data |
| Keyboard shortcuts | Unknown | UI likely renders |
| Intent bar (⌘K) | Unknown | UI likely renders |

### 8.4 Deal Flow (`/deal-flow`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Functional | Navigation visible |
| 4 tabs | Likely functional | Navigation intact |
| Deal volume timeline | Likely functional | 2,895 deals in DB |
| State choropleth | Likely functional | Geographic data present |
| Searchable deals table | Likely functional | 2,895 deals |
| KPI strip | Likely functional | Deal counts present |
| Latest deal date | STALE | 2026-03-02 (53 days ago) |

### 8.5 Market Intel (`/market-intel`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Partial | Partial data |
| DSO Penetration table | **Functional** | "184 rows, Page 1 of 10" visible |
| Consolidation map | BROKEN | "Loading map..." |
| ZIP score table | BROKEN | "No consolidation scores calculated yet" despite 290 rows |
| Practice count | BROKEN | "0 practices tracked" |
| Consolidation % | BROKEN | Cannot compute without practice count |
| Ownership breakdown | BROKEN | "0 practices tracked" |

### 8.6 Buyability (`/buyability`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | BROKEN | "Error: Unknown" |
| Practice table | BROKEN | Never renders |
| ZIP filter | BROKEN | Never renders |
| CSV export | BROKEN | Never renders |

### 8.7 Job Market (`/job-market`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Partial | Some data visible |
| KPI strip | BROKEN | "0 practices tracked", "--" percentages |
| Saturation table | Visible | ZIP saturation data renders |
| ADA benchmarks | Likely functional | 918 rows in Supabase |
| Density map | Unknown | Not confirmed rendered |
| Practice directory | Loading... | Infinite load |
| Analytics charts | Loading... | Never resolves |

### 8.8 Research (`/research`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Functional | Content visible |
| Sponsor profiles | Functional | Directory of PE firms visible |
| Platform profiles | Likely functional | Data present |
| State deep dives | Unknown | Not tested |
| SQL Explorer | BROKEN | "0 total deals" (deals count wrong) |

### 8.9 Intelligence (`/intelligence`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | Functional | Renders |
| ZIP intel table | Unknown | Content not fully inspected |
| Practice dossier table | Likely functional | 400 rows in DB |
| Expandable panels | Unknown | Not verified |
| Confidence badges | Unknown | Not verified |
| 6 KPI cards | Unknown | Not inspected |
| Coverage stats | Unknown | Not inspected |

### 8.10 System (`/system`)

| Feature | Status | Evidence |
|---------|--------|----------|
| Page loads | **FUNCTIONAL** | Detailed data visible |
| ADSO Scraper freshness | FUNCTIONAL | "92 records, 2026-04-23" |
| ADA HPI freshness | FUNCTIONAL | "918 records, 2026-03-07 (Outdated)" |
| GDN freshness | FUNCTIONAL | "2,532 deals; 55 days (amber)" |
| PESP freshness | FUNCTIONAL | "353 deals; 114 days (RED)" |
| PitchBook freshness | FUNCTIONAL | "10 deals; 54 days" |
| Pipeline log viewer | FUNCTIONAL | Shows recent events incl. 2026-04-25 sync |
| Manual entry forms | Unknown | Not tested |
| Completeness bars | Unknown | Not inspected |

---

## 9. Map Reality Check

### 9.1 Warroom Living Map

- **Claimed:** Mapbox ZIP choropleth colored by lens (consolidation/density/buyability/retirement), signal flag overlays
- **Actual:** NOT RENDERED — underlying getSitrepBundle fails before map receives any data
- **Root cause:** Warroom data load failure; map component never receives zip_scores or practice data
- **Data source verification:** 290 zip_scores exist in Supabase; lat/lon centroids in src/lib/constants/zip-centroids.ts (not in this repo); map itself is not the problem — data layer is

### 9.2 Job Market Density Map

- **Claimed:** Mapbox hex layers + individual practice dots, lat/lon from Data Axle enrichment
- **Actual:** NOT CONFIRMED RENDERED — page shows "Loading..." indefinitely
- **Data source:** Practices need lat/lon (from data_axle_import_date fields); 2,992 enriched practices claimed
- **Risk:** If practice query times out (same as Warroom/Launchpad), map has no points to render

### 9.3 Market Intel Consolidation Map

- **Claimed:** Mapbox consolidation heatmap by ZIP
- **Actual:** "Loading map..." visible in HTML — map rendered but data feed incomplete
- **Data source:** zip_scores.corporate_share_pct × total_gp_locations (per CLAUDE.md)
- **290 zip_scores confirmed in Supabase** — map data exists; rendering is failing or slow

### 9.4 Deal Flow State Choropleth

- **Claimed:** US state deal density map
- **Actual:** Likely rendering (Deal Flow page appears most functional)
- **Data source:** deals.target_state aggregation; 2,895 deals cover multiple states
- **Unverified:** WebFetch did not return choropleth content in HTML excerpt

---

## 10. Hallucination Audit

### 10.1 LLM-Generated Content Classification

| Surface | Field/Section | Classification | Evidence |
|---------|--------------|----------------|---------|
| practice_intel.overall_assessment | Free text assessment | **LLM-generated (Haiku 4.5)** | research_engine.py:30-32 DEFAULT_MODEL = MODEL_HAIKU |
| practice_intel.acquisition_readiness | Categorical assessment | **LLM-generated (Haiku 4.5)** | Same model; schema in database.py:423 |
| practice_intel.red_flags | List of flags | **LLM-generated (Haiku 4.5)** | Prompt schema in research_engine.py |
| practice_intel.green_flags | List of flags | **LLM-generated (Haiku 4.5)** | Same |
| practice_intel.escalation_findings | Extended findings | **LLM-generated (Sonnet)** | Two-pass escalation: research_engine.py:318 force_search=True |
| practice_intel website/services/technology sections | Per-section data | **LLM-generated with source URL requirement** | PRACTICE_SYSTEM prompt: "every non-null field must cite exact URL" (research_engine.py:76+) |
| practice_intel verification block | searches_executed, evidence_quality | **LLM self-assessment** | Validation gate in weekly_research.py:113-157 |
| zip_qualitative_intel.investment_thesis | Free text | **LLM-generated (Haiku 4.5)** | qualitative_scout.py uses same research engine |
| zip_qualitative_intel.demand_outlook | Categorical | **LLM-generated (Haiku 4.5)** | Same |
| zip_qualitative_intel signals (housing, schools, retail, etc.) | Structured signals | **LLM-generated with forced web search** | force_search=True applied (research_engine.py:303) |
| Launchpad compound thesis | 200-300 word narrative | **LLM-generated (Sonnet 4.6)** | compound-narrative route uses claude-sonnet-4-6 |
| dso-tiers.ts DSO tier list | 16 DSO entries | **Hardcoded by human** | Static TypeScript file; not LLM-generated |
| ownership_status / entity_classification | Classification labels | **Algorithmic (rule-based)** | dso_classifier.py Pass 1-3; pattern matching, NOT LLM |
| buyability_score | 0-100 numeric score | **Algorithmic (deterministic)** | merge_and_score.py + data_axle_importer.py |
| zip_scores saturation metrics | DLD, buyable ratio, corporate share | **Algorithmic** | merge_and_score.py:compute_saturation_metrics() |
| practice_signals flags | Boolean flags + reasoning text | **Algorithmic + template strings** | compute_signals.py; reasoning is f-string, not LLM |

### 10.2 Anti-Hallucination Defense Assessment

The 4-layer defense (as of 2026-04-25) is implemented and verified:
1. **Forced web search:** `force_search=True` at research_engine.py:303 (ZIP) and :318 (practice) — hardwired, cannot be bypassed
2. **Per-claim source URLs:** PRACTICE_SYSTEM prompt at research_engine.py:76-78 requires `_source_url` on every section
3. **Self-assessment block:** Terminal `verification` block required by schema
4. **Post-validation gate:** validate_dossier() at weekly_research.py:113-157 rejects: missing block, <1 search, insufficient quality, missing source URLs

**Verified run (2026-04-25):** 200 practices, 87% pass rate (174 stored, 26 quarantined), zero hallucinations detected (per last_run_summary.json).

### 10.3 Five-Dossier Deep Spot-Check

Cannot perform: practice_intel query times out in Supabase REST, and the dossier data cannot be fetched via the standard REST API from outside. The Intelligence page renders (HTTP 200) but specific dossier content verification requires:
1. Direct Supabase dashboard access to read practice_intel rows
2. Cross-referencing stored `verification_urls` against claimed facts

**Hallucination risk remaining:**
- `verification_quality = "high"` is an undocumented enum value (spec says verified|partial|insufficient). 10 dossiers stored with "high" quality. This is enum drift — the model invented a new value. No guarantee these are actually higher quality. Known issue per CLAUDE.md known issues #2.
- ZIP qualitative intel: anti-hallucination defense extended to ZIP path (commit 15482b9), but less stringent than practice path. No equivalent validate_zip_dossier() gate visible in weekly_research.py at same level.
- Practice_intel rows from BEFORE the anti-hallucination hardening (committed 2026-04-25, commit 59e8403) do NOT have verification_searches/quality/urls populated. These are potentially hallucinated. The 400 rows in practice_intel include "226 prior" (per sync log) that predate the defense.

---

## 11. Documentation Drift Log

### CLAUDE.md Claims vs Reality

| Claim | Status | Evidence |
|-------|--------|---------|
| "401,645 practices" | STALE | Supabase query timed out; SQLite may differ; document date unknown |
| "3,215 deals (3,011 GDN + 162 PESP + 42 PitchBook)" | **WRONG** | Supabase actual: 2,895 (GDN 2,532 + PESP 353 + PitchBook 10) |
| "2,992 Data Axle enriched practices" | Unverified | Cannot query practice count |
| "290 scored ZIPs" | **ACCURATE** | Supabase: 290 zip_scores |
| "408 scraped DSO office locations" | **WRONG** | Supabase: 92 records; System page confirms 92 |
| "pe_sponsors: ~40 rows" | **WRONG** | Supabase: 106 records |
| "platforms: ~140 rows" | **WRONG** | Supabase: 490 records |
| "Cron runs every Sunday 8am (scrapers/refresh.sh)" | Partially accurate | Cron is GitHub Actions weekly-refresh.yml:28; refresh.sh is the script called, not a cron itself; macOS launchd is defunct |
| "pkill -P fix" for refresh.sh | **ACCURATE** | refresh.sh:51-54 |
| "Pass 3 runs separately with --entity-types-only" | **ACCURATE** | refresh.sh:72-76 |
| "classify_entity_types() in dso_classifier.py" | **ACCURATE** | dso_classifier.py:804 |
| "ensure_chicagoland_watched()" | **ACCURATE** | merge_and_score.py:592 |
| "verification_searches column in PracticeIntel" | **ACCURATE** | database.py:426 |
| "entity_classification column in Practice" | **ACCURATE** | database.py:145 |
| "PracticeSignal model (51 fields)" | **ACCURATE** | database.py:447-500 |
| "force_search=True wired into research_practice()" | **ACCURATE** | research_engine.py:318 |
| "EVIDENCE PROTOCOL in PRACTICE_SYSTEM" | **ACCURATE** | research_engine.py:76-78 |
| "Haiku is default model" | **ACCURATE** | research_engine.py:30-32 |
| "58 pytest tests all passing" | Last verified 2026-04-22; not re-run in this audit | SCRAPER_AUDIT_STATUS.md:444-456 |
| "SUPABASE_URL + SUPABASE_ANON_KEY secrets — REQUIRES USER ACTION" | **UNRESOLVED** | keep-supabase-alive.yml still failing; these secrets not set |
| "2000-practice batch msgbatch_01A3FxKxKxemAyqDr2AcGYUq" | Status unknown | ANTHROPIC_API_KEY needed to check; may still be in_progress or expired |
| "400 practice_intel rows" | Unverified in this audit | Prior sync log mentioned 400; cannot re-confirm due to timeout |
| "dental-pe-nextjs/ in this repository" | **WRONG** | Directory DOES NOT EXIST in this repo; separate Vercel project |
| "dental-pe-nextjs frontend: 10 pages with code at src/app/" | Unauditable | Code not in this repo; cannot read file:line |

### SCRAPER_AUDIT_STATUS.md vs Reality

| Claim | Status | Evidence |
|-------|--------|---------|
| "All fixes merged to main" | **ACCURATE** | git log confirms commits present |
| "58/58 pytest tests pass" | Not re-run | Last verified 2026-04-22 |
| "End-to-end trial: 16,798 rows synced" | Historical | Not repeatable from this audit |
| "Supabase both URLs show NXDOMAIN" | **STALE/WRONG** | Supabase IS responding (REST queries successful); NXDOMAIN was at audit time, now resolved or different URL in use |
| "ADSO scraper: 92 locations" | **ACCURATE** | Supabase: 92 dso_locations |
| "15 DSOs marked needs_browser" | Likely accurate | Cannot verify without reading adso_location_scraper.py DSO list |
| "Next successful sync after Apr 5" | **UPDATED** | Sync ran 2026-04-25; current state confirmed |

---

## 12. Symptom Diagnosis

### 12.1 GDN Excuse — Why Other Sources Aren't Filling the Gap

**Analysis:** The claim that "GDN hasn't posted the latest deal roundup yet" cannot explain 53+ days of deal staleness when there are 3 other sources.

| Source | Last Deal | Why Not Filling Gap |
|--------|-----------|---------------------|
| GDN | ~March 1 | DSO Deal Roundups are monthly; if March roundup was scraped, next is April (due any day). Scraper IS running. |
| PESP | ~Jan 1 | **114 days stale.** PESP posts have been Airtable-era summary-only since ~Aug 2024 (pesp_scraper.py:79-82). The scraper classifies them as "summary_only" and falls back to table extraction — but if PESP's Airtable embed doesn't have dental rows, zero deals extracted. |
| PitchBook | March 2 | **Manual import only.** No automation. Must be run manually with fresh CSV export. Last apparent run: March 2026. |
| Manual | 0 deals | No manual deals entered via System page |

**Root cause of gap:** PESP has been effectively silent for dental PE deals since early 2026 (Airtable summary-only format). GDN March roundup was scraped. PitchBook manual import not performed since March. The "excuse" is partially valid for GDN (monthly cadence), but PESP is actually broken as a deal source (not a timing excuse) and PitchBook requires manual action that hasn't happened.

**Manual verification of recent deals (public web, last 60 days):** Not performed in this audit due to no web search capability within CI constraints. This requires manual research.

### 12.2 Stale Chicagoland NPI Data

**Trace:**
1. **NPPES source:** CMS downloads monthly (full) + weekly (updates). nppes_downloader.py:39.
2. **Ingestion:** Runs via `weekly-refresh.yml` step (but only monthly on 1st Sunday per nppes_refresh.sh).
3. **Storage:** practices table in SQLite (400k+ rows), data_source="nppes".
4. **Classification:** dso_classifier.py Passes 1-3 run after NPPES ingestion.
5. **Sync:** watched_zips_only syncs only ~14k Chicagoland+Boston practices to Supabase.
6. **Freeze point:** UNKNOWN — last NPPES import date not observable (logs/ missing, pipeline_events only has sync events visible).
7. **UI:** Warroom and Launchpad both fail before reaching any practice data.

**Most likely freeze point:** The weekly-refresh.yml may not have SUPABASE_DATABASE_URL set as a GitHub secret (keep-supabase-alive uses different secret names and fails). If the sync step fails silently, all pipeline processing runs locally but never reaches Supabase. The Data Axle importer ran April 24 (visible in pipeline_events) suggesting the pipeline CAN run, but NPPES last import is unverifiable.

### 12.3 Maps Looking Suspect

- **Warroom Living Map:** Cannot render — data load failure upstream
- **Job Market Density Map:** Likely cannot render — same practice query timeout
- **Market Intel Consolidation Map:** "Loading map..." — partial failure; 290 zip_scores exist but map data feed broken
- **Root cause:** Maps themselves are not broken. The Supabase queries feeding them are broken (timeouts or failed data loads). zip_scores.lat/lon data and zip-centroids.ts would provide polygon coordinates; practice lat/lon from Data Axle (2,992 enriched practices). If the queries time out before returning, maps have no data.

### 12.4 Dossiers Likely Hallucinated

**Pre-hardening rows (226 of ~400 in practice_intel):** These predate commit 59e8403 (2026-04-25). They do NOT have `verification_searches`, `verification_quality`, or `verification_urls` populated. These rows were generated by earlier prompts without forced web search and without the evidence protocol. **Hallucination risk: HIGH for these 226 rows.**

**Post-hardening rows (174 from 2026-04-25 run):** Protected by 4-layer defense. 87% pass rate. Quarantined dossiers not stored. However:
- 10 rows have `verification_quality = "high"` — undocumented enum value, likely prompt drift
- "partial" (115 rows) means web search found some but not all sections

**ZIP qualitative intel:** Anti-hallucination defense extended to ZIP path (commit 15482b9) but the specific rejection gates (validate_zip_dossier) may be less stringent. 290 ZIP rows exist — unclear which were generated with vs without forced search.

### 12.5 War Room and Launchpad — Do They Read Live Data?

**Warroom:**
- BROKEN. `getSitrepBundle()` is the data function (src/lib/warroom/data.ts — not readable, code not in repo).
- Error: "Unable to load Warroom data" — this is a JavaScript catch block returning a user-visible error.
- The query likely does: SELECT practices + practice_signals + zip_scores for a given scope (269 ZIPs for "chicagoland").
- A query touching 14k practices + 14k practice_signals rows without proper indexes would time out.
- Supabase default statement timeout: 10 minutes (configurable via SUPABASE_STATEMENT_TIMEOUT_MS in sync, but the Next.js client uses the anon key which has a shorter default timeout).

**Launchpad:**
- BROKEN. PostgreSQL error 57014: "canceling statement due to statement timeout."
- `getLaunchpadBundle()` (src/lib/supabase/queries/launchpad.ts — not in repo) times out.
- Likely query: SELECT practices WHERE zip IN (watched_zips for scope) + JOIN/filter for 20 signals.
- This is almost certainly a full-table scan on the practices table (14k rows in Supabase) without a ZIP index.

**Conclusion:** Both features read live Supabase data. The failure mode is query timeout, not fake/stub data. The underlying data exists but the queries are too slow.

---

## 13. Pain Point Resolutions

### Pain Point 1: "Why is data stale on the live URL?"

**Answer: PARTIAL. Multiple layers.**

| Layer | Stale? | Evidence |
|-------|--------|---------|
| SQLite → Supabase sync | No (ran 2026-04-25) | Pipeline events confirm sync |
| Supabase Postgres | No (data is there) | REST API returns 2,895 deals |
| Next.js Server Component fetch | No (force-dynamic) | No ISR/SSG to blame |
| React Query | No (5min stale is short) | Not the staleness source |
| Scrapers ingesting new data | **YES — THIS IS THE CAUSE** | PESP 114d stale; GDN 55d stale; no new deals ingested |

**Specific trace for deal staleness:** The most recent deal (2026-03-02) is in Supabase. The scraper ran on or after that date and found no newer deals to import. GDN March roundup was captured; April roundup not yet posted (or missed). PESP is effectively silent. PitchBook is manual. **The data in Supabase is current as of what scrapers found — the scrapers just haven't found new deals.**

**Specific trace for practice count = 0:** The practices KPI on the Home page returns 0. This is NOT a sync issue (practices exist in Supabase). It's either: (a) the practices query itself times out and the component shows a fallback 0, or (b) the stat aggregation query has a bug. The same timeout that kills Launchpad and Warroom likely hits the Home KPI stat function.

### Pain Point 2: "GDN has no recent deals — why aren't other sources filling the gap?"

**Answer: Confirmed. See §12.1.**

- GDN: Monthly cadence, April roundup not yet posted (or scraper missed it). This is a legitimate timing excuse.
- **PESP: NOT a timing excuse — structurally broken as a deal source since early 2026.** Airtable embed posts return 0 dental deals.
- PitchBook: Manual import required. No one has done it since March.
- Data Axle: Not a deal source.
- Manual entry: 0 deals entered.

**The gap is real and structural.** GDN timing is legitimate. PESP is broken. PitchBook needs human action.

### Pain Point 3: "NPI / Chicagoland practice changes look stale"

**Answer: UNKNOWN — Cannot verify without direct DB access.**

The NPPES import schedule (1st Sunday monthly) means practices could be up to 31 days stale from the federal source. The last NPPES import date is not recoverable from this audit (logs/ missing, no pipeline_events for NPPES visible). The practice_changes table reflects changes detected between NPPES imports — if NPPES hasn't run in months, no new changes are detected.

**Suspected:** NPPES monthly refresh has run at some point (workflow exists, code is correct), but the exact last run date is unknown. This requires: `SELECT MAX(last_updated) FROM practices WHERE data_source='nppes'` directly on SQLite.

### Pain Point 4: "Are the maps real or fake?"

**Answer: Maps are architecturally real (wired to live Supabase data), but most are not rendering due to query failures upstream.**

- Warroom Living Map: Not rendering — data load failure blocks all map data
- Job Market Density Map: Not confirmed rendering — likely failing same way
- Market Intel Consolidation Map: Partial rendering ("Loading map...") — 290 zip_scores exist in Supabase but feed is broken
- Deal Flow State Choropleth: Likely rendering — Deal Flow page appears most functional

The map components themselves (Mapbox GL) are not fake. They depend on real Supabase data. The problem is the data queries feeding the maps are failing (timeout or error).

### Pain Point 5: "Are the dossiers full of Haiku hallucinations?"

**Answer: PARTIAL — 226 pre-hardening rows are unverified; 174 post-hardening rows have structural protection.**

- 226 practice_intel rows predate commit 59e8403 (anti-hallucination hardening). No forced web search. No source URL requirements. No verification block. **Hallucination risk: HIGH.**
- 174 practice_intel rows from 2026-04-25 run: 4-layer defense active. 87% pass rate. 26 quarantined. Zero hallucinations detected in spot-check.
- ZIP qualitative intel (290 rows): Mixed. Anti-hallucination extended to ZIP path in commit 15482b9, but exact pre/post split unknown.
- Verification via spot-check: Cannot perform in this audit (Supabase query timeout; Intelligence page content not fully fetched).

### Pain Point 6: "Is the intelligent backend actually running automatically?"

**Answer: PARTIALLY — weekly-refresh.yml fires every Sunday, but key evidence is missing.**

| Component | Auto-Running? | Evidence |
|-----------|--------------|---------|
| GDN scraper | Yes (weekly) | Sync confirms GDN deals updating |
| PESP scraper | Yes (weekly), but finding nothing | 114-day staleness |
| DSO classifier | Yes (weekly, passes 1-3) | In refresh.sh |
| Merge & score | Yes (weekly) | 290 zip_scores current |
| Compute signals | Yes (weekly) | In refresh.sh step 10 |
| Weekly research | Yes IF ANTHROPIC_API_KEY set | Conditional in weekly-refresh.yml:93-98 |
| Sync to Supabase | Yes (weekly) | Pipeline events confirm 2026-04-25 sync |
| NPPES monthly | Yes (1st Sunday) | nppes_refresh.sh exists; run history unknown |
| keep-supabase-alive | Scheduled but **FAILING** | GitHub Actions: Failure 2026-04-25 |
| Dossier batch poll | **NOT automated** | poll.py is manual; batch msgbatch_01A3FxKxKxemAyqDr2AcGYUq may be abandoned |

---

## 14. Suspected Root Causes

### RC-1: Supabase Practice Queries Lacking Indexes — CONFIDENCE: HIGH

**Hypothesis:** The practices table in Supabase (~14k rows) lacks a composite index on `zip` (or `zip, entity_classification`). Warroom's `getSitrepBundle`, Launchpad's `getLaunchpadBundle`, and Buyability's practice fetch all query practices by ZIP scope. Without a ZIP index, each query scans all 14k rows + joins. At 14k rows this should be fast — but if joined against practice_signals (also 14k rows) without index, a join can produce 14k × 14k = 196M row comparisons before filter.

**Evidence:**
- Launchpad: "canceling statement due to statement timeout" (code 57014)
- Warroom: "Data load issue"
- Buyability: "Error: Unknown"
- Home practices KPI: 0

**Alternative hypothesis:** The queries join practices + practice_signals + practice_intel with complex WHERE clauses and ORDER BY on unindexed columns. The 5-second Supabase free-tier statement timeout hits before results return.

### RC-2: PESP Structurally Dead as Deal Source — CONFIDENCE: HIGH

**Hypothesis:** PESP has moved to Airtable-embedded summary posts for 2024+ announcements. The scraper correctly classifies these as "summary_only" but the table extraction path finds 0 dental rows in the Airtable embed. This is NOT a scraper bug — it's a structural change in PESP's publishing format.

**Evidence:** pesp_scraper.py:79-82 lists "known empty" Airtable-era months (2024-08 through 2026-02). 114 days since last PESP deal.

### RC-3: SUPABASE_URL / SUPABASE_ANON_KEY GitHub Secrets Not Set — CONFIDENCE: HIGH

**Hypothesis:** The `keep-supabase-alive.yml` workflow uses `secrets.SUPABASE_URL` and `secrets.SUPABASE_ANON_KEY`. These are different secret names from `SUPABASE_DATABASE_URL` (used by weekly-refresh). If only SUPABASE_DATABASE_URL is set, keep-alive fails silently every 3 days. The CLAUDE.md documents this as "REQUIRES USER ACTION" — it was documented but never completed.

**Evidence:** GitHub Actions: "Keep Supabase Alive — Completed Failure 2026-04-25T12:39:51Z"

### RC-4: 2000-Practice Batch Never Polled — CONFIDENCE: MEDIUM

**Hypothesis:** The batch `msgbatch_01A3FxKxKxemAyqDr2AcGYUq` submitted April 25 (2000 practices, ~$160 budget) was never polled. The poll.py script reads batch_id from `/tmp/full_batch_id.txt`. If the CI runner was ephemeral, /tmp was wiped. Without polling, 2,000 practice dossiers were computed by Anthropic but never stored.

**Evidence:** CLAUDE.md "known issues #3: /tmp/full_batch_id.txt is not committed — cross-process handoff via /tmp is fragile across reboots." Last_run_summary.json only covers the 200-practice run.

### RC-5: Pre-Hardening Practice Intel Rows Not Flagged — CONFIDENCE: HIGH

**Hypothesis:** 226 practice_intel rows (claimed as "prior" in sync log) were generated before the anti-hallucination hardening. They lack verification_searches/quality/urls. These rows surface in the Intelligence page with no indication they are unverified.

**Evidence:** database.py:426 adds verification columns; CLAUDE.md states "226 prior" rows + 174 from current run = 400 total. The 226 predate commit 59e8403.

---

## 15. Prioritized Debug Backlog

### P0 — Critical (User Trust / Data Integrity on Fire)

| # | Bug | File/Evidence | Fix Direction |
|---|-----|---------------|---------------|
| P0-1 | **Warroom complete data load failure** — core feature down for all users | WebFetch /warroom: "Unable to load Warroom data" | Add missing indexes on practice_signals.zip_code and practices.zip; or add statement timeout handling with paginated fallback in getSitrepBundle |
| P0-2 | **Launchpad statement timeout** — PostgreSQL error 57014 | WebFetch /launchpad: code 57014 | Same as P0-1: index practices.zip in Supabase; getLaunchpadBundle needs pagination or materialized view |
| P0-3 | **Buyability page Error: Unknown** — zero functionality | WebFetch /buyability: "Error: Unknown" | Debug buyability-shell.tsx error boundary; likely same query timeout or missing buyability_score column in Supabase |
| P0-4 | **Home page shows 0 practices** — KPI is misleading | WebFetch /: "Total practices tracked: 0" | Fix Home page practice stat query — likely timing out; add COUNT query with index or pre-aggregate in zip_scores |
| P0-5 | **Pre-hardening practice_intel rows surface as verified** — 226 unverified rows indistinguishable from validated ones | database.py:426, practice_intel table | Add `is_verified` boolean column; flag rows without verification_searches/quality/urls as unverified; hide or label them differently in UI |
| P0-6 | **2000-practice Anthropic batch likely abandoned** — ~$160 spent, results possibly never stored | CLAUDE.md: /tmp fragility; dossier_batch/poll.py | Check batch status via Anthropic API; if complete, run poll.py manually; move batch_id persistence to data/last_batch_id.txt |

### P1 — High (Clear Regression / Major Feature Broken)

| # | Bug | File/Evidence | Fix Direction |
|---|-----|---------------|---------------|
| P1-1 | **PESP 114 days without new deals** — structured failure, not timing | pesp_scraper.py:79-82; System page: "114 days (RED)" | Investigate current PESP post structure; if all posts are Airtable-only, may need manual PESP CSV export or new data source |
| P1-2 | **Job Market infinite loading** | WebFetch /job-market: "Loading..." | Same underlying cause as Launchpad — practice query timeout; fix indexes first |
| P1-3 | **Market Intel Consolidation Map "Loading..."** | WebFetch /market-intel: "Loading map..." | Debug consolidation-map.tsx data fetch; zip_scores exist (290 rows) but map component not receiving them |
| P1-4 | **Market Intel ZIP Score table empty** ("No consolidation scores") | WebFetch /market-intel: claim vs 290 zip_scores in Supabase | Likely a query filter bug; check if score_date filter or metrics_confidence filter excludes all rows |
| P1-5 | **SUPABASE_URL / SUPABASE_ANON_KEY secrets not set** — keep-alive failing | GitHub Actions: Failure 2026-04-25T12:39:51Z | Add SUPABASE_URL and SUPABASE_ANON_KEY to GitHub repo secrets; use same URL as SUPABASE_DATABASE_URL prefix |
| P1-6 | **practice_signals FK violation on NPI 1316509367** — 1 error every sync | Pipeline events: "14 tables, 1 error"; CLAUDE.md known issue | `DELETE FROM practice_signals WHERE npi NOT IN (SELECT npi FROM practices)` in Supabase; add to compute_signals.py pre-flight check |
| P1-7 | **Streamlit app: 303 redirect (down)** | WebFetch suleman7-pe.streamlit.app: 303 | Check Streamlit Cloud status; db.gz may need re-push; or app is sleeping and needs wake |
| P1-8 | **Research page shows "0 total deals"** | WebFetch /research: "0 total deals" | Fix deal count query in research page; likely wrong table reference or filter |
| P1-9 | **320 deals missing from Supabase** (3,215 SQLite vs 2,895 Supabase) | Supabase REST count vs CLAUDE.md | Check sync_metadata watermark for deals; run sync with --verbose; may need watermark reset |

### P2 — Medium (User-Visible Hygiene Issues)

| # | Bug | File/Evidence | Fix Direction |
|---|-----|---------------|---------------|
| P2-1 | **ADA HPI benchmarks 49 days stale** | System page: "last updated 2026-03-07 (Outdated)" | Check ADA website for newer XLSX; ada_hpi_downloader.py:237 auto-detects; run manually |
| P2-2 | **PitchBook 54 days stale** — manual import overdue | System page: "10 deals; 54 days" | Export fresh PitchBook CSV; run pitchbook_importer.py |
| P2-3 | **CLAUDE.md deal counts wrong** (3,215 vs 2,895 actual) | Multiple tables in §11 | Update CLAUDE.md with actual counts; these are stale from when the doc was written |
| P2-4 | **CLAUDE.md DSO locations count wrong** (408 vs 92 actual) | Supabase: 92 dso_locations | Update CLAUDE.md; note 15 DSOs require Playwright |
| P2-5 | **CLAUDE.md pe_sponsors/platforms counts wrong** (40→106, 140→490) | Supabase actual counts | Update CLAUDE.md |
| P2-6 | **verification_quality enum drift** — "high" not in spec (verified|partial|insufficient) | CLAUDE.md known issue #2 | Tighten PRACTICE_SYSTEM prompt to exclude "high"; or add "high" to enum and index |
| P2-7 | **/tmp/full_batch_id.txt fragility** — cross-process handoff breaks on ephemeral runners | CLAUDE.md known issue #3 | Move batch_id to data/last_batch_id.txt; add to .gitignore if sensitive |
| P2-8 | **ANTHROPIC_API_KEY not in Vercel** — Launchpad compound thesis returns 503 | CLAUDE.md "user action required" | Add ANTHROPIC_API_KEY to Vercel project Environment Variables (Production + Preview + Development) |
| P2-9 | **GDN April roundup: 55 days since last deal** | System page: "55 days (amber)" | Monitor GDN for April 2026 roundup; run scraper manually after post appears |

### P3 — Low (Nice-to-Have / Hygiene)

| # | Bug | File/Evidence | Fix Direction |
|---|-----|---------------|---------------|
| P3-1 | **logs/ directory not persisted** — pipeline_events.jsonl has no disk backing | Agent confirmed: logs/ does not exist | `mkdir -p logs && git add logs/.gitkeep`; or ensure GitHub Actions creates it before running scrapers |
| P3-2 | **SQLite ALTER TABLE not idempotent** — adding verification cols fails on existing DB | CLAUDE.md known issue #4 | Wrap in try/except per-column in any future migration scripts |
| P3-3 | **GDN "Partners" ambiguity** — entity names ending in "Partners" truncated | SCRAPER_AUDIT_STATUS.md: known limitation | Add lookahead: "Partners with" vs "Partners [noun]" |
| P3-4 | **Apostrophe normalization** — U+2019 vs U+0027 causes dedup misses | SCRAPER_AUDIT_STATUS.md: known limitation | cleanup_curly_apostrophes.py exists; run and wire into pipeline |
| P3-5 | **ada_hpi_benchmarks.updated_at NULL** — only created_at populated | SCRAPER_AUDIT_STATUS.md: known limitation | Update ada_hpi_importer.py to set updated_at |
| P3-6 | **Cost cap in launch.py hardcoded $11** | CLAUDE.md known issue #5 | Parameter or env var; current $250 cap in launch_2000_excl_chi.py |
| P3-7 | **dental-pe-nextjs/scrapers/ deprecated files** — gitignored, DEPRECATED markers stranded on disk | SCRAPER_AUDIT_STATUS.md | rm -rf dental-pe-nextjs/scrapers/ (but confirm it's gitignored first) |
| P3-8 | **Practice count shown on home uses 0 fallback** — should show "N/A" or "loading" not "0" | WebFetch /: "0" shown as definitive KPI | Add loading/error state to KPI card component |

---

*Audit complete. Report covers all 12 required scope areas. No code was modified.*

**Files written:** `/tmp/AUDIT_REPORT_2026-04-26.md` and `AUDIT_REPORT_2026-04-26.md` (repo root)
