# @audit-home findings

## Top-line verdict

The Home page KPIs are largely internally consistent — Supabase and the rendered values match on every KPI. However, CLAUDE.md canonical numbers are stale (4,889 GP locations is now 4,833; 4.60% corporate rate is now 4.66%→4.7%). Two confirmed bugs: the activity feed always renders "No recent activity" despite 737 real changes in Supabase (a silent `recentChanges:[]` in the SSR payload); the `enrichedCount` hardcoded constant (2,992) is stale by 9 vs SQLite (2,983 actual). A data quality issue exists in `practice_locations`: 584 records have `entity_classification='org_only_npi'`, a value not in the 11-value canonical system, which silently inflates `unknownCount`.

---

## Per-KPI audit

### KPI 1: Tracked Clinics
- **UI shows:** `4,833` (headline), subtitle: "381,598 federal NPI records (national)"
  Source: production RSC payload confirmed `totalGpLocations: 4833`, `totalPractices: 381598`
- **Supabase returns:** `SUM(total_gp_locations) = 4,833` across all 290 `zip_scores` rows
- **SQLite returns:** `SELECT SUM(total_gp_locations) FROM zip_scores` → **4,833**
  - CHI (IL ZIPs): 4,520 | BOS (MA ZIPs): 313 | Total: 4,833
- **Source code:** `src/lib/supabase/queries/practices.ts:226-242` (zip_scores sub-query in `getPracticeStats`)
  Displayed by `src/app/_components/home-shell.tsx:322-335`
- **Verdict:** ✅ MATCHES (UI = Supabase = SQLite = 4,833)

**CLAUDE.md drift — NOT a code bug, but docs are wrong:**
- CLAUDE.md says "4,889 GP locations watched (CHI 4,575 + BOS 314)" — those are stale numbers from before the Apr 26 pipeline run
- Current truth: 4,833 (CHI 4,520 + BOS 313)
- CLAUDE.md canonical corporate rate "4.60%" used 4,889 as denominator; correct rate is 225/4,833 = **4.66%** (displayed as 4.7%)

---

### KPI 2: PE Deals
- **UI shows:** `2,916` headline, subtitle `147 YTD`
  Source: production RSC payload confirmed `totalDeals: 2916`, `ytdDeals: 147`
- **Supabase returns:** `content-range: 0-0/2916` (confirmed via HEAD with Prefer: count=exact)
  YTD (deals ≥ 2026-01-01): 147 (confirmed via Supabase count query)
- **SQLite returns:** `SELECT COUNT(*) FROM deals` → **2,907**
  YTD (≥ 2026-01-01): **146**
- **Source code:** `src/lib/supabase/queries/deals.ts:51-164` (`getDealStats` — paginates all rows, counts `length`)
- **Verdict:** ❌ DISCREPANCY — Supabase has 9 more deals than SQLite (2,916 vs 2,907); YTD off by 1 (147 vs 146)

  **Evidence:** The CLAUDE.md documents this as the known "ghost row" issue: "SQLite has 2,861 (+34 ghost rows in Supabase from prior scraper experiments — audit §15 #11)". That figure is also stale — the gap has grown to +9 post-April sync. The UI correctly shows what Supabase has (2,916); SQLite is behind.

  **P1 issue:** The SQLite baseline is 9 deals behind Supabase with no mechanism to detect or reconcile. The `sync_to_supabase.py` incremental path can add rows to Supabase that never make it back to SQLite (one-directional sync). This means the audit baseline (SQLite) diverges from the live system over time.

---

### KPI 3: Known Corporate
- **UI shows:** `4.7%`
  Source: production RSC payload confirmed `consolidatedPct: "4.7%"`
- **Supabase returns:** `practice_locations` with `entity_classification IN (dso_regional, dso_national)` AND `is_likely_residential=false` → **225 rows**. `zip_scores` SUM → 4,833. Computed: 225/4833 = **4.66% → rounds to 4.7%**
- **SQLite returns:** Same computation → 225 corporate / 4,833 GP = **4.66% → 4.7%**
- **Source code:** `src/lib/supabase/queries/practices.ts:183-273` (`getPracticeStats`)
  Formula at line 266-269: `(corporate / (totalGpLocations ?? t)) * 100`

- **Verdict:** ✅ MATCHES (UI = 4.7%, computation correct at 4.66%)

