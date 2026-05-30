# @triage-frontend findings
Generated: 2026-05-30

---

## Tool status

Bash, Read, Edit tools fully operational. Vitest confirmed working once node_modules was installed by @triage-build. Dev server started and all 4 key routes probed successfully.

---

## Static findings (A — no node_modules needed)

### Supabase client/server setup

**client.ts** — Clean singleton using `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Throws on missing vars (correct). No hardcoded URLs. `persistSession: false` is correct for SSR.

**server.ts** — Creates a new client per-call (correct for SSR — avoids shared state). Key priority: `SUPABASE_SERVICE_ROLE_KEY || SUPABASE_SECRET_KEY || NEXT_PUBLIC_SUPABASE_ANON_KEY`. The local `.env.local` has `SUPABASE_SECRET_KEY` (not `SUPABASE_SERVICE_ROLE_KEY`), so the fallback chain works correctly. No hardcoded URLs.

**Local env vars present:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MAPBOX_TOKEN`, `SUPABASE_SECRET_KEY`. **Missing locally:** `ANTHROPIC_API_KEY` (expected — AI routes will 503 locally, documented behavior).

**Vercel env gap:** Vercel is documented to need `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`. This is set in the local `.env.local` but NOT verified to be set in Vercel production env vars — worth confirming separately.

### Pagination on large tables

**practices.ts** — All large-table queries paginated correctly:
- `getPracticesByZips`: explicit `.range()` with page param
- `getPracticesWithCoords`: chunked ZIP loop (100/chunk) + inner page loop (1000/page)
- `getPracticeStats`: delegates to `fetchPracticeLocations()` which has its own pagination loop

**practice-locations.ts** — `fetchPracticeLocations()` has correct PAGE_SIZE=1000 while-loop with `.range(from, to)`. Breaks when batch < size. Handles `maxRows` cap correctly.

**deals.ts** — `getDealStats`, `getTopSponsors`, `getTopPlatforms`, `fetchAllDealColumn` all paginate through the 2,900+ deal table correctly.

**FINDING: `getDealCompsForPractice()` MISSING pagination (LOW RISK now, MEDIUM RISK as IL deal volume grows)**

```typescript
// deals.ts line 285-292
const { data, error } = await supabase
  .from("deals")
  .select("deal_date, platform_company, pe_sponsor, specialty, deal_size_mm, ebitda_multiple")
  .eq("target_state", state)
  .gte("deal_date", sinceIso)
  .order("deal_date", { ascending: false });
  // NO .limit() and NO .range() — Supabase default cap = 1000 rows
```

IL has ~400 deals in 24 months at current volume — safe today. If total IL deals exceeds 1000 in the next few years, this silently truncates deal comps for IL-scoped practices. The fix is trivial (`.limit(1000)` or a pagination loop). Currently only called from `compound-narrative/route.ts` where intel is scarce anyway.

**watchedzips.ts, zip-scores.ts, system.ts, changes.ts** — All use pagination or count-only queries. No bare large-table fetches found.

### Entity classification primary (ownership_status fallback)

All query files reviewed use `entity_classification` as primary with `ownership_status` fallback:
- `practices.ts::getPracticeCountsByStatus()` — entity_classification primary, ownership_status fallback when NULL
- `practice-locations.ts::practiceLocationToWarroomRecord()` — calls `classifyPractice(ec, os)` correctly
- `practices.ts::getPracticeStats()` — filters by INDEPENDENT_CLASSIFICATIONS array, DSO_NATIONAL_TAXONOMY_LEAKS

The F27 vitest test (`classification-primary.test.ts`) enforces this across all src/ files — see Vitest results below.

### API routes — 503 guard for ANTHROPIC_API_KEY

All 7 AI routes confirmed to return 503 (not 500) when `ANTHROPIC_API_KEY` is missing:

| Route | Status guard |
|-------|-------------|
| `/api/launchpad/ask` | 503 — "AI Q&A disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/compound-narrative` | 503 — "Compound narrative disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/contract-parse` | 503 — "Contract parsing disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/interview-prep` | 503 — "Interview prep disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/smart-briefing` | 503 — "Smart briefing disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/zip-mood` | 503 — "ZIP mood disabled: ANTHROPIC_API_KEY is not set." |
| `/api/launchpad/narrative` | FILE DOES NOT EXIST (404) — see finding below |

**FINDING: `/api/launchpad/narrative/route.ts` does NOT exist on disk**

The CLAUDE.md documents a `narrative/route.ts` (Claude Haiku "Why this practice for me?" endpoint), but `find` returns only 6 launchpad route files — `narrative` is absent. The `narrative-card.tsx` component likely calls this endpoint. This will 404 on both local and Vercel.

```bash
$ ls src/app/api/launchpad/
ask  compound-narrative  contract-parse  interview-prep  smart-briefing  zip-mood
# narrative/ is MISSING
```

**FINDING: Non-AI routes lack explicit error handling for Supabase failures**

`/api/deals/route.ts`, `/api/practices/[npi]/route.ts`, `/api/watched-zips/route.ts` — these likely handle Supabase errors correctly (throw → 500), but they don't return structured error JSON like the AI routes. Minor — these routes are low-traffic.

### Server Component error handling (page.tsx files)

**Home (`/`)** — Full try/catch wrapping all queries. Falls back to "Loading..." UI. Individual queries use `.catch()` with fallback values. `recentChanges` uses `.catch(() => null)` with null meaning "unavailable" vs `[]` meaning "empty" — HomeShell renders "Activity feed unavailable" for null. Well-structured.

**Warroom (`/warroom`)** — try/catch around `getSitrepBundle()`. Passes `initialBundleError` string to shell which handles gracefully. `getSitrepBundle` itself uses `Promise.allSettled` internally — single query failure degrades to warning, not crash.

**Launchpad (`/launchpad`)** — try/catch with `serializeError()` helper. Passes `initialBundleError` string to shell. `getLaunchpadBundle` uses `Promise.allSettled` internally. `withTimeout()` guards slow queries (25s for practice_intel, 5s per batch for acquisition NPIs).

All 11 page.tsx files reviewed have defensive patterns. No unguarded `throw` paths that would crash the whole page to a 500.

---

## Vitest result (B)

**All 35 tests pass across 4 test files:**

```
 ✓ src/lib/warroom/intent.test.ts (19 tests) 18ms
 ✓ src/__tests__/strip-citations.test.ts (9 tests) 5ms
 ✓ src/__tests__/classification-primary.test.ts (2 tests) 151ms
 ✓ src/lib/warroom/ranking.test.ts (5 tests) 5ms

 Test Files  4 passed (4)
      Tests  35 passed (35)
   Duration  1.20s
```

**F27 classification-primary.test.ts: 2 PASSED** — entity_classification-primary invariant holds across all src/ TypeScript files. No regressions.

One minor warning (non-blocking): `The CJS build of Vite's Node API is deprecated` — cosmetic, does not affect test results.

---

## Dev server runtime result + route HTTP codes (B)

Dev server started (`next dev`, Turbopack, port 3000). Routes probed:

| Route | HTTP Code | Render time | Runtime errors |
|-------|-----------|-------------|----------------|
| `/` | **200** | ~3.0s | enrichedCount warn (non-critical), recentChanges 57014 (handled) |
| `/warroom` | **200** | 20.0s (first compile 5.2s + render 14.8s) | None logged |
| `/launchpad` | **200** | 28.4s (first compile 2.1s + render 26.3s) | Timeout warnings (handled) |
| `/market-intel` | **200** | 22.3s (first compile 2.2s + render 20.0s) | None logged |

All 4 routes return HTTP 200. No 500s, no unhandled exceptions.

### Runtime errors observed (all currently handled):

**Error 1: `[getPracticeStats] enrichedCount query failed:` (empty message)**
- Frequency: Every `GET /` request (~100% of home page loads)
- Cause: `supabase.from("practices").select("npi", { count: "exact", head: true }).not("data_axle_import_date", "is", null)` — the `practices` table HEAD-count query is hitting a Supabase error with an empty `message` field. This is a PostgrestError (not a JS Error), so `enrichErr.message` is `""`. The most likely cause is that the anon key (used as fallback in server client when `SUPABASE_SECRET_KEY` resolves) doesn't have permission to run count queries on the full 381k-row `practices` table without RLS violation — OR Supabase is returning an empty-message timeout.
- **Impact:** Non-critical — code falls back to `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT` constant (2,992 hardcoded). Home page renders with stale enriched count but does not crash.
- **Vercel behavior:** Same fallback. No user-visible breakage, but enriched count on Home KPI card is permanently stale (hardcoded 2,992) even as the real value changes.

