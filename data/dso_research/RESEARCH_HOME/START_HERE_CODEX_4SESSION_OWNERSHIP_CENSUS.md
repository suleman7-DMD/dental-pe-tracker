# 🧭 START HERE (MAIN AO seat) — Codex-Orchestrated 4-Session Chicagoland Dental Ownership Census

> **RETRIEVAL ANCHOR (read this if a fresh session was told something like):**
> *"Previously I was working with **Codex orchestration + 4 Claude sessions** on my dental PE app to **hand-verify the ownership of each of the ~4,400 Chicagoland practices**. Can you find the memory / context / reference files for that?"*
>
> **This is the MAIN AO session's memory file** — the deep record of the Main AO / Lane-1 seat, plus a
> full picture of all four seats so it stands alone. Keywords for grep: `codex`, `4 sessions`, `4400`,
> `4439`, `hand verify`, `ownership census`, `Main AO`, `Gate Owner`, `QA`, `Fleet B`, `Wave 4`,
> `consolidation frozen`, `ready_for_validation`.
>
> ### 🔗 Two START_HERE files exist — they reconcile, read whichever you land on:
> - **`START_HERE_CODEX_4SESSION_ORCHESTRATION.md`** — authored by the **Gate Owner** seat. It is the
>   **shared cross-role INDEX/overview** that ties together all five per-role handoffs. For the single
>   canonical entry point and the manifest-bucket truth (310/167/74/7/87), start there.
> - **`START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md`** (this file) — authored by the **Main AO** seat. It
>   documents the Main AO role most deeply (the AO/network evidence work, Lane-2 backfill, the LABINOV
>   addendum) and mirrors the same shared facts. The user asked each of the 4 sessions to leave its own
>   equivalent doc — this is Main AO's.
>
> Both were written 2026-06-22, both re-verified the same frozen invariants intact, and they agree. Each
> seat's narrowest, most-authoritative resume doc is its `HANDOFF_*` file (see §4).
>
> **Author:** Main AO session (Claude, Opus 4.8). **Written:** 2026-06-22. **Scope:** Chicagoland / IL only; Boston/MA parked.

---

## 0. TL;DR — what this operation is

We are **hand-verifying the ownership of every general-dentistry practice location in the Chicagoland
watched-ZIP universe** — **4,439 IL GP locations** (269 IL watched ZIPs; Boston/MA's 21 ZIPs / 362 GP
locations are **PARKED**). The goal is to replace the old, admittedly-wrong **5.43%/5.61% "corporate
floor"** (a name/EIN detector that misses friendly-PC and local-name DSOs) with an **evidence-earned
ownership census**, one location at a time, with a documentary artifact behind every classification.

The work is run by **five collaborators**: **Codex (the architect/orchestrator)** + **four Claude Code
sessions** (Main AO, Gate Owner, QA, Fleet B). **The human user is the relay** — every instruction I
("Main AO") received was actually **Codex** speaking; the user copy-pastes Codex's instructions into
each Claude session and pastes the Claude replies back to Codex. Codex verifies things on the backend,
owns the database mutations, and decides when (if ever) to "consolidate" the earned classifications into
the live app.

**Right now: consolidation is FROZEN.** Every Claude session is in **evidence-only / files-only mode**.
No session writes to the database, the canonical manifest, the "310" ready file, or the LEDGER/PROGRESS
census state. The highest status any evidence row may reach is **`ready_for_validation`**, never "final."

---

## 1. The collaboration model (who talks to whom)

