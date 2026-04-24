# Dental PE Intelligence Platform — Claude Code Guide

## What This Project Is

A data pipeline + dual-frontend dashboard that tracks private equity consolidation in US dentistry. It scrapes deal announcements, monitors 400k+ dental practices from federal data, classifies who owns what, and scores markets for acquisition risk. Primary metro: Chicagoland (268 expanded ZIPs across 7 sub-zones). Secondary: Boston Metro (21 ZIPs).

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

Key tables: `deals`, `practices`, `practice_changes`, `watched_zips`, `zip_scores`, `dso_locations`, `ada_hpi_benchmarks`, `zip_qualitative_intel`, `practice_intel`

- **practices**: 400k+ rows. Fields: npi (PK), practice_name, doing_business_as, address, city, state, zip, phone, entity_type, taxonomy_code, ownership_status, affiliated_dso, affiliated_pe_sponsor, buyability_score, classification_confidence, classification_reasoning, data_source, latitude, longitude, parent_company, ein, franchise_name, iusa_number, website, year_established, employee_count, estimated_revenue, num_providers, location_type, import_batch_id, data_axle_import_date, entity_classification
- **deals**: 2,500+ rows. PE dental deals from PESP, GDN, PitchBook
- **practice_changes**: Change log for name/address/ownership changes (acquisition detection). 5,100+ rows.
- **zip_scores**: Per-ZIP consolidation stats (290 scored ZIPs), recalculated by merge_and_score.py. One row per ZIP (deduped).
- **watched_zips**: 290 ZIPs (268 Chicagoland + 21 Boston + 1 other). Auto-backfilled by ensure_chicagoland_watched().
- **dso_locations**: 408 scraped DSO office locations from ADSO websites.
- **ada_hpi_benchmarks**: 918 rows. State-level DSO affiliation rates by career stage (2022-2024).

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
- 401,645 practices (362k independent, 2.8k DSO-affiliated, 401 PE-backed, 35k unknown)
- 3,215 deals (3,011 GDN + 162 PESP + 42 PitchBook, coverage Oct 2020 – Mar 2026)
- 2,992 Data Axle enriched practices (with lat/lon, revenue, employees, year established)
- 290 scored ZIPs

## Next.js Frontend (Primary)

**Stack:** Next.js 16, React 19, TypeScript 5, Supabase Postgres, TanStack React Query + Table, Recharts 3, Mapbox GL, Tailwind CSS 4, shadcn UI, Lucide React

**Fonts:** DM Sans (headings, 24px/700 page titles), Inter (body), JetBrains Mono (data values, 28px/700 KPIs). Data labels: 11px/500/Inter/uppercase/tracking-wider.

**Deployment:** Vercel auto-deploys on push to main

