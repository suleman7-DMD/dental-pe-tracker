# @playwright-setup findings

## Setup status
- @playwright/test installed: yes (version 1.59.1)
- chromium installed: yes (Chrome Headless Shell 147.0.7727.15 / playwright chromium-headless-shell v1217)
- Script location: `/Users/suleman/dental-pe-tracker/audit_2026_04_26/playwright/screenshot-all.mjs`
  - Mirror in: `/Users/suleman/dental-pe-tracker/dental-pe-nextjs/playwright/screenshot-all.mjs` (required for node_modules resolution)
- Note: script must be run via `node playwright/screenshot-all.mjs` from inside `dental-pe-nextjs/` — running it directly from the audit dir fails with ERR_MODULE_NOT_FOUND because `@playwright/test` is installed locally in that package.

## Per-route capture results

| Route | HTTP status | Page title | File | Notes |
|---|---|---|---|---|
| / | 200 | Dental PE Intelligence Platform | home.png | Renders fully |
| /launchpad | 200 | Launchpad \| Dental PE Intelligence | launchpad.png | Renders fully |
| /warroom | 200 | Warroom \| Dental PE Intelligence | warroom.png | Renders with pipeline warnings |
| /deal-flow | 200 | Deal Flow \| Dental PE Intelligence | deal-flow.png | Renders fully |
| /market-intel | 200 | Market Intelligence \| Dental PE Intelligence | market-intel.png | Renders fully |
| /buyability | 200 | Buyability Scanner \| Dental PE Intelligence | buyability.png | Renders fully |
| /job-market | 200 | Job Market Intelligence \| Dental PE Intelligence | job-market.png | Renders fully |
| /research | 200 | Research Tools \| Dental PE Intelligence | research.png | Renders — defaulted to "(undisclosed)" PE sponsor |
| /intelligence | 200 | Intelligence \| Dental PE Intelligence | intelligence.png | Renders — raw `<cite>` HTML tags visible in ZIP intel cells |
| /system | 200 | System Health \| Dental PE Intelligence | system.png | Renders — ADA HPI flagged Outdated; GDN 57d stale; PESP 208d stale |
| /data-breakdown | 200 | Data Breakdown \| Dental PE Intelligence | data-breakdown.png | Renders fully |

All 11 screenshots saved to: `/Users/suleman/dental-pe-tracker/audit_2026_04_26/screenshots/baseline/`

File sizes ranged 67K–166K (no zero-byte files; all contain real pixel data).

## Visual spot-check