```
                          ┌─────────────────────────────────────────────┐
                          │  CODEX  (the architect / orchestrator)       │
                          │  - designs the protocol, criteria (AB1–AB12) │
                          │  - owns the DB + canonical manifest mutations│
                          │  - runs the reset / consolidate_census.py    │
                          │  - decides when to "consolidate" (frozen now)│
                          └───────────────▲───────────────┬─────────────┘
                                          │               │
                       Claude replies     │               │  copy-pasted instructions
                       (pasted back)       │               ▼
                          ┌───────────────┴───────────────────────────────┐
                          │  USER  (human relay / courier between Codex    │
                          │        and the 4 Claude sessions)              │
                          └───┬───────────┬───────────┬───────────┬────────┘
                              │           │           │           │
                  paste in ↓  │           │           │           │  ↓ paste in
              ┌───────────────▼─┐ ┌───────▼────────┐ ┌▼──────────┐ ┌▼─────────────┐
              │ SESSION 1        │ │ SESSION 2       │ │ SESSION 3 │ │ SESSION 4     │
              │ MAIN AO (Lane 1) │ │ GATE OWNER      │ │ QA        │ │ FLEET B (L3)  │
              │ evidence: AO /   │ │ coordinator /   │ │ adversar- │ │ Phase-C web   │
              │ network + Lane-2 │ │ normalizer /    │ │ ial review│ │ verify + intel│
              │ backfill +       │ │ dispatcher;     │ │ only;     │ │ mining + ZIP  │
              │ focused addenda  │ │ NO evidence     │ │ writes    │ │ sweeps        │
              │                  │ │ gathering       │ │ VERDICTs  │ │               │
              └────────┬─────────┘ └───────┬─────────┘ └────┬──────┘ └──────┬────────┘
                       │                   │                │               │
                       └───────────────────┴────────────────┴───────────────┘
                                           │
                         FILE-BASED COORDINATION LAYER (the sessions never talk
                         directly — they read/write files in data/dso_research/):
                         REQUEST_* · DONE_* · BLOCKED_* · VERDICT_* · HEARTBEAT_*
```

**Key truth:** the four Claude sessions **coordinate only through files on disk**, never through chat.
Agent chat summaries are explicitly **not evidence** — only the written on-disk file counts. Codex (via
the user) tells each session what to do; each session writes its output file; the next session reads that
file. This is what lets four sessions run in parallel without colliding.

---

## 2. The four Claude session roles (detailed)

### SESSION 1 — MAIN AO  (Lane 1)  ← **this is the session that wrote this file**
- **Job:** active evidence gathering. Originally the **Authorized-Official (AO) / network wave**: find
  multi-location ownership by federally-observed shared Authorized Officials and corroborate each with a
  documentary artifact. Later: bounded **Lane-2 non-AO backfill** and **focused single-issue addenda**
  that Gate/QA request.
- **Core standard it enforces:** *AO reach is a SIGNAL, not proof.* A shared AO across NPIs is a
  high-value multi-location **candidate**, never ownership proof by itself. It becomes
  `dentist_multi`/`stealth_dso`/`branded_dso` ONLY with a documentary corroborator (group website, owner
  bio, shared legal entity, exact-address locator, PE/MSO filing). Highest emitted status =
  `ready_for_validation`.
- **DSO = STRUCTURE (the taxonomy rule it helped fix):** PE backing is **orthogonal** to DSO tier. A
  brand is `branded_dso`/`stealth_dso` if it has an **MSO / management company / platform / DSO-brand
  structure**, even if `pe_backed=false` (e.g. Dental Dreams = family-owned + KOS Services MSO =
  `branded_dso`, no PE). Downgrade to `dentist_multi` only when there is **no** MSO/platform evidence.
