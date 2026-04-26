# HANDOFF_DEBUG_RESULTS.md

**Date:** 2026-04-26
**Branch:** main (uncommitted)
**Build status:** `npm run build` passes clean (all 21 routes)
**Test status:** `scrapers/test_sync_resilience.py` — 14/14 pass

---

## P0 Fix Summary

| ID | Title | Status | Files Changed |
|----|-------|--------|---------------|
| P0-A | Practice display names (DBA-first) | **FIXED** | `ranking.ts`, `track-list-card.tsx`, `practice-directory.tsx`, `buyability-shell.tsx` |
| P0-B | Cross-page corporate KPI mismatch | **ALREADY FIXED** | No changes needed — tiered display already correct in `sitrep-kpi-strip.tsx` and all pages |
| P0-C | practice_changes Supabase sync gap | **DIAGNOSED — NEEDS MANUAL SYNC** | No code fix — requires `python3 scrapers/sync_to_supabase.py --tables practice_changes` |
| P0-D | Intelligence getPracticeIntel pagination | **FIXED** | `intel.ts` |
| P0-E | Job Market map EC bug | **ALREADY FIXED** | No changes needed — `classifyPractice()` already called at line 263 |
| P0-F | Dossier verification quality gate | **ALREADY FIXED** | No changes needed — `DRIFT_REMAP` in `validate_dossier()` already coerces "high" → "partial" |
| P0-G | Sonnet 2-pass escalation never fires | **BY DESIGN** | Batch mode is Pass-1 only; `escalate_eligible.py` exists for follow-up escalation batches |
| P0-H | GDN parser captures fragments | **FIXED** | `gdn_scraper.py` |
| P0-I | test_sync_resilience.py broken | **FIXED** | `test_sync_resilience.py` |

---

## Detailed Fix Evidence

### P0-A: Practice Display Names (DBA-first priority)

**Root cause:** Multiple surfaces used `practice_name ?? doing_business_as` priority, showing doctor legal names (e.g. "SMITH JOHN DDS") instead of brand/DBA names (e.g. "Bright Smiles Dental").

**Files edited:**

1. **`src/lib/warroom/ranking.ts:678`** — `practiceName` field in `RankedTarget` flipped to `doing_business_as ?? practice_name`
2. **`src/lib/warroom/ranking.ts:412`** — `buildHeadline()` same DBA-first flip
3. **`src/app/launchpad/_components/track-list-card.tsx:119-122`** — `practiceSnapshot.name` flipped to `doing_business_as ?? practice_name`
4. **`src/app/job-market/_components/practice-directory.tsx`** — Added `withDisplayName` useMemo that maps `display_name: p.doing_business_as ?? p.practice_name ?? '--'`; updated all 4 column arrays, sort, CSV export, and dependency arrays
5. **`src/app/buyability/_components/buyability-shell.tsx:458`** — Table cell flipped to `p.doing_business_as ?? p.practice_name ?? '--'`

**Verification:** `npm run build` passes. All column keys, CSV headers, and sort logic reference the DBA-first `display_name`.

### P0-B: Cross-page Corporate KPI Mismatch

**Finding:** Already correctly implemented. `sitrep-kpi-strip.tsx` shows "Corporate (High-Conf)" with all-signals amber subtitle. `countCorporateHighConfidence()` in `warroom.ts:897-919` uses dso_national + strong dso_regional (EIN/parent_company) + DSO specialists. Consistent with Home, Market Intel, Job Market, and Launchpad.

### P0-C: practice_changes Supabase Sync Gap

**Finding:** SQLite has 9,293 rows (max id=9,421). Supabase has ~737. The gap was caused by a CASCADE truncation during a prior `_sync_watched_zips_only` run which wiped `practice_changes` via FK dependency. The `incremental_id` strategy is correct but the sync metadata was reset.

**Required user action:** Run `python3 scrapers/sync_to_supabase.py --tables practice_changes` to re-sync all rows. No code fix needed.

### P0-D: Intelligence Practice Intel Pagination

**Root cause:** `getPracticeIntel()` in `intel.ts` had no `.range()` pagination, silently capping at 1,000 rows.

**Fix:** Added a `while` loop with `PAGE=1000` that fetches successive `.range(from, from + PAGE - 1)` slices until a page returns fewer than 1,000 rows.

### P0-E: Job Market Map EC Bug

**Finding:** Already fixed in current code. `practice-density-map.tsx:263` calls `classifyPractice(p.entity_classification, p.ownership_status)` and `STATUS_COLORS` is keyed on `independent`, `corporate`, `specialist`, `non_clinical`, `unknown` — all valid `classifyPractice()` return values.

### P0-F: Dossier Verification Quality Gate

**Finding:** Already handled. `validate_dossier()` in `weekly_research.py:145-153` has `DRIFT_REMAP` that coerces off-spec values: `"high" → "partial"`, `"verified" → "verified"` (pass-through), `"partial" → "partial"`, `"insufficient" → "insufficient"`. The gate rejects `evidence_quality == "insufficient"` at line 163.

