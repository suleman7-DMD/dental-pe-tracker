# REQUEST — Independent QA Review: Wave 4 Lane-2 non-AO backfill (25 rows)

**From:** Gate Owner (coordination/normalization only — files-only, ZERO mutation)
**To:** QA (independent)
**Date:** 2026-06-22
**Predecessor verdict:** `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` = **PASS_WITH_HOLDS**, `systemic_defect_found: false`. This Lane-2 output was written by Main AO (MAIN-001) **after** that verdict and is **not** covered by it — it needs its own QA pass.

## What to review
A fresh, independent verdict on whether the Gate's normalized Lane-2 partition correctly applies the net enforced bar (AB1–AB12 + HB1–HB10 + AH1–AH7 + 12-step decision tree + union of both gate-owner checklists, **stricter-wins**) and does **not overstate floor impact**.

## Inputs (read the on-disk files; agent summaries are not evidence)
| Role | Path |
|------|------|
| Lane-2 evidence (MAIN-001, 25 rows) | `data/dso_research/_wave4_20260621/wave4_lane2_non_ao_backfill25_evidence_20260621.json` |
| Lane-2 self-QA (16/16 bool guards) | `data/dso_research/_wave4_20260621/wave4_lane2_non_ao_backfill25_evidence_20260621_qa.json` |
| **Gate normalized Lane-2 partition (this request's subject)** | `data/dso_research/_wave4_20260621/wave4_gate_normalized_lane2_partition_20260622.json` |
| Deterministic generator (auditable) | `data/dso_research/_wave4_20260621/_gen_gate_lane2_partition_20260622.py` |
| Net enforced bar | `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json` |
| 310 ready file (read-only; MUST stay unmutated) | `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` |

## Gate normalization result (25 rows, balanced)
| Bucket | n | Floor impact |
|--------|---:|--------------|
| `merge_eligible_new_corporate` | **1** | **+1 net-new corporate** (Schock Dental → Dentologie River North, `5cd692a50e5c32b7`) |
| `corroborates_existing_corporate_no_lift` | 12 | **0** — already `dso_national`/`dso_regional` by entity_classification (10 Heartland "Dental Professionals of Illinois, P.C." + DCA New Lenox + Aspen TAG) |
| `true_independent_confirmation` | 2 | 0 — earned T1, **not** corporate (Jova `b7499322a2416c5d`, Bellido-Griffin `0a318ab399f418de`) |
| `hold_needs_more_evidence` | 2 | 0 — Bloomingdale Dental (`d4d827860b4132cb`, **SWEIS adjacency, held**), Midwest Dental Group (`d2e5c43e4975ddb4`, name-collision) |
| `hold_operating_status_or_same_door` | 2 | 0 — Kang (`5404b210ff43f176`, Dental Dreams same-door), Obucina (`499c18e0f7c7ad12`, operating-status/address anomaly) |
| `hold_scope_specialist` | 3 | 0 — IWS FQHC, Heartland Intl Health Center (FQHC), Heartland Health Outreach (nonprofit) — institutional T6 |
| `refuted` | 3 | 0 — Warga, Batchelor (false-positive stealth_dso), Northwestern (substring false-positive) |

**Reconciliation:** total 25 = input 25 ✓; ready_for_validation 15 = source rollup 15 ✓; distinct location_ids 25, 0 duplicates; 310-overlap **0**.

## Floor-impact claim to scrutinize (do NOT overstate)
- **Net-new corporate floor lift = +1 (Dentologie ONLY).** The 12 corroborations add **zero** (already corporate by entity_classification). The 2 true_independent rows are **not** corporate adds.
- **3 legacy-corporate FALSE-POSITIVE SUSPECTS flagged, NOT mutated:** Northwestern Dental Center (`598cc9dae498795b`, REFUTED — "NORTHwestern" substring, actually Northwestern Medicine academic), Midwest Dental Group (`d2e5c43e4975ddb4`, HELD name-collision), Bloomingdale Dental (`d4d827860b4132cb`, HELD SWEIS adjacency). All three are currently corporate in legacy `entity_classification`; if ever acted on they would **lower** the floor — but **nothing is mutated** under the freeze. Surfaced for QA/user decision only.

## Specific QA-attention items
1. **Dentologie (the only +1):** verify the own-locator exact-address transcription (444 N Orleans St, "13 Neighborhood Offices") satisfies AB3/locator_exact, that the T5 `dso_structure_rationale` is populated, and that **no separate `Dentologie River North` location_id already exists** (Main AO flagged a same-door duplicate check).
2. **Protected-network discipline:** confirm Bloomingdale (`d4d827860b4132cb`) is **held**, not released, and its SWEIS adjacency is preserved (AB9 — no protected release this lane).
3. **Heartland name-collision guard:** confirm Heartland International Health Center (FQHC/Tapestry 360) and Heartland Health Outreach (Heartland Alliance nonprofit) are **NOT** promoted as Heartland Dental and remain institutional holds.
4. **true_independent earned, not defaulted:** confirm Jova + Bellido-Griffin carry positive named-owner-operated evidence (not a default).
5. **Refutations:** confirm Warga (30+yr Pankey-faculty solo), Batchelor (solo since 1999), Northwestern (academic) are correctly refuted, not consolidated.

## Constraints attested in this artifact
Files-only; gate ceiling = `ready_for_validation` (never final); consolidation **FROZEN**. No DB/manifest/ready/LEDGER/PROGRESS/ownership_tier/entity_classification/ownership_status mutation. **Freeze re-attested read-only in the partition:** db_md5 `0dec26135bb4d6ee490dc16cfe892ca6` (match), LEDGER 1 line, PROGRESS undetermined_unreviewed 4439 → "FROZEN — intact".

## Requested output
Write an independent verdict file `autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json` (do **not** overwrite the initial verdict). State PASS / PASS_WITH_HOLDS / FAIL, whether the +1-net-new-corporate floor claim is correct and not overstated, and any MUST_FIX vs carry-forward holds. **Do not merge anything into the canonical manifest; do not build a new ready file.**
