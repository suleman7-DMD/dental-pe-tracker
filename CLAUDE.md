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

### NPI rows vs clinic locations — read this before reading any count

NPPES emits one row per provider (NPI-1) AND one row per organization (NPI-2) at the same physical address — so `practices` is keyed by NPI, NOT by clinic. In watched ZIPs, **13,818 NPI rows** in `practices` (post-F32 hygienist-leak cleanup, was 14,053) collapse to **5,732 deduped clinic locations** in `practice_locations` (~2.6× NPI fan-out). Every "381,598 practices" / "13,818 in watched ZIPs" callout is an **NPI-row count**, not a location count. Location-deduped denominator is `SUM(zip_scores.total_gp_locations)` for GP clinics and `practice_locations.location_id` for any address-keyed query. If a Supabase row count looks ~2.6× larger than expected, you're looking at NPI rows; that is not sync drift.

### Numbers cheat-sheet — F29 (read before quoting any count)

For full reconciliation reasoning + Dentagraphics gap analysis, see `RECONCILIATION_VERDICT_2026_04_26.md` §3 (verdict) + §2 (within-unit consistency).

| # | Value | Unit | Scope | Source-of-truth | Surfaces on |
|---|------:|------|-------|-----------------|-------------|
| 1 | **381,598** | NPI rows | global (federal) | `SELECT COUNT(*) FROM practices` (post-F32 cleanup; was 402,004) | "382k dentist practices" headline |
| 2 | **13,818** | NPI rows | 290 watched ZIPs | `practices` join `watched_zips` (post-F32; was 14,053) | Job Market header, NPI-row KPIs |
| 3 | **5,732** | locations | 290 watched ZIPs (raw, all classifications) | `practice_locations` join `watched_zips` | Internal only — NEVER user-facing |
| 4 | **4,889** | GP locations | 290 watched ZIPs | `SUM(zip_scores.total_gp_locations)` post-`dc18d24` | Home, Market Intel, Job Market, Launchpad headline KPIs |
| 5 | **4,575** | GP locations | Chicagoland (269 IL ZIPs) | watched + state=IL filter on (4) | Warroom Sitrep, Market Intel CHI |
| 6 | **314** | GP locations | Boston Metro (21 MA ZIPs) | watched + state=MA filter on (4); 4,575+314=4,889 ✅ | Boston-scoped surfaces |
| 7 | **4,574** | GP locations | all-IL (statewide, NOT just watched) | `practice_locations` filter to state=IL + GP filter | Dentagraphics-comparable scope |
| 8 | **4,409** | active-GP | all-IL, drop `solo_inactive` (no phone+no website) | (7) minus 165 contactless solos | Honest active-GP claim |
| 9 | **3,961** | (their unit unverifiable) | all-IL | Dentagraphics infographic page (verified F30 2026-04-26) | External benchmark — gap to (7) is **+15.5%**, gap to (8) is **+11.3%** |
| 10 | **882** | corporate NPIs | 13,818 NPIs in watched | `entity_classification IN (dso_regional,dso_national)` | "Total corporate" NPI-row KPI = 6.38% post-F32 |
| 11 | **225** | corporate locations | 4,889 GP locs in watched | same on `practice_locations` | Headline corporate share = **4.60%** |

**Single most-confused comparison:** Job Market shows ~14k "practices" (NPI rows, line 2), Warroom shows ~5,491 (location-deduped, line 4 minus a few). Both correct under their own units. Conversion factor is structural NPPES dual-emission (NPI-1 individual + NPI-2 organization at same address).

**The Dentagraphics gap cannot be attributed (F30 outcome).** Their published count is **3,961** for IL with population 12,707,929; only "data courtesy of Medicaid.gov" attribution and explicit "as is, with all faults" disclaimer. No methodology — no row-counting rule, no active-billing filter, no inclusion criteria, no snapshot date. The +15.5% gap (our 4,574 vs their 3,961) cannot be assigned. **Our number has full SQL provenance; theirs has explicit disclaimer.** Do not claim "we match Dentagraphics" — but also do not claim "they're correct and we're wrong."

### SQLite tables

| Table | Rows | Notes |
|-------|-----:|-------|
| `practices` | 381,598 global / 13,818 watched | PK `npi`. **`entity_classification`** is the canonical ownership signal (populated for all watched-ZIP NPIs). Field list: see `database.py` Practice model |
| `practice_locations` | 5,732 watched (4,889 GP) | Address-deduped clinic table (CHI 4,575 + BOS 314). PK `location_id`. **All Sitrep KPIs + headline corporate %/independent % source from this table — NOT `practices`.** Joined via `practice_to_location_xref` |
| `deals` | 2,861 SQLite / 2,861 Supabase | Mix: 2,532 GDN + 353 PESP + 10 PitchBook. Drift reconciled `ac2140a` (2026-04-25) — Pass 2 of `_reconcile_deals()` (`sync_to_supabase.py:924`, called from `:1287`) keys NULL-target rows by composite hash. Coverage Oct 2020 – Mar 2026 |
| `practice_changes` | 8,848 | Change log (name/address/ownership) |
| `zip_scores` | 290 | One row per watched ZIP. `total_gp_locations` is the canonical "how many clinics in this ZIP" denominator |
| `watched_zips` | 290 (269 IL + 21 MA) | Auto-backfilled by `ensure_chicagoland_watched()` |
| `dso_locations` | 92 | Scraped DSO offices |
| `ada_hpi_benchmarks` | 918 | State-level DSO affiliation by career stage (2022-2024). `updated_at` populated F20 |
| `practice_signals` | 13,818 NPI | 8-flag Warroom Hunt overlay (stealth_dso, phantom_inventory, family_dynasty, micro_cluster, retirement_combo, last_change_90d, high_peer_retirement, revenue_default) |
| `zip_signals` | 290 SQLite / **0 Supabase** | Sync gap as of 2026-04-26. Repair: `python3 scrapers/sync_to_supabase.py --tables zip_signals` |

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

