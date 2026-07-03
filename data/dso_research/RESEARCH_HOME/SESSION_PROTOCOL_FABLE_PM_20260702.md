# SESSION PROTOCOL — Fable PM era (supersedes the Codex 4-session courier model)
**Effective:** 2026-07-02 · **Author:** Fable (PM). Any session (Fable or otherwise) resuming
census work reads THIS file first, then `PM_REVIEW_FABLE_20260702.md`, then acts. The repo is the
memory; chat summaries are secondary.

## Operating model
- **One PM session (Fable)** runs everything: investigation, QA, and in-session dispatch of
  Opus 4.8 / Sonnet 5 subagents for mechanical lanes. No human copy-paste relay. The PM reviews
  every agent deliverable before it counts.
- **Sessions are stateless workers.** All state lives in files + the DB. A session ending
  mid-sprint loses nothing if this protocol is followed: every deliverable is a file; every
  decision is written into a dated doc under RESEARCH_HOME.
- **Maximum work per session** (user directive 2026-07-02): no calendar staggering. Each session
  executes every unblocked task, gated only by dependencies, and ends with measurable progress
  recorded below.

## Canonical state (read in this order on resume)
1. `RESEARCH_HOME/SESSION_PROTOCOL_FABLE_PM_20260702.md` (this file — check "Session log")
2. `RESEARCH_HOME/PM_REVIEW_FABLE_20260702.md` (decision MODIFY, blockers, plan, standing rules)
3. `RESEARCH_HOME/PROGRESS.json` + `LEDGER.jsonl` (census tallies; frozen at 0 reviewed until the
   consolidation gate passes)
4. `RESEARCH_HOME/PROOF_ORM_SYNC_MIGRATION_20260702.md` (plumbing blockers B1/B2 cleared)
5. `RESEARCH_HOME/GP_SCOPE_POLICY_DRAFT_20260702.md` (awaiting user sign-off R1–R5)
6. Latest candidate/review artifacts in `data/dso_research/` dated ≥ 20260702

## Hard gates (unchanged unless the user lifts them in writing)
- **No `--allow-db-write` consolidation** until ALL of: hardened validator passes 0-error on the
  final candidate file; weak-row review applied; Fleet B 51-100 QA-accepted; proof package
  presented to user. SQLite first; Supabase sync only after SQLite verification.
- **No denominator mutations** (closures/duplicates/scope) except via evidence-file-documented
  cleanup scripts, reviewed by PM, with before/after counts and CI-guard rebase notes.
- **No entity_classification flips** from census work. Boston/MA parked. No Fleet B 101+ fan-out.
- Never print `.env` values. No git commit/push unless the user asks.

## Accounting (corrected 2026-07-02, coder-verified)
- Census-coverage candidates: **346 before Archer/holds** = 310 (ready file, needs URL repair)
  + 19 Wave-4 merge-eligible + 15 Lane-2 (1 corporate + 2 true-independent + 12
  corroborates-existing-corporate no-lift, all net-new location_ids) + 2 Fleet B T5 pending QA.
- DSO/PE **floor-lift** additions: ~5 pending Fleet B QA. Never conflate coverage with floor lift.
- Validator hardening proof: the 310 file now fails validate-only with 85 errors (71 bad
  evidence_urls entries — matches the coder's independent count).

## Session log (append one block per session)
### 2026-07-02 — Fable PM sprint 1
- B1 fixed: 6 census columns ORM-mapped on Practice + PracticeLocation; sync serializer proven to
  include them. B2 verified: Supabase has all 6 columns + indexes, ownership_tier notnull 0/0.
  Proof: `PROOF_ORM_SYNC_MIGRATION_20260702.md`.
- Validator hardened (`consolidate_census.py`): evidence_urls entries must be real http(s) URLs;
  dicts/prose/bare domains rejected; URL-based and DSO-tier checks now count only valid URLs;
  artifacts type-checked. Fail-closed proven against the 310 file.
- Lane-2 12 corroboration rows verified net-new → coverage accounting corrected to 346.
- Dispatched: closure-candidate agent (Opus), duplicate-candidate agent (Sonnet), frontend-honesty
  agent (Opus), Fleet B 51-100 Gate-normalization agent (Opus), weak-68 QA review (Fable fork).
  All file-only / no-DB-write lanes. PM review of each pending their return.
- Authored: GP-scope policy draft (R1–R5, awaiting user), this protocol.
- **PM review — closure candidates ACCEPTED with notes** (`closure_candidates_review_20260702.json`,
  542 rows: 61 mark_likely_closed / 93 verify_first / 388 keep_active listed-for-transparency).
  Spot-verified: all 542 location_ids exist; sampled strong-row quotes trace to real practice_intel
  text (quotes are near-verbatim COMPOSITES joined with "|" — adjudicators must open the linked
  intel row, not treat the quote as one verbatim string). Cross-check vs outside coder: their 123
  "stricter" candidates ≈ our strong+medium intel-signal set (boundary differences only).
  **Corrections attached:** (a) the agent's chat floor-impact projection mixed denominators (261 is
  the WATCHED corp count incl. MA; IL census universe is 4,439) — do NOT quote its 5.51% figure;
  the JSON `_meta` is clean. (b) 19 of 22 zero-contact rows carry DA_/DIR_ synthetic NPIs that
  survived the 2026-06-12 purge under solo_high_volume/solo_inactive — these are a SCOPE-CORRECTION
  queue item (da_unverified-style reclass, evidence-documented, user-gated), not closures. The
  census validator already refuses DA_ rows as final.