**Env vars:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MAPBOX_TOKEN`

### Pages (9 total)

| Route | Page | What It Shows |
|-------|------|---------------|
| `/` | Home | 6 KPI cards (Lucide icons), two-column layout (recent deals table + activity feed from practice_changes), data freshness bar, 2x3 quick nav grid |
| `/warroom` | **Warroom** | Chicagoland god-mode command surface. 4 modes (Sitrep / Hunt / Profile / Investigate), 8 lenses (consolidation, density, buyability, retirement, pe_exposure, saturation, whitespace, disagreement), 12 scopes (US, chicagoland, 7 subzones, 3 saved presets). Intent bar (⌘K), Living Map, ranked target list, ZIP + practice dossier drawers, pinboard tray, signal flag overlays (15 practice + 8 ZIP), keyboard shortcuts (`?`), URL-synced state. |
| `/deal-flow` | Deal Flow | **4 tabs: Overview \| Sponsors \| Geography \| Deals.** Persistent KPI strip above tabs. Overview: deal volume timeline + specialty charts. Sponsors: top 15 sponsors/platforms. Geography: state choropleth. Deals: full searchable table with URL-synced filters. |
| `/market-intel` | Market Intel | **3 tabs: Consolidation \| ZIP Analysis \| Ownership.** Persistent tiered consolidation KPIs above tabs. Consolidation: DSO Penetration Table + Mapbox consolidation map. ZIP Analysis: ZIP score table + city practice tree. Ownership: 11-type entity classification breakdown + methodology notes. Cross-link banner to Warroom. |
| `/buyability` | Buyability | Verdict extraction from notes field, 4 category KPIs, ZIP filter, sortable table with CSV export |
| `/job-market` | Job Market | **4 tabs: Overview \| Map \| Directory \| Analytics.** Persistent KPI strip + Living Location Selector (4 presets) above tabs. Overview: saturation table (relocated from Market Intel) + ADA benchmarks (relocated from Market Intel) + opportunity signals. Map: hero-sized Mapbox practice density map (hex layers + individual dots). Directory: searchable practice table with detail drawer. Analytics: market overview charts, entity classification breakdown, top DSOs. |
| `/research` | Research | PE sponsor profiles, DSO platform profiles, state deep dives, SQL explorer (SELECT-only, forbidden keywords) |
| `/intelligence` | Intelligence | AI-powered qualitative research — 6 KPI cards (coverage, readiness, cost, confidence), ZIP market intelligence table with expandable 10-signal detail panels, practice dossier table with readiness/confidence badges and expandable due diligence reports. Cross-link banner to Warroom Investigate mode. |
| `/system` | System | Data freshness indicators, source coverage, completeness bars, pipeline log viewer, manual entry forms (add deal, edit practice) |

### Data Flow Pattern

1. **Server Components** (`page.tsx`) fetch from Supabase server-side
2. Pass data to **Client Component shells** (`'use client'`) via props
3. Client shells handle filters, UI state, refetching via **React Query** (5min stale, 30min gc)
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
- **Maps:** subtle shadow on white card background

### Sidebar Navigation

Sidebar grouped into 4 sections (dark #2C2C2C background, goldenrod #B8860B active accent):
- **OVERVIEW:** Dashboard (`/`), Warroom (`/warroom`)
- **MARKETS:** Job Market, Market Intel, Buyability
- **ANALYSIS:** Deal Flow, Research, Intelligence
- **ADMIN:** System

### Module Relocations (2026-03-15 UI Overhaul)

- `saturation-table.tsx`: copied from `market-intel` to `job-market` (now rendered in Job Market Overview tab)
- `ada-benchmarks.tsx`: copied from `market-intel` to `job-market` (now rendered in Job Market Overview tab)
- `dso-penetration-table.tsx`: new component in `market-intel` (extracted from ownership-landscape, rendered in Consolidation tab)
- `recent-changes`: now rendered on Home page activity feed (fetched via `getRecentChanges`)

### Next.js File Quick Reference

| File | What It Does |
|------|-------------|
| `src/app/layout.tsx` | Root layout — fonts, providers (Query, Sidebar, Tooltip), sidebar |
| `src/app/page.tsx` | Home page — fetches stats, deals, freshness |
| `src/app/globals.css` | Tailwind 4 + CSS custom properties + warm light theme |
| `src/app/warroom/page.tsx` | Warroom — `force-dynamic` Server Component calling `getSitrepBundle` |
| `src/app/warroom/_components/warroom-shell.tsx` | Warroom orchestrator — holds state, wires modes, drawers, keyboard |
| `src/app/warroom/_components/scope-selector.tsx` | 12-option scope dropdown (US / chicagoland / 7 subzones / 3 saved) |
| `src/app/warroom/_components/intent-bar.tsx` | ⌘K-focusable NL intent input |
| `src/app/warroom/_components/sitrep-kpi-strip.tsx` | 6 KPIs for Sitrep mode |
| `src/app/warroom/_components/living-map.tsx` | Mapbox ZIP choropleth colored by lens + signal flag overlays |
| `src/app/warroom/_components/briefing-pane.tsx` | Scope-specific alerts + intent chip suggestions |
| `src/app/warroom/_components/target-list.tsx` | Hunt mode ranked practice list |
| `src/app/warroom/_components/dossier-drawer.tsx` | Practice dossier drawer |
| `src/app/warroom/_components/zip-dossier-drawer.tsx` | ZIP dossier drawer (saturation, ownership, top practices) |
| `src/app/warroom/_components/profile-mode-panel.tsx` | Pinned targets side-by-side compare |
| `src/app/warroom/_components/investigate-mode-panel.tsx` | Flag co-occurrence + compound-signal targets |
| `src/app/warroom/_components/pinboard-tray.tsx` | Bottom tray for pinned targets |
| `src/app/warroom/_components/keyboard-shortcuts-overlay.tsx` | `?`-triggered shortcuts dialog |
| `src/lib/warroom/mode.ts` | WARROOM_MODES + WARROOM_LENSES constants |
| `src/lib/warroom/scope.ts` | 12 scope definitions + `normalizeWarroomDataScope()` |
| `src/lib/warroom/geo.ts` | Geographic helpers (subzone ZIPs, bounding boxes) |
| `src/lib/warroom/signals.ts` | WarroomPracticeRecord + SitrepBundle types + flag constants |
| `src/lib/warroom/data.ts` | `getSitrepBundle()` — batch-fetch by scope |
| `src/lib/warroom/intent.ts` | NL intent parsing + flag labels |
| `src/lib/warroom/ranking.ts` | `rankTargets()` composite scoring |
| `src/lib/warroom/briefing.ts` | Briefing item builder |
| `src/lib/hooks/use-warroom-state.ts` | URL-synced warroom state hook |
| `src/lib/hooks/use-warroom-data.ts` | React Query wrapper for SitrepBundle |
| `src/components/layout/warroom-cross-link.tsx` | Goldenrod banner rendered on Market Intel + Intelligence |
| `src/app/deal-flow/page.tsx` | Deal Flow — server fetch, passes to shell |
| `src/app/deal-flow/_components/deal-flow-shell.tsx` | Deal Flow client shell — filters, charts, table |
| `src/app/deal-flow/_components/deal-kpis.tsx` | Deal KPI cards with YoY deltas |
| `src/app/deal-flow/_components/deal-volume-timeline.tsx` | Stacked bar + rolling avg chart |
| `src/app/deal-flow/_components/sponsor-platform-charts.tsx` | Top sponsors/platforms bar charts |
| `src/app/deal-flow/_components/state-choropleth.tsx` | US state deal density map |
| `src/app/deal-flow/_components/specialty-charts.tsx` | Specialty breakdown charts |
| `src/app/deal-flow/_components/deals-table.tsx` | Searchable deals table |
| `src/app/market-intel/page.tsx` | Market Intel — server fetch with classification counts |
| `src/app/market-intel/_components/market-intel-shell.tsx` | Market Intel client shell |
| `src/app/market-intel/_components/consolidation-map.tsx` | Mapbox consolidation heatmap |
| `src/app/market-intel/_components/zip-score-table.tsx` | ZIP scores with computed columns |
| `src/app/market-intel/_components/city-practice-tree.tsx` | Paginated practice tree by city/ZIP |
| `src/app/market-intel/_components/saturation-table.tsx` | Saturation metrics analysis |
| `src/app/market-intel/_components/ada-benchmarks.tsx` | ADA HPI benchmark display |
| `src/app/market-intel/_components/recent-changes.tsx` | Practice change log |
| `src/app/market-intel/_components/dso-penetration-table.tsx` | DSO penetration by ZIP with city names |
| `src/app/buyability/page.tsx` | Buyability — server fetch, passes to shell |
| `src/app/buyability/_components/buyability-shell.tsx` | Buyability client shell |
| `src/app/job-market/page.tsx` | Job Market — server fetch, passes to shell |
| `src/app/job-market/_components/job-market-shell.tsx` | Job Market client shell — all sections |
| `src/app/job-market/_components/living-location-selector.tsx` | 4-preset location picker |
| `src/app/job-market/_components/practice-density-map.tsx` | Mapbox hex + dot density map |
| `src/app/job-market/_components/practice-directory.tsx` | Searchable practice table |
| `src/app/job-market/_components/practice-detail-drawer.tsx` | Practice detail side panel |
| `src/app/job-market/_components/market-overview-charts.tsx` | Ownership donut, consolidation, age, DSOs |
| `src/app/job-market/_components/opportunity-signals.tsx` | Retirement risk, buyability, changes |
| `src/app/job-market/_components/ownership-landscape.tsx` | Entity classification, DSO penetration |
| `src/app/job-market/_components/market-analytics.tsx` | Density, competitive landscape |
| `src/app/job-market/_components/saturation-table.tsx` | Saturation metrics table (relocated from Market Intel) |
| `src/app/job-market/_components/ada-benchmarks.tsx` | ADA HPI benchmarks display (relocated from Market Intel) |
| `src/app/intelligence/page.tsx` | Intelligence — server fetch for ZIP + practice intel |
| `src/app/intelligence/_components/intelligence-shell.tsx` | Intelligence client shell — KPIs, ZIP intel table, practice dossier table, expandable detail panels |
| `src/lib/types/intel.ts` | TypeScript interfaces (ZipQualitativeIntel, PracticeIntel, IntelStats) |
| `src/lib/supabase/queries/intel.ts` | Intel query functions (getZipIntel, getPracticeIntel, getIntelStats) |
| `src/app/research/_components/research-shell.tsx` | Research client shell — tabs |
| `src/app/research/_components/sponsor-profile.tsx` | PE sponsor deep dive |
| `src/app/research/_components/platform-profile.tsx` | DSO platform deep dive |
| `src/app/research/_components/state-deep-dive.tsx` | State-level analysis |
| `src/app/research/_components/sql-explorer.tsx` | SELECT-only SQL query runner |
| `src/app/system/_components/system-shell.tsx` | System client shell |
| `src/app/system/_components/freshness-indicators.tsx` | Data age indicators |
| `src/app/system/_components/data-coverage.tsx` | Source coverage stats |
| `src/app/system/_components/completeness-bars.tsx` | Field completeness visualization |
| `src/app/system/_components/pipeline-log-viewer.tsx` | Pipeline event log viewer |
| `src/app/system/_components/manual-entry-forms.tsx` | Deal/practice entry forms |
| `src/lib/types/index.ts` | TypeScript interfaces (Deal, Practice, ZipScore, WatchedZip, HomeSummary, etc.) |
| `src/lib/types-job-market.ts` | Job Market-specific types |
| `src/lib/supabase/client.ts` | Browser Supabase client (singleton) |
| `src/lib/supabase/server.ts` | Server Supabase client (per-request) |
| `src/lib/supabase/types.ts` | Supabase database type definitions |
| `src/lib/supabase/queries/deals.ts` | Deal query functions |
| `src/lib/supabase/queries/practices.ts` | Practice query functions |
| `src/lib/supabase/queries/zip-scores.ts` | ZIP score query functions |
| `src/lib/supabase/queries/watched-zips.ts` | Watched ZIP query functions |
| `src/lib/supabase/queries/practice-changes.ts` | Practice changes query functions |
| `src/lib/supabase/queries/ada-benchmarks.ts` | ADA benchmark query functions |
| `src/lib/supabase/queries/benchmarks.ts` | Additional benchmark queries |
| `src/lib/supabase/queries/changes.ts` | Change tracking queries |
| `src/lib/supabase/queries/system.ts` | System/freshness query functions |
| `src/lib/constants/entity-classifications.ts` | 11 entity types, helpers, classification logic |
| `src/lib/constants/design-tokens.ts` | Color system, ownership labels/colors |
| `src/lib/constants/colors.ts` | Entity classification color map |
| `src/lib/constants/living-locations.ts` | Job Market location presets (4 presets, ZIP lists) |
| `src/lib/constants/metro-centers.ts` | Metro area center coordinates |
| `src/lib/constants/zip-centroids.ts` | ZIP code lat/lon centroids for map rendering |
| `src/lib/constants/sql-presets.ts` | SQL explorer preset queries |
| `src/lib/constants/deal-type-colors.ts` | Deal type color mappings |
| `src/lib/constants/us-states.ts` | US state abbreviations/names |
| `src/lib/utils/formatting.ts` | formatNumber, formatCurrency, formatPercent, formatDate, formatStatusLabel, computeConsolidationDisplay |
| `src/lib/utils/scoring.ts` | computeJobOpportunityScore, isRetirementRisk, getPracticeAge |
| `src/lib/utils/csv-export.ts` | CSV download utility |
| `src/lib/utils/colors.ts` | Color utility functions |
| `src/lib/hooks/use-url-filters.ts` | URL param sync for shareable filter state |
| `src/lib/hooks/use-sidebar.ts` | Sidebar collapse state |
| `src/lib/hooks/use-section-observer.ts` | Intersection observer for section tracking |
| `src/components/data-display/data-table.tsx` | TanStack Table (sort, filter, paginate, CSV) |
| `src/components/data-display/kpi-card.tsx` | KPI card (icon, label, value, delta, accent, tooltip) |
| `src/components/data-display/data-freshness-bar.tsx` | Data freshness indicator bar |
| `src/components/data-display/section-header.tsx` | Section header with optional action |
| `src/components/data-display/status-badge.tsx` | Status badge component |
| `src/components/data-display/status-dot.tsx` | Small status indicator dot |
| `src/components/data-display/confidence-stars.tsx` | Confidence star rating display |
| `src/components/charts/bar-chart.tsx` | Recharts bar chart wrapper |
| `src/components/charts/stacked-bar-chart.tsx` | Recharts stacked bar chart |
| `src/components/charts/grouped-bar-chart.tsx` | Recharts grouped bar chart |
| `src/components/charts/area-chart.tsx` | Recharts area chart wrapper |
| `src/components/charts/donut-chart.tsx` | Recharts donut/pie chart |
| `src/components/charts/histogram-chart.tsx` | Recharts histogram |
| `src/components/charts/scatter-chart.tsx` | Recharts scatter plot |
| `src/components/charts/chart-container.tsx` | Responsive chart wrapper |
| `src/components/filters/filter-bar.tsx` | Filter controls bar |
| `src/components/filters/search-input.tsx` | Search input with debounce |
| `src/components/filters/multi-select.tsx` | Multi-select dropdown |
| `src/components/filters/date-range-picker.tsx` | Date range picker |
| `src/components/maps/map-container.tsx` | Mapbox GL map wrapper |
| `src/components/layout/sidebar.tsx` | Collapsible left nav (220px / 60px), dark #2C2C2C, 4 grouped sections |
| `src/components/layout/sticky-section-nav.tsx` | Sticky section navigation |
| `src/components/ui/*.tsx` | shadcn UI primitives (button, card, dialog, etc.) |
| `src/providers/query-provider.tsx` | React Query provider (5min stale, 30min gc, 1 retry) |
| `src/providers/sidebar-provider.tsx` | Sidebar state provider |
| `src/app/api/deals/` | API route for deal operations |
| `src/app/api/practices/` | API route for practice operations |
| `src/app/api/sql-explorer/` | API route for SQL explorer (SELECT-only) |
| `src/app/api/watched-zips/` | API route for watched ZIP operations |

## Streamlit Dashboard (Legacy)

Single-file dashboard at `dashboard/app.py` (2,583 lines, 6 pages). Still live at suleman7-pe.streamlit.app but no longer the primary frontend.

### Pages (6 total)

| Page | What It Shows |
|------|---------------|
| **Deal Flow** | Every PE dental deal — charts by year, state, deal type, recent activity feed |
| **Market Intel** | Watched ZIPs — consolidation map, ownership breakdown, ZIP-level detail, practice changes |
| **Buyability** | Individual practice scoring — filters by ZIP, verdict categories, confidence ratings |
| **Job Market** | Post-graduation job hunting — practice density pydeck map, market overview, searchable directory, opportunity signals, ownership landscape, market analytics |
| **Research** | Deep dives — PE sponsor profiles, platform profiles, state analysis, SQL explorer |
| **System** | Data freshness, pipeline logs, manual data entry forms |

### Job Market Page Structure (Streamlit)
- Living location selector: West Loop/South Loop (142 ZIPs), Woodridge (129 ZIPs), Bolingbrook (127 ZIPs), All Chicagoland (268 ZIPs)
- 6 KPI cards computed from practice data (not zip_scores): Total Practices, Independent %, Consolidated %, Avg Buyability, 10+ Staff, Retirement Risk
- Pydeck dual-density hexagon map: green = independent clusters, red/orange = consolidated clusters, individual practice dots via toggle
- Market Overview: consolidation by ZIP bar chart, ownership donut, practice age histogram with retirement risk line, top DSOs bar chart
- Searchable Practice Directory with ownership/source filters, sort options, CSV download
- Opportunity Signals tabs: Retirement Risk, High Buyability scatter, Recent Changes
- Ownership Landscape: status bar chart, size distribution, top DSOs table, DSO penetration by ZIP
- Market Analytics: dentist density by ZIP, consolidation breakdown stacked bar, competitive landscape (DSO market share, PE sponsors active)

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

### Bug fixes applied (March 2026) — do not regress
- All KPI icons use Lucide JSX components (not strings)
- Home page consolidatedPct includes % suffix
- `getRetirementRiskCount` filters by watched ZIPs + `year_established < 1995` + all 7 independent classifications (returns 226)
- `getAcquisitionTargetCount` filters by watched ZIPs + `buyability_score >= 50` (returns 34)
- `getPracticeStats` returns full `PracticeStats` with tiered corporate: `corporateHighConf` (262 = 1.9%), `corporate` (1,392 = 9.9%), `enriched` (2,992)
- Market Intel KPIs computed from entity_classification (server-side classificationCounts prop) with tiered display
- Job Market KPI shows tiered consolidation: "High-Confidence Corporate: 1.9%" primary, "All detected signals: 9.9%" secondary, "Industry estimate: 25-35%" subtitle
- KpiCard component supports `subtitle` prop for tiered display
- ZIP Score table uses `fmtPct` helper for percentage columns; confidence/opportunity_score renderers handle both cell-value and row-object patterns
- City practice tree paginates within each ZIP chunk to avoid Supabase 1000-row limit
- Consolidation map computes pct from corporate_share_pct * total_gp_locations
- Opportunity signals icons are JSX components
- DSO penetration table gets city names from watchedZips lookup and corporate_share_pct from zip_scores
- Job Market enrichment count uses `data_axle_import_date IS NOT NULL`
- `scoring.ts` uses entity_classification with ownership_status fallback
- `getPracticeCountsByStatus` uses entity_classification as primary with ownership_status fallback
- SQL presets use entity_classification (not ownership_status)
- System completeness "Ownership Classified" counts entity_classification primary + ownership_status fallback
- `entity-classifications.ts` exports `INDEPENDENT_CLASSIFICATIONS`, `DSO_NATIONAL_TAXONOMY_LEAKS`, `DSO_REGIONAL_STRONG_SIGNAL_FILTER` constants
- `PracticeStats` interface in both `types.ts` and `types/index.ts`; `HomeSummary` includes `enrichedCount`
- UI overhaul (2026-03-15): dark-to-warm-light theme migration, tab navigation on Deal Flow/Market Intel/Job Market, module relocations (saturation + ADA benchmarks to Job Market, DSO penetration table extracted in Market Intel), sidebar regrouped into 4 sections, Home page restructured with activity feed — all 8 pages render with warm light theme, tabs URL-synced, build passes

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

### Entity Classification in Next.js vs Streamlit

In the Next.js frontend, `entity_classification` is the **primary** ownership field. The helpers in `src/lib/constants/entity-classifications.ts` define the canonical groupings:
- **Independent:** solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group
- **Corporate:** dso_regional, dso_national
- **Specialist:** specialist
- **Non-clinical:** non_clinical
- **Unknown:** NULL entity_classification AND ownership_status not in (dso-affiliated, pe-backed)

The Streamlit app still primarily uses `ownership_status` with entity_classification as supplemental detail.

### Saturation Metrics (in zip_scores)
Computed by `merge_and_score.py`'s `compute_saturation_metrics()`:

- **DLD (Dentist Location Density):** `dld_gp_per_10k` = GP dental offices per 10,000 residents. National avg ~6.1. Lower = less competition.
- **Buyable Practice Ratio:** `buyable_practice_ratio` = % of GP offices classified as solo_established, solo_inactive, or solo_high_volume. Higher = more acquisition targets.
- **Corporate Share:** `corporate_share_pct` = % of GP offices classified as dso_regional or dso_national. Higher = more consolidated market.
- **Market Type:** `market_type` = computed classification based on combined metrics. Set to NULL when `metrics_confidence` is 'low' (data insufficient for reliable labeling).
- **People per GP Door:** `people_per_gp_door` = population / GP locations. Higher = fewer options per resident.

### Specialist Separation Methodology
A practice is classified as `specialist` if ANY of these conditions are met:
1. **Taxonomy code match** — NPPES taxonomy starts with specialist prefix (1223D, 1223E, 1223P, 1223S, 1223X). Excludes 1223G (General) and 122300 (General Dentist).
2. **Practice name keyword** — Name contains: ORTHODONT, PERIODON, ENDODONT, ORAL SURG, MAXILLOFACIAL, PEDIATRIC DENT, PEDODONT, PROSTHODONT, IMPLANT CENT.
3. A location (unique address) counts as GP if it has at least one non-specialist, non-clinical practice. Specialist-only locations are counted separately in `total_specialist_locations`.

### Confidence System
- **`metrics_confidence`** on zip_scores: 'high' (classification coverage >80% AND unknown ownership <20%), 'medium' (coverage >50% AND unknown <40%), 'low' (anything else).
- **`market_type_confidence`**: 'confirmed' (metrics_confidence is high), 'provisional' (medium), 'insufficient_data' (low — market_type set to NULL).
- **`classification_confidence`** on practices: 0-100 score from DSO name/pattern matching. Higher = more certain the ownership classification is correct.

### Market Type Values
Priority order (first match wins): `low_resident_commercial`, `high_saturation_corporate`, `corporate_dominant`, `family_concentrated`, `low_density_high_income`, `low_density_independent`, `growing_undersupplied`, `balanced_mixed`, `mixed` (default).

### Buyability Score Modifiers (Phase 5)
In addition to the base scoring in `compute_buyability()` (data_axle_importer.py), two ADDITIVE penalties are applied after entity classification:
- **Family practice penalty (-20):** `entity_classification == 'family_practice'` — shared last name at address suggests internal succession.
- **Multi-ZIP presence penalty (-15):** Same practice name or EIN appears in 3+ watched ZIPs — likely a chain entity.

## Qualitative Intelligence Layer

AI-powered research tools that layer qualitative signals on top of quantitative pipeline data. Uses Claude API with web search to gather market intelligence and practice due diligence.

### Intel Architecture

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
- Metadata: `research_date`, `research_method`, `raw_json`, `cost_usd`, `model_used`
- Cache TTL: 90 days

**`practice_intel`** — Practice-level due diligence (one row per NPI)
- FK: `npi` references `practices(npi)`
- Signals: website analysis, services, technology, Google reviews, hiring, acquisition news, social media, HealthGrades, ZocDoc, doctor profile, insurance
- Assessment: `red_flags`, `green_flags`, `overall_assessment`, `acquisition_readiness`, `confidence`
- Metadata: `research_date`, `escalated`, `escalation_findings`, `raw_json`, `cost_usd`, `model_used`
- Cache TTL: 90 days

### Intel Cost Model (March 2026 Anthropic Pricing)

| Mode | Model | Cost/Target | Use Case |
|------|-------|-------------|----------|
| ZIP Scout | Haiku 4.5 | ~$0.04-0.06 | Market research per ZIP |
| Practice Research | Haiku 4.5 | ~$0.08-0.12 | Due diligence per practice |
| Two-Pass Deep | Haiku then Sonnet | ~$0.28 | Escalation for high-value targets |
| Batch API | Haiku 4.5 | 50% discount | Weekly automated runs |

Monthly at moderate scale (50 ZIPs + 100 practices): ~$12-18. Actual costs are 2-3x lower than estimates (conservative budgeting).

### Two-Pass Escalation Logic

1. **Pass 1 (Haiku):** All practices get a baseline scan
2. **Escalation decision:** Triggers Sonnet deep dive if:
   - `readiness` is high/medium AND `confidence` is not high, OR
   - 3+ green flags detected
   - Guard: never escalates `unlikely` or `unknown` readiness
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

### Intel Environment

- `ANTHROPIC_API_KEY` — Required. Set via `export ANTHROPIC_API_KEY="sk-ant-..."`
- Cost tracking: `data/research_costs.json` (local JSON, 500-entry rolling log)
- Sync: Both intel tables use `full_replace` strategy in `sync_to_supabase.py`

### Critical Rules for Intel Layer

- NEVER fabricate research data — prompts instruct "return null, never fabricate"
- ALL scripts must use `pipeline_logger.log_scrape_start/complete()` and `logger_config.get_logger()`
- Cache TTL is 90 days — don't re-research fresh data unless `--refresh` flag is passed
- Intel tables sync via `full_replace` — safe to overwrite on each sync run
- `research_engine.py` uses raw HTTP `requests`, NOT the `anthropic` Python SDK (fewer dependencies, faster cold starts)
- Circuit breaker: 3 consecutive API failures → `CircuitBreakerOpen` exception aborts remaining items (prevents 290 items x 120s timeout = 9.6hr hang if Anthropic is down)

## Pipeline Audit — April 2026 (Do Not Regress)

A 3-week pipeline outage was root-caused across every scraper and the Supabase sync. All fixes are in `main` as of 2026-04-22 and validated by a full end-to-end trial run (16,798 rows synced, 6 new deals, zero fatal errors).

| File | Bug | Fix |
|------|-----|-----|
| `scrapers/refresh.sh` | `run_step()` timeout wrapper killed only the subshell wrapper PID; the Python child orphaned and kept running attached to `tee`, so a hung scraper blocked the whole pipeline | `pkill -TERM -P $bgpid` (then `-KILL` after grace) to reap all descendants of the subshell. Verified: 300s sleep child died within 30s of timeout fire |
| `scrapers/sync_to_supabase.py` | deals has a partial UNIQUE INDEX `uix_deal_no_dup (platform_company, target_name, deal_date) WHERE target_name IS NOT NULL` that isn't the ON CONFLICT target. One duplicate raised `psycopg2.errors.UniqueViolation`, aborted the transaction, lost every queued row | Per-row `conn.begin_nested()` savepoint in both `_sync_incremental_updated_at` (deals) and `_sync_incremental_id` (practice_changes). Dups skipped with WARNING, batch continues. Trial: 6 synced, 4 dup-skipped |
| `scrapers/pesp_scraper.py` | DNS NXDOMAIN / transient HTTP failures during PESP redirects cratered the scraper; parser missed deals buried in commentary-heavy posts | DNS/HTTP retry wrapper with exponential backoff. 40+ `COMMENTARY_PATTERNS` regex pre-filter before deal extraction |
| `scrapers/gdn_scraper.py` | Category page restructure caused pagination crawler to wander into unrelated posts | `MAX_RETRIES=3` with backoff, `_is_roundup_link()` category guard limits crawl to known roundup URL patterns |
| `scrapers/adso_location_scraper.py` | Gentle Dental and Tend hung indefinitely on slow iframe-loaded location lists; log_scrape_complete never fired so dashboard showed phantom "running" | `HTTP_TIMEOUT=(10,30)` connect/read tuple, `MAX_SECONDS_PER_DSO=300`, `MAX_SECONDS_TOTAL=1500`. `log_scrape_complete()` moved into `finally` |
| `dental-pe-nextjs/src/lib/supabase/queries/system.ts` | Data Source Coverage panel showed "--" for ADSO Scraper and ADA HPI because those tables weren't queried for freshness; `ada_hpi_benchmarks.updated_at` is NULL on all 918 rows | Added `dso_locations.scraped_at` + `ada_hpi_benchmarks.created_at` queries, exposed under `ADSO Scraper` / `ADA HPI` keys that FreshnessIndicators reads |
| `launchd` (com.suleman.dental-pe.refresh) | macOS Sequoia LWCR stale-context bug caused the weekly cron to silently never fire | Diagnostic pass confirmed + monitored; re-ran manually. See `SCRAPER_AUDIT_STATUS.md` for the full runbook |

See `SCRAPER_AUDIT_STATUS.md` at repo root for the full audit status board with validation test proofs.

### Gotchas Learned from the Audit

- **Sync strategy map is not obvious from scraping code**: `TABLES_TO_SYNC` at the top of `sync_to_supabase.py` declares which strategy each table uses. `deals` uses `incremental_updated_at`, not `incremental_id`. Fixes to dedup behavior must land in BOTH paths.
- **`insert_deal()` dedup is asymmetric**: Python-side dedup checks 5 fields (platform, date, source, target, state) but the Postgres unique index covers only 3 (platform_company, target_name, deal_date). Multi-state deals with shared platform/target/date will silently hit the DB constraint. Per-row savepoints handle this cleanly.
- **Freshness columns aren't always populated**: `ada_hpi_benchmarks.updated_at` is NULL for all rows because `ada_hpi_importer.py` only sets `created_at`. When adding a freshness query, check which timestamp columns are actually populated first.
- **`tee | pipe` hides orphans**: A bash subshell that pipes to `tee` leaves the piped command as a separate PID. `kill $bgpid` only reaps the subshell. Always use `pkill -P $bgpid` when you need to stop the whole group.

## Pipeline Audit — April 23, 2026 (Sync Hardening + Parser Pattern-Hunt)

Continuation of the April 22 audit. After the initial audit left the cron firing but deals stuck at deal_date=2026-03-02 (live Vercel showed stale data on April 23), a multi-agent team went deeper into the Supabase sync resilience and ran pattern-hunt across the GDN/PESP parsers. Code is in `main` as of 2026-04-23; the follow-up live sync verification is still pending a new session.

### Sync resilience hardening (`scrapers/sync_to_supabase.py`)

| Concern | Fix |
|---------|-----|
| `_sync_watched_zips_only` used `DELETE FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)` — this hit `practice_changes_npi_fkey` (ON DELETE NO ACTION) and aborted the transaction, which is why the 05:03 sync threw `ForeignKeyViolation` and the deal_date stayed at 2026-03-02 | Replaced `DELETE` with `TRUNCATE TABLE practices CASCADE` inside the existing atomic `pg_engine.begin()` block. TRUNCATE CASCADE in Postgres IS transactional (the "DDL can't rollback" claim is MySQL-specific). `practice_changes` sync_metadata is reset in the same transaction so the next incremental run re-sends all rows |
| Silent-wipe risk: `_sync_full_replace` had no floor for `platforms` (140 live), `pe_sponsors` (40 live), `zip_overviews` (12 live) — a broken source query returning 0 rows would TRUNCATE live data without warning | Added floors to `MIN_ROWS_THRESHOLD`: `platforms=20`, `pe_sponsors=10`, `zip_overviews=5`. Fresh-install bootstrap requires manually lowering the floor (not a --force flag yet) |
| `except Exception: pass` in `_sync_pipeline_events` silently swallowed malformed JSONL rows | Converted to `except Exception as row_err: log.warning("[pipeline_events] Skipping malformed row: %s", row_err)` |
| No SIGINT/SIGTERM handler — a Ctrl-C mid-sync could leave a table truncated with no rows inserted | Module-level `_shutdown_requested` flag + `_handle_shutdown()` signal handler. 8 checkpoints throughout the sync loop abort gracefully after current batch |
| No post-sync verification — previous sync run showed "290 rows synced" for zip_scores but didn't verify Supabase actually had 290 rows | `_verify_table_count()` reads back row counts after every sync and builds `verified_row_counts` dict. `_sync_watched_zips_only` and `_sync_full_replace` both raise `AssertionError` on mismatch |
| `zip_qualitative_intel` floor of 200 blocked legitimate small-coverage runs | Lowered to 0 (this table grows over time; fresh install may have zero rows) |

### Parser pattern-hunt fixes (`scrapers/gdn_scraper.py`, `scrapers/pesp_scraper.py`)

| Concern | Fix |
|---------|-----|
| GDN fallback `extract_platform()` stopped too early on multi-word entity names connected by `&`, `and`, `of` — e.g. "Pacific & Western Dental Acquires..." captured only "Western Dental" when `&` was non-capitalized | New `_PASS_THROUGH_SET = {"&", "and", "of"}` allows connectors when `entity_words` already has content |
| Several deal-announcement verbs missing from `_DEAL_VERB_SET`, causing entity names to bleed past the verb — logs showed "Bluewater Dental Onboarded Smith Practice Into Its Network" stored as platform_company | Added: `onboarded/onboards/onboarding`, `continues/continuing/continued`, `strengthens/strengthening/strengthened`, `deepens/deepening/deepened` |
| GDN `KNOWN_PLATFORMS` missing "Gen4 Dental Partners" (appeared in 2026 deals) | Added to alphabetical list |
| PESP `KNOWN_PLATFORMS` missing "Enable Dental", "Ideal Dental Management Partners", "Ideal Dental" | Added (count 98→100) |
| PESP `KNOWN_PE_SPONSORS` missing "Bardo Capital", "Mellon Stud Ventures" | Added (count 52→54) |

### Unit test suite (`scrapers/test_sync_resilience.py`) — 11 tests, all pass

- `TestFullReplaceZeroRowGuard` (3 tests): zero-row abort, below-floor abort, above-floor proceeds
- `TestSignalHandler` (4 tests): SIGTERM/SIGINT set flag, handler registered, sync aborts on shutdown
- `TestPostSyncAssertion` (2 tests): full_replace + watched_zips_only raise on count mismatch
- `TestRunVerifiedResults` (2 tests): verified_results populated in extra dict

### GitHub Actions keep-alive (`.github/workflows/keep-supabase-alive.yml`)

Cron `'0 12 */3 * *'` (every 3 days at 12:00 UTC) hits Supabase `/rest/v1/` as read-only ping to prevent free-tier pause. **REQUIRES USER ACTION**: Add `SUPABASE_URL` + `SUPABASE_ANON_KEY` secrets in GitHub repo settings.

