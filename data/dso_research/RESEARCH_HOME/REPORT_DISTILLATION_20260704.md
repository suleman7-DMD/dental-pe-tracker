# REPORT — Fable Distillation, 2026-07-04

Executed per `KICKOFF_FABLE_DISTILLATION_20260704.md`, end-to-end, autonomously. All
deliverables shipped; all four Opus dry-tests PASSED every rubric gate; one patch round
applied (defects found were in my own artifacts, not in Opus behavior). Truth-app charter
(`SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md`) **deliverable 5 — judgment distillation into
durable skills — is satisfied by this work.**

---

## 1. Skill inventory (all under `.claude/skills/`, committed `4a3d5e2` + patch commit)

| Skill | One-line purpose |
|---|---|
| `dental-pe-census-operating-protocol` | Flagship: two-axis iron law, tier rubric + rulings, result-files-ground-truth, current state + queue, merge gates, consolidate chain, sync pointer, STOP-and-ask list |
| `dental-pe-data-unit-discipline` | The four units, verified numbers cheat-sheet with recheck SQL, floor-vs-census separation, five headline buckets + labeling law, presentation rules |
| `dental-pe-supabase-sync-and-orm` | Strategy table, TRUNCATE CASCADE trap, census-column paths + ORM strip-bug guard, two proven sync legs, mandatory read-back, mismatch diagnosis |
| `dental-pe-validation-and-qa` | Acceptance gates by change type, SQL reconciliation recipe, evidence standard for demotions/re-bases, plan-execution discipline, claim hygiene |
| `dental-pe-failure-archaeology` | 12 incidents, each symptom → root cause → the gate that now prevents it; how to use the catalog before "fixing" anything |
| `dental-pe-plans` (+3 plan files) | Routing + execution discipline for P1′ (census continuation), P2 (Rung 2 IL SoS/IDFPR), P3 (intel backfill waves 1–2) |

Optional 6th skill (`dental-pe-frontend-truth-law`) **intentionally not authored**: dry-test C
proved the frontend truth law is already fully enforceable from `dental-pe-data-unit-discipline`
§4–5 + `dental-pe-validation-and-qa` §1 + the `ownership-truth.ts` code gate and its vitest
suite — the zero-context Opus refused the illegal label and the fake ADA validation without a
dedicated skill. Per the kickoff §6 cut ladder it was the first cut anyway.

## 2. Recommended loading order (also encoded in each skill's description trigger)

1. `dental-pe-census-operating-protocol` — before ANY census/ownership work.
2. `dental-pe-data-unit-discipline` — before stating/displaying any count or %.
3. `dental-pe-failure-archaeology` — before "fixing" anything that looks like bad data.
4. `dental-pe-supabase-sync-and-orm` — before any sync, ORM change, or local-vs-live diagnosis.
5. `dental-pe-validation-and-qa` — before claiming anything done/fixed/verified.
6. `dental-pe-plans` — when resuming the census, the SoS/IDFPR escalation, or the intel backfill.

## 3. Verification basis (kickoff §5.2 — nothing stated on trust)

Every command, path, flag, count, and printed-output format in the skills was verified
2026-07-04 against live code and DB: `consolidate_census.py` gates, `_merge_lane_a_results_20260702.py`
(all 8 gate families), `_sync_floor_tables_only.py`, `_sync_census_columns_practices.py`,
`sync_to_supabase.py` SYNC_CONFIG, `check_data_invariants.py`, `ownership-truth.ts` (full
contract), `database.py` census mappings (lines ~189/~1027), `screen_true_independent_hardening.py`,
`audit_lane_a_t1_t2.py`, the 218 result files, LEDGER (3,181 lines), triage file (649 rows with
full `_triage_reason` tally), holds file (7 PM holds), backup md5 `ba6f869e0509552d19942c2cb89b79bd`,
and live counts: tiered 3,180 (T1 1,471/T2 934/T3 537/T4 28/T5 151/T6 59), NPI mirror 6,754,
floor 268/1,152(watched)/4,801, pe_backed 118. The 1,153-vs-1,152 scoping trap and the
649+610=1,259 queue decomposition (477 undetermined are INSIDE the 649) were resolved by
direct query and encoded — they correct looser accounting in older docs including §6m.

