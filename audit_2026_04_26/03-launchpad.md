# @audit-launchpad findings

## Top-line verdict

The Launchpad page is **fundamentally broken for its core scoring purpose**: a Vercel serverless cold-start causes `fetchPracticeIntel()` to time out (8 s ceiling, ~17 s needed) on every cache-miss render, so `intelByNpi` is always empty, the confidence cap pins every single ranked practice to exactly **70/strong**, and the "best-fit" KPI reads **0** across all three tracks. There are 3,098 source-backed `practice_intel` rows in Supabase (money well spent), but none reach the scoring engine. The compound-narrative (`/api/launchpad/compound-narrative`) works perfectly when called directly; the rest of the AI routes are reachable because `ANTHROPIC_API_KEY` is set. The page is not crashing — it is silently serving a fully-flattened, confidence-capped result set while suppressing any user-visible warning.

---

## Page render check

- **HTTP status:** 200 (Vercel CDN cache HIT, `age: 493 s`, stale-time 300 s)
- **Shows tier counts?** KPI strip renders. Values: bestFit = **0**, mentor-rich = 137, hiring = **0**. Tier list renders 60 cards all labeled "strong / 70".
- **Shows practice list?** Yes — 60 practices visible.
- **Errors in HTML?** No visible error banner; sidebar + shell render correctly. The broken state is **silent** — only visible in `dataHealth.warnings` inside the RSC payload:
  1. `"Practice intel timed out; ranking used structural signals only."`
  2. `"Practice changes query failed: [object Object]"`
  3. `"Source-backed intel coverage is thin (0%)"`

---

## practice_intel quality audit

| Metric | SQLite | Supabase | Notes |
|---|---|---|---|
| Total rows | 3,370 | 3,370 | Sync is current |
| with verification_searches | 3,173 | 3,173 | 197 rows missing (all `insufficient`) |
| verified | 891 | 891 | |
| partial | 2,281 | 2,281 | |
| insufficient | 198 | 198 | All have `verification_searches=NULL` |
| null quality | 0 | 0 | |
| **SOURCE-BACKED** (quality∈{verified,partial} AND searches≥2 AND urls present) | **3,098** | **3,098** | Passes the 3-gate check in `launchpad.ts::hasSourceBackedIntel()` |
| DA\_ fake NPIs (no `practices` join) | 241 | 241 | DA\_ rows exist in Supabase `practice_intel` and pass the source-backed gate; they are not joinable to `practice_locations.primary_npi` (which holds real NPIs) but ARE joinable via `provider_npis` JSON array — partial match |

**Critical quality observation:** The 4 top-ranked practices in the RSC payload (NPIs `1750574752`, `1750498911`, `1669876983`, `1801263090`) all have `verification_quality='insufficient'` and `verification_searches=NULL`. These are the practices the ranking engine is trying to score — their intel rows exist but fail the source-backed gate. The 3,098 source-backed rows are largely for practices that rank lower, or whose NPI does not appear as `primary_npi` in `practice_locations`.

---

## Compound narrative API

- **Tested NPI:** `1376605832` (VIPUL SINGHAL DMD, Arlington Heights IL, `solo_high_volume`)
- **Method:** POST (GET returns 405 — route is POST-only)
- **Required body shape:** `{ practice: { npi, zip, state, entity_classification, buyability_score }, signals: [], scores: {succession, high_volume, dso}, track }`
- **Response:** `200` with a full evidence-backed thesis (~350 words, 15 ledger atoms, `evidence_quality: "verified"`)
- **Quality:** Evidence-based. Citations from practice website, Google reviews, Healthgrades, ZIP intel, deal comps. Thesis cites special-needs/sedation niche, Booth MBA, 84 Google reviews (4.4★), 65+ demographic, IL deal comp count.
- **`ANTHROPIC_API_KEY`:** Set in Vercel (no disabled banner rendered, route returns 200 not 503).
- **Note:** The compound-narrative route requires a properly constructed `practice` object passed by the client-side dossier. It does NOT auto-fire from the server render. When a user opens a practice dossier and requests the compound thesis, the route will work. The broken part is the **scoring / ranking pipeline**, not the narrative API.

---

## Track scoring trace

**File:** `src/lib/launchpad/ranking.ts:scoreForTrack()` (line ~270) + `hasThinData()` (line ~256)

**Sample practice:** NPI `1750574752` (solo\_high\_volume, `classification_confidence=85`, buyability\_score present in top-60)

**Expected score (manual computation, succession track):**
- This NPI has `verification_quality='insufficient'` → fails source-backed gate → `intelByNpi` does not contain it
- `hasThinData(practice, null)` → `intel == null` → returns `true`
- Score cap: any raw score > 70 → clamped to **70**
- Structural signals that fire without intel: `mentor_rich_signal` (if solo + 25+ yr + employee_count≥2), `succession_track_signal` (if mentor_rich + buyability≥50)
- Raw score with both: `50 + 25×1.5 + 30×2.0 = 147.5` → clamped 100 → **capped 70**