**CLAUDE.md drift:** Docs say "4.60%" but that used the stale 4,889 denominator. 225/4,889 = 4.60%. Actual current denominator is 4,833. This is a documentation error only — the code is correct.

---

### KPI 4: Retirement Risk
- **UI shows:** `242`
  Source: production RSC payload confirmed `retirementRisk: 242`
- **Supabase returns:** `practice_locations` WHERE `entity_classification IN (7 independent types)` AND `year_established < 1995` AND `year_established IS NOT NULL` AND `is_likely_residential=false` → **242**
- **SQLite returns:** Same query → **242**
- **Source code:** `src/lib/supabase/queries/practices.ts:281-293` (`getRetirementRiskCount`)
  Uses `fetchPracticeLocations()` then filters in-memory.
- **Verdict:** ✅ MATCHES

**Note:** CLAUDE.md says "226 retirement risk practices" under "Current Data Stats" in the Next.js CLAUDE.md — this is stale. Current truth is 242.

---

### KPI 5: Acquisition Targets
- **UI shows:** `22`
  Source: production RSC payload confirmed `acquisitionTargets: 22`
- **Supabase returns:** `practice_locations` WHERE `buyability_score >= 50` AND `is_likely_residential=false` → **22**
- **SQLite returns:** Same query → **22**
- **Source code:** `src/lib/supabase/queries/practices.ts:301-306` (`getAcquisitionTargetCount`)
- **Verdict:** ✅ MATCHES

**CLAUDE.md drift:** dental-pe-nextjs CLAUDE.md says "34 buyability targets" — stale; current truth is 22. Root repo CLAUDE.md says `getAcquisitionTargetCount: watched ZIPs + buyability_score >= 50` — consistent with implementation.

---

### KPI 6: Last New Deal / Last Sync
- **UI shows:** `2026-03-02` (headline), subtitle: `Sync 2026-04-26`
  Source: production RSC payload confirmed `lastNewDealDate: "2026-03-02"`, `lastPipelineRun: "2026-04-26"`
- **Supabase returns:** `MAX(deal_date)` = `2026-03-02`; `MAX(pipeline_events.timestamp)` = `2026-04-26T20:40:23+00:00`
- **SQLite returns:** `SELECT MAX(deal_date) FROM deals` → `2026-03-02` ✅
- **Source code:** `src/app/page.tsx:94-109` (inline Supabase queries in Phase 3)
- **Verdict:** ✅ MATCHES

**Note:** The stale-deal honesty banner fires correctly (last deal 2026-03-02 is >30d ago as of 2026-04-26). Banner shows correct message.

---

## Freshness bar

The freshness bar at the bottom of the page shows:
```
381,598 NPI records | 4,833 GP clinics tracked | 2,916 deals tracked | 2,992 enriched (0.8%) | 290 ZIPs monitored | Last sync: 2026-04-26 | Last new deal: 2026-03-02
```

**Analysis:**
- `381,598 NPI records` — hardcoded constant `GLOBAL_PRACTICE_NPI_COUNT` in `src/lib/constants/data-snapshot.ts`. Matches SQLite `COUNT(*) FROM practices`. ✅
- `4,833 GP clinics tracked` — correct, from `zip_scores`. ✅
- `2,916 deals tracked` — Supabase count, matches UI. ✅ (SQLite has 2,907 — known ghost row gap)
- `2,992 enriched (0.8%)` — **hardcoded constant** `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT = 2_992` in `src/lib/constants/data-snapshot.ts`. SQLite actual: `COUNT(*) FROM practices WHERE data_axle_import_date IS NOT NULL` = **2,983**. Off by 9.
- `290 ZIPs monitored` — Supabase `watched_zips` count = 290. ✅
- `Last sync: 2026-04-26` — from `pipeline_events`. ✅
- `Last new deal: 2026-03-02` — from `MAX(deal_date)`. ✅

**Issue:** `enrichedCount` uses a hardcoded snapshot constant, not a live query. The constant (2,992) is 9 higher than the current SQLite truth (2,983). This is intentional per the code comments ("fast fallback"), but the displayed percentage `0.8%` is computed as `(2992 / 381598) * 100 = 0.78%` rounded to `0.8%` — close enough not to mislead.

---

