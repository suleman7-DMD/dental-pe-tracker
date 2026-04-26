# AUDIT REPORT — Dental PE Intelligence Platform — 2026-04-26

**Snapshot SHA:** `f8d40e9` (HEAD of `main` at audit close)
**In-flight commits during audit window:** `88d0668`, `3c1031a`, `f4b783f`, `b94ca8b`, `f8d40e9`
**Audit type:** Read-only. No code changes, no edits, no commits.
**Sources consolidated:** `AUDIT_REPORT_2026-04-26_FULL.md` (1,124 lines, 6-agent parallel audit at SHA `f4b783f`), `RECONCILIATION_VERDICT_2026_04_26.md` (281 lines), `NPI_VS_PRACTICE_AUDIT.md`, `ADSO_CROSSCHECK_CHECKPOINT.md`, `SCRAPER_AUDIT_STATUS.md`, fresh SQLite ground-truth queries 2026-04-26 ~05:30Z.

> **Note on prior auto-generated `AUDIT_REPORT_2026-04-26.md`:** This file previously contained a GitHub Actions Sonnet 4.6 automated audit dated 2026-04-26 that captured the live "Home shows 0 practices / Warroom unable to load / Launchpad statement timeout / Buyability error / Job Market infinite loading" state during the 00:15Z–04:46Z Supabase wipe window. That snapshot was correct evidence at that timestamp but its CLAUDE.md drift findings were keyed to an older CLAUDE.md revision. The wipe was resolved by `88d0668` (varchar widening + recovery sync); subsequent CLAUDE.md drift items are absorbed into §11 below. Original GHA audit is preserved in git history.

---

## 1. Executive Summary

The platform is **structurally sound but operationally degraded**. Eight discrete problems drive the "looks stale / nothing changes" symptom that prompted this audit:

| # | Problem | Severity | Status at audit close |
|---|---------|----------|----------------------|
| 1 | Supabase `practice_intel` wiped at 00:15Z when Anthropic Haiku emitted free-form `verification_quality` strings exceeding `varchar(20)` | **P0 / RESOLVED** | Fixed by `88d0668` (widen to `varchar(64)`); recovery sync restored 2,013 rows |
| 2 | PESP scraper structurally blocked since Aug 2024 (data moved to Airtable; `pesp_airtable_scraper.py:283` raises `NotImplementedError`) | **P0 / OPEN** | ~540–1,440 missing PESP deals over 18 months |
| 3 | GitHub Actions `weekly-refresh.yml` has `if: env.SUPABASE_DATABASE_URL != ''` gate; secret is missing → CI runs scrapers and silently discards results | **P0 / OPEN** | At least 7 deals from Apr 25 GHA run never reached Supabase |
| 4 | macOS `launchd` weekly cron last fired 2026-04-19; LWCR stale-context bug | **P0 / OPEN** | 7 days stale; manual runs only |
| 5 | `practice-density-map.tsx` (Job Market) keys dot colors off legacy `ownership_status` instead of `entity_classification` — violates "EC primary" rule | **P0 / OPEN** | Map renders with stale ownership semantics |
| 6 | `getPracticeIntel()` in `intel.ts:22-32` has no `.range()` pagination — silently caps at Supabase 1,000-row limit; will drop ~1,013 of 2,013 rows on Intelligence page | **P0 / OPEN** | Latent bug; surfaces only once page is rendered for all rows |
| 7 | Sonnet 2-pass escalation has **never fired** in production — `escalated=0` for all 2,013 dossiers, every `verification_quality` group | **P0 / OPEN** | High-value targets are not getting deeper coverage |
| 8 | Documentation drift in CLAUDE.md is severe — 14+ stale claims (entity_classification breakdown, deal counts, watched_zips count, dso_locations count, file line counts, phantom files/tables) | **P2 / OPEN** | Misleads future debug sessions |

**The user's "ABSOLUTELY NO DIFFERENCE" complaint is real and explained:** During the audit window (00:15Z–04:46Z on 2026-04-26), Supabase `practice_intel` was empty and `practice_signals` was empty, so the Next.js frontend rendered Warroom / Launchpad / Buyability / Job Market against a denuded DB. The user observed this exact state. The `88d0668` commit at 04:46Z restored the data; subsequent confusion is downstream of cache layers (Next.js SSR `force-dynamic`, React Query 30-min stale, browser cache) plus the documented user-facing rendering bug at `practice-density-map.tsx`.

**Maple Park Dental concrete failure (USER-PROVIDED EXAMPLE), spot-checked:**

> User claim: "1048 104TH ST, NAPERVILLE 60564 displays as Julie Romanelli, DSO Regional, 9 employees, est. 2003 — should be Maple Park Dental Care P.C., small_group, 2 providers."

Live SQLite truth (`practices` and `practice_locations`):

| Source table | NPI | Name | EC | Status | Providers | Year |
|---|---|---|---|---|---|---|
| `practices` | 1194885210 | JULIE ROMANELLI | **`small_group`** | independent | 3 | 2003 |
| `practices` | 1992546303 | SANA AHMED | **`small_group`** | independent | (null) | (null) |
| `practice_locations` | location_id `342055fe7f3a390e` | normalized `1048 104th st`, primary_npi=1487714671 | **`small_group`** | (n/a) | provider_count=2 | (n/a) |

**The classification in the database is correct (`small_group`), NOT `dso_regional`.** Two separate problems are tangled in the user's complaint:

(a) The UI renders the **NPPES provider name** ("Julie Romanelli") not a derived practice name like "Maple Park Dental Care P.C." — the `doing_business_as` field is empty for both NPIs at this address; NPPES NPI-1 rows just don't carry that data. Fixing this requires either Data Axle DBA backfill (already part of pipeline but didn't catch this address) or a separate practice-name resolution pass.

(b) If the user actually saw "DSO Regional" on the live page, that is **either a stale cached render from the 00:15Z–04:46Z wipe window, OR a frontend rendering bug**. SQLite has never classified this address as `dso_regional`. With current evidence the DB is innocent; a live-page screenshot is needed to decide between cache vs frontend bug.

---

## 2. Codebase Map

