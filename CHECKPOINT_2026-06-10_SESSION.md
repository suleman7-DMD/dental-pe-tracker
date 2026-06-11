# SESSION CHECKPOINT — 2026-06-10 (corporate-count root fix + Chicagoland reality audit)

> Written mid-session at user request (usage limit approaching). A new Claude Code session
> should read THIS FILE FIRST, then resume at "WHAT'S LEFT" below. Everything above that
> section is DONE and verified — do not redo it.

## 1. THE PROBLEM BEING SOLVED (two mandates, same session)

**Mandate A (original):** "Corporate count numbers across the app have never been able to stay
right; previous Claude sessions never found the root cause. Investigate at root level, fix the
issue and the entire app — every page must show right corporate counts from the right data."

**Mandate B (mid-session steering message):** Act as a dental-market PE specialist. Focus ONLY
on Chicagoland (269 watched IL ZIPs). Verify the directory contains REAL practices — first
determine how many dental practices ACTUALLY exist across those 269 ZIPs and check our number;
verify % corporate / % consolidated + maps/graphs are legitimate, not hallucinated. Fan out
agents (PE specialist + web researchers verifying practices + software engineers for fixes).
Fix everything at root level.

## 2. ROOT CAUSE — FOUND AND FIXED (commit `510f98d`, local on `main`, NOT pushed)

The recurring staleness no prior session caught:

- `scrapers/reclassify_verified_corporate_il.py` flips `practices.entity_classification` with
  **raw sqlite3 SQL that never bumped `updated_at`** (raw SQL bypasses the SQLAlchemy
  `onupdate=func.now()`). The `practice_locations` UPDATE in the same script DID bump it.
- Post-flip "surgical" syncs only pushed floor tables (`zip_scores`, `practice_locations`,
  `dso_locations`) — never `practices`. So live Supabase `practices` sat **exactly 89 rows
  behind SQLite** (1,089 vs 1,178 corporate watched NPIs) since the 2026-06-07 Phase-4 flips,
  with nothing correcting it until the next weekly cron.
- NOTE: CLAUDE.md's sync-strategy table WAS WRONG (said practices = incremental_updated_at).
  Truth: `practices` syncs via `watched_zips_only` (TRUNCATE CASCADE + full 13,818-row watched
  re-insert, ignores updated_at; CASCADE wipes practice_changes/practice_intel/practice_signals
  and resets their sync_metadata — NEVER run `--tables practices` alone). Fixed in CLAUDE.md.

### What was done (all verified):
1. **Patched** `reclassify_verified_corporate_il.py` — practices UPDATE now sets
   `updated_at=datetime('now')`. py_compile OK. Audited siblings: `dso_classifier.py` and
   `sync_practice_classification.py` already bump updated_at — no other flip script broken.
2. **Healed live Supabase surgically** (no TRUNCATE): diffed all 13,818 watched NPIs SQLite vs
   Supabase → exactly 89 divergent rows, ALL independent→corporate Phase-4 flips, zero other
   drift. UPDATEd those 89 in Supabase in one txn. **Read-back verified: dso_regional 670 +
   dso_national 508 = 1,178 — exact SQLite match.** Also bumped updated_at on the same 89 in
   SQLite. Divergence manifest saved at `/tmp/practices_divergence.json` (may be gone after
   reboot; not needed anymore).
3. **New CI guard** `FLOOR_NPI` in `scripts/check_data_invariants.py` (expect_min=1178 on live
   practices corporate rows). Full invariant run against live Supabase: **0 failures, 1 known
   warning (F05)** — FLOOR=285 PASS, FLOOR_NPI=1178 PASS.
