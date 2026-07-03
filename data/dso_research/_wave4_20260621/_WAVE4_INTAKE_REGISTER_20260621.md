# Wave 4 — INTAKE REGISTER (Gate Owner, coordination only)

**Authoritative gate:** `ownership_manifest_QA_wave4_pre_criteria_20260621.json` (AB1–AB12).
**Consolidation:** FROZEN. No `--allow-db-write`. 310 ready file (`_ready_to_validate_wave3_fixed_20260621.json`) untouched.
**Reset invariant @ intake:** PL/P tier nonnull 0/0 · LEDGER 1 line · PROGRESS undetermined 4439 ✓ (re-verified).

## Deliverable tracker
| Lane | Scope | Owner | Expected on-disk artifact | Status |
|------|-------|-------|---------------------------|--------|
| L1 Conflicts | 74 (6 networks, whole-network adjudication) | **Main AO** | `wave4_*conflicts*` evidence file, one tier/network + AB3/AB4 evidence | ⏳ awaiting |
| L2 AO backfill | AO_network 22 + reach3/4/lane1B AO rows | **Main AO** | `wave4_*backfill*` evidence file, named missing_evidence satisfied | ⏳ awaiting |
| L2 non-AO backfill | locator_exact 13 + practice_intel 12 | **UNCLAIMED** | — | ⚠️ coverage gap — flagged to user; NOT self-dispatched |
| L3 Phase-C | top-50 of 158 hard leads | **Fleet B** | `wave4_*phasec*`/Fleet B evidence file w/ transcribed URLs | ⏳ awaiting |

## Intake reconciliation (read-only, AB12) — `wave4_intake_hardlead_reconciliation_20260621.json`
158 asserted hard-signal leads → **0 with transcribed URL**, 1 EIN value, 39 brand-token, 118 assertion-only.
⇒ None currently clear AB1–AB3. The 158 is a Phase-C STARTING POOL; each must earn a transcribed durable
artifact individually. Expect Fleet B's top-50 output to add the URLs that are missing today.

## Acceptance rule (run per returned file)
Accept ONLY files under `_wave4_20260621/` or clearly-named `wave4_*` artifacts. The on-disk file is the
source of truth — agent summaries are not evidence. For each row, run AB1–AB12 + the 14-item checklist;
partition into `merge_eligible` vs `hold` (with named backfill_lane / undetermined). **No partial credit.**
Then request a fresh independent QA verdict BEFORE any manifest merge. Manifest stays unmutated until QA PASS.

## Secondary cross-check — RECONCILED ✓ (`wave4_criteria_reconciliation_20260621.json`)
Internal `QA_preQA_criteria` agent emitted `ownership_manifest_QA_wave4_preQA_criteria_20260621.json`
(distinct filename — **neither QA file overwritten**). Both read fully on-disk. **Finding: no substantive
contradiction** — the secondary is a more granular elaboration of the same AB1–AB12 / DSO=STRUCTURE bar.
**Enforced rule = UNION, stricter-wins.** One real conflict resolved empirically: the secondary's
`db_md5_baseline` typo (`…dc26…`, 2 of 3 spots) vs the verified baseline — live DB md5 = `…dc16…`
(`0dec26135bb4d6ee490dc16cfe892ca6`), matching RE-QA #5 + `pre_criteria` + the secondary's own GO-12.
**Enforced baseline md5 = `…dc16…`.** Stricter elements adopted into the net bar: HB5/HB6/HB10, AH3
(no retrospective web_verified assertion), mandatory `searches_executed`/`search_queries` provenance,
`still_insufficient → evidence_urls: []`, L3-1 (158 leads w/o transcribed artifact → general pool), and
the secondary's 12-step decision tree as the operative per-row normalization order. Authoritative-only
items (14-item checklist, per_input_merge_gates, output_contract) retained in the union.
**Freeze re-verified at reconciliation:** md5 `…dc16…` · LEDGER 1 line · undetermined_unreviewed 4439 ✓.

## Log
- 2026-06-21: intake complete; packets + plan + hardlead reconciliation written; awaiting fleet outputs.
- 2026-06-21: secondary pre-QA criteria file reconciled (stricter-wins, no overwrite); md5-typo conflict
  resolved empirically to `…dc16…`; net enforced bar = AB1–AB12 + HB1–HB10 + AH1–AH7 + 12-step tree +
  union of both gate-owner checklists. Standing by for Main AO / Fleet B evidence outputs.
- 2026-06-21: **GATE-001 DONE.** Main AO Lane-1 (96) + Fleet B Phase-C top-50 normalized into
  `wave4_gate_normalized_partition_20260621.json` (deterministic generator `_gen_gate_partition_20260621.py`).
  Reconciles 146 placements = 96 + 50, balanced; 145 distinct (1 cross-lane dup `f3959b4a9ac8e139` SILVA,
  both nme). Buckets: merge_eligible_new **19** (DentalTown 9 T3 + Precision 8 T3 + r35 T5 + r41 T5;
  none in 310) / corroborates 3 / qa_attention 3 (fd93 AB9+closed, bd77 & 199 Affordable-scope, all in 310) /
  hold_protected 46 / hold_scope 7 / hold_ops_samedoor 5 / hold_nme 43 / rejected 14 / refuted 6.
  Gate overrode agent "ready" on Sonrisa 4 FQHC doors (AB3/AH3 + FQHC T6-vs-T4 unresolved → hold).
  No protected releases; Affordable/ClearChoice held out of GP floor. Freeze re-attested intact
  (md5 `…dc16…` · LEDGER 1 · undetermined 4439).