### Pages (12 total)

| Route | Page | What It Shows |
|-------|------|---------------|
| `/` | Home | 6 KPI cards, two-column (recent deals + activity feed from practice_changes), data freshness bar, 2x3 quick nav |
| `/launchpad` | Launchpad | First-job finder. Track-weighted 0-100 scoring (Succession/Apprentice, High-Volume Ethical, DSO Associate). 20-signal catalog. 5 tiers. 4 living-location scopes. 6-tab practice dossier. Curated DSO tier list. Compound thesis uses Sonnet 4.6 + reads `practice_intel`. |
| `/warroom` | Warroom | Chicagoland command surface. 2 modes (Hunt/Investigate), 4 lenses (consolidation/density/buyability/retirement), 11 scopes. Always-visible Sitrep KPI strip. Intent bar (⌘K), Living Map, ranked target list, ZIP + practice dossiers, pinboard, signal flag overlays (8 practice + 1 ZIP), keyboard shortcuts (`?`, `1`=Hunt, `2`=Investigate, `R`/`P`/`V`/`[`/`]`/`Esc`), URL-synced state. |
| `/deal-flow` | Deal Flow | 4 tabs: Overview \| Sponsors \| Geography \| Deals. Persistent KPI strip. |
| `/market-intel` | Market Intel | 3 tabs: Consolidation \| ZIP Analysis \| Ownership. Persistent tiered consolidation KPIs. Cross-link banner to Warroom. |
| `/buyability` | Buyability | Verdict extraction from notes, 4 category KPIs, ZIP filter, sortable table with CSV export |
| `/job-market` | Job Market | 4 tabs: Overview \| Map \| Directory \| Analytics. Persistent KPI strip + Living Location Selector (4 presets). |
| `/research` | Research | PE sponsor profiles, DSO platform profiles, state deep dives, SQL explorer (SELECT-only, forbidden keywords) |
| `/intelligence` | Intelligence | AI qualitative research — 6 KPIs, ZIP intel table with expandable 10-signal panels, practice dossier table with readiness/confidence badges. Cross-link to Warroom Investigate. |
| `/system` | System | Data freshness, source coverage, completeness bars, pipeline log viewer, manual entry forms |
| `/data-breakdown` | Data Breakdown | Per-KPI provenance — every "X practices in Chicagoland" number traces back to source query, table, ZIP scope, timestamp. Added 2026-04-26 (F31). |

### Data flow pattern

1. **Server Components** (`page.tsx`) fetch from Supabase server-side
2. Pass to **Client Component shells** (`'use client'`) via props
3. Client shells handle filters, UI state, refetching via **React Query** (30min stale, 30min gc; per-hook overrides for warroom/launchpad)
4. URL params sync (`useUrlFilters` hook)
5. Supabase queries in `src/lib/supabase/queries/` organized by table

### Entity classification in Next.js (CRITICAL)

`entity_classification` (11 types) is the **PRIMARY** field for ALL ownership analysis. `ownership_status` is ONLY a fallback when entity_classification is NULL. Vitest test `src/__tests__/classification-primary.test.ts` (F27) enforces this — it walks src/ and fails if any file references `ownership_status` without an `entity_classification` companion (10-entry allowlist, each justified).

Helpers in `src/lib/constants/entity-classifications.ts`:
- `isIndependentClassification(ec)` — true for solo_*, family_practice, small_group, large_group
- `isCorporateClassification(ec)` — true for dso_regional, dso_national
- `classifyPractice(entityClassification, ownershipStatus)` — returns "independent" | "corporate" | "specialist" | "non_clinical" | "unknown"
- `getEntityClassificationLabel(value)` — human-readable label
- Exports also: `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`

### Scoring (`src/lib/utils/scoring.ts`)

- `computeJobOpportunityScore()` — 0-100, entity_classification primary with ownership_status fallback. Factors: ownership (30pts), buyability (25/15pts), employees (20/10pts), year_established (15/8pts)
- `isRetirementRisk()` — independent + 30+ years
- `getPracticeAge()` — years since year_established

### Design system (warm light theme, updated 2026-03-15)

