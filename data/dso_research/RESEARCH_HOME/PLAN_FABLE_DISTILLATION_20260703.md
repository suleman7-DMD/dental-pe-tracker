# PLAN — Fable→Opus/Sonnet Distillation (skill library + plan artifacts)
**Author:** Fable (PM) · 2026-07-03 · Status: ~~PARKED~~ → **TRIGGERED 2026-07-04** — trigger
condition 1 (merge→consolidate→sync chain complete) is MET (runbook §6m). Execute via
**`KICKOFF_FABLE_DISTILLATION_20260704.md`**, which updates this plan's read list, scope (P1 is
obsolete → P1′ census continuation), session rules, and pre-answers the user questions. §§1–5
below remain binding where the kickoff doesn't override.
**Context:** User loses Fable-class access when weekly usage hits 100% (currently ~60%); Opus/Sonnet
carry the repo afterward. Goal: convert Fable's repo-specific judgment into artifacts that stop
weaker models from introducing the failure modes the user has repeatedly seen (plan drift, invented
implementations, loop-stuck debugging, data-integrity damage).

## 0. Trigger conditions (all must hold before running this)
1. Lane A census fleet drained AND the merge→consolidate→sync chain completed (or formally paused
   with a stable runbook state). Distilling before then = distilling a moving target; the flagship
   census skill would be stale within days and we'd pay twice.
2. Weekly usage has ≥8–10% headroom remaining. If not, SKIP — see §5 fallback.
3. Run in a FRESH session (this repo, `cd /Users/suleman/dental-pe-tracker`) so fleet monitoring
   here is not disturbed. Repo read-only except `.claude/skills/` + one report doc in RESEARCH_HOME.

## 1. PM verdict on the Codex-proposed mega-prompt (16 skills, 5 phases)
- **Directionally right, 3× too big.** Codex's own narrowing (5 skills, then dry-test, then patch)
  is the correct shape. Adopt that, not the 16-skill marathon.
- **The most durable distillation is already done and is NOT markdown.** This repo's real defense
  is gates enforced in code: `consolidate_census.py` evidence-URL validation + `--validate-only`
  ceiling, CI invariant guards (`check_data_invariants.py` FLOOR/FLOOR_NPI expect_min), merge-gate
  scripts, fail-closed tier rules, pre-write backups, read-back verification. A hasty model can
  ignore a skill; it cannot ignore a validator that exits 1. **Rule: any judgment that can be a
  code gate becomes a code gate; skills only carry procedure + when-to-stop.**
- **CLAUDE.md outranks skills for invariants.** Skills load only when trigger descriptions match;
  CLAUDE.md always loads. Hard invariants (floor untouched, MA parked, unit discipline, never
  DELETE practices, denominator rules) stay in CLAUDE.md. Skills carry runbook procedure.
- **The single best idea in the thread:** the dry-run feedback loop — after authoring, make Opus
  run no-write test tasks against the skills; every gate it misses = a patch to the skill BEFORE
  Fable access ends. That loop is the actual distillation. Keep it.
- **Oversold claim to ignore:** "skills make Opus perform near Fable level." They don't add
  capability; they prevent known failure modes. Set user expectation accordingly.

## 2. Scope: FIVE skills (adapted from Codex's shortlist) + plan artifacts
Under `.claude/skills/<name>/SKILL.md`, trigger-rich descriptions, imperative runbook voice,
copy-pasteable commands WITH expected output, stop conditions, "common hasty-model failure" +
"minimum proof before continuing" sections:

1. **dental-pe-census-operating-protocol** — the flagship. Two-axis separation (census tier vs
   detector floor), tier rubric + §6h T1 positive-proof rule, result-files-are-ground-truth /
   never re-research, merge gates (§6c/§6e/§6h), holds protocol, consolidate path
   (backup → validate-only → allow-db-write), dual sync legs + read-back, resume mechanics
   (point to MASTER_RESUME runbook as canonical, don't duplicate its tables).
2. **dental-pe-data-unit-discipline** — NPI rows vs locations vs GP denominators vs census rows;
   the numbers cheat-sheet with recheck SQL; "never say practices for NPI counts"; floor ≠ true
   consolidation rate; band presentation rules.
3. **dental-pe-supabase-sync-and-orm** — strategy table, TRUNCATE CASCADE trap (never `--tables
   practices` alone), census-column ORM strip bug history, surgical scripts
   (`_sync_census_columns_practices`, `_sync_practices_changed_rows` does NOT carry census cols),
   mandatory both-leg read-back, MIN_ROWS_THRESHOLD floors.
4. **dental-pe-validation-and-qa** — exact acceptance gates: `npm run build`, F27 vitest, invariant
   script, SQL count reconciliation, evidence-file requirement for any demotion/re-base, "a step is
   done only when its verification output is pasted."
5. **dental-pe-failure-archaeology** — chronology with the lesson each cost: Data-Axle synthetics
   purge, false-corporate demotions (parent_iusa placeholder), duplicate locations, F32 hygienist
   leak, sync drift/staleness, ORM census-strip, model-clamp incident (never global subagent pin),
   Aspen-as-T1 reverse rows. Format: symptom → root cause → the gate that now prevents it.

**Plus (equal priority to the skills): pre-written implementation plans** for the known upcoming
work, using the plan-template discipline (complete code where possible, exact file lists, per-step
verification command + expected output, per-step "hasty-model trap" callout):
- P1: UI Phase 0 census data contract (census_status, network registry, signal-vector persistence,
  stacked ownership truth bar per REVIEW_TRUE_INDEPENDENT_HARDENING §8).
- P2: Rung 2 IL SoS/IDFPR scraper (escalation ladder).
- P3: Intel backfill via Batch API Haiku (dossier-batch machinery, ~$0.008/practice).
The user's stated pain is Opus failing to follow implementation plans — Fable-authored plans with
verification gates + an executing-plans discipline skill is the direct mitigation, higher ROI than
more generic skills.

Optional cheap add-ons (only if headroom): adapt the 4 generic Reddit-OP skills (executing-plans,
spec-fidelity, gated-scope, fact-discipline) — small, mostly boilerplate, encode STOP-on-mismatch.

## 3. Execution recipe (for the future session)
1. Skip Codex's Phase-1 archaeology for content Fable already authored — cite canonical docs
   instead of re-reading everything (CLAUDE.md, MASTER_RESUME_LANE_A_FLEET, SESSION_PROTOCOL,
   DECISIONS_PM, REVIEW/HANDOFF hardening docs). Read only what's changed since.
2. Author the 5 skills + 3 plans. Verify every command/path/count against the repo; date-stamp
   volatile numbers with a recheck command.
3. Post-merge numbers pass: refresh CLAUDE.md stale counts (deals 2,827 etc.) so skills don't
   inherit drift.
4. Dry-test loop with an Opus subagent (no writes): (a) "resume Lane A without re-researching
   completed units"; (b) "diagnose a Supabase/SQLite corporate-count mismatch"; (c) "plan a
   denominator-label fix"; (d) "a researcher assigned Aspen Dental true_independent — what now?"
   Patch every missed gate. Budget one patch round.
5. Final report: skill inventory, loading order, the exact Opus kickoff prompt, maintenance-soon
   list.
Budget target: ≤8% of weekly usage. If dry-tests threaten the cap, cut skills 4→merge into 1, and
keep the flagship + unit-discipline + sync skills intact (highest damage surfaces).

## 4. Hard rules for that session (carry over)
Files-only outside `.claude/skills/`; no DB writes, no sync, no deploys, no commits unless user
asks; never encode a route around change control; supersedence order = live code/tests > newest PM
protocol docs > older handoffs > git history > inference (label inference).

## 5. Fallback if usage runs out before this executes
We are NOT starting from zero: CLAUDE.md + MASTER_RESUME runbook + SESSION_PROTOCOL + DECISIONS +
evidence files + code gates already encode most load-bearing judgment. An Opus session that reads
CLAUDE.md and obeys the runbooks inherits ~80% of the protection. The skills are compression +
trigger-routing + stop-conditions on top. If forced to choose ONE artifact, write skill #1
(census-operating-protocol) only.
