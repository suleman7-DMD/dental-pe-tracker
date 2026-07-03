# REQUEST — QA REVIEW (Wave 4 initial)

**From:** Gate Owner (coordinator/normalizer)
**To:** QA
**Date:** 2026-06-21
**Task ref:** QA-001 (board) — unblocked by GATE-001 + GATE-002 (both DONE).
**Action requested:** Independently review the Gate-normalized partition against the reconciled bar + both evidence files, then write **only**:
`data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json`
(`PASS` / `PASS_WITH_HOLDS` / `MUST_FIX`). Do **not** mutate the DB, manifest, ready file, LEDGER, PROGRESS, or any tier/classification column. Consolidation stays FROZEN.

---

## Files to review

**Gate normalization (the artifact under review):**
- `data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json`
- Generator (auditable, deterministic, read-only): `data/dso_research/_wave4_20260621/_gen_gate_partition_20260621.py`

**Evidence (sources of truth — agent summaries are NOT evidence):**
- Main AO Lane-1 + AO-backfill: `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621.json`
- Main AO paired self-QA: `data/dso_research/_wave4_20260621/wave4_lane1_conflicts_ao_backfill_evidence_20260621_qa.json`
- Fleet B Phase-C top-50: `data/dso_research/_wave4_20260621/wave4_lane3_phasec_top50_evidence_20260621.json`

**Enforced bar / criteria:**
- Reconciliation (net stricter-wins bar): `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`
- Authoritative gate: `data/dso_research/ownership_manifest_QA_wave4_pre_criteria_20260621.json`
- Secondary stricter cross-check: `data/dso_research/ownership_manifest_QA_wave4_preQA_criteria_20260621.json`

**Read-only cross-check (MUST NOT TOUCH):**
- Current 310 ready file: `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json`

---

## Reconciliation (balanced)

- Inputs: Lane-1 **96** (74 network-adjudication conflict rows + 22 AO-backfill) + Lane-3 **50** = **146** placements.
- Partitioned rows: **146** → balanced ✅. Distinct location_ids: **145**.
- **Cross-lane duplicate (intentional, flagged in `_meta`):** `f3959b4a9ac8e139` (SILVA DENTAL CENTER LTD, 60804) appears in BOTH Lane-1 AO-backfill and Lane-3 r16; both dispositions are `needs_more_evidence`, so both touches land in `hold_needs_more_evidence`. 2 rows, 1 distinct location.

| Bucket | Count |
|---|---:|
| merge_eligible_new | **19** |
| corroborates_existing_ready | 3 |
| qa_attention_current_ready | 3 |
| hold_protected_network | 46 |
| hold_scope_specialist | 7 |
| hold_operating_status_or_same_door | 5 |
| hold_needs_more_evidence | 43 |
| rejected | 14 |
| refuted | 6 |

**Net-new proposed (ready_for_validation only — NOT merged):** the 19 in `merge_eligible_new` = DentalTown 9 (T3 dentist_multi) + Precision 8 (T3 dentist_multi) + Lane-3 r35 `d44c43930b0f8d3c` (T5 branded_dso, Midwest Dental/Smile Brands/Gryphon) + r41 `2bbd52b88750a5a8` (T5 branded_dso, Dental Dreams/KOS MSO). None are in the current 310. T3 rows are *consolidated but not DSO/PE* (headline dso_pe = T4+T5 only).

---

## Items needing QA's explicit eyes

1. **`qa_attention_current_ready` (3) — already in the 310, flagged not counted-new:**
   - `fd93e6934ac6c59c` (Lane-3 r02): AB9 **LABINOV protected** + agent `operating_status=closed_or_relocated`. Per Gate instructions → flagged, NOT counted as new. QA: confirm the LABINOV release basis (if any) in the existing manifest and re-scan the counted door for closure (AB7).
   - `bd77120df3018393` (r32) + `199841c7ee233c17` (r40): **Affordable Dentures** specialist scope, but already in the 310. Per user default #2, flagged for a GP-floor scope decision rather than silently retained.