- **Bg:** #FAFAF7 app, #FFFFFF cards, #F7F7F4 elevated/hover, #F5F5F0 inset/input
- **Sidebar:** #2C2C2C dark (intentional contrast), goldenrod #B8860B accent for active items
- **Text:** #1A1A1A primary, #6B6B60 secondary, #9C9C90 muted
- **Borders:** #E8E5DE default, #D4D0C8 hover
- **Accent:** goldenrod #B8860B (was blue #3B82F6)
- **Status:** Corporate #C23B3B, Independent #2563EB, Specialist #0D9488, Group #6366F1
- **KPIs:** 28px JetBrains Mono bold, goldenrod accent border
- Full tokens in `src/lib/constants/design-tokens.ts`.

### Sidebar — 4 grouped sections, **11 nav items**

- **OVERVIEW:** Dashboard (`/`), Launchpad, Warroom
- **MARKETS:** Job Market, Market Intel, Buyability
- **ANALYSIS:** Deal Flow, Research, Intelligence, Data Breakdown (added 2026-04-26)
- **ADMIN:** System

### File map (one-line per directory — grep components by name)

- `src/app/` — `layout.tsx` (root, fonts/providers/sidebar), `page.tsx` (Home), `globals.css` (Tailwind 4 + warm light)
- `src/app/<route>/_components/` — orchestrator `*-shell.tsx` + sub-components per route. Shells: launchpad, warroom, deal-flow, market-intel, buyability, job-market, intelligence, research, system. Notable cross-page: `practice-dossier.tsx` (Launchpad 6-tab drawer), `dossier-drawer.tsx` (Warroom), `living-map.tsx` (Mapbox), `intent-bar.tsx` (⌘K), `practice-density-map.tsx` (Job Market hex+dot)
- `src/app/api/` — `deals/`, `practices/`, `sql-explorer/` (SELECT-only), `watched-zips/`, `launchpad/compound-narrative/route.ts` (Sonnet 4.6, reads `practice_intel`, ephemeral cache, 200-300 word output with `[source: domain]` citations, hedge phrases when evidence is `partial`/`insufficient`)
- `src/lib/launchpad/` — `scope.ts`, `signals.ts` (20 IDs + LaunchpadBundle), `ranking.ts` (TRACK_MULTIPLIERS), `dso-tiers.ts` (16 curated DSOs)
- `src/lib/warroom/` — `mode.ts`, `scope.ts` (11 scopes + `normalizeWarroomDataScope()`), `geo.ts`, `signals.ts`, `data.ts` (`getSitrepBundle()`), `intent.ts`, `ranking.ts`, `briefing.ts`
- `src/lib/supabase/queries/` — `deals.ts`, `practices.ts`, `zip-scores.ts`, `watched-zips.ts`, `practice-changes.ts`, `ada-benchmarks.ts`, `system.ts` (ADSO + ADA HPI freshness via `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at`), `intel.ts`, `launchpad.ts`
- `src/lib/supabase/` — `client.ts`, `server.ts`, `types.ts`
- `src/lib/constants/` — `entity-classifications.ts`, `design-tokens.ts`, `living-locations.ts`, `metro-centers.ts`, `zip-centroids.ts`, `sql-presets.ts` (use entity_classification, NOT ownership_status), `deal-type-colors.ts`, `us-states.ts`
- `src/lib/utils/` — `formatting.ts`, `scoring.ts`, `csv-export.ts`, `colors.ts`
- `src/lib/hooks/` — `use-url-filters.ts`, `use-sidebar.ts`, `use-launchpad-state.ts`, `use-launchpad-data.ts`, `use-warroom-state.ts`, `use-warroom-data.ts`, `use-warroom-intel.ts`
- `src/lib/types/` — `index.ts` (Deal, Practice, ZipScore, WatchedZip, HomeSummary with `enrichedCount`, PracticeStats), `intel.ts` (extended with `verification_searches`, `verification_quality`, `verification_urls`)
- `src/components/data-display/` — `data-table.tsx` (TanStack: render functions MUST return primitives), `kpi-card.tsx` (icon/label/value/delta/accent/`subtitle`), `data-freshness-bar.tsx`, `section-header.tsx`, `status-badge.tsx`, `confidence-stars.tsx`
- `src/components/charts/` — Recharts wrappers (bar, stacked-bar, grouped-bar, area, donut, histogram, scatter, chart-container)
- `src/components/maps/` — `map-container.tsx` (Mapbox GL wrapper)
- `src/components/layout/` — `sidebar.tsx` (220px/60px collapsible, dark, 4 grouped sections), `warroom-cross-link.tsx`
- `src/components/ui/` — shadcn primitives
- `src/providers/` — `query-provider.tsx`, `sidebar-provider.tsx`

Full pre-condensation file map (every component path verbatim): see `CLAUDE_ARCHIVE.md` §"Next.js File Map (directory-grouped)".

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

