# HANDOFF — True Independent Hardening Screen Run
**Author:** Codex QA · 2026-07-03  
**Mode:** Files-only; no SQLite/Supabase writes  
**Status:** First deterministic screen complete; Fable PM review required

## What was built

New read-only script:

```bash
python3 scrapers/screen_true_independent_hardening.py
```

Output artifact:

```text
data/dso_research/_lane_a_20260702/hidden_control_screen_20260703.json
```

The script joins Lane A `result_unit_*.json` rows back to `practice_locations`, then bridges each `location_id` to `primary_npi`, `org_npi`, and all `provider_npis` in `practices`. It emits signal vectors for false T1/T2/T3 risk:

- T1 with provider_count > 1 or multiple provider surnames.
- T1/T2/T3 with DB corporate classifier conflicts.
- T1/T2 with AO reach, shared EIN/TIN, shared phone, shared website, shared mailing, or non-clinical executive AO.
- T1/T2 supported only by directory/social/registry evidence.
- Stale-founder/history language that does not prove current ownership.

It does **not** re-tier rows. It creates a review queue only.

## Run result

Screened current Lane A banked result files:

- Result rows loaded: **2,934**
- Target rows screened: **2,413** (`true_independent`, `single_loc_group`, `dentist_multi`, classified only)
- Clean screen: **365**
- Suspects: **2,048**

Priority counts:

| Priority | Count | Meaning |
|---|---:|---|
| `block_before_merge` | 236 | Must not merge silently; PM/analyst adjudication required |
| `review_high` | 261 | Strong review queue; likely signal stacking or weak evidence + network signal |
| `review_medium` | 725 | Mostly evidence-strength/currentness review |
| `sample_low` | 826 | Weak or wording-only signal; useful for random audits |
| `clean_screen` | 365 | No deterministic signal fired |

`block_before_merge` by assigned tier:

| Tier | Count |
|---|---:|
| `true_independent` | 126 |
| `single_loc_group` | 96 |
| `dentist_multi` | 14 |

Top signal counts overall:

| Signal | Count |
|---|---:|
| `directory_only_support` | 669 |
| `shared_phone_multiple_locations` | 546 |
| `stale_founder_history` | 330 |
| `ao_not_provider_or_practice_name` | 289 |
| `ao_reaches_multiple_locations` | 185 |
| `t2_provider_count_lte1` | 164 |
| `shared_website_domain` | 137 |
| `shared_ein_or_parent_tin` | 103 |
| `t1_group_entity_classification` | 89 |
| `t1_provider_count_gt1` | 85 |
| `t1_multiple_provider_surnames` | 81 |
| `db_corporate_conflict` | 33 |
| `ao_nonclinical_exec_title` | 16 |

## First interpretation

This confirms the core QA concern: T4/T5 are getting adversarial verification, but T1/T2 still need a stronger proof gate. The result does **not** mean 2,048 rows are wrong. It means many rows do not meet the newly widened standard for proving true solo owner-operator status.

The most important subset is the 236 `block_before_merge` rows. Those should be treated as a pre-merge gate.

Examples from the blocker queue:

- `c2c7539541dafe5f` — AMY MARTIN DDS PC, assigned `true_independent`, DB says `large_group`, provider_count 43. This is not a clean T1 under the user's definition.
- `3a1fb3f4223c5cd9` — PARKER AND ASSOCIATES, assigned `true_independent`, DB says `dso_regional`, provider_count 2, shared EIN/TIN signal.
- `719094a274f626fe` — Aspen Dental, assigned `true_independent`, DB corporate conflict. Should not merge silently without correction/hold.
- `f91cac2553a6afe3` — Aspen Dental, assigned `single_loc_group`, DB corporate conflict.
- `1518ac8ad8df5e0c` — DENTAL ASSOCIATES OF NORTH PIER, assigned `single_loc_group`, non-clinical executive AO + shared phone/domain signals.

Caveat: a DB corporate conflict is not automatically truth. Old detector labels can be stale or wrong. It is a blocker because the row has contradictory evidence, not because the row should be auto-promoted to DSO.

## Recommended Fable next steps

1. Do not run Lane A consolidation until every `block_before_merge` row is accepted, corrected, or moved to a hold bucket.
2. Review blocker rows in this order:
   - `db_corporate_conflict`
   - `t1_provider_count_gt1` / `t1_group_entity_classification`
   - `ao_nonclinical_exec_title`
   - stacked network signals: AO + EIN/phone/domain/mail
3. For T1 rows with provider_count > 1, default action should be correction to T2 or hold unless Fable can prove those extra NPIs are stale/non-practicing/no longer at the office.
4. For directory-only T1/T2 rows, do not count as high-confidence until current owner evidence is added or the row is downgraded to medium/hold.
5. Add a separate T1/T2 audit after the DSO verifier pass:
   - Include all 236 blockers or at least all hard-signal blockers.
   - Sample 20-50 from `review_high`.
   - Sample 20 from directory-only `review_medium`.
6. Persist the signal vector or a reduced version of it during consolidation so the future UI can show why a row is "true solo owner-operated" rather than merely "not known corporate."

## Command recap

```bash
python3 -m py_compile scrapers/screen_true_independent_hardening.py
python3 scrapers/screen_true_independent_hardening.py
```

Both completed successfully.