- **PM review — duplicate candidates ACCEPTED** (`duplicate_candidates_review_20260702.json`,
  221 combos = coder's count exactly: 128 likely_duplicate → 125 proposed excess rows / 86
  distinct_shared_phone / 7 needs_review). Spot-verified member addresses against DB (exact match),
  0 members already duplicate_location, house-number guard correctly rescued 21 combos (e.g., 141
  vs 111 W Jackson), 8 trunk-line phones documented (incl. the 10-practice answering-service line).
  Denominator ceiling if all confirmed: −125 rows; human adjudication required before ANY mutation.
- **PM review — frontend honesty fixes ACCEPTED** (13 files, +64/−20 in `dental-pe-nextjs/`,
  uncommitted). All 4 items applied: "Independent" → "Not Confirmed Corporate/Corp." with honest
  tooltips (Market Intel + Job Market); floor qualifiers on ALL per-ZIP surfaces (saturation, DSO
  penetration, ZIP score table, consolidation map, both warroom/launchpad ZIP dossiers); solo_inactive
  "Possibly inactive" badges (directory, launchpad track list, warroom target list); AI routes
  (ask/zip-mood) now frame corporate % as a confirmed floor. PM ran `npm run build` ✓ and F27
  vitest ✓ personally. React-element render follows the existing renderDataQualityStars precedent.
  The agent's census-display spec (section d) contains a stale prerequisite — it didn't know B2 is
  cleared and names a 4-column schema; the 6-column PROOF doc governs. `playwright/`+`tests/`
  untracked dirs are Apr-26 leftovers, NOT this agent's.
- **PM review — weak-68 DSO row review ACCEPTED** (`weak_dso_row_review_20260702.json`: 56 KEEP /
  1 KEEP_WITH_URL_FIX / 4 DOWNGRADE_TO_HOLD / 3 HOLD_PENDING_POLICY (Affordable, reinstateable on
  R1) / 4 DOWNGRADE_TO_T3). PM independently confirmed all four hard conflicts: Grand Dental +
  Elmhurst ARE on the May-30 independent_groups_DO_NOT_classify_corporate list; Grand Dental's own
  reasoning says dentist_owned_multi (tier was a coding error); North Ave reasoning says unresolved.
  Effective 310 impact: −7 rows leave the classified set (4 hold + 3 policy-hold), 4 retier T5→T3
  (stay as coverage), 1 URL repair. **R4 adjustment:** NITTINGER 11 KEEPs stay in the candidate file
  but are a NAMED R4 item (gate-owner self-release ≠ user sign-off; DOL EBSA MEWA evidence is strong
  — PM recommends ACCEPT T5, user decides). SHAFI's 18 rows in the 310 are T3 dentist_multi (Two
  Rivers Dental, dentist-owned) — also gate-owner self-released, also listed under R4.
- **PM review — Fleet B 51-100 gate normalization ACCEPTED WITH CORRECTIONS**
  (`_wave4_20260621/wave4_gate_normalized_lane3_51_100_20260702.json`, 50 rows balanced: 5 merge-
  eligible / 4 protected-hold / 3 scope-hold / 14 needs-more / 24 rejected). PM verified all 5
  merge-eligibles against DB (none already corporate; URLs valid; zero overlap with 310 + prior
  partitions). The QA verdict file was written by the SAME agent mislabeled as "Fable PM" —
  provenance corrected in-file; its substance was good and adversarial (caught rank-83 Archer
  ownership gap → held). **Accepted floor impact: +2 DSO/PE (Grove Dental→NADG/Abry+Jacobs;
  Advanced Family Dental→GLDP/Shore) and +2 T3-consolidated (United Dental Centers, Dental Group of
  Chicago); Archer rank-83 pending.** Fleet B ranks 51-100 are now Gate-normalized AND QA-reviewed.
