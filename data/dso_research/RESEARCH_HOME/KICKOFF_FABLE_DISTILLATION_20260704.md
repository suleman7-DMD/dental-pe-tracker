# KICKOFF — Fable→Opus Distillation Session (skill library + plan artifacts)
**Author:** Fable (data/PM session) · 2026-07-04 · Status: **READY TO EXECUTE**
**Executes:** `PLAN_FABLE_DISTILLATION_20260703.md`. That plan's §1 (PM verdict), §2 (skill specs),
§4 (hard rules), §5 (fallback) remain binding. This kickoff updates its trigger status, read list,
scope deltas, session rules, and pre-answers the user-facing questions to the 2026-07-04 state.
**Supersedence:** live code/tests > this kickoff > the 2026-07-03 plan > older handoffs.

---

## 0. Trigger conditions — evaluated 2026-07-04

1. ✅ **MET.** Lane A merge→consolidate→sync chain is COMPLETE and read-back verified both legs
   (runbook `MASTER_RESUME_LANE_A_FLEET_20260702.md` §6m, banked commit `1006ecd`). Live Supabase =
   local SQLite exactly: 3,180 tiered locations / 6,754 tiered NPI rows / detector floor unchanged
   268 corp locations / 1,152 corp NPIs / 4,801 GP. The flagship census skill now distills a
   FINISHED, PROVEN chain — not a moving target.
2. ⚠️ **USER SELF-CHECK before starting:** weekly Fable usage headroom ≥10%. If under, wait for the
   weekly reset (plan §5 fallback applies if access ends first).
3. Run in a **FRESH session**: `cd /Users/suleman/dental-pe-tracker`. The truth-app frontend session
   may run in parallel — write surfaces are disjoint (see §4).

## 1. What changed since the 2026-07-03 plan (fold ALL of these in)

- **The sync chain is done and proven.** The census-operating-protocol skill must encode the full
  consolidate path with REAL observed outputs, not hypotheticals: pre-write backup → `--validate-only`
  → `--allow-db-write` → leg 1 `python3 -m scrapers._sync_floor_tables_only` (expect: verified row
  counts per table, "LIVE floor now: 268/4801 = 5.58%") → leg 2
  `python3 -m scrapers._sync_census_columns_practices` (expect: "Updated N rows … (0 not present)",
  "VERIFY census NPIs: Supabase=N SQLite truth=N MATCH", identical tier tallies) → independent
  Postgres read-back. §6m has the verbatim outputs — quote them as expected observations.