- All KPI icons are Lucide JSX components; KpiCard supports `subtitle` for tiered display
- Home page consolidatedPct includes % suffix
- `getRetirementRiskCount` filters by watched ZIPs + `year_established < 1995` + all 7 independent classifications
- `getAcquisitionTargetCount` filters by watched ZIPs + `buyability_score >= 50`
- `getPracticeStats` returns full `PracticeStats` with tiered corporate (`corporateHighConf`, `corporate`, `enriched`)
- ZIP Score table uses `fmtPct`; confidence/opportunity_score renderers handle both cell-value and row-object patterns
- City practice tree paginates WITHIN each ZIP chunk (Supabase 1000-row limit)
- Consolidation map computes pct from `corporate_share_pct * total_gp_locations`
- Job Market enrichment count uses `data_axle_import_date IS NOT NULL`
- `entity-classifications.ts` exports `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`
- `PracticeStats` interface in both `types.ts` and `types/index.ts`; `HomeSummary` includes `enrichedCount`
- UI overhaul (2026-03-15): warm light theme, tab nav on Deal Flow/Market Intel/Job Market, sidebar 4 sections, Home activity feed — all 11 pages render with warm light, tabs URL-synced, build passes

## Pipeline File Quick Reference

| File | Lines | What |
|------|-------|------|
| `dashboard/app.py` | 2,583 | Streamlit dashboard — 6 pages (legacy) |
| `scrapers/database.py` | 542 | SQLAlchemy models, `init_db()`, helpers, `normalize_punctuation()` (curly→ASCII) |
| `scrapers/sync_to_supabase.py` | — | SQLite → Supabase sync (3 strategies, per-row savepoints, signal handlers, MIN_ROWS_THRESHOLD floors, post-sync verification) |
| `scrapers/nppes_downloader.py` | 681 | Downloads + imports federal dental provider data |
| `scrapers/data_axle_importer.py` | 2,650 | Data Axle CSV import, 7-phase pipeline + Pass 6 corporate linkage |
| `scrapers/merge_and_score.py` | 1,070 | Dedup deals, score ZIPs, `ensure_chicagoland_watched()`, saturation metrics |
| `scrapers/dso_classifier.py` | 1,570 | 4-pass: Pass 1 name pattern, Pass 2 location, Pass 3 entity_classification (location-deduped — uses `practice_locations`, NOT `practices`), Pass 4 corporate signal escalation |
| `scrapers/pesp_scraper.py` | 1,201 | PE deal scraper. DNS retry wrapper + COMMENTARY_PATTERNS prefilter |
| `scrapers/gdn_scraper.py` | 1,210 | DSO deal roundups. MAX_RETRIES=3, `_is_roundup_link` guard, `_PASS_THROUGH_SET` connectors, expanded `_DEAL_VERB_SET`, `_PARTNERS_VERB_NEXT` lookahead (F21) |
| `scrapers/adso_location_scraper.py` | 968 | DSO office locations. HTTP_TIMEOUT=(10,30), MAX_SECONDS_PER_DSO=300, log_scrape_complete in finally |
| `scrapers/ada_hpi_downloader.py` | 237 | Auto-downloads ADA benchmark XLSX |
| `scrapers/ada_hpi_importer.py` | 351 | Parses ADA HPI XLSX by state/career stage |
| `scrapers/pitchbook_importer.py` | 616 | CSV/XLSX import from PitchBook |
| `scrapers/data_axle_exporter.py` | 805 | Interactive ZIP-batch export tool (7 Chicagoland zones + Boston) |
| `scrapers/research_engine.py` | 400 | Anthropic API client (Haiku/Sonnet, web search, batch API, circuit breaker, EVIDENCE PROTOCOL) |
| `scrapers/intel_database.py` | 266 | CRUD for intel tables (90-day cache TTL) |
| `scrapers/qualitative_scout.py` | 380 | CLI: ZIP-level market research |
| `scrapers/practice_deep_dive.py` | 577 | CLI: practice-level due diligence (two-pass Haiku→Sonnet) |
| `scrapers/weekly_research.py` | 309 | Automated weekly runner (batch API, budget caps, `validate_dossier()`, `DRIFT_REMAP`) |
| `scrapers/pipeline_logger.py` | 295 | Structured JSON-Lines event logger |
| `scrapers/compute_signals.py` | 1,424 | Materializes per-practice + per-ZIP signal flags into `practice_signals` and `zip_signals`. NPI-null guard (`eb75c6c`); filters watched ZIPs to prevent FK violations on global-pool rows |
| `scrapers/cleanup_pesp_junk.py` | 80 | One-shot cleanup CLI: deletes PESP rows whose `target_name` matches commentary fragments. Idempotent |
| `scrapers/pesp_airtable_scraper.py` | 342 | F09 Airtable-era PESP ingester. CSV mode (`csv <path>`) production-ready. Auto mode is a Playwright stub. Per-month manual: open PESP post → ⋯ on Airtable → "Download CSV" → run importer |
| `scrapers/pesp_csv_importer.py` | 80 | F09 thin wrapper around `pesp_airtable_scraper.py` CSV mode |
| `scrapers/fast_sync_watched.py` | 200 | Fast partial sync: re-uploads ONLY watched_zips practices (~14k) without touching global 402k pool |
| `scrapers/dossier_batch/launch.py` | — | Generic batch launcher. Defaults: top-1-per-ZIP Chicagoland, $11 budget. Flags: `--budget`, `--cost-per-practice`, `--target-count`, `--metro-pattern`, `--exclude-zip-pattern`. Writes to `data/last_batch_id.json` (durable) + `/tmp/full_batch_id.txt` (back-compat) |
| `scrapers/dossier_batch/poll.py` | — | Polls every 30s up to 90 min, runs `validate_dossier()`, stores passing dossiers, runs sync. Resolves batch_id: `--batch-id` → durable JSON → legacy `/tmp` |
| `scrapers/dossier_batch/poll_zip_batches.py` | — | Auto-retrieval poller for the 290-ZIP re-research batches |
| `scrapers/dossier_batch/upsert_practice_intel.py` | — | Standalone UPSERT path: copies `practice_intel` from SQLite to Supabase via `INSERT ... ON CONFLICT DO UPDATE`, skipping the TRUNCATE that `full_replace` uses |
| `scrapers/dossier_batch/migrate_verification_cols.py` | — | Adds `verification_searches`, `verification_quality`, `verification_urls` columns to `practice_intel` on BOTH databases. Idempotent (Postgres `ADD COLUMN IF NOT EXISTS`; SQLite PRAGMA introspection) |
| `pipeline_check.py` | 540 | Diagnostic health check |