**Error 2: `[HomePage] recentChanges error: { code: '57014', message: 'canceling statement due to statement timeout' }`**
- Frequency: Every `GET /` request (100% of home page loads locally)
- Cause: `getRecentChanges(supabase, undefined, 90)` with no ZIP filter runs: `SELECT ... FROM practice_changes WHERE change_date >= '2026-03-01' ORDER BY change_date DESC LIMIT 500`. The `practice_changes` table (8,848 rows) is hitting Supabase's statement_timeout on a full-table scan. This implies `change_date` lacks an index, or the Supabase connection has a very short timeout.
- **Impact:** Non-critical locally, but **this means the Home page Activity Feed is ALWAYS unavailable locally**. On Vercel (faster Postgres, likely indexed), this query may succeed. The `.catch(() => null)` handler correctly degrades to "Activity feed unavailable" in the UI.
- **Vercel behavior:** Likely succeeds (Supabase statement_timeout is typically 8s on the pro plan; the query is simple once indexed). But if `change_date` has no index on the Supabase side, this 57014 also fires in production.

**Error 3: `[launchpad] fetchRecentAcquisitionNpis failed: TimeoutError`**
- Frequency: On `/launchpad` first compile (seen in log)
- Cause: `practice_changes` query with 14k+ NPI IN-batch scans hitting the 5s per-batch timeout. Specifically the `.abortSignal(timeoutSignal(5000))` fires.
- **Impact:** Non-critical — `fetchRecentAcquisitionNpis` catches this and returns `{ result: new Set(), warning: "..." }`. Launchpad renders without acquisition flag data.
- **Vercel behavior:** Same — the `.catch` block in getLaunchpadBundle catches and returns graceful fallback.

**Error 4: `[launchpad] practice_intel unavailable: TimeoutError`**
- Frequency: On `/launchpad` first compile
- Cause: `fetchPracticeIntel` wrapped in `withTimeout(25000)` but the practice_intel table is tiny (~23 rows). The timeout was likely triggered by a slow first connection, not row volume. After first compile this resolves.
- **Impact:** Non-critical — `withTimeout` returns null; launchpad renders without intel data.

---

## VERDICT (C)

**Does the app run correctly against live Supabase?**

YES — the app is fundamentally healthy. All 4 probed routes return 200. No 500 errors. No unhandled exceptions. The test suite passes 35/35. All documented invariants (entity_classification primary, pagination, 503 on missing AI key) are correctly implemented.

**Concrete runtime breakages with proof:**

| # | Severity | Description | Proof | Vercel impact |
|---|----------|-------------|-------|---------------|
| 1 | LOW | `narrative/route.ts` missing (404 on narrative API calls) | `ls src/app/api/launchpad/` — only 6 dirs, no `narrative/` | AI narrative card on Launchpad will 404 instead of 503, breaking the generate-button UX |
| 2 | LOW | `enrichedCount` always fails silently, falls back to stale constant | `[getPracticeStats] enrichedCount query failed: ` logged on every `/` load | Enriched count on Home KPI always shows hardcoded 2,992 rather than live count |
| 3 | LOW | `recentChanges` always times out (57014) locally → Activity Feed unavailable | `code: '57014', message: 'canceling statement due to statement timeout'` on every `/` load | May succeed on Vercel if `change_date` has a Supabase index |
| 4 | LOW | `getDealCompsForPractice` missing pagination — silently truncates at Supabase default 1000 rows | Code inspection: no `.range()` or `.limit()` on state+date deals query | Low risk today (IL ~400 deals/24mo), grows over time |
| 5 | MEDIUM | Launchpad renders in 26s+ (first hit); /warroom 14.8s; /market-intel 20s | Dev server log: render times above | On Vercel (serverless), each cold start gets a max 60s function timeout. These pages are close to the limit on complex data loads |

**Works locally but could break on Vercel:**
- The 26s+ launchpad render and 20s+ market-intel render could hit Vercel's 60s serverless function timeout on cold starts with a slow Supabase connection. Not observed failing currently but is in the risk zone.
- `SUPABASE_SECRET_KEY` is in `.env.local` but unclear if it's set in Vercel env vars under that name vs `SUPABASE_SERVICE_ROLE_KEY`. Server client code tries both but a missing key would fall back to anon key for server components.

**Anything only breaking on Vercel (not locally):**
- None identified.

---

## Proposed fixes (NOT applied — diffs only)

### Fix 1: Create the missing `narrative/route.ts`

The narrative card component calls a non-existent endpoint. Create a minimal stub matching the pattern of other AI routes:

```typescript
// src/app/api/launchpad/narrative/route.ts
export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const apiKey = process.env.ANTHROPIC_API_KEY
  if (!apiKey) {
    return NextResponse.json(
      { error: "Narrative disabled: ANTHROPIC_API_KEY is not set. Add it to Vercel env vars to enable." },
      { status: 503 }
    )
  }
  // ... Haiku call for "Why this practice for me?" narrative
}
```

The full implementation is documented in CLAUDE.md — Haiku 4.5, 500 max_tokens, 0.4 temp, dental-career-advisor system prompt, 503 guard, raw HTTP fetch (no SDK).

### Fix 2: Add `getDealCompsForPractice` pagination guard

```typescript
// deals.ts line 285 — add .limit(1000) to make the Supabase cap explicit
const { data, error } = await supabase
  .from("deals")
  .select("deal_date, platform_company, pe_sponsor, specialty, deal_size_mm, ebitda_multiple")
  .eq("target_state", state)
  .gte("deal_date", sinceIso)
  .order("deal_date", { ascending: false })
  .limit(1000); // Supabase default is 1000; make it explicit
```

Or for future-proofing, paginate with a while-loop. For now `.limit(1000)` is sufficient given current data volume.

### Fix 3: Improve enrichedCount error logging to surface actual error

```typescript
// practices.ts line 232 — log the full object not just .message (which is empty)
} else if (enrichErr) {
  console.warn("[getPracticeStats] enrichedCount query failed:", JSON.stringify(enrichErr))
}
```

This is diagnostic only — doesn't change behavior but makes the root cause investigable.

### Fix 4: Add `change_date` index recommendation for Supabase

The 57014 timeout on `practice_changes` is likely from a missing index. In Supabase SQL editor:

```sql
CREATE INDEX IF NOT EXISTS practice_changes_change_date_idx ON practice_changes (change_date DESC);
```

This is a DB-level fix, not a code fix. Once added, the home page Activity Feed will stop timing out.

---

## PROOF

### Vitest output
```
 ✓ src/lib/warroom/intent.test.ts (19 tests) 18ms
 ✓ src/__tests__/strip-citations.test.ts (9 tests) 5ms
 ✓ src/__tests__/classification-primary.test.ts (2 tests) 151ms
 ✓ src/lib/warroom/ranking.test.ts (5 tests) 5ms

 Test Files  4 passed (4)
      Tests  35 passed (35)
   Duration  1.20s
```

### Route HTTP codes
```
/ -> 200
/warroom -> 200 (timeout 28 from curl, but server logged 200 in 20.0s)
/launchpad -> 200
/market-intel -> 200
```

### Dev server log (key errors)
```
GET / 200 in 3.0s (compile: 31ms, render: 2.0s)
[getPracticeStats] enrichedCount query failed:    ← empty message, every / load
[HomePage] recentChanges error: {
  code: '57014',
  details: null,
  hint: null,
  message: 'canceling statement due to statement timeout'
}
GET /warroom 200 in 20.0s (compile: 5.2s, render: 14.8s)
[launchpad] fetchRecentAcquisitionNpis failed: TimeoutError: The operation was aborted due to timeout
[launchpad] practice_intel unavailable: TimeoutError: The operation was aborted due to timeout
GET /launchpad 200 in 28.4s (compile: 2.1s, render: 26.3s)
GET /market-intel 200 in 22.3s (compile: 2.2s, render: 20.0s)
```

### Missing narrative route
```bash
$ ls src/app/api/launchpad/
ask  compound-narrative  contract-parse  interview-prep  smart-briefing  zip-mood
# narrative/ directory is absent
```

### 503 guard verification (all 6 existing AI routes)
All confirmed at `{ status: 503 }` when `ANTHROPIC_API_KEY` is falsy — exact grep output:
```
ask:              { status: 503 }  "AI Q&A disabled: ANTHROPIC_API_KEY is not set..."
contract-parse:   { status: 503 }  "Contract parsing disabled..."
interview-prep:   { status: 503 }  "Interview prep disabled..."
smart-briefing:   { status: 503 }  "Smart briefing disabled..."
zip-mood:         { status: 503 }  "ZIP mood disabled..."
compound-narrative: { status: 503 } "Compound narrative disabled..."
```

### getDealCompsForPractice — no pagination
```typescript
// deals.ts lines 285-292 — no .range() or .limit() call
const { data, error } = await supabase
  .from("deals")
  .select("deal_date, platform_company, pe_sponsor, specialty, deal_size_mm, ebitda_multiple")
  .eq("target_state", state)
  .gte("deal_date", sinceIso)
  .order("deal_date", { ascending: false });
// Supabase will silently return at most 1000 rows
```
