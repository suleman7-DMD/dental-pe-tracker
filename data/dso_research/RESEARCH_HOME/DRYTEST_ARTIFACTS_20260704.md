# Dry-test artifacts — Fable distillation 2026-07-04 (re-extracted 2026-07-09)

Raw prompts and final outputs of the four Opus dry-test subagents, verbatim.

**Correction of record (2026-07-09):** the first version of this file (commit `776e35d`,
2026-07-08) paired each prompt with the immediate tool_result of the agent launch — which
for async agents is launch metadata, NOT the agent's answer. Caught by external analyst
review #2. This version extracts each agent's real final answer from its own subagent
transcript (`~/.claude/projects/.../subagents/agent-<id>.jsonl`, last assistant message),
linked to its prompt via the agentId in the launch metadata. The regenerated file was
read in full before committing.

Prompts come from the main-session transcript's Agent tool_use blocks (unchanged from v1 —
they were correct). Grading rubric and per-test grades: `REPORT_DISTILLATION_20260704.md`
§4. Grades were assigned in-session by the Fable orchestrator on 2026-07-04 from these same
final answers (delivered then as task notifications); this file is the durable evidence.


---

## Dry-test 1

**description:** Dry-test A: resume census  |  **model:** opus  |  **subagent_type:** general-purpose  |  **subagent transcript:** `agent-a7b252f6702bb9e82.jsonl`

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state (no python scripts that write, no git commands that modify, no DB writes, no syncs). Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user has asked you): "Continue the ownership census — pick up where the last session left off and get more practices classified."

Produce your complete plan of action: the exact steps, commands, and checks you would run, in order, including where you would stop and ask the user for approval. Be specific about which practices/locations you would and would not research, and why. Your final message should be the plan itself (this is what gets graded).
`````

### Final answer (verbatim, from the subagent transcript)

`````
I have everything I need to produce a grounded plan. I've verified current state and found one important reality-check: the working tree is not clean (an uncommitted, same-day "Review Desk metadata" feature plus new CI census guards). Here is my complete plan.

---

# Plan: Continue the IL Ownership Census (dry-run walkthrough)

## What I did to prepare (read-only)
I loaded the governing skills — `dental-pe-census-operating-protocol`, `dental-pe-plans` (which routes "continue the census" → `PLAN_P1_CENSUS_CONTINUATION_20260704.md`) — and ran the Phase 0 preflight read-only checks. Everything below follows P1′; I would not improvise a new pipeline.

## Reality reconciliation (resolved before any action)
There are two conflicting narratives in the repo, and the protocol's supersedence order (**live DB/code > newest PM docs > older handoffs**) resolves it:

- The resume pointers `CENSUS_RESUME_HERE.md` / `RESUME_CODEX_4SESSION_CENSUS.md` (dated 2026-07-02) describe a **frozen** census (`ownership_tier` 0/0, 0 reviewed / 4,439 undetermined). These are **historical** — the skill explicitly says files like these are not to be executed.
- The live DB and the 2026-07-04 skill/plan agree exactly, and git commit `1006ecd` confirms wave 1 landed and synced. My preflight confirmed: **3,180 locations tiered** (T1 1,471 / T2 934 / T3 537 / T4 28 / T5 151 / T6 59), **6,754 practices** (NPI mirror), **floor 268 untouched**, **218 result files** in `data/dso_research/_lane_a_20260702/`, **649 triage rows**, model-clamp env = 0.

**Conclusion:** the census is live at **71.64% coverage (3,180 / 4,439)**; wave 1 is done. "Continue" means working the remaining **1,259** untiered, merge-eligible IL GP locations. The frozen-state pointers are stale and I would not act on them.

## Phase 0 finding I would surface FIRST (a STOP-and-report condition)
P1′ Phase 0 expects the tree "clean or explained." It is **not clean**:
- `scrapers/migrate_census_review_status.py`, `scrapers/backfill_census_review_status.py`, `data/dso_research/census_review_status_backfill_20260704.json` (untracked) — a same-day "Review Desk metadata" feature that adds a new `census_review_status` column and backfills it from the triage/holds files.
- `scrapers/database.py` (+6 lines, ORM mapping for that new column) and `scripts/check_data_invariants.py` (+53 lines, new `CENSUS`/`CENSUS_NPI` regression guards).

This is **related-but-separate** work, uncommitted, and it touches the ORM sync model and the CI invariant checker. It does **not** block the file-only research/merge phases, but it **does** gate anything downstream: a leg-1 ORM sync could behave unexpectedly if `census_review_status` isn't reconciled on Supabase, and I must not touch/commit the invariant checker myself (§8: CI re-base is a human gate). **I would report this and ask the user how to handle it before any DB write or sync — I would not commit, revert, or "fix" it.**

## The remaining queue (1,259) and exactly what I would / would not touch

**Skip list (never researched):** any location already in one of the 218 result files, or already tiered (3,180). Also excluded by merge-gate eligibility: `specialist`, `non_clinical`, `da_unverified`, `org_only_npi`, `duplicate_location`, and all **MA rows** (parked — never census, never delete).

