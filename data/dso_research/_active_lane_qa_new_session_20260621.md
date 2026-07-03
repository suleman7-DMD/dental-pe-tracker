# ACTIVE LANE — New Session #1 (QA / Validation Gate + Denominator Review)

> 📥 **[2026-06-21] INBOX — FOCUSED RE-CHECK FROM GATE OWNER (RE-QA #4 MUST-FIX A/B/C APPLIED — ready 315 → 310):** your RE-QA #4 verdict (`ownership_manifest_QA_wave3_reqa4_20260621.json`, "PASS WITH MUST-FIX") has been applied exactly as scoped, no new evidence / no consolidation / no `--allow-db-write`. **Fix A:** 4 operating-status-risk rows demoted ready→needs_more (`f6c6290c16d20224`, `822d3012aedf32b9`, `77357c36224272c8`, `7d1d789828351ecf`), each `preserved_ready_row` + `backfill_lane="operating_status_unverified"`. **Fix B:** ao:SHAFI_REEM EXPLICITLY RELEASED as dentist_multi (`ba663f30996016ce`, `fc658bf62642d908` corrected branded_dso→dentist_multi; `6da55130228a9c54` already dentist_multi) — documented at `ao_network_release_decisions.decisions["ao:SHAFI_REEM"]`, consistent with the prior VERIFIED ao:SHAFI_SOHAIL/Two Rivers dentist_multi release, NOT a pe_backed=false downgrade. **Fix C:** duplicate-door leak `ff41419130267bd9` (pair w/ `f94fb29cc7d444cd`, 2340 N Clybourn) demoted, `duplicate_denominator_blocked.currently_in_candidate_set`+`pairs` updated. **ready_to_validate 310** (= your post_fix_projection.ready_after_A_and_C_demote_B_released), needs_more 167, conflicts 74, backfill 87, rejected 7. Validate-only on the 310 passes (`Loaded 310 … Validation OK`). Reset re-verified intact. **Please do a FOCUSED re-check of A/B/C** — start at **`_QA_REVIEW_REQUEST_gate_manifest_20260621.md`** (now the focused re-check request) → `_ready_to_validate_wave3_fixed_20260621.json` (310 rows) + `consolidation_candidate_manifest_20260621.json` (`qa_mustfix_actions[-1]`, `ao_network_release_decisions.decisions["ao:SHAFI_REEM"]`, `duplicate_denominator_blocked`, `_meta.reqa4_fix`). Consolidation stays FROZEN until the user says "consolidate approved manifest." _(RE-QA #4 full-review request below superseded by this focused re-check.)_
>
> 📥 **[2026-06-21] (prior) RE-QA REQUEST #4 FROM GATE OWNER (QA MUST-FIX applied + WAVE 3 MERGED — AO reach=3 ranked + Fleet B local/website/structural clusters):** the user demanded a two-pass realignment. **PASS 1 (your MUST-FIX, applied FIRST):** 4 ready rows demoted ready→needs_more (`1fa86e6647cd57c5`, `b184f060d46970cd`, `e493e4371bb5cb22`, `d5bc28878405a18c`) — they self-flag candidate/closed/operating-status-unverified, which `--validate-only` cannot catch; each keeps its full original row under `preserved_ready_row`. ready **210 → 206**. **PASS 2 (separate pass):** merged 4 overlapping hunt files, deduped by location_id across ready/needs_more/rejected/conflicts + within-wave. reach3_ranked (51 nets / 138 rows) → **+87 ready** (0 on AO-reach-only — spot-checked Heartland/Familia/Affordable Care/Destiny-ProSmile artifacts); Fleet B local/website/structural (19/5/2 classified) → **+22 ready** (Pieta da_synthetic qa-flag → backfill); 694 needs_verification preserved as LEADS in sidecar `fleet_b_wave3`. **ready_to_validate 206 → 315**, needs_more 162, backfill 87, conflicts 74, rejected 7. Validate-only on the 315 passes (`Loaded 315 … Validation OK`). Reset re-verified intact. Intelligence preserved verbatim in sidecars `ao_network_intelligence.wave3_reach3` (51 nets/138 rows + QA) + `fleet_b_wave3` (720 rows). **Please RE-QA the Wave 3 manifest** — start at **`_QA_REVIEW_REQUEST_gate_manifest_20260621.md`** (now RE-QA #4) → `consolidation_candidate_manifest_20260621.json` (WAVE 3 MERGED, new `qa_mustfix_actions` + `reach3_network_release_decisions` + `fleet_b_wave3_dispositions`), `_ready_to_validate_wave3_20260621.json` (315 rows), reach3_ranked (+`_qa`), the 3 Fleet B cluster files (+`_qa_flags`/`landmine_blocklist`). Consolidation stays FROZEN until the user says "consolidate approved manifest." _(RE-QA #3 below superseded.)_
>
> 📥 **[2026-06-21] (prior) RE-QA REQUEST #3 FROM GATE OWNER (WAVE 2 MERGED — Main AO reach=4 + Fleet B Lane1B):** you signed off the merged 123-row manifest; two Wave-2 hunt outputs have now landed and been MERGED (autonomous pass, user away). ready_to_validate **123 → 210** (+43 reach4, +44 Lane1B), needs_more_evidence **168 → 158**, evidence_gap_backfill_queue **55 → 70**, conflicts **74** (5 reach4 Webster/Berwyn held there + new Webster Dental Management MSO note), rejected **7**. Validate-only on the 210 rows passes (`Loaded 210 … Validation OK`). **Discipline checks for you:** AO reach is SIGNAL only — Kalpana Shah `18bb61421ac89614` was DEMOTED to backfill (ao_cluster AO-reach-only), the other 3 ao_cluster rows KEPT on BBB/website/multi-loc corroboration; every Lane1B QA flag honored (16 → backfill); reach4 QA regate_audit honored (Groh/Napier → dentist_multi); Shafi `1df260dc` held (cross-wave tier conflict). **Intelligence preserved verbatim** in sidecars `ao_network_intelligence.wave2_reach4` (14 nets/56 rows) + `fleet_b_lane1B` (full 320 rows, 258 needs_verification as leads) — nothing flattened. Please **RE-QA the Wave 2 manifest** before any `--allow-db-write`. Start at **`_QA_REVIEW_REQUEST_gate_manifest_20260621.md`** (now RE-QA #3) → it points to `consolidation_candidate_manifest_20260621.json` (WAVE 2 MERGED, new `reach4_network_release_decisions` + `fleet_b_lane1B_dispositions`), `_ready_to_validate_wave2_20260621.json` (210 rows), `ao_network_evidence_reach4_20260621.json` (+`_qa`), `ownership_evidence_queue_fleet_b_lane1B_20260621.json` (+`_qa_flags`). Consolidation stays FROZEN until the user says "consolidate approved manifest." _(SUPERSEDED by RE-QA #4 above — Wave 3 manifest, 315 rows, is the canonical re-review target.)_
>
> 📥 **[2026-06-21] (prior) RE-QA REQUEST #2 — BOTH backfills MERGED:** ready_to_validate **65 → 123**, needs_more_evidence **227 → 168**, conflicts **73 → 74**, backfill **114 → 55**. RELEASED Labinov/Nittinger/Shafi/Brunetti; HELD Sweis + Ramaha. _(Superseded by RE-QA #3 above.)_

**Session role:** adversarial QA gatekeeper. **Date:** 2026-06-21. **Model:** Opus 4.8.

## What this lane OWNS (and will write)
- `data/dso_research/ownership_evidence_QA_20260621.json` — adversarial QA verdicts for every
  candidate row the main session produces (qa_status / qa_reasons / corrected_tier_if_obvious /
  evidence_quality / safe_to_consolidate).
- `data/dso_research/evidence_denominator_review_20260621.json` — row-by-row reconciliation of the
  48 (exact audit) vs 87 (pressure-test) duplicate-cluster conflict.
- This lane file.

## What this lane will NOT touch (collision-safe boundaries)
- **No DB writes.** No `ownership_tier`, no reset, no consolidate `--allow-db-write`.
- **No LEDGER.jsonl / PROGRESS.json mutation.**
- **No `entity_classification` changes.**
- **No duplicate evidence gathering** over the main session's targets
  (`ownership_evidence_targets_20260621.json`: dso_suspects, ao_clusters, institutional, intel_leads).
- **Will NOT touch AO networks** claimed by main session: Shafi, Belkic, Nittinger, Aqel, Brunetti,
  Sweis, Labinov, Ramaha.
- `consolidate_census.py` used in `--validate-only` mode ONLY (no writes).

## Inputs I consume (read-only)
- `census_evidence_candidates_validation_20260621.json` (72 rows, main session validation wave)
- any new `ownership_evidence_queue_*`, `ao_network_evidence_*`, `evidence_locator_*`,
  `evidence_intel_*`, `evidence_zip_sweep_*` files as they appear
- `denominator_audit_20260620.json`, `il_denominator_pressure_test_20260620.json`

## Standing rules I enforce
- "final_ready" from agents = **ready_for_validation only**, never final truth.
- AO reach alone = candidate; dentist_multi needs corroboration (group site / shared legal entity /
  shared owner-dentist / locator + web).
- true_independent must be POSITIVELY earned (one-location owner-operated evidence OR saved
  negative-search artifact), not "no DSO language".
- stealth_dso/branded_dso need exact address+ZIP documentary evidence; reject fuzzy brand-only,
  co-location traps, DA synthetics.
- IL only. Boston parked.

## Stabilization state at lane-claim time
Partial: `consolidate_census.py` patched fail-closed + wave-1 quarantine exists, BUT the
DB/LEDGER/PROGRESS reset is NOT done (349 ownership_tier rows still live; LEDGER 350 lines;
PROGRESS 349/4,439). Do NOT use `ownership_tier IS NULL` as canonical remaining-work until reset
confirmed.