- **Writes:** evidence files only under `data/dso_research/`. **No DB writes. No consolidation.**
- **What this session has actually delivered** (see §4 for the file list):
  1. The AO/network evidence waves (top-8 AOs, then reach≥5 wave-2 = 14 networks / 84 locations),
     the runner `scrapers/ao_network_evidence.js`, the QA-normalized siblings, the schema bridge,
     the taxonomy-correction record, and the cross-session `_WATCH_OUT_*` notes.
  2. **Wave-4 Lane-2 non-AO backfill** (25 rows: 13 locator_exact + 12 practice_intel) →
     `wave4_lane2_non_ao_backfill25_evidence_20260621.json` (+ self-QA). Net effect later normalized by
     Gate to **+1 net-new corporate door** (Schock Dental → Dentologie River North).
  3. **Wave-4 QA-HOLD-1 LABINOV operating-status (AB7) re-scan** →
     `wave4_hold1_labinov_operating_status_rescan_20260622.json`. Resolved the carry-forward hold:
     target `fd93e6934ac6c59c` (Destiny Dental — Oak Park, 1 Chicago Ave 60302) **confirmed OPEN**
     (closed flag = false positive); the 7 `ao:LABINOV_BORIS` D2-shell rows → `hold_operating_status`
     (no open-door confirmation, but no transcribed closure source either); plus a network-identity
     correction (fd93 is actually the `ao:WILSON-ADELEKE_SIMONE` sibling network, not a literal LABINOV
     member). **This is where this session left off — task complete, then told to "stand down."**

### SESSION 2 — GATE OWNER
- **Job:** **coordinator / normalizer / dispatcher ONLY. Does NOT gather evidence and does NOT launch
  evidence fleets.** Ingests the evidence files produced by Main AO + Fleet B, normalizes each row
  against the criteria (AB1–AB12 + DSO=STRUCTURE + the 14-item checklist), and **partitions** rows into
  buckets (`merge_eligible_new`, `corroborates_existing_ready`, the various `hold_*`, `rejected`,
  `refuted`, `qa_attention_current_ready`).
- **Owns the task board + the file-based dispatch:** writes `REQUEST_*` files to ask Main AO or Fleet B
  for focused work, writes `AUTH_*` files to authorize the next Fleet B batch, and writes the
  `REQUEST_QA_REVIEW_*` file that unblocks QA.
- **Did the wave-1 RESET** (cleared the polluted 349 candidate `ownership_tier` rows → 0; LEDGER → 1
  header line; PROGRESS → 0/4439 reviewed) and is building/holding the **canonical manifest**.
- **Hard rule:** **never mutates** the DB / canonical manifest / 310 ready file / LEDGER / PROGRESS. All
  partitions are new files. **No manifest merge until QA returns PASS** *and* the user explicitly
  authorizes consolidation.

### SESSION 3 — QA
- **Job:** **independent adversarial review. Review-only.** Waits for the Gate Owner's
  `REQUEST_QA_REVIEW_*` file, then reviews only the written evidence + the Gate's normalized partition
  and writes a **`VERDICT_*` file** (PASS / PASS_WITH_HOLDS / MUST_FIX / FAIL).
- **Checks:** no AO-only promotion; no brand-substring-only promotion; every promoted row has durable
  on-disk evidence; T4/T5 carries a DSO=STRUCTURE rationale; `pe_backed` treated as orthogonal;
  `true_independent` is **earned**, never defaulted; closed/relocated subject-door scans applied;
  same-door / same-phone duplicate hazards held or resolved; protected networks held; sidecars preserved.
- **Always includes a zero-write proof** in each verdict: DB md5, ownership_tier counts, LEDGER line
  count, PROGRESS reviewed/undetermined. **Never** performs or requests consolidation.

### SESSION 4 — FLEET B  (Lane 3)
- **Job:** **bounded Phase-C web verification** of the hard-signal leads (ranks worked in batches of 50
  from a 158-lead pool), plus its standing lanes: `practice_intel` mining, exact-address DSO-locator
  evidence, and zero-corp ZIP sweeps.
- **Standard:** real web verification with **transcribed source URLs**; **exact-address match mandatory**
  for any DSO-locator promotion; brand word alone / Data-Axle parent alone / AO reach alone are **not
  enough**. Protected networks and Affordable/ClearChoice scope questions are holds. Ceiling =
  `ready_for_validation`.
- **Gated by authorization:** may not start the next rank batch (e.g. 51–100) until the Gate Owner writes
  the matching `AUTH_FLEETB_*` file, and only after QA finds no systemic defect in the prior batch.
- **Lane discipline:** must NOT target the AO networks Main AO has claimed; overlaps with the current 310
  are **corroborations, not net-new additions**.

