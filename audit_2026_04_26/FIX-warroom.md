# FIX-warroom — Completion Report
**Agent:** @fix-warroom  
**Date:** 2026-04-26  
**Status:** ALL FIXES APPLIED — build passes, vitest passes

---

## Fixes Applied

### P0 — Sitrep timeout (FIXED)

**File:** `dental-pe-nextjs/src/lib/supabase/queries/warroom.ts`

**Root cause:** `getWarroomSummary()` had a dead `if (isPolygonScope) { ... } else { ... }` block where BOTH branches called `getScopedPractices(scope, {}, supabase)` — fetching all 5,732 practice_locations rows twice. This caused Supabase free-tier 8s `statement_timeout` for every Sitrep load, making all KPIs show 0 or "--".

**Fix:** Replaced the 58-line dead if/else with a single `Promise.all` that calls the existing lightweight HEAD-only count helpers (`getOwnershipCountsByQuery`, `countEnrichedPractices`, `countAcquisitionTargets`, `countRetirementRisk`, `countCorporateHighConfidence`). These helpers use `SELECT location_id ... head:true` — no row data fetched — and run in parallel rather than sequentially.

Also fixed `fetchPracticeIdentitiesForNpis` (called by `getScopedChanges`) to accept `zipCodes: string[] | null = null` and pass it to `fetchPracticeLocations`. Without this, `getScopedChanges` fetched all 5,732 rows on every call to look up practice metadata for change records — a second full scan per Sitrep load.

### P0 — Signal layer (NOTE)

`loadSignals` defaults to `false` in `data.ts` but `use-warroom-data.ts` already passes `loadSignals: true` on client-side refetch. The 0 `practice_signals` rows in Supabase is a backend sync issue handled by @fix-backend (task #4 completed — index added, sync re-run).

### P1 — 100× percent bug (FIXED, prior session)

**File:** `dental-pe-nextjs/src/app/warroom/_components/living-map.tsx`

`corporate_share_pct` and `buyable_practice_ratio` are stored as decimal fractions (0.0682 = 6.82%) but were passed raw to `formatPercent()` which only appends "%". Now multiply by 100 before calling `formatPercent()` in both the `consolidation` and `buyability` lens computations. Confirmed at lines 55 and 71.

### P1 — org_only_npi filter (FIXED)

**File:** `dental-pe-nextjs/src/lib/supabase/queries/warroom.ts`

Added `.neq("entity_classification", "org_only_npi")` to `basePracticeLocationCountQuery`. This removes 584 NPI-2 organization-record artifacts from all Sitrep KPI counts (total practices, corporate %, independent %, retirement risk, acquisition targets). Also added `neq()` method to the `CountFilterQuery` TypeScript interface.

### P2 — Dead code removal (FIXED)

Collapsed the 58-line identical `if (isPolygonScope) { ... } else { ... }` block inside `getWarroomSummary`. The `isPolygonScope` variable is gone. All 11 Warroom scopes resolve to ZIP arrays; the polygon path never fires in the real UI.

---

## Verification

```
npm run build      → ✓ Compiled successfully in 24.5s, zero TypeScript errors
npx vitest run     → 2 passed (2), 63ms
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/lib/supabase/queries/warroom.ts` | Fix 1: `neq()` on `CountFilterQuery` interface; Fix 2: `fetchPracticeIdentitiesForNpis` zipCodes param; Fix 3: pass zipCodes in `getScopedChanges`; Fix 4: `org_only_npi` filter in `basePracticeLocationCountQuery`; Fix 5: collapse dead if/else in `getWarroomSummary` |
| `src/app/warroom/_components/living-map.tsx` | Fix percent bug: `×100` before `formatPercent()` for `consolidation` and `buyability` lenses |