## Entity Classification System

`entity_classification` provides granular practice-type labels beyond `ownership_status`. Assigned by DSO classifier Pass 3 (`classify_entity_types()` in `dso_classifier.py`) using provider count at address, last name matching, taxonomy codes, corporate signals, and Data Axle enrichment.

### All 11 values

| Value | Definition |
|-------|-----------|
| `solo_established` | Single-provider, 20+ years (or default for single providers with limited data) |
| `solo_new` | Single-provider, established within last 10 years |
| `solo_inactive` | Single-provider, missing phone AND website — likely retired or minimal activity |
| `solo_high_volume` | Single-provider, 5+ employees or $800k+ revenue — likely needs associate help |
| `family_practice` | 2+ providers, same address, share last name — internal succession likely |
| `small_group` | 2-3 providers, same address, different last names, not matching known DSO |
| `large_group` | 4+ providers, same address, not matching known DSO brand |
| `dso_regional` | Appears independent but shows corporate signals (parent company, shared EIN, franchise field, branch location type, generic brand + high provider count) |
| `dso_national` | Known national/regional DSO brand (Aspen, Heartland, etc.) matched with high confidence |
| `specialist` | Specialist practice (Ortho, Endo, Perio, OMS, Pedo) — taxonomy code or name keyword |
| `non_clinical` | Dental lab, supply company, billing, staffing |

Reasoning stored in `classification_reasoning`. Priority (first match wins): non_clinical > specialist > dso_national > corporate signals > family_practice > large_group > small_group > solo variants.

### Canonical groupings (Next.js)

- **Independent:** solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group
- **Corporate:** dso_regional, dso_national
- **Specialist:** specialist
- **Non-clinical:** non_clinical
- **Unknown:** entity_classification IS NULL AND ownership_status NOT IN (dso-affiliated, pe-backed)

### Saturation metrics (in `zip_scores`, computed by `merge_and_score.compute_saturation_metrics()`)

- **DLD** (`dld_gp_per_10k`) — GP dental offices per 10,000 residents. National avg ~6.1. Lower = less competition.
- **Buyable Practice Ratio** (`buyable_practice_ratio`) — % of GP offices in solo_established/solo_inactive/solo_high_volume.
- **Corporate Share** (`corporate_share_pct`) — % of GP offices in dso_regional/dso_national.
- **Market Type** (`market_type`) — combined classification. NULL when `metrics_confidence` is 'low'.
- **People per GP Door** (`people_per_gp_door`) — population / GP locations.

### Specialist separation

Practice classified `specialist` if ANY:
1. NPPES taxonomy starts with: 1223D (orth), 1223E (endo), 1223P (perio), 1223S (oral surg), 1223X (pedo). Excludes 1223G (general) and 122300 (general dentist).
2. Practice name contains: ORTHODONT, PERIODON, ENDODONT, ORAL SURG, MAXILLOFACIAL, PEDIATRIC DENT, PEDODONT, PROSTHODONT, IMPLANT CENT.

Location counts as GP if it has at least one non-specialist, non-clinical practice. Specialist-only locations counted in `total_specialist_locations`.

### Confidence

- `metrics_confidence` (zip_scores): 'high' (coverage >80% AND unknown <20%), 'medium' (>50% AND <40%), 'low' (anything else)
- `market_type_confidence`: 'confirmed' (high) / 'provisional' (medium) / 'insufficient_data' (low → market_type=NULL)
- `classification_confidence` (practices): 0-100 from DSO name/pattern matching

### Buyability score modifiers (Phase 5, additive)