- **#10 NORMALIZATION COMPLETE — validator passes 0 errors on the consolidated candidate file.**
  `_normalize_census_candidates_20260702.py` (deterministic, re-runnable) merged ready-310
  (URL hygiene repaired; weak-68 verdicts applied) + W4p1 19 + Lane-2 15 + Lane-3 3 into
  `_census_candidate_consolidated_20260702.json` (**340 rows, Validation OK**) +
  `_census_holds_20260702.json` (9 holds). Final arithmetic: 349 in → 340 candidates + 9 holds
  (supersedes 346/341/337 estimates). Tiers: T5 99 / T4 21 / T3 171 / T2 7 / T1 32 / T6 10;
  pe_backed 75. Coverage-vs-floor split: 42 net-new T4/T5 (8 of them R4-flagged) / 78
  corroborations / 171 T3.
- **PM catch via fail-closed validator:** Lane-3 rank-100 Advanced Family Dental (Shorewood)
  `6c31d482e9a63431` is a DA_ synthetic remnant (DA_c396391041ac); the real practice
  `0d376204167d44a6` (NPI 1932386810) is ALREADY dso_regional. Both the gate agent AND its QA
  missed it. **Lane-3 accepted floor impact corrected +2 T5 → +1 T5 (Grove Dental only).** Row
  routed to scope-correction queue via holds file.
- **Analyst review adopted (relayed by user):** (1) writer now mirrors tiers to the FULL NPI set —
  primary+org+provider_npis roster, DA_ skipped (+693 NPIs across 225 multi-provider locations on
  the 340; was primary/org only); (2) `REVIEWED_AT` de-hardcoded to the actual run date;
  (3) final arithmetic published (§2 of proof package); (4) closure queue confirmed review-only —
  Metropolitan Dental Care false-positive risk + primary-NPI-only coverage gap (2,069 vs 2,330)
  recorded; (5) duplicate mutations = ONLY explicit mark_duplicate_location row actions (125);
  (6) repo-hygiene recommendation (root + nested dental-pe-nextjs commits) put to user — no
  commits without user's word.
- **#9 PROOF PACKAGE SHIPPED:** `RESEARCH_HOME/PROOF_PACKAGE_CONSOLIDATION_GATE_20260702.md` —
  awaiting user: R1–R5, R4 named networks (NITTINGER/LABINOV/SHAFI with PM recommendations),
  consolidation authorization, repo-hygiene authorization. DB still frozen: ownership_tier 0/0,
  LEDGER 1 line, PROGRESS 0/4,439.
- **USER DELEGATION RECEIVED:** "make the best answers to the decisions. you have answering
  abilities. then proceed." All gate decisions made by PM under delegation and recorded in
  `RESEARCH_HOME/DECISIONS_PM_20260702.md` (R1 YES / R2 YES / R3 YES / R4 YES + NITTINGER T5,
  LABINOV T5, SHAFI T3 / R5 YES + Geneva & MetroSmiles adjudicated ACTIVE / consolidation YES /
  repo hygiene YES). Normalizer updated (R1 reinstatement, ENFORCED R5 closure cross-check —
  found the 2 adjudicated hits, decisions in `_meta`); regenerated file: **343 classified + 6
  holds**, validate-only 0 errors.
- **🔓 CONSOLIDATION EXECUTED — THE FREEZE IS RELEASED.** Pre-write backup
  `data/backups/dental_pe_tracker_pre_census_write_20260702.db` (pre-write md5
  `e2a89a02900d0366fad6d9ee06d23422` matched baseline). Ran `consolidate_census.py
  _census_candidate_consolidated_20260702.json --session fable_pm_consolidation_20260702
  --allow-db-write`: **343 locations + 1,037 mirrored NPIs written; skipped_bad=0; LEDGER now
  344 lines; PROGRESS 343 reviewed / 4,096 remaining = 7.73% coverage.** Post-write verification:
  detector floor UNTOUCHED (corp locations 268, corp NPIs 1,152, GP denominator 4,801), holds
  still NULL, 0 DA_ leaks, ADI/Geneva/MetroSmiles spot checks pass. Tier tally (locations):
  T5 102 / T4 21 / T3 171 / T2 7 / T1 32 / T6 10; pe_backed 78. Floor-lift split: 42 net-new
  T4/T5, 81 corroborations, 171 T3-coverage.
