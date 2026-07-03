# Project Manager Handoff - Chicagoland Ownership Census Review

Author: Codex documentation/audit pass  
Date: 2026-07-02  
Repo: `/Users/suleman/dental-pe-tracker`  
Primary live app: `https://dental-pe-nextjs.vercel.app`  
Scope of this handoff: Chicagoland / Illinois ownership-census work only. Boston / Massachusetts remains parked.

## 1. Executive Summary

This repo has two related but separate ownership systems:

1. The legacy production floor, driven by `entity_classification` and `zip_scores.corporate_location_count`. This is what the live Next.js app currently uses for the 5.58 percent corporate floor.
2. A newer hand-verified ownership census, using `ownership_tier`, `pe_backed`, and supporting evidence columns. This is intended to classify every Chicagoland general-dental location into a richer 6-tier ownership model, with coverage shown explicitly.

The four Opus sessions plus Codex did real forward work, but nothing has been merged into the durable census columns yet. The current state is still intentionally frozen:

- `practice_locations.ownership_tier IS NOT NULL` = 0
- `practices.ownership_tier IS NOT NULL` = 0
- `data/dso_research/RESEARCH_HOME/LEDGER.jsonl` = 1 line
- `data/dso_research/RESEARCH_HOME/PROGRESS.json` = 0 reviewed, 4,439 undetermined
- The 310-row current ready file still validates with `consolidate_census.py --validate-only`
- No Wave 4 evidence has been consolidated into the DB or live app

The main documentation problem is fragmentation, not absence. Each agent wrote useful notes, but they are role-specific, partly redundant, and some are stale. This file is the PM-facing source of truth for review. Older files should be treated as audit trail unless this file explicitly references them as current.

Most important current next step:

Gate Owner should normalize Fleet B ranks 51-100, then request QA. Do not start Fleet B 101+ yet. The remaining hard-lead pool after 100 ranks is mostly brand-chain/surname noise, so throughput should shift toward a better generated queue rather than more broad agent fan-out.

## 2. Current Local State Verified On 2026-07-02

Read-only verification performed from repo root:

```bash
python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session PM_DOC_AUDIT_20260702 --validate-only
```

Result:

- Loaded 310 classification rows
- Validation OK
- validate-only complete
- No DB, LEDGER, or PROGRESS writes

Current census freeze check:

| Check | Current value |
|---|---:|
| `practice_locations.ownership_tier IS NOT NULL` | 0 |
| `practices.ownership_tier IS NOT NULL` | 0 |
| `RESEARCH_HOME/LEDGER.jsonl` lines | 1 |
| `PROGRESS reviewed_via_protocol` | 0 |
| `PROGRESS undetermined_unreviewed` | 4,439 |
| all watched GP locations from `zip_scores` | 4,801 |
| all watched corporate locations from `zip_scores` | 268 |
| IL GP locations from `zip_scores` | 4,439 |
| IL corporate locations from `zip_scores` | 249 |
| watched corporate NPIs | 1,152 |

Current local SQLite hash:

```text
data/dental_pe_tracker.db md5 = e2a89a02900d0366fad6d9ee06d23422
```

Important documentation correction: many June 21-22 artifacts cite `0dec26135bb4d6ee490dc16cfe892ca6` as the then-current DB md5. That md5 no longer matches the local DB on 2026-07-02. The census-specific freeze still holds: ownership columns are empty, LEDGER is untouched, and PROGRESS is reset. Treat the old md5 as a historical freeze proof for those artifacts, not as the current local baseline. Before any write, re-baseline deliberately and record the new hash.

Also note the stray file `data/dental_pe-tracker.db` is 0 bytes and should be ignored. The real DB is `data/dental_pe_tracker.db`.

## 3. What We Were Trying To Build

The goal was to stop treating the legacy corporate detector as the final consolidation answer. The legacy detector is useful, but it misses local-name DSOs, friendly-PC structures, and dentist-owned multi-location groups. The new target is a hand-verified directory of every Chicagoland general-dental location, with each `practice_locations.location_id` assigned one of these ownership tiers:

| Tier | Code | Meaning | Counts as consolidated? | Counts as DSO/PE? |
|---|---|---|---|---|
| T1 | `true_independent` | one dentist owns one location, positively earned | no | no |
| T2 | `single_loc_group` | multi-dentist one-location group, no MSO | yes | no |
| T3 | `dentist_multi` | dentist-owned multi-location group, no MSO | yes | no |
| T4 | `stealth_dso` | local-name practice with documented MSO/platform | yes | yes |
| T5 | `branded_dso` | established DSO/platform brand | yes | yes |
| T6 | `institutional` | FQHC, hospital, university, nonprofit, government | separate scope bucket | no |
| - | `undetermined` | not reviewed or unresolved | excluded | excluded |

Core methodology rules:

- The census unit is the deduped clinic door: `practice_locations.location_id`.
- Boston/MA is out of scope.
- `entity_classification` remains the legacy size/corporate axis. `ownership_tier` is a separate ownership axis.
- DSO tier requires structure: MSO, management company, platform, or established DSO brand.
- `pe_backed` is orthogonal. It is not the tier driver.
- AO reach, brand substring, same phone, co-location, referral directories, or "web_verified" without a transcribed URL are signals only, not proof.
- Every promotion needs durable evidence, preferably exact-address match on the owner/platform locator or a whitelisted DB/legal artifact.
- The gate ceiling is `ready_for_validation`, not final.

## 4. Who Did What

There were five actors:

| Actor | Purpose | Produced |
|---|---|---|
| Codex | Orchestrator and local verifier. Wrote prompts, checked files, designed gates, kept sessions aligned. | This PM handoff; prior prompt instructions; local audits |
| Gate Owner | Coordinator/normalizer. Converts evidence files into partitions and QA requests. Does no evidence hunting. | normalized partitions, QA requests, AUTH files, rollups |
| Main AO | Evidence researcher for AO/network conflicts, AO backfill, and focused addenda. | Lane 1 conflicts/AO backfill evidence, Lane 2 non-AO backfill evidence, LABINOV addendum |
| Fleet B | Bounded Phase-C web verification of ranked hard-signal leads. | top-50 evidence; ranks 51-100 evidence |
| QA | Independent adversarial reviewer. Reviews files only, writes verdicts. | Wave 4 initial verdict; Lane 2 verdict |

The user was effectively the courier between Codex and the four Opus sessions. The sessions coordinated via files under:

```text
data/dso_research/_wave4_20260621/autonomous/
```

This file-based design is sound for auditability, but it is slow and creates stale status files if not paired with one current rollup.

## 5. Authoritative Artifact Map

Use these files for review:

| Path | Status | Purpose |
|---|---|---|
| `data/dso_research/RESEARCH_HOME/PROJECT_MANAGER_HANDOFF_20260702.md` | current | this handoff |
| `data/dso_research/RESEARCH_HOME/00_MULTI_SESSION_CENSUS_MASTER_CONTEXT.md` | useful, partly historical | broad master context written by QA |
| `data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_ORCHESTRATION.md` | useful, partly historical | Gate view of roles and protocol |
| `data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md` | useful, partly historical | Main AO deep memory |
| `data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_FLEET_B.md` | useful, partly historical | Fleet B memory and 51-100 status |
| `data/dso_research/consolidation_candidate_manifest_20260621.json` | frozen current manifest | 310 current ready + sidecars |
| `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` | frozen current ready file | validator-native 310 rows |
| `scrapers/consolidate_census.py` | current validator/writer | fail-closed ownership-tier consolidator |
| `scrapers/migrate_ownership_tier_cols.py` | migration script | additive ownership-axis columns |
| `data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json` | QA-passed | initial Wave 4 partition |
| `data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` | QA-passed | initial Wave 4 verdict |
| `data/dso_research/_wave4_20260621/wave4_gate_normalized_lane2_partition_20260622.json` | QA-passed | Lane 2 partition |
| `data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json` | QA-passed | Lane 2 verdict |
| `data/dso_research/_wave4_20260621/wave4_hold1_labinov_operating_status_rescan_20260622.json` | addendum, not separately QA-requested | LABINOV/Destiny operating-status rescan |
| `data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622.json` | delivered, not Gate-normalized or QA-accepted | Fleet B ranks 51-100 evidence |
| `data/dso_research/_wave4_20260621/autonomous/DONE_FLEETB_PHASEC_51_100_20260622.md` | current for Fleet B band | Fleet B 51-100 completion handoff |