### Known limitations shipped in this round (NOT fixed, documented for future work)

- **GDN "Partners" ambiguity**: `partners/partnered/partnering` are in `_DEAL_VERB_SET` as verbs, so entity names ending in "Partners" (e.g., "Zyphos & Acmera Dental Partners") get truncated to "Zyphos & Acmera Dental". KNOWN_PLATFORMS match catches the common real-world cases (Gen4 Dental Partners, etc.), but a lookahead for "Partners with" vs "Partners <noun>" would improve the fallback. Not urgent because KNOWN_PLATFORMS covers production.
- **Apostrophe normalization**: GDN logs show "Smith's Dental" (U+2019 right single quote) and "Smith's Dental" (U+0027 apostrophe) deduplicating as different entities. Needs a Unicode normalization pass in scraper output.
- **`ada_hpi_benchmarks.updated_at` still NULL**: Freshness UI reads `created_at` as a workaround. Next `ada_hpi_importer.py` run should set both.
- **Mirror scrapers in `dental-pe-nextjs/scrapers/`**: DEPRECATED markers added but the directory is gitignored, so markers are stranded on local disk only. Cron reads from parent `/scrapers/`, so this isn't actively harmful. Recommend a future `rm -rf dental-pe-nextjs/scrapers/` cleanup.

## Skills Available

Use `/scraper-dev` when modifying any scraper. Use `/dashboard-dev` when modifying the Streamlit app OR the Next.js frontend. Use `/data-axle-workflow` for Data Axle export/import tasks. Use `/debug-pipeline` when investigating scraper failures or data issues.
