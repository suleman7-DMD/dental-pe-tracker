# REQUEST — Independent QA Review: Wave 4 Lane-3 Phase-C ranks 51-100 (50 rows)

**From:** Gate Owner (coordination/normalization only — files-only, ZERO mutation)
**To:** QA (independent)
**Date:** 2026-07-02
**Predecessor verdicts:**
- `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` = **PASS_WITH_HOLDS**, `systemic_defect_found: false` (covers Lane 1 + Lane 3 top-50, 146 rows)
- `autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json` = **PASS** (covers Lane 2 backfill, 25 rows)
- This Lane-3 ranks 51-100 output was written by Fleet B (session-isolated, not the Gate Owner's inference) and is **not** covered by either prior verdict — it needs its own independent QA pass.

---

## What to review

A fresh, independent verdict on whether the Gate's normalized partition for Lane 3 ranks 51-100 correctly applies the net enforced bar (AB1–AB12 + HB1–HB10 + AH1–AH7 + 12-step decision tree + union of both gate-owner checklists, **stricter-wins**), correctly applies the **T3 dentist_multi policy ratified 2026-07-02**, and does **not overstate floor impact**.

---

## Inputs (read the on-disk files; agent summaries are not evidence)

| Role | Path |
|------|------|
| Fleet B evidence file (50 rows) | `data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622.json` |
| Fleet B self-QA sibling | `data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622_qa.json` |
| **Gate normalized partition (this request's subject)** | `data/dso_research/_wave4_20260621/wave4_gate_normalized_lane3_51_100_20260702.json` |
| Net enforced bar | `data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json` |
| Schema reference — prior PASS partition | `data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json` |
| Schema reference — prior PASS Lane-2 partition | `data/dso_research/_wave4_20260621/wave4_gate_normalized_lane2_partition_20260622.json` |
| T3 policy source | `data/dso_research/RESEARCH_HOME/PROJECT_MANAGER_HANDOFF_20260702.md` §3 |
| 310 ready file (read-only; MUST stay unmutated) | `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` |

---

## Gate normalization result (50 rows, balanced)

| Bucket | n | Floor impact |
|--------|---:|--------------|
| `merge_eligible_new` | **5** | See breakdown below |
| `hold_protected_network` | 4 | 0 — NITTINGER × 1, SHAFI × 3. Mandatory hold. |
| `hold_scope_specialist` | 3 | 0 — periodontist, Loyola/Trinity Health institutional, endodontist |
| `hold_needs_more_evidence` | 14 | 0 — pending own-locator or address verification |
| `rejected` | 24 | 0 — 12 Patel surname coincidences, 3 Ahmed, 4 Sharma/Singh residential NPPES artifacts, 3 institutional non-clinical, 2 other |
| **TOTAL** | **50** | |

**Floor-impact breakdown for the 5 merge_eligible_new rows:**

| Rank | Location ID | Practice | Proposed Tier | PE-backed | Net-new? | Floor lift |
|------|-------------|----------|---------------|-----------|----------|------------|
| 54 | c5769cc8b2bc5319 | United Dental Centers Ltd | T3 dentist_multi | No | Yes | +1 consolidated (NOT DSO/PE headline) |
| 79 | e4604698cb78a23a | Grove Dental, Bolingbrook | T5 branded_dso | Yes (Abry/NADG) | Yes | +1 DSO corporate |
| 83 | 8d81d4516f493d1e | Archer Dentistry Chicago | T3 dentist_multi | No | Yes | +1 consolidated (NOT DSO/PE headline) |
| 88 | 262af10fbc0f17f8 | Dental Group of Chicago | T3 dentist_multi | No | Yes | +1 consolidated (NOT DSO/PE headline) |
| 100 | 6c31d482e9a63431 | Advanced Family Dental, Shorewood | T5 branded_dso | Yes (Shore Cap/GLDP) | Yes | +1 DSO corporate |

**Net-new corporate floor lift (T5/T4 only) = +2** (Grove Dental + Advanced Family Dental)
**T3 dentist_multi consolidated = +3** (United Dental Centers, Archer Dentistry, Dental Group of Chicago — not DSO/PE headline)
**All 5 are net-new: zero overlap with the 310 ready file, zero overlap with prior partition merge_eligible rows.**

---

## Reconciliation (Gate self-attested — QA must independently verify)

| Check | Gate claim | QA to verify |
|-------|-----------|--------------|
| rows_in | 50 | All 50 Fleet B ranks 51-100 appear exactly once in the partition |
| rows_placed | 50 | Bucket totals 5+4+3+14+24 = 50 |
| distinct location_ids | 50 | Zero duplicates within this partition |
| 310 ready file overlap | 0 | No location_id from the 5 merge_eligible rows appears in the 310 ready file |
| Prior partition merge_eligible overlap | 0 | No location_id from the 5 merge_eligible rows appears in wave4_gate_normalized_partition_20260621.json or wave4_gate_normalized_lane2_partition_20260622.json eligible rows |

---

## Specific QA-attention items

### Priority 1: Verify the two T5 branded_dso exact-address own-locator URLs

**Rank 79 — Grove Dental, Bolingbrook (e4604698cb78a23a)**
- Own locator claimed: `https://www.grovedental.com/dentist-bolingbrook`
- Must confirm: page explicitly lists "160 E. Boughton Road, Bolingbrook, IL 60440" (or exact close match)
- Must confirm: NADG/Abry Partners acquisition April 2019 documentation is real (not hallucinated)
- Must confirm: this location_id does NOT already appear in the 310 ready file or prior partition merge_eligible

**Rank 100 — Advanced Family Dental, Shorewood (6c31d482e9a63431)**
- Own GLDP locator claimed: `https://www.greatlakesdentalpartners.com/company/locations/`
- Must confirm: page explicitly lists "Advanced Family Dental & Orthodontics" Shorewood at "150 Brookforest Ave, Shorewood, IL 60404" (or close match)
- Must confirm: Shore Capital Partners PE backing for GLDP is real (shorecp.com)
- Must confirm: June 2018 GLDP press release affiliation is real

### Priority 2: Three T3 dentist_multi re-buckets under ratified policy

These three rows were re-bucketed by the Gate from the raw Fleet B disposition under T3 policy ratified 2026-07-02. QA must independently assess each.

**Rank 54 — United Dental Centers Ltd, Chicago 60617 (c5769cc8b2bc5319)**
- Raw disposition: `rejected` (assembly note said "mirrors r83, rejected on same T3 basis")
- Gate rebucket to: `merge_eligible_new T3`
- QA check: verify udcchicago.com lists "3540 E. 118th St, Chicago, IL 60617" as an active location
- QA check: confirm Fried family ownership and 4-location group (1 IL + 3 IN) from own website
- QA check: confirm no MSO/PE structure on own website
- QA check: under T3 policy, does the evidence meet the evidence bar (own-brand/owner-named + multi-location + no MSO)?

**Rank 83 — Archer Dentistry Chicago (8d81d4516f493d1e)**
- Raw disposition: agent wrote merge_eligible_new, assembly downgraded to `hold_needs_more_evidence` explicitly preserving the artifact for Gate decision
- Gate rebucket to: `merge_eligible_new T3`
- QA check: verify `https://archerdentistry.com/chicago-booker-area/` lists "654 E 47th St, Chicago, IL 60653" as an Archer Dentistry branch
- QA check: confirm Dr. Hamza Mohammed named owner on archerdentistrychi.com
- QA check: confirm 5-location structure (4 IL + 1 IN, not 5 + 5) — specifically confirm Naperville and Hickory Hills are IL
- QA check: FQHC co-location concern — archerdentistry.com lists 654 E 47th as "Chicago-Booker Area" branch independently from ACCESS Booker FQHC operations. Confirm Archer is the operating dental entity at this address (not a slot within ACCESS staff).
- QA check: confirm no MSO/PE/DSO structure in public records

**Rank 88 — Dental Group of Chicago (262af10fbc0f17f8)**
- Raw disposition: `hold_needs_more_evidence` (held specifically for T3 policy ruling)
- Gate rebucket to: `merge_eligible_new T3`
- QA check: verify `https://dentalgroupofchicago.com/contact/` lists "1556 S. Michigan Ave, Suite 200, Chicago, IL 60605"
- QA check: confirm Dr. Alexander Reznikov named as sole owner/founder
- QA check: confirm the second location "Cityview Dental Arts" at 2232 W Armitage is also owned by Dr. Reznikov (not merely associated)
- QA check: confirm no external MSO/PE/DSO platform

### Priority 3: Protected network discipline

- Confirm rank 52 (SANEI CENTER PC, e50dfc828412c437) is held as `hold_protected_network` — NITTINGER flag. Even though Dr. Sanei appears to have a multi-location network, the NITTINGER pre-flag is mandatory.
- Confirm ranks 60, 61, 82 (Gentle Dental Smile Hanover Park, Gentle Dental Care Brookfield, Ashton Dental Aurora) are all held as `hold_protected_network` — SHAFI surname/entity flag.
- Confirm that the assembly note for rank 61 (Gentle Dental Care Brookfield) flagging the address may have moved to Forte Dentistry does NOT cause a rejection; protected hold takes precedence over operating-status concern.

### Priority 4: Notable rejected rows QA should verify

- **Rank 71 (Patel Dental Oak Brook 60523, aa71dced81c01725):** Rejected because the active occupant is DentalWorks/Sonrava (Dr. Amitkumar Patel is an associate there). Note: this location may already be corporate in the DB under DentalWorks — Gate did not attempt to promote/corroborate here since the DB record's name is "Patel Dental" (NPPES artifact). QA should confirm DentalWorks Oak Brook is already in the DB as corporate so this rejection is harmless.
- **Rank 62 (Oral Health Ctr Maywood, cedf0257b26ccce2):** Rejected as T6 institutional (Loyola Medicine / Trinity Health). DB currently classifies this as `dso_regional` with `affiliated_dso=TRINITY HEALTH`. If accepted as T6 scope, this is NOT a floor-lowering action (freeze is maintained); it is a scope clarification only. QA should flag for user decision.
- **Rank 55 (DentalWorks Skokie, d1ec8b09e0a87323):** Held for address mismatch (9215 vs 9312 Skokie Blvd). The DSO brand Sonrava/DentalWorks and PE backing are confirmed — only the exact-address reconciliation is needed. QA should flag whether this can be resolved by looking up the 9312 address in NPPES to find the correct location_id.

### Priority 5: Systemic pattern checks

- **"Patel Dental" batch (12 rows, ranks 51, 57, 64, 65, 66, 67, 70, 71, 72, 73, 75, 76, 77):** The raw Fleet B evidence used the `brand_chain` signal on the surname "Patel" — Gate analysis found each resolved to a distinct unrelated solo practitioner or coincidental surname. QA should spot-check 3-4 of these rejections to confirm the logic holds.
- **"Ahmed Dental" batch (ranks 84, 85, 86):** Same surname-coincidence pattern. Two rejected, one held. QA spot-check one.
- **"Sharma Dental" / "Singh Dental" batch (ranks 93-98):** Several confirmed residential NPPES addresses (home addresses of dentists, not clinical offices). QA should confirm at least one.

---

## Floor-impact claim to scrutinize (do NOT overstate)

- **Net-new T5/T4 branded/stealth DSO floor lift = +2** (Grove Dental Bolingbrook + Advanced Family Dental Shorewood). Both confirmed PE-backed DSO structures.
- **Net-new T3 dentist_multi lift = +3** (United Dental, Archer Dentistry, Dental Group of Chicago). These are consolidated but NOT DSO/PE — do not count them in the PE-backed headline figure.
- **The 24 rejected rows and 21 holds add zero floor lift.** The 4 protected-network holds are frozen indefinitely. The 3 scope-specialist holds are outside the GP denominator.
- **No false-positive demotions** are surfaced in this partition (unlike Lane 2's 3 legacy-corporate suspects). All rejections are non-corporate dispositions of non-corporate location_ids.

---

## Constraints attested in this artifact

- Files-only; gate ceiling = `ready_for_validation` (NEVER final); consolidation **FROZEN**.
- No DB/manifest/ready/LEDGER/PROGRESS/ownership_tier/entity_classification/ownership_status mutation.
- Historical DB md5 `0dec26135bb4d6ee490dc16cfe892ca6` is the June 21-22 at-authoring proof for the Fleet B evidence file. Current local md5 per PM_HANDOFF_20260702 = `e2a89a02900d0366fad6d9ee06d23422` (NPPES refresh occurred between sessions; census freeze invariants remain intact).
- **LEDGER.jsonl = 1 line; PROGRESS undetermined_unreviewed = 4439; ownership_tier IS NOT NULL = 0.**
- The 310 ready file (`_ready_to_validate_wave3_fixed_20260621.json`) was read in read-only mode; it was not mutated.
- **The Gate performed NO web searches.** All evidence URLs are transcribed from the Fleet B evidence file (`wave4_lane3_phasec_51_100_evidence_20260622.json`) and the Fleet B raw agent output. QA is expected to independently verify the key own-locator URLs for the 5 merge_eligible_new rows.

---

## Requested output

Write an independent verdict file `autonomous/VERDICT_QA_WAVE4_LANE3_51_100_20260702.json` (do **not** overwrite prior verdicts). State PASS / PASS_WITH_HOLDS / FAIL. Address:

1. Whether each of the 5 merge_eligible_new rows meets the evidence bar (exact-address own-locator or whitelisted artifact)
2. Whether the T3 policy was correctly applied to ranks 54, 83, 88
3. Whether protected network discipline was maintained for NITTINGER and SHAFI rows
4. Whether the floor-impact claim is correct and not overstated
5. Any MUST_FIX vs carry-forward holds
6. Whether `systemic_defect_found` is true or false

**Do not merge anything into the canonical manifest; do not build a new ready file; do not mutate any existing file.**