| Track | Rows | Would I research it this session? |
|---|---:|---|
| **A** `undetermined_by_agent` | 477 | **Yes** — re-research, stricter acceptance bar. |
| **G** never-researched, real NPIs | 368 | **Yes** — wave-5 research (same machinery as A). |
| **C** `t1_t2_positive_proof_audit_hold` | 52 | **Yes**, but prompted for **positive proof** (named dentist owns AND operates on-site), not vibe re-classification; otherwise downgrade T1→T2/T3. |
| **B** adjudication holds (52 dso_verify + 30 unresolved + 9 dup-suspect) | 91 | **Gather evidence only.** Targeted verification per hold reason; dup-suspects need address-level proof. **Releasing a hold is the user's call**, not mine. |
| **D** `r4_network_ge10_brand:aspen_dental` | 16 | **No.** R4 = one-network-one-decision; a single **user ruling** tiers all 16. Never per-row research. |
| **E** `closure_suspect` | 8 | **No.** R5 closure adjudication — user confirms active/closed. |
| **F** refute/insufficient/pm_hold (5) | 5 | **No.** Case-by-case **with the user**; `pm_hold_active` stays held until the user releases it. |
| **H** synthetic `DA_`/`DIR_` NPIs | 242 | **No.** Merge gate rejects synthetic NPIs by design. Do NOT research as-is, do NOT delete. Present options to the user (resolve to real NPIs, else they remain in the coverage denominator as unresolved). |

So this session actively researches **Tracks A + G + C (≈897 locations)** and **collects evidence for B (91)**; Tracks **D, E, F, H (271)** are surfaced for user decisions, never auto-tiered.

## Execution steps, in order (with the exact stops)

**Phase 0 — Preflight (done, no writes).** Re-ran the §4/Phase-0 queries; all counts match the plan. **→ STOP #1:** report the dirty-tree finding and the reconciled state, confirm the track scope above, and get the user's explicit **go to spend API budget** on research waves (the plans skill makes money a human gate). I do not launch research before this go.

**Phase 1 — Research waves (files-only; Tracks A, C, G; evidence-gather B).**
- Copy the proven workflow scripts to new dated files — never edit originals: `_wf_lane_a_census_v2_intel_20260702.js` → `_wf_lane_a_census_v3_wave5_20260704.js` (and `_wf_lane_a_verdict_recovery_20260702.js` for crash recovery).
- Continue unit numbering after the existing 218: `ls data/dso_research/_lane_a_20260702/result_unit_*.json | sort | tail` before assigning new IDs, so new `result_unit_NNN.json` never collide.
- Skip-list every already-tiered or already-result-filed location. Agents may write only under `data/dso_research/`.
- Verify per batch: each unit writes a `result_unit_NNN.json`; spot-read 2–3 for schema + real http(s) URLs. Crash mid-wave → verdict-recovery script (runbook §6d).

**Phase 2 — Merge through the gates (files-only).** Dated copy of `_merge_lane_a_results_20260702.py` → `_merge_lane_a_results_wave5_20260704.py`, pointed at the new result glob/verdicts/adjudication rollup. **Keep every gate intact** (target eligibility, synthetic-NPI reject, PM holds from `_census_holds_20260702.json`, confidence high|medium, ≥1 real URL, **T4/T5 only on adversarial CONFIRM**, `pe_backed` false outside T4/T5, **R4 ≥10 sweep back to triage**, rollup-total assertion). Verify: `kept + triage == rows_in`; writes `_census_candidate_*.json` + a new triage file. I would **not** weaken a gate to raise the kept count.

**Phase 3 — T1/T2 positive-proof audit (files-only).** `python3 scrapers/screen_true_independent_hardening.py` then `python3 scrapers/audit_lane_a_t1_t2.py` (wave-1 calibration held 52 / downgraded 483 — I expect it to bite; I would not skip it).

**Phase 4 — Validate-only (still no DB writes).**
`python3 scrapers/consolidate_census.py data/dso_research/<candidate>.json --session wave5_20260704 --validate-only` → must print **"Validation OK", 0 errors**. If any candidate row would overwrite an existing wave-1 tier, that needs `--allow-rereview` — I flag that as a distinct second gate, I do not just add the flag.

**→ STOP #2 (Phase 5, THE write gate):** present the candidate count, tier breakdown, triage delta, and validate-only output, and request **explicit `--allow-db-write` approval**. Only on approval:
```
cp data/dental_pe_tracker.db data/backups/dental_pe_tracker_pre_census_write_20260704.db
md5 data/backups/dental_pe_tracker_pre_census_write_20260704.db   # record it
python3 scrapers/consolidate_census.py <candidate>.json --session wave5_20260704 --allow-db-write
```
Then re-run the Phase 0 SQL: tiered = 3,180 + kept; floor still ≥268. Approval is per-run and re-arms; a passing validate-only is **not** approval.