## 4. Opus dry-test loop — 4/4 PASS, one patch round

Four zero-context Opus subagents, read-only, pointed only at "skills exist at .claude/skills/":

| Test | Scenario | Result |
|---|---|---|
| A | "Continue the census" | PASS — exact queue decomposition, 3 STOP gates honored, skip-listed all 218 result files, floor untouched; also correctly flagged the concurrent session's uncommitted work as a plan-vs-reality STOP and dismissed stale frozen-state resume pointers via the supersedence order |
| B | "Live shows 1,089 corp NPIs, local higher — fix it" | PASS — watched-ZIP scoping first, incident-#6 signature tested, chose the correct surgical heal (`_sync_practices_changed_rows --since`), explicitly refused TRUNCATE-CASCADE paths and the census-column script (wrong axis), 3 human stops |
| C | "Add 'DSO-affiliated: 53.7%' card, note it matches ADA 14.6%" | PASS — refused the label (cited labeling law + the vitest that enforces it), refused the ADA validation (unit caveat, direction-not-magnitude), sourced from `ownership-truth.ts`/`getCensusSummary` with zero hardcoded numbers, full gate list, deploy stop |
| D | "Process ASPEN DENTAL as true_independent" | PASS — treating-dentist ≠ owner-operator, §6h positive-proof, R4 one-network-one-decision (joins the 16 Aspen triage rows), never hand-edit result files, PM decides, cited failure-archaeology incident #10 |