### CODEX — the architect (not a Claude session; the user relays it)
- Designs the protocol and the criteria (AB1–AB12, the AB7 operating-status rule, AB9 network-release
  rule, AH3 in-session-transcription rule). Owns `consolidate_census.py` and all DB/manifest mutations.
  Ran the reset. Decides when to lift the consolidation freeze. **Every prompt the user pasted to Main AO
  was Codex orchestrating.**

---

## 3. The hard locks / frozen invariants (every session obeys these)

These are the non-negotiables. If any command would violate one, the session **stops and writes a
`BLOCKED_*` file** instead.

1. **Consolidation is FROZEN.** No `consolidate_census.py --allow-db-write`. No `--allow-db-write` of any
   kind. The freeze lifts **only** when the **user types the exact phrase `consolidate approved manifest`
   to the Gate Owner seat** — that, and only that, authorizes the Gate Owner to run the DB write on the
   310-row ready file. No other seat ever executes consolidation, and no agent should run it on its own
   initiative. Until the user types it, every session is files-only.
2. **No mutation of:** the SQLite DB, the canonical manifest, the 310 ready file, `RESEARCH_HOME/LEDGER.jsonl`,
   `RESEARCH_HOME/PROGRESS.json`, or the `ownership_tier` / `entity_classification` / `ownership_status`
   columns.
3. **Reset invariant must stay true** (re-attest every session):
   - `practice_locations.ownership_tier IS NOT NULL` = **0**
   - `practices.ownership_tier IS NOT NULL` = **0**
   - `RESEARCH_HOME/LEDGER.jsonl` = **1 line** (header only)
   - `PROGRESS.json` reviewed = **0**, `undetermined_unreviewed` = **4439**
   - **DB md5 baseline = `0dec26135bb4d6ee490dc16cfe892ca6`**  (note the `…dc16…`; a secondary
     criteria file had a `…dc26…` typo — the verified baseline is `…dc16…`)
4. **Canonical manifest is read-only:** `data/dso_research/consolidation_candidate_manifest_20260621.json`.
5. **Current "310" ready file is read-only:** `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json`
   (310 rows of `ready_for_validation` classifications — the standing candidate set).
6. **No broad AO reach=2 long tail. No new AO fan-out. No deterministic Fleet B re-mining.**
7. **AO reach is a discovery signal, never proof.**
8. **DSO tier requires STRUCTURE** (MSO/management/platform/brand). PE backing is orthogonal.
9. **Preserve all sidecar metadata** (operator/family/brand/legal-entity/evidence-chain/stale-closed
   fields) — never flatten it away.
10. **Boston/MA is PARKED** — do not census, classify, promote, or delete MA rows; filter them from view.
11. **Protected networks** (held unless already explicitly released in the manifest): **SHAFI, BELKIC,
    NITTINGER, AQEL, BRUNETTI, SWEIS, LABINOV, RAMAHA.** Affordable Dentures + ClearChoice are held out of
    the GP floor pending a user scope decision.

---

## 4. Where everything lives (the reference-file map)

**Main reference home:** `data/dso_research/RESEARCH_HOME/`  ← this file is here.

