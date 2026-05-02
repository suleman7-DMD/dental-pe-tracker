# @audit-warroom findings

## Top-line verdict

The Warroom Sitrep KPI strip shows ALL ZEROS on every load because `getWarroomSummary()` consistently hits Supabase's statement timeout. The root cause is `getScopedChanges()` performing a full table scan of all 5,732 `practice_locations` rows (with no ZIP filter) on every call, and it is called twice. **Both `practice_signals` and `zip_signals` tables are 0 rows in Supabase**, making every signal overlay, flag badge, investigate-mode panel, and the retirement lens of the Living Map silently broken. Additionally, the consolidation and buyability lens tooltips display values 100× too small (fraction stored as 0.068 rendered as "0.1%" instead of "6.8%"). The "PE Deals in Scope" KPI is permanently 0 because no deals have `target_zip` populated (0 of 2,916 rows).

---

## Sitrep KPI audit

### KPI: Practices in Scope (`ownership.total`)
- **UI shows:** `0` (SSR timeout propagates as empty fallback)
- **Supabase returns:** 5,502 non-residential `practice_locations` (all ZIPs); 5,102 IL (CHI scope)
- **SQLite returns:** 5,502 total non-residential; 5,102 IL
- **Query source:** `src/lib/supabase/queries/warroom.ts:634` `getOwnershipCountsByQuery()` → `countPracticeLocationRows()` — never reached because `getWarroomSummary()` at `:972` calls `getScopedPractices()` (line 1012) which itself calls `fetchPracticeLocations()` and then `getScopedChanges()` (line 1042/1043) which calls `fetchPracticeIdentitiesForNpis()` → full-table `fetchPracticeLocations()` with no zip filter → **statement timeout aborts the whole `getWarroomSummary()` call**
- **Verdict:** ❌ Always 0. P0 timeout bug.

### KPI: Corporate (High-Conf) (`corporateHighConfidence` / `corporateHighConfidencePct`)
- **UI shows:** `0` / `0.0%`
- **Supabase returns:** 225 corporate locations (109 dso_national + 116 dso_regional) out of 5,502 total non-residential = **4.09%** (or ~185 after EIN/parent_company filter for "high-conf")
- **SQLite returns:** 225 (identical to Supabase)
- **Query source:** `src/lib/supabase/queries/warroom.ts:909` `countCorporateHighConfidence()` — never reached (same timeout)
- **Verdict:** ❌ Always 0. P0 timeout bug.

### KPI: Acquisition Ready (`acquisitionTargets`)
- **UI shows:** `0`
- **Supabase returns:** 22 locations with `buyability_score >= 50` (non-residential, all ZIPs)
- **SQLite returns:** 22 (identical)
- **Query source:** `src/lib/supabase/queries/warroom.ts:685` `countAcquisitionTargets()` — never reached (timeout)
- **Verdict:** ❌ Always 0. P0 timeout bug.

### KPI: Retirement Risk (`retirementRisk`)
- **UI shows:** `0`
- **Supabase returns:** 242 independent locations with `year_established < 1995` (IL non-residential)
- **SQLite returns:** 242 (identical)
- **Query source:** `src/lib/supabase/queries/warroom.ts:694` `countRetirementRisk()` — never reached (timeout)
- **Verdict:** ❌ Always 0. P0 timeout bug.

### KPI: PE Deals in Scope (`dealCount`)
- **UI shows:** `0`
- **Supabase returns:** 0 (confirmed — `target_zip` is NULL on all 2,916 deal rows)
- **SQLite returns:** 0 of 2,907 deals have `target_zip` set (0 with ZIP)
- **Query source:** `src/lib/supabase/queries/warroom.ts:714` `countScopedDeals()` — filters `WHERE target_zip IN (scope_zips)` but no deals have target_zip populated
- **Verdict:** ❌ Structurally broken. Not a timeout — the column is simply never populated. Will always show 0 regardless of scope.