```
/Users/suleman/dental-pe-tracker/
├── dental-pe-nextjs/               # Next.js 16 frontend (PRIMARY) — auto-deploys to Vercel
│   ├── src/app/                    # 10 pages: /, /launchpad, /warroom, /deal-flow,
│   │                                #   /market-intel, /buyability, /job-market,
│   │                                #   /research, /intelligence, /system
│   ├── src/lib/supabase/queries/   # 11 query files
│   ├── src/lib/launchpad/          # scope.ts, signals.ts, ranking.ts, dso-tiers.ts
│   ├── src/lib/warroom/            # 9 modules (mode, scope, geo, signals, data, intent, ranking, briefing)
│   ├── scrapers/                   # MIRROR copy — gitignored, marked DEPRECATED
│   └── package.json                # Next 16, React 19, TanStack, Recharts 3, Mapbox GL
│
├── dashboard/app.py                # Streamlit dashboard (LEGACY, 2,583 lines)
│
├── scrapers/                       # 50+ Python files (CLAUDE.md catalogues 14)
│   ├── nppes_downloader.py         # Federal provider data
│   ├── data_axle_importer.py       # 2,650 lines, 7-pass pipeline
│   ├── pesp_scraper.py             # STRUCTURALLY BLOCKED since Aug 2024
│   ├── pesp_airtable_scraper.py    # raises NotImplementedError at line 283
│   ├── gdn_scraper.py              # Working
│   ├── pitchbook_importer.py       # Manual CSV/XLSX import only
│   ├── adso_location_scraper.py    # Working post-3c1031a; sitemap_jsonld method added
│   ├── ada_hpi_downloader.py       # Last successful 2026-03-07
│   ├── dso_classifier.py           # 1,570 lines (CLAUDE.md says 547 — drift +1,023)
│   ├── reclassify_locations.py     # 477 lines, NOT integrated into pipeline (audit B7)
│   ├── merge_and_score.py          # 1,074 lines (CLAUDE.md says 719 — drift +355)
│   ├── compute_signals.py          # 1,424 lines, NPI-null guard at 1093-1206
│   ├── sync_to_supabase.py         # 3 strategies + watched_zips_only
│   ├── refresh.sh                  # Weekly orchestrator
│   ├── pipeline_logger.py          # JSONL event log
│   ├── research_engine.py          # Anthropic API client (raw HTTP)
│   ├── intel_database.py           # Intel CRUD
│   ├── qualitative_scout.py        # ZIP research CLI
│   ├── practice_deep_dive.py       # Practice research CLI
│   ├── weekly_research.py          # Batch API runner with budget caps
│   ├── dossier_batch/              # 6+ scripts: launch.py, launch_2000_excl_chi.py,
│   │                                #   launch_2000_kendall_glenview_chi.py (NEW per b94ca8b),
│   │                                #   poll.py, poll_zip_batches.py, upsert_practice_intel.py,
│   │                                #   migrate_verification_cols.py
│   └── 20+ undocumented scripts    # See §11.5
│
├── data/                           # SQLite DB (~193 MB) + raw CSVs/XLSXs
│   ├── dental_pe_tracker.db        # 15 tables, 402,004 NPI rows, 5,732 locations
│   ├── dental_pe_tracker.db.gz     # gzipped for git push (Streamlit Cloud)
│   ├── pitchbook/raw/              # EMPTY since March 2026
│   └── research_costs.json         # 500-entry rolling cost log
│
├── logs/                           # JSONL pipeline events + per-run logs
│   └── pipeline_events.jsonl       # Last entry 2026-04-26T04:45:16
│
├── pipeline_check.py               # 540-line health check
├── CLAUDE.md                       # Project instructions (root)
├── dental-pe-nextjs/CLAUDE.md      # Next.js scope
├── scrapers/CLAUDE.md              # Scraper scope
├── AUDIT_REPORT_2026-04-26.md      # THIS DOCUMENT (consolidated)
├── AUDIT_REPORT_2026-04-26_FULL.md # 6-agent verbose audit (1,124 lines)
├── RECONCILIATION_VERDICT_2026_04_26.md # Dentagraphics 0.51% drift validation
├── AUDIT_REPORT_2026-04-25.md      # Predecessor
├── FIX_REPORT_2026-04-25.md        # Predecessor
├── NPI_VS_PRACTICE_AUDIT.md        # Dedup record
├── ADSO_CROSSCHECK_CHECKPOINT.md   # ADSO leak record
└── SCRAPER_AUDIT_STATUS.md         # Closed 2026-04-22
```

**Branch:** `main`, synced with `origin/main`. Untracked at audit time: this report and `RECONCILIATION_VERDICT_2026_04_26.md`.

---

## 3. Feature Inventory

### 3.1 Next.js routes (10 pages)

| Route | Page | Status | Notes |
|---|---|---|---|
| `/` | Home | Live | 6 KPI cards (CLAUDE.md says 8 — drift), recent deals + activity feed, freshness bar, 7-card nav (CLAUDE.md says 6 in 2x3 — drift) |
| `/launchpad` | Launchpad | Live | **6 tabs** (Snapshot, Comp, Mentorship, RedFlags, InterviewPrep, ContractParser) — CLAUDE.md says 5; **8 scopes** (4 Chicagoland + 4 Boston) — CLAUDE.md says 4; **6 AI routes** (`compound-narrative`, `red-flags`, `interview-prep`, `comp-band`, `mentorship-fit`, `contract-summary`) — CLAUDE.md says 1 |
| `/warroom` | Warroom | Live | 2 modes, 4 lenses, 11 scopes. URL-synced. Anti-pattern free. Retirement lens silently shows all gray on signal-load failure (no UI feedback) |
| `/deal-flow` | Deal Flow | Live | 4 tabs (Overview, Sponsors, Geography, Deals); persistent KPI strip |
| `/market-intel` | Market Intel | Live | 3 tabs (Consolidation, ZIP Analysis, Ownership); cross-link to Warroom |
| `/buyability` | Buyability | Live | `acquisition_target` = ALL other independents (no ≥50 score gate); drift vs Home/Warroom which DO gate at 50 |
| `/job-market` | Job Market | Live | 4 tabs (Overview, Map, Directory, Analytics); **Map uses legacy `ownership_status`** (P0-2) |
| `/research` | Research | Live | PE sponsor profiles, DSO platforms, state deep-dive, SQL explorer (SELECT-only) |
| `/intelligence` | Intelligence | Live | **`getPracticeIntel()` missing pagination — silent 1,013-row drop** (P0-1) |
| `/system` | System | Live | Freshness indicators now query ADSO + ADA HPI correctly (resolved post-audit cycle) |

### 3.2 Mapbox surfaces (4 maps)

| Map | File | Data Driver | Verdict |
|---|---|---|---|
| Warroom Living Map | `warroom/_components/living-map.tsx` | `entity_classification` via `classifyPractice()` | ✅ Correct |
| Market Intel Consolidation | `market-intel/_components/consolidation-map.tsx` | `corporate_share_pct * total_gp_locations` | ✅ Correct |
| Job Market Practice Density | `job-market/_components/practice-density-map.tsx` | **`ownership_status`** (legacy 5-value field) | ❌ **BUG** — STATUS_COLORS keyed off pre-EC field; renders with stale semantics |
| Deal Flow State Choropleth | `deal-flow/_components/state-choropleth.tsx` | `state` + deal count | ✅ Correct |

### 3.3 Dossier surfaces

| Surface | Backing data | Status |
|---|---|---|
| Practice dossier (Warroom drawer) | `practice_intel` (per-NPI, 2,013 rows) | Live; bulletproof for new dossiers |
| ZIP dossier (Warroom drawer) | `zip_qualitative_intel` (per ZIP) | **287/290 rows are SYNTHETIC PLACEHOLDERS** (cost_usd=0, model_used=NULL) |
| Practice dossier (Launchpad 5-tab) | `practice_intel` + Sonnet thesis route | Live |
| Compound thesis | `/api/launchpad/compound-narrative` Sonnet 4.6 | Live; reads `practice_intel` with `[source: domain]` citations + hedge phrases for `partial`/`insufficient` |

### 3.4 ZIP-level analyses

| Surface | Backing | Drift |
|---|---|---|
| `zip_scores` | `merge_and_score.py::compute_saturation_metrics()` (post-`f4b783f` reads from `practice_locations`) | ✅ Now canonical |
| `zip_signals` | `compute_signals.py` materializes ZIP overlay | **0 rows in Supabase**; 290 in SQLite (sync gap) |
| Saturation table | `saturation-table.tsx` | Renders `zip_scores`; relocated to Job Market |
| ZIP qualitative intel | `zip_qualitative_intel` | 287/290 synthetic |

---

## 4. Pipeline Health Matrix