Treat these as historical or superseded where they conflict with current files:

- `data/dso_research/_wave4_20260621/wave4_gate_rollup_status_20260622.json`: useful, but section 5 says Fleet B 51-100 was pending. That was true when written and is now superseded by `DONE_FLEETB_PHASEC_51_100_20260622.md`.
- June 21-22 md5 attestations: historical. Current local md5 is `e2a89a02900d0366fad6d9ee06d23422`.
- `data/dso_research/RESEARCH_HOME/HANDOFF_GATE_OWNER_20260622.md` validate command: it shows a stale `--ready-file` form. The current script requires:

```bash
python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session SOME_NAME --validate-only
```

## 6. State Of The Work Product

### Frozen current 310

The current ready file has 310 rows and passes validate-only. It has not been consolidated into `ownership_tier`.

Manifest counts from `data/dso_research/consolidation_candidate_manifest_20260621.json`:

| Bucket | Count |
|---|---:|
| ready_to_validate | 310 |
| needs_more_evidence | 167 |
| conflicts | 74 |
| rejected | 7 |
| evidence_gap_backfill_queue | 87 |
| taxonomy_revised | 14 |
| core universe distinct locations | 558 |

Ready tier mix:

| Tier | Count |
|---|---:|
| dentist_multi | 148 |
| branded_dso | 94 |
| true_independent | 30 |
| stealth_dso | 21 |
| institutional | 10 |
| single_loc_group | 7 |

### Wave 4 initial partition

File:

```text
data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json
```

QA verdict:

```text
data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json
```

Status: `PASS_WITH_HOLDS`, 0 must-fix, no systemic Phase-C defect.

Bucket counts:

| Bucket | Count |
|---|---:|
| merge_eligible_new | 19 |
| corroborates_existing_ready | 3 |
| qa_attention_current_ready | 3 |
| hold_protected_network | 46 |
| hold_scope_specialist | 7 |
| hold_operating_status_or_same_door | 5 |
| hold_needs_more_evidence | 43 |
| rejected | 14 |
| refuted | 6 |

The 19 merge-eligible rows were 17 `dentist_multi (T3)` plus 2 `branded_dso (T5)`. They are not merged.

### Lane 2 non-AO backfill

File:

```text
data/dso_research/_wave4_20260621/wave4_gate_normalized_lane2_partition_20260622.json
```

QA verdict:

```text
data/dso_research/_wave4_20260621/autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json
```

Status: `PASS_WITH_HOLDS`, 0 must-fix. QA agreed that the +1 net-new corporate claim is correct and not overstated.

Bucket counts:

| Bucket | Count |
|---|---:|
| merge_eligible_new_corporate | 1 |
| corroborates_existing_corporate_no_lift | 12 |
| true_independent_confirmation | 2 |
| hold_needs_more_evidence | 2 |
| hold_operating_status_or_same_door | 2 |
| hold_scope_specialist | 3 |
| refuted | 3 |

The +1 corporate row is Schock Dental -> Dentologie River North (`5cd692a50e5c32b7`). The 12 Heartland/DCA/Aspen-like corroborations are no floor lift because they were already legacy corporate. The 2 `true_independent` confirmations are useful census information but not corporate.

### LABINOV / Destiny addendum

File:

```text
data/dso_research/_wave4_20260621/wave4_hold1_labinov_operating_status_rescan_20260622.json
```

Main AO found:

- `fd93e6934ac6c59c` Destiny Dental Oak Park is open and should remain ready; the prior closed/relocated flag was a false positive.
- 7 `ao:LABINOV_BORIS` D2 shell addresses remain `hold_operating_status`.
- `fd93e6934ac6c59c` is better understood as a Destiny/ProSmile sibling under `ao:WILSON-ADELEKE_SIMONE`, not literal `ao:LABINOV_BORIS`.