### KPI: 90d Change Events (`changeCount90d`)
- **UI shows:** `0`
- **Supabase returns:** 737 practice_changes rows exist (all within last 90d since all are recent)
- **SQLite returns:** 8,848 (practice_changes)
- **Query source:** `src/lib/supabase/queries/warroom.ts:495` `getScopedChanges()` — times out because after fetching 500 changes, it calls `fetchPracticeIdentitiesForNpis()` at line 514 which does `fetchPracticeLocations(supabase, { includeResidential: true })` — full 5,732-row table scan with NO zip filter. This is the primary timeout trigger.
- **Verdict:** ❌ Always 0. P0 timeout bug (timeout trigger).

### KPI: Flagged Practices (`signalCounts.totalFlaggedPractices`)
- **UI shows:** `--` ("Signal sync pending")
- **Supabase returns:** 0 rows in `practice_signals` table
- **SQLite returns:** 13,818 rows; 95 stealth_dso, 206 phantom_inventory, 1334 family_dynasty, 1288 micro_cluster, 195 retirement_combo, 263 last_change_90d, 688 high_peer_retirement, 2763 revenue_default
- **Query source:** `src/lib/supabase/queries/warroom.ts:746` `getScopedPracticeSignals()`
- **Verdict:** ❌ Permanently broken. `practice_signals` has 0 rows in Supabase. `signalCounts` is hardcoded `null` in `getWarroomSummary()` (line 1050: `const signalCounts: WarroomSignalCounts | null = null;`).

### KPI: Stealth Clusters (`signalCounts.stealthDsoClusters`)
- **UI shows:** `--` ("Signal sync pending")
- **Supabase returns:** 0 (no practice_signals rows)
- **SQLite returns:** 95 stealth_dso practices
- **Verdict:** ❌ Permanently broken (same as above).

### KPI: Phantom Inventory (`signalCounts.phantomInventoryPractices`)
- **UI shows:** `--` ("Signal sync pending")
- **Supabase returns:** 0
- **SQLite returns:** 206
- **Verdict:** ❌ Permanently broken.

### KPI: Retirement Combo (`signalCounts.retirementComboHigh`)
- **UI shows:** `--` ("Signal sync pending")
- **Supabase returns:** 0
- **SQLite returns:** 195
- **Verdict:** ❌ Permanently broken.

### KPI: Avg Buyability (`avgBuyabilityScore`)
- **UI shows:** `--` (null from timed-out summary)
- **Expected:** ~computed from buyabilityRows across 5102 IL practice_locations
- **Query source:** `src/lib/supabase/queries/warroom.ts:933` `averageScopedScores()` — also fetches all practice_locations (~5102 rows); called inside the timed-out `getWarroomSummary()`
- **Verdict:** ❌ Always `--`. P0 timeout.

### KPI: Enriched (`enrichedPractices`)
- **UI shows:** `0` / `0.0%`
- **Supabase returns:** 2,870 locations with `data_axle_enriched=true` (all ZIPs, non-residential)
- **SQLite returns:** 2,870 (identical)
- **Verdict:** ❌ Always 0. Timeout.

---

## practice_signals comparison

| Signal | SQLite count | Supabase count | Match? |
|---|---|---|---|
| **Total rows** | 13,818 | **0** | ❌ |
| stealth_dso | 95 | 0 | ❌ |
| phantom_inventory | 206 | 0 | ❌ |
| family_dynasty | 1,334 | 0 | ❌ |
| micro_cluster | 1,288 | 0 | ❌ |
| retirement_combo | 195 | 0 | ❌ |
| last_change_90d | 263 | 0 | ❌ |
| high_peer_retirement | 688 | 0 | ❌ |
| revenue_default | 2,763 | 0 | ❌ |

**All 13,818 rows are in SQLite but 0 are synced to Supabase.** The sync gap is a known item in CLAUDE.md ("zip_signals: 0 Supabase — Repair: `python3 scrapers/sync_to_supabase.py --tables zip_signals`") but `practice_signals` is NOT called out as having a gap in CLAUDE.md — it claims it is synced as part of the `full_replace` strategy for signal tables.

---

## zip_signals comparison

| | SQLite | Supabase |
|---|---|---|
| count | 290 | **0** |
| Verdict | STALE/MISSING | **MISSING** |

