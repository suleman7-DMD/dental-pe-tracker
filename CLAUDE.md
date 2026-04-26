# Dental PE Intelligence Platform — Claude Code Guide

> **Condensed 2026-04-26 (71k → ~27k chars).** Full pre-condensation content preserved verbatim in `CLAUDE_ARCHIVE.md`. When a section here points to *"full detail: CLAUDE_ARCHIVE.md §X"*, that's where the trimmed prose lives. Sibling audit docs (`SCRAPER_AUDIT_STATUS.md`, `IMPLEMENTATION_PLAN_2026_04_26.md`, `RECONCILIATION_VERDICT_2026_04_26.md`, `NPI_VS_PRACTICE_AUDIT.md`, `AUDIT_REPORT_2026-04-26_FULL.md`) are the canonical sources for historical investigations.

## What This Project Is

A data pipeline + dual-frontend dashboard tracking PE consolidation in US dentistry. Scrapes deal announcements, monitors 381,598 dental practices from federal data (post-F32 hygienist-leak cleanup), classifies ownership, scores markets for acquisition risk. Primary metro: Chicagoland (269 expanded ZIPs). Secondary: Boston Metro (21 ZIPs). Total watched: **290 ZIPs** = 269 IL + 21 MA.

- **Next.js app (primary):** dental-pe-nextjs.vercel.app
- **Streamlit app (legacy):** suleman7-pe.streamlit.app
- **Repo:** github.com/suleman7-DMD/dental-pe-tracker

## Architecture

```
dental-pe-nextjs/    Next.js 16 frontend (primary) — Supabase Postgres, Vercel
dashboard/app.py     Streamlit dashboard (legacy, 2,583 lines, 6 pages)
scrapers/            Python scrapers + importers + classifiers
scrapers/database.py SQLAlchemy models + helpers (SQLite — pipeline DB)
scrapers/sync_to_supabase.py  SQLite → Supabase Postgres sync
data/                SQLite DB (145 MB) + raw data files
logs/                Pipeline event log (JSONL) + per-run logs
pipeline_check.py    Diagnostic health check (540 lines)
```

```
Federal/Web → Python Scrapers → SQLite → sync_to_supabase.py → Supabase Postgres → Next.js
                                       ↘ gzip → git push → Streamlit Cloud (legacy)
```

Push to `main` auto-deploys both: Vercel (~30s) and Streamlit Cloud (~60s).

## Database

### NPI rows vs clinic locations — read before quoting any count

NPPES emits one row per provider (NPI-1) AND one row per organization (NPI-2) at the same address. `practices` is keyed by NPI, NOT clinic. Watched ZIPs: **13,818 NPI rows** (post-F32; was 14,053) collapse to **5,732 deduped clinic locations** (~2.6× fan-out). "381,598 practices" / "13,818 watched" are **NPI-row counts**. Location-deduped denominator is `SUM(zip_scores.total_gp_locations)` for GP, `practice_locations.location_id` for address-keyed queries. ~2.6× Supabase row count = NPI rows, not sync drift.

### Numbers cheat-sheet — F29 (read before quoting any count)

Full reconciliation reasoning + Dentagraphics gap analysis: `RECONCILIATION_VERDICT_2026_04_26.md` §§2-3.

| # | Value | Unit | Scope | Source | Where it surfaces |
|---|------:|------|-------|--------|-------------------|
| 1 | **381,598** | NPI rows | global | `COUNT(*) FROM practices` (post-F32; was 402,004) | "382k practices" headline |
| 2 | **13,818** | NPI rows | 290 watched | `practices` ⋈ `watched_zips` (was 14,053) | Job Market header, NPI KPIs |
| 3 | **5,732** | locations | 290 watched (all classes) | `practice_locations` ⋈ `watched_zips` | Internal only — NEVER user-facing |
| 4 | **4,889** | GP locations | 290 watched | `SUM(zip_scores.total_gp_locations)` post-`dc18d24` | Home, Market Intel, Job Market, Launchpad headline |
| 5 | **4,575** | GP loc | CHI (269 IL) | watched + IL filter on (4) | Warroom Sitrep, Market Intel CHI |
| 6 | **314** | GP loc | BOS (21 MA) | watched + MA filter on (4); 4,575+314=4,889 ✅ | Boston surfaces |
| 7 | **4,574** | GP loc | all-IL (statewide) | `practice_locations` IL+GP filter | Dentagraphics-comparable scope |
| 8 | **4,409** | active-GP | all-IL, drop `solo_inactive` | (7) minus 165 contactless | Honest active-GP claim |
| 9 | **3,961** | (their unit) | all-IL | Dentagraphics infographic (F30) | External benchmark — +15.5% gap to (7), +11.3% to (8) |
| 10 | **882** | corp NPIs | 13,818 watched | `entity_classification IN (dso_regional,dso_national)` | NPI-row corporate KPI = 6.38% |
| 11 | **225** | corp locations | 4,889 GP watched | same on `practice_locations` | Headline corporate share = **4.60%** |