After base `compute_buyability()`:
- **Family practice penalty (-20):** `entity_classification == 'family_practice'`
- **Multi-ZIP presence penalty (-15):** Same name or EIN appears in 3+ watched ZIPs

### Market types

Priority order (first match wins): `low_resident_commercial`, `high_saturation_corporate`, `corporate_dominant`, `family_concentrated`, `low_density_high_income`, `low_density_independent`, `growing_undersupplied`, `balanced_mixed`, `mixed`.

## Qualitative Intelligence Layer

AI-powered research layered on quantitative pipeline data. Claude API + web search.

### Architecture

```
research_engine.py     — Anthropic API (Haiku/Sonnet, web search, batch, prompt caching, EVIDENCE PROTOCOL)
intel_database.py      — CRUD (SQLAlchemy sessions, 90-day cache TTL)
qualitative_scout.py   — CLI: ZIP-level
practice_deep_dive.py  — CLI: practice-level (two-pass Haiku→Sonnet)
weekly_research.py     — Automated runner (validate_dossier, DRIFT_REMAP, budget caps)
```

### Tables

**`zip_qualitative_intel`** — One row per watched ZIP. Signals: housing, schools, retail, commercial, dental news, real estate, zoning, population, employers, competitors. Synthesis: `demand_outlook`, `supply_outlook`, `investment_thesis`, `confidence`. Metadata: `research_date`, `research_method`, `raw_json`, `cost_usd`, `model_used`. TTL 90d.

**`practice_intel`** — One row per NPI. Signals: website, services, technology, Google reviews, hiring, acquisition news, social media, HealthGrades, ZocDoc, doctor profile, insurance. Assessment: `red_flags`, `green_flags`, `overall_assessment`, `acquisition_readiness`, `confidence`. **Verification (F-anti-hallucination):** `verification_searches` (int), `verification_quality` (varchar 20, indexed: `verified|partial|insufficient`), `verification_urls` (text). Metadata: `research_date`, `escalated`, `escalation_findings`, `raw_json`, `cost_usd`, `model_used`. TTL 90d.

### Cost model (March 2026 Anthropic pricing)

| Mode | Model | Cost/Target | Use |
|------|-------|-------------|-----|
| ZIP Scout | Haiku 4.5 | ~$0.04-0.06 | Market research per ZIP |
| Practice Research | Haiku 4.5 | ~$0.075 (bulletproofed; real ~$0.008 in batch — see Anti-Hallucination §) | Due diligence per practice |
| Two-Pass Deep | Haiku→Sonnet | ~$0.28 | High-value escalation |
| Batch API | Haiku 4.5 | 50% token discount (web_search NOT discounted) | Weekly automated |

### Two-pass escalation

1. Pass 1 (Haiku) baseline scan
2. Escalate if `readiness` is high/medium AND `confidence` not high, OR 3+ green flags. Never escalates `unlikely`/`unknown`.
3. Pass 2 (Sonnet) deeper search, verified findings
4. Merge: dict union, list concat, string override

### CLI

```bash
# ZIP research
python3 scrapers/qualitative_scout.py --zip 60491
python3 scrapers/qualitative_scout.py --metro chicagoland
python3 scrapers/qualitative_scout.py --status
python3 scrapers/qualitative_scout.py --report 60491

# Practice research
python3 scrapers/practice_deep_dive.py --zip 60491 --top 10 --deep
python3 scrapers/practice_deep_dive.py --npi 1234567890
python3 scrapers/practice_deep_dive.py --status
python3 scrapers/practice_deep_dive.py --report 1234567890

# Weekly automation
python3 scrapers/weekly_research.py --budget 5
python3 scrapers/weekly_research.py --dry-run
```

### Environment + rules

- `ANTHROPIC_API_KEY` required. Local batch needs it; Vercel needs it separately for compound-narrative
- Cost tracking: `data/research_costs.json` (500-entry rolling log)
- Both intel tables sync via `full_replace`
- NEVER fabricate — prompts say "return null, never fabricate"
- ALL scripts use `pipeline_logger.log_scrape_start/complete()` and `logger_config.get_logger()`
- TTL 90d — don't re-research fresh data unless `--refresh`
- `research_engine.py` uses raw HTTP `requests`, NOT the `anthropic` SDK
- Circuit breaker: 3 consecutive API failures → `CircuitBreakerOpen` aborts (prevents 290 × 120s = 9.6hr hang)

## Anti-Hallucination Defense (April 25, 2026 — Do Not Regress)

Every dossier passes a 4-layer gate before landing in `practice_intel`. Validated by 200-practice batch (msgbatch_017YJJ2M3WbLv4Q7gEhubK2o): 87% pass rate (174 stored / 26 quarantined), 854 forced web searches (avg 4.27/practice), 0 hallucinations slipped through.