The `zip_signals` sync gap is documented in CLAUDE.md. As a result:
- The **retirement lens** in the Living Map shows all grey dots (no data; `retirement_combo_high_count` comes exclusively from `zip_signals`)  
- The Investigate mode's `topSignals.stealthClusters` is always empty (`[]`)  
- The `ada_benchmark_gap_flag` ZIP overlay never fires

---

## Mapbox token
- **Present in .env.local?** Yes
- **Value (first 10 chars):** `pk.eyJ1Ijoic`
- Token format is valid (`pk.` prefix = public token). Map should render structurally.
- **However:** ~50% of ranked target locations lack latitude/longitude (`2,763 of 5,502` non-residential `practice_locations` have `latitude=null`). The map's target-pin layer will silently drop half of ranked practices. Only 2,739/5,502 (49.8%) have coordinates.

---

## Source code red flags

- `src/lib/supabase/queries/warroom.ts:448` — `fetchPracticeLocations(supabase, { includeResidential: true })` inside `fetchPracticeIdentitiesForNpis()` with NO zip filter. This fetches all 5,732 `practice_locations` rows to build an NPI→location map. Called every time `getScopedChanges()` runs. Why concerning: `getScopedChanges()` is called twice (lines 1042, 1043) inside `getWarroomSummary()`. That is two full-table scans of 5,732 rows in one function call — this is the primary Supabase statement timeout trigger.

- `src/lib/supabase/queries/warroom.ts:986-1036` — Dead-code duplication: the `if (isPolygonScope)` and `else` branches of `getWarroomSummary()` contain **identical code**. Both branches call `getScopedPractices(scope, {}, supabase)` and compute the same five counters identically. The `isPolygonScope` path will never be `true` for the default "chicagoland" scope (no polygon).

- `src/lib/supabase/queries/warroom.ts:1050` — `const signalCounts: WarroomSignalCounts | null = null;` — hardcoded `null`. Signal counts are **never computed in `getWarroomSummary()`**. Comment says "Signal tables are optional overlays." But the Sitrep KPI strip's "Flagged Practices", "Stealth Clusters", "Phantom Inventory", and "Retirement Combo" KPIs are driven by `signalCounts`. They will permanently show `--`.

- `src/lib/warroom/data.ts:117` — `const loadSignalLayer = options.loadSignals ?? false;` — and no caller passes `loadSignals: true`. In `use-warroom-data.ts:92-101`, `loadOptions` doesn't include `loadSignals`. So the signal layer is **never loaded**. The `practiceSignals` and `zipSignals` arrays are always `[]` from the client-side fetch, confirming every flag on ranked targets will be empty and all signal KPIs will show `--` or `0`.

- `src/app/warroom/_components/living-map.tsx:53` — Consolidation lens: `format: (value) => formatPercent(value)`. `corporate_share_pct` in `zip_scores` is stored as a decimal fraction (e.g., `0.0682` = 6.82%). `formatPercent(0.0682)` outputs `"0.1%"` when the correct display is `"6.8%"`. The tooltip, legend min/max, and aria-labels all show values 100× too small. Same bug applies to the buyability lens (line 65-66): `buyable_practice_ratio` is also a fraction, but displayed with `formatPercent()`.

- `src/lib/supabase/queries/warroom.ts:714-722` — `countScopedDeals()` scopes by `target_zip IN (scope_zips)`. Zero of 2,916 deals have `target_zip` populated (verified SQLite: `0/2,907` have ZIP). The "PE Deals in Scope" KPI and deal count in `getWarroomSummary()` will always return 0 for any ZIP-scoped query. The actual 59 IL deals are retrievable by `target_state = 'IL'` but the warroom doesn't use that field.

- `src/lib/supabase/queries/warroom.ts:784` — `query.abortSignal(timeoutSignal(1500))` — 1.5-second abort on `practice_signals` chunk queries. For the 269 CHI ZIPs chunked at 50 ZIPs/chunk = 6 chunks × ≤1.5s each = ≤9 seconds. But given `practice_signals` has 0 rows in Supabase, each chunk returns empty immediately. The timeout guard is correct in design but protects a table that doesn't exist.