**Most-confused comparison:** Job Market ~14k "practices" (NPI rows, line 2) vs Warroom ~5,491 (locations, line 4 minus a few). Both correct under their own units. Conversion = structural NPPES dual-emission.

**Dentagraphics gap (F30):** Their **3,961** for IL has only "data courtesy of Medicaid.gov" + "as is, with all faults" disclaimer; no methodology disclosed. The +15.5% gap (our 4,574 vs their 3,961) cannot be assigned. Our number has SQL provenance; theirs has disclaimer. Don't claim "we match Dentagraphics" or "they're correct and we're wrong."

### SQLite tables

| Table | Rows | Notes |
|-------|-----:|-------|
| `practices` | 381,598 global / 13,818 watched | PK `npi`. **`entity_classification`** is canonical ownership signal (populated for all watched NPIs) |
| `practice_locations` | 5,732 watched (4,889 GP: CHI 4,575 + BOS 314) | Address-deduped, PK `location_id`. **All Sitrep KPIs + headline corp %/independent % source HERE — NOT `practices`.** Joined via `practice_to_location_xref` |
| `deals` | 2,861 / 2,861 | 2,532 GDN + 353 PESP + 10 PitchBook. Drift reconciled `ac2140a` — Pass 2 of `_reconcile_deals()` (`sync_to_supabase.py:924`, called from `:1287`) keys NULL-target rows by composite hash. Oct 2020 – Mar 2026 |
| `practice_changes` | 8,848 | name/address/ownership change log |
| `zip_scores` | 290 | One per watched ZIP. `total_gp_locations` = canonical clinic-count denominator |
| `watched_zips` | 290 (269 IL + 21 MA) | Auto-backfilled by `ensure_chicagoland_watched()` |
| `dso_locations` | 92 | Scraped DSO offices |
| `ada_hpi_benchmarks` | 918 | State DSO affiliation × career stage. `updated_at` populated (F20) |
| `practice_signals` | 13,818 NPI | Warroom Hunt 8-flag overlay (stealth_dso, phantom_inventory, family_dynasty, micro_cluster, retirement_combo, last_change_90d, high_peer_retirement, revenue_default) |
| `zip_signals` | 290 SQLite / **0 Supabase** | Sync gap. Repair: `python3 scrapers/sync_to_supabase.py --tables zip_signals` |

**Watched-ZIP `entity_classification` breakdown (NPI rows, post-`520c33e`):** solo_established 3,575 / small_group 2,727 / large_group 2,456 / specialist 2,353 / family_practice 1,701 / solo_high_volume 709 / dso_national 222 / solo_inactive 170 / dso_regional 244 / solo_new 17 / non_clinical 16. NULL=0.

**Corporate share NPI vs location is structural.** NPI rows: 882 corporate / 13,818 watched = 6.28%. Locations: 225 corporate / 4,889 GP = **4.60%** (CHI 4.52%, BOS 5.73%). One corporate location houses 2-5 NPIs. **Use `practice_locations` / `zip_scores.corporate_location_count` for headline KPIs.** Only quote NPI counts when the unit is "individual dentists working at corporate" (Job Market scoring). Legacy `ownership_status` is ~zero in SQLite — `entity_classification` (via `classifyPractice()` helper) is canonical in the Next.js frontend.

### Sync strategies (`sync_to_supabase.py`)

| Strategy | Tables | How |
|----------|--------|-----|
| `incremental_updated_at` | practices, **deals** | Only rows changed since last sync timestamp |
| `incremental_id` | practice_changes | New rows only (id > last_synced_id), watched-ZIP filter |
| `full_replace` | zip_scores, watched_zips, dso_locations, ada_hpi_benchmarks, pe_sponsors, platforms, zip_overviews, zip_qualitative_intel, practice_intel | TRUNCATE CASCADE + INSERT |

Both incremental paths wrap each row insert in a `begin_nested()` savepoint so an `IntegrityError` on the secondary partial unique index `uix_deal_no_dup` (platform_company+target_name+deal_date) skips the duplicate with a WARNING instead of aborting the whole batch transaction.

### Supabase Postgres (Next.js Frontend)

Mirror of SQLite, synced by `scrapers/sync_to_supabase.py`. Same schema, same table names. Next.js reads directly from Supabase — never touches SQLite.

## Next.js Frontend (Primary)

**Stack:** Next.js 16, React 19, TypeScript 5, Supabase Postgres, TanStack React Query + Table, Recharts 3, Mapbox GL, Tailwind CSS 4, shadcn UI, Lucide React.