**Actual score from RSC:** **70** — matches.

**Match?** Yes — the formula is correct. The problem is that `intel` is always `null` at the time of scoring because the `fetchPracticeIntel()` call times out.

**Tier implication:** `score=70` → `tierFromScore(70)` → `"strong"` (65–79 range). No practice ever reaches `"best_fit"` (≥80) because the cap is lower than the threshold.

---

## DSO tier list source

- **Hardcoded in:** `src/lib/launchpad/dso-tiers.ts` — 16 hand-curated entries
- **Last updated:** File mtime `2026-04-24 15:23` (commit of Phase 2 ship)
- **Entries:** Mortenson (T1), MB2 (T1), Dental Associates WI (T1), Pacific Dental (T2), Dental Care Alliance (T2), Benevis (T2), Community Dental Partners (T2), Heartland (T3), National Dental Group (T3), Great Expressions (T3), American Dental Partners (T3), Aspen (Avoid), Sage (Avoid), Western (Avoid), Smile Brands (Avoid), Risas (Avoid)
- **Looks fresh?** Yes — citations present with URLs, comp bands populated for most entries, rationale sentences are specific. No obviously stale data (no pre-2023 citations found). Not reading from DB.
- **One gap:** Sage Dental and Western Dental have `compBand: null` (no comp data). Not a data correctness issue, just incomplete.

---

## Critical issues

### P0 — Practice intel always times out → all 5,103 practices score exactly 70, bestFit=0

**File:** `src/lib/supabase/queries/launchpad.ts:536` (`withTimeout("practice_intel", 8000, ...)`)  
**Evidence:** RSC `dataHealth.warnings[0] = "Practice intel timed out; ranking used structural signals only."`. `intelFetched: 0`. All 60 visible practices: `displayScore: 70`, `bestTier: "strong"`. `intelCoverage: {total: 5103, withIntel: 0, pct: 0}`. `successionCandidates.bestFit: 0`, `highVolumeCandidates.bestFit: 0`, `dsoCandidates.bestFit: 0`.

**Root cause:** `fetchPracticeIntel()` fans out `npisForPractice()` across all 5,103 practice\_location records, collecting `primary_npi` + each `provider_npis` JSON array → **~12,753 unique NPIs** → 26 batches of 500, run in `Promise.all`. Each batch is a Supabase `.in("npi", batch)` query against `practice_intel` (3,370 rows). From a warm connection, 26 parallel queries take ~0.7 s; from a Vercel serverless cold start with fresh Supabase connection, the combined latency exceeds 8 s. Timeout fires, `withTimeout` returns `null`, `intelRows = []`, `intelByNpi` is empty, every practice gets `hasThinData()=true`, every score ≥ 70 is capped at 70.

**Impact:** The confidence cap renders 3,098 source-backed `practice_intel` rows (likely \$2,400–\$35,000 in Anthropic API spend) invisible to the ranking engine. `hiringNow=0`, `bestFit=0`, zero signal differentiation. The page is operationally broken even though the data is correct in the DB.

**Fix direction (NOT implementing — investigation only):** Increase timeout to 20 s, OR pre-filter `fetchPracticeIntel` to only query NPIs that exist in `practice_intel` (e.g. a cached NPI set fetched at bundle start), OR move `intelByNpi` to a separate React Query client-side fetch with a longer timeout. Alternatively, reduce scope — only fetch intel for the top-N practices after structural ranking.

---

### P0 — Top-ranked practices have `verification_quality='insufficient'` intel that gets rejected by the 3-condition gate

**File:** `src/lib/supabase/queries/launchpad.ts:169` (`hasSourceBackedIntel()`), `chooseBestIntel()`  
**Evidence:** The 4 top-ranked RSC NPIs (`1750574752`, `1750498911`, `1669876983`, `1801263090`) all have `verification_quality='insufficient'` and `verification_searches=NULL` in Supabase `practice_intel`. They were researched (rows exist) but the dossier failed the anti-hallucination gate. The `auditForIntel()` function labels them `status: "rejected"` and excludes them from `intelByNpi`. Even if the timeout were fixed, these specific top practices would still have no intel.

**Impact:** The practices that are most likely to be succession targets (high buyability, mentor-rich) are precisely the ones that were researched and failed validation. The intel spend on these NPIs produced no benefit for the ranking engine.

---

### P1 — `fetchRecentAcquisitionNpis` fails with `[object Object]` error — `recent_acquisition_warning` never fires