- **SUPABASE SYNC COMPLETE + READ-BACK VERIFIED (both legs).** Leg 1
  `python3 -m scrapers._sync_floor_tables_only` (full_replace; ORM-serialized so census columns
  ride along): dso_locations 633 / zip_scores 290 / practice_locations 5,657, live floor
  268/4,801 = 5.58%. Leg 2 NEW `scrapers/_sync_census_columns_practices.py` (surgical per-row
  UPDATE of ONLY the 6 census columns, BATCH=200, pre-flight information_schema check, pe_backed
  int→bool cast for Postgres boolean): 1,037/1,037 updated, 0 missing. Live verification:
  practice_locations ownership_tier notnull **343 = SQLite (exact tier-tally match)**, practices
  **1,037 = SQLite (exact tally: branded_dso 427 / dentist_multi 476 / stealth_dso 62 /
  single_loc_group 16 / true_independent 43 / institutional 13)**, pe_backed locations 78,
  floor invariants live 268/1,152/179 da_unverified/5,657 total, DA_ leak 0. NOTE:
  `_sync_practices_changed_rows.py` does NOT carry census columns — after any future
  consolidation, run `_sync_census_columns_practices` for the practices leg.
- **Hard-gate status change:** the "No --allow-db-write" gate is SATISFIED AND CONSUMED for this
  run (all four conditions met; user delegated the final authorization). Future consolidations
  re-arm the same gate. The "no git commit/push unless the user asks" line is superseded for
  THIS session's two authorized commits (root census infra/evidence/docs + nested
  dental-pe-nextjs honesty fixes) per DECISIONS_PM_20260702.md §Repo hygiene.
- Still open (user-gated, review-only): scope-correction queue (19 DA_/DIR_ + Shorewood),
  duplicate adjudication (125 explicit row actions), closure-queue NPI-bridging improvement,
  Archer rank-83 resolution (research in flight → folds via `--allow-rereview`).

### 2026-07-02 (later) — Fable PM sprint 2: Lane A waves + intel capture
- **Lane A wave fleet running** (post-consolidation, next ~3,488 practices in 218 unit files at
  `_lane_a_20260702/unit_*.json`): Wave 1 = units 001–064 (run `wf_429ac485-f85`), Wave 2 =
  units 065–128 (run `wf_9245198a-80a`), both on the v1 census-only script; Sonnet 5 research
  agents + Opus 4.8 adversarial verify on every T4/T5 claim (models transcript-verified after
  the `~/.claude/settings.json` subagent-pin fix + restart). Results land as
  `result_unit_*.json`; merge gate = `_merge_lane_a_results_20260702.py` (fail-closed; NOTE
  `WAVE="wave1"` hardcode — combine ALL waves' verdicts into `_verdicts_wave1.json` or
  parameterize before merging multi-wave).
- **Intel capture worked in (user directive)**: waves 3+4 (units 129–173 / 174–218, launch as
  waves 1/2 complete) use the v2 script `_wf_lane_a_census_v2_intel_20260702.js` — census
  contract unchanged + optional per-practice `intel` object (opportunistic, no extra searches,
  per-field source URLs). Converter `_merge_lane_a_intel_20260702.py` lands validated blocks in
  `practice_intel` (primary_npi key, verification_quality=partial,
  research_method=lane_a_census_opportunistic, never clobbers existing rows; Supabase leg =
  `dossier_batch/upsert_practice_intel.py`). Committed `a95656f`. Unlocks Launchpad
  SIGNALS_REQUIRING_INTEL coverage.
- **🛟 DISASTER-RECOVERY RUNBOOK SHIPPED (user-directed full backup under rate-limit pressure):**
  `RESEARCH_HOME/MASTER_RESUME_LANE_A_FLEET_20260702.md` — fleet map + run IDs, journal paths for
  verdict recovery, relaunch-missing-units procedure (v2 script for all relaunches), normal
  merge→consolidate→sync chain, rate-limit protocol, model-unclamp check, reference index. v1
  script archived into repo as `_wf_lane_a_census_v1_20260702.js`. Fleet at authoring: 37/128
  result files (wave 1: 001–023; wave 2: 065–078).
- **PLANNED (user-approved, deferred): intel backfill for waves 1+2 (~2,048 practices) on an
  upgraded dedicated search** → full plan in
  `RESEARCH_HOME/PLAN_INTEL_BACKFILL_WAVES_1_2_20260702.md` (Option A: v3 intel-only workflow
  wave reusing the v2 intel contract + existing converter, no API credits; Option B:
  dossier-batch pipeline ~$16 for dossier-grade rows; decide using waves 3+4 `n_intel` yield).
  Do NOT re-run census research on units 001–128 for this.