This addendum has not been separately requested/reviewed by QA. It is not a blocker for Wave 4 acceptance, but PM should review whether it should be folded into the next Gate rollup.

### Fleet B ranks 51-100

Files:

```text
data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622.json
data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622_qa.json
data/dso_research/_wave4_20260621/autonomous/DONE_FLEETB_PHASEC_51_100_20260622.md
```

Status: delivered, not accepted. Needs Gate normalization and fresh QA.

Disposition counts:

| Disposition | Count | Notes |
|---|---:|---|
| rejected | 25 | mostly surname-coincidence "X Dental" patterns |
| hold_needs_more_evidence | 16 | signals but no exact-address durable artifact |
| hold_protected_network | 4 | NITTINGER/SHAFI protected holds |
| hold_scope_specialist | 3 | perio, endo, Loyola institutional |
| merge_eligible_new | 2 | two T5 DSO/PE candidates |

The two merge-eligible rows:

| Rank | location_id | Practice | Address | Proposed tier | Evidence claim |
|---:|---|---|---|---|---|
| 79 | `e4604698cb78a23a` | Grove Dental | 160 E Boughton Rd, Bolingbrook 60440 | T5 branded_dso | own locator exact match; NADG / Abry |
| 100 | `6c31d482e9a63431` | Advanced Family Dental | 150 Brookforest Ave, Shorewood 60404 | T5 branded_dso | Great Lakes Dental Partners exact match; Shore Capital |

Important judgment call:

- Rank 83, Chicago Dentistry LLC / Archer Dentistry (`8d81d4516f493d1e`), was downgraded from agent `merge_eligible_new` to `hold_needs_more_evidence`. The evidence supports a real dentist-owned 5-location group, but no MSO/DSO/PE. Under current rules it is not a T4/T5 corporate-floor lift. It may be T3 `dentist_multi` if the census treats dentist-owned multi-site groups as consolidated.

## 7. Documentation Problems Found And How To Treat Them

1. There is no single old file that is both complete and fully current. The best pre-existing overview is `00_MULTI_SESSION_CENSUS_MASTER_CONTEXT.md`, but this PM handoff supersedes it for July 2026 review.
2. `wave4_gate_rollup_status_20260622.json` is stale on Fleet B 51-100. It says output pending. Later Fleet B files show output complete.
3. Several files cite the historical md5 `0dec...`. Current local DB md5 is `e2a89...`; the census freeze should be checked through ownership columns, LEDGER, and PROGRESS, then re-baselined.
4. `HANDOFF_GATE_OWNER_20260622.md` has a stale validate-only command using `--ready-file`. The actual script takes the results JSON as positional arg and requires `--session`.
5. `FLEET_B_AUTONOMOUS_INSTRUCTIONS_20260621.md` still says "do not start 51-100 unless AUTH exists" and gives an old expected output filename ending 20260621. Fleet B has already completed 51-100 and wrote the 20260622 file.
6. Some agent docs use "floor", "census candidate", "ready", and "corporate lift" inconsistently. The PM should keep these separate:
   - `ready_for_validation` = evidence ceiling, not DB write
   - `ownership_tier` census = currently empty
   - legacy floor = `entity_classification`/`zip_scores` currently driving the live app
   - corporate-floor lift = only T4/T5-equivalent changes to legacy dso classes, not T3 dentist-owned multi-location groups
7. Historical JSON verdicts and evidence files should not be edited. They are audit trail. Fixes should be made in new rollup/handoff files or in explicitly versioned normalized artifacts.

## 8. Methodology Assessment

What is working:

- File-based coordination preserved auditability. Every role's output is on disk.
- The strict evidence bar prevented garbage promotions from brand substrings, AO-only clusters, FQHC/name collisions, and exact-address misses.
- QA caught real problems: protected networks, Affordable/ClearChoice scope, Sonrisa/CDCA FQHC ambiguity, stale operating-status flags, and Heartland name collisions.
- The separation between `entity_classification` and `ownership_tier` is architecturally correct. It lets the app preserve old behavior while a deeper census matures.
- `consolidate_census.py` is intentionally fail-closed and validates the 310 file without writes.

