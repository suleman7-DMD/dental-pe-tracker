# HANDOFF - Codex Coordinator / User Strategy Session

**Date:** 2026-06-21  
**Repo:** `/Users/suleman/dental-pe-tracker`  
**Role:** coordinator / rigor gate / session-alignment lead. Do not act as Gate Owner, QA, Main AO, or Fleet B unless user explicitly asks; instead synthesize updates, inspect files locally, and give exact prompts/instructions to the right session.

## Non-Negotiable Rules

- **Chicagoland/IL only. Boston/MA is parked.**
- **No DB writes unless the user explicitly says exactly:** `consolidate approved manifest`.
- Do not casually say that trigger phrase unless recommending or quoting it as the protected trigger.
- Until that explicit trigger, consolidation is frozen. No `--allow-db-write`.
- `AO reach` is a discovery signal, not ownership proof.
- DSO tier requires **structure**: MSO / management company / platform / established DSO brand. PE backing is an orthogonal boolean. `pe_backed=false` does not downgrade a DSO; `pe_backed=true` alone does not make something DSO.
- Preserve network intelligence sidecars. Do not flatten away operator/family/brand/legal-entity/evidence-chain/stale-closed metadata.
- Treat closed/stale subject-door rows, duplicate-door rows, and implicit protected-network releases as high-risk until explicitly adjudicated.
- Fleet B deterministic DB-only lanes are exhausted. Do not re-mine affiliated_dso_chain, da_officers, DBA, or phone clustering.
- Do not launch broad AO reach=2 long-tail hunting unless user/Gate/QA explicitly authorize it.

## Current Canonical State

The 2026-06-21 reset/consolidation gate is clean and frozen.

Canonical files:

- Manifest: `data/dso_research/consolidation_candidate_manifest_20260621.json`
- Current ready file: `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json`
- Latest QA verdict: `data/dso_research/ownership_manifest_QA_wave3_reqa5_20260621.json`
- Session handoffs:
  - `data/dso_research/RESEARCH_HOME/HANDOFF_GATE_OWNER_20260621.md`
  - `data/dso_research/RESEARCH_HOME/HANDOFF_QA_20260621.md`
  - `data/dso_research/RESEARCH_HOME/HANDOFF_MAIN_AO_20260621.md`
  - `data/dso_research/RESEARCH_HOME/HANDOFF_FLEET_B_20260621.md`

Latest verified counts:

- Ready: **310**
- Needs more evidence: **167**
- Conflicts: **74**
- Rejected: **7**
- Evidence gap backfill queue: **87**
- Core distinct locations: **558**
- Cross-bucket collisions: **0**

Ready tier mix:

- `dentist_multi`: 148
- `branded_dso`: 94
- `true_independent`: 30
- `stealth_dso`: 21
- `institutional`: 10
- `single_loc_group`: 7

Ready evidence-basis mix:

- `name_chain`: 165
- `web_verified`: 81
- `intel_dossier`: 25
- `locator`: 19
- `ein_cluster`: 10
- `structural`: 7
- `ao_cluster`: 3

Floor is still untouched:

- Current live floor after the 2026-06-19/20 audit: **268 / 4,801 = 5.58%** watched GP-location floor.
- Watched corporate NPIs: **1,152**.
- Older 5.43% / 261 / 1,119 figures in the F29 cheat-sheet are superseded by the CLAUDE.md banner. Do not treat them as current.
- DB reset invariant: `practice_locations.ownership_tier` non-null = 0, `practices.ownership_tier` non-null = 0.
- `RESEARCH_HOME/LEDGER.jsonl` remains header-only / 1 line.
- `RESEARCH_HOME/PROGRESS.json` remains 0/4439 reviewed, all tier tallies zero.

Validate-only has passed repeatedly:

```bash
python3 scrapers/consolidate_census.py \
  data/dso_research/_ready_to_validate_wave3_fixed_20260621.json \
  --session <validate-only-session-name> \
  --validate-only
```

Expected output: `Loaded 310 classification rows ... Validation OK ... no DB/ledger/progress writes.`

## How We Got Here