- 2026-06-21: **GATE-002 DONE.** Wrote `autonomous/REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md` (all evidence +
  normalization + criteria paths; 8 QA-attention items surfaced). **STOPPED — awaiting QA verdict
  `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` (QA-001).** No further dispatch (Lane-2 backfill /
  Fleet B 51-100) until QA returns and finds no systemic Phase-C defect.
- 2026-06-21: **QA-001 RETURNED** `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` = **PASS_WITH_HOLDS**,
  `systemic_defect_found: false` (3 carry-forward holds: LABINOV stale_closed re-scan, Affordable GP-scope
  user decision, T5 dso_structure_rationale null-field). No systemic Phase-C defect ⇒ Fleet B 51-100 cleared.
- 2026-06-22: **GATE-003 DONE (Lane-2 normalization, files-only, zero mutation).** Normalized Main AO's Lane-2
  non-AO backfill (25 rows; written after the initial partition, NOT in QA-001 scope) into
  `wave4_gate_normalized_lane2_partition_20260622.json` (generator `_gen_gate_lane2_partition_20260622.py`).
  Reconciles 25/25 balanced; 25 distinct; 310-overlap **0**. Buckets: merge_eligible_new_corporate **1**
  (Schock Dental→Dentologie River North `5cd692a50e5c32b7`, the ONLY +1 net-new corporate) /
  corroborates_existing_corporate_no_lift **12** (10 Heartland DPI-PC + DCA New Lenox + Aspen TAG — already
  corporate by entity_classification, **0 floor lift**) / true_independent_confirmation **2** (Jova,
  Bellido-Griffin — earned T1, NOT corporate) / hold_needs_more_evidence 2 (Bloomingdale **SWEIS-held**,
  Midwest Dental Group) / hold_operating_status_or_same_door 2 (Kang same-door, Obucina) / hold_scope_specialist
  3 (IWS + Heartland Intl + Heartland Outreach FQHC/nonprofit — Heartland NAME-collision guard preserved) /
  refuted 3 (Warga, Batchelor, Northwestern substring-FP). **Floor impact NOT overstated: +1 net-new corporate
  only.** 3 legacy-corporate false-positive suspects (Northwestern refuted, Midwest + Bloomingdale held)
  flagged to QA, **NOT mutated**. Wrote `autonomous/REQUEST_QA_REVIEW_WAVE4_LANE2_20260622.md` (QA-002 request).
  **AUTHORIZED Fleet B 51-100** via `autonomous/AUTH_FLEETB_PHASEC_51_100_20260621.md` (files-only; ranks 51-100;
  exclude 1-50 + 310 unless corroborating; no re-mining; no DB/manifest/ready/LEDGER/PROGRESS writes;
  Affordable/ClearChoice scope-held; protected networks held; output requires fresh QA). Freeze re-attested
  intact (md5 `…dc16…` · LEDGER 1 · undetermined 4439). **No manifest merge, no new ready file. STOPPED.**
- 2026-06-22: **QA-002 RETURNED** `autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json` = **PASS_WITH_HOLDS**,
  0 MUST_FIX, `systemic_defect_found: false`, **+1 net-new corporate claim independently verified & not
  overstated**. Dentologie same-door duplicate concern CLOSED by QA read-only scan (no `%dentologie%` /
  `444 n orleans` dup). 3 carry-forward holds QA-L2-HOLD-1 (Heartland corroboration-grade evidence),
  -2 (3 legacy-corporate false-positive suspects, frozen), -3 (institutional/FQHC scope). Also received
  Main AO addendum `wave4_hold1_labinov_operating_status_rescan_20260622.json` resolving initial QA-HOLD-1:
  fd93e6934ac6c59c (Destiny Oak Park) CONFIRMED OPEN -> keep_ready (closed flag = false positive); 7
  ao:LABINOV_BORIS D2-shell rows -> hold_operating_status (no open-door confirm, no closure source);
  network-identity correction (fd93 is ao:WILSON-ADELEKE_SIMONE sibling, not literal LABINOV member).
- 2026-06-22: **GATE-004 DONE (rollup/status only, files-only, zero mutation).** Wrote
  `wave4_gate_rollup_status_20260622.json` summarizing: §1 initial partition (19 net-new merge-eligible;
  PASS_WITH_HOLDS) · §2 Lane-2 (+1 net-new corporate Dentologie + 12 corroborations + 2 true_independent +
  4 holds + 3 refutations; PASS_WITH_HOLDS) · §3 LABINOV addendum (fd93 keep_ready; 7 D2 shells
  hold_operating_status; identity correction) · §4 open policy holds (Affordable/ClearChoice scope,
  institutional/FQHC scope, protected-network holds, operating-status holds, 3 legacy false-positive
  suspects frozen, T5 rationale data-quality hold) · §5 Fleet B 51-100 (AUTH written, output pending).
  Aggregate: **22 net-new census candidates at ready_for_validation** (19 initial + 3 Lane-2 net-new; 12
  corroborations NOT counted); **legacy floor concrete lift = +1 (Dentologie ONLY) — not overstated**;
  nothing merged. Freeze intact (md5 `…dc16…` · LEDGER 1 · undetermined 4439 · tier 0/0). **No manifest
  merge, no new ready file, no DB write. STOPPED — awaiting Fleet B 51-100 output + explicit user
  consolidation authorization.**
