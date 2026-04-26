# Dental PE Intelligence Platform — Claude Code Guide

## What This Project Is

A data pipeline + dual-frontend dashboard that tracks private equity consolidation in US dentistry. It scrapes deal announcements, monitors 402,004 dental practices from federal data, classifies who owns what, and scores markets for acquisition risk. Primary metro: Chicagoland (268 expanded ZIPs across 7 sub-zones). Secondary: Boston Metro (21 ZIPs).

**Next.js app (primary):** dental-pe-nextjs.vercel.app
**Streamlit app (legacy):** suleman7-pe.streamlit.app
**Repo:** github.com/suleman7-DMD/dental-pe-tracker

## Architecture

```
dental-pe-nextjs/    Next.js 16 frontend (primary) — Supabase Postgres, Vercel
dashboard/app.py     Streamlit dashboard (legacy, 2,583 lines, single file, 6 pages)
scrapers/            Python scrapers + importers + classifiers (the data pipeline)
scrapers/database.py SQLAlchemy models + helpers (SQLite — local pipeline DB)
scrapers/sync_to_supabase.py  Syncs SQLite → Supabase Postgres for Next.js frontend
data/                SQLite DB (145 MB) + raw data files (CSV, XLSX)
logs/                Pipeline event log (JSONL) + per-run log files
pipeline_check.py    Diagnostic health check tool (540 lines)
```

### Data Flow

```
Federal/Web Sources → Python Scrapers → SQLite (local) → sync_to_supabase.py → Supabase Postgres
                                                       ↘ gzip → git push → Streamlit Cloud (legacy)
                                                       ↘ Supabase → Next.js Server Components → Client UI
```

Push to `main` auto-deploys both: Vercel (Next.js, ~30s) and Streamlit Cloud (~60s).

## Database

### SQLite (Pipeline — via SQLAlchemy)

Key tables: `deals`, `practices`, `practice_locations`, `practice_changes`, `watched_zips`, `zip_scores`, `dso_locations`, `ada_hpi_benchmarks`, `zip_qualitative_intel`, `practice_intel`, `practice_signals`, `zip_signals`

> **NPI rows vs clinic locations — read this before reading any count.** NPPES emits one row per provider (NPI-1) AND one row per organization (NPI-2) at the same physical address — so `practices` is keyed by NPI, NOT by clinic. In watched ZIPs, 14,053 NPI rows in `practices` collapse to ~5,732 deduped clinic locations in `practice_locations` (~2.7× NPI fan-out: 9,768 individual + 3,793 organization + 492 null). Every "402,004 practices" / "14,053 in watched ZIPs" callout in this doc is an **NPI-row count**, not a location count. The location-deduped denominator is `SUM(zip_scores.total_gp_locations)` for GP clinics and `practice_locations.location_id` for any address-keyed query. If a Supabase row count looks ~2.7× larger than expected, you are looking at NPI rows; that is not sync drift.

- **practices**: 402,004 NPI rows globally / 14,053 NPI rows in watched ZIPs. Fields: npi (PK), practice_name, doing_business_as, address, city, state, zip, phone, entity_type, taxonomy_code, ownership_status, affiliated_dso, affiliated_pe_sponsor, buyability_score, classification_confidence, classification_reasoning, data_source, latitude, longitude, parent_company, ein, franchise_name, iusa_number, website, year_established, employee_count, estimated_revenue, num_providers, location_type, import_batch_id, data_axle_import_date, entity_classification
- **practice_locations**: 5,732 location rows in Supabase (5,265 GP + 467 specialist/non-clinical, watched ZIPs only). Address-deduped clinic table created by the `dc18d24` ULTRA-FIX dedup pipeline. Fields: location_id (PK), normalized_address, primary_npi, org_npi, provider_npis (JSON), provider_count, is_likely_residential, entity_classification, buyability_score, affiliated_dso, etc. **All Sitrep KPIs and headline corporate %/independent% counts in the Next.js app source from this table — NOT from `practices`.** Joined back to `practices` via `practice_to_location_xref`.
- **deals**: 2,861 rows in SQLite, 2,861 in Supabase (drift reconciled in commit `ac2140a` 2026-04-25 — Pass 2 of `_reconcile_deals` keys NULL-target rows by composite hash, deleted 25 stranded ghosts). PE dental deals from PESP, GDN, PitchBook.
- **practice_changes**: Change log for name/address/ownership changes (acquisition detection). 8,848 rows.
- **zip_scores**: Per-ZIP consolidation stats (290 scored ZIPs), recalculated by merge_and_score.py. One row per ZIP (deduped). `total_gp_locations` is the location-deduped GP clinic count and is the canonical denominator for "how many clinics are in this ZIP."
- **watched_zips**: 290 ZIPs (268 Chicagoland + 21 Boston + 1 other). Auto-backfilled by ensure_chicagoland_watched().
- **dso_locations**: 92 scraped DSO office locations from ADSO websites.
- **ada_hpi_benchmarks**: 918 rows. State-level DSO affiliation rates by career stage (2022-2024).
- **practice_signals**: 14,053 NPI rows (one per watched-ZIP NPI) — materialized 8-flag overlay for Warroom Hunt mode (stealth_dso, phantom_inventory, family_dynasty, micro_cluster, retirement_combo, last_change_90d, high_peer_retirement, revenue_default). NPI-keyed because flags are about provider behavior, not clinic identity. **Live count Supabase: 14,053** (post `dc18d24`+`520c33e`).
- **zip_signals**: 290 ZIP rows — materialized ZIP-level overlay (ada_benchmark_gap_flag, deal_catchment_24mo, etc.). One row per watched ZIP. **Live count Supabase: 0 as of 2026-04-26** (sync gap; SQLite has 290 — needs `python3 scrapers/sync_to_supabase.py --tables zip_signals` to re-run).

### Supabase Postgres (Next.js Frontend)

Mirror of SQLite tables, synced by `scrapers/sync_to_supabase.py`. Same schema, same table names. The Next.js app reads directly from Supabase — it never touches SQLite.

### Supabase Sync Strategies (sync_to_supabase.py)

| Strategy | Tables | How It Works |
|----------|--------|--------------|
| `incremental_updated_at` | practices, **deals** | Only rows changed since last sync timestamp |
| `incremental_id` | practice_changes | New rows only (id > last_synced_id), filter_watched_zips applies |
| `full_replace` | zip_scores, watched_zips, dso_locations, ada_hpi_benchmarks, pe_sponsors, platforms, zip_overviews, zip_qualitative_intel, practice_intel | TRUNCATE CASCADE + INSERT |

Both incremental paths wrap each row insert in a `begin_nested()` savepoint so an `IntegrityError` on the secondary partial unique index `uix_deal_no_dup` (platform_company+target_name+deal_date) skips the duplicate with a WARNING instead of aborting the whole batch transaction.

### Current Data Stats

> Counts below labeled `(NPI rows)` are NPPES provider+organization rows (~2.7× the clinic count); counts labeled `(locations)` are address-deduped from `practice_locations`. Don't compare across labels without converting first.

