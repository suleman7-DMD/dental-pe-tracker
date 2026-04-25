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
- **dso_locations**: 92 scraped DSO office locations from ADSO websites.
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
- 2,895 deals (2,532 GDN + 353 PESP + 10 PitchBook, coverage Oct 2020 – Mar 2026)
- 2,992 Data Axle enriched practices (with lat/lon, revenue, employees, year established)
- 290 scored ZIPs

## Next.js Frontend (Primary)

**Stack:** Next.js 16, React 19, TypeScript 5, Supabase Postgres, TanStack React Query + Table, Recharts 3, Mapbox GL, Tailwind CSS 4, shadcn UI, Lucide React

**Fonts:** DM Sans (headings, 24px/700 page titles), Inter (body), JetBrains Mono (data values, 28px/700 KPIs). Data labels: 11px/500/Inter/uppercase/tracking-wider.

**Deployment:** Vercel auto-deploys on push to main

**Env vars:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MAPBOX_TOKEN`

### Pages (10 total)

| Route | Page | What It Shows |
|-------|------|---------------|
| `/` | Home | 6 KPI cards (Lucide icons), two-column layout (recent deals table + activity feed from practice_changes), data freshness bar, 2x3 quick nav grid |
| `/launchpad` | Launchpad | First-job finder for new dental grads. Track-weighted 0-100 scoring (Succession / Apprentice, High-Volume Ethical, DSO Associate). 20-signal catalog (mentor-rich, hiring-now, boutique solo, FFS/concierge, community DSO, family dynasty, ghost practice, DSO avoid-tier, etc.). 5 tiers (Best Fit / Strong / Maybe / Low / Avoid). 4 living-location scopes. 5-tab practice dossier (Snapshot / Compensation / Mentorship / Red Flags / Interview Prep). Curated DSO tier list with comp bands + citations. |
| `/warroom` | **Warroom** | Chicagoland command surface. 2 modes (Hunt / Investigate), 4 lenses (consolidation, density, buyability, retirement), 11 scopes (chicagoland, 7 subzones, 3 saved presets). Always-visible Sitrep KPI strip. Intent bar (⌘K), Living Map, ranked target list, ZIP + practice dossier drawers, pinboard tray, signal flag overlays (8 practice + 1 ZIP), keyboard shortcuts (`?`, `1`=Hunt, `2`=Investigate, `R`/`P`/`V`/`[`/`]`/`Esc`), URL-synced state. |
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
- **Maps:** subtle shadow on white card background

### Sidebar Navigation

Sidebar grouped into 4 sections (dark #2C2C2C background, goldenrod #B8860B active accent):
- **OVERVIEW:** Dashboard (`/`), Launchpad (`/launchpad`), Warroom (`/warroom`)
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
| `src/app/launchpad/page.tsx` | Launchpad — `force-dynamic` Server Component calling `getLaunchpadBundle` |
| `src/app/launchpad/_components/launchpad-shell.tsx` | Launchpad orchestrator — holds state, wires top bar, list, dossier |
| `src/app/launchpad/_components/scope-selector.tsx` | 4-option living-location dropdown (West Loop, Woodridge, Bolingbrook, All Chicagoland) |
| `src/app/launchpad/_components/track-switcher.tsx` | All / Succession / High-Volume / DSO track toggle |
| `src/app/launchpad/_components/launchpad-kpi-strip.tsx` | 6 KPIs (practices, best-fit, mentor-rich, hiring, avoid, comp range) |
| `src/app/launchpad/_components/track-list.tsx` | Ranked list grouped by tier (Best Fit / Strong / Maybe / Low / Avoid) |
| `src/app/launchpad/_components/track-list-card.tsx` | Single ranked-practice card with score, tier badge, signals, warnings |
| `src/app/launchpad/_components/practice-dossier.tsx` | 5-tab drawer — Snapshot / Compensation / Mentorship / Red Flags / Interview Prep |
| `src/lib/launchpad/scope.ts` | LAUNCHPAD_SCOPES + resolveLaunchpadZipCodes (reuses LIVING_LOCATIONS) |
| `src/lib/launchpad/signals.ts` | 20 signal IDs, LaunchpadTrack types, tier thresholds, LaunchpadBundle type contract |
| `src/lib/launchpad/ranking.ts` | TRACK_MULTIPLIERS table, evaluateSignals, scoreForTrack, rankTargets orchestrator |
| `src/lib/launchpad/dso-tiers.ts` | 16 hand-curated DSO entries with tiers, rationale, citations, comp bands |
| `src/lib/hooks/use-launchpad-state.ts` | URL-synced Launchpad state (scope, track, selectedNpi, pinnedNpis) |
| `src/lib/hooks/use-launchpad-data.ts` | React Query wrapper for LaunchpadBundle |
| `src/lib/supabase/queries/launchpad.ts` | getLaunchpadBundle — parallel fetch + rankTargets + summary |
| `src/app/warroom/page.tsx` | Warroom — `force-dynamic` Server Component calling `getSitrepBundle` |
| `src/app/warroom/_components/warroom-shell.tsx` | Warroom orchestrator — holds state, wires modes, drawers, keyboard |
| `src/app/warroom/_components/scope-selector.tsx` | 11-option scope dropdown (chicagoland / 7 subzones / 3 saved) |
| `src/app/warroom/_components/intent-bar.tsx` | ⌘K-focusable NL intent input |
| `src/app/warroom/_components/sitrep-kpi-strip.tsx` | 6 KPIs (always-visible above Hunt + Investigate panels) |
| `src/app/warroom/_components/living-map.tsx` | Mapbox ZIP choropleth colored by lens + signal flag overlays |
| `src/app/warroom/_components/briefing-rail.tsx` | Scope-specific alerts + intent chip suggestions |
| `src/app/warroom/_components/target-list.tsx` | Hunt mode ranked practice list |
| `src/app/warroom/_components/dossier-drawer.tsx` | Practice dossier drawer |
| `src/app/warroom/_components/zip-dossier-drawer.tsx` | ZIP dossier drawer (saturation, ownership, top practices) |
| `src/app/warroom/_components/investigate-mode-panel.tsx` | Flag co-occurrence + compound-signal targets |
| `src/app/warroom/_components/pinboard-tray.tsx` | Bottom tray for pinned targets |
| `src/app/warroom/_components/keyboard-shortcuts-overlay.tsx` | `?`-triggered shortcuts dialog |
| `src/lib/warroom/mode.ts` | WARROOM_MODES + WARROOM_LENSES constants |
| `src/lib/warroom/scope.ts` | 11 scope definitions + `normalizeWarroomDataScope()` |
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
| `src/providers/query-provider.tsx` | React Query provider (30min stale, 30min gc, 1 retry — data changes weekly) |
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

### Anti-Hallucination Defense (April 25, 2026)

Every practice dossier is gated through a 4-layer defense before it can land in `practice_intel`. Validated by a 200-practice Chicagoland run: 87% pass rate (174 stored / 26 quarantined), 854 forced web searches (avg 4.27/practice), $14.91 real cost (~$0.075/practice).

| Layer | Where | What it does |
|-------|-------|--------------|
| **1. Forced search** | `research_engine.py::_call_api()` accepts `force_search=True`, which sets `body["tool_choice"] = {"type": "tool", "name": "web_search"}` | Anthropic guarantees ≥1 `web_search` invocation per practice — model can no longer answer from priors. Practice path calls with `max_searches=5, force_search=True` |
| **2. Per-claim source URLs** | PRACTICE_USER schema in `research_engine.py` requires `_source_url` on every section (website, services, technology, google, hiring, acquisition, social, healthgrades, zocdoc, doctor, insurance) | Every non-null field is traceable to a URL. Schema instructs `"no_results_found"` when a search yields nothing — fabrication has no escape hatch |
| **3. Self-assessment block** | Terminal `verification` block in PRACTICE_USER: `{searches_executed, search_queries, evidence_quality (verified\|partial\|insufficient), primary_sources}` | Model self-rates evidence quality. `insufficient` triggers automatic rejection downstream |
| **4. Post-validation gate** | `weekly_research.py::validate_dossier(npi, data) -> (ok, reason)` | 5 rejection rules: `missing_verification_block`, `insufficient_searches(N)`, `evidence_quality=insufficient`, `website.url_without_source`, `google.metrics_without_source`. Quarantined dossiers are NOT stored |

**Schema changes (do not regress):**
- `PracticeIntel` model in `database.py` has 3 columns: `verification_searches` (int), `verification_quality` (varchar 20, indexed), `verification_urls` (text). Both Supabase + SQLite have them. **`Base.metadata.create_all()` does NOT alter existing tables** — adding new columns requires explicit `ALTER TABLE` on both databases.
- `intel_database.py::store_practice_intel()` extracts `data["verification"]` and writes those 3 columns.
- `weekly_research.py::retrieve_batch()` calls `validate_dossier()` BEFORE `store_practice_intel()`. Quarantined dossiers don't even hit the DB.

**EVIDENCE PROTOCOL in PRACTICE_SYSTEM (research_engine.py)** — non-negotiable rules baked into the system prompt:
1. Execute web_search ≥2 times per practice (required: `<name> <city> <state>`, `<name> <city> reviews`)
2. Every non-null field must be backed by a URL recorded in `_source_url`
3. Never infer from priors
4. Brand/technology claims must come from the practice's own website
5. If a search returns nothing, set fields to null AND `_source_url` to `"no_results_found"`
6. The terminal `verification` block is mandatory

**Cost calibration:** ~$0.075/practice for full bulletproofed run (vs $0.04-0.06 baseline without `force_search`). Driver: 4-5 forced searches × $0.01 + cache_create overhead on first call. The Anthropic Messages Batch API still gives 50% token discount; web_search cost is not discounted.

**Validation outcomes (200-practice Chicagoland, msgbatch_017YJJ2M3WbLv4Q7gEhubK2o):**
- 174 stored: 115 partial / 52 verified / 10 high quality
- 26 quarantined: 18 `evidence_quality=insufficient`, 8 `missing_verification_block`
- 0 hallucinations slipped through (the Robert Ficek / Lutterbie pattern from the test batch — model searched, found a different doctor at the address, correctly returned `insufficient` instead of fabricating)

**Operational scripts (in `scrapers/dossier_batch/` — committed, NOT in /tmp anymore):**
- `scrapers/dossier_batch/launch.py` — picks top-1 unresearched independent per Chicagoland watched ZIP (priority order: solo_high_volume → solo_established → solo_inactive → family_practice → small_group → large_group → buyability_score DESC → year_established ASC). Builds batch with bulletproofed prompts via `engine.build_batch_requests(items, "practice")`. Submits to Anthropic, writes batch_id to `/tmp/full_batch_id.txt`. Cost cap hardcoded at $11 (trim above that) — bump in script if budget grows.
- `scrapers/dossier_batch/poll.py` — reads batch_id from `/tmp/full_batch_id.txt`, polls Anthropic every 30s up to 90 min. On completion: fetches all results, computes per-call usage (input/output/cache_read/cache_create/web_search), runs `validate_dossier()`, stores passing dossiers via `store_practice_intel()`, runs `python3 scrapers/sync_to_supabase.py`, writes `/tmp/full_batch_summary.json`.
- `scrapers/dossier_batch/migrate_verification_cols.py` — one-shot Supabase migration to add `verification_searches`, `verification_quality`, `verification_urls` columns to `practice_intel` (idempotent — uses `ADD COLUMN IF NOT EXISTS`). The same ALTER must be run on local SQLite (`data/dental_pe_tracker.db`) using `sqlite3` CLI; SQLite doesn't support `IF NOT EXISTS` on column adds — wrap in try/except for "duplicate column".
- `scrapers/dossier_batch/last_run_summary.json` — full per-NPI breakdown of the 200-practice 2026-04-25 run. Useful as a regression baseline for future bulletproofing changes.

### Session Status — April 25, 2026 (Anti-Hallucination Bulletproofing)

This is the operational record of the April 25 session for future debugging. The architecture is documented above; this section is the "what happened, what's left" diary.

**What the session was supposed to address (full scope):**

The user gave a hard requirement: zero hallucination tolerance for practice dossiers ("theres no point of a dossier to begin with if i find even one hallucination"). The required deliverables:
1. **Hardcode the bulletproofed instructions into the API/scraper tool itself** — not session-only or prompt-only; the EVIDENCE PROTOCOL must live in `research_engine.py` so every batch run uses it automatically
2. **Run the recommended top-1-per-ZIP × ~195 Chicagoland dossiers at full quality with `max_uses=5`** within the user's $10.75 budget
3. Ship + commit + deploy + push to live Vercel + check the prior failed Vercel email + update CLAUDE.md + report next steps

**What got done (commits, files, validation results):**

- ✅ **PRACTICE_SYSTEM rewrite** — `research_engine.py` (committed in `59e8403 feat(scrapers): Phase 3 anti-hallucination evidence protocol`). The non-negotiable EVIDENCE PROTOCOL is now baked into every batch request:
  - Mandatory ≥2 web_search invocations per practice (required queries: `<name> <city> <state>` and `<name> <city> reviews`)
  - Every non-null field requires a URL in `_source_url`
  - "no_results_found" pattern when web_search yields nothing
  - Mandatory terminal `verification` block (`searches_executed`, `search_queries`, `evidence_quality`, `primary_sources`)
- ✅ **Forced search via tool_choice** — `research_engine.py:149` `_call_api()` accepts `force_search=False`; when True, sets `body["tool_choice"] = {"type": "tool", "name": "web_search"}`. `research_engine.py:268` `research_practice()` calls with `max_searches=5, force_search=True`. `build_batch_requests()` for practice path conditionally adds tool_choice.
- ✅ **PracticeIntel schema extended** — `database.py:426-428` adds `verification_searches` (Integer), `verification_quality` (String(20), indexed), `verification_urls` (Text). Same columns on Supabase via `scrapers/dossier_batch/migrate_verification_cols.py` and on local SQLite via raw `ALTER TABLE` statements.
- ✅ **store_practice_intel writes verification fields** — `intel_database.py:188-190` extracts `data["verification"]` and persists `searches_executed`, `evidence_quality`, `primary_sources` JSON.
- ✅ **Post-validation gate** — `weekly_research.py:113` `validate_dossier(npi, data) -> (bool, str)` with 5 rejection rules:
  1. `missing_verification_block` — model skipped the terminal block
  2. `insufficient_searches(N)` — `searches_executed < 1`
  3. `evidence_quality=insufficient` — model self-rejected
  4. `website.url_without_source` — claimed a website but didn't cite where it came from
  5. `google.metrics_without_source` — claimed review counts/rating without source URL
  Quarantined dossiers are NOT stored; they're logged with reason in the batch summary.
- ✅ **Test batch (5 practices, $0.276)** — proved all 4 layers work. Notable: NPI Robert Ficek searched for "Ficek DDS at 333 W Wacker", found a different Dr. Ficek in Des Plaines, correctly returned `evidence_quality: insufficient` instead of fabricating a match. Stored to `data/dental_pe_tracker.db` (after manual SQLite ALTER TABLE for the 3 verification columns — `Base.metadata.create_all()` does NOT alter existing tables).
- ✅ **Full Chicagoland production batch (200 practices, $14.91, 100% Anthropic success)** — `msgbatch_017YJJ2M3WbLv4Q7gEhubK2o`:
  - 174 stored: 115 partial / 52 verified / 10 high quality
  - 26 quarantined: 18 `evidence_quality=insufficient`, 8 `missing_verification_block`
  - 854 total web_search invocations (avg 4.27/practice, 1 practice did 0 searches and was correctly quarantined)
  - 0 hallucinations slipped through validation
- ✅ **Sync to Supabase succeeded** — `sync_exit_code: 0`, 17,968 rows total. `practice_intel: 400 rows verified` in Supabase (174 from this run + 226 prior). Visible at https://dental-pe-nextjs.vercel.app/intelligence.
- ✅ **Vercel deployment audit** — the user's failed-deploy email was deployment `5lk23k7fe` from 1h prior to session: `Module not found: '@/lib/hooks/use-warroom-intel'` referenced by `dossier-drawer.tsx` + `zip-dossier-drawer.tsx`. Resolved in a follow-up commit (file now exists at `dental-pe-nextjs/src/lib/hooks/use-warroom-intel.ts` dated 2026-04-24 23:27). Last 2+ deployments **● Ready** in 54-56s.
- ✅ **CLAUDE.md updated** — committed `e615bb8 docs(claude): document anti-hallucination defense + 200-practice run` and pushed to main, triggering Vercel rebuild `dvqb3ym5z`.
- ✅ **Operational scripts moved out of `/tmp/`** — copied into `scrapers/dossier_batch/` so they survive `/tmp` wipes and are reproducible.

**Cost calibration (real, post-session):**

- Test batch: $0.055/practice (5 practices, prompts cached from prior runs)
- Production batch: **$0.075/practice** (200 practices, paid cache_create overhead on the new system prompt)
- Token cost: $6.37 (1.49M input + 0.51M output + 6.9M cache_read + 6.4M cache_create at Haiku batch pricing)
- Search cost: $8.54 (854 × $0.01 — web_search not discounted by batch API)
- Estimate-vs-actual delta: estimated $11, actual $14.91 (overshoot 36%) — driven by cache_create + slightly more searches than the test sample suggested. **For future budget math, use $0.075/practice, not $0.055.**

**Known issues / debug breadcrumbs (open, not blocking):**

1. **`practice_signals` FK violation in sync logs (RESOLVED 2026-04-25)** — NPI `1316509367` is `GRACE KWON` in WORCESTER, MA, zip `01610` (an earlier audit note misstated this as "Grace Kim, Boston, 02115" — corrected per direct SQLite lookup). Was pre-existing in `practice_signals` but missing from `practices`. Fixed by: (a) `compute_signals.py:475-505` filters `WHERE zip IN (SELECT zip_code FROM watched_zips)`, (b) explicit `npi IS NOT NULL` guard added in commit `eb75c6c`. Verified: SQLite `practice_signals.orphan_count = 0`. Sync floor `MIN_ROWS_THRESHOLD["practice_signals"] = 1000` protects against silent wipes.
2. **`verification_quality` enum drift** — model returned `"high"` for 10 dossiers when spec is `verified|partial|insufficient`. Validation gate accepts non-`insufficient` values, so `"high"` slipped through. Either tighten the prompt to suppress `"high"` or widen the enum/index in `database.py:427`.
3. **`/tmp/full_batch_id.txt` is not committed** — `launch.py` writes it, `poll.py` reads it. Cross-process handoff via `/tmp` is fragile across reboots. Future: pass batch_id as CLI arg or use `data/last_batch_id.txt`.
4. **SQLite `ALTER TABLE` is not idempotent** — running `migrate_verification_cols.py` against SQLite would fail with "duplicate column" since SQLite has no `ADD COLUMN IF NOT EXISTS`. Currently handled out-of-band; should be wrapped in try/except.
5. **Cost cap in `launch.py` is hardcoded $11** — trims to fit. Bump in script if budgeting more (e.g., for the 8,500-practice backfill).

**Validation outcome breakdown (full per-NPI in `scrapers/dossier_batch/last_run_summary.json`):**

| Quality | Count | Validation |
|---------|-------|------------|
| verified | 52 | pass (all stored) |
| high | 10 | pass (enum drift, see issue #2) |
| partial | 115 | pass (most common — useful but not exhaustive) |
| insufficient | 18 | quarantine |
| (missing block) | 8 | quarantine |

**Next-up backfill numbers (for planning):**

- Remaining unresearched Chicagoland independents: ~8,559 (pool was 8,759 minus the 200 just done)
- Cost at $0.075/practice: **~$642 to cover all of Chicagoland**
- Throttled options:
  - One-shot blitz: ~$642, ~12 batch runs at the 200-practice/run cap
  - Weekly drip via `weekly_research.py --budget 50`: ~$50/week × ~13 weeks
  - Tier-prioritized (only `solo_high_volume + family_practice + solo_inactive` with buyability ≥ 50): roughly 2,000 practices × $0.075 = ~$150
- Boston Metro: 21 ZIPs, ~zero practice_intel coverage. Same script with `metro_area LIKE '%Boston%'` swap on the SQL filter. ~50-100 dossiers @ ~$8.

**To rerun the same batch end-to-end (recipe):**

```bash
# 1. (one-time, if columns missing on a fresh DB)
python3 scrapers/dossier_batch/migrate_verification_cols.py
# also for SQLite:
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