### P0-G: Sonnet Escalation Never Fires

**Finding:** By design in batch mode. `build_batch_requests()` at line 465-468 documents: "This path is Pass-1 ONLY. It does NOT fire the Sonnet escalation." The escalation follow-up path is `scrapers/dossier_batch/escalate_eligible.py`, which reads Pass-1 dossiers from `practice_intel`, filters by `_should_escalate()`, and submits Sonnet escalation batches.

The `_should_escalate()` function itself (lines 377-404) is correctly gated: never escalates unlikely/unknown/low readiness; escalates high/medium readiness when confidence != "high"; escalates with 5+ green flags AND partial/insufficient evidence.

### P0-H: GDN Parser Fragment Bug

**Root cause:** `extract_target()` regex character class `_N` included whitespace, so phrases like "Smith Dental which is located" were captured as the target name. No stop-word termination.

**Fix:** Added `_TARGET_STOP_WORDS` set (`which`, `located`, `headquartered`, `based`, `situated`, `operating`, `serving`, `providing`, `offering`, `established`) and `_clean_target()` helper that strips trailing stop words from captured names. Applied to both inverted and standard pattern branches. Also extracted `_GENERIC_WORDS` set to reduce duplication.

### P0-I: test_sync_resilience.py Broken

**Root cause:** Two missing symbols in the mock stubs:
1. `PracticeLocation` not in the `scrapers.database` mock symbol list
2. `or_` and `and_` not on the `sqlalchemy` mock module

**Fix:**
1. Added `"PracticeLocation"` to the `for sym in [...]` list at line 39-42
2. Added `sa_mod.or_` and `sa_mod.and_` lambda stubs at lines 62-63

**Verification:** `python3 -m pytest scrapers/test_sync_resilience.py -v` — 14/14 pass (was 13/14 before, 0/14 with original PracticeLocation ImportError).

---

## Build Verification

```
$ cd dental-pe-nextjs && npm run build
▲ Next.js 16.1.6 (Turbopack)
✓ Compiled successfully in 20.5s
Running TypeScript ... ✓
21 routes (all ƒ dynamic except /_not-found)
```

## Test Verification

```
$ python3 -m pytest scrapers/test_sync_resilience.py -v
14 passed in 0.56s
```

---

## Remaining Blockers (User Action Required)

| Item | Action | Why |
|------|--------|-----|
| P0-C sync gap | Run `python3 scrapers/sync_to_supabase.py --tables practice_changes` | Re-syncs 9,293 rows from SQLite to Supabase |
| P0-G escalation | Run `python3 scrapers/dossier_batch/escalate_eligible.py` after accumulating Pass-1 dossiers | Fires Sonnet Pass-2 on eligible candidates |
| P0-H data repair | Existing deal rows with fragment targets (e.g. "Smith Dental which is located") need manual review/cleanup in SQLite | Parser fix prevents future fragments; historical data untouched |
| Deploy | Commit changes and push to `main` for Vercel auto-deploy | Changes are uncommitted |
| Live verify | After deploy, verify DBA names show correctly on Warroom, Launchpad, Job Market, Buyability | Only local build verified so far |

---

## Page Sweep Checklist

| Page | Route | Build OK | Display Name Fix Applied | Notes |
|------|-------|----------|--------------------------|-------|
| Home | `/` | Yes | N/A (no practice names in KPIs) | KPIs verified correct |
| Launchpad | `/launchpad` | Yes | Yes (track-list-card.tsx) | DBA-first in card heading + practiceSnapshot |
| Warroom | `/warroom` | Yes | Yes (ranking.ts) | DBA-first in target list + dossier + headline |
| Deal Flow | `/deal-flow` | Yes | N/A (shows deal names, not practice names) | |
| Market Intel | `/market-intel` | Yes | N/A (ZIP-level, no practice name display) | |
| Buyability | `/buyability` | Yes | Yes (buyability-shell.tsx) | DBA-first in table |
| Job Market | `/job-market` | Yes | Yes (practice-directory.tsx) | DBA-first in all 4 tab columns + CSV |
| Intelligence | `/intelligence` | Yes | N/A (uses NPI, not display name) | Pagination fix applied |
| Research | `/research` | Yes | N/A | |
| System | `/system` | Yes | N/A | |
| Data Breakdown | `/data-breakdown` | Yes | N/A | |

---

## New Findings During Debug

1. **P0-B, P0-E, P0-F were already fixed** in prior sessions — the audit caught stale state that had been resolved.
2. **`sortPractices()` needed generic typing** — the augmented `withDisplayName` type broke the `Practice[]` parameter. Fixed with `<T extends Practice>`.
3. **`filtered` useMemo had stale dependency** — referenced `practices` instead of `withDisplayName`. Fixed.
4. **practice_changes sync gap** is an operational issue (sync metadata reset from CASCADE), not a code bug. The `incremental_id` strategy works correctly.
5. **Batch escalation** is intentionally Pass-1-only with a documented follow-up path via `escalate_eligible.py`. Not a bug.
