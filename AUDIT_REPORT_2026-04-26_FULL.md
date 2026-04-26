# Dental PE Tracker — Full System Audit (Manual, Read-Only)
**Date:** 2026-04-26
**Audit baseline SHA:** `520c33e` (`tier-2 phone re-promotion + cross-link helpers`)
**Audit window end SHA:** `f4b783f` (`fix(audit): location-level zip_scores + classification sync helper`)
**Audit window:** 2026-04-26 ~04:00Z → 2026-04-26 ~05:30Z (concurrent debug sessions live)
**Methodology:** 6 parallel domain-scoped agents (A=Ingestion, B=Enrichment, C=Storage, D=Frontend, E=Sync/Cache, F=Docs)
**Mode:** AUDIT-ONLY (no code changes by this session)

---

## Document Layout
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
16. [Appendix A: Real-Time Fix Verification Log](#appendix-a-real-time-fix-verification-log)
17. [Appendix B: Unknowns](#appendix-b-unknowns-by-agent)

---

## 1. Executive Summary

**Headline finding:** The "Frankenstein" perception is correct — the platform has six structurally distinct layers (sources → SQLite → Supabase → Next.js SSR → React Query → browser) and at least four of them have a known defect that is currently active or only just patched. **One commit during this audit window (`88d0668`, 04:46Z) reveals the root cause of the 2026-04-26 Supabase data wipe** the user reported as "stale data on live URL." It was not a caching failure — it was an Anthropic Haiku LLM emitting a 36-character `verification_quality` value into a `varchar(20)` column, which raised `StringDataRightTruncation` mid-INSERT, aborting the transaction after `TRUNCATE practices CASCADE` had already executed. That sequence left `practice_intel` and `practice_signals` both EMPTY in Supabase and caused Warroom / Launchpad / Buyability to time out and Job Market to show "0 practices tracked."

**The "GDN April 2026 excuse" is half-true.** GDN April 2026 is genuinely not yet published (3-5 week post-month-end lag is normal). But the staleness compounds across three additional unrelated upstream blocks:

1. **PESP migrated to Airtable iframes in Aug 2024.** `pesp_scraper.py:474` returns `"summary_only"` on iframe detection, marks 18 months as "expected empty." Recovery path `pesp_airtable_scraper.py::auto_ingest()` raises `NotImplementedError`. **540-1,440 PE deals are missing from your DB and only manual Airtable export per month can recover them.** This explains why max PESP `deal_date` is 2025-10-01.
2. **GitHub Actions weekly-refresh cron has the secret `SUPABASE_DATABASE_URL` missing.** When the April 25 GHA run found 7 GDN deals, the sync was skipped via the `if: env.SUPABASE_DATABASE_URL != ''` gate. The deals were discarded with the ephemeral runner.
3. **launchd weekly cron is dead** (last successful fire: 2026-04-19 16:45). macOS Sequoia LWCR stale-context bug. GHA replacement has only ever fired once on manual dispatch.

**The Warroom / Launchpad / dossier hallucination concern is justified but partially defended.** A 4-layer anti-hallucination defense (forced search, per-claim source URLs, self-assessment block, post-validation gate) was rolled out 2026-04-25 and validated 87% pass rate (174/200 stored, 26 quarantined, 0 hallucinations slipped through). HOWEVER:

- **223 of 2,013 practice dossiers (11%) predate the bulletproofing rollout** — they are Data-Axle-only synthetic-NPI (`DA_*`) practices and have NO verification block, NO `_source_url`, NO quarantine gate.
- **287 of 290 ZIP-level intel rows are synthetic placeholders** (`cost_usd=0`, `model_used=NULL`). Only 3 ZIPs have real research data. The Intelligence page KPIs imply broad coverage that doesn't exist.
- **Sonnet 2-pass escalation has NEVER fired** (`escalated=0` for all 2,013 rows). Either the threshold logic is wrong or the boolean isn't being set after Pass-2 merge.
- **31 dossiers passed validation despite `searches_executed=1`** when the spec requires ≥2.
- **`verification_quality` enum drift:** 10 rows have `"high"` (not in the spec enum `verified|partial|insufficient`). The validation gate accepts non-`insufficient` values, so `"high"` slipped through. (This is the same drift class that caused the data wipe with even-longer values.)

**The maps and visualizations contain at least one critical bug:** `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` colors dots by **legacy `ownership_status`** (5 values) rather than `entity_classification` (11 values). This violates the canonical "EC primary" rule documented in CLAUDE.md and causes visual classification disagreement across pages.

**The Next.js read path has one CRITICAL P0 pagination bug:** `getPracticeIntel()` in `dental-pe-nextjs/src/lib/supabase/queries/intel.ts:22-32` does NOT call `.range()`. Once the 2026-04-26 sync completes and Supabase has all 2,013 dossiers, the Intelligence page will silently drop 1,013 of them (Supabase caps at 1,000 rows/query). No error to user.

**Documentation drift is severe.** Of 11 entity-classification breakdown lines in CLAUDE.md, every one is wrong post-`520c33e` — some by huge margins (`non_clinical` doc 16 vs actual 743, `dso_regional` doc 109 vs actual 478, `solo_inactive` doc 170 vs actual 749, `specialist` doc 2,353 vs actual 1,429). Deal counts wrong (2,861 doc / 2,854 actual). Phantom files documented but not in code (`narrative-card.tsx`, `use-launchpad-narrative.ts`, `api/launchpad/narrative/`). 20+ scripts in `scrapers/` are not in the Quick Reference.

**The 14 sync resilience tests are BROKEN.** `scrapers/test_sync_resilience.py` fails to import `PracticeLocation` from `scrapers.database` (the test stub at line 43 is missing this symbol). All tests fail at collection time. CLAUDE.md still says "11 tests, all pass."

**Three real-time fixes landed during the audit window** (between 00:46Z and 00:50Z), validated against findings:
- `88d0668` (verification_quality varchar widen) — DIRECTLY FIXES Agent C's schema-conflict P0
- `3c1031a` (sitemap_jsonld scraper + Ideal Dental) — ADDRESSES Agent A H5 (10+ DSOs skipped). dso_locations count went 92 → 249.
- `f4b783f` (merge_and_score reads practice_locations + sync_practice_classification helper) — ADDRESSES Agent B B7 (Pass 3 still queried `practices` not `practice_locations`)

**Root-cause ranking** (most → least impactful for "why does it feel stale"):
1. 2026-04-26 Supabase wipe (now patched in `88d0668`, recovery sync complete)
2. PESP Airtable structural block (NOT FIXED, 18mo of deals lost without manual recovery)
3. GHA `SUPABASE_DATABASE_URL` missing secret (NOT FIXED — every CI run silently discards deals)
4. ADSO timeout escape (Python child survives SIGTERM 2h+ past 30m timeout — orphan logs)
5. `getPracticeIntel()` missing pagination (NOT FIXED — silent 1,013-row drop incoming)
6. `practice-density-map.tsx` uses legacy `ownership_status` (NOT FIXED)

---

## 2. Codebase Map

```
dental-pe-tracker/
├── dental-pe-nextjs/                    # Primary frontend (Next.js 16, React 19)
│   ├── src/app/                         # 10 pages: /, /launchpad, /warroom, /deal-flow,
│   │                                    #   /market-intel, /buyability, /job-market,
│   │                                    #   /research, /intelligence, /system
│   ├── src/app/api/                     # API routes: deals, practices, sql-explorer,
│   │                                    #   watched-zips, launchpad/* (6 routes:
│   │                                    #   ask, compound-narrative, contract-parse,
│   │                                    #   interview-prep, smart-briefing, zip-mood)
│   ├── src/lib/supabase/                # client.ts, server.ts, queries/{deals,practices,
│   │                                    #   zip-scores,watched-zips,practice-changes,
│   │                                    #   ada-benchmarks,system,intel,launchpad}.ts
│   ├── src/lib/launchpad/                # scope, signals, ranking, dso-tiers
│   ├── src/lib/warroom/                  # mode, scope, geo, signals, data, intent,
│   │                                    #   ranking, briefing
│   ├── src/lib/constants/                # entity-classifications, design-tokens,
│   │                                    #   colors, living-locations, metro-centers,
│   │                                    #   zip-centroids, sql-presets, deal-type-colors
│   ├── src/lib/utils/                    # formatting, scoring, csv-export, colors
│   ├── src/lib/hooks/                    # use-url-filters, use-sidebar, use-section-observer,
│   │                                    #   use-launchpad-state, use-launchpad-data,
│   │                                    #   use-warroom-state, use-warroom-data,
│   │                                    #   use-warroom-intel
│   ├── src/lib/types/                    # Deal, Practice, ZipScore, WatchedZip, etc.
│   ├── src/components/data-display/      # data-table (TanStack), kpi-card,
│   │                                    #   data-freshness-bar, section-header,
│   │                                    #   status-badge, status-dot, confidence-stars
│   ├── src/components/charts/            # Recharts wrappers
│   ├── src/components/maps/              # map-container (Mapbox GL wrapper)
│   ├── src/components/layout/            # sidebar (220px/60px collapsible),
│   │                                    #   warroom-cross-link
│   └── src/components/ui/                # shadcn primitives
│
├── dashboard/app.py                     # Streamlit (legacy) — 3,083 lines, 6 pages
│
├── scrapers/                            # Python pipeline
│   ├── database.py                      # SQLAlchemy models — 963 lines
│   ├── pipeline_logger.py               # JSONL event log — 295 lines
│   ├── logger_config.py                 # Logger factory
│   ├── refresh.sh                       # 11-step orchestrator — 126 lines
│   │
│   ├── # === Scrapers (data ingest) ===
│   ├── pesp_scraper.py                  # 1,201 lines — PESP HTML/iframe (BLOCKED Aug 2024+)
│   ├── pesp_airtable_scraper.py         # 1,201 lines — manual recovery (NotImplementedError)
│   ├── gdn_scraper.py                   # 1,210 lines — GDN monthly roundups
│   ├── pitchbook_importer.py            # 616 lines — manual CSV/XLSX
│   ├── adso_location_scraper.py         # 943 lines — DSO office crawler
│   ├── ada_hpi_downloader.py            # 237 lines — ADA benchmark XLSX
│   ├── ada_hpi_importer.py              # 351 lines — ADA HPI parser
│   ├── nppes_downloader.py              # 681 lines — federal provider data
│   ├── data_axle_importer.py            # 2,650 lines — 7-phase Data Axle pipeline
│   ├── data_axle_exporter.py            # 805 lines — interactive CLI
│   ├── data_axle_scraper.py             # web scrape variant
│   ├── data_axle_automator.py           # automation wrapper
│   │
│   ├── # === Classifiers / Scoring ===
│   ├── dso_classifier.py                # 1,570 lines — 3-pass classifier
│   ├── reclassify_locations.py          # 477 lines — location-level rewrite (KNOWN BUG)
│   ├── merge_and_score.py               # 1,074 lines — dedup + scoring
│   ├── compute_signals.py               # 1,424 lines — practice/zip signal materialization
│   │
│   ├── # === Sync ===
│   ├── sync_to_supabase.py              # 1,308 lines — 3 strategies, SIGTERM-aware
│   ├── fast_sync_watched.py             # 200 lines — partial sync (~14k watched rows)
│   ├── fast_sync_locations_and_scores.py # untracked — partial sync variant
│   ├── sync_practice_classification.py  # NEW (f4b783f) — focused EC backfill UPDATE helper
│   │
│   ├── # === Anti-hallucination AI layer ===
│   ├── research_engine.py               # 577 lines — Anthropic API client
│   ├── intel_database.py                # 266 lines — Intel CRUD
│   ├── qualitative_scout.py             # 380 lines — ZIP research CLI
│   ├── practice_deep_dive.py            # 577 lines — Practice research CLI
│   ├── weekly_research.py               # 504 lines — Batch API runner + validate_dossier
│   │
│   ├── # === Batch operations ===
│   ├── dossier_batch/
│   │   ├── launch.py                    # Top-1 per Chicagoland ZIP
│   │   ├── launch_2000_excl_chi.py      # 2000 non-606xx
│   │   ├── launch_2000_kendall_glenview_chi.py  # NEW (untracked)
│   │   ├── poll.py                      # Auto-retrieval poller
│   │   ├── poll_zip_batches.py          # ZIP intel poller
│   │   ├── upsert_practice_intel.py     # ON CONFLICT DO UPDATE path
│   │   └── migrate_verification_cols.py # Schema migration
│   │
│   ├── # === One-off / utility ===
│   ├── cleanup_pesp_junk.py             # 80 lines
│   ├── cleanup_curly_apostrophes.py
│   ├── backfill_last_names.py
│   ├── backfill_practices_classification.py # untracked
│   ├── cross_link_deals.py              # untracked
│   ├── cross_link_dso_locations.py      # untracked
│   ├── census_loader.py
│   ├── refine_residential.py
│   ├── upsert_practices_phaseB.py
│   ├── dedup_practice_locations.py
│   ├── assess_address_normalization.py
│   ├── audit_coverage.py
│   ├── directory_importer.py
│   ├── migrate_fast.py
│   ├── migrate_to_supabase.py
│   └── test_sync_resilience.py          # 14 tests — ALL BROKEN (ImportError)
│
├── data/
│   ├── dental_pe_tracker.db             # SQLite ~193MB (gzip-compressed for git)
│   ├── nppes/                           # March 2026 + March/April 2026 deltas
│   ├── pitchbook/                       # raw/ EMPTY since March 2026
│   ├── data_axle/                       # CSV exports
│   └── research_costs.json              # Rolling cost log (500 entries)
│
├── logs/
│   ├── pipeline_events.jsonl            # 480 lines, range 2026-03-07 → 2026-04-26
│   ├── refresh_*.log                    # Per-run pipeline output
│   ├── cron_refresh.log                 # last 2026-04-19 16:45
│   └── cron_nppes.log                   # last 2026-04-02 06:01
│
├── pipeline_check.py                    # 464 lines diagnostic CLI
├── schema_postgres.sql                  # HISTORICAL ARTIFACT (3 tables behind, 10 cols missing)
├── CLAUDE.md                            # 320+ lines — drift table in §11
├── scrapers/CLAUDE.md                   # subset — also drifted
├── dental-pe-nextjs/CLAUDE.md           # frontend subset — also drifted
│
├── .github/workflows/
│   ├── weekly-refresh.yml               # Sun 08:00 UTC — 1 successful manual run only
│   ├── keep-supabase-alive.yml          # Every 3d 12:00 UTC
│   ├── reaudit.yml                      # Read-only, 8 specific entries
│   ├── weekly-drift.yml                 # Mon 13:00 UTC, read-only
│   ├── audit-sweep.yml                  # 1st of month 13:00 UTC, read-only
│   └── auto-fix.yml                     # Trigger UNKNOWN
│
└── ~/Library/LaunchAgents/              # macOS launchd (DEAD)
    ├── com.dental-pe.weekly-refresh.plist  # Sunday 8am EDT — last fire 04-19
    ├── com.dental-pe.nppes-refresh.plist   # Day=1 6am — last fire 04-02
    └── com.dental-pe.session-fix.plist     # RunAtLoad
```

**Codebase size summary:**
- Python pipeline: ~25,000 lines across 40+ files in `scrapers/`
- Streamlit dashboard: 3,083 lines (single file)
- Next.js: ~24,000+ lines TypeScript/TSX across 10 routes + shared libs
- Total docs: ~7 audit/status MD files in repo root

---

## 3. Feature Inventory Table

### 3.1 Next.js Pages (10 routes)

| Route | Doc claims | Reality | Status |
|---|---|---|---|
| `/` Home | 6 KPI cards | 6 KPI cards (`home-shell.tsx:68-224`); but `dental-pe-nextjs/CLAUDE.md` says 8 — DRIFT | ✅ |
| `/` quick-nav | "2x3 (6 cards)" | 7 nav cards in grid-cols-3 (DRIFT) | ❌ |
| `/launchpad` KPI strip | "Comp range" | "Intel coverage" Phase 3 (root CLAUDE.md stale) | ⚠️ DRIFT |
| `/launchpad` dossier | 5 tabs | **6 tabs** (Snapshot, Comp, Mentorship, RedFlags, InterviewPrep, ContractParser) | ❌ DRIFT |
| `/launchpad` scopes | 4 | **8** (4 Chicagoland + 4 Boston Phase 3) | ❌ DRIFT |
| `/launchpad` saved searches | documented | DELETED in Phase 3 | ❌ PHANTOM |
| `/launchpad` AI routes | "compound-narrative only" | 6 routes (ask, compound-narrative, contract-parse, interview-prep, smart-briefing, zip-mood) | ❌ DRIFT |
| `/warroom` modes | 2 | 2 (Hunt/Investigate) | ✅ |
| `/warroom` lenses | 4 | 4 (consolidation, density, buyability, retirement) | ✅ |
| `/warroom` scopes | 11 | 11 (chicagoland, 7 subzones, 3 saved presets) | ✅ |
| `/warroom` Sitrep KPIs | — | 12 KPI cards in xl:grid-cols-6 | ✅ |
| `/warroom` keyboard shortcuts | "?, ⌘K, /, 1, 2, R, P, V, [, ], Esc" | All confirmed in `warroom-shell.tsx` | ✅ |
| `/deal-flow` tabs | 4 | 4 (Overview, Sponsors, Geography, Deals) | ✅ |
| `/market-intel` tabs | 3 | 3 (Consolidation, ZIP Analysis, Ownership) | ✅ |
| `/market-intel` consolidation map | XSS-escaped | `escapeHtml()` confirmed (fix from 2026-04-05) | ✅ |
| `/buyability` filter | "watched-ZIPs only" | restrict to watched ZIPs (`page.tsx:18-20`, changed 2026-04-26) | ✅ NEW |
| `/buyability` acquisition_target | "≥50 score" | **ALL other independents (no threshold)** in `categorize()` | ❌ DRIFT |
| `/job-market` tabs | 4 | 4 (Overview, Map, Directory, Analytics) | ✅ |
| `/job-market` Practice density map | colored by EC | **colored by legacy `ownership_status`** | ❌ BUG |
| `/intelligence` KPIs | 6 | 6 KPI cards | ✅ |
| `/intelligence` real intel | "23 of 401k" | actually 2,013 in SQLite (doc stale) | ❌ DRIFT |
| `/research` tabs | 4 | 4 — but ResearchShell does NOT receive deals count, any deal KPI = 0 | ⚠️ BUG |
| `/system` ADSO/ADA freshness | — | `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at` (fixed 2026-04-22) | ✅ |

### 3.2 Streamlit Pages (Legacy)

| Page | Status |
|---|---|
| Deal Flow / Market Intel / Buyability / Job Market / Research / System | Live at suleman7-pe.streamlit.app — uses primarily `ownership_status`, EC supplemental |
| WebFetch result | HTTP 303 — render UNKNOWN |

### 3.3 Anti-Hallucination Defense (4 layers)

| Layer | Location | Status |
|---|---|---|
| L1 force_search=True | `research_engine.py:197,237` | ✅ |
| L1 ZIP path force_search | `research_engine.py:302-303` | ✅ FIXED (was missing) |
| L1 JOB_HUNT path force_search | `research_engine.py:344` | ✅ FIXED (was missing) |
| L2 PRACTICE_USER `_source_url` schema | `research_engine.py:117-118` | ✅ |
| L3 Terminal verification block | mandatory | ✅ |
| L4 validate_dossier 5 rejection rules | `weekly_research.py:113-155` | ⚠️ See §10 |
| Quarantine gate | `weekly_research.py:259-261` | ✅ |
| `--sync-only` bypass (was leak) | removed | ✅ FIXED |
| Pass-2 escalation | `practice_deep_dive.py` | ❌ NEVER FIRES — escalated=0 for all 2,013 rows |

---

## 4. Pipeline Health Matrix

### 4.1 Scraper Reality (18 scrapers)

| Scraper | Last Run (UTC) | Last Success | Status | Concern |
|---|---|---|---|---|
| pesp_scraper | 2026-04-23T19:51:48 | "0 new, 142 dupes" | ⚠️ SOURCE BLOCK | Airtable migration since Aug 2024 |
| pesp_airtable_scraper | NEVER RUN | — | ❌ NotImplementedError | 540-1,440 missing PE deals |
| gdn_scraper | 2026-04-25T15:08:39 | "0 new, 2272 dupes" | ✅ working, source latency only | April 2026 not yet published |
| pitchbook_importer | 2026-04-22T23:03:36 | "No files" | ⚠️ MANUAL | data/pitchbook/raw/ empty since March |
| adso_location_scraper | 2026-04-26T00:36:22 | ORPHAN | ❌ TIMEOUT ESCAPE | 2h past 30m timeout, no complete event |
| ada_hpi_downloader | 2026-04-25T15:05:31 | ORPHAN (no complete) | ⚠️ | `created_at` populated, `updated_at` IS populated (DOC SAYS NULL) |
| ada_hpi_importer | 2026-04-23T19:59:02 | "918 updated from 3 files" | ✅ | |
| dso_classifier | 2026-04-24T18:01:37 | "306 changes" | ✅ | But DOC says 547 lines / actual 1,570 |
| merge_and_score | 2026-04-26T00:32:08 | dedup={'total_deals':2854} | ✅ | Now reads `practice_locations` (f4b783f) |
| weekly_research | 2026-04-04T07:00:06 | $5 budget | ❌ 22 DAYS STALE | Auto-runner not firing |
| compute_signals | 2026-04-25T13:26:20 | materialization complete | ✅ | NPI null guard verified |
| sync_to_supabase | 2026-04-26T00:15:25 | ORPHAN | ⚠️ See E2 below | Was the data-wipe trigger |
| nppes_downloader | 2026-04-24T17:59:22 | "1142 dental, 359 new" | ⚠️ MANUAL ONLY | Cron last fired April 1 |
| data_axle_importer | 2026-04-24T18:07:31 | 6 ORPHANS in 6 minutes | ❌ CRASH PATTERN | Repeated rapid-fire orphan starts |

### 4.2 Sync History (last 14d)

- 67 sync starts, 29 completes, 2 errors, 38 orphan starts
- 22-start orphan storm 2026-04-25 12:54-14:18 (rapid debug session displaced by file lock /tmp/dental-pe-sync.lock)
- 2026-04-24T08:01:08 complete with NO matching start (duration 9162s = 2.5h, origin UNKNOWN)
- 2026-04-26T00:15:25 sync = OPEN ORPHAN at audit baseline (this was the data-wipe sync that aborted on `verification_quality` truncation; recovery sync followed by `88d0668` at 00:46Z)

### 4.3 Pipeline Events Log

- File: `logs/pipeline_events.jsonl`
- Lines: 480 (auto-rotates at 1000)
- Range: 2026-03-07 → 2026-04-26
- JSON field: `"event"` (NOT `"event_type"` as some docs imply)

### 4.4 Confirmed Orphan Starts (5)

1. `adso_scraper` 2026-04-19T14:44:30 (3-day gap)
2. `ada_hpi_downloader` 2026-04-25T15:05:31
3. `sync_to_supabase` 9 rapid orphans 2026-04-25 13:55-14:30
4. `data_axle_importer` 6 orphans 2026-04-24 18:01-18:07
5. `adso_scraper` 2026-04-26T00:36:22

---

## 5. Scheduled Job Table

### 5.1 launchd (3 plists at `~/Library/LaunchAgents/`)

| Plist | Schedule | Last Fire | Status |
|---|---|---|---|
| `com.dental-pe.weekly-refresh` | Weekday=0 Hour=8 (no TZ → EDT) | 2026-04-19 16:45 | ❌ DEAD (macOS Sequoia LWCR bug) |
| `com.dental-pe.nppes-refresh` | Day=1 Hour=6 | 2026-04-02 06:01 | ⚠️ Last April 1 fire correct, May 1 untested |
| `com.dental-pe.session-fix` | RunAtLoad=True | On macOS login | ✅ bootout+bootstrap |

### 5.2 GitHub Actions (6 workflows)

| Workflow | Schedule | Status |
|---|---|---|
| weekly-refresh.yml | Sun 08:00 UTC | **1 manual dispatch only — NEVER fired on cron**. `if: env.SUPABASE_DATABASE_URL != ''` gate causes silent sync skip |
| keep-supabase-alive.yml | Every 3d 12:00 UTC | Apr 25 cron FAILED, Apr 25 manual dispatches succeeded → secrets likely added between |
| reaudit.yml | 8 dated entries through 2026-05-09 | Read-only |
| weekly-drift.yml | Mon 13:00 UTC | Read-only |
| audit-sweep.yml | 1st of month 13:00 UTC | Read-only |
| auto-fix.yml | UNKNOWN trigger | NOT EXAMINED |

### 5.3 refresh.sh (11 steps, 126 lines)

```
[1] DB backup
[2] PESP 15m
[3] GDN 15m
[4] PitchBook 5m
[5] ADSO 30m
[6] ADA-HPI 10m
[7] DSO Pass1+2 15m
[7b] DSO Pass3 20m
[8] Merge+Score 10m
[9] Weekly Research 15m (conditional)
[10] Signals 10m
[11] Sync 30m (conditional)
[POST] Compress + git push
```

`run_step()` at lines 31-64: `pkill -TERM -P $bgpid` then `-KILL` after 30s grace. Exit 124 on timeout = WARNING + Continuing.

**Timeout escape (CONFIRMED ONGOING):** April 19 PESP ran 4h 4m past 15m timeout; GDN ran 2h 2m; ADSO orphan still logging Tend pages 2h+ past 30m. Python child has no SIGTERM handler in HTTP request loop.

---

## 6. Database Integrity

### 6.1 Schema Source-of-Truth Drift

**16 tables in SQLite vs schema_postgres.sql vs SQLAlchemy:**

- **Missing from `schema_postgres.sql`:** `practice_signals`, `zip_signals`, `practice_locations`
- **Missing from SQLAlchemy:** `sync_metadata` (Supabase-only)

### 6.2 Critical Column Divergences

1. **`practices.buyability_confidence`** — present in SQLite + `schema_postgres.sql`; **MISSING from SQLAlchemy `Practice` model** (`database.py:95-148`)
2. **`practice_intel`** — Migration `2026_04_24_launchpad_jobhunt_columns.sql` adds 10 cols (`succession_intent_detected`, `new_grad_friendly_score`, `mentorship_signals`, `associate_runway`, `compensation_signals`, `red_flags_for_grad`, `green_flags_for_grad`, `verification_searches`, `verification_quality`, `verification_urls`) — **all missing from `schema_postgres.sql`**
3. **`verification_quality` TYPE** — Was `String(64)` SQLAlchemy / `varchar(20)` Postgres / spec values verified|partial|insufficient (max 12 chars). **Caused 2026-04-26 data wipe** when Haiku emitted "sufficient to identify data mismatch" (36 chars). FIXED by `88d0668` at 04:46Z: ALTER TABLE Postgres + SQLAlchemy widened to varchar(64). ✅
4. **`zip_scores.corporate_highconf_count`** — queried by `launchpad.ts:154`; **MISSING from SQLAlchemy `ZipScore` model** (`database.py:236-288`); UNKNOWN in Supabase
5. **`practice_signals` / `zip_signals.created_at` TYPE MISMATCH** — SQLite stores TEXT, SQLAlchemy expects DateTime (`database.py:499,556`)
6. **`practice_locations`** — `buyability_score` / `classification_confidence` / `estimated_revenue` stored as INTEGER in SQLite, should be Float — silent precision truncation

### 6.3 Sync Strategy Map (sync_to_supabase.py:130-155)

| Table | Strategy | Conflict | Filter |
|---|---|---|---|
| practices | watched_zips_only | npi | watched_zips |
| deals | incremental_updated_at | id | — |
| practice_changes | incremental_id | id | filter_watched_zips |
| zip_scores, watched_zips, dso_locations, ada_hpi_benchmarks, pe_sponsors, platforms, zip_overviews, zip_qualitative_intel | full_replace | None | — |
| practice_intel | full_replace | None | filter_watched_zips_npi |
| practice_signals | full_replace | None | filter_watched_zips_npi |
| zip_signals, practice_locations | full_replace | None | — |

### 6.4 SQLite ↔ Supabase Parity (CRITICAL)

| Table | SQLite | Supabase | Drift |
|---|---|---|---|
| practices | 402,004 | 14,053 | INTENDED (watched_zips filter) |
| practice_intel | 2,013 | ~400 → recovered to 2,013 (post-88d0668) | RESOLVED |
| practice_signals | populated | wiped → recovered to 14,053 (post-88d0668) | RESOLVED |
| deals | 2,854 | 2,861 | 7-row ghost surplus (incremental_updated_at NEVER deletes) |

**`_reconcile_deals` function (commit ac2140a)** — CLAUDE.md and commit message reference it but **function NOT FOUND** in `merge_and_score.py` (1,074 lines searched). The 25-row ghost cleanup was a one-off SQL/script, not a reusable function. Cannot re-run reconciliation programmatically.

### 6.5 Freshness Field Audit

| Column | Status |
|---|---|
| `practices.created_at`, `updated_at` | ✅ populated |
| `deals.created_at`, `updated_at` | ✅ populated |
| `practice_changes.created_at` | ✅ populated |
| `zip_scores.score_date` (DATE) | ✅ |
| `zip_scores.updated_at`, `created_at` | ❌ MISSING IN SCHEMA |
| `ada_hpi_benchmarks.created_at` | ✅ MAX 2026-03-07 |
| `ada_hpi_benchmarks.updated_at` | ✅ NOW POPULATED MAX 2026-04-23 23:59:01 — **DOC DRIFT (CLAUDE.md says NULL)** |
| `dso_locations.scraped_at` | ✅ |
| `zip_qualitative_intel.created_at`, `updated_at` | ✅ |
| `practice_intel.created_at`, `updated_at` | ✅ |
| `practice_signals` / `zip_signals.created_at` | ⚠️ stored as TEXT |
| `practice_locations.created_at`, `updated_at` | ✅ DATETIME |

### 6.6 Orphan + Duplicate Audit

- `practice_signals` orphan_count = 0 (eb75c6c filter + NPI null guard)
- CASCADE trap from `TRUNCATE practices CASCADE` wipes `practice_changes`, `practice_intel`, `practice_signals` — handled by `sync_metadata` reset at lines 824-831
- `practice_locations` dedup: 5,732 rows (deduped from 14,053 NPIs); key=(normalized_address, zip), `is_likely_residential` filter

### 6.7 BROKEN TESTS

`scrapers/test_sync_resilience.py` — **14 tests ALL FAIL** at collection time:
```
ImportError: cannot import name 'PracticeLocation' from 'scrapers.database'
```
Test stub at line 43 missing `PracticeLocation` symbol. CLAUDE.md still says "11 tests, all pass."

---

## 7. Data Flow Diagrams

### 7.1 Ingest → Storage → Frontend

```
[Federal/Web Sources]
    │
    ├── PESP HTML  ────────► pesp_scraper.py ────► (BLOCKED Aug 2024+) ──┐
    │                                                                     │
    ├── PESP Airtable ───── pesp_airtable_scraper.py (NotImplementedError)│
    │                                                                     │
    ├── GDN posts  ────────► gdn_scraper.py     ────►                     │
    │                                                                     │
    ├── PitchBook CSV ─────► pitchbook_importer.py (manual only) ─────────┤
    │                                                                     │
    ├── ADSO sites ────────► adso_location_scraper.py (TIMEOUT ESCAPE)    │
    │                                                                     │
    ├── ADA HPI XLSX ──────► ada_hpi_importer.py ────►                    │
    │                                                                     │
    ├── NPPES ZIP ─────────► nppes_downloader.py (manual only) ───────────┤
    │                                                                     │
    └── Data Axle CSV ─────► data_axle_importer.py (CRASH PATTERN) ───────┤
                                                                          ▼
                                                          ┌─────────────────────┐
                                                          │ data/dental_pe_     │
                                                          │   tracker.db        │
                                                          │   (SQLite ~193MB)   │
                                                          └─────────┬───────────┘
                                                                    │
                              ┌─────────────────────────────────────┤
                              │                                     │
                              ▼                                     │
                  dso_classifier.py 3-pass                          │
                  merge_and_score.py                                │
                  compute_signals.py                                │
                  weekly_research.py (Anthropic Batch API)          │
                              │                                     │
                              ▼                                     │
                  ┌────────────────────┐                            │
                  │ practice_intel     │  ←── 4-layer anti-halluc   │
                  │ zip_qualitative_   │       defense              │
                  │   intel            │                            │
                  │ practice_signals   │                            │
                  │ zip_signals        │                            │
                  │ practice_locations │                            │
                  │ zip_scores         │                            │
                  └────────┬───────────┘                            │
                           │                                        │
                           ▼                                        │
                  sync_to_supabase.py                               │
                  fast_sync_watched.py                              │
                  sync_practice_classification.py (NEW f4b783f)     │
                           │                                        │
                           ▼                                        ▼
                  ┌─────────────────────┐              gzip → git push
                  │ Supabase Postgres   │                     │
                  │ (Vercel-facing)     │                     ▼
                  └────────┬────────────┘          Streamlit Cloud
                           │
                ┌──────────┴────────┐
                ▼                   ▼
       Next.js Server         Browser (React Query 30min staleTime)
       Components (SSR
       force-dynamic on
       all 10 pages)
```

### 7.2 Caching Layers (L0–L6)

```
L0  Source scraper (weekly cron)
     │
     ▼
L1  SQLite → Supabase sync (incremental_updated_at watermark)
     │
     ▼
L2  Supabase Postgres (pgBouncer port 6543, statement_timeout 600s)
     │
     ▼
L3  Next.js Server fetch (force-dynamic on ALL 10 page.tsx)
     │
     ▼
L4  Vercel Edge/CDN (next.config.ts EMPTY, no headers, no middleware)
     │
     ▼
L5  React Query (TanStack: 30min staleTime, 30min gcTime, retry:1)
     │
     ▼
L6  Browser HTTP (no Cache-Control)
```

**Zero anti-patterns.** No `cache()`, `unstable_cache`, `revalidatePath`, `revalidateTag`, `'use cache'`, `{cache:'...'}`, `{next:{...}}` anywhere. The "stale data" symptom is purely upstream.

### 7.3 Anti-Hallucination Pipeline

```
weekly_research.py
       │
       ▼
research_engine.py::_call_api(force_search=True, max_searches=5)
       │  tool_choice = {"type": "tool", "name": "web_search"}
       ▼
Anthropic Haiku 4.5 (Batch API, 50% token discount)
       │
       │  Output: PRACTICE_USER schema with _source_url per section + verification block
       ▼
Anthropic returns batch results
       │
       ▼
weekly_research.py::retrieve_batch()
       │
       ▼
validate_dossier(npi, data) → (ok, reason)
       │  5 rules:
       │    1. missing_verification_block
       │    2. insufficient_searches(N<2)
       │    3. evidence_quality=insufficient
       │    4. website.url_without_source
       │    5. google.metrics_without_source
       ▼
   PASS │      FAIL
       │      │
       ▼      ▼
intel_database.py::store_practice_intel()    QUARANTINED (not stored)
       │
       ▼
practice_intel table (SQLite)
       │
       ▼
sync_to_supabase.py (full_replace + filter_watched_zips_npi)
       │
       ▼
Supabase practice_intel
```

---

## 8. Frontend Audit

### 8.1 Page-by-Page Reality

#### `/` Home
- **6 KPI cards** (`home-shell.tsx:68-224`) — DRIFT vs `dental-pe-nextjs/CLAUDE.md` saying 8
- **7 nav cards in grid-cols-3** — DRIFT vs CLAUDE.md "2x3 (6 cards)"
- Live values: Tracked Clinics 5,265 GP / 14,053 NPI subtitle, PE Deals 2,895, Corporate 322 (1.7% high-conf), Retirement 226, Acquisition 34
- Deal-flow-stale banner at `home-shell.tsx:229-238` fires when `lastNewDealDate > 30d` ago

#### `/launchpad`
- KPI strip: 6 cards (`launchpad-kpi-strip.tsx:53-145`). "Comp range" REPLACED by "Intel coverage" Phase 3
- **6-tab dossier** (Snapshot/Comp/Mentorship/RedFlags/InterviewPrep/ContractParser) — DRIFT vs both CLAUDE.mds saying 5
- **8 scopes** (4 Chicagoland + 4 Boston Metro) — DRIFT vs root CLAUDE.md saying 4
- Saved searches DELETED in Phase 3 (still in CLAUDE.md)
- 6 AI routes under `/api/launchpad/`: narrative, ask, compound-narrative, interview-prep, zip-mood, contract-parse, smart-briefing — all 503 if no `ANTHROPIC_API_KEY`

#### `/warroom`
- Sitrep 12 KPI cards in xl:grid-cols-6 (`sitrep-kpi-strip.tsx:47-223`)
- 2 modes (Hunt/Investigate); Profile + Sitrep standalone CUT in Phase 2
- 4 lenses; pe_exposure/saturation/whitespace/disagreement CUT
- 11 scopes (chicagoland, 7 subzones, 3 saved presets); US scope cut
- Keyboard shortcuts confirmed in `warroom-shell.tsx`: `?`, `⌘K`, `/`, `1`, `2`, `R`, `P`, `V`, `[`, `]`, `Esc`
- Practice dedup at `warroom.ts:375` via `dedupPracticesByLocation()`
- "Signal sync pending" appears when `signalCounts` is null

#### `/deal-flow`
- 4 tabs (Overview/Sponsors/Geography/Deals)
- Supabase has 2,895 deals (vs SQLite 2,861 = +34 ghost rows per docs; actual SQLite now 2,854)

#### `/market-intel`
- 3 tabs; 11 parallel count queries on `practice_locations`
- Tiered KPIs: high-conf headline, all-signals secondary
- Consolidation map: raw Mapbox GL JS, XSS-escaped via `escapeHtml()`, 0%→green/15%→amber/30%→red
- Warroom cross-link banner href: `?mode=hunt&lens=consolidation`

#### `/buyability`
- **Changed 2026-04-26** to restrict to watched ZIPs (`page.tsx:18-20`)
- `categorize()` at `buyability-shell.tsx:~40-65`: `acquisition_target` = ALL other independents (NO score threshold)
- DRIFT: `dental-pe-nextjs/CLAUDE.md` says ≥50 — only true for Home/Warroom counts, not buyability page

#### `/job-market`
- 4 tabs, 9 KPIs with tiered display
- **CRITICAL BUG**: `practice-density-map.tsx` uses `ownership_status` for dot colors, NOT `entity_classification`. Violates "EC primary" rule.
- Retirement Risk 156 vs Home/Warroom 226 — different ZIP scope (Chicagoland commutable vs all 290 watched)

#### `/intelligence`
- 6 KPI cards
- Per `dental-pe-nextjs/CLAUDE.md`: "23 of 401k practices have real practice_intel"; "258 of 290 zip_qualitative_intel are synthetic placeholders" (actual: 287/290)
- VerificationBadge coerces "high" enum drift → "Partial"
- Warroom cross-link href: `?mode=investigate&lens=consolidation`

#### `/research`
- 4 tabs; ResearchShell receives sponsors[]/platforms[]/states[] but NOT deal count
- Any "Total deals" KPI here would render 0
- SQL Explorer requires `execute_sql` RPC in Supabase

#### `/system`
- ADSO + ADA HPI freshness fixed 2026-04-22 — reads `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at`

### 8.2 Pagination Coverage

| Function | Table | Paginated? | Risk |
|---|---|---|---|
| getPracticesByZips | practices | ✅ `.range()` | safe |
| getPracticesWithCoords | practices | ✅ chunked 100 ZIPs | safe |
| getPracticeStats | practice_locations | count-only | safe |
| fetchAllPracticesByZips (launchpad) | practices | ✅ 1000/page | safe |
| fetchPracticeIntel (launchpad) | practice_intel | ✅ batched 500 NPIs | safe |
| **getPracticeIntel (intel.ts:22-32)** | **practice_intel** | **❌ NO PAGINATION** | **CRITICAL P0** |
| getZipIntel (intel.ts:10-19) | zip_qualitative_intel | NO | safe (290 rows) |
| getCompletenessMetrics (system.ts:292-368) | practices | count queries | denominator bug (watched not global) |

**`getPracticeIntel()` P0 BUG:** Once Supabase has 2,013 dossiers, the Intelligence page silently shows only 1,000 (most recent), drops 1,013. No error to user. Supabase caps at 1,000 rows/query.

### 8.3 Cross-Page Consistency

| Metric | Home | Job Market | Market Intel | Warroom |
|---|---|---|---|---|
| Total clinics | 5,265 GP / 14,053 NPI | 14,053 NPI / 5,265 GP | 14,053 | scope subset |
| High-conf corporate % | 1.7% | 1.9% (POSSIBLY STALE STRING) | 1.7% | scope-specific |
| Retirement Risk | 226 | 156 (smaller ZIP scope) | n/a | scope-specific |
| Acquisition Targets | 34 (≥50) | n/a | n/a | 34 (≥50) |
| PE Deals | 2,895 | n/a | n/a | n/a |

Buyability page `acquisition_target` = ALL other independents (different definition than Home/Warroom).

### 8.4 URL State Sync

| Page | Hook | Method | Param Count | Persistence |
|---|---|---|---|---|
| Warroom | use-warroom-state.ts | replace+debounce 150ms | 8 | localStorage fallback |
| Launchpad | use-launchpad-state.ts | replace | 7 | URL only; ZIP `/^\d{5}$/` regex |
| Research | research-shell.tsx | push | 1 | URL only |
| Generic | use-url-filters.ts | push | varies | URL only |

Warroom invalid scope IDs silently default to `chicagoland` with no error to user.

### 8.5 React Query Setup

Default: `staleTime=30min`, `gcTime=30min`, `refetchOnWindowFocus=false`, `retry=1`
- `use-warroom-data`: 5min staleTime override
- `use-launchpad-data`: 5min staleTime override
- All hooks compliant with Supabase 1000-row limit (paginate or chunk) — except `getPracticeIntel()` (see §8.2)

---

## 9. Map Reality Check

### 9.1 Map 1: Warroom Living Map
- `react-map-gl/mapbox` Source/Layer/Marker/Popup
- Lens computations in `LENS_COMPUTATIONS` (`living-map.tsx:47-76`)
- **Retirement lens reads `zipSignal.retirement_combo_high_count`** — silently shows all gray if signals fail to load (no UI feedback)

### 9.2 Map 2: Market Intel Consolidation Map
- Raw Mapbox GL JS (NOT react-map-gl)
- Corporate count = `corporate_share_pct * total_gp_locations`
- 3-tier: 0%→green / ≥15%→amber / ≥30%→red
- XSS-escaped via `escapeHtml()` (fixed 2026-04-05) ✅

### 9.3 Map 3: Job Market Practice Density Map ❌
- react-map-gl + deck.gl
- **BUG**: `STATUS_COLORS` keyed on legacy `ownership_status` values (`independent`/`likely_independent`/`dso_affiliated`/`pe_backed`/`unknown`) NOT `entity_classification`
- Violates documented "EC primary" rule
- Causes visual inconsistency with other pages

### 9.4 Map 4: Deal Flow State Choropleth
- Mapbox GL JS, state-level aggregation — wired correctly ✅

### 9.5 ZIP Centroid Spot Check (5/289)
- 60491 [41.6, -87.96] ✓
- 60439 [41.71, -87.98] ≈ ✓
- 60540 [41.77, -88.14] ✓
- 60022 [42.13, -87.76] ✓
- 60601 [41.89, -87.62] ✓

---

## 10. Hallucination Audit

### 10.1 Coverage Reality

| Table | Total | Real Research | Synthetic / Pre-Bulletproof |
|---|---|---|---|
| `practice_intel` SQLite | 2,013 | 1,790 | **223 DA_-prefix synthetic NPIs** (predate bulletproofing) |
| `zip_qualitative_intel` | 290 | 3 | **287 synthetic placeholders** (cost_usd=0, model_used=NULL) |

The 223 DA_-prefix rows have NO verification block, NO `_source_url`, NO quarantine gate — verified by spot-check of `bbk5593vw.output`: `DA_a1e15c67031b` (Smile More Today / Vernon Hills) has NO `verification` block, NO per-section `_source_url`, only flat fields.

### 10.2 Validation Gate (weekly_research.py:113-155)

5 spec rules:
1. `missing_verification_block` (line 129)
2. `insufficient_searches(N<2)` (line 137)
3. `evidence_quality=insufficient` (line 147)
4. `website.url_without_source` (line 151)
5. `google.metrics_without_source` (line 155)

### 10.3 Validation Gate Defects

- **31 rows passed validation with `searches_executed=1`** despite spec requiring ≥2
- **Verification_quality enum drift:** 10 rows have `"high"` (not in spec enum verified|partial|insufficient)
- Anomalous strings observed: `"4th search failed due to token limit"` in search_queries arrays
- Gate accepts non-`insufficient` quality values, so `"high"` slips through
- **The "verification_quality" drift class also caused the 2026-04-26 data wipe** (Haiku emitted 36-char value, overflowed varchar(20)). Fixed by `88d0668` widen to varchar(64) but **upstream prompt drift not solved**.

### 10.4 Two-Pass Escalation FAILURE

- **`escalated=0` for ALL 2,013 rows** — Sonnet escalation has NEVER fired
- Escalation logic at `practice_deep_dive.py` triggers when `readiness=high|medium AND confidence != high` OR 3+ green flags
- Either: (a) escalation thresholds too strict, or (b) `escalated` boolean not being set after Pass 2 merge
- **Cost analysis:** $0.075/practice baseline × 2,013 = $151. If escalation worked at expected ~10% rate, cost would be ~$200. Current spend reflects only Pass 1.

### 10.5 Per-Practice Cost Calibration

- Bulletproofed run: ~$0.075/practice (4-5 forced searches × $0.01 + cache_create)
- Validated 200-practice batch (msgbatch_017YJJ2M3WbLv4Q7gEhubK2o): 87% pass rate (174 stored / 26 quarantined), 854 forced searches (avg 4.27/practice), $14.91 cost
- 2026-04-25 batch `msgbatch_01A3FxKxKxemAyqDr2AcGYUq` — 2,000 non-606xx practices submitted; result rolled into the 2,013 SQLite count

---

## 11. Documentation Drift Log

### 11.1 Entity-Classification Breakdown (CRITICAL — every line wrong)

| Classification | CLAUDE.md says | Actual SQLite | Drift |
|---|---|---|---|
| solo_established | 3,575 | 2,729 | -846 |
| small_group | 2,727 | 2,859 | +132 |
| large_group | 2,456 | 2,418 | -38 |
| **specialist** | 2,353 | **1,429** | **-924** |
| family_practice | 1,708 | 1,351 | -357 |
| solo_high_volume | 709 | 876 | +167 |
| **solo_inactive** | 170 | **749** | **+579** |
| **dso_regional** | 109 | **478** | **+369** |
| dso_national | 213 | 404 | +191 |
| **non_clinical** | 16 | **743** | **+727** |
| solo_new | 17 | 17 | ✅ |

Classifier was re-run by commit `520c33e`, invalidating every breakdown line. Doc not refreshed.

### 11.2 Deal Counts

| Metric | Doc | Actual |
|---|---|---|
| Total deals SQLite | 2,861 | **2,854** |
| Total deals Supabase | 2,861 | 2,861 (7-row ghost) |
| GDN | 2,532 | **2,515** |
| PESP | 353 | **329** |
| PitchBook | 10 | 10 ✅ |

### 11.3 File Line-Count Drift

| File | Doc | Actual | Δ |
|---|---|---|---|
| dashboard/app.py | 2,583 | 3,083 | +500 |
| scrapers/database.py | 542 | 963 | +421 |
| scrapers/dso_classifier.py | 547 | **1,570** | **+1,023** |
| scrapers/merge_and_score.py | 719 | 1,074 | +355 |
| scrapers/research_engine.py | 400 | 577 | +177 |
| scrapers/pesp_scraper.py | 552 | 1,201 | +649 |
| scrapers/gdn_scraper.py | 720 | 1,210 | +490 |
| scrapers/adso_location_scraper.py | 728 | 943 | +215 |
| scrapers/weekly_research.py | 309 | 504 | +195 |
| pipeline_check.py | 540 | 464 | -76 |

### 11.4 Phantom Documentation (referenced but not in code)

1. `narrative-card.tsx`, `use-launchpad-narrative.ts`, `api/launchpad/narrative/route.ts` — all 3 referenced in `dental-pe-nextjs/CLAUDE.md`, **none exist**. Superseded by `compound-thesis.tsx` + `compound-narrative` route.
2. `use-launchpad-saved-searches.ts` — referenced; deleted in Phase 3
3. `_verify_table_count()` function — inline checks only, no named function
4. `scrapers/CLAUDE.md` says **408** dso_locations — actual **92** (now 249 post-3c1031a)
5. CLAUDE.md src/app/api/ section lists ONLY `compound-narrative` route — 5 other launchpad routes exist

### 11.5 Scripts In-Code But NOT in CLAUDE.md Quick Reference (20+)

`pesp_airtable_scraper.py`, `assess_address_normalization.py`, `audit_coverage.py`, `backfill_last_names.py`, `backfill_practices_classification.py` (untracked), `census_loader.py`, `cleanup_curly_apostrophes.py`, `cross_link_deals.py` (untracked), `cross_link_dso_locations.py` (untracked), `data_axle_automator.py`, `data_axle_scraper.py`, `dedup_practice_locations.py`, `directory_importer.py`, `fast_sync_locations_and_scores.py` (untracked), `migrate_fast.py`, `migrate_to_supabase.py`, `reclassify_locations.py` (477 lines), `refine_residential.py`, `sync_practice_classification.py`, `upsert_practices_phaseB.py`, `test_sync_resilience.py`

### 11.6 Audit-Document Lineage

| Doc | Status |
|---|---|
| AUDIT_REPORT_2026-04-26.md (auto Sonnet 4.6 GHA) | Reading from STALE context — citations don't match current CLAUDE.md |
| AUDIT_REPORT_2026-04-25.md | Most comprehensive predecessor |
| FIX_REPORT_2026-04-25.md | Items §15 #2-4 mostly RESOLVED; #1 awaiting user |
| SCRAPER_AUDIT_STATUS.md | Closed 2026-04-22 23:05 — does NOT reflect April 25 work |
| NPI_VS_PRACTICE_AUDIT.md | Records `dc18d24` dedup; `reclassify_locations.py` known bug |
| ADSO_CROSSCHECK_CHECKPOINT.md | Documents "37% of real DSO locations leak into independent buckets" |

### 11.7 SIGTERM Checkpoints

CLAUDE.md says "8 checkpoints" — actual is **11** (lines 421, 479, 583, 594, 633, 641, 712, 801, 838, 1156, 1223 + declaration at 74 + handler at 79).

---

## 12. Symptom Diagnosis

### 12.1 "Live URL keeps showing stale data"

**Root cause: 2026-04-26 Supabase data wipe** (now fixed by `88d0668` at 04:46Z).

Sequence of events:
1. Sync started 2026-04-26T00:15:25 (still orphan at audit baseline)
2. `TRUNCATE practices CASCADE` executed — wiped `practice_intel` + `practice_signals`
3. Re-INSERT into `practice_intel` hit `StringDataRightTruncation` on row N because Anthropic Haiku emitted free-form `verification_quality` values ("sufficient to identify data mismatch" 36 chars, "verified - MISMATCH DETECTED" 28 chars, "insufficient_for_requested_classification" 41 chars) into a `varchar(20)` column
4. Transaction aborted mid-batch — Supabase left with `practice_intel=0`, `practice_signals=0`
5. Warroom / Launchpad / Buyability showed timeouts; Job Market showed "0 practices tracked"
6. **88d0668** (04:46Z) widened to `varchar(64)`. Recovery sync restored `practice_intel=2013` / `practice_signals=14053`.

### 12.2 "GDN April excuse doesn't fit"

The GDN April 2026 roundup is genuinely not yet published (correct). But the 55-day staleness compounds across multiple unrelated upstream blocks:

| Source | Status | Diagnosis |
|---|---|---|
| GDN | Source latency | April post not yet published (correct) |
| PESP | **STRUCTURAL** | Airtable migration since Aug 2024; manual recovery only — 540-1,440 deals missing |
| PitchBook | **MANUAL** | data/pitchbook/raw/ empty; no automated download |
| GHA sync | **OPERATIONAL** | SUPABASE_DATABASE_URL secret missing; CI deals discarded |
| GDN failed pages | **DATA QUALITY** | Jul/Aug 2025 may be partially missing (8 page failures) |
| ADSO timeout | **COVERAGE** | 10+ DSOs skipped "needs browser"; 92 locations vs Heartland alone has 1700+ (now 249 post-3c1031a) |

### 12.3 "All Chicagoland NPI data shows stale state"

NPPES file age: March 2026 full + March + April 2026 deltas. Last `nppes_downloader` run: 2026-04-24T17:59:22 (manual; cron last fired April 1). Jan/Feb 2026 deltas missing. NPI freshness is acceptable; the perceived staleness is a downstream artifact of the data-wipe sync (item 12.1) plus broken weekly_research cron (last fire 2026-04-04, 22 days stale).

### 12.4 "Warroom / First Job Search look suspect"

Warroom is structurally OK (no anti-patterns found). Concerns:
- Retirement lens silently shows all gray when signals fail to load — no UI feedback
- Practice dedup at warroom.ts:375 via `dedupPracticesByLocation()` is correct
- Sitrep KPI strip 12 cards in xl:grid-cols-6 — correct

Launchpad has structural drift (6 tabs not 5, 8 scopes not 4, saved searches gone) but the underlying logic is correct. The compound-narrative route reads `practice_intel` and uses `[source: domain]` citations + hedge phrases for `partial`/`insufficient` evidence — the architecture is defensive.

### 12.5 "Maps look suspect"

Confirmed: **practice-density-map.tsx uses legacy `ownership_status` for dot colors**. This is a real bug. The other 3 maps (Warroom Living, Market Intel Consolidation, Deal Flow Choropleth) are correct.

### 12.6 "Dossiers and ZIP-level analyses likely have hallucinations"

**Mostly defended for new dossiers, but with three holes:**
1. 223 DA_ pre-bulletproof dossiers have NO defenses (11% of corpus)
2. 287/290 ZIP intel rows are synthetic placeholders
3. Sonnet 2-pass escalation has never fired

The 4-layer defense itself is sound — validated 87% pass rate, 0 hallucinations slipped through on the 200-practice run. But the gate has loose enum checking (accepts "high") and 31 dossiers slipped through with `searches_executed=1`.

---

## 13. Pain Point Resolutions

### 13.1 Items Resolved In Audit Window (3 commits, 04:46Z–04:50Z)

| # | Commit | Fix | Verifies | Status |
|---|---|---|---|---|
| 1 | `88d0668` | Widen `verification_quality` varchar(20)→varchar(64) (Postgres ALTER + SQLAlchemy update) | Agent C P0 #4 (type conflict) and Agent F F1 (doc drift String(20)) | ✅ CORRECT FIX |
| 2 | `3c1031a` | Add `scrape_sitemap_jsonld()` method + Ideal Dental coverage. dso_locations 92→249. | Agent A H5 (10+ DSOs skipped "needs browser") | ✅ CORRECT FIX (partial — does not unblock Aspen/Heartland/PDS/MB2/Dental365) |
| 3 | `f4b783f` | `merge_and_score::compute_saturation_metrics` reads from `practice_locations`; new `sync_practice_classification.py` helper | Agent B B7 (Pass 3 still queried `practices` not `practice_locations`); resolves NPI-vs-clinic-locations drift | ✅ CORRECT FIX |

### 13.2 Items Recently Resolved (pre-audit but verified during audit)

| Item | Resolution | Verified |
|---|---|---|
| `refresh.sh` orphan timeout (April audit) | `pkill -TERM -P $bgpid` | ✅ refresh.sh:51-55 |
| `sync_to_supabase` deals dedup | `begin_nested()` savepoints both incremental paths | ✅ lines 401-405,433 + 568-572,599 |
| `_sync_watched_zips_only` FK violation | TRUNCATE CASCADE inside atomic begin() | ✅ lines 749-821 |
| MIN_ROWS_THRESHOLD floors | platforms=20, pe_sponsors=10, zip_overviews=5 | ✅ lines 111-120 |
| `_sync_pipeline_events pass→log.warning` | Fixed | ✅ |
| ADSO HTTP_TIMEOUT(10,30), MAX_SECONDS_PER_DSO=300, MAX_SECONDS_TOTAL=1500 | Fixed | ✅ |
| ADSO/ADA HPI freshness in system.ts | Reads `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at` | ✅ lines 139-193 |
| PESP DNS retry + 40+ COMMENTARY_PATTERNS | Fixed | ✅ pesp_scraper.py:42, 259, 396 |
| GDN _PASS_THROUGH_SET={"&","and","of"} | Fixed | ✅ gdn_scraper.py:655 |
| ZIP/JOB_HUNT force_search | Fixed | ✅ research_engine.py:302-303, 344 |
| `--sync-only` bypass | Removed | ✅ |
| compute_signals NPI null guard | Fixed | ✅ compute_signals.py:1093-1206 |
| compute_signals watched-ZIP filter | Fixed | ✅ lines 475-505 |
| eb75c6c FK violation | Resolved | ✅ |

### 13.3 Items NOT YET Resolved (open at audit close)

See §15 Prioritized Debug Backlog.

---

## 14. Suspected Root Causes

### 14.1 Ranked

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | **2026-04-26 Supabase data wipe** from `verification_quality` varchar(20) overflow | RESOLVED (`88d0668`) | Commit message diagnostic: 36-char Haiku output |
| H2 | PESP Airtable structural block ~18mo missing | CONFIRMED OPEN | `pesp_scraper.py:74-95, 474`; `pesp_airtable_scraper.py:283 NotImplementedError` |
| H3 | GDN April 2026 not yet published | CONFIRMED (source latency only) | Coverage check passes |
| H4 | GHA `SUPABASE_DATABASE_URL` missing | CONFIRMED OPEN | weekly-refresh.yml gate; April 25 7 deals discarded |
| H5 | ADSO timeout escape + orphan | CONFIRMED ONGOING | April 19 ran 2h past 30m timeout; April 26 audit-baseline orphan |
| H6 | 10+ DSOs skipped "needs browser" | PARTIAL FIX (`3c1031a` adds Ideal Dental + sitemap method, but Aspen/Heartland/PDS/MB2/Dental365 still pending) | Confirmed structural |
| H7 | PitchBook permanently manual | CONFIRMED | data/pitchbook/raw/ empty since March |
| H8 | "growth investment" parse fail | CONFIRMED | `extract_target()` requires "acquired X" |
| H9 | `weekly_research` silent fail since April 4 | LIKELY | 22 days stale |
| H10 | `data_axle_importer` crash on April 24 | CONFIRMED | 6 orphans in 6 minutes |
| H11 | Sonnet escalation never fires | CONFIRMED | escalated=0 for all 2,013 rows |
| H12 | `getPracticeIntel()` missing pagination | CONFIRMED OPEN | intel.ts:22-32 |
| H13 | `practice-density-map.tsx` uses legacy `ownership_status` | CONFIRMED OPEN | STATUS_COLORS keyed wrong |
| H14 | `test_sync_resilience.py` 14 tests broken | CONFIRMED OPEN | ImportError: PracticeLocation |
| H15 | `_reconcile_deals` documented but doesn't exist | CONFIRMED | merge_and_score.py 1,074 lines searched |
| H16 | 287 synthetic ZIP intel placeholders | CONFIRMED | cost_usd=0, model_used=NULL |
| H17 | 223 DA_ pre-bulletproof dossiers | CONFIRMED | spot-check confirmed |
| H18 | reclassify_locations.py affiliated_dso bug | CONFIRMED | 37% real DSO leak per ADSO_CROSSCHECK_CHECKPOINT.md |
| H19 | corporate_highconf_count missing from ZipScore SQLAlchemy | CONFIRMED | database.py:236-288 |

---

## 15. Prioritized Debug Backlog

### P0 — Data correctness, user-facing impact (fix immediately)

| # | Item | Location | Fix sketch |
|---|---|---|---|
| P0-1 | `getPracticeIntel()` missing `.range()` pagination → silent 1,013-row drop on Intelligence page | `dental-pe-nextjs/src/lib/supabase/queries/intel.ts:22-32` | Add `.range(0, 9999)` or chunked pagination loop |
| P0-2 | `practice-density-map.tsx` uses legacy `ownership_status` for dot colors | `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` | Rekey STATUS_COLORS to entity_classification (11 values); use `classifyPractice()` helper |
| P0-3 | `test_sync_resilience.py` ImportError: PracticeLocation | `scrapers/test_sync_resilience.py:43` | Add `PracticeLocation` symbol to test stub OR import from `scrapers.database` |
| P0-4 | `verification_quality` enum drift — gate accepts "high" | `scrapers/weekly_research.py:147` | Tighten gate to enum verified|partial|insufficient OR widen prompt to suppress "high" |
| P0-5 | GHA `weekly-refresh.yml` `SUPABASE_DATABASE_URL` missing secret | GitHub repo settings | Add secret; verify next cron run completes sync |
| P0-6 | Sonnet 2-pass escalation never fires (escalated=0 for all 2,013) | `scrapers/practice_deep_dive.py` | Audit threshold logic + verify escalated bool is set after Pass-2 merge |

### P1 — Pipeline integrity, data backfills (weeks)

| # | Item | Location | Notes |
|---|---|---|---|
| P1-1 | PESP Airtable manual recovery — 18 months × 30-80 deals | `scrapers/pesp_airtable_scraper.py:283 NotImplementedError` | Implement `auto_ingest()` OR document monthly manual export procedure |
| P1-2 | ADSO browser-rendered DSOs (Aspen, Heartland, PDS, MB2, Dental365) | `scrapers/adso_location_scraper.py` | Add Playwright/Selenium fallback; estimated 1700+ Heartland locations missing |
| P1-3 | 31 dossiers passed validation with searches_executed=1 | `scrapers/weekly_research.py:137` | Re-validate; quarantine and re-research |
| P1-4 | 287 synthetic ZIP intel placeholders | `data/dental_pe_tracker.db` `zip_qualitative_intel` | Re-research all 287 via `qualitative_scout.py --metro chicagoland` |
| P1-5 | 223 DA_ pre-bulletproof dossiers | `data/dental_pe_tracker.db` `practice_intel` | Either re-research with bulletproofing OR mark as `verification_quality=insufficient` |
| P1-6 | `reclassify_locations.py` affiliated_dso bug — 37% leak | `scrapers/reclassify_locations.py` | Read `affiliated_dso` field; not yet integrated into pipeline |
| P1-7 | `_reconcile_deals` doc-vs-code mismatch | CLAUDE.md / `merge_and_score.py` | Either implement function OR remove from docs |
| P1-8 | `corporate_highconf_count` missing from ZipScore SQLAlchemy | `scrapers/database.py:236-288` | Add column; verify Supabase schema |
| P1-9 | weekly_research cron 22 days stale | refresh.sh + GHA | Diagnose why step 9 isn't firing |
| P1-10 | `data_axle_importer` April 24 crash pattern (6 rapid-fire orphans) | `scrapers/data_axle_importer.py` | Add error handler; investigate what crashed |
| P1-11 | ADSO timeout escape — Python child survives SIGTERM | `scrapers/adso_location_scraper.py` | Add SIGTERM handler in HTTP request loop |

### P2 — Documentation and maintenance (low-priority)

| # | Item |
|---|---|
| P2-1 | Refresh CLAUDE.md EC breakdown (every line wrong post-520c33e) |
| P2-2 | Refresh deal counts (2,861 doc / 2,854 actual; GDN 2,532 / 2,515; PESP 353 / 329) |
| P2-3 | Refresh file line counts (10/23 files >100 lines off) |
| P2-4 | Remove phantom file references (narrative-card.tsx, use-launchpad-narrative.ts, api/launchpad/narrative/) |
| P2-5 | scrapers/CLAUDE.md dso_locations=408 → 249 |
| P2-6 | Add 20+ undocumented scripts to Quick Reference |
| P2-7 | Update SIGTERM checkpoints "8" → "11" |
| P2-8 | Update Launchpad docs: 6 tabs (not 5), 8 scopes (not 4), 6 AI routes (not 1) |
| P2-9 | Update Home docs: 6 KPI cards (not 8), 7 nav cards in grid-cols-3 (not 2x3 6 cards) |
| P2-10 | Update buyability docs: acquisition_target = ALL independents (not ≥50) |
| P2-11 | Update verification_quality doc: String(64) (not String(20)) |
| P2-12 | Update practice_intel doc: 2,013 (not "23 of 401k") |
| P2-13 | Update unresearched count: 9,034 (not 8,559) |
| P2-14 | Update ada_hpi_benchmarks.updated_at: NOW POPULATED (not NULL) |
| P2-15 | Schema_postgres.sql 3 tables behind, 10 cols missing → regenerate or deprecate |

### P3 — Operational hardening

| # | Item |
|---|---|
| P3-1 | `cleanup pipeline_logger.py event field` → `event_type` consistency |
| P3-2 | NPPES Jan/Feb 2026 deltas — investigate retention |
| P3-3 | Fresh-install bootstrap procedure for MIN_ROWS_THRESHOLD floors |
| P3-4 | Mirror scrapers in `dental-pe-nextjs/scrapers/` (DEPRECATED markers stranded) |
| P3-5 | Apostrophe normalization (U+2019 vs U+0027 dedup) |
| P3-6 | `/tmp/full_batch_id.txt` cross-process handoff fragility |

---

## Appendix A: Real-Time Fix Verification Log

This audit was conducted with a **continuous monitor** policy: each agent (A-F) refreshes every ~10min to detect codebase changes from concurrent debug sessions and verify whether incoming fixes are correct.

### A.1 Audit-window commits

| Time (UTC) | SHA | Author | Title | Verified Against |
|---|---|---|---|---|
| 2026-04-26 04:46Z | `88d0668` | Suleman S + Claude | fix(schema): widen practice_intel.verification_quality varchar(20)→varchar(64) | Agent C P0 #4 (verification_quality type conflict) + Agent F F1 (doc drift) |
| 2026-04-26 04:47Z | `3c1031a` | Suleman S | feat(adso): sitemap_jsonld scraping method + Ideal Dental coverage | Agent A H5 (10+ DSOs skipped "needs browser") |
| 2026-04-26 04:50Z | `f4b783f` | Suleman S | fix(audit): location-level zip_scores + classification sync helper | Agent B B7 (Pass 3 queried `practices` not `practice_locations`) |

### A.2 Verification details

#### `88d0668` — verification_quality varchar widen — ✅ CORRECT FIX

**Cause stated in commit message:**
> Anthropic Haiku emitted free-form values like "sufficient to identify data mismatch" (36 chars), "verified - MISMATCH DETECTED" (28 chars), "insufficient_for_requested_classification" (41 chars). Spec was verified|partial|insufficient (max 12 chars) but the model drifted beyond what varchar(20) could absorb.

**Verification:**
- Diff scope: 1 file changed, 1 insertion, 1 deletion (database.py)
- Field name and target type match Agent C's diagnosis (database.py:427 widened to String(64))
- Postgres live ALTER TABLE applied (per commit message, not directly verified)
- Recovery sync restored `practice_intel=2013` / `practice_signals=14053` (per commit message)

**Caveat:** The fix widens the safety margin but does NOT solve upstream prompt drift. Agent B B2 finding remains open: validation gate accepts non-`insufficient` values, so `"high"` (10 rows) still slips through. P0-4 in backlog.

#### `3c1031a` — sitemap_jsonld + Ideal Dental — ✅ CORRECT FIX (PARTIAL)

**Stated impact:**
> First production run pulled 157 office locations from sitemap, matched 147 to NPPES practices, flipped 98 to dso_affiliated. dso_locations row count grew 92 → 249 (+170%).

**Verification:**
- Live row count check: dso_locations now 249 (was 92 at audit baseline) ✅
- Method addition: `scrape_sitemap_jsonld()` correctly handles `MAX_SECONDS_PER_DSO` and `MAX_SECONDS_TOTAL` (matches existing `scrape_html_subpages()` pattern)
- Bug fix: `_extract_from_jsonld` now handles `@type` as a list (e.g., `["LocalBusiness", "Dentist"]` on Ideal Dental). Previously array types silently returned 0 — this is a real defect that 3c1031a fixes correctly.

**Caveat:** TX/OK/GA/TN/NC-heavy locations don't directly impact Chicagoland/Boston watched-ZIP corporate share. Aspen/Heartland/PDS/MB2/Dental365 still pending — these likely need Playwright/Selenium not sitemap JSON-LD. P1-2 in backlog.

#### `f4b783f` — practice_locations + sync_practice_classification — ✅ CORRECT FIX

**Stated changes:**
> 1. `merge_and_score.py::compute_saturation_metrics` — now reads gp/specialist location counts directly from practice_locations (the canonical address-deduped table).
> 2. `scripts/sync_practice_classification.py` — focused helper that pushes backfilled entity_classification + classification_reasoning from SQLite to Supabase via batched UPDATEs.

**Verification:**
- Resolves Agent F F7 finding: commit 889edc2 was misleading because pipeline still called `dso_classifier.py --entity-types-only` (queries `practices`) not `reclassify_locations.py` (queries `practice_locations`). f4b783f makes the merge_and_score path consistent with the canonical dedup table.
- New helper avoids the full TRUNCATE CASCADE + re-INSERT path, which is what TRIGGERED the 04-26 wipe — this is defensive design.
- CLAUDE.md updated: NPI-rows-vs-clinic-locations boilerplate added; practice_locations / practice_signals / zip_signals marked as canonical tables; entity_classification breakdown refreshed (still drifts vs current actual but improves over baseline).

**Caveat:** NPI-level signals (classification coverage, Data Axle enrichment ratio, ownership confidence) still come from `practices` table per intentional design. Agent B B7 (Phase 3 of dso_classifier.py queries `practices` not `practice_locations`) remains a separate concern from `merge_and_score::compute_saturation_metrics`.

### A.3 Working-tree changes detected during audit (uncommitted)

| File | Status |
|---|---|
| `scrapers/dossier_batch/launch_2000_kendall_glenview_chi.py` | NEW UNTRACKED (post-f4b783f) — appears to be a scoped batch launcher for Kendall + Glenview Chicago. Not yet read in detail. |

---

## Appendix B: Unknowns (by agent)

### Agent A
1. April 12 cron run — no log file
2. weekly_research April 5/12 status
3. GDN July/August 2025 actual coverage
4. PESP Airtable content volume (estimated 270-540 deals)
5. auto-fix.yml workflow trigger and behavior
6. data_axle_importer crash reason (April 24)
7. NPPES Jan/Feb 2026 delta retention
8. WebFetch of pestakeholder.org April 2026 (tool not loaded)

### Agent B
1. Sonnet escalation logic — why escalated=0 for all rows (untested or threshold issue)
2. 287 synthetic ZIP intel — were they generated by an early scaffolding script that never got cleaned?
3. The 31 rows with searches_executed=1 — pre-bulletproofing leaks or gate bug?
4. DA_-NPI dossier quality — none have verification blocks; reliability unknown
5. Whether `practice_intel` schema validation (verification_quality VARCHAR(20) vs SQLAlchemy String(64)) caused silent truncation in Postgres — **RESOLVED by 88d0668: WAS the wipe trigger**

### Agent C
1. Supabase practice_intel exact current count post-recovery (now 2013 per commit message)
2. corporate_highconf_count actually exists in Supabase zip_scores?
3. watched_zips.demographics_updated_at population state
4. practice_signals reflects post-Phase B dso_regional reclassification?
5. verification_quality column width in Supabase live (RESOLVED: now 64)
6. Next.js anon Supabase client statement_timeout

### Agent D
1. Streamlit live status (HTTP 303)
2. Job Market "1.9%/9.9%" — string literal vs derived
3. practice_locations Supabase sync status post-Phase B
4. practice_intel migration applied in Supabase (10 new cols)
5. execute_sql RPC configured
6. Warroom corporateHighConfidencePct exact formula
7. GHA keep-alive secrets state
8. ANTHROPIC_API_KEY in Vercel env vars

### Agent E
1. 2026-04-26T00:15:25 sync status (RESOLVED: was the wipe trigger; recovery sync followed 88d0668)
2. Supabase pooler mode (transaction vs session)
3. Vercel deployment timestamp
4. GHA SUPABASE_DATABASE_URL secret state for weekly-refresh
5. Why Apr 25 12:39 keep-alive failed
6. 2026-04-24T08:01:08 orphan complete origin

### Agent F
1. Live Supabase row counts (no connection)
2. compute_signals last sync to Supabase (FK fixed but re-sync state)
3. reclassify_locations.py affiliated_dso bug fix status
4. practice_intel sync to Supabase (RESOLVED post-88d0668: 2013)
5. weekly-refresh.yml first successful GHA run
6. zip_qualitative_intel real vs synthetic ratio
7. SUPABASE_DATABASE_URL in GHA secrets

---

**End of report.** This document is a snapshot at SHA `f4b783f` (2026-04-26 ~05:30Z). Codebase is actively being patched in concurrent debug sessions — see Appendix A for fixes detected during the audit window. Continuous-monitor mode will append further fix verifications below if dispatched.