### Home (`home.png`)
Sidebar renders with 4 grouped sections (OVERVIEW / MARKETS / ANALYSIS / ADMIN) and all 11 nav items. Six KPI cards visible: Tracked Clinics **4,833** / PE Deals **2,916** (147 YTD) / Known Corporate **4.7%** / Retirement Risk **242** / Acquisition Targets **22** / Last New Deal **2026-03-02**. Freshness banner present: "Last new deal: 2026-03-02 (55d ago) — Pipeline syncs are running normally." Recent Deals table populated with real rows. Warm light design system (bg #FAFAF7, goldenrod sidebar active state) confirmed correct. Activity feed panel on right is blank in the viewport (likely lazy / requires scroll).

### Warroom (`warroom.png`)
Chicagoland Warroom renders with Hunt/Investigate mode toggle, scope selector (All Chicagoland 269 ZIPs), lens (Consolidation), ⌘K intent bar, and preset buttons (SW succession plays / Stealth DSO scan / Family dynasties / Solo dentists near retirement). **PIPELINE NOTES banner is showing three warnings:** "Summary unavailable: canceling statement due to statement timeout", "Recent changes unavailable: canceling statement due to statement timeout", "Signal layer skipped on first paint." All 12 KPI tiles render but show 0 / dashes (consistent with the timeout warnings — data did not load before screenshot). This is a P1 issue: the Sitrep KPI strip is producing statement timeouts and returning empty data.

### Launchpad (`launchpad.png`)
Renders fully. KPIs visible: GP Clinics in Scope **4,520** (5,103 NPI rows) / Best-Fit Candidates **0** / Mentor-Rich **137** / Hiring Now **0** / Avoid-Tier DSOs **34** / Evidence Coverage **0/60**. Track selector (ALL / Succession / High-Volume / DSO), Living Location (All Chicagoland 269 ZIPs), Smart Briefing, and Reset controls all present. Ranked practices list showing 60 total — top entry is Lang Dental (CHICAGO IL 60652, score 70 STRONG FIT). Red flag patterns banner shows 2 active warnings.

### Deal Flow (`deal-flow.png`)
Renders fully. Header: 2,916 deals | 3 sources | Filtered view. KEY METRICS: Total Deals **2,916** / Active PE Sponsors **104** / Active Platforms **490** / Deals YTD **105**. YoY deltas visible (all negative). Overview tab active; Deal Volume Over Time bar chart rendering. Last source check: 2026-04-27.

### Market Intel (`market-intel.png`)
Renders fully. Header: 381,598 practices tracked / 2,992 Data Axle enriched / Updated Today. KPIs: Tracked Clinics **4,833** (5,502 NPI rows) / Known Corporate **2.0%** (189) / Independent (of total) **73.1%** / Specialist + Other **22.8%**. Shared-phone signal row shows 4.1% (225). Consolidation tab active; DSO Penetration by ZIP table loading (60418 Crestwood 66.7%, 60416 Coal City 50.0% at top). Cross-link to Warroom present.

### Buyability (`buyability.png`)
Renders fully. Four category KPIs: Acquisition Targets **409** / Dead Ends **74** / Job Targets **419** / Specialists **98**. Practice Analysis table (1000 rows) visible with practice name, address, city, ZIP, status badge, classification, score, confidence stars, year est. Top entries: Lang Dental score 100, multiple UNAVAIL entries at 85. ZIP filter and All Categories dropdown present. CSV export button visible.

### Job Market (`job-market.png`)
Renders fully. Header: 381,598 practices tracked / 2,992 enriched (0.8%) / Updated Today. Living Area selector defaulted to "West Loop / South Loop (142 ZIPs)". KPIs: Tracked Clinics **2,943** (5,103 NPI rows) / Independent % **73.5%** / High-Confidence Corporate **4.0%** / Avg Buyability **--** / 10+ Staff **543** / Retirement Risk **242**. Secondary metrics: Avg Dental Density **8.9/10k** / Buyable Practice % **53%** / High-Volume Solos **589**. Saturation Analysis table rendering with Boston-area ZIPs. Overview / Map / Directory / Analytics tabs present.

### Research (`research.png`)
Renders. Defaulted to "(undisclosed)" PE sponsor — expected first-load behavior (no sponsor pre-selected). PE Sponsor Profile tab active; shows 2 total deals and a Deal Timeline scatter chart with 2 dots. Platform Profile / State Deep Dive / SQL Explorer tabs all present in nav.

### Intelligence (`intelligence.png`)
Renders. KPIs: Zips Researched **3/290** / ZIP Coverage **1.0%** / Practices Researched **3370** / High Readiness **0** / Total Research Cost **$0.19** / Avg Confidence **High**. ZIP Market Intelligence table shows 3 rows (60004, 60515, 60606). **P1 issue: raw `<cite index="...">` HTML tags are bleeding through into the Demand and Investment Thesis cells** (e.g. `<cite index="3-9">Arlington Heights appreciation rates 5.84%...`). These are unrendered citation markup strings from the AI qualitative layer — they should be stripped or rendered as superscripts, not displayed raw.

### System (`system.png`)
Renders fully. Data Source Coverage table shows 7 sources. Green/Current: nppes (5,094 records), data_axle (451), manual (7), Global NPI pool (381,598), Data Axle enriched NPIs (2,992), ADSO Scraper (249). **Red/Outdated: ADA HPI (918 records, last updated 2026-03-07)**. Deal Source Freshness section: GDN shows **57d since last deal** (amber), PESP shows **208d since last deal** (red). Data Freshness Timestamps show NPPES/ADSO synced 2026-04-26; ADA Benchmarks last at 2026-03-07.

### Data Breakdown (`data-breakdown.png`)
Renders fully. Header KPIs: 7 Blocks / 290 Watched ZIPs / 0 Drift Alerts. All Practices (Global Snapshot): **381,598** NPI rows — Reconciled. Watched-ZIP GP Clinic Locations (deduped): **5,502** clinic locations — Reconciled. Watched ZIPs by State: **290** — Reconciled. Deals by Source: **2,916** — Reconciled. Category filter tabs (All / Practices / Deals / ZIPs / Intelligence) and Expand all control present.

## Critical issues

- **[P1] /warroom — Sitrep KPI strip statement timeouts**: Three PIPELINE NOTES warnings visible: "Summary unavailable: canceling statement due to statement timeout", "Recent changes unavailable: canceling statement due to statement timeout", "Signal layer skipped on first paint." All 12 Sitrep KPI tiles render as 0/dashes. This is the Warroom's primary value proposition and it is returning empty data on load.

- **[P1] /intelligence — Raw `<cite>` HTML tags rendered as plain text**: ZIP intel cells in the ZIP Market Intelligence table display unstripped `<cite index="N-M">` markup literally. Affects Demand, Supply, and Investment Thesis columns. Evidence of a missing HTML sanitization or citation-stripping step between AI output storage and frontend rendering.

- **[P1] /system — PESP deal freshness 208 days stale**: PESP last deal ingested was ~208 days ago. GDN is 57 days stale. Both are red/amber. Upstream sources may have stopped publishing or the scrapers are silently not ingesting new deals. Last new deal across all sources is 2026-03-02 (55 days ago per Home banner).

- **[P1] /system — ADA HPI outdated**: ADA HPI benchmarks last updated 2026-03-07 (~50 days ago). Flagged red in the Data Source Coverage table.

- **[P1] /home — Tracked Clinics KPI shows 4,833, not the expected 4,889 GP locations**: Home KPI card reads "4,833" with subtitle "381,598 federal NPI records (national)". Per CLAUDE.md the canonical headline GP location count should be 4,889 (sum of zip_scores.total_gp_locations). This is a ~56-location discrepancy that warrants investigation — either the KPI source has drifted from zip_scores or the display is pulling a different denominator.

- **[P2] /launchpad — Best-Fit Candidates = 0, Evidence Coverage = 0/60**: No practices scored above the best-fit threshold and zero of 60 ranked targets have source-backed dossiers. This suggests the compound-narrative/practice_intel pipeline has not run for this metro or results are not surfacing. May be expected if batch research hasn't been executed, but worth flagging for the audit team.

- **[P2] /warroom — Activity feed right panel blank**: The right-side activity feed panel on Home appears blank in the 1440×900 viewport. May be a lazy-load / hydration issue that resolves on scroll or interaction, but worth confirming it populates.