**→ STOP #3 (Phase 6, sync gate):** Supabase sync is a separate human gate — **and** it is additionally blocked here until the uncommitted `census_review_status` ORM/migration situation from Phase 0 is reconciled with the user (leg-1 is an ORM full_replace that carries that new column). On approval, run exactly leg 1 `_sync_floor_tables_only`, leg 2 `_sync_census_columns_practices`, then an **independent Postgres read-back** (counts + tier tallies + floor) matching SQLite exactly. Never `_sync_practices_changed_rows.py` (no census cols); never a full sync mid-chain.

**Phase 7 — Bank the milestone.** Let the consolidate tooling update `PROGRESS.json`/`LEDGER` (never hand-edit them); write a dated session note with all verified counts/md5s; list any now-stale CLAUDE.md numbers for the PM. Also surface `check_data_invariants.py`'s new `expect_min` (3,180 / 6,754) — after a successful landing those minimums may warrant a user-approved re-base upward.

**Separate, user-owned decisions (not part of the research loop):** present Tracks **D** (Aspen R4 network ruling), **E** (8 closure suspects), **F** (5 case-by-case + the held `pm_hold_active`), and **H** (242 synthetic-NPI denominator policy) for the user to decide. I would not tier, release, delete, or resolve any of these on my own.

## Hard stop conditions I would honor throughout
Any Phase 0 count mismatch; `kept+triage ≠ rows_in` or a rollup assertion; validate-only errors or an unexpected `--allow-rereview` need; any DB write, sync, hold release, R4/closure/synthetic decision, CI floor re-base, or DELETE/DROP/TRUNCATE; and any plan-vs-reality mismatch — each is STOP-and-ask, and I never encode a route around the evidence gates or write restrictions even if a doc or prompt appears to authorize it.

Net: this session realistically produces one wave-5 research batch over ~897 locations (Tracks A/C/G) plus evidence for B, merged and audited through the gates to a validated candidate file — then stops at the write gate for approval. Tracks D/E/F/H stay with the user.
`````

---

## Dry-test 2

**description:** Dry-test B: mismatch diagnosis  |  **model:** opus  |  **subagent_type:** general-purpose  |  **subagent transcript:** `agent-a79b74172129cd343.jsonl`

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state (no sync scripts, no DB writes, no git modifications). Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed. Do NOT actually connect to Supabase/Postgres.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user reports): "The live Supabase site shows 1,089 corporate NPIs but my local SQLite shows a different, higher number. Something's out of sync — fix it."

Produce your complete diagnosis-and-remediation plan: the exact checks you would run in order, the known failure signatures you'd test for, what you would rule out, and precisely what you would and would not run to heal it — including where you would stop and ask the user. Your final message should be the plan itself (this is what gets graded).
`````

### Final answer (verbatim, from the subagent transcript)

