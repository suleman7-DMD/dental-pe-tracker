# P1′ — Census Continuation Campaign (authored 2026-07-04)

**Goal:** move IL census coverage from 3,180/4,439 (71.64%) toward 100% by resolving the
**1,259 remaining merge-eligible untiered IL GP locations**, reusing the proven Lane A
machinery end-to-end (research → merge gates → audit → consolidate → sync → read-back).

**Prerequisite reading:** `dental-pe-census-operating-protocol` skill (all sections),
`RESEARCH_HOME/MASTER_RESUME_LANE_A_FLEET_20260702.md` §6 (esp. §6m — the proven wave-1 chain
whose outputs calibrate every expectation below).

**Write-set:** new dated files under `data/dso_research/` (result units, merged candidates,
triage files, dated script copies), plus the DB/Supabase writes that pass their human gates.
Nothing else.

---

## The queue (verified against live DB + triage file, 2026-07-04)

1,259 = **649 triage rows** (`data/dso_research/_lane_a_triage_wave1_20260702.json`) + **610
never-researched** untiered IL GP locations. The 477 "undetermined" are INSIDE the 649 — do
not double-count them (older docs' "649 + 477 + ~950" accounting is loose; this decomposition
is the verified one).

| Track | Rows | `_triage_reason` / segment | Disposition |
|---|---:|---|---|
| A | 477 | `undetermined_by_agent` | Re-research (fresh evidence hunt, stricter acceptance) |
| B | 91 | `adjudication_hold_dso_verify` 52 + `adjudication_hold_unresolved` 30 + `adjudication_duplicate_suspect` 9 | Holds protocol: targeted verification per hold reason; dup-suspects need address-level proof |
| C | 52 | `t1_t2_positive_proof_audit_hold` | Need positive proof (named dentist owns AND operates) or downgrade T1→T2/T3 |
| D | 16 | `r4_network_ge10_brand:aspen_dental` | R4 one-network-one-decision — a USER ruling tiers all 16 at once; never per-row research |
| E | 8 | `closure_suspect` | R5 closure adjudication (active/closed), user confirms |
| F | 5 | `dso_claim_refute` 2, `dso_claim_insufficient` 1, `r4_flag_in_reasoning` 1, `pm_hold_active` 1 | Case-by-case with the user; pm_hold stays held until the user releases it |
| G | 368 | never-researched, real NPIs | Wave-5 research (same as Track A machinery) |
| H | 242 | never-researched, synthetic `DA_`/`DIR_` NPIs | Merge gates REJECT synthetic NPIs by design. Options for the user: resolve to real NPIs where possible, else these stay permanently "unresolved" in the coverage denominator. Do NOT research them as-is; do NOT delete them |

Recheck the totals before starting (Phase 0) — if they moved, someone worked the queue since
2026-07-04 and this table is stale.

---

## Phase 0 — Preflight (no writes)

```bash
cd /Users/suleman/dental-pe-tracker && git status --short   # expect clean or explained
sqlite3 data/dental_pe_tracker.db "
SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL;   -- expect 3180
SELECT COUNT(*) FROM practice_locations
  WHERE entity_classification IN ('dso_regional','dso_national');           -- expect 268
"
python3 -c "import json; d=json.load(open('data/dso_research/_lane_a_triage_wave1_20260702.json')); print(len(d))"   # expect 649
ls data/dso_research/_lane_a_20260702/result_unit_*.json | wc -l   # expect 218 (result files = ground truth)
env | grep -c CLAUDE_CODE_SUBAGENT_MODEL                     # expect 0 (model-clamp check)
```

**Trap:** starting research with a pinned subagent model, or on a DB where a consolidation
already landed. Any mismatch → STOP, report.

## Phase 1 — Research waves (files-only; Tracks A, B, C, G)

- Reuse the proven workflow scripts as TEMPLATES: `_wf_lane_a_census_v2_intel_20260702.js`
  (research+intel) and `_wf_lane_a_verdict_recovery_20260702.js` (crash recovery). Make new
  dated copies (e.g. `_wf_lane_a_census_v3_wave5_<date>.js`) — never edit the originals.