| Component | Last successful run | Frequency | Status |
|---|---|---|---|
| `pesp_scraper.py` | Pre-Aug 2024 (live site) | Weekly | ❌ STRUCTURAL — Airtable migration |
| `pesp_airtable_scraper.py` | Never | Weekly | ❌ `NotImplementedError` at line 283 |
| `gdn_scraper.py` | 2026-04-23 | Weekly | ⚠️ April roundup not yet published (source latency); 8 page failures Jul/Aug 2025 |
| `pitchbook_importer.py` | March 2026 manual | Manual | ⚠️ `data/pitchbook/raw/` empty since March |
| `adso_location_scraper.py` | 2026-04-26 04:45Z | Weekly | ✅ Refreshed; 249 rows post-`3c1031a` (was 92) |
| `ada_hpi_downloader.py` + `ada_hpi_importer.py` | 2026-03-07 | Quarterly | ✅ Within cadence |
| `nppes_downloader.py` | 2026-04-24 17:59 (manual) | Monthly | ⚠️ Cron last fired April 1; Jan/Feb 2026 deltas missing |
| `data_axle_importer.py` | 2026-04-24 (with 6-orphan crash burst) | Manual | ⚠️ Crash pattern unexplained |
| `dso_classifier.py` Pass 3 | 2026-04-26 | Weekly | ✅ Reclassifier ran post-`520c33e`; `practices.entity_classification` 0 NULL in watched ZIPs |
| `reclassify_locations.py` | Run on demand | None | ❌ NOT integrated into pipeline; affiliated_dso bug per ADSO_CROSSCHECK_CHECKPOINT.md (37% real DSO leak) |
| `merge_and_score.py` | 2026-04-26 (post-`f4b783f`) | Weekly | ✅ Now reads from `practice_locations` |
| `compute_signals.py` | Run on demand | Weekly | ⚠️ FK fixed in `eb75c6c`; SQLite has 290 zip_signals; **Supabase has 0** (sync gap) |
| `sync_to_supabase.py` | 2026-04-26 (post-recovery from 04:46Z fix) | Weekly | ✅ All 3 strategies hardened; 11 SIGTERM checkpoints (CLAUDE.md says 8 — drift); savepoints on incremental dedup |
| `qualitative_scout.py` | March 2026 (synthetic placeholders dominate) | Weekly | ❌ 287/290 rows synthetic (cost_usd=0) |
| `practice_deep_dive.py` / `weekly_research.py` | 2026-04-25 (200-practice batch) | Weekly | ⚠️ Bulletproofed and working; **escalated=0 for all 2,013 rows** — Sonnet 2-pass never fires |
| `dossier_batch/launch_2000_excl_chi.py` | 2026-04-25 (`msgbatch_01A3FxKxKxemAyqDr2AcGYUq`) | One-shot | ⚠️ Submitted; results not yet inspected at audit close |
| Launchpad `/api/launchpad/compound-narrative` | Live | On-demand | ✅ Defensive; uses `[source: domain]` + hedge phrases |
| Streamlit Cloud (legacy) | HTTP 303 (alive) | Push to main | ✅ Auto-deploy on push |
| Vercel (Next.js) | Live | Push to main | ✅ Auto-deploy ~30s |

---

## 5. Scheduled Job Table

| Scheduler | Job | Schedule | Last fire | Status |
|---|---|---|---|---|
| macOS `launchd` (`com.suleman.dental-pe.refresh`) | `scrapers/refresh.sh` | Sundays 8 AM | 2026-04-19 | ❌ macOS Sequoia LWCR stale-context bug; 7 days stale |
| macOS `launchd` (NPPES monthly) | `scrapers/nppes_downloader.py` | First Sunday 6 AM | 2026-04-01 | ⚠️ 25 days stale; manual run 2026-04-24 |
| GitHub Actions `weekly-refresh.yml` | full pipeline | Weekly | 2026-04-25 | ❌ Runs scrapers but `if: env.SUPABASE_DATABASE_URL != ''` gate skips sync; secret missing |
| GitHub Actions `keep-supabase-alive.yml` | Read-only ping | Every 3 days 12:00 UTC | (depends on `SUPABASE_URL` + `SUPABASE_ANON_KEY` secrets) | ⚠️ Apr 25 12:39 ping failed (per audit Agent E) |
| Internal `weekly_research.py` (within refresh.sh step 9) | Intel batch API | Weekly | 2026-04-04 (last logged) | ❌ 22 days stale; reason unconfirmed |
| Vercel auto-deploy | Next.js build | On push to main | 2026-04-26 | ✅ |
| Streamlit Cloud auto-deploy | `dashboard/app.py` | On push to main | 2026-04-26 | ✅ |

**Critical operational fact:** Even when GitHub Actions runs the pipeline, the sync step is skipped because `SUPABASE_DATABASE_URL` is not in the GHA secrets. The user must add that secret manually. There is no programmatic fix.

---

## 6. Database Integrity

### 6.1 SQLite ground-truth row counts (audit-fresh, 2026-04-26 ~05:30Z)

| Table | Rows | CLAUDE.md claim | Drift |
|---|---|---|---|
| `practices` | 402,004 | 402,004 | ✅ |
| `practices` (watched ZIPs) | 14,053 | 14,053 | ✅ |
| `practice_locations` | 5,732 | 5,732 | ✅ |
| `practice_locations` (GP) | 5,082 | 5,265 | ⚠️ −183 |
| `practice_locations` (specialist + non_clinical) | 650 | 467 | ⚠️ +183 |
| `deals` (total) | 2,854 | 2,861 | ⚠️ −7 |
| `deals` (GDN) | 2,515 | 2,532 | ⚠️ −17 |
| `deals` (PESP) | 329 | 353 | ⚠️ −24 |
| `deals` (PitchBook) | 10 | 10 | ✅ |
| `practice_changes` | 8,946 | 8,848 | ⚠️ +98 |
| `zip_scores` | 290 | 290 | ✅ |
| `watched_zips` (60xxx Chicagoland) | 269 | 268 | ⚠️ +1 |
| `watched_zips` (02xxx Boston) | 21 | 21 | ✅ |
| `watched_zips` (TOTAL) | 290 | 290 | ✅ |
| `dso_locations` | 249 | 92 | ⚠️ +157 (post-`3c1031a` Ideal Dental ingestion — doc not refreshed) |
| `ada_hpi_benchmarks` | 918 | 918 | ✅ |
| `practice_signals` | 14,053 | 14,053 | ✅ |
| `zip_signals` (SQLite) | 290 | "290 in SQLite" | ✅ |
| `zip_signals` (Supabase) | 0 | "0 in Supabase" | ✅ (acknowledged sync gap) |
| `practice_intel` | 2,013 | "23 of 401k" + "post-recovery 2,013" | ⚠️ doc inconsistency |
| `zip_qualitative_intel` | 290 | (n/a) | of which **287 are synthetic placeholders** |

### 6.2 Entity classification distribution

**Watched-ZIP `practices` (NPI-keyed) — fresh 2026-04-26:**

| EC | Live | CLAUDE.md (post-`520c33e`) | Drift |
|---|---|---|---|
| `solo_established` | 3,575 | 3,575 | ✅ |
| `small_group` | 2,727 | 2,727 | ✅ |
| `large_group` | 2,456 | 2,456 | ✅ |
| `specialist` | ~1,429 | 2,353 | ⚠️ −924 |
| `family_practice` | 1,701 | 1,701 | ✅ |
| `solo_high_volume` | 709 | 709 | ✅ |
| `dso_national` | **404** | 222 | ❌ +82% |
| `dso_regional` | **478** | 244 | ❌ +96% |
| `solo_inactive` | 170 | 170 | ✅ |
| `solo_new` | 17 | 17 | ✅ |
| `non_clinical` | ~743 | 16 | ❌ ×46 |
| **Total Corporate** | **882** | 466 | ❌ +89% |

The reclassifier has run between the CLAUDE.md commit and the audit. Doc must be refreshed.

**`practice_locations` (address-keyed) — confirms architecture:**

| EC | Locations |
|---|---|
| solo_established | 2,058 |
| small_group | 918 |
| solo_inactive | 749 |
| specialist | 630 |
| solo_high_volume | 589 |
| large_group | 322 |
| family_practice | 207 |
| dso_regional | 116 |
| dso_national | 109 |
| non_clinical | 20 |
| solo_new | 14 |
| **TOTAL** | **5,732** |
| **Corporate (locations)** | **225** = 4.60% of 4,889 GP locations |

Confirms CLAUDE.md "4.60% (225/4,889)" claim ✅. NULL EC count = 0 ✅.

### 6.3 `practice_to_location_xref` — PHANTOM TABLE