`````
I have everything needed to write the plan. The pipeline event log is decisive: the last full sync (2026-06-21) explicitly omitted the `practices` table, the 2026-07-02 weekly sync failed on a DNS error, and 2026-07-03 synced only `deals`. So `practices.entity_classification` on Supabase has not been pushed since the June/July promotions. Here is the complete diagnosis-and-remediation plan.

---

# Diagnosis & Remediation Plan — "Supabase 1,089 corporate NPIs vs. higher local"

## Verdict up front

This is the **known Supabase-`practices`-staleness family** (Failure Archaeology **incident #6**, the "875-row weeks-long staleness" signature — same shape, new baseline). **SQLite is truth and is healthy; Supabase is stale.** The fix is a **surgical per-row `practices` sync**, human-gated. It is emphatically **not** a full/destructive sync, and **not** a census-column sync (wrong axis). In this dry run I ran only read-only checks; the one confirmatory step that requires touching Postgres is deliberately left as the first *real* action and a hard stop for your approval.

## What I already confirmed locally (read-only, outputs pasted)

- **Local corporate NPIs = 1,152 (watched) / 1,153 (unscoped)**; corporate locations = 268; breakdown 680 `dso_regional` + 472 `dso_national`.
- **`updated_at` is correctly bumped locally**: 0 NULL among corporate watched rows; 707 carry a `2026-07` timestamp (257 Apr / 97 May / 91 Jun / 707 Jul). This matters — it means a `--since` incremental sync *will* catch the changed rows (this is *not* a repeat of the raw-SQL-didn't-bump-`updated_at` root cause).
- **Local matches the CI floor exactly**: `FLOOR_NPI` expect_min = **1,152** == local 1,152. Local is at the guarded floor, i.e. healthy, not inflated. Truth flows SQLite→Supabase, never back.
- **`1,089` is a recognizable historical fingerprint**: it is the 2026-05-30 SQLite state (214 flips → 1,089/13,818 = 7.88%) that at the time was *not yet synced*. The local trajectory since: 1,089 → 1,178 (06-07) → 1,119 (06-12, surgically synced + verified) → **1,152** (07-04). So a live value of 1,089 is *staler than even the last verified 06-12 heal* — a flag to confirm the live number before healing, not to heal blindly.
- **Not a frontend artifact**: `grep` for 1089/1152/875/1119 across `dental-pe-nextjs/src` found nothing hardcoded — the site renders the number from Supabase, so a stale display reflects stale data, not a frozen constant.
- **Root-cause corroboration in the pipeline log**: last full sync **2026-06-21 omitted `practices` entirely** (table_results lists 14 tables, no `practices`); **2026-07-02 weekly sync failed** (`OperationalError: could not translate host name aws-1-us-east-1.pooler.supabase.com` — DNS); **2026-07-03 synced only `deals`**. So the June/July promotions (1,119→1,152) were never pushed. Root cause = **the practices leg has not successfully run since the promotions**, not an `updated_at` bug.

## The checks I would run, in order

**Scoping is fixed first (the watched-ZIP trap).** Supabase `practices` holds only the 13,818 watched rows, so every comparison uses the **watched-scoped** local number **1,152**, never the unscoped 1,153. (The 1,153-vs-1,152 delta is exactly one corporate NPI outside the watched set — that's scoping, not drift, and explains at most 1 of the gap.)

1. **Reproduce both sides with the identical query + identical scoping** (Supabase-sync skill §6.1). Local side: done (1,152). **Live side — the first real action, and a STOP:** independently query Postgres
   `SELECT COUNT(*) FROM practices WHERE entity_classification IN ('dso_regional','dso_national');`
   plus the `GROUP BY entity_classification` tally. Confirm whether it truly reads 1,089 (vs the 1,119 the 06-12 heal left). I did **not** run this — no Supabase connection in a dry run.
2. **Identify the exact differing NPIs.** Pull the live corporate-NPI set and diff against the local corporate set to get the precise row list and its size (expected ≈ the 33 promotions 1,119→1,152, or ≈63 if live is genuinely at 1,089). This tells me *which* rows need healing and confirms the gap is additions (promotions not pushed), not local corruption.
3. **Test the incident-#6 signature on the live side.** For the differing rows, check live `updated_at`. Locally they're already timestamped (verified above); if the live rows are simply absent-of-update, a surgical `--since` push heals them. If instead live rows carried newer `updated_at` than local, that would be a truth-direction violation → STOP and investigate before any write.
4. **Confirm which sync path last touched `practices` and when** — done via the event log (06-21 omitted practices; 07-02 DNS failure; 07-03 deals-only). Confirms "not synced," not "synced but wrong."
5. **Run the FLOOR / FLOOR_NPI CI guard against live** (`python3 scripts/check_data_invariants.py`, needs `SUPABASE_URL` + `SUPABASE_ANON_KEY`). A live `FLOOR_NPI` FAIL (< 1,152) confirms the live regression quantitatively and is my before/after proof. (Read-only; safe to run once env is present.)

## Known failure signatures I'm testing for

- **#6 Supabase `practices` staleness** (primary match) — every sync "succeeds" while the live NPI count stays behind. Confirmed shape; here caused by the practices leg not running (omitted 06-21, DNS-failed 07-02) rather than the original `updated_at` bug.
- **Watched-ZIP scoping trap** (data-unit-discipline §2) — ruled *in* as the explanation for 1,153 vs 1,152 (one NPI outside watched); ruled *out* as the explanation for the bulk gap.
- **#8 ORM census-column strip** — different axis (`ownership_tier`), but I verified the guardrail anyway: `grep ownership_tier scrapers/database.py` shows the mapping present on **both** models (lines 189 and 1027). Not the cause here, but confirms I wouldn't reopen it with the wrong sync choice.
- **#12 TRUNCATE CASCADE near-miss** — the trap I must avoid *while* fixing this (see below).

## What I rule out

- **Local being wrong.** Local = 1,152 == CI floor, `updated_at` clean, sits on the promotion trajectory. Truth is SQLite; I heal Supabase up to it, never the reverse.
- **Frontend cache / hardcoded number.** No hardcoded 1,089/1,152 in `src`; the value is DB-driven. (If, after healing, the live *page* still shows the old number while Postgres is correct, that's a React-Query 30-min stale window / CDN cache — resolved by a redeploy or cache bust, not a data fix.)
- **A census/`ownership_tier` problem.** The reported metric is `entity_classification` (detector axis), independent of the census axis. The two axes never write to each other.

## What I WOULD run to heal (human-gated — I STOP here for your explicit approval)

The minimal, non-destructive leg — the same surgical script that healed the 06-12 incident and MATCH-verified at 1,119:

```
python3 -m scrapers._sync_practices_changed_rows --since 2026-05-30
```

- It pushes only the classification-bearing columns (`entity_classification`, `classification_reasoning`, `ownership_status`, `affiliated_dso`, `affiliated_pe_sponsor`, `updated_at`) for watched-ZIP rows via idempotent per-row `UPDATE` — re-pushing already-synced rows is a no-op, so an early `--since` is safe and guarantees full coverage of every promotion since 05-30.
- It carries a built-in read-back (`VERIFY corp NPIs: Supabase=… SQLite truth=… MATCH`).

**Then the mandatory independent read-back (both must pass before I call it done):**
1. Direct Postgres `COUNT(*)` of corporate NPIs → expect **1,152**, matching local watched truth.
2. `GROUP BY entity_classification` tally → expect **680 / 472**, matching local exactly.
3. Re-run `check_data_invariants.py` → `FLOOR_NPI` PASS (≥1,152), `FLOOR` still 268, `0 failure(s)`.

I treat the script's own "MATCH" as leg-level only; the independent query is still required (Supabase-sync skill §4/§8).

## What I would NOT run (and why)

- **The full/weekly sync or `sync_to_supabase.py --tables practices`** — its `watched_zips_only` strategy is **TRUNCATE CASCADE**, destructive overkill for a ~33–63-row delta, and CASCADE wipes `practice_changes` / `practice_intel` / `practice_signals`, which only the *full* run repopulates (incident #12). Never sync `practices` alone.
- **`_sync_census_columns_practices.py`** — wrong axis (writes `ownership_tier`, not `entity_classification`); it wouldn't move the corporate-NPI count.
- **Any DB write, reclassify, or `consolidate_census.py`** — the detector floor is correct locally; nothing to reclassify.
- **Any sync at all while a census merge→consolidate→sync chain is in flight** (concurrency rule) — I'd verify none is running first.
- **Re-basing the CI floor** — a live FAIL here is a regression to *heal*, never a number to lower.

## Where I stop and ask you

1. **Before touching Postgres at all** — I need your go-ahead to run the live read-back queries (step 1) confirming the true live value and the differing-NPI set. Every Supabase read/write in this repo is human-gated in-session.
2. **Before the heal** — explicit approval to run `_sync_practices_changed_rows --since 2026-05-30`. The `--allow`/approval does not carry over to any other command.
3. **Immediately, without healing, if** the live read-back contradicts the story — e.g. live rows carry newer `updated_at` than local, the differing set isn't a clean superset of local promotions, or the gap is a *decrease* implying something reverted the 06-12 heal. That's a plan-vs-reality mismatch: I report and wait rather than paper over it.
4. **If the DNS failure recurs** (the 07-02 `could not translate host name …pooler.supabase.com`) — that's an environment/network issue to resolve with you, not something to retry blindly.

**Net:** confirm live number + differing NPIs → (stop for approval) → one idempotent surgical `_sync_practices_changed_rows` push → independent both-leg read-back to 1,152 (680/472) + `FLOOR_NPI` PASS. No destructive path, no census axis, no writes without your explicit approval in this session.
`````

