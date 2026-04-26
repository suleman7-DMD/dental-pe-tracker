# HANDOFF_DEBUG_RESULTS.md

**Date:** 2026-04-26
**Branch:** main (1 commit ahead of origin/main; new GDN parser changes uncommitted)
**Build status:** `npm run build` passes clean (21 routes, Turbopack 16.1.6)
**Test status:** `pytest scrapers/test_sync_resilience.py` — 14/14 pass
**Live verify:** dev server on :3001 — 11/11 routes return HTTP 200

---

## P0 Fix Summary

| ID | Title | Status | Files Changed |
|----|-------|--------|---------------|
| P0-A | Practice display names (DBA-first) | **FIXED** (prior session) | `ranking.ts`, `track-list-card.tsx`, `practice-directory.tsx`, `buyability-shell.tsx` |
| P0-B | Cross-page corporate KPI parity | **WORKING-AS-INTENDED** | `getPracticeStats()` + `countCorporateHighConfidence()` both source from `practice_locations`; gap was stale doc |
| P0-C | practice_changes Supabase sync gap | **NOT-A-BUG** | UX label fix shipped: "Recent Activity · Watched ZIPs" qualifier |
| P0-D | Intelligence `getPracticeIntel` pagination | **FIXED** (prior session) | `intel.ts` — paginated while-loop `range(from, from+1000-1)` |
| P0-E | Job Market map EC bug | **WORKING-AS-INTENDED** | `practice-density-map.tsx:263` already calls `classifyPractice(p.entity_classification, p.ownership_status)` |
| P0-F | Dossier verification quality gate | **FIXED** | `weekly_research.py` — `DRIFT_REMAP` + H28 cross-citation host check |
| P0-G | Sonnet 2-pass escalation | **BY-DESIGN, AWAITING USER ACTION** | `escalate_eligible.py` — 1,563/3,370 candidates eligible at $0.27 each = $422.01 (paid action) |
| P0-H | GDN parser fragments | **FIXED (this session)** | `gdn_scraper.py` — char class +comma, cap `{3,50}`→`{3,80}`, `_clean_target()` rewrite + 1 row backfill |
| P0-I | `test_sync_resilience.py` broken | **FIXED** (prior session) | `test_sync_resilience.py` — added PracticeLocation + sqlalchemy stubs |

---

## Preflight DB Snapshot (verified fresh, this session)

```
practices_global       = 381,598
watched_practices      = 13,818  (post-F32 hygienist cleanup)
practice_locations     =  5,732
zip_scores_total_gp    =  4,833  (sum of zip_scores.total_gp_locations)
practice_signals       = 13,818
zip_signals SQLite     =    290  (sync gap to Supabase still open: 0 in Supabase)
practice_intel         =  3,370
deals                  =  2,854
practice_changes       =  9,293
watched_zips           =    290  (IL=269, MA=21)
```

---

## Detailed Fix Evidence

### P0-A: Display names (DBA-first)

Prior-session fix held up on re-verification. `src/lib/warroom/ranking.ts:412` and `:678`, `src/app/launchpad/_components/track-list-card.tsx:119-122`, `src/app/job-market/_components/practice-directory.tsx`, and `src/app/buyability/_components/buyability-shell.tsx:458` all use `doing_business_as ?? practice_name ?? '--'`. Curl of `/buyability` shows `doing_business_as` token in rendered markup; build passes.

### P0-B: Cross-page corporate parity

`countCorporateHighConfidence()` at `src/lib/supabase/queries/warroom.ts:897-919` and `getPracticeStats()` both query `practice_locations` (location-deduped) for both numerator and denominator. Earlier "4.1% vs 1.5–1.7%" report was based on pre-`dc18d24` numbers when other surfaces still used NPI-row denominators. Now consistent. `sitrep-kpi-strip.tsx:66-78` shows "Corporate (High-Conf)" with "All signals: X%" amber subtitle — confirmed via curl of `/warroom`.

### P0-C: practice_changes sync gap

Diagnostic SQL on Supabase: `SELECT COUNT(*) FROM practice_changes` = 737. SQLite has 9,293, but only 737 fall inside watched ZIPs after `incremental_id` strategy applies `filter_watched_zips=True`. `orphan_no_practice = 0`, `max_id = 9421`. The 8,556-row "gap" is the watched-ZIP filter doing its job — the global-pool changes are intentionally not synced to Supabase. UX action shipped: `home-shell.tsx:230` now shows "Recent Activity · Watched ZIPs" qualifier so users understand the scope.

### P0-D: Intelligence pagination

`getPracticeIntel()` in `src/lib/supabase/queries/intel.ts` lines 32-52 has paginated while-loop with `PAGE = 1000`. Live verification via curl `/intelligence`: 3,543 unique 10-digit NPI tokens in rendered markup, well above the 1,000-row Supabase cap. Pre-fix would have capped at ~1000.