- `src/lib/supabase/queries/warroom.ts:937` — `averageScopedScores()` calls `fetchPracticeLocations()` without a row limit to compute `avgBuyabilityScore`. It fetches all 5,102 IL non-residential locations just to average one field. Should use a Supabase `avg()` aggregate query instead.

---

## Critical issues

- **[P0] All Sitrep KPIs show 0/-- on every load** — `src/lib/supabase/queries/warroom.ts:441-540` (getScopedChanges / fetchPracticeIdentitiesForNpis) — `fetchPracticeLocations(supabase, { includeResidential: true })` with no ZIP filter fetches all 5,732 rows twice per `getWarroomSummary()` call, triggering Supabase's statement timeout. Evidence: SSR HTML bundle shows `"warnings":["Summary unavailable: canceling statement due to statement timeout","Recent changes unavailable: canceling statement due to statement timeout"]` with all ownership/enrichment/retirement/corporate KPIs = 0.

- **[P0] practice_signals has 0 rows in Supabase** — confirmed via REST API `content-range: */0`. All 8 signal flag overlays are silently absent. All 40 ranked targets have `flagCount: 0` in the SSR bundle. Investigate mode shows "No practices with 2+ overlapping signals in this scope" for every view. Stealth cluster and phantom inventory KPIs permanently show `--`.

- **[P0] zip_signals has 0 rows in Supabase** — confirmed via REST API `content-range: */0`. The retirement lens on the Living Map silently renders all ZIP dots grey (no data). The ADA benchmark gap flag never fires. The `zip_ada_benchmark_gap_flag` filter chip in Hunt mode returns 0 results.

- **[P1] "PE Deals in Scope" KPI is permanently 0** — `target_zip` is NULL on all 2,916 deals in Supabase and all 2,907 deals in SQLite. The scope filter `WHERE target_zip IN (scope_zips)` never matches. Fix requires populating `target_zip` from geocoding `target_city`/`target_state` or switching the scope filter to `target_state`.

- **[P1] Consolidation and buyability lens tooltips/legend are 100× wrong** — `src/app/warroom/_components/living-map.tsx:53,65` — `corporate_share_pct` and `buyable_practice_ratio` are stored as decimal fractions (0.0682 = 6.82%) but displayed via `formatPercent()` which does `.toFixed(1) + "%"`, outputting "0.1%" instead of "6.8%". The color gradient normalizes correctly (relative ranking is preserved), but every label, tooltip, legend endpoint, and aria-label shows values that are 100× too small.

- **[P1] Signal layer is never loaded** — `src/lib/warroom/data.ts:117` — `loadSignals` defaults to `false` and no caller passes `loadSignals: true`. Even if `practice_signals` were synced to Supabase, the client would never fetch them because `useWarroomData()` does not expose `loadSignals`. The warning "Signal layer skipped on first paint" appears in the UI warning box on every load.

- **[P1] ~50% of ranked targets lack coordinates** — 2,763 of 5,502 non-residential `practice_locations` have `latitude=null`. These practices are ranked in Hunt mode but invisible on the Living Map. The map's target-pin geojson layer silently drops them.

- **[P2] `zip_scores.corporate_highconf_count` is NULL for all rows** — confirmed via SSR bundle (all `corporate_highconf_count: null`). The high-confidence corporate count per ZIP is not populated. The ZIP dossier's corporate share breakdown cannot distinguish high-conf from phone-only corporate.

- **[P2] Duplicate code in `getWarroomSummary()`** — `src/lib/supabase/queries/warroom.ts:986-1036` — the `if (isPolygonScope) { ... } else { ... }` branches are 100% identical. The polygon path (`isPolygonScope = true`) would only fire for a polygon-drawn scope, which is not exposed in the Warroom UI. The else-branch is dead for all real usage.

- **[P2] `getScopedChanges()` does not filter by scope ZIPs** — `src/lib/supabase/queries/warroom.ts:503-509` — the practice_changes fetch at line 503 does NOT apply a ZIP filter. It fetches the 500 most recent changes globally (all ZIPs), then tries to resolve them to scope ZIPs via the NPI→location lookup. Any changes for practices outside the scope are filtered at line 527 (`includeMissingPractice = false`). This wastes bandwidth and triggers the full-table-scan that causes the timeout.