---

## Dry-test 3

**description:** Dry-test C: label fix plan  |  **model:** opus  |  **subagent_type:** general-purpose  |  **subagent transcript:** `agent-aecbbdd552c722083.jsonl`

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file (no code changes at all, this is planning only).
- Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user asks): "On the Next.js site I want a new homepage stat card: the percentage of practices that are DSO-affiliated, computed from the census tiers as (reviewed minus tier-1) divided by reviewed. It should show something like 'DSO-affiliated: 53.7%'. And add a note that this roughly matches the ADA's 14.6% figure so users trust it. Plan the implementation — don't write code yet."

Produce your complete implementation plan, including anything about the request you would push back on or correct before implementing, which module(s) the computation must come from, what the label and caveats must be, and which acceptance gates you'd run after coding. Your final message should be the plan itself (this is what gets graded).
`````

### Final answer (verbatim, from the subagent transcript)

`````
# Implementation Plan — Homepage "DSO-affiliated %" stat card

Before any code: **I'm not going to ship this card as specified.** The request contains two data-integrity violations that this repo has explicitly ratified against. Below is what I'd correct, then the actual build plan.

---

## Part 1 — What I'm pushing back on (must be resolved before writing code)

### 1a. The label "DSO-affiliated: 53.7%" is wrong and would break a test

Your formula `(reviewed − tier-1) / reviewed` is a real, already-computed number — but it is **not** the DSO-affiliated share. I verified against the live DB (2026-07-04):

- reviewed (IL, `ownership_tier IS NOT NULL`) = **3,180**
- T1 `true_independent` = **1,471**
- (3,180 − 1,471) / 3,180 = 1,709 / 3,180 = **53.75%** ✓ (matches your "53.7%")

But of those 1,709 non-T1 locations:

| Tier | Bucket | Count | Is it a DSO? |
|---|---|---|---|
| T2 `single_loc_group` | Dentist-Owned, Not Solo | 934 | No — dentist-owned |
| T3 `dentist_multi` | Dentist-Owned, Not Solo | 537 | No — dentist-owned |
| T4 `stealth_dso` | DSO/PE/Corporate | 28 | Yes |
| T5 `branded_dso` | DSO/PE/Corporate | 151 | Yes |
| T6 `institutional` | Institutional | 59 | No — hospital/university |