**Fonts:** DM Sans (headings, 24px/700), Inter (body), JetBrains Mono (data values, 28px/700 KPIs). Data labels: 11px/500/Inter/uppercase/tracking-wider.

**Deploy:** Vercel auto-deploys on push to main.

**Env vars:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MAPBOX_TOKEN`. **`ANTHROPIC_API_KEY`** required for `/api/launchpad/compound-narrative` (Sonnet thesis route) — set in Vercel env (Production + Preview + Development), then redeploy. Without it, the route returns `503: Compound narrative disabled`.

### Pages (11 routes)

| Route | Notes |
|-------|-------|
| `/` Home | 6 KPI cards, recent deals + activity feed from practice_changes, freshness bar, quick nav |
| `/launchpad` | First-job finder. Track-weighted 0-100 (Succession/Apprentice, High-Volume Ethical, DSO Associate). 20-signal catalog, 5 tiers, 4 living-location scopes, 6-tab dossier, curated DSO tier list. Compound thesis: Sonnet 4.6 + `practice_intel` |
| `/warroom` | Chicagoland command. 2 modes (Hunt/Investigate), 4 lenses, 11 scopes. Sitrep KPI strip, ⌘K intent bar, Living Map, target list, ZIP + practice dossiers, pinboard, 8 practice + 1 ZIP signal overlays. Keyboard: `?`, `1/2`, `R/P/V`, `[/]`, `Esc`. URL-synced |
| `/deal-flow` | 4 tabs: Overview \| Sponsors \| Geography \| Deals |
| `/market-intel` | 3 tabs: Consolidation \| ZIP Analysis \| Ownership. Cross-link to Warroom |
| `/buyability` | Verdict extraction, 4 category KPIs, ZIP filter, sortable + CSV export |
| `/job-market` | 4 tabs: Overview \| Map \| Directory \| Analytics. Living Location Selector (4 presets) |
| `/research` | PE sponsor + DSO platform profiles, state deep dives, SQL explorer (SELECT-only) |
| `/intelligence` | AI qualitative — 6 KPIs, ZIP intel + practice dossier expandable panels. Cross-link to Warroom Investigate |
| `/system` | Freshness, coverage, completeness bars, log viewer, manual entry |
| `/data-breakdown` | Per-KPI provenance (F31, 2026-04-26) |

### Data flow + entity classification (CRITICAL)

Server Components (`page.tsx`) fetch Supabase → Client shells (`*-shell.tsx`, `'use client'`) handle filters/state → React Query (30min stale/gc, per-hook overrides for warroom/launchpad) → URL params sync via `useUrlFilters`. Queries in `src/lib/supabase/queries/` per table.

**`entity_classification` is PRIMARY for all ownership analysis.** `ownership_status` is fallback only when entity_classification IS NULL. Vitest `src/__tests__/classification-primary.test.ts` (F27) walks src/ and fails on `ownership_status` references missing `entity_classification` companion (10-entry justified allowlist).

Helpers in `src/lib/constants/entity-classifications.ts`: `isIndependentClassification(ec)` (solo_*/family/small/large_group), `isCorporateClassification(ec)` (dso_regional/national), `classifyPractice(ec, os)` → "independent"|"corporate"|"specialist"|"non_clinical"|"unknown", `getEntityClassificationLabel(v)`. Also exports `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`.

### Scoring (`src/lib/utils/scoring.ts`)

`computeJobOpportunityScore()` 0-100, entity_classification primary + ownership_status fallback. Factors: ownership 30pts, buyability 25/15pts, employees 20/10pts, year_established 15/8pts. `isRetirementRisk()` = independent + 30+ years. `getPracticeAge()` = years since year_established.

### Design system (warm light, 2026-03-15)

Bg #FAFAF7 / cards #FFFFFF / hover #F7F7F4 / input #F5F5F0. Sidebar #2C2C2C dark, goldenrod #B8860B active. Text #1A1A1A/#6B6B60/#9C9C90. Borders #E8E5DE/#D4D0C8. Accent goldenrod #B8860B. Status: Corporate #C23B3B, Independent #2563EB, Specialist #0D9488, Group #6366F1. KPIs 28px JetBrains Mono bold. Full tokens: `src/lib/constants/design-tokens.ts`.

### Sidebar (4 sections, 11 items)

- **OVERVIEW:** Dashboard, Launchpad, Warroom
- **MARKETS:** Job Market, Market Intel, Buyability
- **ANALYSIS:** Deal Flow, Research, Intelligence, Data Breakdown
- **ADMIN:** System

### File map (high-level — grep for component names; full per-component listing in CLAUDE_ARCHIVE.md §"Next.js File Map")

- `src/app/<route>/_components/` — orchestrator `*-shell.tsx` per route + sub-components. Cross-page primitives: `practice-dossier.tsx` (Launchpad 6-tab), `dossier-drawer.tsx` (Warroom), `living-map.tsx` (Mapbox), `intent-bar.tsx` (⌘K), `practice-density-map.tsx` (Job Market hex+dot)
- `src/app/api/launchpad/compound-narrative/route.ts` — Sonnet 4.6, reads `practice_intel`, ephemeral cache, 200-300 word output with `[source: domain]` citations, hedge phrases when evidence is `partial`/`insufficient`
- `src/lib/launchpad/`, `src/lib/warroom/` — domain logic (scope, signals, ranking, intent, briefing)
- `src/lib/supabase/queries/` — per-table query modules. `system.ts` reads ADSO + ADA HPI freshness via `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at`
- `src/lib/constants/entity-classifications.ts` — exports `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`, `classifyPractice()`. `sql-presets.ts` uses entity_classification, NOT ownership_status
- `src/lib/types/index.ts` — Deal, Practice, ZipScore, WatchedZip, HomeSummary (with `enrichedCount`), PracticeStats. `intel.ts` extends `practice_intel` with `verification_searches`, `verification_quality`, `verification_urls`
- `src/components/data-display/data-table.tsx` — TanStack; render functions MUST return primitives. `kpi-card.tsx` supports `subtitle` prop for tiered display
- `src/components/charts/` Recharts wrappers, `src/components/maps/map-container.tsx` Mapbox wrapper, `src/components/layout/sidebar.tsx` (220px/60px collapsible, 4 grouped sections), `src/components/ui/` shadcn primitives
- `src/providers/query-provider.tsx` (React Query 30min stale/gc, 1 retry), `sidebar-provider.tsx`

## Streamlit Dashboard (Legacy)

Single file `dashboard/app.py` (2,583 lines, 6 pages: Deal Flow, Market Intel, Buyability, Job Market, Research, System). Live at suleman7-pe.streamlit.app but no longer primary. Streamlit still uses `ownership_status` primary; entity_classification supplemental.

## Automated Pipeline

Cron runs every Sunday 8am (`scrapers/refresh.sh`):
1. Backup DB → 2. PESP scraper → 3. GDN scraper → 4. PitchBook importer → 5. ADSO scraper → 6. ADA HPI downloader → 7. DSO classifier → 8. Merge & score → 9. Weekly qualitative research ($5 budget cap) → 10. Sync to Supabase → Compress DB + git push.

Monthly NPPES refresh (first Sunday 6am): downloads federal provider data updates.

Every step logs structured events to `logs/pipeline_events.jsonl` via `scrapers/pipeline_logger.py`.

## Critical Rules

### Don't break the pipeline

- ALL scrapers import from `scrapers.pipeline_logger` — keep `log_scrape_start()` and `log_scrape_complete()` calls in every scraper's `run()`
- ALL scrapers use `scrapers.logger_config.get_logger("scraper_name")`
- `database.py` auto-decompresses `.db.gz` on Streamlit Cloud — never remove that logic
- `refresh.sh` uses `run_step()` wrapper — errors in one step don't kill the pipeline

### Market Intel transparency

- Consolidation percentages MUST use total practices as denominator (conservative)
- Never use `classified_count` as denominator for headline KPIs — that inflates numbers
- Always show unknown count when >30% of practices are unclassified
- Labels must say "Known Consolidated" not just "Consolidated"

### Data integrity

- `insert_or_update_practice()` and `insert_deal()` handle dedup — use them, don't raw INSERT
- NPPES uses NPI as unique key (10-digit number)
- PitchBook dedup: fuzzy match on company name + date
- Data Axle dedup: address normalization + fuzzy name match
- Data Axle importer Pass 6: Corporate Linkage Detection (parent company fuzzy, EIN clustering, IUSA parent linkage, franchise field)
- Never DELETE from `practices` — only update ownership_status / entity_classification

### Streamlit Cloud constraints

- DB must be gzipped for git push (`data/dental_pe_tracker.db.gz`)
- App decompresses on first load via `_ensure_db_decompressed()`
- Keep `dashboard/app.py` imports inside functions where possible (cold start)

### Next.js frontend rules

- **`entity_classification` is primary** — ALWAYS, with `ownership_status` as fallback only when NULL. F27 vitest enforces this.
- `classifyPractice()` is the canonical helper across the entire frontend
- KPI icons: Lucide JSX components (not strings)
- Supabase returns max 1000 rows per query — MUST paginate with `.range()` for large result sets
- Consolidation % denominator is ALWAYS total practices
- DataTable render functions must return primitives (`string | number | null`), never objects
- Run `npm run build` in `dental-pe-nextjs/` after every change to verify TypeScript compilation
- Server Components (`page.tsx`) fetch; client shells (`*-shell.tsx`) handle interactivity
- URL params sync via `useUrlFilters` — preserve URL shareability

### Do not regress (key invariants — full bug-fix log in CLAUDE_ARCHIVE.md)

- KPI icons are Lucide JSX components; KpiCard `subtitle` prop for tiered display
- `getRetirementRiskCount`: watched ZIPs + `year_established < 1995` + all 7 independent classifications
- `getAcquisitionTargetCount`: watched ZIPs + `buyability_score >= 50`
- `getPracticeStats`: tiered corporate (`corporateHighConf`, `corporate`, `enriched`)
- ZIP Score: `fmtPct`; confidence/opportunity_score renderers handle both cell-value AND row-object
- City practice tree paginates WITHIN each ZIP chunk (Supabase 1000-row limit)
- Consolidation map: pct from `corporate_share_pct * total_gp_locations`
- Job Market enrichment: `data_axle_import_date IS NOT NULL`
- `PracticeStats` interface in both `types.ts` and `types/index.ts`; `HomeSummary` has `enrichedCount`
- UI overhaul 2026-03-15: warm light, tab nav, sidebar 4 sections, Home activity feed — all 11 pages, tabs URL-synced, build passes

## Pipeline File Quick Reference

Full descriptions in `CLAUDE_ARCHIVE.md` §"Pipeline File Quick Reference".

| File | Purpose |
|------|---------|
| `dashboard/app.py` | Streamlit, 6 pages (legacy) |
| `scrapers/database.py` | SQLAlchemy models, `init_db()`, `normalize_punctuation()` curly→ASCII (F19) |
| `scrapers/sync_to_supabase.py` | SQLite→Supabase. 3 strategies, per-row savepoints, signal handlers, MIN_ROWS_THRESHOLD floors, post-sync verification |
| `scrapers/nppes_downloader.py` | Federal provider data |
| `scrapers/data_axle_importer.py` | 7-phase + Pass 6 corporate linkage |
| `scrapers/merge_and_score.py` | Dedup deals, score ZIPs, `ensure_chicagoland_watched()`, saturation |
| `scrapers/dso_classifier.py` | 4-pass: name → location → entity_classification (uses `practice_locations`) → corporate escalation |
| `scrapers/pesp_scraper.py` | PE deals. DNS retry + COMMENTARY_PATTERNS prefilter |
| `scrapers/gdn_scraper.py` | DSO roundups. `_is_roundup_link`, `_PASS_THROUGH_SET`, `_DEAL_VERB_SET`, `_PARTNERS_VERB_NEXT` (F21) |
| `scrapers/adso_location_scraper.py` | DSO offices. HTTP_TIMEOUT=(10,30), MAX_SECONDS_PER_DSO=300, log in `finally` |
| `scrapers/ada_hpi_{downloader,importer}.py` | ADA benchmark XLSX |
| `scrapers/pitchbook_importer.py` | PitchBook CSV/XLSX |
| `scrapers/data_axle_exporter.py` | ZIP-batch export (7 CHI zones + BOS) |
| `scrapers/research_engine.py` | Anthropic client. Haiku/Sonnet, web search, batch, circuit breaker, EVIDENCE PROTOCOL |
| `scrapers/intel_database.py` | Intel CRUD, 90d TTL |
| `scrapers/qualitative_scout.py` | ZIP CLI |
| `scrapers/practice_deep_dive.py` | Practice CLI (two-pass Haiku→Sonnet) |
| `scrapers/weekly_research.py` | Automated runner. `validate_dossier()`, `DRIFT_REMAP`, budget caps |
| `scrapers/pipeline_logger.py` | JSONL event logger |
| `scrapers/compute_signals.py` | Materializes `practice_signals` + `zip_signals`. NPI-null guard (`eb75c6c`), watched-zip filter |
| `scrapers/cleanup_pesp_junk.py` | One-shot: drop PESP rows with commentary-fragment targets. Idempotent |
| `scrapers/pesp_airtable_scraper.py` + `pesp_csv_importer.py` | F09 Airtable-era PESP. CSV mode prod; auto mode is Playwright stub. Per-month: open PESP → ⋯ on Airtable → CSV → run importer |
| `scrapers/fast_sync_watched.py` | Partial sync: watched_zips only (~14k), skip global 402k |
| `scrapers/dossier_batch/launch.py` | Batch launcher. Flags `--budget`, `--cost-per-practice`, `--target-count`, `--metro-pattern`, `--exclude-zip-pattern`. Writes `data/last_batch_id.json` + `/tmp/full_batch_id.txt` |
| `scrapers/dossier_batch/poll.py` | Polls 30s up to 90min, validates, stores, syncs. Batch_id: `--batch-id` → JSON → `/tmp` |
| `scrapers/dossier_batch/poll_zip_batches.py` | 290-ZIP re-research poller |
| `scrapers/dossier_batch/upsert_practice_intel.py` | UPSERT `practice_intel` (skip TRUNCATE of full_replace) |
| `scrapers/dossier_batch/migrate_verification_cols.py` | Adds 3 verification cols to BOTH DBs. Idempotent |
| `pipeline_check.py` | Diagnostic health check |

## Entity Classification System

Assigned by DSO classifier Pass 3 (`classify_entity_types()` in `dso_classifier.py`) using provider count at address, last-name match, taxonomy codes, corporate signals, Data Axle data. Reasoning stored in `classification_reasoning`. Priority (first wins): non_clinical > specialist > dso_national > corporate signals > family_practice > large_group > small_group > solo variants.

### 11 values

| Value | Definition |
|-------|-----------|
| `solo_established` | Single-provider, 20+ years (or default for single providers w/ limited data) |
| `solo_new` | Single-provider, last 10 years |
| `solo_inactive` | Single-provider, no phone AND no website |
| `solo_high_volume` | Single-provider, 5+ employees or $800k+ revenue |
| `family_practice` | 2+ providers same address, shared last name |
| `small_group` | 2-3 providers same address, different last names, no DSO match |
| `large_group` | 4+ providers same address, no DSO brand match |
| `dso_regional` | Independent-looking but corporate signals (parent co, shared EIN, franchise, branch type, generic brand + high provider count) |
| `dso_national` | Known national/regional DSO brand (Aspen, Heartland, etc.) matched high-confidence |
| `specialist` | Ortho/Endo/Perio/OMS/Pedo by taxonomy or name keyword |
| `non_clinical` | Lab, supply, billing, staffing |

### Canonical groupings (Next.js)

- **Independent:** solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group
- **Corporate:** dso_regional, dso_national
- **Specialist:** specialist
- **Non-clinical:** non_clinical
- **Unknown:** entity_classification IS NULL AND ownership_status NOT IN (dso-affiliated, pe-backed)

### Saturation, specialist, confidence, modifiers, market types

**Saturation** (in `zip_scores`, via `merge_and_score.compute_saturation_metrics()`): `dld_gp_per_10k` (national avg ~6.1, lower=less competition), `buyable_practice_ratio` (% GP in solo_established/inactive/high_volume), `corporate_share_pct` (% GP in dso_*), `market_type` (NULL when `metrics_confidence=low`), `people_per_gp_door`.

**Specialist** if ANY: (1) taxonomy starts 1223D/E/P/S/X (excludes 1223G, 122300); (2) name contains ORTHODONT, PERIODON, ENDODONT, ORAL SURG, MAXILLOFACIAL, PEDIATRIC DENT, PEDODONT, PROSTHODONT, IMPLANT CENT. Location is GP if ≥1 non-specialist non-clinical practice. Specialist-only → `total_specialist_locations`.

**Confidence:** `metrics_confidence` high (coverage>80% AND unknown<20%) / medium (>50%/<40%) / low. `market_type_confidence` confirmed/provisional/insufficient_data (low→NULL). `classification_confidence` 0-100 from name match.

**Buyability modifiers (Phase 5, additive after `compute_buyability()`):** family_practice **-20**; same name/EIN in 3+ watched ZIPs **-15**.

**Market types (priority order):** low_resident_commercial > high_saturation_corporate > corporate_dominant > family_concentrated > low_density_high_income > low_density_independent > growing_undersupplied > balanced_mixed > mixed.

## Qualitative Intelligence Layer

AI research layered on pipeline data. Claude API + web search. Architecture: `research_engine.py` (Anthropic API client), `intel_database.py` (CRUD, 90d TTL), `qualitative_scout.py` (ZIP CLI), `practice_deep_dive.py` (practice CLI, two-pass Haiku→Sonnet), `weekly_research.py` (automated runner with `validate_dossier`, `DRIFT_REMAP`, budget caps).

### Tables

- **`zip_qualitative_intel`** — one row per watched ZIP. Signals: housing, schools, retail, commercial, dental news, real estate, zoning, population, employers, competitors. Synthesis: demand_outlook, supply_outlook, investment_thesis, confidence. TTL 90d.
- **`practice_intel`** — one row per NPI. Signals: website, services, technology, Google reviews, hiring, acquisition news, social, HealthGrades, ZocDoc, doctor profile, insurance. Assessment: red_flags, green_flags, overall_assessment, acquisition_readiness, confidence. **Verification:** `verification_searches`, `verification_quality` (verified\|partial\|insufficient), `verification_urls`. TTL 90d.

### Cost model (March 2026)

ZIP Scout (Haiku 4.5) ~$0.04-0.06/ZIP. Practice Research (Haiku 4.5) ~$0.075 retail / **~$0.008 batch** (use $0.008 for planning — see Anti-Hallucination §). Two-Pass Deep (Haiku→Sonnet) ~$0.28 retail. Batch API: 50% token discount, web_search NOT discounted.

### Two-pass escalation

Pass 1 (Haiku) baseline. Escalate if `readiness=high|medium` AND `confidence!=high`, OR 3+ green flags. Never escalates `unlikely`/`unknown`. Pass 2 (Sonnet) deeper search, verified findings. Merge: dict union, list concat, string override.

### CLI

```bash
# ZIP
python3 scrapers/qualitative_scout.py --zip 60491
python3 scrapers/qualitative_scout.py --metro chicagoland
python3 scrapers/qualitative_scout.py --status
python3 scrapers/qualitative_scout.py --report 60491