The project reset a prior candidate-quality wave because QA found overreach, duplicate-door tier contradictions, and weak AO-only rows. A strict manifest/gate process was rebuilt.

Major progression:

- Revised safe manifest: 65 ready.
- Backfill merge: 123 ready.
- Wave 2 merge: 210 ready.
- QA found 4 operating-status risk rows -> demoted to 206.
- Wave 3 merge: 315 ready.
- QA RE-QA #4 found three must-fix classes.
- Gate Owner fixed them.
- QA RE-QA #5 passed.
- Current fixed ready count: **310**.

RE-QA #4 fixes now resolved:

- **Fix A:** 4 operating-status subject-door risks demoted:
  - `f6c6290c16d20224`
  - `822d3012aedf32b9`
  - `77357c36224272c8`
  - `7d1d789828351ecf`
  - Each preserved with `preserved_ready_row`, `backfill_lane="operating_status_unverified"`.
- **Fix B:** `ao:SHAFI_REEM` explicitly adjudicated/released as `dentist_multi`.
  - `ba663f30996016ce`
  - `fc658bf62642d908`
  - `6da55130228a9c54`
  - Two rows corrected from `branded_dso` to `dentist_multi`.
  - Reason: DSO=STRUCTURE rule; no MSO/platform evidence; prior Shafi/Two Rivers release consistency. Not a `pe_backed=false` downgrade.
- **Fix C:** duplicate-door leak demoted:
  - `ff41419130267bd9`
  - Backfill lane: `duplicate_door_tier_conflict`
  - Same-door/twin issue with `f94fb29cc7d444cd`.
  - `duplicate_denominator_blocked.currently_in_candidate_set` updated.

No outstanding QA must-fix remains.

## Current Sessions

All four new Claude sessions are healthy and aligned.

Gate Owner:

- Read handoff.
- Confirms gate clear but frozen.
- Has an interactive choice prompt:
  1. Continue evidence work first
  2. Consolidate 310 now
  3. Hold/review more
- Recommended answer: **choose option 1**.

QA:

- Read handoff.
- Confirms RE-QA #5 pass.
- Offers independent re-verification / floor projection / future review.
- Should remain review-only unless assigned a specific QA task.

Main AO:

- Read handoff.
- Verified no AO jobs running.
- Confirmed current floor is 5.58%, not stale 5.43%.
- Holding. No reach=2 long-tail.

Fleet B:

- Read/verified handoff.
- Confirmed all queues and counts.
- Holding. Deterministic lanes exhausted.

## User's Current Strategic Preference

User is leaning toward **more data hunt before consolidation**, not immediate DB writes. The last recommendation given:

> Choose Gate Owner option 1: Continue evidence work first. Do not consolidate the 310 yet. Do not launch broad AO reach=2. Do a bounded Wave 4 Evidence Closure Sprint.

**Important live state:** the user has **not yet answered the Gate Owner's interactive choice prompt**. Gate Owner is waiting on:

1. Continue evidence work first
2. Consolidate 310 now
3. Hold/review more

The intended next answer is option **1**, with the bounded Wave 4 instructions below. A fresh Codex session should first help the user paste exact instructions into all four Claude sessions:

- Gate Owner: select/execute option 1 and hold consolidation frozen while coordinating Wave 4 intake.
- QA: define pre-QA criteria for Wave 4 before any new outputs are merged.
- Main AO: work only bounded conflict/network dossiers and AO-specific backfill; no broad reach=2.
- Fleet B: work Phase-C web verification on high-signal leads only; no deterministic re-mining.

If user asks what to tell Gate Owner, use:

```text
Choose option 1: Continue evidence work first.

Do not consolidate yet. Keep consolidation frozen. I want a bounded Wave 4 Evidence Closure Sprint, files-only/no DB writes, focused on:
1. resolving the 74 conflicts by network,
2. working the 87 formal backfill rows,
3. Phase-C web-verifying the strongest Fleet B leads, starting with hard-signal parent/affiliated/brand/EIN candidates, not the full 694 blindly.

No broad AO reach=2 long tail. No --allow-db-write.
```

## Recommended Next Hunt: Wave 4 Evidence Closure Sprint

This should be evidence-only, no DB writes, no consolidation, no broad new AO fan-out.