What is too slow or brittle:

- Human-relayed four-session coordination does not scale to 4,439 locations.
- One-off Gate generators such as `_gen_gate_partition_20260621.py` are auditable but hardcoded. They should not become the production workflow.
- Fleet B broad Phase-C batches are showing diminishing returns. Ranks 51-100 produced only 2 merge candidates and 25 rejects; after rank 100, the remaining hard-lead pool appears mostly brand-chain/surname noise.
- QA is necessary for high-risk additions, but full adversarial review on every low-risk true-independent confirmation may be overkill once validators are stronger.
- Documentation grew faster than the canonical state model. Future sessions need one current status ledger plus immutable artifacts, not multiple competing "start here" files.

Bottom line:

The strategy is directionally right for quality, but not yet scalable enough for a full 4,439-location census. Keep the evidence bar. Replace the ad hoc multi-agent fan-out with generated work queues, deterministic validators, and tiered QA.

## 9. Recommended Strategy Going Forward

### A. Stop broad Fleet B after 51-100 until the queue is redesigned

Do not authorize ranks 101-158 as a simple continuation. The remaining hard-lead pool after top100 + current 310 is about 55 rows and appears to be almost entirely `brand_chain` only:

- 52 `brand_chain`
- 3 `brand_chain + intel_keyword`

That is low-yield and high false-positive risk. If any of those are worked, first re-rank them with stricter filters:

- existing `db_affiliated_dso`
- exact DSO locator candidate
- real parent company
- real EIN cluster
- DSO/platform domain
- known PE platform acquisition
- high provider count plus platform evidence

Brand-chain alone should default to hold or reject unless a separate artifact is found.

### B. Normalize Fleet B 51-100 next

Immediate next task:

1. Gate Owner reads `wave4_lane3_phasec_51_100_evidence_20260622.json`.
2. Gate writes a new normalized partition, e.g. `wave4_gate_normalized_lane3_51_100_20260702.json`.
3. Gate writes `REQUEST_QA_REVIEW_WAVE4_LANE3_51_100_20260702.md`.
4. QA reviews.
5. No merge and no new ready file until explicit user authorization.

Expected Gate treatment:

- Grove Dental and Advanced Family Dental likely enter `merge_eligible_new`.
- NITTINGER/SHAFI rows remain `hold_protected_network`.
- Loyola/perio/endo remain `hold_scope_specialist`.
- Archer Dentistry remains hold unless user/PM decides T3 dentist-owned multi-site groups should count as consolidated census additions.

### C. Build a real queue generator

Create a script that produces a single ranked `ownership_census_work_queue` artifact from SQLite, with columns:

- `location_id`
- practice name, address, city, ZIP, phone, website
- current `entity_classification`
- provider count
- NPI/legal names
- candidate signal types
- reason for priority
- prior artifact references
- current bucket if already seen
- expected evidence type needed
- blocked policy flags
- duplicate/same-door flags

The queue should exclude:

- MA rows
- specialist, non_clinical, da_unverified, duplicate_location
- already current 310 unless the task is explicit corroboration/demotion
- already Wave 4 reviewed rows unless the task is explicit addendum
- `parent_iusa=000000000`

Prioritize in this order:

1. Structural DSO candidates not yet reviewed: exact locator, real parent, real EIN cluster, known platform.
2. Legacy false-positive demotion candidates that could lower the floor.
3. High-density zero-corp ZIPs where current detector is implausibly low.
4. Large groups and solo_high_volume rows needing T1/T2/T3 classification.
5. Brand-chain-only rows last.

### D. Automate exact-address locator verification

For known DSOs/platforms, build reusable locators and address-normalization checks instead of repeatedly asking agents to search:

- Heartland
- Aspen/TAG
- Dental Dreams/KOS
- NADG
- Great Lakes Dental Partners
- DCA
- Smile Brands
- Familia
- Dentologie
- Affordable/ClearChoice, if scope is decided