# Practice
python3 scrapers/practice_deep_dive.py --zip 60491 --top 10 --deep
python3 scrapers/practice_deep_dive.py --npi 1234567890
python3 scrapers/practice_deep_dive.py --status
python3 scrapers/practice_deep_dive.py --report 1234567890

# Weekly
python3 scrapers/weekly_research.py --budget 5
python3 scrapers/weekly_research.py --dry-run
```

### Rules

- `ANTHROPIC_API_KEY` required (local + Vercel separately for compound-narrative)
- Cost log: `data/research_costs.json` (500-entry rolling)
- Both intel tables sync `full_replace`
- NEVER fabricate — prompts say "return null, never fabricate"
- ALL scripts use `pipeline_logger.log_scrape_start/complete()` + `logger_config.get_logger()`
- TTL 90d — `--refresh` to override
- `research_engine.py` uses raw HTTP `requests`, NOT `anthropic` SDK
- Circuit breaker: 3 consecutive failures → `CircuitBreakerOpen` aborts (prevents 290 × 120s = 9.6hr hang)

## Anti-Hallucination Defense (April 25, 2026 — Do Not Regress)

Every dossier passes a 4-layer gate before landing in `practice_intel`. 200-practice validation batch: 87% pass rate, 0 hallucinations. Full validation outcomes + cost calibration tables + RESOLVED known-issues commits: `CLAUDE_ARCHIVE.md` §"Anti-Hallucination Defense".

| Layer | Where | What |
|-------|-------|------|
| **1. Forced search** | `research_engine.py::_call_api(force_search=True)` sets `tool_choice={"type":"tool","name":"web_search"}` | ≥1 web_search guaranteed per practice. Practice path: `max_searches=5` |
| **2. Per-claim source URLs** | PRACTICE_USER schema in `research_engine.py` requires `_source_url` on every section | Every non-null field traceable. `"no_results_found"` when search yields nothing |
| **3. Self-assessment** | Terminal `verification` block: `{searches_executed, search_queries, evidence_quality (verified\|partial\|insufficient), primary_sources}` | Model self-rates. `insufficient` → auto-reject |
| **4. Post-validation gate** | `weekly_research.py::validate_dossier(npi, data) -> (ok, reason)` | 5 rules: `missing_verification_block`, `insufficient_searches(N)`, `evidence_quality=insufficient`, `website.url_without_source`, `google.metrics_without_source`. Quarantined dossiers NOT stored |

**Schema invariants:** `PracticeIntel` model (`database.py:426-428`) has `verification_searches` (Int), `verification_quality` (String(20) indexed), `verification_urls` (Text) on BOTH DBs. `Base.metadata.create_all()` does NOT alter existing tables — column adds require explicit `ALTER TABLE`. `intel_database.py::store_practice_intel()` writes the 3 cols; `weekly_research.py::retrieve_batch()` calls `validate_dossier()` BEFORE store.

**EVIDENCE PROTOCOL** (PRACTICE_SYSTEM): (1) ≥2 web_search per practice (`<name> <city> <state>`, `<name> <city> reviews`); (2) every non-null field has URL in `_source_url`; (3) never infer from priors; (4) brand/tech claims from practice's own website; (5) empty search → null + `_source_url="no_results_found"`; (6) terminal `verification` block mandatory; (7) `evidence_quality` exactly `verified|partial|insufficient` — never `high|low|medium` (F33).

**Cost:** Use **Anthropic console** (https://console.anthropic.com/usage), NOT `poll.py.totals.total_cost_usd` (~8.5-11× overcount). **Plan $0.008/practice batch** ($16 for 2000-practice, $80 for 10k). Flag if real >$0.015. Don't quote `poll.py` cost — reconcile first.

**End-to-end recipe:**

```bash
# 1. one-time on fresh DB, idempotent
python3 scrapers/dossier_batch/migrate_verification_cols.py