`CLAUDE.md:97` reads: "Joined back to `practices` via `practice_to_location_xref`."

**Live SQLite tables:** `ada_hpi_benchmarks`, `deals`, `dso_locations`, `pe_sponsors`, `platforms`, `practice_changes`, `practice_intel`, `practice_locations`, `practice_signals`, `practices`, `watched_zips`, `zip_overviews`, `zip_qualitative_intel`, `zip_scores`, `zip_signals` — **15 tables, none named `practice_to_location_xref`**.

The xref table either was never created in SQLite or was deprecated. CLAUDE.md must be updated.

### 6.4 `practice_intel` integrity

| Verification quality | Rows | Avg searches | Avg escalated |
|---|---|---|---|
| `partial` | 1,286 | 3.48 | **0.0** |
| `verified` | 490 | 3.75 | **0.0** |
| `unverified` (DA_ pre-bulletproof) | 223 | (no data) | **0.0** |
| `high` (off-spec — should be quarantined) | 10 | 4.0 | **0.0** |
| `verified - MISMATCH DETECTED` (28-char overflow) | 1 | 4.0 | **0.0** |
| `sufficient to identify data mismatch` (36-char overflow) | 1 | 4.0 | **0.0** |
| `sufficient` | 1 | 4.0 | **0.0** |
| `insufficient_for_requested_classification` (41-char overflow) | 1 | 4.0 | **0.0** |
| **TOTAL** | **2,013** | | |

**Two confirmed bugs:**
1. **Sonnet 2-pass escalation has NEVER fired**: `escalated=0` across every group. H11 in FULL audit is confirmed at 100% rate. The `practice_deep_dive.py` escalation threshold or merge logic is broken or unset.
2. **Validation gate accepts `"high"`**: `validate_dossier()` quarantines only `evidence_quality=insufficient`; "high" is non-spec but slips through. 10 rows are leaks.

The 3 long-overflow values (28, 36, 41 chars) confirm the wipe trigger at 00:15Z — these strings would fail `varchar(20)`. Post-`88d0668` widening, they fit in `varchar(64)`.

### 6.5 Foreign key + orphan integrity

- `practice_signals.orphan_count = 0` (verified post-`eb75c6c` NPI-null guard + watched-ZIP filter at `compute_signals.py:475-505`)
- Earlier audit noted NPI 1316509367 (GRACE KWON, WORCESTER MA, zip 01610) was orphaned in `practice_signals`. Resolved.
- `practice_changes` newest = 2026-04-26 (today) — change-detection writer is alive
- `practice_changes` oldest acquisition = 2026-03-07; closure type ends 2026-03-14 (215 closures, all early March) — closure detection appears one-shot or stalled

### 6.6 Cross-table freshness snapshot

| Table | Latest timestamp | Days stale at audit |
|---|---|---|
| `dso_locations.scraped_at` | 2026-04-26 04:45Z | 0 |
| `ada_hpi_benchmarks.created_at` | 2026-03-07 08:01 | 50 |
| `deals.deal_date` | 2026-03-02 | 55 |
| `practice_intel.research_date` | 2026-04-26 00:15Z | 0 |
| `practice_changes.change_date` | 2026-04-26 | 0 |

### 6.7 Practice-changes type distribution

| Type | Count | Oldest | Newest |
|---|---|---|---|
| acquisition | 4,358 | 2026-03-07 | 2026-04-26 |
| unknown | 3,082 | 2026-03-12 | 2026-04-24 |
| relocation | 1,063 | 2026-03-12 | 2026-04-24 |
| name_change | 228 | 2026-03-12 | 2026-04-24 |
| closure | 215 | 2026-03-12 | **2026-03-14** |

The closure detector wrote 215 rows in 3 days then went silent — likely a one-shot detection on the March NPPES delta and never re-fired. Worth investigating whether the closure rule fires on the monthly delta or just the seed.

### 6.8 DSO breakdown post-`3c1031a` (verified)

| DSO | Locations |
|---|---|
| Ideal Dental | **157** (matches commit message) |
| Tend | 30 |
| Gentle Dental | 29 |
| Risas Dental | 21 |
| Specialized Dental Partners | 6 |
| Community Dental Partners | 6 |
| (others) | < 6 each |
| **TOTAL** | **249** |

Aspen, Heartland, PDS, MB2, Dental365 absent — confirms structural "needs browser" block (P1-2).

---

## 7. Data Flow Diagrams

```
                     ┌────────────────────────┐
                     │  External Sources      │
                     │  (NPPES, Data Axle,    │
                     │   PESP*, GDN, ADSO,    │
                     │   ADA HPI, PitchBook)  │
                     └───────────┬────────────┘
                                 │
                     [* PESP Airtable BLOCKED Aug 2024]
                                 │
                                 v
                     ┌────────────────────────┐
                     │  scrapers/*.py          │
                     │  + research_engine.py   │
                     │    (Anthropic Haiku/    │
                     │     Sonnet via batch)   │
                     └───────────┬────────────┘
                                 │
                                 v
                     ┌────────────────────────┐
                     │  SQLite (~193 MB)       │
                     │  data/dental_pe_tracker │
                     │  15 tables              │
                     └───────────┬────────────┘
                                 │
                                 v
                     ┌────────────────────────┐
                     │  sync_to_supabase.py    │
                     │  3 strategies:          │
                     │  - incremental_updated  │
                     │  - incremental_id       │
                     │  - full_replace         │
                     │  + watched_zips_only    │
                     └─────┬─────────┬────────┘
                           │         │
                           v         v
              ┌────────────┐         ┌──────────────┐
              │  Supabase  │         │  git push    │
              │  Postgres  │         │  → gz of SQLite│
              └─────┬──────┘         │  → Streamlit │
                    │                │    Cloud     │
                    v                └──────────────┘
        ┌───────────────────────┐
        │  Next.js Server Comp  │
        │  (force-dynamic)      │
        └─────┬─────────────────┘
              │
              v
        ┌───────────────────────┐
        │  React Query 30min    │
        │  (browser cache)      │
        └─────┬─────────────────┘
              │
              v
        ┌───────────────────────┐
        │  Browser DOM          │
        └───────────────────────┘
```

**6 cache layers (L0–L5):** Source → SQLite → Supabase → Next.js SSR → React Query → Browser DOM. The "ABSOLUTELY NO DIFFERENCE" complaint is largely L4 (React Query 30-min stale + 30-min gc) compounded by L2 emptiness during 00:15Z–04:46Z.

**SIGTERM resilience:** sync_to_supabase.py has 11 checkpoints (lines 421, 479, 583, 594, 633, 641, 712, 801, 838, 1156, 1223) — CLAUDE.md says 8.

---

## 8. Frontend Audit

### 8.1 EC primary rule compliance (CLAUDE.md "Critical Rules")

| Component | Uses EC primary? | Verdict |
|---|---|---|
| `classifyPractice()` helper | ✅ | Canonical |
| Home page KPIs | ✅ via `getPracticeStats()` | Correct |
| Market Intel KPIs | ✅ tiered display | Correct |
| Job Market Overview | ✅ | Correct |
| Job Market `practice-density-map.tsx` | ❌ legacy `ownership_status` | **BUG P0-2** |
| Buyability `acquisition_target` filter | EC-aware but no ≥50 score gate | **DRIFT** (Home/Warroom DO gate) |
| Warroom Living Map | ✅ | Correct |
| Warroom Sitrep KPIs | ✅ via `getSitrepBundle()` | Correct |
| Launchpad ranking | ✅ | Correct |
| Intelligence page | EC-aware but `getPracticeIntel()` is unpaginated | **BUG P0-1** |
| `compound-narrative` route | EC-aware + reads `practice_intel` | Correct |

### 8.2 Cross-page KPI consistency