The output should be deterministic:

```json
{
  "location_id": "...",
  "candidate_platform": "...",
  "locator_url": "...",
  "exact_address_match": true,
  "matched_street": "...",
  "matched_zip": "...",
  "evidence_snapshot": "..."
}
```

Agents should only handle cases the deterministic verifier cannot resolve.

### E. Tier the QA effort

Keep full adversarial QA for:

- all T4/T5 net-new DSO/PE candidates
- protected networks
- scope-sensitive classes
- demotions of existing corporate rows
- same-door/duplicate conflicts
- medium confidence rows

Use lighter validation for:

- true-independent confirmations with own-site named owner evidence
- clear T3 dentist-owned multi-site groups with exact owner/locator but no MSO
- rows that are simple rejections of brand-substring false positives

This keeps quality while reducing review bottlenecks.

### F. Decide policy holds before large consolidation

The PM should force explicit decisions on:

- Affordable Dentures / ClearChoice: in or out of GP floor?
- Institutional/FQHC rows: separate denominator, excluded, or reported as own bucket?
- T3 dentist-owned multi-site groups: included in "consolidated" census headline, but not DSO/PE. Confirm display language.
- Protected networks: keep as explicit holds unless whole-network release is re-validated.
- Legacy false-positive suspects: should they be demoted from legacy corporate before any new floor is published?

## 10. App And Codebase Review Instructions For The Project Manager

Please review the app and codebase end to end before approving consolidation or frontend changes. The central question is whether this is the right strategy for correctly classifying about 4,439 Chicagoland general-dental locations across the watched IL ZIPs.

Review these parts first:

1. `dental-pe-nextjs/`
   - Confirm the live app is still displaying the legacy `entity_classification` floor from Supabase.
   - Confirm no UI currently consumes `ownership_tier`.
   - Review language around "corporate", "consolidated", "known consolidated", "floor", and "coverage".
   - Verify the user can understand the difference between:
     - confirmed legacy corporate floor
     - hand-reviewed ownership-census coverage
     - DSO/PE share
     - dentist-owned multi-location consolidation
2. `src/lib/constants/entity-classifications.ts`
   - Confirm `entity_classification` is still the primary ownership display helper.
   - Decide whether a new helper is needed for `ownership_tier`.
3. `src/lib/constants/consolidation-honesty.ts`
   - Confirm the floor/ADA band still reflects legacy data only.
   - Decide how a coverage-based census result should coexist with or replace this band.
4. `src/lib/supabase/queries/`
   - Confirm large queries paginate correctly.
   - Identify where ownership-tier fields would need to be selected once consolidated.
5. `scrapers/migrate_ownership_tier_cols.py`
   - Confirm Supabase has matching ownership-tier columns before any live sync.
6. `scrapers/consolidate_census.py`
   - Review validator assumptions, required schema, and write behavior.
   - Confirm it should update only ownership-axis columns and never `entity_classification`.
7. `scrapers/sync_to_supabase.py`
   - Decide how ownership-tier columns get synced after consolidation.
   - Avoid destructive partial sync paths unless dependents are understood.
8. `data/dso_research/_wave4_20260621/`
   - Review normalized partitions and QA verdicts, not just chat summaries.
9. `data/dso_research/consolidation_candidate_manifest_20260621.json`
   - Review current 310 and sidecars.
10. Live URL: `https://dental-pe-nextjs.vercel.app`
   - Walk every route where consolidation/corporate ownership appears:
     - Home
     - Market Intel
     - Warroom
     - Launchpad
     - Job Market
     - Buyability
     - Data Breakdown
   - Verify labels do not overclaim the detector floor as true consolidation.
   - Decide what the UI should show during partial census coverage.

Recommended display model once the census starts writing:

```text
Confirmed legacy DSO floor: X% of GP locations
Hand-reviewed ownership census coverage: N / 4,439 locations
Among reviewed:
  consolidated (T2-T5): A%
  DSO/PE structure (T4-T5): B%
  true independent (T1): C%
  institutional/scope-held: D%
Unreviewed: explicitly undetermined
```