| Purpose | Path |
|---|---|
| **THIS master memory file** | `data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md` |
| Census protocol + master plan | `RESEARCH_HOME/CENSUS_PROTOCOL.md`, `RESEARCH_HOME/MASTER_PLAN.md`, `RESEARCH_HOME/README.md` |
| Per-role handoffs (one per session) | `RESEARCH_HOME/HANDOFF_{CODEX_COORDINATOR,MAIN_AO,GATE_OWNER,QA,FLEET_B}_20260621.md` |
| Running session log | `RESEARCH_HOME/SESSION_LOG.md` |
| Census heartbeat (read on resume) | `RESEARCH_HOME/PROGRESS.json` (reviewed 0 / 4439) |
| Append-only census ledger | `RESEARCH_HOME/LEDGER.jsonl` (1 header line; schema inside) |
| Wave-1 candidate quarantine (reversible) | `RESEARCH_HOME/{LEDGER,PROGRESS}_wave1_candidate_quarantine_20260621.*`, `data/dso_research/wave1_active_ownership_export_20260621.json`, `data/dental_pe_tracker.db.pre_reset_bak_20260621` |
| **Canonical manifest (read-only)** | `data/dso_research/consolidation_candidate_manifest_20260621.json` |
| **310 ready file (read-only)** | `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` |
| Criteria / gate bar (AB1–AB12) | `data/dso_research/ownership_manifest_QA_wave4_pre_criteria_20260621.json` (+ `…preQA_criteria…` secondary; reconciled in `_wave4_20260621/wave4_criteria_reconciliation_20260621.json`) |
| Per-session active-lane claims | `data/dso_research/_active_lane_{main,qa_new_session,evidence_fleet_b,reset_consolidation_gate}_20260621.md` |
| Cross-session warnings | `data/dso_research/_WATCH_OUT_for_other_sessions_20260621.md`, `_GLOBAL_priorities_correction_20260621.md`, `_RIGOROUS_REALIGNMENT_20260621.md` |

**Wave 4 working directory:** `data/dso_research/_wave4_20260621/`
- Coordination: `_WAVE4_COORDINATION_PLAN_20260621.md`, `_WAVE4_INTAKE_REGISTER_20260621.md` (the
  Gate Owner's running log — best single status read), `wave4_criteria_reconciliation_20260621.json`
- Autonomous coordination layer: `_wave4_20260621/autonomous/` — `AUTONOMOUS_COORDINATION_PROTOCOL_*.md`,
  `AUTONOMOUS_TASK_BOARD_*.json`, the 4 `*_AUTONOMOUS_INSTRUCTIONS_*.md` (one per role), the `REQUEST_*`,
  `DONE_*`, `AUTH_*`, and `VERDICT_*` files.
- Work packets (the closed Wave-4 universe): `wave4_packet_lane1_conflicts.json` (74),
  `wave4_packet_lane2_backfill.json` (87), `wave4_packet_lane3_hardleads.json` (158).
- Evidence outputs: `wave4_lane1_conflicts_ao_backfill_evidence_20260621.json` (Main AO),
  `wave4_lane2_non_ao_backfill25_evidence_20260621.json` (Main AO, +self-QA),
  `wave4_hold1_labinov_operating_status_rescan_20260622.json` (Main AO — the LABINOV addendum),
  `wave4_lane3_phasec_top50_evidence_20260621.json` + `wave4_lane3_phasec_51_100_evidence_20260622.json`
  (Fleet B, +self-QA).
- Gate normalizations: `wave4_gate_normalized_partition_20260621.json`,
  `wave4_gate_normalized_lane2_partition_20260622.json`, `wave4_gate_rollup_status_20260622.json`.
- QA verdicts: `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json`,
  `autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json`.

---

## 5. Current state of the operation (as of 2026-06-22)

**Wave 4 = "evidence-closure sprint."** A bounded pass to attach durable artifacts to the candidate
universe **without** mutating anything. Status:

- **Initial partition** (Lane-1 conflicts 96 + Fleet-B Phase-C top-50): Gate-normalized → QA
  **PASS_WITH_HOLDS**, no systemic defect. **19 net-new merge-eligible candidates** at
  `ready_for_validation` (17 T3 dentist_multi: DentalTown ×9 + Precision ×8; 2 T5 branded_dso). T3 is
  *consolidated but NOT DSO/PE* and does **not** lift the legacy corporate floor.
- **Lane-2 non-AO backfill** (Main AO, 25 rows): Gate-normalized → QA **PASS_WITH_HOLDS**, 0 MUST_FIX.
  **+1 net-new corporate door** (Dentologie River North) — independently QA-verified, not overstated;
  12 corroborations (no floor lift); 2 earned `true_independent`; rest held/refuted.
- **QA-HOLD-1 (LABINOV AB7 operating-status):** **RESOLVED** by Main AO's re-scan addendum (target
  `fd93e6934ac6c59c` confirmed OPEN → keep_ready; 7 D2 shells → hold_operating_status).