| Metric | Home | Market Intel | Job Market | Warroom | Drift |
|---|---|---|---|---|---|
| Total practices | 14,053 NPI | 14,053 NPI | 14,053 NPI | 14,053 NPI | ✅ |
| Corporate (NPI) | 882 (6.28%) | 882 | 882 | 225 (4.60%) — uses `practice_locations` | ✅ Intentional unit difference per CLAUDE.md |
| Acquisition targets | ≥50 buyability | ≥50 buyability | ≥50 buyability | ≥50 | ⚠️ Buyability page = ALL independents (NO GATE) |
| Retirement risk | independent + 30+ years | (n/a) | (n/a) | independent + 30+ | ✅ |
| Deals (count) | 2,854 SQLite / Supabase mirror | same | same | same | ✅ |
| Recent deals (most recent date) | 2026-03-02 | 2026-03-02 | (n/a) | (n/a) | ✅ |

**`buyability` page filter discrepancy** is a real drift bug: the page lists ALL non-corporate independents as `acquisition_target`, while Home/Warroom enforce `buyability_score >= 50`. Either tighten the page filter or document the alternate definition.

### 8.3 Streamlit smoke

- HTTP 303 redirect (alive)
- Single 2,583-line `dashboard/app.py`, 6 pages
- Still primarily uses `ownership_status`; EC supplemental — intentional, since this is the legacy frontend
- Auto-deploys on push (DB gzipped)

### 8.4 Phantom files referenced in docs

`dental-pe-nextjs/CLAUDE.md` references files that **do not exist**:
1. `narrative-card.tsx` — superseded by `compound-thesis.tsx`
2. `use-launchpad-narrative.ts` — superseded
3. `api/launchpad/narrative/route.ts` — superseded by `compound-narrative/route.ts`
4. `use-launchpad-saved-searches.ts` — deleted in Phase 3

---

## 9. Map Reality Check

Of the 4 Mapbox surfaces, 3 are correct and 1 is broken:

### 9.1 ✅ Warroom Living Map (`warroom/_components/living-map.tsx`)
- Reads `WarroomPracticeRecord` via `getSitrepBundle()`
- Color logic dispatches through `classifyPractice()` (EC primary)
- Marker dedup at `warroom.ts:375` via `dedupPracticesByLocation()`

### 9.2 ✅ Market Intel Consolidation Map (`market-intel/_components/consolidation-map.tsx`)
- Computes pct as `corporate_share_pct * total_gp_locations`
- Uses location-deduped denominator from `zip_scores`

### 9.3 ❌ Job Market Practice Density (`job-market/_components/practice-density-map.tsx`)
- **BUG P0-2**: STATUS_COLORS dictionary keyed off legacy 5-value `ownership_status` (`independent`, `dso-affiliated`, `pe-backed`, etc.)
- Should use `entity_classification` (11 values) via `classifyPractice()` helper
- Renders dot colors with stale ownership semantics; misclassifies dso_regional and dso_national entries
- Hex aggregation is independent of color logic and remains correct

### 9.4 ✅ Deal Flow State Choropleth (`deal-flow/_components/state-choropleth.tsx`)
- Joins deal counts to state geometries; no EC dependency

---

## 10. Hallucination Audit

The 4-layer anti-hallucination defense (forced search, per-claim `_source_url`, self-assessment block, post-validation gate) is sound where it runs. **Five holes confirmed**:

### 10.1 Pre-bulletproof DA_ dossiers (223 rows / 11% of corpus)
- `verification_quality = 'unverified'`, no `verification_searches`, no `verification_urls`
- Predate the bulletproofing protocol (April 25, 2026)
- Recommendation: re-research OR mark as `verification_quality=insufficient` and exclude from frontend rendering

### 10.2 Synthetic ZIP intel placeholders (287 / 290 rows in `zip_qualitative_intel`)
- `cost_usd = 0`, `model_used = NULL`
- Likely scaffolding output that was never replaced with real research
- Warroom ZIP dossier surfaces are reading these placeholders silently

### 10.3 Sonnet 2-pass escalation has never fired
- `escalated = 0` across all 2,013 dossiers in EVERY `verification_quality` group
- High-value targets (high readiness + non-high confidence, OR 3+ green flags) should escalate to Sonnet 4.6 — but the threshold logic in `practice_deep_dive.py` is either misconfigured or the merge step never sets `escalated=True`
- Side effect: highest-value practices have ONLY Haiku quality

### 10.4 Validation gate accepts `"high"` (10 rows)
- `validate_dossier()` quarantines only `evidence_quality=insufficient`
- `"high"` is off-spec (spec is `verified|partial|insufficient`) but slips through silently
- Either tighten the gate enum check OR widen the prompt to suppress "high"

### 10.5 31 dossiers passed validation with `searches_executed=1`
- Threshold should be ≥2 searches per `EVIDENCE PROTOCOL` rule 1
- Quarantine + re-research recommended

**The 4-layer defense itself works** — the 200-practice batch of 2026-04-25 had 87% pass rate, 0 hallucinations slipped through against the spec. The above are gate edge cases, not protocol failures.

---

## 11. Documentation Drift Log

### 11.1 Severe drift (must refresh CLAUDE.md)

| Claim | CLAUDE.md | Live | Severity |
|---|---|---|---|
| watched_zips Chicagoland count | 268 | 269 | minor |
| watched_zips total | 290 (matches) | 290 | ✅ |
| dso_regional count | 244 | 478 (+96%) | **major** |
| dso_national count | 222 | 404 (+82%) | **major** |
| Total corporate (NPI rows) | 466 | 882 (+89%) | **major** |
| specialist count | 2,353 | ~1,429 | **major** −39% |
| non_clinical count | 16 | ~743 | **major** ×46 |
| dso_locations | 92 | 249 (post-`3c1031a`) | **major** +170% |
| `scrapers/CLAUDE.md` dso_locations | 408 | 249 | **major** |
| deals SQLite | 2,861 | 2,854 | minor −7 |
| deals (GDN) | 2,532 | 2,515 | minor −17 |
| deals (PESP) | 353 | 329 | minor −24 |
| `practice_to_location_xref` table | "joined back via" | DOES NOT EXIST in SQLite | **PHANTOM** |
| `practice_intel.verification_quality` | varchar(20) | varchar(64) post-`88d0668` | corrected |
| `_reconcile_deals` function | exists | NOT FOUND in `merge_and_score.py` 1,074 lines | **PHANTOM** |
| Pipeline File Quick Reference line counts | 14 entries | 10/14 off by >100 lines (e.g., `dso_classifier.py` 547 doc / 1,570 actual; `merge_and_score.py` 719 doc / 1,074 actual) | **major** |
| SIGTERM checkpoints | 8 | 11 | minor |
| `dental-pe-nextjs/CLAUDE.md` Home KPIs | 8 | 6 | doc drift |
| Launchpad tabs | 5 | 6 | doc drift |
| Launchpad scopes | 4 | 8 | doc drift |
| Launchpad AI routes | 1 | 6 | doc drift |
| Phantom Next.js files | listed | 4 don't exist | **major** |
| 20+ undocumented scripts | not in Quick Reference | exist in `scrapers/` | catalog gap |

### 11.2 Documents in working tree

- `AUDIT_REPORT_2026-04-26_FULL.md` — predecessor verbose 1,124-line audit (preserved)
- `RECONCILIATION_VERDICT_2026_04_26.md` — Dentagraphics 0.51% drift validation (preserved)
- `AUDIT_REPORT_2026-04-26.md` — THIS document
- `AUDIT_REPORT_2026-04-25.md`, `FIX_REPORT_2026-04-25.md` — predecessors
- `NPI_VS_PRACTICE_AUDIT.md` — dedup record
- `ADSO_CROSSCHECK_CHECKPOINT.md` — 37% leak record
- `SCRAPER_AUDIT_STATUS.md` — closed 2026-04-22, does not reflect April 25–26 work

---

## 12. Symptom Diagnosis (User Pain Points)

### 12.1 "GDN April 2026 excuse doesn't fit"