- **402,004 (NPI rows) practices globally; 14,053 (NPI rows) in watched ZIPs / 5,732 (locations) in Supabase `practice_locations`.** `entity_classification` populated for all 14,053 watched-ZIP NPIs (96.5% NULL globally) — Pass 3 of `dso_classifier.py` only runs on watched-ZIP practices.
- **Watched-ZIP entity_classification breakdown (NPI rows, post-`520c33e` 2026-04-26 Tier-2 phone re-promotion):** solo_established 3,575 / small_group 2,727 / large_group 2,456 / specialist 2,353 / family_practice 1,701 / solo_high_volume 709 / dso_national 222 / solo_inactive 170 / dso_regional 244 / solo_new 17 / non_clinical 16. NULL is 0. **Pre-`520c33e`:** dso_national=213, dso_regional=109. **Pre-`dc18d24` baseline** (April-2026 audit `NPI_VS_PRACTICE_AUDIT.md` Appendix C): dso_regional was 1,181 — that 1,072 reclassification was the location-dedup classifier rewrite, NOT this Tier-2 re-promotion.
- **Total corporate (NPI rows): 882 (6.28% of 14,053)** post-2026-04-26 NPI backfill (was 466 pre-backfill, 322 pre-Tier-2, 1,392 pre-`dc18d24`). At the location level (`practice_locations`), corporate share is **4.52% Chicagoland (207/4,575 GP locations) / 5.73% Boston Metro (18/314)** — combined **4.60% (225/4,889)**. **NPI % > location % is structural, not a bug**: a single corporate location can house 2-5 NPIs, so per-NPI counts inflate vs per-location counts. Use `practice_locations` / `zip_scores.corporate_location_count` for headline KPIs; only quote the NPI count when the unit being discussed is "individual dentists working at corporate" (Job Market scoring).
- Legacy `ownership_status` field is now ~zero in SQLite — `entity_classification` is the canonical ownership signal everywhere in the Next.js frontend (see `classifyPractice()` helper).
- 2,861 deals in SQLite / 2,895 in Supabase (drift reconciled 2026-04-25 in `ac2140a`; +34 ghost rows in Supabase remain, see audit §15 #11). Mix: 2,532 GDN + 353 PESP + 10 PitchBook. Coverage: Oct 2020 – Mar 2026 (live `MAX(deal_date)=2026-03-02`; April 2026 GDN roundup not yet published as of 2026-04-26).
- 2,992 (NPI rows) Data Axle enriched practices (with lat/lon, revenue, employees, year established).
- 290 scored ZIPs.
- **practice_signals: 14,053 (NPI rows) in Supabase** (one row per watched-ZIP NPI) — Warroom Hunt mode signal flag overlay is live.
- **zip_signals: 0 in Supabase / 290 in SQLite** — sync gap as of 2026-04-26 (Warroom ZIP-level overlay silent until re-sync).

## Next.js Frontend (Primary)

**Stack:** Next.js 16, React 19, TypeScript 5, Supabase Postgres, TanStack React Query + Table, Recharts 3, Mapbox GL, Tailwind CSS 4, shadcn UI, Lucide React

**Fonts:** DM Sans (headings, 24px/700 page titles), Inter (body), JetBrains Mono (data values, 28px/700 KPIs). Data labels: 11px/500/Inter/uppercase/tracking-wider.

**Deployment:** Vercel auto-deploys on push to main

**Env vars:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MAPBOX_TOKEN`. **`ANTHROPIC_API_KEY`** required for `/api/launchpad/compound-narrative` (Sonnet thesis route) — must be set in Vercel project env vars (Production + Preview + Development), then redeploy. Without it, the route returns `503: Compound narrative disabled`.

### Pages (10 total)

| Route | Page | What It Shows |
|-------|------|---------------|
| `/` | Home | 6 KPI cards (Lucide icons), two-column layout (recent deals table + activity feed from practice_changes), data freshness bar, 2x3 quick nav grid |
| `/launchpad` | Launchpad | First-job finder for new dental grads. Track-weighted 0-100 scoring (Succession / Apprentice, High-Volume Ethical, DSO Associate). 20-signal catalog. 5 tiers (Best Fit / Strong / Maybe / Low / Avoid). 4 living-location scopes. 5-tab practice dossier. Curated DSO tier list with comp bands + citations. Compound thesis route uses Sonnet 4.6 + reads `practice_intel`. |
| `/warroom` | **Warroom** | Chicagoland command surface. 2 modes (Hunt / Investigate), 4 lenses (consolidation, density, buyability, retirement), 11 scopes (chicagoland, 7 subzones, 3 saved presets). Always-visible Sitrep KPI strip. Intent bar (⌘K), Living Map, ranked target list, ZIP + practice dossier drawers, pinboard tray, signal flag overlays (8 practice + 1 ZIP), keyboard shortcuts (`?`, `1`=Hunt, `2`=Investigate, `R`/`P`/`V`/`[`/`]`/`Esc`), URL-synced state. |
| `/deal-flow` | Deal Flow | **4 tabs: Overview \| Sponsors \| Geography \| Deals.** Persistent KPI strip above tabs. |
| `/market-intel` | Market Intel | **3 tabs: Consolidation \| ZIP Analysis \| Ownership.** Persistent tiered consolidation KPIs above tabs. Cross-link banner to Warroom. |
| `/buyability` | Buyability | Verdict extraction from notes field, 4 category KPIs, ZIP filter, sortable table with CSV export |
| `/job-market` | Job Market | **4 tabs: Overview \| Map \| Directory \| Analytics.** Persistent KPI strip + Living Location Selector (4 presets) above tabs. |
| `/research` | Research | PE sponsor profiles, DSO platform profiles, state deep dives, SQL explorer (SELECT-only, forbidden keywords) |
| `/intelligence` | Intelligence | AI-powered qualitative research — 6 KPI cards, ZIP market intelligence table with expandable 10-signal panels, practice dossier table with readiness/confidence badges. Cross-link banner to Warroom Investigate mode. |
| `/system` | System | Data freshness indicators, source coverage, completeness bars, pipeline log viewer, manual entry forms |

### Data Flow Pattern

1. **Server Components** (`page.tsx`) fetch from Supabase server-side
2. Pass data to **Client Component shells** (`'use client'`) via props
3. Client shells handle filters, UI state, refetching via **React Query** (30min stale, 30min gc — data changes weekly; per-hook overrides exist for warroom/launchpad)
4. URL params sync for shareable filter state (`useUrlFilters` hook)
5. Supabase queries in `src/lib/supabase/queries/` organized by table

### Entity Classification in Next.js (CRITICAL)

The Next.js app uses `entity_classification` (11 types) as the **PRIMARY** field for all ownership analysis. `ownership_status` is ONLY used as a fallback when entity_classification is NULL.

Key helpers in `src/lib/constants/entity-classifications.ts`:
- `isIndependentClassification(ec)` — true for solo_*, family_practice, small_group, large_group
- `isCorporateClassification(ec)` — true for dso_regional, dso_national
- `classifyPractice(entityClassification, ownershipStatus)` — returns "independent" | "corporate" | "specialist" | "non_clinical" | "unknown"
- `getEntityClassificationLabel(value)` — human-readable label

### Scoring (src/lib/utils/scoring.ts)

- `computeJobOpportunityScore()` — 0-100 score using entity_classification with ownership_status fallback. Factors: ownership (30pts), buyability (25/15pts), employees (20/10pts), year_established (15/8pts)
- `isRetirementRisk()` — independent (by entity_classification or fallback) + 30+ years
- `getPracticeAge()` — years since year_established

### Design System (Warm Light Theme — updated 2026-03-15)

- **Background:** #FAFAF7 (app), #FFFFFF (cards), #F7F7F4 (elevated/hover), #F5F5F0 (inset/input)
- **Sidebar:** #2C2C2C (stays dark as intentional contrast), goldenrod #B8860B accent for active items
- **Text:** #1A1A1A (primary), #6B6B60 (secondary), #9C9C90 (muted), #B5B5A8 (dimmed)
- **Borders:** #E8E5DE (default), #D4D0C8 (hover)
- **Accent:** #B8860B (goldenrod — was blue #3B82F6)
- **Semantic colors:** Green #2D8B4E, Red #C23B3B, Amber #D4920B, Blue #2563EB, Purple #7C3AED, Teal #0D9488
- **Status colors:** Corporate #C23B3B, Independent #2563EB, Specialist #0D9488, Group #6366F1
- **KPI cards:** 28px JetBrains Mono bold values, goldenrod accent border
- **Tables:** alternating rows #FFFFFF/#FAFAF7, semibold headers with border-b-2

### Sidebar Navigation

4 grouped sections (dark #2C2C2C bg, goldenrod #B8860B active accent):
- **OVERVIEW:** Dashboard (`/`), Launchpad (`/launchpad`), Warroom (`/warroom`)
- **MARKETS:** Job Market, Market Intel, Buyability
- **ANALYSIS:** Deal Flow, Research, Intelligence
- **ADMIN:** System

### Module Relocations (2026-03-15 UI Overhaul)

- `saturation-table.tsx` + `ada-benchmarks.tsx`: copied from `market-intel` to `job-market` (rendered in Overview tab)
- `dso-penetration-table.tsx`: new component in `market-intel` (extracted from ownership-landscape, rendered in Consolidation tab)
- `recent-changes`: now rendered on Home page activity feed (fetched via `getRecentChanges`)

### Next.js File Map (directory-grouped)

Pattern: each page route is a Server Component (`page.tsx`) that fetches Supabase data and passes it to a client `*-shell.tsx` orchestrator. Sub-components live in `_components/` siblings; cross-page primitives live in `src/components/`.

- **`src/app/`** — `layout.tsx` (root, fonts/providers/sidebar), `page.tsx` (Home), `globals.css` (Tailwind 4 + warm light theme)
- **`src/app/launchpad/_components/`** — `launchpad-shell.tsx` (orchestrator), `scope-selector.tsx`, `track-switcher.tsx`, `launchpad-kpi-strip.tsx`, `track-list.tsx`, `track-list-card.tsx`, `practice-dossier.tsx` (5-tab drawer), `compound-thesis.tsx` (Sonnet thesis with Regenerate button, plain prose)
- **`src/app/warroom/_components/`** — `warroom-shell.tsx`, `scope-selector.tsx` (11 options), `intent-bar.tsx` (⌘K), `sitrep-kpi-strip.tsx`, `living-map.tsx` (Mapbox), `briefing-rail.tsx`, `target-list.tsx`, `dossier-drawer.tsx`, `zip-dossier-drawer.tsx`, `investigate-mode-panel.tsx`, `pinboard-tray.tsx`, `keyboard-shortcuts-overlay.tsx`
- **`src/app/deal-flow/_components/`** — `deal-flow-shell.tsx`, `deal-kpis.tsx`, `deal-volume-timeline.tsx`, `sponsor-platform-charts.tsx`, `state-choropleth.tsx`, `specialty-charts.tsx`, `deals-table.tsx`
- **`src/app/market-intel/_components/`** — `market-intel-shell.tsx`, `consolidation-map.tsx`, `zip-score-table.tsx`, `city-practice-tree.tsx` (paginates within ZIP chunks), `saturation-table.tsx`, `ada-benchmarks.tsx`, `recent-changes.tsx`, `dso-penetration-table.tsx`
- **`src/app/buyability/_components/`** — `buyability-shell.tsx`
- **`src/app/job-market/_components/`** — `job-market-shell.tsx`, `living-location-selector.tsx` (4 presets), `practice-density-map.tsx` (Mapbox hex+dot), `practice-directory.tsx`, `practice-detail-drawer.tsx`, `market-overview-charts.tsx`, `opportunity-signals.tsx`, `ownership-landscape.tsx`, `market-analytics.tsx`, `saturation-table.tsx` (relocated), `ada-benchmarks.tsx` (relocated)
- **`src/app/intelligence/_components/`** — `intelligence-shell.tsx` (KPIs + ZIP intel + practice dossier expandable panels)
- **`src/app/research/_components/`** — `research-shell.tsx`, `sponsor-profile.tsx`, `platform-profile.tsx`, `state-deep-dive.tsx`, `sql-explorer.tsx`
- **`src/app/system/_components/`** — `system-shell.tsx`, `freshness-indicators.tsx`, `data-coverage.tsx`, `completeness-bars.tsx`, `pipeline-log-viewer.tsx`, `manual-entry-forms.tsx`
- **`src/app/api/`** — `deals/`, `practices/`, `sql-explorer/` (SELECT-only), `watched-zips/`, `launchpad/compound-narrative/route.ts` (Sonnet 4.6, reads `practice_intel`, ephemeral cache, 200-300 word output with `[source: domain]` citations, hedge phrases when evidence is `partial`/`insufficient`, fallback "Structural signals only…" when intel missing)
- **`src/lib/launchpad/`** — `scope.ts` (LAUNCHPAD_SCOPES + resolveLaunchpadZipCodes), `signals.ts` (20 signal IDs + LaunchpadBundle contract), `ranking.ts` (TRACK_MULTIPLIERS, evaluateSignals, scoreForTrack, rankTargets), `dso-tiers.ts` (16 curated DSOs)
- **`src/lib/warroom/`** — `mode.ts` (WARROOM_MODES + WARROOM_LENSES), `scope.ts` (11 scopes + `normalizeWarroomDataScope()`), `geo.ts`, `signals.ts` (WarroomPracticeRecord + SitrepBundle types), `data.ts` (`getSitrepBundle()`), `intent.ts` (NL parsing), `ranking.ts` (`rankTargets()`), `briefing.ts`
- **`src/lib/supabase/queries/`** — `deals.ts`, `practices.ts`, `zip-scores.ts`, `watched-zips.ts`, `practice-changes.ts`, `ada-benchmarks.ts`, `benchmarks.ts`, `changes.ts`, `system.ts` (ADSO + ADA HPI freshness via `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at`), `intel.ts` (getZipIntel, getPracticeIntel, getPracticeIntelByNpi, getIntelStats), `launchpad.ts` (getLaunchpadBundle)
- **`src/lib/supabase/`** — `client.ts` (browser singleton), `server.ts` (per-request), `types.ts` (DB types)
- **`src/lib/constants/`** — `entity-classifications.ts` (11 types + `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`), `design-tokens.ts`, `colors.ts`, `living-locations.ts` (4 Job Market presets), `metro-centers.ts`, `zip-centroids.ts`, `sql-presets.ts` (use entity_classification, NOT ownership_status), `deal-type-colors.ts`, `us-states.ts`
- **`src/lib/utils/`** — `formatting.ts` (formatNumber/Currency/Percent/Date/StatusLabel, computeConsolidationDisplay), `scoring.ts` (computeJobOpportunityScore, isRetirementRisk, getPracticeAge — entity_classification primary), `csv-export.ts`, `colors.ts`
- **`src/lib/hooks/`** — `use-url-filters.ts`, `use-sidebar.ts`, `use-section-observer.ts`, `use-launchpad-state.ts`, `use-launchpad-data.ts`, `use-warroom-state.ts`, `use-warroom-data.ts`, `use-warroom-intel.ts` (added 2026-04-24)
- **`src/lib/types/`** — `index.ts` (Deal, Practice, ZipScore, WatchedZip, HomeSummary with `enrichedCount`, PracticeStats), `intel.ts` (ZipQualitativeIntel, PracticeIntel — extended with `verification_searches`, `verification_quality`, `verification_urls`), `types-job-market.ts`
- **`src/components/data-display/`** — `data-table.tsx` (TanStack: sort/filter/paginate/CSV — render functions MUST return primitives), `kpi-card.tsx` (icon/label/value/delta/accent/`subtitle` for tiered display), `data-freshness-bar.tsx`, `section-header.tsx`, `status-badge.tsx`, `status-dot.tsx`, `confidence-stars.tsx`
- **`src/components/charts/`** — `bar-chart`, `stacked-bar-chart`, `grouped-bar-chart`, `area-chart`, `donut-chart`, `histogram-chart`, `scatter-chart`, `chart-container` (Recharts wrappers)
- **`src/components/filters/`** — `filter-bar`, `search-input` (debounced), `multi-select`, `date-range-picker`
- **`src/components/maps/`** — `map-container.tsx` (Mapbox GL wrapper)
- **`src/components/layout/`** — `sidebar.tsx` (220px/60px collapsible, dark, 4 grouped sections), `sticky-section-nav.tsx`, `warroom-cross-link.tsx` (goldenrod banner on Market Intel + Intelligence)
- **`src/components/ui/`** — shadcn primitives (button, card, dialog, etc.)
- **`src/providers/`** — `query-provider.tsx` (React Query 30min stale/gc, 1 retry), `sidebar-provider.tsx`

## Streamlit Dashboard (Legacy)

Single-file dashboard at `dashboard/app.py` (2,583 lines, 6 pages). Still live at suleman7-pe.streamlit.app but no longer the primary frontend. Pages: Deal Flow, Market Intel, Buyability, Job Market (pydeck dual-density hex map, 6 KPI cards from practice data, ownership landscape, market analytics), Research, System. Streamlit still primarily uses `ownership_status` with entity_classification as supplemental detail.

## Automated Pipeline

Cron runs every Sunday 8am (`scrapers/refresh.sh`):
1. Backup DB → 2. PESP scraper → 3. GDN scraper → 4. PitchBook importer → 5. ADSO scraper → 6. ADA HPI downloader → 7. DSO classifier → 8. Merge & score → 9. Weekly qualitative research ($5 budget cap) → 10. Sync to Supabase → Compress DB + git push

Monthly NPPES refresh (first Sunday 6am): downloads federal provider data updates.

Every step logs structured events to `logs/pipeline_events.jsonl` via `scrapers/pipeline_logger.py`.

After pipeline runs, `scrapers/sync_to_supabase.py` pushes updated data to Supabase Postgres for the Next.js frontend.

## Critical Rules

### Don't break the pipeline
- ALL scrapers import from `scrapers.pipeline_logger` — keep `log_scrape_start()` and `log_scrape_complete()` calls in every scraper's `run()` function
- ALL scrapers import from `scrapers.logger_config` — use `get_logger("scraper_name")`
- `database.py` auto-decompresses `.db.gz` on Streamlit Cloud — never remove that logic
- `refresh.sh` uses `run_step()` wrapper — errors in one step don't kill the pipeline

### Market Intel transparency
- Consolidation percentages MUST use total practices as denominator (conservative)
- Never use `classified_count` as denominator for headline KPIs — that inflates numbers
- Always show unknown count when >30% of practices are unclassified
- Labels must say "Known Consolidated" not just "Consolidated"

### Data integrity
- `insert_or_update_practice()` and `insert_deal()` handle dedup — use them, don't raw INSERT
- NPPES data uses NPI as unique key (10-digit number)
- PitchBook dedup uses fuzzy matching on company name + date
- Data Axle dedup uses address normalization + fuzzy name matching
- Data Axle importer has Pass 6: Corporate Linkage Detection (parent company fuzzy match, EIN clustering, IUSA parent linkage, franchise field)
- Never delete from `practices` table — only update ownership_status

### Streamlit Cloud constraints
- DB must be gzipped for git push (`data/dental_pe_tracker.db.gz`)
- App decompresses on first load via `_ensure_db_decompressed()`
- Keep `dashboard/app.py` imports inside functions where possible (cold start speed)

### Next.js frontend rules
- **Entity classification is primary** — ALWAYS use `entity_classification`, with `ownership_status` as fallback only when entity_classification is NULL
- `classifyPractice()` is the canonical helper for ownership categorization across the entire frontend
- KPI cards must use **Lucide JSX components** for icons (not strings)
- Supabase returns max 1000 rows per query — MUST paginate with `.range()` for large result sets
- Consolidation % denominator is ALWAYS total practices
- DataTable render functions must return primitives (`string | number | null`), never objects
- Run `npm run build` in `dental-pe-nextjs/` after every change to verify TypeScript compilation
- Server Components (`page.tsx`) do the Supabase fetch; client shells (`*-shell.tsx`) handle interactivity
- URL params sync via `useUrlFilters` — changes to filter logic must preserve URL shareability

### Do not regress (consolidated bug-fix log, March–April 2026)
- All KPI icons are Lucide JSX components (not strings); KpiCard supports `subtitle` prop for tiered display
- Home page consolidatedPct includes % suffix
- `getRetirementRiskCount` filters by watched ZIPs + `year_established < 1995` + all 7 independent classifications
- `getAcquisitionTargetCount` filters by watched ZIPs + `buyability_score >= 50`
- `getPracticeStats` returns full `PracticeStats` with tiered corporate (`corporateHighConf`, `corporate`, `enriched`)
- Market Intel + Job Market KPIs use entity_classification (server-side classificationCounts prop) with tiered display: "High-Confidence Corporate" primary / "All detected signals" secondary / "Industry estimate: 25-35%" subtitle
- ZIP Score table uses `fmtPct` helper; confidence/opportunity_score renderers handle both cell-value and row-object patterns
- City practice tree paginates WITHIN each ZIP chunk to avoid Supabase 1000-row limit
- Consolidation map computes pct from `corporate_share_pct * total_gp_locations`
- DSO penetration table reads city names from watchedZips lookup, corporate_share_pct from zip_scores
- Job Market enrichment count uses `data_axle_import_date IS NOT NULL`
- `scoring.ts`, `getPracticeCountsByStatus`, SQL presets, System "Ownership Classified" all use entity_classification primary with ownership_status fallback
- `entity-classifications.ts` exports `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER`
- `PracticeStats` interface in both `types.ts` and `types/index.ts`; `HomeSummary` includes `enrichedCount`
- UI overhaul (2026-03-15): warm light theme, tab navigation on Deal Flow/Market Intel/Job Market, module relocations (saturation + ADA → Job Market, DSO penetration extracted in Market Intel), sidebar regrouped into 4 sections, Home activity feed — all 8 pages render with warm light theme, tabs URL-synced, build passes

## Pipeline File Quick Reference

| File | Lines | What It Does |
|------|-------|-------------|
| `dashboard/app.py` | 2,583 | Full Streamlit dashboard — 6 pages (legacy) |
| `scrapers/database.py` | 542 | SQLAlchemy models, init_db(), helpers |
| `scrapers/sync_to_supabase.py` | — | Syncs SQLite → Supabase Postgres (3 strategies) |
| `scrapers/nppes_downloader.py` | 681 | Downloads + imports federal dental provider data |
| `scrapers/data_axle_importer.py` | 2,650 | Imports Data Axle CSVs with 7-phase pipeline + Pass 6 corporate linkage |
| `scrapers/merge_and_score.py` | 719 | Dedup deals, score ZIPs, ensure_chicagoland_watched() |
| `scrapers/dso_classifier.py` | 547 | Name pattern matching + location matching to classify ownership |
| `scrapers/pesp_scraper.py` | 552 | Scrapes PE deal announcements |
| `scrapers/gdn_scraper.py` | 720 | Scrapes DSO deal roundups (old-format paragraph splitting for 2020-2022 posts) |
| `scrapers/adso_location_scraper.py` | 728 | Scrapes DSO office locations from websites |
| `scrapers/ada_hpi_downloader.py` | 237 | Auto-downloads ADA benchmark XLSX files |
| `scrapers/ada_hpi_importer.py` | 351 | Parses ADA HPI XLSX by state/career stage |
| `scrapers/pitchbook_importer.py` | 616 | CSV/XLSX import from PitchBook deal/company search |
| `scrapers/data_axle_exporter.py` | 805 | Interactive ZIP-batch export tool (7 Chicagoland zones + Boston) |
| `scrapers/research_engine.py` | 400 | Core Anthropic API client (Haiku/Sonnet, web search, batch API, circuit breaker) |
| `scrapers/intel_database.py` | 266 | CRUD for intel tables (SQLAlchemy sessions, 90-day cache TTL) |
| `scrapers/qualitative_scout.py` | 380 | CLI: ZIP-level market research via Claude API |
| `scrapers/practice_deep_dive.py` | 577 | CLI: Practice-level due diligence (two-pass Haiku→Sonnet) |
| `scrapers/weekly_research.py` | 309 | Automated weekly research runner (batch API, budget caps) |
| `scrapers/pipeline_logger.py` | 295 | Structured JSON-Lines event logger |
| `scrapers/compute_signals.py` | 1,424 | Materializes per-practice + per-ZIP signal flags into `practice_signals` and `zip_signals` for Warroom + Launchpad. NPI-null guard added in `eb75c6c`; filters watched ZIPs to prevent FK violations on global-pool rows. |
| `scrapers/cleanup_pesp_junk.py` | 80 | One-shot cleanup CLI: deletes PESP deal rows whose `target_name` matches a known commentary fragment (e.g. "based on", "according to") that escaped the COMMENTARY_PATTERNS pre-filter. Idempotent; safe to re-run. |
| `scrapers/fast_sync_watched.py` | 200 | Fast partial sync: re-uploads ONLY the practices in `watched_zips` (~14k rows) without touching the global 402k pool. Used when a watched-ZIP-scoped change (entity_classification refresh, signal recompute) needs to land in Supabase without paying the full incremental scan cost. |
| `scrapers/dossier_batch/launch.py` | — | Picks top-1 unresearched independent per Chicagoland watched ZIP, builds bulletproofed batch via `engine.build_batch_requests`, submits to Anthropic. Writes `batch_id` to `/tmp/full_batch_id.txt`. |
| `scrapers/dossier_batch/launch_2000_excl_chi.py` | — | Bigger variant: top-2000 unresearched independents EXCLUDING Chicago-proper (`zip NOT LIKE '606%'`). Cost cap raised to $250. Used for the 2026-04-25 backfill batch `msgbatch_01A3FxKxKxemAyqDr2AcGYUq`. |
| `scrapers/dossier_batch/poll.py` | — | Reads `batch_id`, polls Anthropic every 30s up to 90 min, runs `validate_dossier()` per result, stores passing dossiers via `store_practice_intel()`, runs `sync_to_supabase.py`, writes `/tmp/full_batch_summary.json`. |
| `scrapers/dossier_batch/poll_zip_batches.py` | — | Auto-retrieval poller for the 290-ZIP re-research batches (audit §15 #7). Reads `/tmp/zip_batch_ids.json` (one or more batch IDs), polls each, validates via `validate_zip_dossier()`, stores via `store_zip_intel()`. |
| `scrapers/dossier_batch/upsert_practice_intel.py` | — | Standalone UPSERT path: copies `practice_intel` rows from local SQLite to Supabase via `INSERT ... ON CONFLICT DO UPDATE`, skipping the TRUNCATE that `sync_to_supabase.py`'s `full_replace` strategy uses. Useful when you want to land verified dossiers in Supabase without waiting for the next full sync (or when full sync is wiping data). |
| `scrapers/dossier_batch/migrate_verification_cols.py` | — | One-shot Supabase migration: adds `verification_searches`, `verification_quality`, `verification_urls` columns to `practice_intel` (idempotent, uses `ADD COLUMN IF NOT EXISTS`). Companion SQLite ALTER must be run separately (no IF NOT EXISTS support). |
| `pipeline_check.py` | 540 | Diagnostic health check tool |

## Entity Classification System

The `entity_classification` field on practices provides granular practice-type labels beyond `ownership_status`. Classifications are assigned by the DSO classifier's Pass 3 (`classify_entity_types()` in `dso_classifier.py`), using provider count at address, last name matching, taxonomy codes, corporate signals, and Data Axle enrichment data.

### All 11 Entity Classification Values
| Value | Definition |
|-------|-----------|
| `solo_established` | Single-provider practice, operating 20+ years or default for single providers with limited data |
| `solo_new` | Single-provider practice, established within last 10 years |
| `solo_inactive` | Single-provider practice, missing phone and website — likely retired or minimal activity |
| `solo_high_volume` | Single-provider with 5+ employees or $800k+ revenue — likely needs associate help |
| `family_practice` | 2+ providers at same address share a last name — internal succession likely |
| `small_group` | 2-3 providers at same address, different last names, not matching known DSO |
| `large_group` | 4+ providers at same address, not matching known DSO brand |
| `dso_regional` | Appears independent but shows corporate signals (parent company, shared EIN, franchise field, branch location type, generic brand + high provider count) |
| `dso_national` | Known national/regional DSO brand (Aspen, Heartland, etc.) matched with high confidence |
| `specialist` | Specialist practice (Ortho, Endo, Perio, OMS, Pedo) — identified by taxonomy code or practice name keywords |
| `non_clinical` | Dental lab, supply company, billing entity, staffing service |

Each classification stores its reasoning in `classification_reasoning` for auditability. First matching rule wins (priority: non_clinical > specialist > dso_national > corporate signals > family_practice > large_group > small_group > solo variants).

### Canonical Groupings (Next.js)
- **Independent:** solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group
- **Corporate:** dso_regional, dso_national
- **Specialist:** specialist
- **Non-clinical:** non_clinical
- **Unknown:** NULL entity_classification AND ownership_status not in (dso-affiliated, pe-backed)

### Saturation Metrics (in zip_scores)
Computed by `merge_and_score.py`'s `compute_saturation_metrics()`:
- **DLD (Dentist Location Density):** `dld_gp_per_10k` = GP dental offices per 10,000 residents. National avg ~6.1. Lower = less competition.
- **Buyable Practice Ratio:** `buyable_practice_ratio` = % of GP offices classified as solo_established, solo_inactive, or solo_high_volume. Higher = more acquisition targets.
- **Corporate Share:** `corporate_share_pct` = % of GP offices classified as dso_regional or dso_national. Higher = more consolidated market.
- **Market Type:** `market_type` = computed classification based on combined metrics. Set to NULL when `metrics_confidence` is 'low' (data insufficient for reliable labeling).
- **People per GP Door:** `people_per_gp_door` = population / GP locations. Higher = fewer options per resident.

### Specialist Separation Methodology
A practice is classified as `specialist` if ANY:
1. **Taxonomy code match** — NPPES taxonomy starts with specialist prefix (1223D, 1223E, 1223P, 1223S, 1223X). Excludes 1223G (General) and 122300 (General Dentist).
2. **Practice name keyword** — Name contains: ORTHODONT, PERIODON, ENDODONT, ORAL SURG, MAXILLOFACIAL, PEDIATRIC DENT, PEDODONT, PROSTHODONT, IMPLANT CENT.
3. A location (unique address) counts as GP if it has at least one non-specialist, non-clinical practice. Specialist-only locations are counted separately in `total_specialist_locations`.

### Confidence System
- **`metrics_confidence`** on zip_scores: 'high' (classification coverage >80% AND unknown ownership <20%), 'medium' (coverage >50% AND unknown <40%), 'low' (anything else).
- **`market_type_confidence`**: 'confirmed' (metrics_confidence is high), 'provisional' (medium), 'insufficient_data' (low — market_type set to NULL).
- **`classification_confidence`** on practices: 0-100 score from DSO name/pattern matching.

### Market Type Values
Priority order (first match wins): `low_resident_commercial`, `high_saturation_corporate`, `corporate_dominant`, `family_concentrated`, `low_density_high_income`, `low_density_independent`, `growing_undersupplied`, `balanced_mixed`, `mixed` (default).

### Buyability Score Modifiers (Phase 5)
In addition to the base scoring in `compute_buyability()` (data_axle_importer.py), two ADDITIVE penalties are applied after entity classification:
- **Family practice penalty (-20):** `entity_classification == 'family_practice'` — shared last name at address suggests internal succession.
- **Multi-ZIP presence penalty (-15):** Same practice name or EIN appears in 3+ watched ZIPs — likely a chain entity.

## Qualitative Intelligence Layer

AI-powered research tools that layer qualitative signals on top of quantitative pipeline data. Uses Claude API with web search to gather market intelligence and practice due diligence.

### Architecture
```
scrapers/research_engine.py       — Core Anthropic API client (Haiku/Sonnet, web search, batch API, prompt caching)
scrapers/intel_database.py        — CRUD for intel tables (uses SQLAlchemy sessions from database.py)
scrapers/qualitative_scout.py     — CLI: ZIP-level market research
scrapers/practice_deep_dive.py    — CLI: Practice-level due diligence (two-pass Haiku→Sonnet escalation)
scrapers/weekly_research.py       — Automated pipeline runner with budget caps
```

### Intel Database Tables

**`zip_qualitative_intel`** — ZIP-level market research (one row per watched ZIP)
- FK: `zip_code` references `watched_zips(zip_code)`
- Signals: housing, schools, retail, commercial, dental news, real estate, zoning, population, employers, competitors
- Synthesis: `demand_outlook`, `supply_outlook`, `investment_thesis`, `confidence`
- Metadata: `research_date`, `research_method`, `raw_json`, `cost_usd`, `model_used`. Cache TTL: 90 days.

**`practice_intel`** — Practice-level due diligence (one row per NPI)
- FK: `npi` references `practices(npi)`
- Signals: website analysis, services, technology, Google reviews, hiring, acquisition news, social media, HealthGrades, ZocDoc, doctor profile, insurance
- Assessment: `red_flags`, `green_flags`, `overall_assessment`, `acquisition_readiness`, `confidence`
- Verification: `verification_searches` (int), `verification_quality` (varchar 20, indexed), `verification_urls` (text)
- Metadata: `research_date`, `escalated`, `escalation_findings`, `raw_json`, `cost_usd`, `model_used`. Cache TTL: 90 days.

### Cost Model (March 2026 Anthropic Pricing)

| Mode | Model | Cost/Target | Use Case |
|------|-------|-------------|----------|
| ZIP Scout | Haiku 4.5 | ~$0.04-0.06 | Market research per ZIP |
| Practice Research | Haiku 4.5 | ~$0.075 (bulletproofed) | Due diligence per practice |
| Two-Pass Deep | Haiku then Sonnet | ~$0.28 | Escalation for high-value targets |
| Batch API | Haiku 4.5 | 50% token discount (web_search NOT discounted) | Weekly automated runs |

### Two-Pass Escalation Logic
1. **Pass 1 (Haiku):** All practices get a baseline scan
2. **Escalation decision:** Triggers Sonnet deep dive if `readiness` is high/medium AND `confidence` is not high, OR 3+ green flags. Guard: never escalates `unlikely` or `unknown` readiness.
3. **Pass 2 (Sonnet):** Deeper web search, verified findings, nuanced assessment
4. **Merge:** Pass 2 results merged into Pass 1 (dict union, list concat, string override)

### Intel CLI Usage

```bash
# ZIP research
python3 scrapers/qualitative_scout.py --zip 60491          # Single ZIP
python3 scrapers/qualitative_scout.py --metro chicagoland   # All Chicagoland ZIPs
python3 scrapers/qualitative_scout.py --status              # Coverage dashboard
python3 scrapers/qualitative_scout.py --report 60491        # View stored report

# Practice research
python3 scrapers/practice_deep_dive.py --zip 60491 --top 10 --deep  # Top 10, two-pass
python3 scrapers/practice_deep_dive.py --npi 1234567890             # Specific practice
python3 scrapers/practice_deep_dive.py --status                     # Coverage dashboard
python3 scrapers/practice_deep_dive.py --report 1234567890          # View stored dossier

# Weekly automation
python3 scrapers/weekly_research.py --budget 5              # $5 cap, batch API
python3 scrapers/weekly_research.py --dry-run               # Preview queue
```

### Environment
- `ANTHROPIC_API_KEY` — Required. Set via `export ANTHROPIC_API_KEY="sk-ant-..."`. Local batch runs need it; Vercel needs it separately for the Launchpad compound-narrative route.
- Cost tracking: `data/research_costs.json` (local JSON, 500-entry rolling log)
- Sync: Both intel tables use `full_replace` strategy in `sync_to_supabase.py`

### Critical Rules for Intel Layer
- NEVER fabricate research data — prompts instruct "return null, never fabricate"
- ALL scripts use `pipeline_logger.log_scrape_start/complete()` and `logger_config.get_logger()`
- Cache TTL is 90 days — don't re-research fresh data unless `--refresh` flag is passed
- Intel tables sync via `full_replace` — safe to overwrite on each sync run
- `research_engine.py` uses raw HTTP `requests`, NOT the `anthropic` Python SDK (fewer dependencies, faster cold starts)
- Circuit breaker: 3 consecutive API failures → `CircuitBreakerOpen` aborts remaining items (prevents 290 items × 120s timeout = 9.6hr hang if Anthropic is down)

## Anti-Hallucination Defense (April 25, 2026 — Do Not Regress)

Every practice dossier is gated through a 4-layer defense before it can land in `practice_intel`. Validated by a 200-practice Chicagoland run (msgbatch_017YJJ2M3WbLv4Q7gEhubK2o): 87% pass rate (174 stored / 26 quarantined), 854 forced web searches (avg 4.27/practice), $14.91 cost (~$0.075/practice). 0 hallucinations slipped through.

| Layer | Where | What it does |
|-------|-------|--------------|
| **1. Forced search** | `research_engine.py::_call_api()` accepts `force_search=True`, sets `body["tool_choice"] = {"type": "tool", "name": "web_search"}` | Anthropic guarantees ≥1 `web_search` per practice — model can no longer answer from priors. Practice path calls with `max_searches=5, force_search=True` |
| **2. Per-claim source URLs** | PRACTICE_USER schema in `research_engine.py` requires `_source_url` on every section (website, services, technology, google, hiring, acquisition, social, healthgrades, zocdoc, doctor, insurance) | Every non-null field traceable to a URL. Schema instructs `"no_results_found"` when a search yields nothing — fabrication has no escape hatch |
| **3. Self-assessment block** | Terminal `verification` block in PRACTICE_USER: `{searches_executed, search_queries, evidence_quality (verified\|partial\|insufficient), primary_sources}` | Model self-rates evidence quality. `insufficient` triggers automatic rejection downstream |
| **4. Post-validation gate** | `weekly_research.py::validate_dossier(npi, data) -> (ok, reason)` | 5 rejection rules: `missing_verification_block`, `insufficient_searches(N)`, `evidence_quality=insufficient`, `website.url_without_source`, `google.metrics_without_source`. Quarantined dossiers are NOT stored |

**Schema changes (do not regress):**
- `PracticeIntel` model in `database.py:426-428` has 3 columns: `verification_searches` (Integer), `verification_quality` (String(20), indexed), `verification_urls` (Text). Both Supabase + SQLite have them. **`Base.metadata.create_all()` does NOT alter existing tables** — adding new columns requires explicit `ALTER TABLE` on both databases.
- `intel_database.py::store_practice_intel()` extracts `data["verification"]` and writes those 3 columns.
- `weekly_research.py::retrieve_batch()` calls `validate_dossier()` BEFORE `store_practice_intel()`. Quarantined dossiers don't even hit the DB.

**EVIDENCE PROTOCOL in PRACTICE_SYSTEM (research_engine.py)** — non-negotiable rules baked into the system prompt:
1. Execute web_search ≥2 times per practice (required: `<name> <city> <state>`, `<name> <city> reviews`)
2. Every non-null field must be backed by a URL recorded in `_source_url`
3. Never infer from priors
4. Brand/technology claims must come from the practice's own website
5. If a search returns nothing, set fields to null AND `_source_url` to `"no_results_found"`
6. The terminal `verification` block is mandatory

**Cost calibration:** Use the **Anthropic console** (https://console.anthropic.com/usage), NOT `poll.py`'s `totals.total_cost_usd`, as the source of truth for actual billing. `poll.py`'s estimate is a worst-case overcount — verified 2026-04-26 against console for two batch runs:

| Run | poll.py estimate | Console actual | Overcount |
|-----|------------------|----------------|-----------|
| 200-practice (msgbatch_017YJJ…) | $14.91 | (rolled into MTD) | — |
| 2000-practice (msgbatch_01A3…) | $124.57 | ~$11 (MTD delta) | ~11× |
| Combined month-to-date (2026-04-25→26) | $139.48 | **$16.33** | **~8.5×** |

**Two bugs in `poll.py` cost math (`scrapers/dossier_batch/poll.py:148-160`):**
1. `web_search_requests` from `usage.server_tool_use` overcounts ~4.5× the billed search count (console showed 1,505 Haiku searches; poll.py reported 6,744). Cause unknown — possibly counts retries or sub-queries.
2. Full Haiku rates (`$0.50/$2.50/$0.05/$0.625` per MTok) are applied without the 50% Messages Batch API discount. Real batch rates are half: `$0.25/$1.25/$0.025/$0.3125`. Web-search unit price is also probably ~$0.0015/req in batch (not $0.01) — needs explicit confirmation from Anthropic billing.

**Real cost per practice (2026-04-26 calibration):** ~$0.005-0.010/practice in batch mode with bulletproofed protocol. **For future budget math, use $0.008/practice as the planning rate** — that gives $16 for a 2000-practice run, $80 for 10k. Confirm with the console after each run; flag if real cost exceeds $0.015/practice.

**Don't quote `poll.py.totals.total_cost_usd` to the user as the actual bill** — it's a worst-case estimate. Always reconcile with https://console.anthropic.com/usage before reporting cost.

**Operational scripts (`scrapers/dossier_batch/`):** see Pipeline File Quick Reference table for `launch.py`, `launch_2000_excl_chi.py`, `poll.py`, `poll_zip_batches.py`, `upsert_practice_intel.py`, `migrate_verification_cols.py`. `last_run_summary.json` holds the per-NPI breakdown of the 2026-04-25 200-practice run as a regression baseline.

**Known issues (open, not blocking):**
1. **`verification_quality` enum drift** — model returned `"high"` for 10 dossiers when spec is `verified|partial|insufficient`. Validation gate accepts non-`insufficient` values, so `"high"` slipped through. Either tighten the prompt to suppress `"high"` or widen the enum/index in `database.py:427`.
2. **`/tmp/full_batch_id.txt` is not committed** — `launch.py` writes it, `poll.py` reads it. Cross-process handoff via `/tmp` is fragile across reboots. Future: pass batch_id as CLI arg or use `data/last_batch_id.txt`.
3. **SQLite `ALTER TABLE` is not idempotent** — `migrate_verification_cols.py` against SQLite would fail with "duplicate column" since SQLite has no `ADD COLUMN IF NOT EXISTS`. Wrap in try/except or run via `sqlite3` CLI.
4. **Cost cap in `launch.py` is hardcoded $11** — trims to fit. `launch_2000_excl_chi.py` raised to $250. Bump the script if budget grows.
5. **`practice_signals` FK violation (RESOLVED 2026-04-25)** — NPI `1316509367` is GRACE KWON in WORCESTER, MA, zip `01610` (an earlier audit note misstated this as "Grace Kim, Boston, 02115" — corrected per direct SQLite lookup). Was pre-existing in `practice_signals` but missing from `practices`. Fixed by: (a) `compute_signals.py:475-505` filters `WHERE zip IN (SELECT zip_code FROM watched_zips)`, (b) explicit `npi IS NOT NULL` guard added in commit `eb75c6c`. Verified: `practice_signals.orphan_count = 0`. Sync floor `MIN_ROWS_THRESHOLD["practice_signals"] = 1000` protects against silent wipes.

**Backfill planning (post-200-practice run):**
- Remaining unresearched Chicagoland independents: ~8,559 (~$642 at $0.075/practice for full coverage)
- Tier-prioritized (only `solo_high_volume + family_practice + solo_inactive` with buyability ≥ 50): ~2,000 practices × $0.075 = ~$150
- Boston Metro (21 ZIPs, ~zero coverage): ~50-100 dossiers @ ~$8
- The 2000-practice non-606xx batch (`msgbatch_01A3FxKxKxemAyqDr2AcGYUq`) was submitted 2026-04-25 (284 solo_high_volume + 1716 solo_established across 171 ZIPs)

**End-to-end recipe:**
```bash
# 1. (one-time, if columns missing on a fresh DB)
python3 scrapers/dossier_batch/migrate_verification_cols.py
sqlite3 data/dental_pe_tracker.db \
  "ALTER TABLE practice_intel ADD COLUMN verification_searches INTEGER;" \
  "ALTER TABLE practice_intel ADD COLUMN verification_quality VARCHAR(20);" \
  "ALTER TABLE practice_intel ADD COLUMN verification_urls TEXT;"

# 2. submit
python3 scrapers/dossier_batch/launch.py
#    → writes /tmp/full_batch_id.txt

# 3. poll + validate + store + sync (background)
nohup python3 scrapers/dossier_batch/poll.py > /tmp/poll.log 2>&1 &

# 4. when /tmp/full_batch_summary.json appears, inspect it
python3 -c "import json; s=json.load(open('/tmp/full_batch_summary.json')); print(f\"stored={s['stored']} rejected={s['rejected']} cost=\${s['totals']['total_cost_usd']}\")"
```

## Pipeline Audit (April 22-23, 2026 — Do Not Regress)

A 3-week pipeline outage was root-caused across every scraper, the Supabase sync, and parser pattern-hunt. All fixes are in `main`. Follow-up live sync verification was still pending when the April 23 sub-audit ended. See `SCRAPER_AUDIT_STATUS.md` at repo root for the full audit status board.

### Bug fix table

| File | Bug | Fix |
|------|-----|-----|
| `scrapers/refresh.sh` | `run_step()` timeout wrapper killed only the subshell wrapper PID; the Python child orphaned and kept running attached to `tee`, blocking the whole pipeline | `pkill -TERM -P $bgpid` (then `-KILL` after grace) to reap all descendants. Verified: 300s sleep child died within 30s of timeout fire |
| `scrapers/sync_to_supabase.py` (deals dedup) | deals has a partial UNIQUE INDEX `uix_deal_no_dup (platform_company, target_name, deal_date) WHERE target_name IS NOT NULL` that isn't the ON CONFLICT target. One duplicate raised `psycopg2.errors.UniqueViolation`, aborted the transaction, lost every queued row | Per-row `conn.begin_nested()` savepoint in both `_sync_incremental_updated_at` (deals) and `_sync_incremental_id` (practice_changes). Dups skipped with WARNING, batch continues |
| `scrapers/sync_to_supabase.py` (`_sync_watched_zips_only`) | `DELETE FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)` hit `practice_changes_npi_fkey` (ON DELETE NO ACTION) and aborted; the 05:03 sync threw `ForeignKeyViolation` and deal_date stayed at 2026-03-02 | `TRUNCATE TABLE practices CASCADE` inside the existing atomic `pg_engine.begin()` block. TRUNCATE CASCADE in Postgres IS transactional. `practice_changes` sync_metadata reset in same transaction |
| `scrapers/sync_to_supabase.py` (silent-wipe risk) | `_sync_full_replace` had no floor for `platforms` (140 live), `pe_sponsors` (40 live), `zip_overviews` (12 live) — broken source query returning 0 rows would TRUNCATE live data without warning | Added floors to `MIN_ROWS_THRESHOLD`: `platforms=20`, `pe_sponsors=10`, `zip_overviews=5`. `zip_qualitative_intel` floor lowered to 0 (table grows over time). Fresh-install bootstrap requires manual floor lowering |
| `scrapers/sync_to_supabase.py` (resilience) | `except Exception: pass` in `_sync_pipeline_events` silently swallowed malformed JSONL rows; no SIGINT/SIGTERM handler; no post-sync verification | Converted `pass` → `log.warning(...)`. Module-level `_shutdown_requested` flag + `_handle_shutdown()` signal handler with 8 checkpoints throughout the sync loop. `_verify_table_count()` reads back row counts after every sync; `_sync_watched_zips_only` and `_sync_full_replace` raise `AssertionError` on mismatch |
| `scrapers/pesp_scraper.py` | DNS NXDOMAIN / transient HTTP failures during PESP redirects cratered the scraper; parser missed deals buried in commentary-heavy posts | DNS/HTTP retry wrapper with exponential backoff. 40+ `COMMENTARY_PATTERNS` regex pre-filter before deal extraction |
| `scrapers/gdn_scraper.py` | Category page restructure caused pagination crawler to wander into unrelated posts | `MAX_RETRIES=3` with backoff, `_is_roundup_link()` category guard limits crawl to known roundup URL patterns |
| `scrapers/gdn_scraper.py` (parser) | Fallback `extract_platform()` stopped too early on multi-word entity names connected by `&`, `and`, `of` (e.g. "Pacific & Western Dental Acquires…" captured only "Western Dental"). Several deal-announcement verbs missing from `_DEAL_VERB_SET` | New `_PASS_THROUGH_SET = {"&", "and", "of"}` allows connectors when `entity_words` already has content. Added verbs: `onboarded/onboards/onboarding`, `continues/continuing/continued`, `strengthens/strengthening/strengthened`, `deepens/deepening/deepened`. Added "Gen4 Dental Partners" to KNOWN_PLATFORMS |
| `scrapers/pesp_scraper.py` (parser) | KNOWN_PLATFORMS missing "Enable Dental", "Ideal Dental Management Partners", "Ideal Dental"; KNOWN_PE_SPONSORS missing "Bardo Capital", "Mellon Stud Ventures" | Added all 5 to alphabetical lists |
| `scrapers/adso_location_scraper.py` | Gentle Dental and Tend hung indefinitely on slow iframe-loaded location lists; log_scrape_complete never fired so dashboard showed phantom "running" | `HTTP_TIMEOUT=(10,30)` connect/read tuple, `MAX_SECONDS_PER_DSO=300`, `MAX_SECONDS_TOTAL=1500`. `log_scrape_complete()` moved into `finally` |
| `dental-pe-nextjs/src/lib/supabase/queries/system.ts` | Data Source Coverage panel showed "--" for ADSO Scraper and ADA HPI because those tables weren't queried for freshness; `ada_hpi_benchmarks.updated_at` is NULL on all 918 rows | Added `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at` queries, exposed under `ADSO Scraper` / `ADA HPI` keys that FreshnessIndicators reads |
| `launchd` (com.suleman.dental-pe.refresh) | macOS Sequoia LWCR stale-context bug caused the weekly cron to silently never fire | Diagnostic pass confirmed + monitored; re-ran manually. See `SCRAPER_AUDIT_STATUS.md` for the full runbook |

### Audit gotchas
- **Sync strategy map is not obvious from scraping code**: `TABLES_TO_SYNC` at the top of `sync_to_supabase.py` declares which strategy each table uses. `deals` uses `incremental_updated_at`, not `incremental_id`. Fixes to dedup behavior must land in BOTH paths.
- **`insert_deal()` dedup is asymmetric**: Python-side dedup checks 5 fields (platform, date, source, target, state) but the Postgres unique index covers only 3 (platform_company, target_name, deal_date). Multi-state deals with shared platform/target/date will silently hit the DB constraint. Per-row savepoints handle this cleanly.
- **Freshness columns aren't always populated**: `ada_hpi_benchmarks.updated_at` is NULL for all rows because `ada_hpi_importer.py` only sets `created_at`. When adding a freshness query, check which timestamp columns are actually populated first.
- **`tee | pipe` hides orphans**: A bash subshell that pipes to `tee` leaves the piped command as a separate PID. `kill $bgpid` only reaps the subshell. Always use `pkill -P $bgpid` when you need to stop the whole group.

### Test suite (`scrapers/test_sync_resilience.py`) — 11 tests, all pass
- `TestFullReplaceZeroRowGuard` (3): zero-row abort, below-floor abort, above-floor proceeds
- `TestSignalHandler` (4): SIGTERM/SIGINT set flag, handler registered, sync aborts on shutdown
- `TestPostSyncAssertion` (2): full_replace + watched_zips_only raise on count mismatch
- `TestRunVerifiedResults` (2): verified_results populated in extra dict

### GitHub Actions keep-alive (`.github/workflows/keep-supabase-alive.yml`)
Cron `'0 12 */3 * *'` (every 3 days at 12:00 UTC) hits Supabase `/rest/v1/` as read-only ping to prevent free-tier pause. **REQUIRES USER ACTION**: Add `SUPABASE_URL` + `SUPABASE_ANON_KEY` secrets in GitHub repo settings.

### Known limitations (NOT fixed, documented for future work)
- **GDN "Partners" ambiguity**: `partners/partnered/partnering` are in `_DEAL_VERB_SET` as verbs, so entity names ending in "Partners" (e.g., "Zyphos & Acmera Dental Partners") get truncated. KNOWN_PLATFORMS catches the common cases; a lookahead for "Partners with" vs "Partners <noun>" would improve the fallback.
- **Apostrophe normalization**: GDN logs show "Smith's Dental" (U+2019) and "Smith's Dental" (U+0027) deduplicating as different entities. Needs a Unicode normalization pass.
- **`ada_hpi_benchmarks.updated_at` still NULL**: Freshness UI reads `created_at` as a workaround. Next `ada_hpi_importer.py` run should set both.
- **Mirror scrapers in `dental-pe-nextjs/scrapers/`**: DEPRECATED markers added but the directory is gitignored, so markers are stranded on local disk. Cron reads from parent `/scrapers/`, so this isn't actively harmful. Recommend a future `rm -rf dental-pe-nextjs/scrapers/` cleanup.

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` when modifying the Streamlit app OR the Next.js frontend. Use `/data-axle-workflow` for Data Axle export/import tasks. Use `/debug-pipeline` when investigating scraper failures or data issues.