**File:** `src/lib/supabase/queries/launchpad.ts:472` (`catch (err)`)  
**Evidence:** RSC `dataHealth.warnings[1] = "Practice changes query failed: [object Object]"`. `recentChangesFetched: 0`.  
**Root cause:** The function runs 26 sequential batches (BATCH_SIZE=500, not parallel). Each batch uses `.abortSignal(timeoutSignal(1500))`. When Supabase's abort signal fires, the Supabase client throws a `PostgrestError` object (`{ message, details, hint, code }`) which is **not an `Error` instance**. The catch block: `err instanceof Error ? err.message : String(err)` → `String(PostgrestError)` → `"[object Object]"`. The error message is opaque, and `recent_acquisition_warning` is silently disabled for all 5,103 practices.

**Secondary issue:** 26 sequential batches × 1,500 ms timeout = up to 39 s maximum. The sequential loop (not `Promise.all`) is the design bug. Even with a fixed error serializer, this function is too slow for serverless.

---

### P1 — `deals.target_zip` is NULL for all 2,861 deals — ZIP-scoped deal awareness is permanently dead

**File:** `src/lib/supabase/queries/launchpad.ts:388` (`fetchRecentDeals`)  
**Evidence:** `SELECT COUNT(*) FROM deals WHERE target_zip IS NOT NULL` → 0 (SQLite). Supabase: `content-range: */0` for `target_zip=not.is.null`. RSC: `recentDealsFetched: 0`.  
**Impact:** The `recentDeals` array is always empty. `recentDealZips` set is always empty. No deal context appears in ZIP dossier PE activity tab. The signal `growing_undersupplied_signal` (which reads `recentDealZips`) never fires on deal proximity. Feature has never worked.

---

### P1 — 584 `org_only_npi` locations (10.2% of `practice_locations`) are ranked in Launchpad

**File:** `src/lib/supabase/queries/practice-locations.ts::fetchPracticeLocations()` — no entity\_classification filter  
**Evidence:** Supabase `practice_locations` entity\_classification distribution (5,732 total): `org_only_npi: 584`. These are billing-only/admin-only NPI-2 organization records with no individual provider practicing at the address. `classifyPractice("org_only_npi", ...)` returns `"unknown"`.  
**Impact:** ~584 ghost locations appear in the 5,103-practice ranked set. They inflate `totalPracticesInScope`, suppress the true mentor-rich concentration, and can surface in the track list. The `entity-classifications.ts` comment explicitly says "org\_only\_npi is intentionally excluded — it's a billing-only / closed location with no operator." The query does not enforce this exclusion.

---

### P1 — CHI GP location count is 4,520 (docs say 4,575 — 55-location drift)

**Evidence:** `SELECT SUM(total_gp_locations) FROM zip_scores WHERE state='IL' (via watched_zips join)` → **4,520** SQLite, **4,520** Supabase (CHI subset of 4,833 total). CLAUDE.md documents **4,575**. Discrepancy is 55 locations. The RSC shows `totalGpLocations: 4520`. The docs are stale; the DB is the source of truth.

---

### P2 — `SIGNALS_REQUIRING_INTEL` export in `signals.ts` is defined but not enforced in `ranking.ts`

**File:** `src/lib/launchpad/signals.ts:270` (exported but never imported in `ranking.ts`)  
**Evidence:** `grep -n "SIGNALS_REQUIRING_INTEL" ranking.ts` returns 0 hits. The 5 signals marked `requiresIntel: true` (`hiring_now_signal`, `succession_published_signal`, `tech_modern_signal`, `ffs_concierge_signal`, `medicaid_mill_warning`) are gated by `intel` being non-null within `evaluateSignals()` directly (checking `intel?.hiring_active`, `intel?.technology_level`, etc.). So the functional effect is correct, but the exported constant is dead code and a misleading contract.

---

### P2 — `recentDealZips` is threaded through `SignalEvaluationContext` but never read

**File:** `src/lib/launchpad/ranking.ts:148` (interface), `490` (set creation)  
**Evidence:** `grep -n "recentDealZips" ranking.ts` → defined in interface and instantiated in `rankTargets()`, passed into `evalCtx`, but `evaluateSignals()` destructures the context and never uses `recentDealZips`. Dead code. Combined with finding #4 (target\_zip always NULL), the deal-proximity logic is doubly broken — the set is always empty AND is never consulted.

---

## Data quality context for AI dossier spend

| Population | Count | Notes |
|---|---|---|
| Total `practice_intel` rows | 3,370 | Matches SQLite and Supabase |
| Source-backed (3-gate pass) | 3,098 (91.9%) | `verification_quality∈{verified,partial}` AND `searches≥2` AND `urls present` |
| Top-4 RSC practices with intel | 4 rows — all `insufficient` | These are the highest-scoring structural candidates; their dossiers failed anti-hallucination gate |
| DA\_ fake NPIs in `practice_intel` | 241 | Non-joinable to `practice_locations.primary_npi` |
| `intelFetched` in production RSC | **0** | Timeout fires before any intel is used |

The API spend produced 3,098 valid dossiers that are stored, synced, and correctly formatted — but due to the 8-second timeout on Vercel serverless, none of them are reaching the ranking engine on production page renders.