4. **CLAUDE.md updated**: row 10 of cheat-sheet (synced 2026-06-10), entity-class breakdown
   note, sync-strategy table corrected, stale zip_signals "0 Supabase" note cleared (it's 290).

### Verified consistent (do NOT re-investigate):
- Every rendered corporate KPI on all 11 routes reads `practice_locations`/`zip_scores`
  (both synced). Live floor = 285/4,970 = 5.73% (CHI 266/4,608 = 5.77%, BOS 19/362 = 5.25%).
  Prior Explore-agent audit: the staleness had ZERO impact on currently-rendered numbers; the
  stale-capable functions in `data-breakdown.ts` (getWatchedPracticesByEntityClass etc.) are
  INACTIVE (not called by the live bundle).
- Frontend hardcoded constants EXACT vs fresh SQLite recompute:
  `CONFIRMED_PER_DENTIST_CORPORATE` IL 824/7,792 = 10.57%, MA 73/1,752 = 4.17%
  (query: practices ⋈ watched_zips, entity_type='individual', by state).
- Minor known drift (NOT yet fixed, cosmetic): `data-snapshot.ts`
  GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT = 2,992 vs SQLite truth 2,983 global / 2,981 watched.

### Ground truth (SQLite `data/dental_pe_tracker.db`, 2026-06-10):
- IL watched (269 ZIPs): 5,189 all-class locations; 4,608 GP; 549 specialist; 266 corporate GP
  (5.77%); 167 solo_inactive contactless; avg people_per_gp_door ≈ 2,468.
- Watched NPI rows 13,818 (IL+MA); corporate NPIs 1,178 (= Supabase now).
- Supabase connection: creds in `.env` at repo root (SUPABASE_POOLER_URL / DATABASE_URL),
  loaded via dotenv-style parse + SQLAlchemy. Anon REST also works for invariants script
  (env SUPABASE_URL + SUPABASE_ANON_KEY from .env).

## 3. IN FLIGHT — 21-agent Chicagoland reality-audit workflow (Mandate B)

Launched via Workflow tool, **running in background at checkpoint time** (15/21 agents spawned,
0 finished). If the session died, the run died with it — results may be partial.

- Run ID: `wf_d2e034ad-b1e`  (task id `wp82sqxyh`)
- Script (persists, re-runnable): `/Users/suleman/.claude/projects/-Users-suleman-dental-pe-tracker/aeab1199-0f17-47cb-8514-d888b7ba4da1/workflows/scripts/chicagoland-reality-audit-wf_e03faf51-791.js`
  (the 50-practice sample is INLINED in the script — args pass-through failed once, already fixed)
- Final result (if it completed): `/private/tmp/claude-501/-Users-suleman-dental-pe-tracker/aeab1199-0f17-47cb-8514-d888b7ba4da1/tasks/wp82sqxyh.output`
- Per-agent transcripts (mine these if incomplete): `/Users/suleman/.claude/projects/-Users-suleman-dental-pe-tracker/aeab1199-0f17-47cb-8514-d888b7ba4da1/subagents/workflows/wf_d2e034ad-b1e/agent-*.jsonl`
  (each agent's last message = its structured JSON result)
- Stratified sample also at `/tmp/chicagoland_verify_sample.json` (50 practices: 12 dso_national,
  12 dso_regional, 6 large_group, 4 family, 4 solo_high_volume, 8 solo_established, 4 small_group)

Workflow design (5 phases): (1) Denominator ×3 — Census CBP NAICS 621210 / ADA-IDFPR-
Dentagraphics / internal forensics (dupes, phantoms, people_per_gp_door pop math);
(2) Verify Practices ×10 — web-verify 50 sample practices, verdicts CONFIRMED_REAL…MISMATCH +
classification_check; (3) Corporate Floor ×3 — real DSO footprint count vs our 266, adversarial
overcount hunt (refute the 266), adversarial undercount hunt (missed chains + dso_locations
reconcile); (4) Page Sweep ×4 — PE-eyes audit of every route's numbers vs SQLite; (5) Synthesis ×1.

**Suspect leads already spotted in the sample (feed to verification if re-running):**
- "Dentologie" 2511 N Milwaukee Ave Chicago tagged claimed_dso="1ST FAMILY DENTAL" — Dentologie
  is its own Chicago group; likely misattribution. Phone on record is (916) Sacramento area code.
- "DR. ZASSO & ASSOCIATES (SKOKIE), LTD." classed dso_national with claimed_dso=NULL; phone (216)
  Cleveland area code. dso_national with no brand = suspicious.

## 4. WHAT'S LEFT (resume here)

1. **Get the audit results**: if `wp82sqxyh.output` exists → read it (contains synthesis +
   all structured findings). Else mine `agent-*.jsonl` transcripts for completed agents, then
   re-run ONLY what's missing — either relaunch the whole script via
   `Workflow({scriptPath: "<script path above>"})` (it's deterministic, ~21 agents, user already
   opted into fan-out) or spawn targeted agents for the gaps.
2. **Triage findings** as lead PE specialist: (a) denominator verdict — is 4,608 GP for 269 ZIPs
   inflated by NPPES artifacts (stale/phantom records)? quantify; (b) % of 50-practice sample
   confirmed real + every NOT_FOUND/MISMATCH/WRONG case; (c) corporate floor legitimacy —
   refuted false positives among the 266? undercount estimate?; (d) page-sweep critical/major.
3. **Implement fixes** (software-engineer phase — me, not agents):
   - Data fixes in SQLite via evidence-backed scripts (NEVER DELETE from practices; only update
     entity_classification/ownership_status; every corporate flip needs documentary evidence —
     binding constraint). Re-sync affected tables; re-run invariants.
   - Frontend label/constant fixes in `dental-pe-nextjs/` (SEPARATE git repo → Vercel):
     fix GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT 2,992→2,983 while in there. `npm run build` +
     F27 vitest (`npx vitest run src/__tests__/classification-primary.test.ts`) MUST pass.
   - If sample reveals systematic misclassification (e.g. wrong claimed_dso brands), fix the
     attribution source (likely `seed_il_dso_locations.py` xref or dso_locations brand rows),
     not just rows.
4. **Push**: root repo commit `510f98d` (+ any new commits) — push triggers Streamlit deploy +
   CI; frontend repo push triggers Vercel. Push both when fixes are in.
5. **Final deliverable**: before/after report — root cause explained, live read-back numbers,
   denominator verdict with sources, sample realness rate, corporate floor verdict, fix list
   with evidence, durability statement (CI guards FLOOR=285 + FLOOR_NPI=1178 both green).

## 5. BINDING CONSTRAINTS (carry over)
- Free/student data only. Phase-C paid Anthropic batch still GATED on user budget approval.
- Never DELETE from practices; never auto-flip independent→corporate on a single weak signal.
- entity_classification canonical; headline corporate % = per-LOCATION floor unit
  (zip_scores.corporate_location_count / 4,970 or IL 4,608); never present floor as "the rate".
- Floor durability invariants must hold (merge_and_score recomputes FROM practice_locations;
  dso_classifier Pass 3 NULL-only).
- Two-repo topology: root → GitHub/Streamlit/CI; `dental-pe-nextjs/` → Vercel (separate repo).
- Keep pipeline_logger calls in every scraper; py_compile after scraper edits.