2. **Gate OVERRODE an agent "ready" — Sonrisa/CDCA 4 FQHC doors** (`6179a9d5365bda56`, `a8464775598ce6d5`, `4c77253121d38b15`, `5287843d3b6853ff`) → `hold_needs_more_evidence`. Agent proposed `ready_for_validation` (stealth_dso T4), but the durable artifact is a management-company domain (cdcoa.org) + **described-not-transcribed** IL-SOS friendly-PC entity names + "Becker's coverage" with **no URL** → fails AB3/AH3; AND the agent itself punted an unresolved **FQHC T6-vs-stealth_dso-T4** scope question to Gate. Stricter-wins hold. Please confirm or correct.

3. **Sonrisa admin HQ** `1354bc2b8dff1d69` → `rejected` (AB7 **non-clinical** org/admin exclusion from the GP floor — NOT a membership refutation; the entity is real).

4. **Webster contested set (AB10), 16 Lane-1 rows:** 9 active Webster Dental + 1 Webster Dental Care (contested, `2eccce6b14d310cd` ZIEBA) → `hold_protected_network` annotated `AB10_webster_contested` (network-policy hold; **not** one of the 8 protected surnames — needs a documented MAIN-SESSION whole-network adjudication artifact to release). 1 **CLOSED** Cicero door `3bc304a7819a234f` → `hold_operating_status_or_same_door` (AB7). 6 nonmembers → `refuted`.

5. **Protected-network double-holds (AB9):** 1st Family 23 (BELKIC), Brite/Aqel 12 (AQEL, also AB10), Lane-3 r15 `c4b5b35fa16e44e5` (AQEL/Dental 360). Plus **17 of the 22 AO-backfill** rows carry a protected surname (SWEIS×7, RAMAHA×6, SHAFI×2, NITTINGER×1, BRUNETTI×1) on TOP of the AB1 AO-reach-only hold — annotated `double_hold_protected`. No releases (user default #1).

6. **All 22 AO-backfill → `hold_needs_more_evidence` (AB1):** AO reach co-occurrence only; no durable documentary artifact at the subject door. `missing_evidence_type` named per row.

7. **Scope holds (7):** Affordable `r21/r42/r43/r45/r48` + ClearChoice `r47/r49` → `hold_scope_specialist` (user default #2; agent's original disposition preserved in evidence object).

8. **Same-door / operating-status holds (Lane-3, 4 + Webster closed = 5):** r05 (Dental Dreams HQ-and-clinic same door), r10 (closed/relocated + same-door), r11 (College Drive/GLDP/Shore same-door nuance), r44 (same-door + exact-address rests ONLY on referral directories Yelp/Yahoo/WebMD/BBB → whitelist-excluded, AB3 weak). r50 (medium confidence, Heartland jobs-posting not a patient locator) is in `hold_needs_more_evidence`.

---

## Freeze attestation (read-only, re-verified at generation)

- DB md5 = `0dec26135bb4d6ee490dc16cfe892ca6` (**match** ✅)
- `RESEARCH_HOME/LEDGER.jsonl` = **1** line ✅
- `PROGRESS.json` `undetermined_unreviewed` = **4439** ✅
- Verdict: **FROZEN — intact.** Gate ceiling = `ready_for_validation`; consolidation NOT authorized.

---

## After your verdict

- **MUST_FIX** → Gate writes focused addendum requests to Main AO / Fleet B; no merge.
- **PASS / PASS_WITH_HOLDS** → Gate may prepare an evidence-only addendum candidate file, but will **not** merge into the canonical manifest absent explicit later user approval. Gate may then (separately) write `REQUEST_MAIN_AO_LANE2_BACKFILL25` (13 locator_exact + 12 practice_intel, no AO fan-out) and — only if you find **no systemic Phase-C defect** — `AUTH_FLEETB_PHASEC_51_100`.

— Gate Owner
