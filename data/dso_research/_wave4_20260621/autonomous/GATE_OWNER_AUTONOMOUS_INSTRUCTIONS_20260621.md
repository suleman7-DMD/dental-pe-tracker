# Gate Owner Autonomous Instructions

Read first:

1. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`
2. `data/dso_research/_wave4_20260621/autonomous/AUTONOMOUS_TASK_BOARD_20260621.json`
3. `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

You are coordinator / normalizer / dispatcher only. Do not research evidence. Do not mutate the DB, canonical manifest, ready file, LEDGER, PROGRESS, ownership_tier, entity_classification, or ownership_status. Do not run `--allow-db-write`.

## Immediate Job

Normalize these two evidence files:

- `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621.json`
- `data/dso_research/_wave4_20260621/wave4_lane3_phasec_top50_evidence_20260621.json`

Against:

- `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`
- `data/dso_research/ownership_manifest_QA_wave4_pre_criteria_20260621.json`
- `data/dso_research/ownership_manifest_QA_wave4_preQA_criteria_20260621.json`

Write one new file:

`data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json`

## Required Partitions

Use these buckets:

- `merge_eligible_new`
- `corroborates_existing_ready`
- `hold_needs_more_evidence`
- `hold_protected_network`
- `hold_scope_specialist`
- `hold_operating_status_or_same_door`
- `rejected`
- `refuted`
- `qa_attention_current_ready`

## User Defaults While Away

1. No protected-network releases. LABINOV, AQEL, BELKIC, SWEIS, RAMAHA, SHAFI, NITTINGER, BRUNETTI stay held unless already explicitly released in the existing manifest.
2. Affordable Dentures and ClearChoice stay held out of GP floor pending user scope decision.
3. Fleet B current-ready overlaps are corroborations, not net-new adds.
4. Any row with unresolved closed/relocated status, same-door nuance, medium confidence, AB9, or scope flag is a hold unless your normalization explicitly resolves it with evidence.

## Specific Known Issues To Preserve

- Fleet B ready overlaps with current 310:
  - `fd93e6934ac6c59c`
  - `64a25dd567a92ae3`
  - `b62beb82551b076f`
  - `58a87486cd2546e5`
  - `bd77120df3018393`
  - `199841c7ee233c17`
- `fd93e6934ac6c59c` is current-ready but now AB9 LABINOV protected. Put in `qa_attention_current_ready` and do not count as new.
- `bd77120df3018393` and `199841c7ee233c17` are current-ready but Affordable scope-flagged. Put in `qa_attention_current_ready`.
- Main AO has 21 release-eligible rows and 22 AO backfill holds.
- Main AO ready rows use `durable_evidence` / `evidence_source` rather than `evidence_urls`; preserve and normalize these into the evidence object.

## After Normalization

Write:

`data/dso_research/_wave4_20260621/autonomous/REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md`

Include paths to all evidence and normalization files. Then stop and wait for QA verdict.

## Optional Dispatch After QA Request

After the QA request file is written, you may allow Main AO to work the bounded Lane 2 non-AO backfill task by writing:

`data/dso_research/_wave4_20260621/autonomous/REQUEST_MAIN_AO_LANE2_BACKFILL25_20260621.md`

This is limited to 13 `locator_exact` + 12 `practice_intel` rows. No AO fan-out.

Do not authorize Fleet B ranks 51-100 until the normalized partition exists and QA has not found a systemic Phase-C defect.