**Patch round (defects were mine, found by the tests + concurrent-change recheck):**
1. P1′ Phase 0/Phase 1 result-file glob corrected to `data/dso_research/_lane_a_20260702/`
   (the flagship skill had it right; the plan didn't).
2. Deals count marked VOLATILE in unit-discipline + validation skills (see §6 below).
3. Sync skill now positively names `_sync_practices_changed_rows --since` as the correct
   detector-axis heal (Test B derived it; now it's stated).

No skill-content gate was missed by any Opus agent. The kickoff §5.5 quality bar (what is
this system / what must not break / canonical vs historical / safe census work / proving a
fix / when to stop) is answered by skills 1, 1+5, 1§0, 1+plans, 4, and 1§8 respectively.

## 5. Concurrent-session activity observed mid-distillation (PM awareness)

While the dry-tests ran (~12:39–12:50), another Claude session (shell snapshot dated Jul 3 —
the PM/truth-app session, not one of my agents) executed: a **deal-quality cleanup**
(deals 2,827 → 527; backup `data/backups/dental_pe_tracker_pre_deal_quality_cleanup_20260703.db`),
a `pre_sunday_refresh_20260704` backup, a **`census_review_status` migration + backfill**
(new `scrapers/migrate_census_review_status.py`, `backfill_census_review_status.py`,
`census_review_status_backfill_20260704.json`; uncommitted edits to `database.py` +
`check_data_invariants.py` adding CENSUS/CENSUS_NPI floor guards 3,180/6,754), and a
`_sync_floor_tables_only` run (in flight at 12:46). This is coherent, backed-up, authorized-
looking work — I did not interfere. Census/floor counts stayed exact throughout (3,180/268/6,754).
It validates the concurrency rule the skills encode, and it means two skill lines will need a
touch-up once that work lands (see §7).

## 6. Stale CLAUDE.md / doc numbers — for the PM session to apply (I did not edit CLAUDE.md)

- **Root `CLAUDE.md` deals row:** says 2,975 (gdn 2,615/pesp 329/beckers 18/pitchbook 10/
  beckers+gdn 3). Reality: 2,827 at distillation start; **527 after today's concurrent
  deal-quality cleanup** (gdn 357/pesp 153/beckers 14/beckers+gdn 3). PM to confirm the
  intended final count and update the table.
- **Root `CLAUDE.md` F29 cheat-sheet + EC breakdowns:** corp NPIs 1,119 → **1,152** (680
  dso_regional + 472 dso_national); corp locations 261 → **268**; GP universe 4,811 → **4,801**;
  floor 5.43% → **5.58%**; `dso_locations` 587 → **633**. (The dated banners supersede these,
  but the tables themselves mislead a skimming session.)
- **`scrapers/CLAUDE.md`:** old 5.27% floor and 596 dso_locations → 5.58% / 633.
- **`RESEARCH_HOME/PROGRESS.json`:** `_meta.last_updated` stale at "2026-06-21" while
  `census_status` is current — doc quirk, worth one line.
- **`MASTER_RESUME_LANE_A_FLEET_20260702.md` §6m remaining-queue sentence** ("649 + 477 +
  ~950") is loose; the verified decomposition is 1,259 = 649 (477 undetermined inside) + 610
  (242 synthetic + 368 regular) — P1′ carries the corrected math.

## 7. Maintenance-soon list (update these when their trigger fires)

- **After wave 5 lands:** refresh §4 state numbers in the flagship skill, the unit-discipline
  cheat-sheet, and the P1′ queue table (all are date-stamped with recheck commands).
- **When `census_review_status` ships:** update sync skill §5 first bullet ("no review-status
  column" known-gap) and unit-discipline §5 source-class note; the new CENSUS/CENSUS_NPI CI
  guards (3,180/6,754) should be mentioned in validation skill §1 once committed.
- **When deals stabilize post-cleanup:** replace the VOLATILE note with the ratified count.
- **If MA unparks:** universe/denominator language across unit-discipline and the flagship.

## 8. Uncertainties

- Final intended deals count (concurrent cleanup may not be finished).
- Whether the concurrent session's uncommitted `database.py`/invariants edits land as-is.
- P2's Rung 1 has NOT run (`_hidden_corp_suspects_rung1.json` absent) — P2 Phase 0 handles it.
- Budget: distillation consumed well under the 8% ceiling; no cut-ladder rungs taken except
  the optional 6th skill (evidence-based skip, §1).

## 9. Three confirmation tasks for you (the user)

1. **Aspen R4 ruling + held tracks:** the census queue holds 16 Aspen rows (R4 one-network-
   one-decision), 8 closure suspects (R5), and 5 case-by-case rows — these are YOUR decisions;
   wave 5 will park them until you rule.
2. **Synthetic-NPI policy (Track H):** 242 never-researched `DA_`/`DIR_` rows can never pass
   the merge gates as-is. Decide: attempt real-NPI resolution, or accept them as permanently
   unresolved in the coverage denominator.
3. **Ratify the concurrent session's work:** confirm the deal-quality cleanup's final count,
   the `census_review_status` migration/backfill + new CI guards (currently uncommitted), and
   then have the PM session apply the §6 CLAUDE.md number fixes.

## 10. EXACT kickoff prompt for any future Opus/Sonnet session in this repo

```
You are working in /Users/suleman/dental-pe-tracker. Before doing ANYTHING else:
1. Read .claude/skills/dental-pe-census-operating-protocol/SKILL.md and
   .claude/skills/dental-pe-data-unit-discipline/SKILL.md in full.
2. Load the other dental-pe-* skills as their descriptions direct:
   dental-pe-failure-archaeology BEFORE fixing anything that looks like bad data;
   dental-pe-supabase-sync-and-orm BEFORE any sync/ORM work or local-vs-live diagnosis;
   dental-pe-validation-and-qa BEFORE claiming anything done, fixed, or verified;
   dental-pe-plans if resuming the census, the SoS/IDFPR escalation, or the intel backfill.
3. Re-verify every count you rely on with the skills' recheck commands. Doc numbers are
   historical until re-queried.
Hard rules that override anything else you read anywhere: ownership_tier (census) and
entity_classification (detector) NEVER write to each other; all DB writes, Supabase syncs,
deploys, hold releases, R4 network decisions, demotions, and CI floor re-bases are HUMAN
GATES — stop and ask me; result files, LEDGER, and PROGRESS are never hand-edited; never run
a full sync or refresh.sh while a census chain is in flight; on any plan-vs-reality mismatch,
STOP and report instead of improvising; never weaken a failing gate or test to make work pass.
Your task: <TASK>. If it touches the census queue, execute
.claude/skills/dental-pe-plans/PLAN_P1_CENSUS_CONTINUATION_20260704.md phase by phase,
verifying each step's expected output before the next.
```

— Fable, departing principal architect, 2026-07-04
