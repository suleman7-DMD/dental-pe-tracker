# fix-frontend — FIX PHASE REPORT
Date: 2026-05-30

## Files Changed

### 1. CREATED: `dental-pe-nextjs/src/app/api/launchpad/narrative/route.ts`

New file restoring the missing Launchpad narrative route (was 404 after commit 056c658 deleted narrative-card.tsx and its hook).

**Contract:**
- `POST /api/launchpad/narrative`
- Request: `{ npi: string, practice: PracticeSnapshot, signals: string[], scores: TrackScores, track: "succession"|"high_volume"|"dso"|"all" }`
- Response: `{ narrative: string, model: string }`
- Model: `claude-haiku-4-5-20251001`
- Raw HTTP `fetch()` to `https://api.anthropic.com/v1/messages` (no SDK — project convention)
- API key guard at TOP: absent key → HTTP 503 immediately

**Key implementation details:**
- `export const runtime = "nodejs"`, `export const dynamic = "force-dynamic"` (matches siblings)
- `validateBody()` runtime type-checks all required fields before calling Anthropic
- `buildPrompt()` assembles a structured context string from the PracticeSnapshot + signals + scores, filtered of null entries via `.filter((s): s is string => s !== null)`
- System prompt: candid dental career advisor, 3-5 sentences plain prose, honest with caveats, never fabricate, close with one verification action
- 4 track labels: succession, high_volume, dso, all
- 502 on Anthropic network/API errors, 400 on bad input, 503 on missing key
- MAX_TOKENS=500, TEMPERATURE=0.4

### 2. EDITED: `dental-pe-nextjs/src/lib/supabase/queries/deals.ts`

Added `.limit(1000)` to `getDealCompsForPractice` query (Supabase silently caps at 1000 without an explicit limit; making the cap explicit is the project convention and prevents silent truncation).

**Diff:**
```diff
     .eq("target_state", state)
     .gte("deal_date", sinceIso)
-    .order("deal_date", { ascending: false });
+    .order("deal_date", { ascending: false })
+    .limit(1000);
```

## Build Result

```
✓ Compiled successfully in 9.5s
  Running TypeScript ... (passed)
  Generating static pages using 7 workers (6/6) in 406.9ms

Route (app)
...
├ ƒ /api/launchpad/narrative   ← NEW, registered dynamic
...
```

Exit code: 0

## Vitest Result

```
 ✓ src/__tests__/strip-citations.test.ts (9 tests)
 ✓ src/lib/warroom/intent.test.ts (19 tests)
 ✓ src/lib/warroom/ranking.test.ts (5 tests)
 ✓ src/__tests__/classification-primary.test.ts (2 tests)  ← F27 green

 Test Files  4 passed (4)
      Tests  35 passed (35)
```

## 503 Curl Proof

```
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:3099/api/launchpad/narrative \
  -H "Content-Type: application/json" \
  -d '{"npi":"1234567890","practice":{"name":"Test Dental"},"signals":[],"scores":{"succession":50,"high_volume":60,"dso":30},"track":"all"}'
503
```

Dev server log: `POST /api/launchpad/narrative 503 in 736ms`

No `ANTHROPIC_API_KEY` in `.env.local` → correct 503 (not 404, not 500).

## Collision Rule Compliance

- Created only: `src/app/api/launchpad/narrative/route.ts`
- Edited only: `src/lib/supabase/queries/deals.ts` (`getDealCompsForPractice` function only)
- No git commands run — changes left in working tree for lead review