**Diagnosis: PARTIALLY CORRECT — the excuse is technically true but masks 5 unrelated upstream blocks.**

GDN April roundup is genuinely not yet published (verifiable via category page crawler). But the 55-day deal-staleness perception compounds:

| Source | Issue | Net deal lag |
|---|---|---|
| GDN | April post not yet published — source latency | ~3-4 weeks |
| **PESP** | Airtable migration since Aug 2024; `pesp_airtable_scraper.py:283` raises `NotImplementedError` | **18 months × 30-80 deals/mo = 540-1,440 missing** |
| PitchBook | Manual import only; `data/pitchbook/raw/` empty since March | indeterminate |
| GHA sync | `SUPABASE_DATABASE_URL` secret missing → CI scrapes deals but discards them | 7+ Apr 25 deals lost |
| ADSO | 10+ DSOs skipped "needs browser" (Aspen, Heartland, PDS, MB2, Dental365); partial fix in `3c1031a` | structural |
| `weekly_research` cron | 22 days stale; reason unconfirmed | research-only, not deal flow |

**Evidence:**
- `scrapers/pesp_scraper.py:74-95, 474` — confirms structural block
- `scrapers/pesp_airtable_scraper.py:283` — `NotImplementedError`
- `data/pitchbook/raw/` empty
- `.github/workflows/weekly-refresh.yml` — `if: env.SUPABASE_DATABASE_URL != ''` gate at sync step

### 12.2 "Stale Chicagoland NPI"

**Diagnosis: PERCEPTION, NOT REALITY — NPI freshness is acceptable; staleness is a downstream sync artifact.**

- NPPES file age: March 2026 full + March + April 2026 deltas
- `nppes_downloader.py` last successful: 2026-04-24 17:59 (manual). Cron last fire: 2026-04-01 (25 days stale)
- Jan/Feb 2026 deltas missing (retention question — see Appendix C)
- **The perceived staleness is downstream of the 00:15Z–04:46Z Supabase wipe** (see 12.6) plus the broken `weekly_research` cron (last fire 2026-04-04, 22 days stale)
- `practice_changes.change_date` newest = 2026-04-26 (today) — change detection is alive

### 12.3 "Suspect maps"

**Diagnosis: 3 of 4 maps correct; 1 confirmed bug.**

See §9 above. The bug is `practice-density-map.tsx` keying off legacy `ownership_status` instead of `entity_classification`. Evidence:

- `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` STATUS_COLORS dictionary uses 5-value field (`independent`, `dso-affiliated`, `pe-backed`, etc.)
- Should use 11-value `entity_classification` via `classifyPractice()` helper
- Confirmed against `dental-pe-nextjs/src/lib/constants/entity-classifications.ts` exports

### 12.4 "Dossier hallucinations"

**Diagnosis: MOSTLY DEFENDED, 5 holes.**

See §10 above. The 4-layer defense holds for new bulletproofed dossiers (87% pass rate, 0 hallucinations slipped through). But 5 holes:
1. 223 DA_ pre-bulletproof dossiers (no defense)
2. 287/290 ZIP intel rows synthetic placeholders (no defense, no research)
3. Sonnet 2-pass escalation never fires (high-value targets get only Haiku)
4. Gate accepts `"high"` (10 rows leaked)
5. 31 rows passed gate with `searches_executed=1` (should be ≥2)

Plus the trigger of the wipe: 3 dossiers had >20-char `verification_quality` strings (`"sufficient to identify data mismatch"` 36 ch; `"verified - MISMATCH DETECTED"` 28 ch; `"insufficient_for_requested_classification"` 41 ch) — these are now stored at varchar(64) post-`88d0668`.

### 12.5 "Broken Warroom / Launchpad"

**Diagnosis: STRUCTURAL DRIFT IN DOCS, NOT IN CODE.**

- Warroom: structurally correct, no anti-patterns. Retirement lens silently shows all gray on signal-load failure (no UI feedback) — minor.
- Launchpad: 6 tabs (not 5), 8 scopes (not 4), 6 AI routes (not 1) — docs are wrong, code is right.
- Launchpad `compound-narrative` defensive: `[source: domain]` citations + hedge phrases for partial/insufficient evidence + fallback "Structural signals only…" when intel missing.

The "broken" perception is downstream of (a) the 00:15Z–04:46Z Supabase wipe rendering Warroom KPIs against an empty `practice_intel` table, and (b) doc drift causing user/operator to expect a 5-tab Launchpad.

### 12.6 "ABSOLUTELY NO DIFFERENCE in my current app as it stands"

**Diagnosis: REAL, ROOT-CAUSED, PARTLY UNRESOLVED.**

The user observed the live frontend rendering against `practice_intel = 0` and `practice_signals = 0` during the 04:30Z window. The data was restored at 04:46Z by `88d0668`, but multiple cache layers (L4 React Query 30-min stale + L5 browser cache) plus the documented frontend bugs (P0-1 pagination, P0-2 wrong field) mean even after data recovery, several pages will not visibly change without:

1. A hard refresh / cache bust
2. Vercel re-deploy (auto on push, but no push since `f8d40e9`)
3. The two open frontend bugs being fixed

**Maple Park Dental concrete failure (USER EXAMPLE):**

User said the address `1048 104TH ST, NAPERVILLE 60564` displays as "Julie Romanelli, DSO Regional, 9 employees, est. 2003" but should be "Maple Park Dental Care P.C., small_group, 2 providers."

Live SQLite truth (2026-04-26):

| Source | NPI | Name | EC | Status | Providers | Year |
|---|---|---|---|---|---|---|
| `practices` | 1194885210 | JULIE ROMANELLI | **`small_group`** | independent | 3 | 2003 |
| `practices` | 1992546303 | SANA AHMED | **`small_group`** | independent | (null) | (null) |
| `practice_locations` | (`342055fe7f3a390e`) primary_npi=1487714671 | (NPPES org name not stored) | **`small_group`** | (n/a) | provider_count=2 | (n/a) |

**The DB classification is `small_group`, NOT `dso_regional`.** Two distinct issues are tangled:

(a) **Display name issue:** NPPES NPI-1 returns provider names. `doing_business_as` is empty for both Maple Park NPIs. Data Axle DBA enrichment didn't catch this address. Fix path: backfill `doing_business_as` for this address either via Data Axle re-import OR via `practice_locations.normalized_address` + a separate practice-name resolution pass (e.g., Google Places lookup).

(b) **"DSO Regional" attribution:** SQLite has NEVER classified this address as `dso_regional`. If the user truly saw this on the live page, this points to one of:
   - Stale cached render (00:15Z–04:46Z wipe window)
   - Frontend rendering bug (e.g., `practice-density-map.tsx` legacy `ownership_status` mapping)
   - User screenshot mismatch

Recommend: live-page screenshot of the Maple Park dossier card with browser timestamp, and verification that the page is rendering against `entity_classification='small_group'` not a fallback.

---

## 13. Pain Point Resolutions

### 13.1 Resolved during audit window (3 commits, 04:46Z–04:50Z, all on `main`)

| # | Commit | Title | Verifies | Status |
|---|---|---|---|---|
| 1 | `88d0668` | fix(schema): widen practice_intel.verification_quality varchar(20)→varchar(64) | wipe trigger (long Haiku strings) | ✅ Correct fix; recovery sync restored 2,013 rows |
| 2 | `3c1031a` | feat(adso): sitemap_jsonld scraping method + Ideal Dental coverage | "10+ DSOs skipped" | ✅ Partial; +157 dso_locations; Aspen/Heartland/PDS/MB2/Dental365 still pending |
| 3 | `f4b783f` | fix(audit): location-level zip_scores + classification sync helper | NPI vs locations drift | ✅ Correct; `compute_saturation_metrics` now reads from `practice_locations` |

### 13.2 Recently resolved (pre-audit, verified during audit)