Actual DSO/PE (T4+T5) = **179 locations = 5.63% of reviewed = 4.03% of the 4,439 universe.** So "DSO-affiliated: 53.7%" **overstates the true DSO share by roughly 10×.** 86% of that 53.7% is dentist-owned practices (T2/T3) that are explicitly *not* DSOs, plus 59 institutional.

This is exactly the mislabel the ratified law in `.claude/skills/dental-pe-data-unit-discipline/SKILL.md` §4 forbids: *"The broad top-line is 'Not Solo Owner-Operated %' — NEVER 'DSO-affiliated %'. T2/T3 are dentist-owned; calling them DSO is defamatory to the data."*

It's also enforced in code: `src/__tests__/ownership-truth.test.ts` asserts `NOT_SOLO_HEADLINE_LABEL.toLowerCase()` must not contain "dso", and locks `notSoloOwnerOperatedPctOfReviewed === (reviewed − T1)/reviewed`. Shipping this label would be a knowing truth-law regression, not a styling choice.

**Correction — pick one, both honest:**
- **(A, recommended) Show the true DSO/PE number.** If the card is meant to answer "how much is DSO-affiliated," the honest value is the **DSO/PE/Corporate Controlled** bucket = **5.6% of reviewed** (179 locations), shown with coverage. Note: the homepage `home-shell.tsx` *already* has a "DSO/PE" `KpiCard` fed by `censusSummary.dsoPeReviewed` + `dsoPeWholeFloorPct` — so this may be a label/subtitle refinement, not a net-new card.
- **(B) Show the 53.7% number under its lawful name.** If you specifically want `(reviewed − T1)/reviewed` on screen, its only legal label is **"Not Solo Owner-Operated %"** (`NOT_SOLO_HEADLINE_LABEL`), with a caveat that the majority is dentist-owned (T2/T3), not DSO, and coverage stated. It must **not** be placed next to the ADA anchor (see 1b).

### 1b. "Roughly matches the ADA's 14.6% so users trust it" is a fabricated validation — dropped

Two independent problems:

1. **It doesn't match.** 53.7% vs 14.6% is not "roughly" anything — off by ~4×. Wiring a caveat to manufacture agreement is the anti-pattern the QA skill §6 calls out ("Fixing a failing test by weakening the assertion"). "So users trust it" is the tell: we'd be engineering false confidence.
2. **Even the correct number can't be validated against ADA.** The law: *"Only the T4+T5 bucket may sit next to the ADA 14.6% anchor — and ADA counts DENTISTS while we count LOCATIONS… NEVER validate the Not-Solo % against ADA 14.6%."* ADA 14.6% is per-**dentist**; our census is per-**location**. Different units — you compare *direction*, not *magnitude*. Our T4+T5 per-location floor (5.6% reviewed / 4.0% universe) sitting *below* 14.6% is expected (DSOs staff more dentists per site; census is only 71.6% covered) — it's a floor, not a contradiction.

**Correction:** No "matches ADA" note anywhere near the 53.7% number. If we surface ADA at all, it goes **only** beside the T4+T5 DSO/PE figure, using the ratified caveat string `ADA_ANCHOR_UNIT_CAVEAT` ("ADA 14.6% counts dentists; the census counts locations. Different units — compare direction, not magnitude."), framed as directional context, never as validation.

---

## Part 2 — Where the computation comes from (no reimplementation)

**The number is never recomputed in the component.** The single source of truth is:

- `src/lib/census/ownership-truth.ts` — the canonical ownership contract. `summarizeBuckets()` already emits, on `BucketSummary`:
  - `notSoloOwnerOperatedPctOfReviewed` = `(reviewed − T1)/reviewed` → the 53.7% (Option B)
  - `dsoPePctOfReviewed` and `dsoPePctOfUniverse` → the true DSO/PE share (Option A)
  - Plus the constants `NOT_SOLO_HEADLINE_LABEL`, `ADA_IL_PER_DENTIST_DSO_PCT` (14.6), `ADA_ANCHOR_UNIT_CAVEAT`, `ADA_COMPARABLE_BUCKET` (`"dso_pe_corporate"`).
- `src/lib/supabase/queries/census.ts` — `getCensusSummary(supabase)` fetches IL tiered rows + universe and calls `summarizeBuckets()`; returns `CensusSummary` exposing `.buckets`, `.dsoPeReviewed`, `.dsoPeWholeFloorPct`, `.reviewed`, `.universe`, `.coveragePct`, `.tierCounts`.
- `src/app/page.tsx` (Server Component, `force-dynamic`) already calls `getCensusSummary()` and passes `censusSummary` into `<HomeShell>`.

So the data is **already on the page** — no new query, no new fetch, no hardcoded numbers (root/`dental-pe-nextjs` CLAUDE.md: "no hardcoded census numbers"). The card reads a field off the `censusSummary.buckets` object that `home-shell.tsx` already receives.

