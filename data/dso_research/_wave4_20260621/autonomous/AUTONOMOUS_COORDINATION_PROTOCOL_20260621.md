# Wave 4 Autonomous Coordination Protocol

Date: 2026-06-21
Scope: Chicagoland / Illinois only. Boston / Massachusetts is parked.

This protocol lets the four Claude Code sessions keep working while the user is away, using files as the coordination layer. It is evidence-only and reversible. No session may write to the DB, canonical manifest, current ready file, LEDGER, PROGRESS, ownership_tier, entity_classification, or ownership_status.

## Hard Locks

1. Consolidation is frozen. Do not run `consolidate_census.py --allow-db-write`.
2. The protected consolidation trigger phrase is not authorized. Do not say it as an instruction to execute.
3. Current reset invariant must remain true:
   - `practice_locations.ownership_tier IS NOT NULL` = 0
   - `practices.ownership_tier IS NOT NULL` = 0
   - `RESEARCH_HOME/LEDGER.jsonl` = 1 line
   - `PROGRESS.json` reviewed = 0 and `undetermined_unreviewed` = 4439
   - DB md5 baseline = `0dec26135bb4d6ee490dc16cfe892ca6`
4. The canonical manifest remains read-only until QA passes a specific Gate-normalized addendum:
   - `data/dso_research/consolidation_candidate_manifest_20260621.json`
5. The current ready file remains unchanged:
   - `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json`
6. No broad AO reach=2 long tail.
7. No deterministic Fleet B re-mining.
8. AO reach is a discovery signal only, never proof.
9. DSO tier requires structure: MSO / management company / platform / established DSO brand. PE backing is orthogonal.
10. Preserve sidecar metadata. Do not flatten away operator/family/brand/legal-entity/evidence-chain/stale-closed fields.

## User Decisions While Away

Use these conservative defaults until the user returns:

1. No new protected-network releases. LABINOV, AQEL, BELKIC, SWEIS, RAMAHA, SHAFI, NITTINGER, and BRUNETTI remain held unless already explicitly released in the existing manifest.
2. Affordable Dentures and ClearChoice remain held out of the GP floor as specialist/tooth-replacement scope questions. Do not add them to GP ready. If they are already in the current 310, flag for QA rather than silently retaining.
3. Fleet B current-ready overlaps are corroborations, not additions.
4. Any row with unresolved closed/relocated status, same-door nuance, medium confidence, AB9, or scope flag is a hold unless Gate resolves it in a written normalization file and QA agrees.

## Current Inputs

Pre-QA criteria:
- Authoritative: `data/dso_research/ownership_manifest_QA_wave4_pre_criteria_20260621.json`
- Secondary stricter cross-check: `data/dso_research/ownership_manifest_QA_wave4_preQA_criteria_20260621.json`
- Reconciliation: `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`

Wave 4 evidence outputs ready for Gate normalization:
- Main AO: `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621.json`
- Main AO self-QA: `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621_qa.json`
- Fleet B top 50: `data/dso_research/_wave4_20260621/wave4_lane3_phasec_top50_evidence_20260621.json`

Work packets:
- Lane 1 conflicts: `data/dso_research/_wave4_20260621/wave4_packet_lane1_conflicts.json`
- Lane 2 backfill: `data/dso_research/_wave4_20260621/wave4_packet_lane2_backfill.json`
- Lane 3 hard leads: `data/dso_research/_wave4_20260621/wave4_packet_lane3_hardleads.json`

## File-Based Coordination

All autonomous coordination files live in:

`data/dso_research/_wave4_20260621/autonomous/`

Use these file types:

- `REQUEST_*`: Gate asks another role to act.
- `DONE_*`: a role says its requested work is complete.
- `BLOCKED_*`: a role found a decision that requires the user.
- `VERDICT_*`: QA review output.
- `HEARTBEAT_*`: optional short progress note.

Each role writes new files only. Do not edit another role's output except Gate may write a separate normalization or request file derived from it.

## Autonomous Flow

1. Gate Owner normalizes the Main AO and Fleet B outputs into:
   - `data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json`
2. Gate Owner writes:
   - `data/dso_research/_wave4_20260621/autonomous/REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md`
3. QA reviews the normalized partition plus evidence files and writes:
   - `data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json`
4. If QA returns MUST_FIX, Gate writes focused addendum requests to Main AO or Fleet B.
5. If QA returns PASS or PASS_WITH_HOLDS, Gate may prepare an evidence-only addendum candidate file, but must not merge it into the canonical manifest without explicit later approval.
6. After initial QA is requested, Main AO may work the bounded Lane 2 non-AO backfill packet (13 `locator_exact` + 12 `practice_intel`) if it has not already received a more specific Gate request.
7. Fleet B may not start ranks 51-100 unless Gate writes:
   - `data/dso_research/_wave4_20260621/autonomous/AUTH_FLEETB_PHASEC_51_100_20260621.md`
   Gate may write that only after current top-50 normalization exists and QA has not found a systemic Phase-C defect.

## Output Contract

Every evidence row must include:

- `location_id`
- `practice_name`
- `city`, `zip`, `state`
- `source_lane`
- `candidate_types` or network/gate network
- `proposed_tier`
- `pe_backed`
- `evidence_urls` and/or `durable_evidence` plus `evidence_source`
- `operating_status_check`
- `same_door_check`
- `protected_network_status`
- `dso_structure_rationale` for any T4/T5
- `disposition`
- `hold_reason` if held
- preserved sidecar fields when present

Allowed dispositions:

- `merge_eligible_new`
- `corroborates_existing_ready`
- `hold_needs_more_evidence`
- `hold_protected_network`
- `hold_scope_specialist`
- `hold_operating_status_or_same_door`
- `rejected`
- `refuted`

## Stop Conditions

Stop and write a `BLOCKED_*` file if:

- Any command would mutate the DB or canonical manifest.
- A user policy call is needed: protected-network release, Affordable/ClearChoice GP scope, or consolidation.
- A row would require broad AO reach=2 discovery.
- QA finds a systemic defect that invalidates a whole evidence lane.