### Priority 1 - Resolve 74 Conflicts by Network

Conflict network counts:

- `1st Family Dental`: 23
- `Webster Dental`: 16
- `Brite Dental (Fadi Aqel)`: 12
- `Dental Town (Razzak)`: 9
- `Precision Dental Care`: 8
- Other/NO_GATE: 5
- `Webster Dental Care (contested)`: 1

Why this is highest leverage:

- Whole network decisions can move many rows at once.
- Existing conflict rows already have multiple signed-pass contradictions.
- Need documentary tie-breakers, especially MSO/management-company/platform evidence versus dentist-owned multi-location evidence.

Expected output from a conflict-resolution lane:

- One network dossier per conflict group.
- Recommended disposition per network:
  - `ready_to_validate` with tier and rationale,
  - `needs_more_evidence`,
  - or remain `conflict`.
- Documentary URLs and artifacts.
- Explicit DSO=STRUCTURE judgment.
- Stale/closed/specialist/duplicate notes.

### Priority 2 - Work 87 Formal Backfill Rows

Breakdown from current manifest:

- `AO_network`: 22
- `locator_exact`: 13
- `practice_intel`: 12
- `NO_LANE`/Wave-source mixed rows: 40

Tier hints:

- `dentist_multi`: 36
- `branded_dso`: 24
- `stealth_dso`: 7
- `institutional`: 6
- `undetermined`: 6
- `true_independent`: 5
- `single_loc_group`: 3

Priority inside backfill:

- branded/stealth DSO rows likely need locator/MSO/management-company proof.
- institutional rows likely need FQHC/hospital/university registry pages.
- AO rows need non-AO corroboration or should remain held.
- Operating-status and duplicate-door rows should not be promoted without active-door proof.

### Priority 3 - Phase-C Web-Verify the Strongest Fleet B Leads

Fleet B wave3 sidecar has:

- 720 total rows.
- 694 `needs_verification` leads preserved.
- Deterministic mining exhausted.

Do **not** work all 694 blindly. Start with hard-signal subset.

Strong local-cluster hard-signal subset found by local scan: about **158** leads with parent/affiliated/brand/EIN/dso_regional_review signals.

Candidate type distribution among those stronger leads includes:

- `brand_chain`: 85
- `parent_company_chain`: 16
- `affiliated_dso_chain`: 16
- `brand_chain + intel_keyword`: 5
- `brand_chain + phone_cluster`: 4
- `affiliated_dso_chain + ao_cluster`: 4
- `affiliated_dso_chain + dso_regional_review`: 4
- `ein_cluster`: 4
- plus smaller multi-signal groups.

Examples of high-scoring leads seen in scan:

- `fca68628fa6d431c` Chen Emily DDS, score 8, affiliated/brand/parent signals.
- `fd93e6934ac6c59c` PRO DENTAL IL - CHAD WISE PC, score 8.
- `c6078e6641ef7f48` CHICAGO DENTAL COSMETICS, score 7.
- `ae22984236e8c767` Kim Sara DMD, score 6.
- `336b69ba6a3ac455` YONG CHANG DDS PC, score 6.
- `23bc585758c9558a` Semenza, Angelo, score 6.

Phase-C output should be a validator-native evidence queue, not DB writes.

Required proof standard:

- At least one real documentary URL or durable DB artifact beyond weak signal.
- For DSO/PE:
  - public locator,
  - MSO/management-company page,
  - known DSO brand with exact address,
  - PE/parent transaction or platform evidence,
  - friendly-PC legal chain plus parent/platform corroboration.
- For dentist_multi:
  - same dentist/family/operator controls multiple locations,
  - no MSO/platform evidence,
  - active-door status checked.
- For true_independent:
  - earned, not fallback.
- Ambiguous rows stay `needs_verification` or `undetermined`.

## Suggested Multi-Session Assignment for Wave 4

Gate Owner:

- Remain intake/merge only.
- Do not run research.
- Ask it to produce a Wave 4 intake contract and wait for outputs, or just hold.

QA:

- Write pre-QA criteria for Wave 4 before work starts.
- Focus checks:
  - no AO-only,
  - no brand-substring-only,
  - closed/stale subject-door scan,
  - duplicate-denominator leak scan,
  - protected-network release audit,
  - DSO=STRUCTURE consistency,
  - sidecar preservation.

Main AO:

- Best used for conflict network dossiers and AO-specific backfill.
- Do not launch broad reach=2.
- Can work targeted conflict groups: 1st Family, Webster, Brite/Fadi Aqel, Dental Town/Razzak, Precision Dental.

Fleet B:

- Best used for Phase-C web verification of hard-signal Fleet B leads.
- Do not re-run deterministic lanes.
- Start with top 50-100 hard-signal leads, not all 694.

Codex coordinator:

- Inspect local files and updates.
- Catch inconsistencies.
- Give exact prompts.
- Do not take over DB-writing role unless explicitly asked.

## Prompt to Start Wave 4

If user asks for exact prompts, start with this Gate Owner instruction:

```text
Select option 1: Continue evidence work first.

Keep consolidation frozen. Do not run --allow-db-write.

I want a bounded Wave 4 Evidence Closure Sprint, files-only. Please coordinate intake only and do not mutate the DB. Target:
1. Resolve the 74 conflicts by network, especially 1st Family Dental, Webster Dental, Brite Dental/Fadi Aqel, Dental Town/Razzak, and Precision Dental Care.
2. Work the 87 formal backfill rows.
3. Phase-C web-verify the strongest Fleet B leads from the 694 sidecar pool, starting with hard-signal parent_company_chain / affiliated_dso_chain / brand_chain / EIN / dso_regional_review leads.

No broad AO reach=2 long tail.
No new consolidation.
No DB writes.
Preserve all sidecar/network intelligence.
Ask QA to define pre-QA criteria before outputs are merged.
```

Then give Main AO and Fleet B bounded assignments after Gate/QA acknowledge.

## Local Verification Commands for New Codex

Run these before making recommendations:

```bash
cd /Users/suleman/dental-pe-tracker

python3 scrapers/consolidate_census.py \
  data/dso_research/_ready_to_validate_wave3_fixed_20260621.json \
  --session codex_resume_healthcheck_20260621 \
  --validate-only

python3 - <<'PY'
import json, sqlite3, collections
base='data/dso_research'
ready=json.load(open(f'{base}/_ready_to_validate_wave3_fixed_20260621.json'))['classifications']
manifest=json.load(open(f'{base}/consolidation_candidate_manifest_20260621.json'))
print('ready rows', len(ready), 'distinct', len({r['location_id'] for r in ready}))
print('tier mix', dict(collections.Counter(r['assigned_tier'] for r in ready)))
print('counts', manifest['counts'])
conn=sqlite3.connect('data/dental_pe_tracker.db')
cur=conn.cursor()
for table in ['practice_locations','practices']:
    cur.execute(f"select count(*) from {table} where ownership_tier is not null")
    print(table, 'ownership_tier_nonnull', cur.fetchone()[0])
cur.execute("select sum(corporate_location_count), sum(total_gp_locations) from zip_scores")
corp, den = cur.fetchone()
print('floor', corp, den, round(corp/den*100,4))
cur.execute("""
select count(*)
from practices p join watched_zips w on p.zip=w.zip_code
where p.entity_classification in ('dso_regional','dso_national')
""")
print('watched corp NPIs', cur.fetchone()[0])
PY
```

Expected:

- 310 ready, 310 distinct.
- `ownership_tier_nonnull` 0/0.
- floor 268/4801 = 5.58%.
- watched corporate NPIs 1152.

## Tone / User Preference

User wants rigorous, high-productivity work, but not sloppy volume. They upgraded usage and want many agents doing useful work; however, they repeatedly emphasized QA first and no weak promotion. They are frustrated by small ready count, so remind them:

- 310 is ledger-grade, not total leads.
- There are large unresolved pools: 74 conflicts, 87 backfill, 694 Fleet B leads.
- The next sprint should convert existing evidence into ready rows rather than chasing weak new AO fan-out.

Keep answers direct, concrete, and action-oriented. Use exact file names, counts, IDs, and copy-paste prompts.