# 2. submit (default: top-1-per-ZIP Chicagoland, $11)
python3 scrapers/dossier_batch/launch.py
# Bigger pool:
#   python3 scrapers/dossier_batch/launch.py --target-count 2000 --budget 250 --exclude-zip-pattern '606%'

# 3. poll + validate + store + sync (background)
nohup python3 scrapers/dossier_batch/poll.py > /tmp/poll.log 2>&1 &

# 4. when /tmp/full_batch_summary.json appears
python3 -c "import json; s=json.load(open('/tmp/full_batch_summary.json')); print(f\"stored={s['stored']} rejected={s['rejected']} cost=\${s['totals']['total_cost_usd']}\")"
```

**RESOLVED issues (commits in archive):** F33 enum drift (DRIFT_REMAP + quarantine, `c4f7acc`); F23 durable batch_id (`data/last_batch_id.json` + `/tmp/full_batch_id.txt`, `81be614`); F24 SQLite migration idempotency (`81be614`); F25 `launch.py` flags (`81be614`); `practice_signals` FK violation (watched-zip filter + npi NOT NULL guard `eb75c6c` + `MIN_ROWS_THRESHOLD["practice_signals"]=1000`).

**Backfill outlook:** ~8,559 unresearched CHI independents (~$68 batch / ~$642 retail). Tiered (solo_high_volume + family_practice + solo_inactive, buyability≥50): ~2,000 × $0.008 = ~$16. BOS Metro: ~$1.

## Pipeline Audit (Apr 22-23, 2026) + F-Fix Verification (Apr 26 — 33/33 PASS)

3-week pipeline outage root-caused; all 11 fixes in `main`. Multi-agent re-audit on Apr 26 verified F01-F33 PASS. Full bug-fix table, gotchas, test suite, F-fix verification per fix, cost calibration, multi-agent coexistence rules, direct-verify commands: `CLAUDE_ARCHIVE.md` §§"Pipeline Audit" + "Session Digest", plus `SCRAPER_AUDIT_STATUS.md`, `IMPLEMENTATION_PLAN_2026_04_26.md`.

**Key invariants in `main`:**
- `refresh.sh::run_step()` reaps descendants via `pkill -TERM -P $bgpid`
- Per-row `conn.begin_nested()` savepoint in `_sync_incremental_updated_at` (deals) + `_sync_incremental_id` (practice_changes) — handles `uix_deal_no_dup` dups
- `_sync_watched_zips_only` uses `TRUNCATE practices CASCADE` (transactional in Postgres) — avoids `practice_changes_npi_fkey` violation
- `MIN_ROWS_THRESHOLD` floors: `platforms=20`, `pe_sponsors=10`, `zip_overviews=5`, `practice_signals=1000`
- SIGTERM/SIGINT handler with 8 checkpoints; `_verify_table_count()` post-sync; `AssertionError` on mismatch
- PESP DNS retry + 40+ COMMENTARY_PATTERNS prefilter
- GDN `_PASS_THROUGH_SET={"&","and","of"}`, expanded `_DEAL_VERB_SET`, `_PARTNERS_VERB_NEXT={"with","to","and"}` (F21)
- ADSO `HTTP_TIMEOUT=(10,30)`, `MAX_SECONDS_PER_DSO=300`, `log_scrape_complete()` in `finally`
- `database.normalize_punctuation()` curly→ASCII at GDN/PESP boundary (F19)
- F28 GitHub Actions weekly invariants CI: `.github/workflows/data-invariants.yml`, cron `0 13 * * 1`, Discord webhook
- F-fix span: `5d00689` (Apr 25 12:54) → `e3e2d1c` (Apr 26 12:02), ~23h, 50+ commits, 4 parallel sessions
- Test suite `scrapers/test_sync_resilience.py` — 11 tests pass

**Keep-alive** (`.github/workflows/keep-supabase-alive.yml`) cron `0 12 */3 * *`. **USER ACTION REQUIRED:** add `SUPABASE_URL` + `SUPABASE_ANON_KEY` repo secrets.

**Direct-verify commands:**

```bash
# F32 hygienist cleanup live check
cd /Users/suleman/dental-pe-tracker && python3 -c "import sqlite3; c=sqlite3.connect('data/dental_pe_tracker.db'); print('global:', c.execute('SELECT COUNT(*) FROM practices').fetchone()[0]); print('watched:', c.execute('SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code').fetchone()[0]); print('non_dental_leak:', c.execute(\"SELECT COUNT(*) FROM practices WHERE taxonomy_code IS NOT NULL AND taxonomy_code NOT LIKE '1223%'\").fetchone()[0])"

# F27 vitest
cd /Users/suleman/dental-pe-tracker/dental-pe-nextjs && npx vitest run src/__tests__/classification-primary.test.ts

# F19/F21 GDN parser
cd /Users/suleman/dental-pe-tracker && python3 -m pytest scrapers/test_gdn_parser.py -k "partners or apostrophe" -v

# Full F-fix timeline
git log --pretty=format:"%h | %ad | %s" --date=iso 5d00689^..e3e2d1c
```

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` for the Streamlit app OR Next.js frontend. Use `/data-axle-workflow` for Data Axle export/import. Use `/debug-pipeline` for scraper failures or data issues.
