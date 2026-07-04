---
name: dental-pe-plans
description: Load when asked to CONTINUE or RESUME major workstreams in this repo - the ownership census (finish the remaining untiered IL GP locations), the hidden-corporate escalation (IL SoS/IDFPR Rung 2), or the practice-intel backfill for Lane A waves 1-2. Routes to the authored plan artifacts in this directory and states the execution discipline that applies to ALL of them.
---

# Plan Registry + Execution Discipline

This directory holds ready-to-execute plan artifacts distilled 2026-07-04 from the ratified
source plans. Each plan step carries: the action, the verification command, the expected
output, and the hasty-model trap it guards against.

## Routing

| User asks for… | Execute | Source of truth it wraps |
|---|---|---|
| "continue the census", "finish the remaining practices", "wave 5", "work the triage queue" | `PLAN_P1_CENSUS_CONTINUATION_20260704.md` (this dir) | `RESEARCH_HOME/MASTER_RESUME_LANE_A_FLEET_20260702.md` (esp. §6m) |
| "hidden corporates", "IL SoS", "IDFPR", "Rung 2", "MSO hunting" | `PLAN_P2_RUNG2_IL_SOS_IDFPR_20260704.md` (this dir) | `RESEARCH_HOME/PLAN_HIDDEN_CORPORATE_ESCALATION_20260703.md` |
| "intel backfill", "waves 1-2 intel", "practice_intel gaps" | `PLAN_P3_INTEL_BACKFILL_20260704.md` (this dir) | `RESEARCH_HOME/PLAN_INTEL_BACKFILL_WAVES_1_2_20260702.md` |

If a plan here conflicts with live code or a newer dated doc, the live code / newer doc wins —
STOP and report the conflict rather than executing the stale step.

## Non-negotiable execution discipline (all plans)

1. **Load the core skills first:** `dental-pe-census-operating-protocol`,
   `dental-pe-data-unit-discipline`, `dental-pe-validation-and-qa` — plus
   `dental-pe-supabase-sync-and-orm` before any sync step.
2. **Phase 0 always runs.** Every plan opens with a preflight that re-verifies the counts it
   assumes. If preflight numbers differ from the plan's, the plan is stale — report, don't
   improvise.
3. **One step at a time.** Run the step's verification command and compare to expected output
   BEFORE the next step. Bank each verified milestone (counts, md5s, file paths) in a session
   note.
4. **Human gates stay human.** DB writes (`--allow-db-write`), all Supabase syncs, network-level
   decisions (R4), demotions/re-bases, and spending money (API batches) each require the user's
   explicit go in THIS session. A plan step saying "then sync" is an instruction to ASK, not
   to run.
5. **Result files are ground truth.** Never re-research a unit that has a result file; never
   hand-edit result files, verdicts, LEDGER, or PROGRESS.
6. **No scope creep.** A step that turns out to require touching files outside the plan's
   declared write-set is a STOP condition.

## Common hasty-model failures

- Executing a plan's commands without Phase 0, on top of a DB the plan no longer describes.
- Treating the plan artifact as authority over the live merge/consolidate code (the code's
  gates win; plans describe, code enforces).
- Editing the dated historical scripts in place instead of making a new dated copy for a new
  wave.
- Batch-running all steps then verifying once at the end.