| Layer | Where | What |
|-------|-------|------|
| **1. Forced search** | `research_engine.py::_call_api()` accepts `force_search=True`, sets `body["tool_choice"] = {"type":"tool","name":"web_search"}` | Anthropic guarantees ≥1 `web_search` per practice. Practice path: `max_searches=5, force_search=True` |
| **2. Per-claim source URLs** | PRACTICE_USER schema in `research_engine.py` requires `_source_url` on every section (website, services, technology, google, hiring, acquisition, social, healthgrades, zocdoc, doctor, insurance) | Every non-null field traceable. Schema instructs `"no_results_found"` when search yields nothing |
| **3. Self-assessment block** | Terminal `verification` block in PRACTICE_USER: `{searches_executed, search_queries, evidence_quality (verified\|partial\|insufficient), primary_sources}` | Model self-rates evidence. `insufficient` triggers automatic rejection |
| **4. Post-validation gate** | `weekly_research.py::validate_dossier(npi, data) -> (ok, reason)` | 5 rejection rules: `missing_verification_block`, `insufficient_searches(N)`, `evidence_quality=insufficient`, `website.url_without_source`, `google.metrics_without_source`. Quarantined dossiers NOT stored |

**Schema invariants (do not regress):**
- `PracticeIntel` model in `database.py:426-428` has `verification_searches` (Integer), `verification_quality` (String(20), indexed), `verification_urls` (Text). Both Supabase + SQLite have them. **`Base.metadata.create_all()` does NOT alter existing tables** — adding columns requires explicit `ALTER TABLE` on both.
- `intel_database.py::store_practice_intel()` extracts `data["verification"]` and writes those 3 columns.
- `weekly_research.py::retrieve_batch()` calls `validate_dossier()` BEFORE `store_practice_intel()`.

**EVIDENCE PROTOCOL (PRACTICE_SYSTEM in `research_engine.py`):**
1. Execute web_search ≥2 times per practice (required: `<name> <city> <state>`, `<name> <city> reviews`)
2. Every non-null field backed by URL in `_source_url`
3. Never infer from priors
4. Brand/technology claims must come from the practice's own website
5. If search returns nothing, set fields to null AND `_source_url` to `"no_results_found"`
6. Terminal `verification` block is mandatory
7. `evidence_quality` MUST be exactly one of: `verified|partial|insufficient`. NEVER `high`, `low`, `medium` (F33 enforcement)