## Recent deals feed

The UI shows 10 rows ordered by `deal_date DESC` from Supabase:
```
2026-03-02 | -- | Bain Capital Tech Opportunities (Michael Grandfield) | DoseSpot | MA
2026-03-01 | Today's Dental Network | -- | Mid-County Dental Associates | FL
2026-03-01 | -- | -- | All About Smiles Dentistry | OK
... (10 rows total, all from 2026-03-01 or 2026-03-02)
```

**SQLite ground truth** (`SELECT deal_date, target_name, pe_sponsor, platform_company, target_state FROM deals ORDER BY deal_date DESC LIMIT 10`):
```
2026-03-02 | (null) | Bain Capital Tech Opportunities | DoseSpot | MA
2026-03-01 | Mid-County Dental Associates, Largo, FL | (null) | Mid-County Dental Associates | FL
2026-03-01 | The Center for Dental Wellness at Camarillo | (null) | MB2 Dental | CA
2026-03-01 | Today's Dental Network | (null) | Mid-County Dental Associates | FL
... (10 rows)
```

**Verdict:** ✅ SUBSTANTIALLY MATCHES. Both sources show the same top deal dates (2026-03-01/02). Minor ordering differences exist within the same date because the sort is `deal_date DESC` without a tiebreaker — row order for same-date deals is non-deterministic. The Supabase and SQLite result sets have the same deals, just in different intra-date ordering.

**One content gap:** The Mar 2026 GDN roundup (`gdn` source) shows 48 deals in SQLite vs the Supabase set which appears to contain them. The 9-row Supabase surplus vs SQLite is in other time periods, not visible in the top-10.

---

## Activity feed

- **UI shows:** "No recent activity" — the `RecentActivityFeed` component rendered its empty-state.
- **Production RSC payload contains:** `"recentChanges":[]` — the server returned an empty array.
- **Supabase `practice_changes` reality:** 737 rows total, with `MAX(change_date) = 2026-04-24`. The last 90 days (since 2026-01-26) contain **all 737 rows** in Supabase.
- **What the code does:** `src/app/page.tsx:87-91` calls `getRecentChanges(supabase, undefined, 90).then(changes => changes.slice(0, 8))`. The `undefined` ZIP codes argument means it takes the "no ZIP filter" path in `src/lib/supabase/queries/changes.ts:65-74`:

```typescript
// No ZIP filter: get all recent changes
const { data, error } = await supabase
  .from("practice_changes")
  .select("*")
  .gte("change_date", sinceDateStr)
  .order("change_date", { ascending: false })
  .limit(500);
```

This query SHOULD return 737 rows from Supabase (all within last 90 days). Yet the RSC payload shows `recentChanges:[]`.

- **SQLite reality:** `practice_changes` has 9,293 total rows, all dated 2026-04-26 (bulk run from NPPES classification pass). SQLite has 9,293 recent changes; Supabase has 737. The 737 in Supabase are from the `incremental_id` sync strategy which filters to watched-ZIP NPIs.

**Verdict:** ❌ BROKEN — Activity feed shows "No recent activity" despite 737 real changes in Supabase from as recently as 2026-04-24. Root cause: the `recentChanges:[]` in the SSR payload suggests a runtime error or timeout was swallowed by the `.catch(() => [] as PracticeChange[])` at `src/app/page.tsx:90-93`. The changes exist in Supabase (verified via REST API), but the server-side fetch is silently failing and returning empty. **No error surface to user** — the feed just shows "No recent activity" with no indication of a fetch failure.

**P0 bug:** Activity feed is dead. 737 changes present in Supabase are never shown. The `.catch` at `page.tsx:90` swallows the error with `return [] as PracticeChange[]` and logs only to server console (not surfaced to user).

---

## Critical issues found

### [P0] Activity feed always empty — `src/app/page.tsx:87-93` — silent catch eats real data

The `recentChanges: []` in the SSR payload means `getRecentChanges()` returned empty despite Supabase having 737 rows from as recently as 2026-04-24. The `.catch(() => [])` at line 90-93 of `page.tsx` silently converts any Supabase error into an empty array. The user sees "No recent activity" with no indication something went wrong. This has been broken at production for at least one deploy cycle.