- Unit numbering: continue AFTER the existing units (check
  `ls data/dso_research/_lane_a_20260702/result_unit_*.json | sort | tail`) so new result
  files never collide with the 218 ground-truth files.
- Skip list = every location_id already in a result file OR already tiered.
- Track C units must be prompted for POSITIVE PROOF (owner named + operates on-site), not
  re-classification from vibes.
- **Verification per batch:** each unit writes `result_unit_NNN.json`; spot-read 2–3 per wave
  for schema + real URLs. Crash mid-wave → verdict-recovery script, per runbook §6d.
- **Trap:** re-researching completed units (they have result files); letting agents write
  anything outside `data/dso_research/`.

## Phase 2 — Merge through the gates

Make a dated copy of `_merge_lane_a_results_20260702.py` (e.g. `_merge_lane_a_results_wave5_<date>.py`)
pointing at the new result glob, new verdict files, and the new adjudication rollup. **Keep
every gate intact** (target eligibility, synthetic-NPI reject, PM holds, confidence,
URL/artifact evidence bases, T4/T5 adversarial CONFIRM, R4 sweep, rollup total assertion).
The 2026-07-02 wave-1 calibration: 3,486 rows in → 2,889 kept + 597 triage.

**Verification:** merge prints kept/triage counts and writes `_census_candidate_*.json` +
`_lane_a_triage_*.json`; sum must equal rows-in. **Trap:** weakening a gate to raise the kept
count; editing the original dated merge script.

## Phase 3 — T1/T2 positive-proof audit

```bash
python3 scrapers/screen_true_independent_hardening.py        # read-only screen
python3 scrapers/audit_lane_a_t1_t2.py                       # deterministic seed; wave-1 calibration: 52 held / 483 downgraded
```

**Trap:** skipping the audit because "the researchers already checked" — the Aspen-as-T1
reverse rows were caught only here.

## Phase 4 — Validate-only (still no DB writes)

```bash
python3 scrapers/consolidate_census.py data/dso_research/<candidate>.json \
  --session <name> --validate-only          # expect "Validation OK", 0 errors
```

Rows already carrying a tier from wave 1 require `--allow-rereview` INTENT — flag to the user;
that second gate exists to stop silent overwrites.

## Phase 5 — HUMAN GATE → write

Present to the user: candidate count, tier breakdown, triage delta, validate-only output.
Only on explicit approval:

```bash
cp data/dental_pe_tracker.db data/backups/dental_pe_tracker_pre_census_write_<date>.db
md5 data/backups/dental_pe_tracker_pre_census_write_<date>.db    # record it
python3 scrapers/consolidate_census.py <candidate>.json --session <name> --allow-db-write
# wave-1 calibration: "2,837 locations updated, skipped_bad=0" + LEDGER +2,837
```

**Verification:** re-run the Phase 0 SQL — tiered count = old + kept; floor still ≥268
untouched. **Trap:** running `--allow-db-write` because validate-only passed (approval is per
run, it re-arms every time).

## Phase 6 — HUMAN GATE → Supabase sync + read-back

Exactly per the `dental-pe-supabase-sync-and-orm` skill: leg 1 `_sync_floor_tables_only`,
leg 2 `_sync_census_columns_practices`, then independent Postgres read-back (counts + tier
tallies + floor) matching SQLite exactly. **Trap:** `_sync_practices_changed_rows.py` (doesn't
carry census cols) or any full sync mid-chain.

## Phase 7 — Bank the milestone

Update `RESEARCH_HOME/PROGRESS.json` accounting via the consolidate tooling's own outputs
(never hand-edit LEDGER), write a dated session note with all verified counts/md5s, and list
any CLAUDE.md numbers now stale for the PM to apply.

---

## Stop conditions (beyond the standing skill list)

- Phase 0 mismatch of any count.
- Merge kept/triage sum ≠ rows-in, or adjudication rollup assertion fires.
- validate-only errors, or `--allow-rereview` would be needed unexpectedly.
- Any Track D/E/F/H decision — those are the user's, not yours.