### P0-E: Job Market map entity_classification

`practice-density-map.tsx:263` calls `classifyPractice(p.entity_classification, p.ownership_status)`. `STATUS_COLORS` keyed on `independent | corporate | specialist | non_clinical | unknown` — all valid `classifyPractice()` return values. No regression on curl `/job-market`.

### P0-F: Verification quality gate (anti-hallucination)

Prior `DRIFT_REMAP` in `validate_dossier()` at `weekly_research.py:145-153` coerces `"high"` → `"partial"`, etc. The H28 follow-up extension (committed `d4bc2a9`) adds rule 6: cross-citation host check. When both `website.url` and `website._source_url` are populated, hosts must match (case-insensitive, www-stripped) OR `_source_url` must be in `_DIRECTORY_HOST_ALLOWLIST` (google/yelp/healthgrades/zocdoc/facebook/linkedin/etc.). Catches the Schmookler-class "cited URL belongs to a different dentist" hallucination that the URL-presence check missed. New helpers `_canonical_host()` + `_is_directory_host()`. 10/10 smoke cases pass.

### P0-G: Sonnet escalation

By design — batch mode is Pass-1 only. `build_batch_requests()` at `weekly_research.py:465-468` is documented as Pass-1 ONLY. The escalation path is `scrapers/dossier_batch/escalate_eligible.py`, which reads Pass-1 dossiers, filters by `_should_escalate()`, and submits Sonnet escalation batches. Dry run on current state: **1,563 eligible / 3,370 dossiers, est. $422.01** at Sonnet rates. Awaiting user authorization (paid action — not a code fix).

### P0-H: GDN parser fragments

**Two-tier defect:**

1. The prior fix (commit `cfdab89`) added `_TARGET_STOP_WORDS` and `_clean_target()` but left the regex character class `_N = r"A-Za-z0-9\s\'’\-&\."` (no comma) and the `{3,50}` upper bound. As a result:
   - Long fragments (>50 chars) never matched the inverted patterns at all (`Bowers Orthodontic Specialists which is located in Austin, TX, was acquired by EPIC4` is 60+ chars before the verb).
   - Relative clauses with embedded commas (`Premier Endodontic Group, headquartered in Houston, was acquired by ABC Partners`) couldn't be spanned because comma wasn't in the class.

2. **Fix applied this session** (`scrapers/gdn_scraper.py:761-790`):
   - Added `,` to `_N`: `r"A-Za-z0-9\s\'’\-&\.,"` so non-greedy matches can span clausal commas. Inline comment explains the trade-off.
   - Raised cap `{3,50}` → `{3,80}` in all 16 patterns (sed-applied).
   - Rewrote `_clean_target()`: scan from left, find first stop word, truncate at that index, then peel any trailing aux/stop leftovers. Replaces the prior right-to-left peel loop, which only worked when the stop word was the very last token.

3. **Smoke test results (6/6 pass after fix):**
   - `Bowers Orthodontic Specialists which is located in Austin, TX, was acquired by EPIC4` → `Bowers Orthodontic Specialists` ✅
   - `Premier Endodontic Group, headquartered in Houston, was acquired by ABC Partners` → `Premier Endodontic Group` ✅
   - `Smith Dental was acquired by ABC Partners in 2024` → `Smith Dental` ✅ (regression check)
   - `Bright Smiles which is located in Chicago has joined Heartland Dental` → `Bright Smiles` ✅
   - `Dr. Jones Family Dentistry, which has been operating since 1985, was acquired by Smile Brands` → `Dr. Jones Family Dentistry` ✅
   - `Heart of Texas Smiles led by Dr. Garcia has joined Imagen Dental Partners` → `Heart of Texas Smiles` ✅

4. **Historical-data backfill:** DB scan for fragment-tagged rows (`LIKE '%led by Dr%' OR '%which is%' OR '%headquartered%' OR '%located in%'`) found 1 remaining: `id=1292, target_name='Heart of Texas Smiles led by Dr', platform=Imagen Dental Partners, deal_date=2022-04-01`. Updated to `'Heart of Texas Smiles'` via direct SQL. Now 0 rows match the fragment-detection scan.

5. **Known limitation (non-blocking):** sentence-end without punctuation, e.g. `Imagen Dental Partners acquired Heart of Texas Smiles` (no terminator), still returns `None` because the standard pattern requires a terminator (`,|.|;|in|from|...`). Pre-existing parser limitation, not introduced by this fix.

### P0-I: Test stubs

Prior fix (commit `cfdab89`) added `PracticeLocation` to the database mock symbol list and `or_`/`and_` lambda stubs to the sqlalchemy mock module. Re-run this session: **14/14 pass in 0.52s**.

---

## Build & Live Verification

