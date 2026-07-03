# MASTER RESUME — Lane A census fleet + intel system (2026-07-02)

**Purpose: complete disaster-recovery instructions.** If the computer crashes, the session dies,
or the user hits a usage rate-limit and everything halts, a FRESH session must be able to resume
every running operation from THIS FILE alone (plus the repo). Written by Fable (lead PM) while
waves 1+2 were in flight. Read `SESSION_PROTOCOL_FABLE_PM_20260702.md` first for the operating
model and hard gates; this file is the fleet-specific runbook.

---

## 0. Mission and command structure (the full vision)

- **End state:** every one of the ~4,096 remaining IL-watched GP locations carries an
  evidence-backed `ownership_tier` (census axis), AND the app has a rich per-practice intel
  directory (`practice_intel`) powering Launchpad/Warroom/Job-Market job-hunt features.
  343 locations already tiered + consolidated + synced (see SESSION_PROTOCOL).
- **Command structure:** Fable session = lead project manager, project vision architect, QA,
  and master agent deployer. **Sonnet 5** (`claude-sonnet-5`) agents do per-unit web research;
  **Opus 4.8** (`claude-opus-4-8`) agents adversarially verify every stealth/branded DSO claim.
  Fable personally PM-reviews all T4/T5 rows + network claims + a T1 sample before any DB write.
  All DB writes go through the fail-closed merge gate + `consolidate_census.py`.
- **Two-axis rule (NEVER violate):** the census (`ownership_tier`) NEVER mutates the detector
  floor (`entity_classification`; floor invariants 268 corp locations / 1,152 corp NPIs /
  4,801 GP). Boston/MA is parked; IL only.
- **Agent prompt contracts (canonical, verbatim in repo):**
  - v1 census-only: `data/dso_research/_wf_lane_a_census_v1_20260702.js`
  - v2 census + opportunistic intel: `data/dso_research/_wf_lane_a_census_v2_intel_20260702.js`
  Both scripts contain the exact researcher + verifier prompts, JSON schemas, tier definitions,
  hard rules (no fabrication, R4 ≥10-location networks → undetermined, closure_suspect →
  undetermined, T4/T5 need documentary URLs, AO/EIN reach never enough for T4/T5).

## 1. Fleet state at authoring (2026-07-02 ~21:45)

| Wave | Units | Script | Workflow run | Task | Status at authoring |
|------|-------|--------|--------------|------|---------------------|
| 1 | 001–064 | v1 (census only) | `wf_429ac485-f85` | wx7o6w9ks | in flight; results 001–023 on disk |
| 2 | 065–128 | v1 (census only) | `wf_9245198a-80a` | wend8mdzb | in flight; results 065–078 on disk |
| 3 | 129–173 | v2 (census+intel) | not launched | — | launch when wave 1 completes |
| 4 | 174–218 | v2 (census+intel) | not launched | — | launch when wave 2 completes |
| backfill | 001–128 intel-only | v3 (to author) | later session | — | `PLAN_INTEL_BACKFILL_WAVES_1_2_20260702.md` |

- Unit files (input, 218 total ≈ 3,488 practices): `data/dso_research/_lane_a_20260702/unit_NNN.json`
- Result files (output, ground truth of completed work):
  `data/dso_research/_lane_a_20260702/result_unit_NNN.json`
- ~6 concurrent agents per workflow (per-workflow cap = min(16, cores−2) on this machine).
- Session task list (does NOT survive restarts — mirrored here): #1 monitor waves 1+2;
  #3 merge→consolidate→sync→commit chain; #4 launch waves 3+4 on v2; #5 intel backfill later.
- A background watcher pings at 40 result files for mid-flight QA (single-shot, session-local).

## 2. Volatile session assets a fresh session must know about

These live OUTSIDE the repo under the session directory
`/Users/suleman/.claude/projects/-Users-suleman-dental-pe-tracker/4d259360-781e-4eee-9774-4f0a41d11ff2/`:

- **Agent journals (verdict recovery):**
  `subagents/workflows/wf_429ac485-f85/journal.jsonl` (wave 1) and
  `subagents/workflows/wf_9245198a-80a/journal.jsonl` (wave 2). Every agent's return value is
  recorded there — including each Opus verifier's `{unit_id, verdicts:[{location_id, verdict,
  notes}]}`. If the session dies before the workflow returns, verdicts are recovered from these
  files (procedure §4B). Per-agent transcripts (`agent-*.jsonl`) in the same dirs prove models:
  `grep -c '"model":"claude-sonnet-5"' agent-*.jsonl`.
- **Original v1 script:** `workflows/scripts/lane-a-census-wave1-wf_b4f93973-e64.js` — now also
  copied into the repo as `data/dso_research/_wf_lane_a_census_v1_20260702.js`.
- `Workflow` resume (`resumeFromRunId`) is SAME-SESSION ONLY. A fresh session cannot resume a
  dead run — it relaunches MISSING units only (procedure §4B). Result files on disk are never
  lost; completed work is never redone.

## 3. Normal path (session alive, waves complete)

1. **Dump verdicts.** Each workflow's return has `perUnit[].verdicts`. Combine verdicts from
   ALL completed waves into ONE flat list at
   `data/dso_research/_lane_a_20260702/_verdicts_wave1.json`:
   `[{"location_id": "...", "verdict": "CONFIRM|REFUTE|DOWNGRADE_T3|INSUFFICIENT", "notes": "..."}, ...]`
   (The merge gate `_merge_lane_a_results_20260702.py` has `WAVE="wave1"` hardcoded and reads
   ALL result_unit_*.json — one combined verdict file is the intended path; a DSO row without a
   verdict fail-closes to triage, so missing verdicts are safe but wasteful.)
2. **Merge gate:** `python3 data/dso_research/_merge_lane_a_results_20260702.py`
   → `_census_candidate_lane_a_wave1_20260702.json` + `_lane_a_triage_wave1_20260702.json`.
3. **PM review (Fable personally):** every T4/T5 row (evidence URLs + verifier notes), every
   network_id claim, a ≥10-row T1/T2 sample, and the triage reasons histogram.
4. **Backup then consolidate:**
   `cp data/dental_pe_tracker.db data/backups/dental_pe_tracker_pre_census_write_<date>.db`
   (record md5), then
   `python3 scrapers/consolidate_census.py data/dso_research/_census_candidate_lane_a_wave1_20260702.json --session fable_pm_lane_a_20260702 --validate-only`
   → fix any errors → rerun with `--allow-db-write` (gate re-arms per SESSION_PROTOCOL).
5. **Sync BOTH legs (order matters, and leg 2 is census-specific):**
   `python3 -m scrapers._sync_floor_tables_only` AND
   `python3 -m scrapers._sync_census_columns_practices`
   (`_sync_practices_changed_rows.py` does NOT carry census columns.) Read back live counts.
6. **Intel harvest (only meaningful once v2 waves have run):**
   `python3 data/dso_research/_merge_lane_a_intel_20260702.py --dry-run` → spot-QA 2–3 intel
   blocks against their source URLs → run live → Supabase leg
   `python3 scrapers/dossier_batch/upsert_practice_intel.py` (surgical UPSERT; never
   full_replace for this).
7. **Docs + commit:** update SESSION_PROTOCOL session log, PROGRESS.json/LEDGER are written by
   consolidate_census itself; verify detector floor unchanged (268/1,152/4,801); commit with
   trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Never commit `.env` or DB
   backups.

## 4. Disaster recovery (crash / rate-limit / dead session)

### A. Assess what completed (always step 1)

```bash
ls data/dso_research/_lane_a_20260702/result_unit_*.json | wc -l
python3 - <<'EOF'
import glob, os
have = {os.path.basename(p)[12:15] for p in glob.glob('data/dso_research/_lane_a_20260702/result_unit_*.json')}
missing = [i for i in range(1, 219) if f'{i:03d}' not in have]
print(f"{len(have)} done; missing units:", missing)
EOF
```
Result files are ground truth. A unit with a result file is DONE (never re-research it).

### B. Recover Opus verdicts for completed units (if the workflow died before returning)

```bash
python3 - <<'EOF'
import json, glob
out = []
for jf in glob.glob('/Users/suleman/.claude/projects/-Users-suleman-dental-pe-tracker/'
                    '4d259360-781e-4eee-9774-4f0a41d11ff2/subagents/workflows/wf_*/journal.jsonl'):
    for line in open(jf):
        if '"verdicts"' not in line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        def walk(o):
            if isinstance(o, dict):
                if 'verdicts' in o and isinstance(o['verdicts'], list):
                    out.extend(v for v in o['verdicts'] if isinstance(v, dict) and 'location_id' in v)
                for v in o.values(): walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
            elif isinstance(o, str) and '"verdicts"' in o:
                try: walk(json.loads(o))
                except Exception: pass
        walk(rec)
