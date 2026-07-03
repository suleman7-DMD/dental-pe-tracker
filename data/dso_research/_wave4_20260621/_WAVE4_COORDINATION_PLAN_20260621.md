# Wave 4 — Evidence Closure Sprint — COORDINATION PLAN (files-only)

**Role:** Gate Owner coordinates INTAKE ONLY. **Does NOT gather evidence and does NOT launch evidence fleets.**
**Authorized by user, 2026-06-21.** Scope: **Chicagoland / IL only. Boston/MA PARKED.**

## AUTHORITATIVE PRE-QA GATE
`ownership_manifest_QA_wave4_pre_criteria_20260621.json` — **AB1–AB12** + 14-item Gate-Owner checklist +
`merge_eligibility_decision_rule`. This is THE bar; intake normalizes every Wave 4 output against it.
If the internal `QA_preQA_criteria` agent returns a second file
(`ownership_manifest_QA_wave4_preQA_criteria_20260621.json`), it is a SECONDARY cross-check only —
on any conflict the **STRICTER rule wins**. Never overwrite either QA file.

## FLEET OWNERSHIP (research is NOT the Gate Owner's to run)
| Lane | Owner | Status |
|------|-------|--------|
| 1 — Conflicts (74) + AO backfill | **Main AO session** | in progress |
| 3 — Phase-C hard leads (top-50 of 158) | **Fleet B session** | in progress |
| 2 — non-AO backfill (locator_exact 13, practice_intel 12) | *unconfirmed* | flag as coverage gap; DO NOT self-dispatch |
Gate Owner does NOT launch duplicate fleets. Unowned sublanes are RECORDED as coverage gaps, not filled.

## HARD CONSTRAINTS (apply to every agent + the Gate Owner)
1. **Consolidation FROZEN.** No `consolidate_census.py --allow-db-write`. No mutation of the DB, LEDGER,
   PROGRESS, `ownership_tier`, `entity_classification`, or `ownership_status`. Reset invariant must stay
   `PL/P tier nonnull = 0/0`, `LEDGER = 1 line`, `PROGRESS undetermined = 4439`.
2. **NO MERGE into the canonical manifest** until each output is normalized against AB1–AB12 of the
   authoritative gate above AND a fresh QA verdict records PASS.
3. **Keep `_ready_to_validate_wave3_fixed_20260621.json` (310) intact.** Do not touch the canonical
   manifest's existing buckets/sidecars in this sprint — Wave 4 outputs are NEW evidence files only.
4. **No new consolidation. No deterministic Fleet B re-mining. No broad AO reach=2 long tail.**
   Work only the curated packets below (74 + 87 + 158 = the closed Wave 4 universe).
5. **Preserve ALL sidecar/network intelligence** — operator/family/brand/legal-entity/evidence-chain/
   stale-closed metadata must be carried through, never flattened.
6. **Protected networks (per authoritative gate AB9): SHAFI, BELKIC, NITTINGER, AQEL, BRUNETTI, SWEIS,
   LABINOV, RAMAHA.** No auto-release. Verified MSO/structure evidence may be RECORDED as a flag, but
   release requires an explicit per-network release decision. NB: **Brite Dental / Fadi Aqel (Lane 1, 12
   rows) is now a protected surname AND overlaps Webster (AB10)** — stays held absent explicit release.
7. **Duplicate-door hazard:** if a verified address is a same-door twin of another bucketed row, FLAG it
   (do not silently promote both). 9 known pairs in `duplicate_denominator_blocked`.

## WORK PACKETS (in this dir)
| Lane | Packet | Items |
|------|--------|------:|
| 1 — Conflicts | `wave4_packet_lane1_conflicts.json` | 74 (6 network groups) |
| 2 — Backfill | `wave4_packet_lane2_backfill.json` | 87 (4 sublanes) |
| 3 — Hard-signal leads | `wave4_packet_lane3_hardleads.json` | 158 (A 18 / B 46 / C 94) |

## EVIDENCE OUTPUT CONTRACT
Governed by `output_contract_for_main_ao_and_fleet_b` + `required_per_promoted_row` in the authoritative
gate file. Summary of what a merge-eligible row MUST carry: location_id / name / zip / city / state(IL);
proposed T1–T6 tier with DSO=STRUCTURE rationale for any T4/T5; pe_backed bool + cited doc if true;
a **transcribed durable artifact on disk** (actual EIN value / named parent entity / exact-address
locator URL / db field — NOT a description, NOT a confidence label); evidence_source path/URL that exists;
operating-status (subject door open) check; same-door check; protected-network release ref if applicable.
**Default disposition for any failing/ambiguous row = needs_more_evidence (named backfill_lane) or
undetermined. Never ready, never defaulted true_independent. No partial credit.**

## INTAKE ACCEPTANCE (what the Gate Owner will accept)
- Only files **under `data/dso_research/_wave4_20260621/`** OR clearly-named `wave4_*`/Wave 4 evidence
  artifacts. Agent SUMMARIES are not evidence — the on-disk file is the source of truth (checklist #1).
- Each row checked mechanically + manually against AB1–AB12; partitioned into merge-eligible vs hold.

## PIPELINE
intake (done) → authoritative pre-QA gate landed (done) → **[evidence fleets run: Main AO + Fleet B]** →
Gate Owner ingests Wave-4 files, normalizes against AB1–AB12, partitions eligible/hold (files-only,
NO manifest mutation) → request fresh QA verdict → (merge into manifest ONLY after QA PASS) →
HOLD for user's explicit `consolidate approved manifest`. Consolidation stays FROZEN the entire time.