### Build
```
$ cd dental-pe-nextjs && npm run build
▲ Next.js 16.1.6 (Turbopack)
✓ Compiled successfully in 23.5s
✓ Generating static pages (6/6) in 338.3ms
21 routes (1 static /_not-found, 20 dynamic)
```

### Tests
```
$ python3 -m pytest scrapers/test_sync_resilience.py -v
14 passed in 0.52s
```

### Live route verification (dev server :3001)
```
/                200  109,390 bytes
/launchpad       200   80,050 bytes
/warroom         200  868,811 bytes
/deal-flow       200 1,643,851 bytes
/market-intel    200  899,740 bytes
/buyability      200  694,604 bytes
/job-market      200 1,215,617 bytes
/research        200   95,868 bytes
/intelligence    200 40,175,331 bytes  ← pagination working (3,543 unique NPIs)
/system          200   99,778 bytes
/data-breakdown  200  196,211 bytes
```

Content sanity:
- `/warroom` markup contains `Corporate (High-Conf)` and `All signals` (P0-B confirmed)
- `/buyability` markup contains `doing_business_as` field key (P0-A confirmed)
- `/intelligence` markup contains 3,543 unique 10-digit NPI tokens (P0-D confirmed: pagination > 1000 cap)

---

## Remaining Blockers (User Action Required)

| Item | Action | Why |
|------|--------|-----|
| P0-G escalation budget | Run `python3 scrapers/dossier_batch/escalate_eligible.py` (~$422) | 1,563 eligible Pass-1 dossiers; Sonnet Pass-2 needs paid auth |
| `zip_signals` Supabase sync | Run `python3 scrapers/sync_to_supabase.py --tables zip_signals` | SQLite has 290 rows, Supabase has 0 (Warroom ZIP-overlay silent) |
| Vercel `ANTHROPIC_API_KEY` | Set in Vercel project env (Production + Preview + Development), redeploy | `/api/launchpad/compound-narrative` returns 503 without it |
| Commit + deploy | `git commit -am 'P0-H: GDN parser regex cap + comma in char class'` then `git push` | GDN parser change is uncommitted |
| GitHub secrets for keep-alive | Add `SUPABASE_URL` + `SUPABASE_ANON_KEY` to repo secrets | `.github/workflows/keep-supabase-alive.yml` cron will 401 otherwise |

---

## Remaining Risks

1. **GDN parser comma-in-class trade-off:** non-greedy `?` should still terminate at the first comma in standard patterns (since terminator alternatives include `,`), but if a future pattern is rewritten greedily, captures could absorb commas. The 6/6 smoke + backfill scan + historical 1-row repair gives high confidence today; revisit if a dry run pulls in wrong-target captures.
2. **`zip_signals` 290-row sync gap is silent.** Watched ZIPs are scored locally but the ZIP-overlay flags (ada_benchmark_gap_flag, deal_catchment_24mo, etc.) read 0 in Supabase. Warroom ZIP dossiers will show no overlay until re-sync.
3. **Sonnet escalation backlog grows weekly.** Each Pass-1-only batch adds candidates. At current rate (~50 new eligible/week) the $422 cost grows linearly until run.
4. **practice_intel cost-tracking divergence.** `poll.py.totals.total_cost_usd` overcounts ~8.5× actual billing per the April 25 calibration. Don't quote that to the user as the bill — reconcile with https://console.anthropic.com/usage.
5. **Live deploy not yet verified.** Local dev :3001 returned 200 on all 11 routes; Vercel auto-deploy on push has not been re-tested in this session.

---

## Page Sweep Checklist

| Page | Route | Local 200 | Display Name DBA-First | Notes |
|------|-------|-----------|------------------------|-------|
| Home | `/` | ✅ | N/A | Recent Activity scope qualifier "· Watched ZIPs" added |
| Launchpad | `/launchpad` | ✅ | ✅ track-list-card | DBA-first in card heading + practiceSnapshot |
| Warroom | `/warroom` | ✅ | ✅ ranking.ts | DBA-first in target list + dossier + headline; high-conf KPI verified |
| Deal Flow | `/deal-flow` | ✅ | N/A | shows deal names, not practice names |
| Market Intel | `/market-intel` | ✅ | N/A | ZIP-level only |
| Buyability | `/buyability` | ✅ | ✅ buyability-shell | DBA-first in table |
| Job Market | `/job-market` | ✅ | ✅ practice-directory | DBA-first in 4 tab columns + CSV; map uses entity_classification |
| Intelligence | `/intelligence` | ✅ | N/A (NPI-keyed) | Pagination fix confirmed: 3,543 NPIs >> 1000 cap |
| Research | `/research` | ✅ | N/A | |
| System | `/system` | ✅ | N/A | |
| Data Breakdown | `/data-breakdown` | ✅ | N/A | Provenance audit page |