- **A truth-app frontend session is in flight** (charter `SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md`).
  It already shipped the frontend ownership contract `dental-pe-nextjs/src/lib/census/ownership-truth.ts`
  + truth-law tests (frontend commits `68796d6`/`61dabe2`, authored under the repo's "Codex QA" git
  identity) and three docs: `DATA_CONTRACT_TRUTH_APP_20260704.md`, `SPEC_TRUTH_APP_ROUTES_20260704.md`,
  `PURGE_LIST_LEGACY_TRUTH_CLAIMS_20260704.md`. That contract module is a CODE GATE — skills cite it,
  never restate its tables. **This distillation session OWNS the skill library** (the charter's
  deliverable 5 is satisfied by your output; note that in your final report so the truth-app session
  doesn't duplicate it).
- **Plan §2's "P1: UI Phase 0 census data contract" is OBSOLETE** (shipped, above). Replace with
  **P1′: census continuation campaign plan** — the actual hardest live problem (see §2 Q1).
- **Corrected hold accounting:** the 91 adjudication holds are INSIDE the 649 triage pool, not
  additive. Remaining census queue = 649 triage (incl. 91 holds) + ~477 undetermined-researched
  + ~610 synthetic/wave-5 rows. Recheck triage/holds against
  `data/dso_research/_census_holds_20260702.json` + `RESEARCH_HOME/PROGRESS.json`.
- **`AGENTS.md` does not exist at repo root** — any inherited read list mentioning it is wrong.
  CLAUDE.md is the always-loaded invariant layer.
- Supabase has **no review-status column** — held/undetermined/never-researched rows are all
  NULL-tier in Postgres. The frontend contract already accepts a future `census_review_status`
  (`deriveSourceClass(tier, reviewStatus?)`). Record this as a known gap, not a bug.

## 2. Pre-answered PM questions (do NOT ask the user these — fold answers into the skills)

1. **Hardest live problem:** continuing the census safely without Fable — 649 triage rows (incl. 91
   holds) needing adjudication, ~477 undetermined needing re-research or acceptance, ~610
   synthetic/wave-5 rows needing decomposition — while a weaker model resists re-researching units
   with result files, corrupting census columns, or conflating axes. P1′ targets exactly this.
2. **Fable behaviors to preserve:** verify-before-claim (numbers predicted before commands run);
   both-leg read-back after any sync; evidence-URL gates; result-files-are-ground-truth; stop on
   plan-vs-reality mismatch; unit discipline (NPI rows ≠ locations ≠ GP denominator); holds instead
   of guesses; date-stamped volatile numbers with recheck commands; banking milestones with proof.
3. **Past mistakes that cost the most:** Data-Axle synthetic records counted as practices (179-row
   purge); Evenly `parent_iusa=000000000` placeholder → 13 false corporates; ORM census-column
   sync-strip bug (silent data loss); the 875-row Supabase staleness that persisted for weeks;
   model-clamp incident (never pin a global subagent model); Aspen-as-T1 reverse rows caught by the
   §6h positive-proof gate; sessions tripping over parked MA rows. Each becomes a
   failure-archaeology entry: symptom → root cause → the gate that now prevents it.
4. **Human-gated no matter what:** any `--allow-db-write` consolidation; any Supabase sync; any
   frontend push (push = live deploy); any FLOOR/FLOOR_NPI CI re-base; any DELETE anywhere;
   reopening MA/Boston. Encode as STOP-and-ask conditions.
5. **Deliverable priority:** census continuity > sync/DB safety > data-unit discipline > frontend
   truth law > scraper safety. (Matches the plan's cut ladder.)

## 3. Final scope

**Core skills (5) under `.claude/skills/<name>/SKILL.md`** — exactly as specced in plan §2:
1. `dental-pe-census-operating-protocol` (flagship; now includes the PROVEN sync chain per §1)
2. `dental-pe-data-unit-discipline`
3. `dental-pe-supabase-sync-and-orm`
4. `dental-pe-validation-and-qa`
5. `dental-pe-failure-archaeology`

**Optional 6th (only if headroom after dry-tests):** `dental-pe-frontend-truth-law` — the charter §2
hard rules + five buckets + labeling law + source classes, citing `ownership-truth.ts` as the code
gate and the purge list as the work queue. Do not duplicate the contract module's tables.

**Plan artifacts (equal priority to skills), plan-template discipline (per-step verification command
+ expected output + hasty-model trap):**
- **P1′: census continuation campaign** — decision-gated phases over the 649 triage (holds protocol
  for the 91), ~477 undetermined, ~610 synthetic/wave-5; reuses Lane A machinery (workflow scripts,
  merge gates §6c/§6e/§6h, consolidate→sync→read-back chain) with exact commands + expected numbers.
- **P2: Rung 2 IL SoS/IDFPR scraper** (escalation ladder, from the original plan).
- **P3: Intel backfill via Batch API Haiku** (~$0.008/practice, dossier-batch machinery).

## 4. Session rules (writes)

- Write ONLY: `.claude/skills/**` + `RESEARCH_HOME/REPORT_DISTILLATION_20260704.md` (final report).
- **Git commits of those files ARE pre-authorized** (main repo, milestone commits, standard
  Co-Authored-By trailer). Nothing else: no DB writes, no Supabase sync, no deploys, no
  `dental-pe-nextjs/` edits (the truth-app session works there), no CLAUDE.md edits — if you find
  stale CLAUDE.md numbers, LIST them in the final report for the PM session to apply.
- Never encode a route around change control, evidence gates, or DB-write restrictions.
- Supersedence when sources disagree: live code/tests > newest PM protocol docs (§6m, DECISIONS,
  charter) > older handoffs (the 4-session/freeze-era docs are HISTORICAL) > git history > inference
  (label inference as inference).

## 5. Execution recipe

1. **Read (canonical set — skip broad archaeology, Fable authored most of it):** CLAUDE.md;
   `MASTER_RESUME_LANE_A_FLEET_20260702.md` (§6c/§6e/§6h/§6m minimum);
   `SESSION_PROTOCOL_FABLE_PM_20260702.md`; `DECISIONS_PM_20260702.md`;
   `DECISION_TRUE_INDEPENDENT_HEADLINE_20260703.md`; `SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md`;
   `DATA_CONTRACT_TRUTH_APP_20260704.md`; `PURGE_LIST_LEGACY_TRUTH_CLAIMS_20260704.md`;
   `PROOF_ORM_SYNC_MIGRATION_20260702.md`; code: `scrapers/consolidate_census.py`,
   `scrapers/database.py` (census cols), `scrapers/_sync_floor_tables_only.py`,
   `scrapers/_sync_census_columns_practices.py`, `scrapers/sync_to_supabase.py` (strategy table),
   `scripts/check_data_invariants.py`, `dental-pe-nextjs/src/lib/census/ownership-truth.ts`.
   `CLAUDE_ARCHIVE.md` + git log only as needed for archaeology entries.
2. **Author** the 5 skills + P1′/P2/P3. Verify every command, path, flag, and count against the repo
   before stating it; date-stamp volatile numbers with a one-line recheck command.
3. **Dry-test loop (the actual distillation):** spawn Opus subagents via the Agent tool with
   `model: "opus"` and explicit no-write instructions. Four tests: (a) "resume Lane A without
   re-researching completed units"; (b) "diagnose a hypothetical Supabase/SQLite corporate-count
   mismatch"; (c) "plan a Next.js denominator-label fix without changing code"; (d) "a researcher
   assigned Aspen Dental true_independent — what now?". Every gate Opus misses = a patch to the
   relevant skill. Budget one patch round.
4. **Final report** (`REPORT_DISTILLATION_20260704.md`): skill inventory + one-line purposes;
   loading order; what was spot-verified; what remains uncertain; maintenance-soon list; stale
   CLAUDE.md numbers found; the EXACT kickoff prompt the user should paste into future Opus
   sessions; the three confirmation tasks for the user to give Opus; and the note that charter
   deliverable 5 is satisfied by this library.
5. **Quality bar** (reject shallow skills): a zero-context Opus must be able to answer — what is
   this system, what must not break, which docs are canonical vs historical, how do I safely work
   the census, how do I prove a fix is real, when must I stop and ask the user.

## 6. Budget ladder

Target ≤8% of weekly usage. If tight, cut in this order: optional 6th skill → P3 → P2 → merge
skills 2+4 into skill 1 → (last resort) ship only `dental-pe-census-operating-protocol` (plan §5:
that one artifact alone carries the highest-damage surface).

## 7. Kickoff prompt (user pastes this into the fresh session)

> Read `data/dso_research/RESEARCH_HOME/KICKOFF_FABLE_DISTILLATION_20260704.md` and execute it
> end-to-end, autonomously. You are the departing principal architect distilling this repo's
> judgment into `.claude/skills/` so Opus-class models can continue safely. Writes only per its §4
> (skills + final report; milestone commits pre-authorized; everything else read-only — no DB
> writes, no sync, no deploys, no frontend edits). Author the 5 core skills + P1′/P2/P3 plan
> artifacts, run the Opus dry-test loop with subagents and patch every missed gate, then write the
> final report including the exact future-Opus kickoff prompt. Do not ask me the five PM questions —
> they are pre-answered in §2. Budget ≤8% of weekly usage; follow the §6 cut ladder if tight.
