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

---

## §6 SECOND FLIGHT (2026-07-02 late, post-rate-limit reset) — CURRENT FLEET STATE

Waves 1+2 (first flight) terminated on the user's session rate limit at ~85/128 units.
**Final first-flight state: 85 result files on disk (ground truth). ALL first-flight Opus verify
agents were rate-limit-killed → ZERO verdicts exist from the first flight.** The 25 result files
carrying 35 unverified T4/T5 claims are being re-verified by the recovery workflow below.

After the reset the PM relaunched everything in one shot (all four run concurrently):

| What | Units / input | Run ID | Task ID | Script |
|---|---|---|---|---|
| Relaunch missing w1+w2 units | 46–64, 104, 106–128 (43 units) | `wf_a79097d5-2c2` | wfvl0wyni | v2 intel script (repo) |
| Wave 3 | 129–173 (45 units) | `wf_facf67a9-304` | wji2buo1f | v2 intel script (repo) |
| Wave 4 | 174–218 (45 units) | `wf_a8ac7ebd-e28` | wy93djy68 | v2 intel script (repo) |
| Verdict recovery (Opus 4.8) | 25 result files w/ 35 T4/T5 claims | `wf_edc106cc-7cf` | w7zwnx52v | `data/dso_research/_wf_lane_a_verdict_recovery_20260702.js` (archived copy) |

- Verdict-recovery agents READ each result file themselves and adversarially verify its
  stealth_dso/branded_dso rows (CONFIRM/REFUTE/DOWNGRADE_T3/INSUFFICIENT). The workflow RETURNS
  the verdicts (writes no files) — on completion the PM writes them into the flat combined
  verdicts file (`_lane_a_20260702/_verdicts_wave1.json`) for the merge gate. If THIS session
  dies after recovery completes, verdicts are in the run journal:
  `~/.claude/projects/-Users-suleman-dental-pe-tracker/4d259360-781e-4eee-9774-4f0a41d11ff2/subagents/workflows/wf_edc106cc-7cf/journal.jsonl`.
- The 25 files needing verdicts: units 003 004 006 012 015 018 022 023 024 025 026 029 032 033
  035 036 039 073 080 081 085 090 096 097 102 — PLUS any T4/T5 rows in second-flight units,
  which the v2 script verifies inline (each second-flight unit returns its own verdicts).
- Recovery-of-the-recovery: if any of these four runs dies, the §4 procedures apply unchanged
  (result files on disk = ground truth; relaunch only missing units with the v2 script; recover
  verdicts from journals; fresh verify agents for any unit with T4/T5 rows and no verdict).

### §6a Session-restart resume (2026-07-02, later the same night) — PROVEN RECOVERY

The PM session restarted (context compaction → background continuation). The three RESEARCH
workflows were checkpointed but failed auto-adoption ("adopt scriptPath rejected") — the
**verdict-recovery workflow survived the restart and kept running** (task w7zwnx52v, unchanged).
Disk still read 85 result files (no second-flight research had landed yet), so nothing was lost.

Recovery that WORKED (use this exact pattern for any future session restart):
`Workflow({scriptPath: <repo v2 script>, resumeFromRunId: "<run id>", args: <same units>})` —
cross-session resume on the SAME run IDs succeeded; cached agent() calls (incl. ~10 banked Opus
verdicts in the recovery journal) replay instantly. New task IDs after resume:

| What | Run ID (unchanged) | New Task ID |
|---|---|---|
| Relaunch missing w1+w2 units (43) | `wf_a79097d5-2c2` | wmi4a38vs |
| Wave 3 (45) | `wf_facf67a9-304` | wrk5dujmd |
| Wave 4 (45) | `wf_a8ac7ebd-e28` | w87b116uy |
| Verdict recovery | `wf_edc106cc-7cf` | w7zwnx52v (never died) |

Journals now live under BOTH session dirs — the resumed runs write to
`~/.claude/projects/-Users-suleman-dental-pe-tracker/a281c7b1-8c8d-4811-9e1c-efed0be4e197/subagents/workflows/<runId>/journal.jsonl`
(the old 4d259360… paths hold the pre-restart entries, incl. the first ~11 recovery verdicts for
units 003 004 006 012 015 018 022 024 025). Check BOTH when recovering verdicts.

