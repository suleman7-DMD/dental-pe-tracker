# QA / VALIDATION-GATE HANDOFF — Chicagoland Ownership Census (2026-06-21)

**For:** the next QA / validation-gate session (fresh context)
**From:** QA / validation-gate session (RE-QA #4 + #5)
**Role contract:** independent adversarial QA. **REVIEW-ONLY.** No DB writes. No `--allow-db-write`. No mutation of the manifest, `LEDGER.jsonl`, `PROGRESS.json`, `ownership_tier`, or any prior QA file. Write **new** files only.

---

## 0. Standing hard rules (still in effect — do not violate)

- **Chicagoland / IL only.** Boston/MA is PARKED. Do not investigate MA.
- **No DB writes. No `--allow-db-write`.** No `ownership_tier` / `LEDGER` / `PROGRESS` mutation.
- **No-anchor math:** consolidation % is computed FROM the census ledger with coverage. NEVER anchored to ADA 14.6%, "30% metro," or the legacy 5% `entity_classification` floor. (The 5% floor is a *different axis* — leave it alone.)
- **Never silent-default to `true_independent`.** It is EARNED with evidence. Ambiguous → `undetermined` / `needs_verification`.
- **Do not touch `entity_classification`** (legacy axis) unless explicitly told — it is a corroborating signal only.
- **Protected networks** (do-not-release without main-session release): SHAFI, BELKIC, NITTINGER, AQEL, BRUNETTI, SWEIS, LABINOV, RAMAHA.
- **`pe_backed=false` is NEVER an automatic reason** to downgrade `branded_dso` → `dentist_multi`. DSO tier rests on STRUCTURE (DSO/MSO/management-co/platform/established brand), not on PE status.
- **DO NOT** run `data/dso_research/census_batches_remaining_20260621.json` as a mass final-classification wave.
- Treat all `final_ready` / `final_*` agent outputs as `ready_for_validation`, **not** final truth.
- `consolidate_census.py --allow-db-write` is **NOT authorized** until the user explicitly says **"consolidate approved manifest."**

---

## 1. The 6-tier model (LOCKED)

| Tier | Meaning |
|------|---------|
| **T1 `true_independent`** | One dentist, ONE location. EARNED with evidence, never defaulted. |
| **T2 `single_loc_group`** | 2+ UNRELATED dentists, one location, dentist-owned. |
| **T3 `dentist_multi`** | Dentist-owned multi-location, NO separate DSO/MSO/platform. |
| **T4 `stealth_dso`** | Local / friendly-PC brand backed/managed by a DSO/MSO/PE platform. |
| **T5 `branded_dso`** | DSO/platform/management-co structure OR established DSO brand (even if family-owned / non-PE). |
| **T6 `institutional`** | FQHC / hospital / university / government. |
| `undetermined` | Ambiguous — held for verification. |
| `pe_backed` | **Orthogonal boolean**, set ONLY from documented MSO/PE evidence. |

**Headline rules:** `consolidated = T2+T3+T4+T5`; `dso_pe = T4+T5 only`.

---

## 2. Canonical objects & key paths

| Object | Path |
|--------|------|
| **Canonical manifest** (REVIEW-ONLY) | `data/dso_research/consolidation_candidate_manifest_20260621.json` (mtime `1782072689` at RE-QA #5) |
| **Current validator-native ready file** | `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` ← **310 rows, USE THIS** |
| STALE ready file (superseded, audit only) | `data/dso_research/_ready_to_validate_wave3_20260621.json` (315 rows — pre-fix; do NOT consume) |
| Consolidate script | `scrapers/consolidate_census.py` |
| Pipeline DB | `data/dental_pe_tracker.db` |
| Ledger (source of truth for coverage) | `data/dso_research/RESEARCH_HOME/LEDGER.jsonl` |
| Progress | `data/dso_research/RESEARCH_HOME/PROGRESS.json` |

**Validator semantics:** `consolidate_census.py --validate-only` is a **SCHEMA / DB-state gate ONLY**. It loads the ready file, checks schema and that target `practice_locations.ownership_tier IS NULL` (no overwrite without `--allow-rereview`), then exits BEFORE any write. It does **NOT** re-judge evidence or operating status. Run exactly one of `--validate-only` | `--allow-db-write`. Never pass `--allow-db-write` until the user authorizes.

---

## 3. QA verdict history

| Pass | Object | Verdict | File |
|------|--------|---------|------|
| RE-QA #2 | merged 123-row manifest | PASS | `ownership_manifest_QA_merged_20260621.json` (+ `_revision_signoff`, `_addendum_refined_criteria`) |
| Fleet B lane3 | Fleet B evidence | PASS | `ownership_evidence_QA_fleet_b_lane3_20260621.json` |
| RE-QA #3 | reach4 + lane1B merge (Wave 2, 210 rows) | PASS | `ownership_manifest_QA_reach4_lane1b_merge_20260621.json` |
| pre-Wave3 demotion | 4-row MUST-FIX re-merge (ready 210→206) | PASS | `ownership_manifest_QA_remerge_demotion_20260621.json` |
| **RE-QA #4** | **Wave 3 manifest (315 ready)** | **PASS WITH MUST-FIX (A/B/C)** | `ownership_manifest_QA_wave3_reqa4_20260621.json` |
| **RE-QA #5** | **confirm A/B/C applied (310 ready)** | **PASS — no outstanding MUST-FIX** | `ownership_manifest_QA_wave3_reqa5_20260621.json` |

**These QA files are immutable. Do not edit them. Append new verdicts as new files.**

---

## 4. LATEST VERDICT (RE-QA #5): **PASS — no outstanding MUST-FIX**

The Gate Owner re-merged the manifest and produced the fixed validator-native file. All three RE-QA #4 MUST-FIX classes are applied and independently verified. Ready dropped 315 → **310**.

### Counts at RE-QA #5 (all PASS, 0 collisions)
- ready_to_validate **310** | needs_more_evidence **167** | conflicts **74** | rejected **7** | core-universe distinct **558**
- Ready tier mix: dentist_multi **148** / branded_dso **94** / true_independent **30** / stealth_dso **21** / institutional **10** / single_loc_group **7**
- `consolidated` (T2+T3+T4+T5) in ready = **270**; `dso_pe` (T4+T5) = **115**

---

## 5. The A/B/C MUST-FIX and how each was verified

### A — operating-status demotions (4 subject-door closed/relocated rows)
Same defect class as the original pre-Wave3 4: the row's OWN counted door is self-flagged closed/relocated, which `--validate-only` cannot detect.

| location_id | practice | issue |
|---|---|---|
| `f6c6290c16d20224` | Pinewood Dental PC, Orland Park 60467 | relocated to Lemont; NPPES address stale |
| `822d3012aedf32b9` | Optimal Dental, Tinley Park 60477 | own row: "Yelp shows closed" |
| `77357c36224272c8` | Dental Design Group / Smile Designers, Naperville | "closed on Yelp; Da Vinci now at address" |
| `7d1d789828351ecf` | Gentle Dental Care P.C., Chicago 60651 | self-flagged "stale/closed shell" |

**Verified:** all 4 in `needs_more_evidence`, each with `preserved_ready_row` + `backfill_lane="operating_status_unverified"`.
*(9 sibling/legacy "closed" notes were adjudicated in RE-QA #4 and correctly LEFT in ready — closure referred to a different sibling door, not the subject.)*

### B — ao:SHAFI_REEM explicit adjudication (3 rows; protected SHAFI surname)
Two Rivers Dental / Dr. Reem Shafi (~20+ Chicagoland offices under distinct local trade names). In RE-QA #4 these 3 rows had entered ready via the generic reach3 gate with NO explicit protected-network release, plus a mixed-tier inconsistency (2 branded_dso, 1 dentist_multi).

**Verified:** `ao_network_release_decisions.decisions['ao:SHAFI_REEM']` now exists with `network_evidence_quality="verified"`, `decision="release_eligible"`, `covered_by_prior_release="ao:SHAFI_SOHAIL"`. Both branded_dso rows corrected → dentist_multi, so all 3 (`ba663f30996016ce`, `fc658bf62642d908`, `6da55130228a9c54`) are uniformly **dentist_multi, pe_backed=false**. The downgrade is justified on the **DSO=STRUCTURE rule** (no documented MSO/management-co/platform) and consistency with the prior verified Two Rivers release — **explicitly NOT** a pe_backed=false downgrade. Released branch → ready stayed at 310 (not 307).
- *Non-blocking residual:* a ~20-office single-owner trade-name network *could* be read as branded_dso; the Gate Owner applied DSO=STRUCTURE consistently. Defensible and internally consistent — recorded, not a defect.

### C — duplicate_denominator_blocked leak (1 row)
`ff41419130267bd9` (Peters, Erika / 2340 N Clybourn Ave / 773-528-2205, Fleet B `ein-015`) had leaked into ready as dentist_multi. It is a `duplicate_denominator_blocked` ID sharing the SAME physical door (same phone) with `f94fb29cc7d444cd` (CHICAGO DENTAL PROFESSIONALS INC, prior true_independent) — a same-door conflict that location_id dedup cannot catch. The DDB `currently_in_candidate_set` was stale `[]`.

**Verified:** `ff41419130267bd9` demoted to `needs_more_evidence`, `preserved_ready_row` + `backfill_lane="duplicate_door_tier_conflict"`; `duplicate_denominator_blocked.currently_in_candidate_set` updated with a "LEAK FOUND + FIXED 2026-06-21" record; twin `f94fb29cc7d444cd` confirmed in NO live bucket.

### Cross-cutting verification (RE-QA #5)
- **validate-only:** `Loaded 310 ... Validation OK ... no DB/ledger/progress writes` on the fixed file.
- **Zero DB writes (definitive):** `data/dental_pe_tracker.db` md5 **identical** before/after = `0dec26135bb4d6ee490dc16cfe892ca6`; `PL ownership_tier IS NOT NULL` = 0→0; `LEDGER.jsonl` = 1 line→1 line; `PROGRESS.json` tier tallies all 0, `undetermined_unreviewed` = 4439 unchanged.
- **Fixed file == manifest bucket:** 310 == 310 exactly, 0 drift.
- **Sidecars preserved:** ao wave1 6 / wave2_reach4 14 / wave3_reach3 51 / individuals 13; fleet_b_wave3 720 (local 637 / website 79 / structural 4).
- **Held networks no-leak:** SWEIS / RAMAHA / AQEL / BELKIC = 0 in ready; Webster contested set held in conflicts.

---

## 6. Remaining risk areas to watch in FUTURE waves

These are the recurring failure modes this gate has caught. Re-check every one on any new merge:

1. **Closed/stale subject-door rows.** The validator cannot see operating status. Scan every new ready row for self-flags ("closed," "Yelp shows closed," "relocated," "stale shell," "now at same address"). **Separate subject-door closure (DEMOTE → `operating_status_unverified`) from sibling/legacy-location notes (OK to keep).** Adjudicate every "closed" mention explicitly.
2. **`duplicate_denominator_blocked` leaks.** Any new ready id that is also a DDB id, OR shares a physical door (same normalized address / same phone) with another row carrying a *conflicting* tier. location_id dedup will NOT catch same-door duplicates. Confirm `currently_in_candidate_set` is kept current. Demote with `backfill_lane="duplicate_door_tier_conflict"` until the door is reconciled to one canonical row + one tier.
3. **Implicit protected-network releases.** Any ready row whose network/surname is on the protected list (SHAFI, BELKIC, NITTINGER, AQEL, BRUNETTI, SWEIS, LABINOV, RAMAHA) MUST have an explicit entry in `ao_network_release_decisions.decisions` with `network_evidence_quality="verified"` OR a documented "covered by prior release." Reaching ready through a generic per-row gate is NOT a release.
4. **AO-reach-only rows.** AO co-occurrence reach is a discovery SIGNAL, not proof. Every ready row needs a durable artifact beyond reach: shared real EIN, documented DSO/PE/MSO parent or legal entity, verifiable locator/website URL, or the row's own `db_affiliated_dso`/`db_parent_company`. (RE-QA #4 confirmed 0/87 reach3 rows were reach-only — keep this bar.)
5. **Webster conflicts.** The Webster Dental contested set (Cicero/Evanston/Schaumburg/North Suburban + Berwyn Family Dental, Klyber Dental, Brite/Aqel) is CONTESTED (DSO vs dentist_multi across passes) and is held in `conflicts`. Do NOT promote any of it to ready without a main-session adjudication.
6. **`pe_backed=false` downgrades.** Never let `pe_backed=false` be the *reason* a branded_dso becomes dentist_multi. Require a STRUCTURE rationale.
7. **Stale validator-native files.** When a re-merge happens, confirm the ready FILE consumed by the validator matches `manifest.buckets.ready_to_validate` exactly (count AND id set). Older `_ready_to_validate_*` files persist for audit and can mislead — always validate the newest `_fixed` file and diff it against the manifest bucket.
8. **Fleet B artifact discipline.** Only `classified` (non-undetermined) rows are ready-eligible; all `needs_verification` stay sidecar LEADS. Each promoted Fleet B row must be EIN-cluster or known-DSO/PE-parent backed, not brand-substring / co-location-only. Honor `qa_flag` → backfill (e.g. `da_synthetic_npi`).

---

## 7. Current gate state

- **Consolidation is FROZEN.** No outstanding QA MUST-FIX. The 310-row fixed file passes `--validate-only` with zero DB writes; sidecars and held networks intact.
- `consolidate_census.py --allow-db-write` is **NOT authorized.** It runs ONLY when the user explicitly says **"consolidate approved manifest."**
- DB/LEDGER/PROGRESS are pristine: PL `ownership_tier` non-null = 0, LEDGER = 1 line, PROGRESS all-zero tallies, `undetermined_unreviewed` = 4439.

---

## 8. Recommended checklist for ANY next merge

Run this in order; write a fresh `ownership_manifest_QA_*_20260621.json` (or dated) verdict — never mutate prior ones.

1. **Re-read the canonical manifest** as the source of truth (don't trust agent summaries).
2. **Counts & partition:** ready / needs_more / conflicts / rejected; assert mutual exclusivity (**0 collisions**) and distinct-location total.
3. **Validator-native file parity:** newest `_ready_to_validate_*` file count AND id-set == manifest ready bucket (0 drift). Identify and ignore stale files.
4. **Closed/stale subject-door scan** (risk #1) — demote subject-door closures; adjudicate sibling notes explicitly.
5. **DDB / same-door leak scan** (risk #2) — id overlap + same-address/same-phone conflicting tiers.
6. **Protected-network release audit** (risk #3) — explicit `ao_network_release_decisions` entry or documented coverage for every protected row in ready.
7. **Durable-evidence-beyond-AO-reach** check on all new promotions (risk #4); Fleet B artifact discipline (risk #8).
8. **Tier-consistency / no `pe_backed=false` downgrade** (risk #6); reach3 regate convention = `candidate_tier`/`gate_status` are the corrected values (reach4 uses `final_tier`/`final_gate`).
9. **Sidecars preserved** (ao wave1 6 / wave2_reach4 14 / wave3_reach3 51; fleet_b_wave3 720) and **held networks** (Sweis/Ramaha/Aqel/Belkic 0 in ready; Webster in conflicts).
10. **Run `--validate-only`** on the newest fixed file with a **before/after DB md5 + LEDGER/PROGRESS snapshot** to prove zero writes.
11. **Write verdict** with exact MUST-FIX IDs if any; state gate authorization (always NOT authorized until the user's explicit "consolidate approved manifest").

---
*End of handoff. No manifest / DB / prior-QA-file mutation performed in producing this document.*
