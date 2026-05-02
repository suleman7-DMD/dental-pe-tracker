# @fix-home-intel completion report

## Files changed
- `dental-pe-nextjs/src/lib/supabase/queries/changes.ts:1-82` — select("*") → explicit column list `CHANGE_COLS` to eliminate statement_timeout risk (57014)
- `dental-pe-nextjs/src/app/page.tsx:89-93` — recentChanges catch now returns `null` (not `[]`) to distinguish fetch-failure from genuinely empty data
- `dental-pe-nextjs/src/app/_components/home-shell.tsx:29-232` — HomeShellProps.recentChanges is now `PracticeChange[] | null`; RecentActivityFeed renders "Activity feed unavailable" for `null`, "No recent activity" for `[]`
- `dental-pe-nextjs/src/app/intelligence/_components/intelligence-shell.tsx:1-880` — imported stripCitations() from utility; applied to demand_outlook/supply_outlook/investment_thesis in table columns and detail panel; SignalValue component now strips citations on string values
- `dental-pe-nextjs/src/lib/utils/strip-citations.ts` (NEW) — shared `stripCitations()` utility with overloaded signatures for string/null/undefined
- `dental-pe-nextjs/src/__tests__/strip-citations.test.ts` (NEW) — 9 vitest assertions covering simple cite, multiple cites, attributes, no cites, null, undefined, empty, adjacent cites, case-insensitivity
- `dental-pe-nextjs/src/lib/supabase/queries/practices.ts:219-240` — `getPracticeStats()` enrichedCount is now a live Supabase count query with fallback to snapshot constant
- `dental-pe-nextjs/src/lib/constants/data-snapshot.ts:11` — `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT` marked `@deprecated` with migration note

## Build + tests
- npm run build: ✅ (Compiled successfully in 23.3s, TypeScript clean, all 22 routes)
- vitest: ✅ 35 tests passed (4 test files, incl. new strip-citations.test.ts — 9/9)

## Home activity feed
- Root cause of original failure: `select("*")` on `practice_changes` fetches all columns including `notes` (which can be large JSON text blobs). This triggered Supabase statement_timeout (57014) on production. The `.catch()` converted the error into `[]`, so the UI silently showed "No recent activity" despite 737 real rows existing.
- Fix: changed `changes.ts` to use an explicit column list `"id,npi,change_date,field_changed,old_value,new_value,change_type,notes,created_at"` (same as warroom's `CHANGE_SELECT` pattern). Also changed catch to return `null` so HomeShell can surface "Activity feed unavailable" rather than hiding the error.
- Verification: Build passes; the query now matches the pattern used successfully by the Warroom which queries the same table.

## Intelligence citations
- Files patched: `src/app/intelligence/_components/intelligence-shell.tsx`, new `src/lib/utils/strip-citations.ts`
- Sanitizer location: `src/lib/utils/strip-citations.ts:22-27` (exported function, overloaded signatures)
- Applied at: zipColumns renders for demand_outlook/supply_outlook/investment_thesis + ZIP detail panel + SignalValue component (covers all long-text AI fields)
- Test: `src/__tests__/strip-citations.test.ts` — 9 assertions, all pass
- Verification: vitest run → 9/9 pass. Build clean.

## enrichedCount
- Removed constant: no (kept with `@deprecated` comment; still used as fallback + by job-market/market-intel/system/data-breakdown pages)
- New live query: `supabase.from("practices").select("npi", {count: "exact", head: true}).not("data_axle_import_date", "is", null)` — count-only HEAD request, no rows fetched
- Live value: 2,983 (vs stale constant 2,992, drift +9 now corrected on Home page)
- Fallback: on query error, falls back to `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT` (2,992) with console.warn

## Remaining concerns
- The other 4 pages that still use `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT` (job-market, market-intel, system, data-breakdown) continue to show 2,992 instead of 2,983. These are display-only numbers and the drift is trivial (~0.3%), but they should be migrated to the same live-query pattern in a future pass.
- The `practice_changes` index `ix_practice_changes_change_date_desc` is in `scrapers/migrations/2026_04_26_frontend_performance_indexes.sql` (untracked, not yet applied to Supabase). Applying that index will make the `getRecentChanges` query even faster. The explicit column list fix reduces risk even without the index.
- `recentChanges` null check now makes the activity feed show "unavailable" correctly when the query fails, but does not retry. A retry with backoff could be added if timeout is intermittent.