### §6b Verdict recovery COMPLETE (2026-07-02 ~22:15) — verdicts file WRITTEN + PM-reviewed

`wf_edc106cc-7cf` finished 25/25 agents, 0 errors: **35/35 first-flight DSO claims adjudicated —
CONFIRM 27 / DOWNGRADE_T3 7 / REFUTE 1 / INSUFFICIENT 0.** Flat merge-gate file WRITTEN:
`_lane_a_20260702/_verdicts_wave1.json` (35 entries keyed by location_id, with notes +
urls_checked + unit_id + verifier tag). PM reviewed all 8 non-CONFIRMs — ACCEPTED:
- REFUTE laneA_004 `2b12cf9aa3afed8a` (ACDI/1288 Rickert Dr Naperville — dentist-owned group that
  collapsed 2018; address now independent David Chang DDS Ltd).
- DOWNGRADE_T3 ×7: Webster Dental Care ×2 (dentist-owned, founder Dr. Rempas — units 032/033),
  32 Dental Group ×2 (all LLCs dentist-officered — unit 039), Universal Dental Clinics ×2
  (founder Dr. Ahmed Ramaha — unit 090), Midwest Dental Sleep Center ×1 (founder/pres is
  Dr. Richard Craig DDS; the "non-dentist CEO Scott Craig" basis refuted — unit 085).
- MERGE-TIME FLAG: unit 032 row `d4f1bdbda7e997f6` has mislabeled `network_id`
  "brand:family_dental_care" (should be Webster) — fix/note during merge review.

REMAINING VERDICT WORK: second-flight units (the 3 research runs above) return their own inline
verdicts in each workflow's return payload — APPEND those to the SAME `_verdicts_wave1.json`
(the merge gate reads exactly one flat file, WAVE="wave1" hardcode) before running the merge.

### §6c External analyst review (2026-07-02 ~93% window) — HARD GATES ADOPTED