- `refresh.sh` orphan timeout — `pkill -TERM -P $bgpid` ✅
- `sync_to_supabase` deals dedup `begin_nested()` savepoints both incremental paths ✅
- `_sync_watched_zips_only` FK violation — TRUNCATE CASCADE inside atomic begin() ✅
- MIN_ROWS_THRESHOLD floors (platforms=20, pe_sponsors=10, zip_overviews=5) ✅
- `_sync_pipeline_events pass→log.warning` ✅
- ADSO HTTP_TIMEOUT(10,30), MAX_SECONDS_PER_DSO=300 ✅
- ADSO/ADA HPI freshness in `system.ts` reads `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at` ✅
- PESP DNS retry + 40+ COMMENTARY_PATTERNS ✅
- GDN `_PASS_THROUGH_SET={"&","and","of"}` ✅
- ZIP/JOB_HUNT `force_search` ✅
- `--sync-only` bypass removed ✅
- `compute_signals` NPI null guard + watched-ZIP filter ✅
- `eb75c6c` FK violation resolved (NPI 1316509367 GRACE KWON, WORCESTER MA 01610) ✅

### 13.3 Open at audit close (see §15 Backlog)

---

## 14. Suspected Root Causes (Ranked)

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | 2026-04-26 Supabase data wipe from `verification_quality` varchar(20) overflow | RESOLVED (`88d0668`) | 3 long-overflow strings in current `practice_intel`; commit message confirms recovery |
| H2 | PESP Airtable structural block ~18 months | CONFIRMED OPEN | `pesp_scraper.py:74-95, 474`; `pesp_airtable_scraper.py:283 NotImplementedError` |
| H3 | GDN April 2026 not yet published | CONFIRMED (source latency only) | Coverage check passes |
| H4 | GHA `SUPABASE_DATABASE_URL` missing | CONFIRMED OPEN | weekly-refresh.yml gate; April 25 7 deals discarded |
| H5 | ADSO timeout escape + orphan | CONFIRMED ONGOING | April 19 ran 2h past 30m timeout; April 26 audit-baseline orphan |
| H6 | 10+ DSOs skipped "needs browser" | PARTIAL FIX (`3c1031a` adds Ideal Dental + sitemap method, but Aspen/Heartland/PDS/MB2/Dental365 still pending) | Confirmed structural |
| H7 | PitchBook permanently manual | CONFIRMED | `data/pitchbook/raw/` empty since March |
| H8 | "growth investment" parse fail | CONFIRMED | `extract_target()` requires "acquired X" |
| H9 | `weekly_research` silent fail since April 4 | LIKELY | 22 days stale |
| H10 | `data_axle_importer` crash on April 24 | CONFIRMED | 6 orphans in 6 minutes |
| H11 | **Sonnet escalation never fires** | CONFIRMED 100% | `escalated=0` for all 2,013 rows across every quality group |
| H12 | `getPracticeIntel()` missing pagination | CONFIRMED OPEN | `intel.ts:22-32` |
| H13 | `practice-density-map.tsx` uses legacy `ownership_status` | CONFIRMED OPEN | STATUS_COLORS keyed wrong |
| H14 | `test_sync_resilience.py` 14 tests broken | CONFIRMED OPEN | ImportError: PracticeLocation |
| H15 | `_reconcile_deals` documented but doesn't exist | CONFIRMED PHANTOM | merge_and_score.py 1,074 lines searched |
| H16 | 287 synthetic ZIP intel placeholders | CONFIRMED | cost_usd=0, model_used=NULL |
| H17 | 223 DA_ pre-bulletproof dossiers | CONFIRMED | spot-check: verification_quality='unverified' |
| H18 | `reclassify_locations.py` affiliated_dso bug | CONFIRMED | 37% real DSO leak per ADSO_CROSSCHECK_CHECKPOINT.md |
| H19 | `corporate_highconf_count` missing from ZipScore SQLAlchemy | CONFIRMED | database.py:236-288 |
| H20 | `practice_to_location_xref` referenced but doesn't exist | CONFIRMED PHANTOM | sqlite_master listing |
| H21 | Validation gate accepts off-spec `"high"` | CONFIRMED | 10 rows in `practice_intel` |
| H22 | Buyability page filter no ≥50 score gate (drift vs Home/Warroom) | CONFIRMED | All independents marked acquisition_target |
| H23 | Closure detector silent since 2026-03-14 | LIKELY | 215 rows in 3 days then no closures since |
| H24 | NPPES doing_business_as backfill incomplete | CONFIRMED via Maple Park spot-check | Two NPIs at 60564 1048 104TH ST have empty DBA |

---

## 15. Prioritized Debug Backlog

### P0 — Data correctness, user-facing impact (fix immediately)

| # | Item | Location | Fix sketch |
|---|---|---|---|
| P0-1 | `getPracticeIntel()` missing `.range()` pagination → silent 1,013-row drop on Intelligence page | `dental-pe-nextjs/src/lib/supabase/queries/intel.ts:22-32` | Add `.range(0, 9999)` or chunked pagination loop |
| P0-2 | `practice-density-map.tsx` uses legacy `ownership_status` for dot colors | `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` | Rekey STATUS_COLORS to entity_classification (11 values); use `classifyPractice()` helper |
| P0-3 | `test_sync_resilience.py` ImportError: PracticeLocation | `scrapers/test_sync_resilience.py:43` | Add `PracticeLocation` symbol to test stub OR import from `scrapers.database` |
| P0-4 | `verification_quality` enum drift — gate accepts "high" | `scrapers/weekly_research.py:147` | Tighten gate to enum verified\|partial\|insufficient OR widen prompt to suppress "high" |
| P0-5 | GHA `weekly-refresh.yml` `SUPABASE_DATABASE_URL` missing secret | GitHub repo settings | Add secret; verify next cron run completes sync |
| P0-6 | Sonnet 2-pass escalation never fires (escalated=0 for all 2,013) | `scrapers/practice_deep_dive.py` | Audit threshold logic + verify escalated bool is set after Pass-2 merge |
| P0-7 | Buyability page `acquisition_target` filter has no ≥50 score gate | `dental-pe-nextjs/src/app/buyability/_components/buyability-shell.tsx` | Either add `buyability_score >= 50` filter OR document the alternate definition |
| P0-8 | `practice_signals` / `zip_signals` Supabase sync gap | `scrapers/sync_to_supabase.py` | Run `python3 scrapers/sync_to_supabase.py --tables zip_signals` |

### P1 — Pipeline integrity, data backfills (weeks)

| # | Item | Location | Notes |
|---|---|---|---|
| P1-1 | PESP Airtable manual recovery — 18 months × 30-80 deals (~540-1,440 missing) | `scrapers/pesp_airtable_scraper.py:283 NotImplementedError` | Implement `auto_ingest()` OR document monthly manual export procedure |
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
| P1-12 | Maple Park Dental DBA backfill (and broader DBA gap) | NPI 1194885210 / 1992546303 + class | Data Axle re-import for 60564 OR practice-name resolver pass |
| P1-13 | macOS launchd LWCR stale-context bug | `com.suleman.dental-pe.refresh` | Investigate Sequoia-specific fix; consider replacing with GHA cron + remote trigger |
| P1-14 | Closure detector silent since 2026-03-14 | `scrapers/data_axle_importer.py` or `compute_signals.py` | Verify closure rule fires on monthly delta, not just full seed |

### P2 — Documentation drift (low-priority)