**Cost calibration:** Use the **Anthropic console** (https://console.anthropic.com/usage) as source of truth, NOT `poll.py`'s `totals.total_cost_usd`. The poll.py estimate is ~8.5–11× overcount (verified against console for two batch runs — full table in `CLAUDE_ARCHIVE.md` §"Cost calibration"). Two bugs: (1) `web_search_requests` from `usage.server_tool_use` overcounts ~4.5× billed; (2) Full Haiku rates applied without 50% Messages Batch API discount.

**Real cost per practice in batch mode: ~$0.005-0.010. Use $0.008/practice as the planning rate** ($16 for 2000-practice run, $80 for 10k). Confirm with console; flag if real cost >$0.015/practice. Don't quote `poll.py.totals.total_cost_usd` to user — reconcile with console first.

**End-to-end recipe:**

```bash
# 1. (one-time on fresh DB) — idempotent on both DBs
python3 scrapers/dossier_batch/migrate_verification_cols.py

# 2. submit (defaults: top-1-per-ZIP Chicagoland, $11)
python3 scrapers/dossier_batch/launch.py
# Or bigger pool:
#   python3 scrapers/dossier_batch/launch.py --target-count 2000 --budget 250 --exclude-zip-pattern '606%'

# 3. poll + validate + store + sync (background)
nohup python3 scrapers/dossier_batch/poll.py > /tmp/poll.log 2>&1 &
# Override: nohup python3 scrapers/dossier_batch/poll.py --batch-id msgbatch_XXX > ...

# 4. when /tmp/full_batch_summary.json appears, inspect it
python3 -c "import json; s=json.load(open('/tmp/full_batch_summary.json')); print(f\"stored={s['stored']} rejected={s['rejected']} cost=\${s['totals']['total_cost_usd']}\")"
```

**Known issues (all RESOLVED — full reasoning + commits in CLAUDE_ARCHIVE.md §"Anti-Hallucination Defense"):**
1. F33 `verification_quality` enum drift — DRIFT_REMAP coerces 7 known drift values; `evidence_quality_unknown` quarantine for off-spec. Commit `c4f7acc`.
2. F23 batch_id handoff — durable `data/last_batch_id.json` + back-compat `/tmp/full_batch_id.txt`. Commit `81be614`.
3. F24 SQLite migration idempotency — Postgres `ADD COLUMN IF NOT EXISTS` + SQLite PRAGMA introspection. Commit `81be614`.
4. F25 `launch.py` budget configurability — `--budget`, `--cost-per-practice`, `--target-count`, `--metro-pattern`, `--exclude-zip-pattern`. Commit `81be614`.
5. `practice_signals` FK violation (resolved 2026-04-25) — `compute_signals.py:475-505` filters `WHERE zip IN (SELECT zip_code FROM watched_zips)` + explicit `npi IS NOT NULL` guard (`eb75c6c`). Sync floor `MIN_ROWS_THRESHOLD["practice_signals"] = 1000`.

**Backfill planning (post-200-practice run):** ~8,559 unresearched Chicagoland independents (~$642 at $0.075/practice). Tier-prioritized (solo_high_volume + family_practice + solo_inactive with buyability ≥ 50): ~2,000 × $0.075 = ~$150. Boston Metro (21 ZIPs, ~zero coverage): 50-100 dossiers @ ~$8.

## Pipeline Audit (April 22-23, 2026 — Do Not Regress)

A 3-week pipeline outage was root-caused across every scraper, the Supabase sync, and parser pattern-hunt. **All 11 fixes are in `main`.** Full bug-fix table + audit gotchas + test suite + GitHub Actions keep-alive details + known limitations: `CLAUDE_ARCHIVE.md` §"Pipeline Audit (April 22-23, 2026)" and `SCRAPER_AUDIT_STATUS.md`.

**Key invariants now in `main`:**
- `refresh.sh::run_step()` reaps descendants via `pkill -TERM -P $bgpid` (not just subshell PID)
- Per-row `conn.begin_nested()` savepoint in `_sync_incremental_updated_at` (deals) and `_sync_incremental_id` (practice_changes) — handles `uix_deal_no_dup` partial unique index dups
- `_sync_watched_zips_only` uses `TRUNCATE TABLE practices CASCADE` (transactional in Postgres) instead of DELETE that hit `practice_changes_npi_fkey`
- `MIN_ROWS_THRESHOLD` floors for `platforms=20`, `pe_sponsors=10`, `zip_overviews=5`, `practice_signals=1000` — prevent silent wipe from broken source query
- SIGTERM/SIGINT handler with 8 checkpoints throughout sync loop; `_verify_table_count()` post-sync read-back; `AssertionError` on mismatch
- PESP DNS retry wrapper + 40+ COMMENTARY_PATTERNS pre-filter
- GDN `_PASS_THROUGH_SET = {"&","and","of"}`, expanded `_DEAL_VERB_SET`, `_PARTNERS_VERB_NEXT={"with","to","and"}` (F21)
- ADSO `HTTP_TIMEOUT=(10,30)`, `MAX_SECONDS_PER_DSO=300`, `log_scrape_complete()` in `finally`
- `database.normalize_punctuation()` translates curly quotes/apostrophes (U+2018-U+201D) → ASCII at GDN/PESP boundary (F19)
- F28 GitHub Actions weekly data-invariants CI: `.github/workflows/data-invariants.yml`, cron `0 13 * * 1`, runs `scripts/check_data_invariants.py`, Discord webhook on failure (non-blocking)
- Test suite `scrapers/test_sync_resilience.py` — 11 tests, all pass

**GitHub Actions keep-alive** (`.github/workflows/keep-supabase-alive.yml`) cron `0 12 */3 * *` pings Supabase REST. **REQUIRES USER ACTION:** add `SUPABASE_URL` + `SUPABASE_ANON_KEY` secrets in repo settings.

## Session Digest — 2026-04-26 Multi-Agent F-Fix Verification (33/33 PASS)

A multi-agent (A-D) deployment ran a full root-cause re-audit of every F-numbered fix. Each opened as a separate task at the root level. **Final outcome: 33/33 PASS, zero re-fixes.**

- **Window:** 2026-04-25 12:54 → 2026-04-26 12:02 (~23 hours, 50+ commits, 4 parallel sessions)
- **First commit:** `5d00689` (run_step timeout in nppes_refresh.sh)
- **Last commit:** `e3e2d1c` (P0-H GDN parser regex cap + comma in char class)

Full F-fix verification table (F01-F33), session window, cost calibration outcomes, multi-agent coexistence rules, and direct-verify commands: `CLAUDE_ARCHIVE.md` §"Session Digest — 2026-04-26 Multi-Agent F-Fix Verification" and `IMPLEMENTATION_PLAN_2026_04_26.md`.

**Direct-verify commands (re-runnable):**

```bash
# F32 hygienist cleanup live check
cd /Users/suleman/dental-pe-tracker && python3 -c "import sqlite3; c=sqlite3.connect('data/dental_pe_tracker.db'); print('global:', c.execute('SELECT COUNT(*) FROM practices').fetchone()[0]); print('watched:', c.execute('SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code').fetchone()[0]); print('non_dental_leak:', c.execute(\"SELECT COUNT(*) FROM practices WHERE taxonomy_code IS NOT NULL AND taxonomy_code NOT LIKE '1223%'\").fetchone()[0])"

# F27 vitest test
cd /Users/suleman/dental-pe-tracker/dental-pe-nextjs && npx vitest run src/__tests__/classification-primary.test.ts

# F19/F21 GDN parser re-test
cd /Users/suleman/dental-pe-tracker && python3 -m pytest scrapers/test_gdn_parser.py -k "partners or apostrophe" -v

# Full timeline
git log --pretty=format:"%h | %ad | %s" --date=iso 5d00689^..e3e2d1c
```

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` for the Streamlit app OR Next.js frontend. Use `/data-axle-workflow` for Data Axle export/import. Use `/debug-pipeline` for scraper failures or data issues.
