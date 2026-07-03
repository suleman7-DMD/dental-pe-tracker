# QA Autonomous Instructions

Read first:

1. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`
2. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_TASK_BOARD_20260621.json`
3. `data/dso_research/ownership_manifest_QA_wave4_pre_criteria_20260621.json`
4. `data/dso_research/ownership_manifest_QA_wave4_preQA_criteria_20260621.json`
5. `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

Role: independent adversarial QA. Review-only. Write new verdict files only. No DB writes, no manifest edits, no ready-file edits, no LEDGER/PROGRESS edits, no prior-QA edits.

## Wait Condition

Do not review until this file exists:

`data/dso_research/_wave4_20260621/autonomous/REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md`

Then review only written files. Do not review chat summaries.

## Expected Inputs

- `data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json`
- `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621.json`
- `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621_qa.json`
- `data/dso_research/_wave4_20260621/wave4_lane3_phasec_top50_evidence_20260621.json`
- `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

## Review Focus

Apply AB1-AB12 plus the stricter secondary criteria. Specifically verify:

- no AO-only promotion;
- no brand-substring-only promotion;
- every promoted row has durable on-disk evidence;
- T4/T5 has DSO=STRUCTURE rationale;
- `pe_backed` is orthogonal;
- `true_independent` is earned;
- closed/stale subject-door scan was applied;
- same-door / same-phone / duplicate-door hazards were held or resolved;
- protected-network rows were held unless explicitly released in the prior manifest;
- Webster remains held unless whole-network adjudication is accepted;
- sidecars are preserved;
- Fleet B rows with AB9, scope, same-door nuance, medium confidence, or closed/relocated status are held unless Gate resolved them in writing.

Known current-ready QA attention:

- `fd93e6934ac6c59c` current-ready + AB9 LABINOV flag.
- `bd77120df3018393` current-ready + Affordable scope flag.
- `199841c7ee233c17` current-ready + Affordable scope flag.

## Output

Write:

`data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json`

Include:

- verdict: PASS / PASS_WITH_HOLDS / MUST_FIX / FAIL
- exact location_ids for every MUST_FIX
- bucket-count reconciliation
- current-ready overlap audit
- zero-write proof: DB md5, ownership_tier counts, LEDGER lines, PROGRESS reviewed/undetermined

Do not request or perform consolidation.