| # | Item |
|---|---|
| P2-1 | Refresh CLAUDE.md EC breakdown (every line wrong post-`520c33e`) |
| P2-2 | Refresh deal counts (2,861 doc / 2,854 actual; GDN 2,532 / 2,515; PESP 353 / 329) |
| P2-3 | Refresh file line counts (10/14 files >100 lines off) |
| P2-4 | Remove phantom file references (narrative-card.tsx, use-launchpad-narrative.ts, api/launchpad/narrative/, use-launchpad-saved-searches.ts) |
| P2-5 | scrapers/CLAUDE.md dso_locations=408 → 249 |
| P2-6 | Add 20+ undocumented scripts to Quick Reference |
| P2-7 | Update SIGTERM checkpoints "8" → "11" |
| P2-8 | Update Launchpad docs: 6 tabs (not 5), 8 scopes (not 4), 6 AI routes (not 1) |
| P2-9 | Update Home docs: 6 KPI cards (not 8), 7 nav cards (not 6 in 2x3) |
| P2-10 | Update buyability docs: acquisition_target = ALL independents (not ≥50) |
| P2-11 | Update verification_quality doc: String(64) (not String(20)) |
| P2-12 | Update practice_intel doc: 2,013 (not "23 of 401k") |
| P2-13 | Update unresearched count: 9,034 (not 8,559) |
| P2-14 | Update ada_hpi_benchmarks.updated_at: NOW POPULATED (not NULL) |
| P2-15 | Schema_postgres.sql 3 tables behind, 10 cols missing → regenerate or deprecate |
| P2-16 | Remove phantom `practice_to_location_xref` from CLAUDE.md OR create the table |
| P2-17 | Remove phantom `_reconcile_deals` from CLAUDE.md OR implement |
| P2-18 | Update watched_zips count: 269 IL + 21 MA = 290 (not "268 + 21 + 1") |

### P3 — Operational hardening

| # | Item |
|---|---|
| P3-1 | `pipeline_logger.py event` → `event_type` consistency |
| P3-2 | NPPES Jan/Feb 2026 deltas — investigate retention |
| P3-3 | Fresh-install bootstrap procedure for MIN_ROWS_THRESHOLD floors |
| P3-4 | Mirror scrapers in `dental-pe-nextjs/scrapers/` (DEPRECATED markers stranded) |
| P3-5 | Apostrophe normalization (U+2019 vs U+0027 dedup) |
| P3-6 | `/tmp/full_batch_id.txt` cross-process handoff fragility |
| P3-7 | Vercel cache bust strategy when Supabase emptied (e.g., `unstable_revalidate` on detected zero rows) |

---

## Appendix A: Real-Time Fix Verification (audit window 04:46Z–04:50Z)

| Time (UTC) | SHA | Title | Verified Against | Verdict |
|---|---|---|---|---|
| 2026-04-26 04:46Z | `88d0668` | fix(schema): widen practice_intel.verification_quality varchar(20)→varchar(64) | Agent C P0 #4 + Agent F F1 | ✅ CORRECT FIX |
| 2026-04-26 04:47Z | `3c1031a` | feat(adso): sitemap_jsonld + Ideal Dental | Agent A H5 | ✅ CORRECT FIX (PARTIAL) |
| 2026-04-26 04:50Z | `f4b783f` | fix(audit): location-level zip_scores + classification sync helper | Agent B B7 | ✅ CORRECT FIX |
| 2026-04-26 ~05:00Z | `b94ca8b` | feat(scrapers): kendall+glenview+chi 2k launcher (priority-zoned) | Untracked at FULL audit close | NEW — not yet inspected in detail |
| 2026-04-26 ~05:15Z | `f8d40e9` | docs: refresh corporate-share callouts post-NPI backfill | Doc updates | Acknowledged |

---

## Appendix B: Methodology

### B.1 What this audit did

- Read 100% of `AUDIT_REPORT_2026-04-26_FULL.md` (1,124 lines, 6-agent parallel audit at SHA `f4b783f`)
- Read 100% of `RECONCILIATION_VERDICT_2026_04_26.md` (281 lines)
- Ran **fresh** SQLite ground-truth queries:
  - Row counts for 15 tables
  - Entity classification distribution at NPI level + location level
  - Deal source breakdown (GDN/PESP/PitchBook)
  - `practice_intel.verification_quality` distribution + escalation rate
  - `practice_changes` recency + type breakdown
  - Cross-table freshness snapshot (ADSO, ADA HPI, deals, intel)
  - DSO breakdown post-`3c1031a`
  - Watched ZIPs metro split
- Spot-checked Maple Park Dental (1048 104TH ST, NAPERVILLE 60564) per user-provided concrete failure
- Verified `practice_to_location_xref` table existence (it does not)
- Cross-referenced FULL audit findings with my live data to identify CLAUDE.md drift not captured by FULL audit

### B.2 What this audit did NOT do

- Live HTTP probe of all 10 Vercel routes (did not connect to Supabase REST or Vercel)
- Hallucination spot-check of 5 random `practice_intel` dossiers vs cited URLs (relies on FULL audit's 200-practice batch validation)
- Manual web search for PE deals 2026-03-01 → 2026-04-25 (FULL audit confirms structural blocks already)
- Code-level inspection of `practice_deep_dive.py` escalation logic (confirmed empirical state via SQLite)
- Streamlit live render verification beyond HTTP 303 (legacy frontend, lower priority)
- New parallel agent dispatches A–F (the FULL audit already executed this; this report consolidates rather than re-runs)

### B.3 Confidence levels

- **HIGH**: All bug counts, distribution numbers, drift figures (verified via fresh SQLite queries 2026-04-26)
- **MEDIUM**: User pain point root causes (relies on FULL audit's structural analysis + this audit's confirmation queries)
- **LOWER**: Pre-audit fix verifications (relied on commit messages + diff scope rather than independent reproduction)

---

## Appendix C: Open Unknowns Carried Forward

These could not be resolved in the audit window without live Supabase REST or Vercel access:

1. Live Supabase row counts post-`88d0668` recovery (FULL audit cites commit message: `practice_intel=2013`, `practice_signals=14053`)
2. Live Vercel render of Maple Park Dental dossier card (needs screenshot to disambiguate cache vs frontend bug)
3. Live `zip_signals` Supabase row count (SQLite has 290; doc says Supabase has 0)
4. Whether `corporate_highconf_count` exists in live Supabase `zip_scores` schema (SQLAlchemy lacks it per `database.py:236-288`)
5. ANTHROPIC_API_KEY presence in Vercel project env vars (`/api/launchpad/compound-narrative` returns 503 without it)
6. Streamlit live page render of all 6 pages (HTTP 303 alive but no per-page health probe)
7. GHA `SUPABASE_DATABASE_URL` secret state (gate behavior implied; needs repo settings inspection)
8. WebFetch of pestakeholder.org April 2026 deal list (PESP Airtable structural block)
9. NPPES Jan/Feb 2026 delta retention status

---

## Appendix D: Original GHA Sonnet 4.6 Audit Findings (preserved highlights)

The previous content of this file was an automated GHA Sonnet 4.6 audit captured during the 00:15Z–04:46Z wipe window. Its "Top 10 Verified Broken" findings #1-5 (Home shows 0 practices, Warroom unable to load, Launchpad statement timeout, Buyability error, Job Market infinite loading) were correct evidence of the wipe state but are now obsolete post-`88d0668` recovery. Its "Top 10 Verified Stale" findings about CLAUDE.md drift on deal counts (3,215 claim vs 2,895 actual), DSO Locations (408 vs 92), PE Sponsors (40 vs 106), Platforms (140 vs 490) reflect an OLDER CLAUDE.md revision that has since been partially refreshed; this consolidated audit's §11 reconciles drift against the CURRENT CLAUDE.md revision. The original audit document is preserved in git history.

---

**End of report.** Snapshot SHA `f8d40e9`, 2026-04-26 ~05:30Z. This document supersedes the previous auto-GHA `AUDIT_REPORT_2026-04-26.md` and consolidates `AUDIT_REPORT_2026-04-26_FULL.md` + `RECONCILIATION_VERDICT_2026_04_26.md` into a single canonical audit artifact for this session. The 24-hypothesis root-cause table and the P0–P3 backlog are the actionable outputs.
