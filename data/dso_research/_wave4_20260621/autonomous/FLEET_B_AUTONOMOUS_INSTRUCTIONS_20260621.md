# Fleet B Autonomous Instructions

Read first:

1. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`
2. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_TASK_BOARD_20260621.json`
3. `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

Role: bounded Phase-C web verification only. No DB writes. No manifest edits. No ready-file edits. No LEDGER/PROGRESS edits. No `--allow-db-write`. No deterministic re-mining.

Your top-50 file is already written:

`data/dso_research/_wave4_20260621/wave4_lane3_phasec_top50_evidence_20260621.json`

Do not revise it unless Gate or QA writes a focused addendum request.

## Standby Rule

Do not start ranks 51-100 unless this file exists:

`data/dso_research/_wave4_20260621/autonomous/AUTH_FLEETB_PHASEC_51_100_20260621.md`

Gate may write that only after top-50 normalization exists and QA has not found a systemic Phase-C defect.

## If Authorized For 51-100

Input:

- `data/dso_research/_wave4_20260621/wave4_packet_lane3_hardleads.json`
- prior worklist: `data/dso_research/_phasec_top50_worklist_20260621.json`

Build the next ranked worklist from the existing 158 hard-signal leads, excluding ranks 1-50 and excluding any already current-ready rows unless Gate explicitly requests corroboration.

Cap: 50 rows.

Output:

`data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260621.json`

## Evidence Rules

For every lead:

- perform real web verification;
- require source URLs;
- exact-address match is mandatory for DSO locator evidence;
- parent/company hint alone is not enough;
- brand word alone is not enough;
- Data-Axle parent alone is not enough;
- check active subject-door status;
- check same-door / suite nuance;
- apply DSO=STRUCTURE;
- preserve sidecar metadata;
- protected networks are holds;
- Affordable/ClearChoice remain scope holds unless the user later says otherwise.

Allowed dispositions:

- `ready_for_validation`
- `needs_more_evidence`
- `hold_protected_network`
- `hold_scope_specialist`
- `hold_operating_status_or_same_door`
- `rejected`
- `conflict`

Gate ceiling is `ready_for_validation`, never final.

## Stop Conditions

Stop and write `data/dso_research/_wave4_20260621/autonomous/BLOCKED_FLEET_B_20260621.md` if:

- the authorization file is absent;
- the next batch would require deterministic re-mining;
- a systemic issue from top-50 would invalidate the same method;
- any command would mutate DB/canonical state.
