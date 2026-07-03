# FOCUSED RE-CHECK REQUEST — RE-QA #4 MUST-FIX A/B/C APPLIED (2026-06-21)

**From:** Reset + Consolidation Gate Owner (4th session, autonomous — user away)
**To:** QA / Validation Gate session
**Status of the world:** CONSOLIDATION FROZEN. Gate Owner has NOT run `--allow-db-write`.
**Source verdict applied:** `ownership_manifest_QA_wave3_reqa4_20260621.json` (overall "PASS WITH MUST-FIX"; consolidate_authorization = NOT AUTHORIZED — review-only).

> ✅ **Your RE-QA #4 MUST-FIX (A+B+C) has been applied, exactly as scoped — no new evidence, no
> consolidation, no `--allow-db-write`. ready_to_validate 315 → 310.** This is a FOCUSED re-check of the
> three fixes only (not a full re-review of the 310-row set you already RE-QA'd at 315).

## What changed (the only deltas since your RE-QA #4)

### Fix A — 4 operating-status-risk rows DEMOTED ready → needs_more_evidence
`f6c6290c16d20224` (PINEWOOD DENTAL, PC / Orland Park 60467), `822d3012aedf32b9` (OPTIMAL DENTAL
ASSOCIATES, LLC / Tinley Park 60477), `77357c36224272c8` (DENTAL DESIGN GROUP, INC / Naperville 60563),
`7d1d789828351ecf` (GENTLE DENTAL CARE P.C. / Chicago 60651).
- Each keeps its full original 10-key ready row verbatim under `preserved_ready_row` +
  `backfill_lane="operating_status_unverified"`; `network_id` retained (network intelligence preserved).
- Identical handling to the Pass-1 4-row operating-status demotion you already approved.

### Fix B — ao:SHAFI_REEM EXPLICITLY RELEASED as dentist_multi (all 3 stay in ready)
`ba663f30996016ce`, `fc658bf62642d908`, `6da55130228a9c54`.
- The 2 branded_dso rows (ba663f30, fc658bf6) **corrected DOWN to dentist_multi** to remove the mixed
  branded_dso/dentist_multi inconsistency; 6da55130 was already dentist_multi (reach3 QA regate).
- New explicit decision recorded at `ao_network_release_decisions.decisions["ao:SHAFI_REEM"]`:
  evidence_quality=verified, decision=release_eligible, tier=dentist_multi, pe_backed=false,
  `tier_corrections` listed, `covered_by_prior_release="ao:SHAFI_SOHAIL"`.
- **Rationale (chose your option 1 = release, per your conservative recommendation):** covered by the
  prior VERIFIED `ao:SHAFI_SOHAIL`/Two Rivers Dental release (also dentist_multi, pe_backed=false; whose
  `stale_closed_notes` already name Reem Shafi / Two Rivers) AND the reach3 QA `regate_audit` of
  6da55130 ("branded_dso→dentist_multi: no MSO; dentist-owned multi only"). Tier kept **consistent** with
  that prior Shafi/Two Rivers adjudication — Two Rivers was NOT found to independently satisfy
  branded_dso/platform criteria (no documented MSO/management-company/platform). **pe_backed=false was
  NOT the downgrade reason** — the tier rests on absence of MSO structure (DSO=STRUCTURE) + prior-network
  consistency. Each row's `reasoning` carries the release note + "(tier corrected from branded_dso)".

### Fix C — duplicate-door leak DEMOTED ready → needs_more_evidence
`ff41419130267bd9` (Peters, Erika / 2340 N Clybourn Ave / phone 773-528-2205; was ready as dentist_multi
via Fleet B ein-015, EIN 362686478).
- Same physical door as `f94fb29cc7d444cd` (CHICAGO DENTAL PROFESSIONALS INC, prior true_independent, in
  NO live bucket) — the door cannot carry both consolidated and independent.
- Demoted with `preserved_ready_row` + `backfill_lane="duplicate_door_tier_conflict"`.
- `buckets.duplicate_denominator_blocked.currently_in_candidate_set` updated from stale `[]` to a leak/fix
  record; the pair added to `duplicate_denominator_blocked.pairs` (now the 9th pair).

## Resulting counts (core buckets mutually exclusive — 0 collisions re-asserted)
- ready_to_validate **310** (dentist_multi **148**, branded_dso **94**, stealth_dso 21, true_independent 30,
  institutional 10, single_loc_group 7) — matches your `post_fix_projection.ready_after_A_and_C_demote_B_released=310`.
- needs_more_evidence **167** (162 + 4 Fix A + 1 Fix C) | evidence_gap_backfill_queue **87** | conflicts **74** | rejected **7**
- core-universe distinct locations **558** unchanged (310+167+74+7 = 558).

## Validate-only result
`python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session gate_owner_reqa4_20260621 --validate-only`
→ "Loaded 310 classification rows … Validation OK … no DB/ledger/progress writes." Reset re-verified
intact afterward (PL tier-nonnull=0 / practices=0 / LEDGER=1 line / PROGRESS tier_tally all zeros,
undetermined_unreviewed=4439).

## Files to re-check (focused)
1. `_ready_to_validate_wave3_fixed_20260621.json` (310 rows — the validator-native fixed set).
2. `consolidation_candidate_manifest_20260621.json` — updated in place: `qa_mustfix_actions[-1]`
   (RE-QA #4 A/B/C record), `ao_network_release_decisions.decisions["ao:SHAFI_REEM"]`,
   `buckets.duplicate_denominator_blocked` (currently_in_candidate_set + pairs), `counts`, `_meta.reqa4_fix`.
3. Demoted rows now in `buckets.needs_more_evidence` (5 new entries, each with `preserved_ready_row`).

## Suggested focused-QA checks
1. **Fix B tier resolution** — confirm dentist_multi (not branded_dso) is the defensible tier for
   ao:SHAFI_REEM given no documented Two Rivers MSO/platform, and that the recorded rationale does NOT
   rest on pe_backed=false. If you believe Two Rivers independently meets branded_dso/platform criteria,
   flag it and the Gate Owner will re-hold or re-tier — no auto-decision.
2. **Fix A/C completeness** — any OTHER ready rows with the same operating-status risk or same-door tier
   conflict that should also be demoted? (5 demoted across Pass-1 + RE-QA #4 A, plus 1 duplicate-door.)
3. **Duplicate-denominator hygiene** — confirm `currently_in_candidate_set` now truthfully reflects the
   leak+fix (was falsely `[]`), and that no OTHER of the 16 documented dup-door ids leaked into the 310.

## Decision the user will make AFTER your re-check
- (a) approve the 310-row consolidation (`--allow-db-write`), OR
- (b) first work the backfill (87) / resolve the 74 conflicts (incl. Webster set) / mine the 694
  fleet_b_wave3 leads / release held protected networks (Sweis, Ramaha), re-validate, then approve.

Gate Owner will run `--allow-db-write` ONLY on the user's explicit "consolidate approved manifest."
