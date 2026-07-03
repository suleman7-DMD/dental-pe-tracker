# Main AO Autonomous Instructions

Read first:

1. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`
2. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_TASK_BOARD_20260621.json`
3. `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

Role: bounded evidence work only. No DB writes. No manifest edits. No ready-file edits. No LEDGER/PROGRESS edits. No `--allow-db-write`. No broad AO reach=2 long tail.

Your Lane 1 conflict/AO-backfill file is already written:

`data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621.json`

Do not revise it unless Gate or QA writes a focused addendum request.

## Autonomous Next Work

If you have no focused addendum request, work this bounded evidence packet:

Input:

`data/dso_research/_wave4_20260621/wave4_packet_lane2_backfill.json`

Only work rows where:

- `backfill_lane == "locator_exact"`, or
- `backfill_lane == "practice_intel"`

Expected count: 25 rows (13 locator_exact + 12 practice_intel). Do not work AO_network rows. Do not work unlaned rows unless Gate writes a separate request.

Output:

`data/dso_research/_wave4_20260621/wave4_lane2_non_ao_backfill25_evidence_20260621.json`

Also write a short self-QA:

`data/dso_research/_wave4_20260621/wave4_lane2_non_ao_backfill25_evidence_20260621_qa.json`

## Evidence Rules

For every row:

- perform real web verification;
- cite actual URLs or durable artifacts;
- check active subject-door status;
- check same-door / phone duplicate risk;
- apply DSO=STRUCTURE for T4/T5;
- never default to true_independent;
- if evidence is weak, set disposition `hold_needs_more_evidence`;
- if protected network is touched, hold and flag;
- if specialist / non-GP scope appears, hold scope rather than promote.

Allowed dispositions:

- `ready_for_validation`
- `hold_needs_more_evidence`
- `hold_protected_network`
- `hold_scope_specialist`
- `hold_operating_status_or_same_door`
- `rejected`
- `refuted`

Gate ceiling is `ready_for_validation`, never final.

## Stop Conditions

Stop and write `data/dso_research/_wave4_20260621/autonomous/BLOCKED_MAIN_AO_20260621.md` if:

- the work would require broad AO discovery;
- the work would require a protected-network release;
- the row cannot be resolved without a user policy decision;
- any command would mutate DB/canonical state.