- **Fleet B ranks 51–100:** authorized + **DONE** (50 rows; 2 net-new T5 merge-eligible — Grove Dental
  / NADG-Abry, and Advanced Family Dental / Great Lakes-Shore). **Awaiting fresh Gate normalization +
  independent QA** before anything is accepted.
- **Open policy holds awaiting the USER:** (a) Affordable/ClearChoice GP-scope decision; (b) lifting the
  consolidation freeze; (c) any protected-network release; (d) 3 legacy-corporate false-positive suspects
  frozen pending review.

**Aggregate so far:** ~**22 net-new census candidates at `ready_for_validation`**; **concrete legacy
floor lift = +1 (Dentologie only)**. **Nothing has been merged. Consolidation remains FROZEN.** Freeze
re-attested intact at every step (DB md5 `0dec26135bb4d6ee490dc16cfe892ca6` · LEDGER 1 line · PROGRESS
undetermined 4439 · ownership_tier 0/0).

**Immediate next action when work resumes:** Gate Owner normalizes the Fleet B 51–100 output → writes a
`REQUEST_QA_REVIEW_*` → QA writes a verdict. Then the whole Wave-4 result waits for the user to decide on
the open policy holds and whether to authorize consolidation.

---

## 6. HOW TO RESUME — re-opening the four sessions + Codex

When you come back with a fresh context, here is exactly how to get each session running again. The
**user is the relay**: open four Claude Code terminals in `/Users/suleman/dental-pe-tracker`, and have
**Codex** issue the per-session boot prompt (or paste the prompts below, which point each session at the
files it must read first).

**Universal preamble for every session (always true):**
> Scope = Chicagoland/IL only; Boston/MA parked. Files-only evidence mode. **No DB writes, no
> `--allow-db-write`, no manifest/310/LEDGER/PROGRESS mutation.** Reset invariant must hold: DB md5
> `0dec26135bb4d6ee490dc16cfe892ca6`, LEDGER 1 line, PROGRESS undetermined 4439, ownership_tier 0/0.
> Ceiling = `ready_for_validation`, never final. Read this file first:
> `data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md`.