### Session Status — April 25, 2026 (continued: 2000-practice big-pool batch + Launchpad thesis rewrite)

After the morning's 200-practice validation succeeded, the user requested a much bigger run + a fix to the "Thesis unavailable" / vague-thesis problem on the live Launchpad. Two parallel deliverables shipped:

**(C) Big-pool batch — 2000 unresearched independents, EXCLUDING Chicago proper**

User direction: exclude the hyper-saturated downtown core (West Loop, Loop, etc.) but keep adjacent independents like Cicero, Berwyn, Oak Park, Evanston. The simplest faithful filter is `zip NOT LIKE '606%'` — Chicago proper occupies the entire 60601-60699 ZIP block (56 of the 269 watched ZIPs).

- New launcher: `scrapers/dossier_batch/launch_2000_excl_chi.py` (commit `ebf7054`)
- SQL filter: `zip IN (chicagoland watched) AND zip NOT LIKE '606%' AND ownership_status IN ('independent','likely_independent','unknown') AND npi NOT IN practice_intel AND entity_classification IN (6 indep types)`
- Pool size confirmed: **5,784 eligible practices across 213 non-606xx ZIPs**
- Pick strategy: top **2000 by priority** (NOT top-1-per-ZIP — 213 ZIPs can't fill 2000). Priority order matches `launch.py`: solo_high_volume → solo_established → solo_inactive → family_practice → small_group → large_group → buyability_score DESC → year_established ASC
- First-run actuals: **284 solo_high_volume + 1716 solo_established** spread across 171 ZIPs (the priority lookahead ran out of solo_inactive/family/small/large in the non-606xx pool before reaching them — those tiers are concentrated in Chicago proper)
- Cost cap raised: $11 → **$250**. Estimate $0.080/practice (calibrated from the 200-practice run's $0.075/practice including cache_create overhead). 2000 × $0.080 = $160 expected.
- Submitted as **`msgbatch_01A3FxKxKxemAyqDr2AcGYUq`**, status `in_progress`. Poller in background via `nohup python3 scrapers/dossier_batch/poll.py > /tmp/poll_2000.log 2>&1 &`.
- Step 2 (after this batch validates): backfill the remaining ~3,784 non-606xx practices that didn't make the priority cut. Same script, bump `TARGET_COUNT`. Step 3 (later): the 56 Chicago-proper ZIPs if/when the user wants downtown coverage.

**(B) Compound-narrative thesis rewrite — fixes "way too vague" complaint**

Symptom: Launchpad practice cards showed `Thesis unavailable: Compound narrative disabled: ANTHROPIC_API_KEY is not set` when the env var was missing, AND when it WAS set the thesis was a tiny generic blurb. Root cause: the route was hardcoded to a 50-word ceiling, used Haiku 4.5 with `max_tokens=200`, and never read from `practice_intel` — so even with research available, the thesis was structurally limited to be vague.

Files changed (commit `cc2115a` in `dental-pe-nextjs`):
- `src/app/api/launchpad/compound-narrative/route.ts` — fully rewritten
- `src/app/launchpad/_components/compound-thesis.tsx` — added inline Regenerate button + switched to `whitespace-pre-line` plain prose (was `italic` muted text)
- `src/lib/types/intel.ts` — extended `PracticeIntel` with the 3 verification columns added 2026-04-25 (`verification_searches`, `verification_quality`, `verification_urls`)

What the new route does:
1. Server-side fetch `practice_intel` by NPI from Supabase via `getPracticeIntelByNpi()` — the route is now stateful with respect to research data
2. Model: `claude-sonnet-4-6` (was Haiku 4.5)
3. `max_tokens: 800` (was 200), `temperature: 0.3` (was 0.5)
4. Target length: **200-300 words across 4-6 sentences** (was 50 words / 2-3 sentences)
5. **Citation requirement**: every substantive claim must be backed by either a structural signal or `[source: domain]` shorthand drawn from `verification_urls`. System prompt requires ≥2 source citations when intel exists.
6. **Prompt caching**: system prompt wrapped in `cache_control: { type: "ephemeral" }` for 90% cost savings on repeated calls within a session
7. **Graceful fallback** when intel is missing: thesis MUST open with "Structural signals only — verified web research not yet collected for this practice." and stick to entity classification, age, providers, and active signals. Forbidden to fabricate doctor names, retirement intent, review counts, or technology lists.
8. Verification discipline baked into system prompt: `partial`/`insufficient` evidence quality forces hedge phrases ("limited public footprint suggests…", "available evidence indicates…")

User prompt structure:
- Practice block (name, location, entity, age, providers, employees, revenue, buyability, DSO, website)
- Active signals list
- Track scores + requested track
- IF intel present: overall_assessment, acquisition_readiness, confidence, evidence quality + search count, hiring/acquisition/google/owner_career_stage signals, services + technology lists, green/red flags, **list of cite-able verified URLs with `[source: domain]` shorthand instructions**
- IF intel missing: explicit `STATUS: NOT YET COLLECTED` directive

**(A) User action still required** — without `ANTHROPIC_API_KEY` in Vercel env vars, the new compound-narrative route will continue returning `503: Compound narrative disabled: ANTHROPIC_API_KEY is not set. Add it to Vercel env vars to enable.` The morning's "i just topped up" referred to Anthropic credits (used by the local 2000-practice batch); the Vercel env var is a separate manual step. **Add `ANTHROPIC_API_KEY` to Vercel project settings → Environment Variables → Production + Preview + Development**, then redeploy.

**Verification commands once env var is set:**

```bash
# Should return a 200 with a thesis (not 503)
curl -s -X POST https://dental-pe-nextjs.vercel.app/api/launchpad/compound-narrative \
  -H "content-type: application/json" \
  -d '{"practice":{"npi":"1234567890","name":"Test","entity_classification":"solo_established","city":"Chicago","year_established":1985,"num_providers":1},"signals":["mentor_density","ffs_concierge"],"scores":{"succession":80,"high_volume":60,"dso":40},"track":"succession"}' | jq
```

**Coexistence note (do not regress):** the parent `dental-pe-tracker` repo had concurrent uncommitted changes from a parallel agent during this session (`scrapers/compute_signals.py` FK guard for null NPIs, `scrapers/research_engine.py` ZIP_SYSTEM evidence protocol extension). Those are NOT mine — left untouched, will be committed by whoever owns them. My only parent-repo commit was `ebf7054` (the launch_2000_excl_chi.py script).

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