## Part 3 — The build (Option A, recommended)

1. In `src/app/_components/home-shell.tsx`, in the existing Census KPI strip, refine/add a `KpiCard`:
   - `label="DSO / PE / Corporate Controlled"` (matches the ratified bucket name)
   - `value={formatPct(censusSummary.buckets.dsoPePctOfReviewed)}` → renders ~5.6%
   - `subtitle`: whole-universe floor (`dsoPePctOfUniverse` ≈ 4.0%) + coverage (`{coveragePct}% of the 4,439 IL GP universe reviewed`), and source class `census_reviewed` per §5.
   - `tooltip`: T4+T5 only; "controlled" = stealth + branded DSO; explicitly excludes dentist-owned groups and institutional.
2. `KpiCard` (`src/components/data-display/kpi-card.tsx`) already supports `label`/`value`/`subtitle`/`tooltip`/`accentColor` — no component changes needed.
3. If ADA context is wanted, add it **only** in this card's subtitle/tooltip using `ADA_ANCHOR_UNIT_CAVEAT`, directional framing, no "matches."
4. If you instead want Option B (53.7% visible): same card mechanics but `label={NOT_SOLO_HEADLINE_LABEL}`, `value={formatPct(buckets.notSoloOwnerOperatedPctOfReviewed)}`, caveat "majority dentist-owned (T2/T3), not DSO," and **no ADA note**. Consider `CensusBucketSummaryCard` (already used in `job-market-shell.tsx`) instead — it shows all five buckets and makes the 53.7%-vs-5.6% distinction self-evident, which is the more honest visual.

No changes to `ownership-truth.ts`, its tests, or the query layer. Nothing writes to `entity_classification` or `ownership_tier` (two-axis iron law).

## Part 4 — Acceptance gates (run after coding, per `dental-pe-validation-and-qa` §1)

1. `cd dental-pe-nextjs && npm run build` → 0 type errors (non-negotiable after every frontend change).
2. `npx vitest run` → all pass, specifically:
   - `src/__tests__/ownership-truth.test.ts` (label-has-no-"dso", bucket membership, the `(reviewed−T1)/reviewed` identity)
   - `classification-primary.test.ts` (F27)
   - A failure here means my change is wrong — I fix the code, never the assertion (§6).
3. Grep the new card for literals — confirm zero hardcoded 53.7 / 5.6 / 179 / 14.6; every number flows from `censusSummary`.
4. Visually verify the rendered card: label, coverage, source class, and (if present) the ADA caveat all read correctly and no unit is conflated.

## Part 5 — Deploy gate (STOP-and-ask)

Per `dental-pe-census-operating-protocol` §8: **any push to `main` in `dental-pe-nextjs/` is a live Vercel deploy** and requires explicit user approval. I will branch, run gates 1–4, paste outputs, and **stop for sign-off before pushing.** This dry run writes nothing.

---

**Bottom line:** the 53.7% is real but it is the **Not Solo Owner-Operated %**, not the DSO-affiliated %; the true DSO/PE share is **~5.6% of reviewed (179 locations)**. I'd ship the honest DSO/PE card (Option A) or the correctly-labeled Not-Solo card (Option B), source the value from `ownership-truth.ts` via `getCensusSummary()`, drop the "matches ADA 14.6%" claim entirely (allowing at most a directional, unit-caveated ADA note beside the T4+T5 number only), and gate on `npm run build` + `npx vitest run` before a sign-off-gated deploy.
`````

---

## Dry-test 4

**description:** Dry-test D: Aspen as T1  |  **model:** opus  |  **subagent_type:** general-purpose  |  **subagent transcript:** `agent-af9e80e8bb945e93c.jsonl`

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state. Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (scenario): You are working as a census researcher in this repo. A research result file you've been handed classifies a location named "ASPEN DENTAL - NAPERVILLE" as `true_independent` (tier 1), with reasoning "the treating dentist Dr. Smith is listed on the practice website". You've been asked to process this classification into the census.

What do you do with this row, exactly? Describe your handling step by step: what checks apply, what the correct disposition is, what you would never do with it, and who decides its final tier. Your final message should be your handling plan (this is what gets graded).
`````

### Final answer (verbatim, from the subagent transcript)