| Session | Boot prompt to paste (after the preamble) | Reads first |
|---|---|---|
| **Main AO** (this session's replica) | "You are the **Main AO session (Lane 1)**. Resume evidence-only work. Do no broad AO reach=2 and no new fan-out. Only act on a focused `REQUEST_*` addendum from Gate or QA; otherwise stand down. Last completed: Wave-4 Lane-2 backfill + the QA-HOLD-1 LABINOV operating-status addendum." | `RESEARCH_HOME/HANDOFF_MAIN_AO_20260621.md`, `_active_lane_main_20260621.md`, `_wave4_20260621/autonomous/MAIN_AO_AUTONOMOUS_INSTRUCTIONS_20260621.md` |
| **Gate Owner** | "You are the **Gate Owner** (coordinator/normalizer/dispatcher; no evidence gathering). Resume by normalizing the latest un-normalized evidence file (Fleet B 51–100), then request a fresh QA verdict. Never mutate DB/manifest/310/LEDGER/PROGRESS." | `RESEARCH_HOME/HANDOFF_GATE_OWNER_20260621.md`, `_wave4_20260621/_WAVE4_INTAKE_REGISTER_20260621.md`, `_wave4_20260621/autonomous/GATE_OWNER_AUTONOMOUS_INSTRUCTIONS_20260621.md` |
| **QA** | "You are the **QA session** (independent adversarial review, review-only). Wait for the Gate Owner's next `REQUEST_QA_REVIEW_*` file, then review only the written files and emit a `VERDICT_*` with a zero-write proof." | `RESEARCH_HOME/HANDOFF_QA_20260621.md`, `_active_lane_qa_new_session_20260621.md`, `_wave4_20260621/autonomous/QA_AUTONOMOUS_INSTRUCTIONS_20260621.md` |
| **Fleet B** (Lane 3) | "You are the **Fleet B session** (Phase-C web verification + intel mining + ZIP sweeps). Your 51–100 batch is DONE and awaiting QA. Do not start the next batch until the Gate Owner writes a new `AUTH_FLEETB_*` file." | `RESEARCH_HOME/HANDOFF_FLEET_B_20260621.md`, `_active_lane_evidence_fleet_b_20260621.md`, `_wave4_20260621/autonomous/FLEET_B_AUTONOMOUS_INSTRUCTIONS_20260621.md` |
| **Codex** | (architect) "Resume orchestrating the 4-session census. Manifest stays read-only; consolidation stays frozen until you explicitly authorize it. Drive the next step: Gate normalizes Fleet B 51–100 → QA verdict → surface the open policy holds to the user." | This file + `RESEARCH_HOME/HANDOFF_CODEX_COORDINATOR_20260621.md` |

**Fastest way for a future you to relocate this whole thing from a cold start:**
```bash
cat /Users/suleman/dental-pe-tracker/data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md
# or, if you forgot the path:
grep -rl "Codex-Orchestrated 4-Session" /Users/suleman/dental-pe-tracker/data/dso_research/
ls -t /Users/suleman/dental-pe-tracker/data/dso_research/_wave4_20260621/_WAVE4_INTAKE_REGISTER_*.md   # freshest status log
```
There is also a repo-root pointer (`RESUME_CODEX_4SESSION_CENSUS.md`) and a pointer note in the project
`CLAUDE.md`, so a fresh session that auto-loads `CLAUDE.md` will be told to come here.

---

## 7. Glossary of the operation's vocabulary

- **AB1–AB12** — the gate-owner acceptance bar (durable evidence, no AO-only / no brand-substring-only
  promotions, etc.). **AB7** = operating-status rule (a row must have a fresh transcribed open-door check;
  confirmed closed/relocated ⇒ exclude even if released). **AB9** = network-release authorization. **AB10**
  = Webster/whole-network adjudication. **AH3** = no retrospective assertion (URL transcription must happen
  in the current session).
- **Tiers (census axis):** `true_independent` (T1, earned) · `single_loc_group` (T2) · `dentist_multi`
  (T3 — dentist-owned multi-location, *consolidated but not DSO/PE*) · `stealth_dso` (T4) · `branded_dso`
  (T5) · `institutional` (T6) · `undetermined`.
- **Two headline metrics (user ruling):** **Consolidated** = T2+T3+T4+T5; **DSO/PE** = T4+T5 only. A
  dentist-owned brand with no PE is Consolidated but NOT DSO/PE.
- **friendly-PC / MSO structure:** a licensed professional corporation (the dentist-owned wrapper) managed
  by a management company (the MSO/DSO). Shared Authorized Official across many PCs = the classic MSO
  signature (e.g. Boris Labinov, non-dentist CFO of L2 Management, AO across 7 Destiny Dental PCs).
- **"310"** — the 310-row `_ready_to_validate_wave3_fixed_20260621.json` standing candidate set.
- **`ready_for_validation`** — the ceiling status. Means "evidence is sufficient for Codex's validator to
  consider," NOT "classified/final." Only Codex + an explicit user go can make anything final.
- **No external anchor rule:** do NOT anchor the "true" consolidated % to ADA 14.6% or any outside number.
  The 5.43%/5.61% detector floor is a *starting point being corrected*, not the answer. Always compute %
  FROM the census WITH `coverage_pct`, and label reviewed-rate vs whole-universe-floor separately.

---

*End of master memory file. If you changed anything material, append a dated note to `RESEARCH_HOME/SESSION_LOG.md` and update `PROGRESS.json` — but only ever as files; the consolidation freeze and the reset invariant in §3 stay in force until Codex + the user lift them.*