dedup = {v['location_id']: v for v in out}
json.dump(list(dedup.values()),
          open('data/dso_research/_lane_a_20260702/_verdicts_wave1.json', 'w'), indent=1)
print('recovered verdicts:', len(dedup))
EOF
```
**Fallback if journals are gone:** rebuild claims from result files (rows with
`assigned_tier` in stealth_dso/branded_dso and status classified) and launch fresh Opus 4.8
verify agents using the `verifyPrompt` contract from the v1/v2 script verbatim. Worst case: run
the merge gate with NO verdicts — every DSO claim fail-closes to triage (safe, nothing wrong is
written), then re-verify triage later.

### C. Relaunch missing units (fresh session)

Use the **v2 script for ALL relaunches** (superset of v1 — captures intel too):

```
Workflow({
  scriptPath: "/Users/suleman/dental-pe-tracker/data/dso_research/_wf_lane_a_census_v2_intel_20260702.js",
  args: { units: [<absolute paths of data/dso_research/_lane_a_20260702/unit_NNN.json for each MISSING unit>] }
})
```
Generate the list from §4A's `missing`. Batch ~45–64 units per workflow; run two workflows in
parallel for ~12 concurrent agents. Waves 3/4 = units 129–173 / 174–218 if not yet launched.
Result files land incrementally, so a second crash still loses nothing.

**Before relaunching, verify subagent models are unclamped:** `~/.claude/settings.json` env must
have `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-8`, `ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5`,
`CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP=1`, and NO `CLAUDE_CODE_SUBAGENT_MODEL` pin (that pin
caused the 2026-07-02 sonnet-4-6 clamp incident; env snapshots at CLI startup — a settings change
requires a session restart). Prove it live by grepping the new run's `agent-*.jsonl` for
`"model":"claude-sonnet-5"`.

### D. Rate-limit protocol (the scenario prompting this file)

- When the user warns usage is low: **do NOT launch new waves.** Let running agents finish
  naturally (each finished unit persists its result file). Spend remaining budget on
  documentation/commits (cheap), not research.
- If the limit hits mid-flight: agents die; on usage reset (1–2h), run §4A→C in the SAME session
  if it survived (relaunch missing units; `resumeFromRunId` also works same-session), or a fresh
  session per §4A→C.
- After ANY halt, before merging: re-check result-file count vs verdict coverage; the merge gate
  fail-closes gaps.

## 5. Reference index (everything a fresh session needs)

| Asset | Path |
|-------|------|
| Operating model, hard gates, session log | `RESEARCH_HOME/SESSION_PROTOCOL_FABLE_PM_20260702.md` |
| Gate rulings (R1–R6, delegation) | `RESEARCH_HOME/DECISIONS_PM_20260702.md` |
| v1 census script (waves 1–2, archived copy) | `data/dso_research/_wf_lane_a_census_v1_20260702.js` |
| v2 census+intel script (waves 3+) | `data/dso_research/_wf_lane_a_census_v2_intel_20260702.js` |
| Unit queue builder (made the 218 units) | `data/dso_research/_build_lane_a_queue_20260702.py` |
| Unit + result files | `data/dso_research/_lane_a_20260702/` |
| Fail-closed merge gate | `data/dso_research/_merge_lane_a_results_20260702.py` |
| Intel converter → practice_intel | `data/dso_research/_merge_lane_a_intel_20260702.py` |
| Intel backfill plan (waves 1+2, later) | `RESEARCH_HOME/PLAN_INTEL_BACKFILL_WAVES_1_2_20260702.md` |
| Census writer/validator | `scrapers/consolidate_census.py` (`--validate-only` first, always) |
| Sync leg 1 / leg 2 | `scrapers/_sync_floor_tables_only.py` / `scrapers/_sync_census_columns_practices.py` |
| Intel Supabase leg | `scrapers/dossier_batch/upsert_practice_intel.py` |
| Holds (6 active) | `data/dso_research/_census_holds_20260702.json` |
| Progress/ledger | `RESEARCH_HOME/PROGRESS.json`, `RESEARCH_HOME/LEDGER.jsonl` |
| Pre-consolidation DB backup + md5 | `data/backups/dental_pe_tracker_pre_census_write_20260702.db` (`e2a8...422`) |

**Standing user directives:** maximum work per session; Fable = PM/architect/QA/agent deployer
with delegated gate authority ("make the best answers... then proceed"); Sonnet 5 research /
Opus 4.8 verify; PM personally reviews all agent work; honest undetermined > guessed tier;
detector floor untouched; MA parked; never commit .env or DB backups; commits end with
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