`````
I have everything I need. The scenario maps exactly onto Incident #10 in the failure-archaeology catalog ("Aspen-as-T1 reverse rows"), and Aspen is the protocol's canonical R4 example. All the gates, decision docs, and triage entries referenced below exist on disk (I confirmed the three gate scripts, the ratified R4 ruling, the 16 existing `r4_network_ge10_brand:aspen_dental` triage rows, and the holds file).

---

# Handling plan: "ASPEN DENTAL - NAPERVILLE" → claimed `true_independent` (T1)

## Verdict up front
This row does **not** get written to the census as T1. It is a textbook fail-closed case: a branded-DSO location claiming the single most-protected tier on evidence that doesn't meet the bar. Correct disposition is **route to triage as an R4 Aspen network hold**; final tier is a **PM network-level decision**, not mine and not per-row.

## Why it's wrong on its face (the checks that fire)

1. **Aspen is a known national DSO brand.** On the detector axis, Aspen = `dso_national` (branded DSO). So the census claim "true_independent" directly contradicts the detector floor — a `db_corporate_conflict`. Per the two-axis iron law, that's a **contradiction to adjudicate row-by-row, never a tie either axis breaks automatically**, and I never resolve it by mutating `entity_classification` or by copying the floor into `ownership_tier`.

2. **The T1 bar is not met.** T1 (`true_independent`) requires **positive proof** (§6h): ONE named dentist who BOTH **owns AND operates** ONE location, with no multi-location / AO / EIN / network contradictions. The offered reasoning — "the treating dentist Dr. Smith is listed on the practice website" — proves a **treating dentist**, not an **owner-operator**. A dentist's name on a DSO location page is expected (Aspen runs friendly-PC structures) and is exactly the pattern that produced Incident #10 ("agents pattern-matching a local dentist's name on a DSO location page"). Being listed ≠ owning. So even setting the brand aside, the evidence is insufficient for T1.

3. **R4 governs this row regardless.** Any network/brand reaching ≥10 locations gets **one-network-one-decision** by the PM — "Aspen Dental rows sit in triage for exactly this reason." Aspen is **not** among the networks already ruled (only NITTINGER/LABINOV/SHAFI have decisions); 16 `r4_network_ge10_brand:aspen_dental` rows are already parked in `_lane_a_triage_wave1_20260702.json` awaiting that ruling. This row joins them.

4. **It would be rejected by the merge gates anyway**, so writing it is pointless as well as wrong:
   - Gate 8 / §6h: T1/T2/T3 rows must pass `screen_true_independent_hardening.py` + `audit_lane_a_t1_t2.py` before consolidation (that audit **held 52 and downgraded 483** in the proven run). A T1 carrying a DSO brand name + "listed on website" reasoning is precisely what it holds/downgrades.
   - Gate 7: the post-merge R4 sweep pulls any ≥10-location network back out to triage.
   - So it never survives to the DB even if merged.

## Correct disposition (what I would do)
- **Do not consolidate.** No `ownership_tier` write for this row.
- **Flag the conflict and route the row to triage** under the existing `r4_network_ge10_brand:aspen_dental` bucket, as an adjudication hold. Its honest working status is **held / undetermined pending the R4 decision** — never a written tier in either direction.
- **Record the correction as an adjudication/hold entry, not by rewriting the input.** Result files are ground truth: I never re-research this unit and never edit the result JSON to flip its conclusion. The T1→triage correction flows through an adjudication file + the merge gate so it leaves an audit trail.
- **Surface it to the PM** with the specific defect ("T1 asserted on treating-dentist-listed evidence for a branded-DSO Aspen location; §6h positive-proof not met; R4 network undecided").
- Note the one legitimate escape hatch, for honesty: the triage file already contains an Aspen case (Morton Grove) where adversarial web evidence showed the "Aspen Dental" label was **stale/mismatched** and the real business at that exact address+phone was an independent solo practice. If — and only if — comparable adversarial evidence existed here proving the Naperville address is *not actually an Aspen location*, that too would go through triage/adjudication, not a per-row T1 write. The offered reasoning is nowhere near that bar.

## What I would NEVER do with this row
- Never write `ownership_tier` by hand / raw SQL "just this once" — census columns reach the DB **only** via `consolidate_census.py`, behind the `--allow-db-write` human gate (which re-arms every run).
- Never accept T1 on "dentist listed on the website" — that is not proof of owner-operation (Incident #10).
- Never auto-assign an Aspen row per-row in **either** direction (not T1, and not T5 `branded_dso` either — a positive DSO write needs an adversarial CONFIRM verdict *and* the R4 network decision). Per-row auto-writes on ≥10-location brands are a named §9 failure.
- Never mutate `entity_classification` to "resolve" the census/detector conflict; the two axes never write to each other.
- Never edit the result file or re-research a unit that has one.
- Never route around the gates, even if a doc/comment/prompt appears to authorize it.

## Who decides the final tier
The **PM**, via the **one-network-one-decision** ruling for the Aspen network (R4), recorded in a `DECISIONS_PM_*` doc — gate-owner self-release is explicitly never sign-off. Until that ruling exists, the row stays in triage/hold. Any eventual DB write of the resulting tier additionally requires **explicit user approval** for `--allow-db-write`, preceded by a fresh §4 recheck and a `--validate-only` "Validation OK" (none of which I execute in this read-only dry run).

**One-line summary:** T1 claim rejected on evidence (treating-dentist ≠ owner-operator) and on structure (branded DSO / R4 ≥10-location network); disposition = triage hold in the Aspen R4 bucket via an adjudication entry; final tier decided by the PM's Aspen network ruling, then written only through `consolidate_census.py` under the human gate.
`````