Do not publish a single "true consolidation percent" until coverage is high enough and the method is stable.

## 11. Suggested Immediate Work Plan

1. Documentation baseline:
   - Treat this file as current.
   - Keep older handoffs as audit trail.
   - Update only pointer docs, not historical JSON verdicts.
2. Gate normalization:
   - Normalize Fleet B 51-100.
   - Request QA.
3. QA:
   - Review only the Gate-normalized 51-100 partition and cited evidence.
4. Policy decisions:
   - Decide Affordable/ClearChoice, institutional/FQHC, and T3 dentist-owned multi-site display semantics.
5. Engineering:
   - Build a generated work queue and deterministic locator verifier before more agent fan-out.
6. Frontend:
   - Design an ownership-census coverage panel before turning on DB writes.
7. Consolidation:
   - Only after PM and user approve, assemble a versioned addendum candidate.
   - Run validate-only.
   - Then, and only then, use the protected DB-write path.

## 12. Commands For The PM

Read-only census freeze check:

```bash
cd /Users/suleman/dental-pe-tracker
python3 - <<'PY'
import hashlib, json, sqlite3
db='data/dental_pe_tracker.db'
print('db_md5', hashlib.md5(open(db,'rb').read()).hexdigest())
c=sqlite3.connect(db)
for t in ('practice_locations','practices'):
    print(t, c.execute(f"select count(*) from {t} where ownership_tier is not null").fetchone()[0])
print('ledger_lines', sum(1 for _ in open('data/dso_research/RESEARCH_HOME/LEDGER.jsonl')))
p=json.load(open('data/dso_research/RESEARCH_HOME/PROGRESS.json'))
print('reviewed', p['census_status']['reviewed_via_protocol'])
print('undetermined', p['tier_tally']['undetermined_unreviewed'])
PY
```

Validate the frozen 310 ready file:

```bash
python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session PM_REVIEW --validate-only
```

Summarize current Wave 4 buckets:

```bash
python3 - <<'PY'
import json
for path in [
  'data/dso_research/_wave4_20260621/wave4_gate_normalized_partition_20260621.json',
  'data/dso_research/_wave4_20260621/wave4_gate_normalized_lane2_partition_20260622.json',
]:
    d=json.load(open(path))
    print('\\n', path)
    for k,v in d['buckets'].items():
        print(k, len(v) if isinstance(v, list) else type(v).__name__)
PY
```

Summarize Fleet B 51-100:

```bash
python3 - <<'PY'
import json, collections
rows=json.load(open('data/dso_research/_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622.json'))['rows']
print(collections.Counter(r['disposition'] for r in rows))
for r in rows:
    if r['disposition'] == 'merge_eligible_new':
        print(r['rank'], r['location_id'], r['practice_name'], r['zip'], r['proposed_tier'], r['evidence_urls'])
PY
```

Check current legacy floor:

```bash
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('data/dental_pe_tracker.db')
print('all watched', c.execute("select sum(total_gp_locations), sum(corporate_location_count) from zip_scores").fetchone())
print('IL only', c.execute("select sum(total_gp_locations), sum(corporate_location_count) from zip_scores where state='IL'").fetchone())
print('corp NPIs', c.execute("select count(*) from practices p join watched_zips w on p.zip=w.zip_code where p.entity_classification in ('dso_regional','dso_national')").fetchone()[0])
PY
```

## 13. Final Recommendation

Do not approve immediate consolidation just because there are QA-passed artifacts. First, have the PM review the methodology, the live app semantics, and the separation between the legacy corporate floor and the hand-reviewed ownership census.

The evidence discipline is good. The current process is too manual. The right path is:

1. Finish the pending Fleet B 51-100 Gate+QA loop.
2. Freeze broad Fleet B fan-out.
3. Build a scalable work queue and exact-address locator verifier.
4. Decide policy holds.
5. Add frontend census-coverage semantics.
6. Only then consolidate a versioned, QA-passed candidate set.

This preserves quality without turning the rest of the 4,439-location project into slow circular re-review of practices already handled.