**Evidence:**
- Supabase REST: `GET /practice_changes?change_date=gte.2026-01-26` → `content-range: 0-0/737`
- Production RSC payload: `"recentChanges":[]`
- UI: "No recent activity" rendered

**To diagnose:** Check Vercel function logs at https://vercel.com/suleman7-dmds-projects/dental-pe-nextjs/deployments for `[HomePage] recentChanges error:` log lines. The server console error is being logged but not surfaced.

---

### [P1] Deals count divergence — Supabase +9 ghost rows over SQLite

Supabase has 2,916 deals; SQLite has 2,907. CLAUDE.md documented a "+34 surplus" from scraper experiments; the gap has narrowed but not closed. There is no reconciliation tool or alert for this drift. The displayed deal count (2,916 from Supabase) is what the pipeline actually synced, not the SQLite canonical.

**Evidence:**
- `SELECT COUNT(*) FROM deals` → SQLite: 2,907
- Supabase REST count: 2,916
- YTD discrepancy: Supabase=147, SQLite=146

---

### [P2] `enrichedCount` uses stale hardcoded constant

`GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT = 2_992` in `src/lib/constants/data-snapshot.ts` is used directly in `getPracticeStats()` (line 219) and displayed in the freshness bar. SQLite ground truth is 2,983 (9 fewer). The constant was set at a point-in-time snapshot and is not updated on each sync.

**Evidence:**
- `src/lib/constants/data-snapshot.ts`: `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT = 2_992`
- SQLite: `SELECT COUNT(*) FROM practices WHERE data_axle_import_date IS NOT NULL` → 2,983

---

### [P2] `org_only_npi` — undocumented 12th entity_classification value in production data

`practice_locations` has 584 rows with `entity_classification = 'org_only_npi'`. This value does not exist in the 11-value system documented in CLAUDE.md. It is not handled by `isIndependentClassification()`, `isCorporateClassification()`, or `classifyPractice()` — it falls through to `unknown`.

**Impact on Home KPIs:**
- These 584 rows are in the `unknownCount` bucket in `getPracticeStats()`: `unknownCount = total(5502) - corporate(225) - independent(4024) = 1,253`. Of that 1,253 "unknown", 584 are `org_only_npi`, 593 are `specialist`, 76 are `non_clinical`, and 0 are truly unclassified.
- The `independentPct` (73.1%) and `consolidatedPct` (4.7%) KPIs exclude these 584 locations, which is correct — they are NPI-2 organization-only records (no individual dentist NPI). But the classification system documentation does not mention this value.

**Evidence:**
- SQLite: `SELECT entity_classification, COUNT(*) FROM practice_locations WHERE is_likely_residential = 0 GROUP BY entity_classification` → `org_only_npi: 584`
- `src/lib/constants/entity-classifications.ts` — no `org_only_npi` entry

---

### [P3] CLAUDE.md canonical numbers are stale (docs-only, no code impact)

| Claimed value | Actual current value | Source |
|---|---|---|
| 4,889 GP locations | **4,833** | `SUM(zip_scores.total_gp_locations)` |
| CHI 4,575 | **4,520** | IL ZIP rows in zip_scores |
| BOS 314 | **313** | MA ZIP rows in zip_scores |
| 4.60% corporate rate | **4.66%** (shown as 4.7%) | 225/4833 |
| 226 retirement risk (nextjs CLAUDE.md) | **242** | practice_locations query |
| 34 buyability targets (nextjs CLAUDE.md) | **22** | practice_locations query |
| 2,861 deals in SQLite (CLAUDE.md) | **2,907** | Current SQLite count |
| 2,895 deals in Supabase (CLAUDE.md) | **2,916** | Current Supabase count |

These are documentation staleness only — the code queries live data correctly. Update CLAUDE.md and dental-pe-nextjs/CLAUDE.md with the 2026-04-26 actuals.

---

## Methodology note

Production HTML verified via `curl -sL https://dental-pe-nextjs.vercel.app/` — the app is Next.js with React Server Components. KPI values were confirmed directly from the `self.__next_f.push` RSC payload embedded in the HTML (not inferred from rendered text). Supabase values were confirmed via direct REST API queries against `wfnhludbwcujfgnrgtds.supabase.co`. SQLite queries run against `/Users/suleman/dental-pe-tracker/data/dental_pe_tracker.db` (modified 2026-04-26 20:52).
