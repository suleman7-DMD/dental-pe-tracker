---
name: dental-pe-validation-and-qa
description: MANDATORY before claiming ANY task in this repo is done, fixed, verified, or safe to commit/deploy — code changes, data fixes, frontend edits, pipeline runs, reclassifications, or plan steps. Defines the acceptance gates (build, tests, invariants, SQL reconciliation) and the evidence standard for demotions/re-bases. Load it when writing "done", "fixed", "verified", or before any commit.
---

# Validation & QA Gates

The operating standard: **a step is done only when its verification output is pasted.** Not
"the script ran", not "it should work now". Predict the number a command will print BEFORE
running it; a surprise result is a finding, not noise.

## 1. Acceptance gates by change type

| You changed… | You must run… | Pass looks like |
|---|---|---|
| Frontend code (`dental-pe-nextjs/`) | `npm run build` then `npx vitest run` | Build completes with 0 type errors; all tests pass — including `classification-primary.test.ts` (F27) and the ownership-truth-law tests |
| Python pipeline / data | The relevant script with `--validate-only`/`--dry-run` first, then SQL reconciliation (§2) | Predicted counts match actual |
| Anything touching Supabase | Read-back per the `dental-pe-supabase-sync-and-orm` skill | Live = local, exactly |
| CI invariants / floors | `python3 scripts/check_data_invariants.py` (needs `SUPABASE_URL` + `SUPABASE_ANON_KEY` env) | FLOOR ≥268, FLOOR_NPI ≥1152, F02=0, F01=0; summary "0 failure(s)" |
| Census artifacts | `consolidate_census.py … --validate-only` | "Validation OK", 0 errors |

`npm run build` after EVERY frontend change is non-negotiable — TypeScript strictness is a
load-bearing gate here, not a formality.

## 2. SQL count reconciliation (the universal data gate)

Before/after any data-touching change, snapshot the counts the change should and should NOT
move:

```bash
sqlite3 data/dental_pe_tracker.db "
SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL;   -- census (3180 @2026-07-04)
SELECT COUNT(*) FROM practice_locations
  WHERE entity_classification IN ('dso_regional','dso_national');           -- floor (268)
SELECT SUM(total_gp_locations) FROM zip_scores;                             -- universe (4801)
SELECT COUNT(*) FROM deals;                                                 -- deals (2827)
"
```

Write down the prediction, run, compare. Any count that moved when it shouldn't have = STOP,
investigate, report. Do not proceed on top of an unexplained delta.

## 3. Evidence standard for demotions and re-bases

Any change that DEMOTES data (corporate→independent, tier removal, row exclusion) or RE-BASES
a guarded number (FLOOR/FLOOR_NPI expect_min) requires:
1. A dated evidence file in `data/dso_research/` listing every affected id with per-row
   reasoning (pattern: `il_false_corporate_demotions_20260612.json`).
2. A user decision recorded before execution (these are human-gated).
3. The CI guard note updated in the same change explaining the new baseline's derivation.
Undocumented demotions are indistinguishable from data corruption — the FLOOR guard exists
because a refresh once silently reverted verified promotions.

## 4. Plan-execution discipline

- Execute plans step-by-step; run each step's verification command before starting the next.
- **STOP on plan-vs-reality mismatch.** If a file, count, or behavior differs from what the
  plan says you'll find, do not improvise a workaround or "fix" reality to match the plan.
  Report the mismatch and wait.
- No scope creep: a plan step that turns out to need out-of-scope edits is a stop condition,
  not an invitation.
- Bank milestones: after each verified step, record what was proven (counts, outputs, paths)
  in the session log or handoff doc so a crash doesn't lose the proof.

## 5. Claim hygiene

- Report failures faithfully: paste failing output, don't summarize it away.
- If a step was skipped, say so explicitly.
- Never round, estimate, or "approximately" a number you can query exactly.
- Date-stamp every volatile number and pair it with its recheck command.
- Distinguish "I verified X" (output pasted) from "the doc says X" (inherited claim).

## 6. Common hasty-model failures

- Declaring done from exit code 0 without reading the output.
- Running verification once at the end instead of per-step, so a mid-plan failure poisons
  everything after it.
- "Fixing" a failing test by weakening the assertion (F27 and the truth-law tests encode
  ratified user decisions — a failure means YOUR change is wrong).
- Re-basing a floor guard to make CI green instead of investigating the drop.
- Verifying against the doc's stale number instead of a fresh query.

## 7. Minimum proof before continuing

For the change type you made, every gate in §1 run fresh, output pasted, predictions stated
beforehand. If any gate cannot be run (missing env, missing approval), say so explicitly and
stop — an unrunnable gate is not a passed gate.