An independent analyst review + randomized audit (n=12, seed 20260703) found NO hallucination
pattern (9/12 strong pass, 0 fabricated practices/URLs; all sampled DSO claims held). Adopted
as BINDING pre-merge gates:
1. **HARD GATE: no merge/consolidation until `landed T4/T5 claims == verdict-covered claims`**
   (assert in the merge step), or uncovered claims are DELIBERATELY triaged with a note. At
   §6c authoring: 77 landed claims, 35 covered, 42 awaiting inline v2 verdicts (verify agents
   hadn't completed yet — journals showed research-stage results only).
2. **PM HOLD: row `b4ae96a81c4e81fb` DISTINCTIVE DENTAL CARE (626 N Addison Rd, Villa Park,
   assigned dentist_multi)** — analyst found cited site now centers on Oswego/Dr. Zaidi; Villa
   Park Bhojani evidence looks historical; possible ownership transition (Serenity Dental).
   Route to hold `operating_status_or_ownership_transition` at merge — do NOT write as clean T3.
3. Post-wave randomized audit becomes standing practice: fixed-seed n=20, forced inclusion of
   T4/T5 + T1/T2/T3 strata, independent URL verification.
4. Merge-review rule for T1/T2/T3: a directory listing alone proves existence/address, NOT
   ownership tier — require official site / provider bio / state record / multi-source corrob.
   Weak-evidence examples flagged: JACK S. LITZ DDS LTD, Paulos/Neighborhood Dental.
5. Stale-page rule: cited page showing old doctor/network evidence while the current site
   suggests a different operator → fail closed to hold.
6. Opportunistic intel stays labeled `lane_a_census_opportunistic` and is NEVER ownership
   evidence unless independently source-backed.

### §6d PAUSE SNAPSHOT (2026-07-02, user at ~93% usage — graceful pause executed)

- TaskStop'd all 3 research workflows (wmi4a38vs / wrk5dujmd / w87b116uy). Verdict recovery
  already complete. **184/218 units on disk, all committed.**
- Missing 34 units: 115 117-128 162-173 209 210 212-218.
- RESUME: `Workflow({scriptPath: <repo v2 script>, resumeFromRunId, args: same units})` for
  `wf_a79097d5-2c2` (relaunch), `wf_facf67a9-304` (w3), `wf_a8ac7ebd-e28` (w4) — args in §6
  table; completed agents replay cached. Then harvest inline verdicts from return payloads +
  journals (BOTH session dirs) into `_verdicts_wave1.json`; §6c gate 1 assert before merge.
- Verdicts file at pause: 35 entries; landed T4/T5 claims ~77+ → coverage assert WILL fail
  until inline verdicts harvested post-resume. That is the fail-closed design, not a bug.

## §6e — DEEP-DIVE + ANALYST RECONCILIATION (2026-07-02, paused state; PM-verified numbers)

Analyst's independent audit CONFIRMED against disk/DB — adopt their framing everywhere:
- Lane A input universe = **3,486 rows across 218 units** (unit files carry `{unit_id, practices}`).
  Say "2,918 rows banked (184/218 units)", never "3,700 banked". 3,700+ is only the post-completion
  projection (3,486 + 343 consolidated = 3,829 max Lane-A-era coverage; zero overlap verified).
- Banked: 2,918 rows / 2,533 classified (86.8%) / 385 undetermined. Conf: 1,592 high, 941 medium.
  Basis: web_verified 2,471, locator 57, ao_cluster 4, structural 1. 2,727 rows carry ≥1 URL;
  4,626 searches logged. Raw tier tally: T1 1,327 / T2 815 / T3 272 / T4 17 / T5 60 / T6 44.
- **Merge gate unchanged & fail-closed: 77 T4/T5 claims vs 35 verdicts** — harvest inline verdicts
  on resume before merge (§6c gate 1). Raw files still show pre-verdict DSO assignments by design.

**THE 610-LOCATION GAP DECOMPOSED (new — answers analyst's open question).** DB untiered IL-watched
GP pool = 4,096; units cover 3,486; uncovered 610 = **242 synthetic DA_/DIR_-NPI rows** (merge gate
rejects these anyway; they are the existing NPI-bridging queue) **+ 6 PM holds + ~362 real-NPI
locations never assigned to any unit** (heavy Naperville 60540 cluster in sample). ⇒ **WAVE 5
(~23 units, ~362 rows) needed after wave-4 completion** to close the researchable universe.
Unit-input lids not in current pool: 0 (no drift).

Detector-vs-human matrix (classified rows): 33 DSO claims at detector-independent locations;
31 reverse rows (detector dso_* → hand-verified dentist-owned/independent). PM review items at
merge: (a) reverse row "Aspen Dental, Morton Grove → true_independent conf=high" — suspicious,
eyeball; (b) 12 placeholder rows (§ prior note); (c) network-slug dedupe map grew:
1st_family_dental/1st-family-dental, dentalworks/dentalworks_sonrava/dentalworks-sonrava,
nadg/north_american_dental_group/grove_dental_nadg, destiny_dental/destiny_dental_prosmile
(midwest_dental vs midwest_dental_sleep_center are legitimately DISTINCT — do not merge).
R4 rule observed working (Dentologie 13-loc, CSG/GLDP 35-loc, Grove/NADG, Klyber/Webster all
deferred undetermined with R4 notes). Succession radar: 61 hand-verified T1/T2 est ≤1990
(oldest 1911). Intel: 1,117 rows populated (owner_career_stage 267, services 669, hiring 3).
Closure discipline: 8 "permanently closed" + 3 obituary cases correctly held undetermined.

### §6f UNPAUSE (2026-07-03) — second resume, same §6d recipe

User signal "gracefully unpause". Pre-resume checks: 184/218 files on disk; verdicts file 35
entries; landed T4/T5 claims recounted = 77 (gate gap 42, closes via inline verdicts). All three
research runs resumed with resumeFromRunId + identical args (cached agents replay; only the 34
missing units run live). New task IDs: relaunch wnx7tcqw0 / wave3 wme4f2x05 / wave4 wmwhcpbu1
(run IDs unchanged: wf_a79097d5-2c2 / wf_facf67a9-304 / wf_a8ac7ebd-e28). Journals for THIS
resume are under session dir 4d259360… again. On completion: harvest inline verdicts →
_verdicts_wave1.json, §6c gates, merge, PM review (§6e items), n=20 audit, consolidate, sync.

### §6g PAUSE 2 + UNPAUSE 2 (2026-07-03) — third launch, same recipe

PAUSE 2 (user at ~2% usage): TaskStop'd wnx7tcqw0/wme4f2x05/wmwhcpbu1; everything banked in
commit `fe18e64` (185/218 on disk — unit 115 landed during the §6f window). Escalation-ladder
plan committed `454c9e5` (`PLAN_HIDDEN_CORPORATE_ESCALATION_20260703.md`). During the pause the
ANALYST committed independently: `003b878` (deal-flow scraper hardening), `d2777ec` (deal
cleanup + sync_to_supabase changes — PM review required), `4e344c6` (true-independent hardening
screen = Rung 1 artifacts: `scrapers/screen_true_independent_hardening.py`,
`hidden_control_screen_20260703.json`, REVIEW + HANDOFF docs), `3c76c73` (DA audit defaults).
None touch `_lane_a_20260702/` unit/result files, the merge gate, or consolidate_census.

UNPAUSE 2 (user signal "please gracefully un-pause and continue"): pre-resume checks — 185/218
files on disk; missing 33 units: 117–128, 162–173, 209, 210, 212–218; model env unclamped
(opus-4-8/sonnet-5, no subagent pin). All three runs resumed with resumeFromRunId + identical
args. New task IDs: relaunch **w04zw4vq6** / wave3 **wohhaw4ea** / wave4 **wtnzpeec6**
(run IDs unchanged: wf_a79097d5-2c2 / wf_facf67a9-304 / wf_a8ac7ebd-e28). Journals under
session dir 4d259360…. On completion: same §6f chain (harvest inline verdicts → gates → merge →
PM review → n=20 audit → consolidate → sync), PLUS wave 5 build (~23 units, ~362 rows, §6e).

### §6h TRUE-INDEPENDENT HARDENING GATES ADOPTED (2026-07-03, PM ruling)

PM reviewed the analyst's pause-window work and ADOPTS it as BINDING, layered on the §6c gates
(evidence: `RESEARCH_HOME/REVIEW_TRUE_INDEPENDENT_HARDENING_20260703.md` +
`RESEARCH_HOME/HANDOFF_TRUE_INDEPENDENT_HARDENING_RUN_20260703.md`, commits 003b878/d2777ec/
4e344c6/3c76c73; deals leg verified — Supabase = SQLite 2,827 by id, 0 ghosts, dry-run read-back
2026-07-03):
1. **Core rule: T1 is a POSITIVE, current, corroborated ownership claim — not the absence of
   DSO evidence.** Directory-only T1/T2 rows are never high-confidence.
2. **New pre-merge gate:** after the fleet drains, RE-RUN
   `python3 scrapers/screen_true_independent_hardening.py` over all 218 units; NO consolidation
   until every `block_before_merge` row (236 at the 185-unit snapshot) is accepted, corrected,
   or moved to a hold bucket. Review order: db_corporate_conflict → t1_provider_count_gt1 /
   t1_group_entity_classification → ao_nonclinical_exec_title → stacked network signals.
3. **Separate T1/T2 audit** (in addition to the §6c n=20 DSO-stratified audit): include all
   hard-signal blockers + sample ≥20 from review_high + ≥20 directory-only review_medium.
4. T1 rows with provider_count > 1 default to correction→T2 or hold unless the extra NPIs are
   proven stale/non-practicing.
5. Persist the (reduced) signal vector at consolidation so the UI can show WHY a row is T1
   (feeds UI redesign Phase 0 data contract).
6. A `db_corporate_conflict` is a blocker because the evidence is CONTRADICTORY, not because
   the detector label wins — adjudicate row-by-row; fail-closed to hold.
Doc drift noted for next docs pass: CLAUDE.md deals counts are stale (now 2,827: gdn 2,472 /
pesp 329 / beckers 23 / beckers+gdn 3; pitchbook source deleted entirely — all 10 rows were
source-less+target-less; cleanup evidence `data/dso_research/deal_quality_cleanup_20260703.json`,
pre-write backup `data/backups/dental_pe_tracker_pre_deal_quality_cleanup_20260703.db`).

## §6i — FLEET FULLY DRAINED (2026-07-03, third flight complete)
All 3 final workflows completed with 0 unit failures (w04zw4vq6: 43u; wtnzpeec6: 45u; wohhaw4ea: 45u).
**218/218 result files on disk = 3,486 rows, 0 duplicate location_ids.** Final fleet-wide totals:
- Tiers: T1 true_independent 1,588 / T2 single_loc_group 938 / T3 dentist_multi 336 /
  T4 stealth_dso 24 / T5 branded_dso 74 / T6 institutional 49 / undetermined 477
  (classified 3,009; not-T1 among classified = 1,421 = 47.2%; T4+T5 = 98 = 3.3%; pe_backed 72).
- Confidence: high 1,937 / medium 1,204 / low 345.
- Inline verdict coverage on the three final flights: 64/64 DSO claims verified
  (45 CONFIRM, 18 DOWNGRADE_T3/refute, 1 INSUFFICIENT — the "Kang Dental" row in unit_131,
  lid 5404b210ff43f176: address is genuinely Dental Dreams HQ but the provider linkage was
  fabricated (cited NPI belongs to an Indiana provider); MUST go to hold/undetermined, not T5).
- Verdict downgrades cluster on dentist-owned networks misfiled as stealth_dso: Webster Dental
  Care (x2), Family Dental Care/Alemis, Dental 360/Brite, Mirza DDS, Umbrella, Dental Store/Old
  Orchard (x3), Blue Coral (specialist, excluded from GP floor anyway), Glen Ellyn FDC (Elite
  attribution contradicted). These become T3 at merge — the two-concept split (DECISION_TRUE_
  INDEPENDENT_HEADLINE_20260703.md) keeps them out of the DSO bucket without calling them T1.
- §6h screen re-run over FULL set (was 185 units, now 218): 2,862 screened → block_before_merge
  277 / review_high 325 / review_medium 860 / sample_low 975 / clean 425. Output:
  `_lane_a_20260702/hidden_control_screen_20260703.json` (regenerated).
**Next (in order, per §6h gates):** (1) adjudicate all 277 block_before_merge rows (accept /
correct / hold) — files-only artifacts; (2) apply verifier verdicts (DOWNGRADE_T3 etc.) in the
merge script; (3) n=20+ T1/T2 audit incl. directory-only + structural-signal rows; (4) only then
merge→consolidate(validate-only→allow-db-write)→dual-leg sync with read-back. No DB writes before
(1)–(3) complete.

## §6j — Fable session-limit recovery by Codex (2026-07-03)

The adjudication workflow `wf_723bfaaf-f92` reported completion just before the Fable session hit
the usage limit, but only **13 batch files** landed in
`_lane_a_20260702/adjudication/` (`batch_00.json` … `batch_12.json`). Those files cover
**130 of 277** `block_before_merge` rows, not the full queue.

Codex recovery actions:
- Preserved the 130 real adjudicator dispositions exactly as written.
- Wrote `_lane_a_20260702/_adjudication_missing_20260703.json` for the **147 rows with no
  landed disposition**.
- Wrote `_lane_a_20260702/_adjudication_rollup_20260703.json` with all 277 blockers represented:
  - real adjudicated: 130
  - explicit fail-closed recovery holds: 147
  - accepted original tier: 28
  - corrected tier: 61
  - real adjudicator holds: 41
  - recovery holds: 147

Important policy: the 147 recovery rows are **not adjudicated accepts/corrections**. They are
`hold_unadjudicated_session_limit` and `merge_action=hold_do_not_merge`. This keeps §6h safe:
no row lacking an adjudicator disposition can silently merge as T1/T2/T3. Fable may later rerun
adjudication only for the missing queue; until then, the conservative merge candidate must exclude
those 147 rows.

No DB, Supabase, LEDGER, or PROGRESS writes occurred during this recovery.

## §6k — Codex completed the missing adjudication queue (2026-07-03)

User asked Codex to finish the 147 rows Fable's session-limit crash left unadjudicated. Codex did
**not** label these as Opus outputs. Provenance is separate and explicit:

- Script: `scrapers/adjudicate_missing_lane_a_codex.py`
- Input: `_lane_a_20260702/_adjudication_missing_20260703.json` (147 bundles)
- Codex output: `_lane_a_20260702/adjudication_codex_missing_20260703.json`
- Complete rollup: `_lane_a_20260702/_adjudication_rollup_complete_20260703.json`

Policy used: conservative §6h adjudication from persisted bundles only, no live web re-check. DB
corporate conflicts and parent/control signals stay held; T1 is accepted only with own/current
owner-operator + single-location proof; T2/T3 are accepted only when already outside the true-solo
bucket and not contradicted by corporate/control signals.

Complete 277-blocker rollup now reads:
- Source split: Opus batch dispositions 130 / Codex missing-row dispositions 147.
- Merge-original accepts: 99.
- Merge-corrected tier: 65 (57 T1→T2 from Opus, 4 T1→T3 from Opus, 4 T2→T3 from Codex).
- Held out of merge: 113.
- Hold split: hold_dso_verify 51 / hold_network_review 24 / hold_unresolved 26 /
  hold_control_review 12.

Use `_adjudication_rollup_complete_20260703.json` for the next merge gate, not the older §6j
recovery-only rollup. If Fable wants higher coverage, review the 113 holds, especially the 72
Codex holds, but they must remain excluded unless explicitly accepted/corrected. Still no DB,
Supabase, LEDGER, or PROGRESS writes occurred.

## §6l — T1/T2 positive-proof audit completed (2026-07-04)

User asked Codex to run the required T1/T2 audit gate before any Lane A write. Codex ran a
files-only audit/remediation pass:

- Script: `scrapers/audit_lane_a_t1_t2.py`
- Audit artifact: `_lane_a_20260702/audit_t1_t2_positive_proof_20260704.json`
- Source-check artifact: `_lane_a_20260702/audit_t1_t2_source_check_20260704.json`
- Source-check manual notes: `_lane_a_20260702/audit_t1_t2_source_check_notes_20260704.md`

Policy applied:
- Hold T1/T2 rows that still carry `db_corporate_conflict` or `parent_or_legal_entity_signal`.
- Hold T1 rows that still carry hard roster/group contradictions (`t1_provider_count_gt1`,
  `t1_group_entity_classification`, `t1_multiple_provider_surnames`).
- Downgrade high-confidence directory-supported T1/T2 rows to medium; do not let directory-only
  evidence publish as high-confidence true-independent proof.

Result after late Opus batches (`batch_13` through `batch_18`, plus `batch_22`) were incorporated:
- Adjudication rollup source split: Opus 200 / Codex missing-row recovery 77.
- Scanned 2,419 candidate T1/T2 rows.
- Held 50 rows into triage as `t1_t2_positive_proof_audit_hold`.
- Downgraded confidence on 482 overconfident T1/T2 rows.
- Candidate now has **2,836 rows** and validates cleanly with `consolidate_census.py --validate-only`.
- Tally after audit: T1 1,437 / T2 932 / T3 362 / T4 7 / T5 49 / T6 49.
- Triage now has 650 rows.

Bounded source check over the 104-row fixed-seed audit sample: 85/104 sampled rows had at least
one resolving citation. Three corporate-language regex hits were manually reviewed; all three were
already held. No additional source-check holds were added.

Still no DB, Supabase, LEDGER, or PROGRESS writes occurred.

## §6m — ADJUDICATION COMPLETE AT FULL OPUS COVERAGE + LOCAL DB WRITE EXECUTED (Fable, 2026-07-04)

Workflow `wf_723bfaaf-f92` resumed after the session-limit reset and finished **28/28 batches,
0 errors**: all **277 blockers now carry researched Opus dispositions** (accept 111 / correct 75
/ hold_dso_verify 52 / hold_unresolved 30 / duplicate_suspect 9). This SUPERSEDES the Codex
fail-closed stopgap (§6j/§6k) — `adjudicate_missing_lane_a_codex.py` re-run converged the rollup
to source_counts `{opus_batch: 277}` (codex_missing file now has 0 rows; kept for provenance).

Chain re-run in order, all gates green:
1. `_merge_lane_a_results_20260702.py` → 2,889 kept / triage 597 (holds 91, dup-suspects 9 excluded).
2. `audit_lane_a_t1_t2.py` (seed 20260704) → 52 held, 483 confidence-downgraded → candidate **2,837**.
3. `consolidate_census.py … --validate-only` → Validation OK.
4. Pre-write backup `data/backups/dental_pe_tracker_pre_census_write_20260704.db`
   (md5 `ba6f869e0509552d19942c2cb89b79bd`, = pre-write live DB md5).
5. `consolidate_census.py … --session fable_lane_a_wave1_final_20260704 --allow-db-write` →
   **2,837 locations updated, skipped_bad=0; LEDGER +2,837**.

LOCAL SQLite state (verified by direct query):
- `practice_locations.ownership_tier` notnull **3,180** = census coverage **3,180/4,439 = 71.64%**.
- Full tally: T1 1,471 / T2 934 / T3 537 / T4 28 / T5 151 / T6 59; `pe_backed` 118 locations.
- NPI mirror: 6,754 `practices` rows carry ownership_tier.
- Detector floor UNTOUCHED: corp locations 268 / corp NPIs 1,152 (two-axis separation intact).

✅ **SUPABASE SYNC EXECUTED + READ-BACK VERIFIED BOTH LEGS (Fable, 2026-07-04 ~12:07 local).**
User granted explicit full permission ("you have my full permissions to run all that stuff make
it autonomous"), superseding the earlier permission-classifier denial. Run order + results:
```bash
python3 -m scrapers._sync_floor_tables_only          # leg 1 ✅ exit 0: practice_locations 5,657 / zip_scores 290 / dso_locations 633 (verified counts)
python3 -m scrapers._sync_census_columns_practices   # leg 2 ✅ exit 0: 6,754/6,754 rows updated, 0 not present; per-tier tally Supabase = SQLite MATCH
```
Read-back (direct Postgres queries, all targets EXACT):
- `practice_locations` ownership_tier notnull **3,180** — T1 1,471 / T2 934 / T3 537 / T4 28 / T5 151 / T6 59; `pe_backed` 118.
- `practices` census mirror **6,754** (tally: true_independent 1,810 / single_loc_group 2,624 / dentist_multi 1,370 / stealth_dso 94 / branded_dso 604 / institutional 252).
- Detector floor UNCHANGED: corp locations 268 / corp NPIs 1,152 / zip_scores GP 4,801 / zip_scores corp 268 (live floor 5.58%).

Live-app sanity (deployed frontend at `7443f0a`, reads Supabase directly — no redeploy needed):
`/practice/199841c7ee233c17` (Affordable Dentures & Implants) renders the census layer end-to-end
— "Verified · Branded DSO · PE" badge, 4 evidence URLs (Harvest Partners portfolio, DentistryIQ,
PitchBook), legacy detector class explicitly labeled "kept as context below the hand-reviewed
census tier". `/job-market` headline KPIs still lead with the detector floor (honestly labeled,
5.6% Confirmed Corporate) — moving census to primary display is the chartered truth-app session's
Phase 1+, which this sync UNBLOCKS. Note: Codex has 1 unpushed frontend commit (`68796d6`
ownership-truth contract) + uncommitted /system census-sync-status work in progress — left alone
per the concurrency rule.

Remaining census work AFTER sync (not blocking): holds queue 91 (52 dso_verify + 30 unresolved +
9 duplicate_suspect) + triage 649 rows + 477 undetermined + ~950 never-researched (wave-5 queue).
Next mission: SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md (truth-safe app redesign).
