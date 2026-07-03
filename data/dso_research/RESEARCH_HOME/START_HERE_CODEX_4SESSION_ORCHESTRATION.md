# 🧭 START HERE — Codex-Orchestrated 4-Session Chicagoland Ownership Census

> **THIS IS THE MEMORY FILE.** If you are a fresh Claude session and the user said something like:
> *"previously I was working with Codex orchestration + 4 Claude sessions on my dental PE app to hand-verify each of the ~4,400 Chicagoland practices — can you find the memory and context and reference files for that"*
> **— you have found it. Read this whole file, then jump to §9 "How to resume" and re-instantiate the right session.**
>
> Discovery keywords (so search finds this): codex orchestration · 4 claude sessions · hand verify 4400 chicagoland dental practices · ownership census · 6-tier ownership · gate owner · consolidation gate · reset · Wave 4 · ready_to_validate.
>
> **Authored:** 2026-06-22 by the **Reset + Consolidation Gate Owner** session (Opus 4.8), at the user's explicit request to document its role + every other role + exactly how the four sessions collaborate, and to leave a one-command resume path. The Gate Owner documented its own role most deeply; each of the other three sessions was asked to leave the equivalent doc for itself. All five **per-role handoffs already exist** in this folder (see §8) — this file is the index/overview that ties them together.
>
> **Companion memory files (they reconcile — no overwrite):** the **Main AO** session wrote its own seat-and-mission memory `START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md` (same folder) + a repo-root pointer `RESUME_CODEX_4SESSION_CENSUS.md`, and added the project-root `CLAUDE.md` discovery banner. **THIS file is the cross-role orchestration index**; the Main AO file leans into the census mission + the Main AO seat. Either one orients a fresh session — read this one for the who-does-what map and the freeze/gate mechanics. If they ever disagree on a count, the canonical manifest + `PROGRESS.json` win.

---

## 0. The 30-second picture

You are looking at a **multi-agent, file-coordinated, frozen-until-authorized** research operation whose single deliverable is a **hand-verified ownership directory of every Chicagoland general-dental practice**. It is **not** the legacy "5.43% corporate floor" detector — that is a *different, older axis* that stays untouched. This work builds a brand-new **6-tier ownership census** (`ownership_tier` column), location by location, with documentary evidence for every call.

```
                          ┌─────────────────────────────────────────┐
                          │  CODEX  (architect / coordinator / GPT)  │
                          │  backend session — verifies, sequences,  │
                          │  writes the exact prompts                 │
                          └───────────────────┬─────────────────────┘
                                              │  (prompts)
                                   ┌──────────▼──────────┐
                                   │   THE HUMAN (relay)  │  suleman7@bu.edu
                                   │  copy-pastes Codex's │
                                   │  instructions into   │
                                   │  each Claude session │
                                   └──────────┬──────────┘
                  ┌───────────────┬───────────┼────────────┬────────────────┐
                  ▼               ▼           ▼            ▼                 ▼
          ┌─────────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────┐   (all coordinate
          │  GATE OWNER │ │   MAIN AO   │ │ FLEET B │ │    QA    │    ONLY through
          │ (me — this  │ │  network /  │ │evidence │ │ adversa- │    files on disk,
          │  document)  │ │ authorized- │ │ mining  │ │ rial     │    never directly)
          │ merge/gate/ │ │ official    │ │(DB-only,│ │ review-  │
          │ validate    │ │ clusters    │ │ web-free│ │ only     │
          └─────────────┘ └─────────────┘ └─────────┘ └──────────┘
                  │               │           │            │
                  └───────────────┴─────┬─────┴────────────┘
                                        ▼
                  data/dso_research/  +  RESEARCH_HOME/  (the shared "blackboard")
                  consolidation_candidate_manifest_*.json  ← the canonical work product
```

**The hard truth that governs everyone:** nothing is written to the database until the user types the exact trigger phrase **`consolidate approved manifest`**. Until then every session writes **files only**. The whole team is currently parked at that frozen line, with a QA-passed candidate set staged and waiting.

---

## 1. The mission (Goal 2)

Build a fully-investigated ownership **DIRECTORY** of **every Chicagoland watched-ZIP general-dental practice location** — **~4,439 IL GP locations** across **269 IL watched ZIPs**. Each location must end up either:
- placed in one of **6 ownership tiers** with **documentary evidence**, or
- explicitly marked **`undetermined`** (never silently defaulted to "independent").

The census is **done** only when `PROGRESS.json.census_status.remaining == 0`.

**Boston / MA is PARKED** (21 ZIPs / 362 GP locations). It stays in the DB (do not delete) but is filtered from view and is **never** censused until the user un-parks it.

**The "no-anchor" rule (user ruling 2026-06-20):** the published consolidation % is computed **only from this census (the LEDGER), shown with coverage** — never anchored to the ADA ~14.6% per-dentist figure, never to "some metros are 30%," and the legacy ~5.4% detector floor is the *starting point being corrected*, **not** the answer. (Full text in `README.md` §"THE NO-ANCHOR RULE".)

---

## 2. The cast — who is who

| Actor | What it is | Job | On-disk identity |
|---|---|---|---|
| **Codex** | The architect/coordinator. A **GPT/Codex** session on the backend — **not a Claude session.** | Reads all files locally, verifies counts, catches inconsistencies, sequences the waves, and writes the **exact prompts** the human pastes into each Claude session. Does **not** itself do evidence research or DB writes unless explicitly asked. | `RESEARCH_HOME/HANDOFF_CODEX_COORDINATOR_20260621.md` |
| **The human** | The user (suleman7@bu.edu). | The **relay**. Every prompt a Claude session received was Codex's instruction, pasted by the human. Types the one trigger phrase that unfreezes consolidation. | — |
| **Gate Owner** | Claude session (Opus 4.8). **This document's author.** | **Merger / validator / gatekeeper ONLY.** Normalizes other sessions' evidence into the canonical manifest, runs `consolidate_census.py --validate-only`, holds the freeze, requests QA, authorizes the next fleet band. **Gathers no evidence, runs no agent fleets, makes no DB writes.** | `_active_lane_reset_consolidation_gate_20260621.md` · `HANDOFF_GATE_OWNER_20260621.md` · `HANDOFF_GATE_OWNER_20260622.md` (current) |
| **Main AO** | Claude session. | Mines NPPES **authorized-official (AO) clusters** — one official on 2+ watched-IL GP NPIs = a shared owner/officer candidate. Works conflict-network dossiers + AO backfill. **AO reach = discovery signal, not proof.** | `_active_lane_main_20260621.md` · `HANDOFF_MAIN_AO_20260621.md` |
| **Fleet B** | Claude session. | The **API-free / web-free** evidence miner — deterministic DB/Data-Axle clustering (EIN, brand, domain, officer, phone, structural residue) + Phase-C web verification of the strongest leads. | `_active_lane_evidence_fleet_b_20260621.md` · `HANDOFF_FLEET_B_20260621.md` |
| **QA** | Claude session. | **Independent adversarial review, REVIEW-ONLY.** Re-derives counts from the canonical files (never trusts agent summaries), scans for the recurring failure modes, writes a `VERDICT_*`/`ownership_manifest_QA_*` verdict. Cannot release protected networks; cannot authorize consolidation. | `_active_lane_qa_new_session_20260621.md` · `HANDOFF_QA_20260621.md` |

The four `_active_lane_*_20260621.md` markers in `data/dso_research/` are the proof that four distinct Claude sessions exist — one marker per session.

---

## 3. How the four sessions collaborate (the protocol)

There is **no direct session-to-session messaging.** Everything is a **shared-blackboard / file-passing** protocol under `data/dso_research/` (+ `RESEARCH_HOME/`). Codex reads the blackboard, the human relays, each session reads/writes files.

**The file-passing conventions:**
- Each session **writes NEW files only** — it never overwrites another session's file (QA verdicts, manifests, and prior handoffs are immutable).
- **Filename prefixes act as a message bus:** `REQUEST_*` (Gate→QA "please review"), `VERDICT_*` / `ownership_manifest_QA_*` (QA→Gate "here is my ruling"), `AUTH_*` (Gate→Fleet "you are cleared for the next band"), `DONE_*` / `BLOCKED_*` / `HEARTBEAT_*` (status), `_active_lane_*` (each session's append-only lane log).
- **The canonical work product is one file:** `consolidation_candidate_manifest_20260621.json` — 7 mutually-exclusive buckets (`ready_to_validate`, `needs_more_evidence`, `conflicts`, `rejected`, `evidence_gap_backfill_queue`, `duplicate_denominator_blocked`, `taxonomy_revised`) + preserved network-intelligence sidecars. Only the Gate Owner mutates it, and only after QA passes.
- **The validator-native mirror:** `_ready_to_validate_wave3_fixed_20260621.json` (310 rows) is exactly what a real consolidation run would consume. It must equal the manifest's `ready_to_validate` bucket (count + id-set) with 0 drift.

**The end-to-end loop (one wave):**
```
1. Main AO / Fleet B  →  drop an evidence file (wave4_*…json) on the blackboard, files-only.
2. Gate Owner         →  normalize each row through the enforced bar (§5), partition into
                         merge_eligible vs hold, write a *_gate_normalized_*.json + a REQUEST_QA_*.md.
                         Mutates NOTHING canonical yet.
3. QA                 →  independently re-derive from the on-disk file, scan failure modes,
                         write VERDICT_QA_*.json (PASS / PASS_WITH_HOLDS / MUST-FIX).
4. Gate Owner         →  if PASS: (still) hold; write a rollup; AUTH the next fleet band.
                         if MUST-FIX: apply the documented fix, re-validate, re-request QA.
5. Codex + human      →  read the rollup, decide the next move, relay the next prompts.
   …repeat until the user types "consolidate approved manifest", which only THEN unfreezes step 6:
6. Gate Owner         →  consolidate_census.py --allow-db-write  (NOT yet reached).
```

**The freeze is the synchronization primitive.** Every session re-verifies the same four invariants read-only before and after it writes, so any accidental DB leak is caught immediately by whoever looks next:

| Invariant | Required value |
|---|---|
| DB md5 (`data/dental_pe_tracker.db`) | `0dec26135bb4d6ee490dc16cfe892ca6` |
| `practice_locations.ownership_tier IS NOT NULL` / `practices.ownership_tier IS NOT NULL` | `0` / `0` |
| `RESEARCH_HOME/LEDGER.jsonl` lines | `1` (header only) |
| `PROGRESS.json` `tier_tally.undetermined_unreviewed` | `4439` |

(Re-verified intact at the close of this documentation session — 2026-06-22.)

---

## 4. The taxonomy everyone classifies into (LOCKED)

**6 ownership tiers + an orthogonal PE flag + `undetermined`.** Stored as a new `ownership_tier` column (+ `pe_backed`, evidence cols, `network_id`) on `practices` and `practice_locations`. `entity_classification` stays as the *size* axis (backward-compat, untouched).

| # | `ownership_tier` | Meaning | Consolidated? | DSO/PE? |
|---|---|---|---|---|
| T1 | `true_independent` | One dentist owns ONE location. **EARNED with evidence, never defaulted.** | no | no |
| T2 | `single_loc_group` | 2+ unrelated dentists, one location, dentist-owned. | **yes** | no |
| T3 | `dentist_multi` | One dentist-owner, 2+ locations, **no MSO/platform** (mini-DSO / "stealth owner"). | **yes** | no |
| T4 | `stealth_dso` | PE/MSO-backed friendly-PC under local names. | **yes** | **yes** |
| T5 | `branded_dso` | The brand IS the NPPES name (Aspen, Dental Dreams). | **yes** | **yes** |
| T6 | `institutional` | FQHC / hospital / university / government safety-net. | no (own bucket) | no |
| — | `undetermined` | Not yet reviewed OR genuinely ambiguous. Shown explicitly. | excluded | excluded |

**The single most important rule — `DSO = STRUCTURE`:** a DSO/PE tier (T4/T5) requires **structure** — an MSO / management company / platform / established DSO brand. **`pe_backed` is an orthogonal boolean**, never a downgrade reason: `pe_backed=false` does **not** turn a branded_dso into dentist_multi, and `pe_backed=true` alone does **not** make something a DSO.

**Two published headlines (both computed live from the census, with coverage):** Consolidated % = (T2+T3+T4+T5)/reviewed · DSO/PE % = (T4+T5)/reviewed.

---

## 5. The evidence bar (why "ready" is hard to earn)

A row reaches `ready_for_validation` only on a **durable documentary artifact**. The enforced bar is the **union (stricter-wins)** of: AB1–AB12 + HB1–HB10 + AH1–AH7 + the 12-step merge-eligibility decision tree + both gate-owner checklists. Default for anything failing/ambiguous = `needs_more_evidence` / `undetermined`. **No partial credit.**

**Counts as evidence:** a shared real EIN across 3+ locations with ≥1 corroborating member · a DSO's OWN locator with exact street+ZIP (URL transcribed in-session) · state corp / IDFPR registry naming an MSO · whitelisted DB artifacts `db_affiliated_dso` / `db_parent_company` · a `practice_intel` dossier naming a DSO with its citation URL · SEC/press naming a PE platform + location.

**Does NOT count:** AO reach alone · brand substring · co-location · asserted "web_verified" with no URL on disk · `DA_`-synthetic NPIs · referral directories (Zocdoc/Healthgrades/Vitals/Yelp) · `parent_iusa=000000000` placeholder.

**Standing HELD items (do not promote without an explicit decision):**
- **8 protected networks** — LABINOV, AQEL, BELKIC, SWEIS, RAMAHA, SHAFI, NITTINGER, BRUNETTI. Release requires an explicit per-network decision **and** `network_evidence_quality='verified'`. *(History: SHAFI_SOHAIL / SHAFI_REEM and LABINOV/NITTINGER/BRUNETTI have recorded Wave-2/3 release decisions as `dentist_multi`/verified; SWEIS + RAMAHA remain held with 0 verified rows.)*
- **Affordable Care / ClearChoice** — scope-held, out of the GP floor pending a user decision.
- **Operating-status / same-door / duplicate-denominator** rows — held until an active-door proof reconciles the door to one tier.

---

## 6. Current state — exactly where the team is parked (2026-06-22)

**Consolidation: FROZEN.** No `--allow-db-write` has ever run. Freeze invariant intact (§3).

**The canonical Wave-3 manifest** (`consolidation_candidate_manifest_20260621.json`), QA-passed (RE-QA #5 PASS):

| Bucket | Count |
|---|---:|
| **ready_to_validate** | **310** |
| needs_more_evidence | 167 |
| conflicts | 74 |
| rejected | 7 |
| evidence_gap_backfill_queue | 87 |
| core-universe distinct locations | 558 (310+167+74+7) |

Ready tier mix: dentist_multi 148 · branded_dso 94 · true_independent 30 · stealth_dso 21 · institutional 10 · single_loc_group 7. `--validate-only` on `_ready_to_validate_wave3_fixed_20260621.json` passes with zero writes.

**Wave 4 "Evidence Closure Sprint" (files-only, in progress):**
- **GATE-001/002 + QA-001:** initial Wave-4 partition normalized (`wave4_gate_normalized_partition_20260621.json`) → **19 net-new merge-eligible** candidates → QA-001 = **PASS_WITH_HOLDS**, no systemic defect.
- **GATE-003 + QA-002:** Lane-2 non-AO backfill (25 rows) normalized (`wave4_gate_normalized_lane2_partition_20260622.json`) → **+1 net-new corporate** (Schock Dental → Dentologie River North) + 12 corroborations (0 floor lift) + 2 true_independent confirmations + 4 holds + 3 refutations → QA-002 = **PASS_WITH_HOLDS**, +1 claim independently verified & **not overstated**.
- **LABINOV addendum** (`wave4_hold1_labinov_operating_status_rescan_20260622.json`): Destiny Oak Park `fd93e6934ac6c59c` confirmed OPEN → keep_ready; 7 D2-shell rows → hold_operating_status; network-identity correction (fd93 = `ao:WILSON-ADELEKE_SIMONE` sibling, not literal LABINOV).
- **GATE-004 rollup** (`wave4_gate_rollup_status_20260622.json`): **aggregate = 22 net-new census candidates at `ready_for_validation`** (19 initial + 3 Lane-2 net-new); **concrete legacy-floor lift = +1 (Dentologie only) — not overstated**; nothing merged.
- **Fleet B ranks 51–100:** AUTHORIZED then **DELIVERED** (`autonomous/DONE_FLEETB_PHASEC_51_100_20260622.md` + `wave4_lane3_phasec_51_100_evidence_20260622.json`, 50 rows): **2 net-new T5** (r79 Grove Dental / Bolingbrook — NADG-Abry; r100 Advanced Family Dental / Shorewood — Great Lakes-Shore) + 25 rejected / 16 needs-more / 4 protected-held / 3 scope; r83 Archer downgraded T3→hold. **NOT yet Gate-normalized — this is the open next gate task on resume** (normalize → REQUEST_QA → STOP; nothing merges before a fresh QA pass).

**Full Wave-4 audit trail:** `_wave4_20260621/_WAVE4_INTAKE_REGISTER_20260621.md` (GATE-001 → GATE-004 log).

---

## 7. What the GATE OWNER session (this document's author) has done

This session's complete record, oldest → newest:

**The reset + gate build (2026-06-21, logged in the lane marker + SESSION_LOG):**
- **Reset** the polluted Wave-1 candidate census (349 `ownership_tier` rows that QA found were candidate-quality, not classifications) — preserved everything to quarantine files + a DB backup (`data/dental_pe_tracker.db.pre_reset_bak_20260621`), then NULLed the 6 ownership columns on 349+349 rows. `entity_classification`/`ownership_status` untouched, 0 deletes. LEDGER → header-only, PROGRESS → 0/4439.
- **Built the canonical manifest** through 7 phases + 4 QA rounds: Phase 7 (123 ready) → 7b QA must-fix (65) → 7c backfill merge (123) → 7d Wave-2 merge (210) → 7e Pass-1 must-fix (206) → 7f Wave-3 merge (315) → 7g RE-QA #4 must-fix A/B/C (**310**) → **RE-QA #5 PASS**. Every step: validate-only passes, freeze re-verified intact.
- **Codified `DSO = STRUCTURE`** (`ownership_taxonomy_DSO_structure_gate_review_20260621.json`); held SWEIS/RAMAHA; held Webster/Berwyn in conflicts.

**Wave 4 (2026-06-22, logged in the intake register):**
- **GATE-001** — normalized Main AO Lane-1 (96) + Fleet B Phase-C top-50 into `wave4_gate_normalized_partition_20260621.json` (deterministic generator). 19 net-new merge-eligible; overrode agent "ready" on Sonrisa FQHC doors (DSO=STRUCTURE / FQHC-T6 unresolved → hold).
- **GATE-002** — wrote `REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md`; stopped for QA.
- **GATE-003** — normalized Main AO's Lane-2 non-AO backfill (25 rows) into `wave4_gate_normalized_lane2_partition_20260622.json` (+1 net-new corporate, characterized floor impact without overstating); wrote `REQUEST_QA_REVIEW_WAVE4_LANE2_20260622.md`; **authorized Fleet B 51–100** via the AUTH file.
- **GATE-004** — wrote the files-only rollup `wave4_gate_rollup_status_20260622.json`.
- **This documentation pass** — read all five role handoffs + README/MASTER_PLAN/PROGRESS/SESSION_LOG/lane markers, re-verified the freeze read-only, and wrote: this START_HERE file, the updated `HANDOFF_GATE_OWNER_20260622.md`, a CLAUDE.md discovery pointer, and lane/SESSION_LOG entries. **Zero DB / manifest / ready / LEDGER / PROGRESS mutation.**

Across the entire session: **no evidence gathered, no agent fleets run, no web search for owners, no DB writes.** The Gate Owner only normalizes, validates, gates, and documents.

---

## 8. File index — where everything lives

**The reference home is `data/dso_research/RESEARCH_HOME/`.** The shared blackboard is its parent `data/dso_research/`.

| File | Role |
|---|---|
| **`START_HERE_CODEX_4SESSION_ORCHESTRATION.md`** | **This file — the discoverable entry point / overview of all roles.** |
| `README.md` | Model, no-anchor rule, resume loop, binding rules, LEDGER schema. |
| `MASTER_PLAN.md` | Phases 0–7 execution plan. |
| `PROGRESS.json` | Machine-readable heartbeat (coverage, tier tallies, candidate pools, next_batch). |
| `LEDGER.jsonl` | Append-only, one line per reviewed location (currently header-only — census not yet run). |
| `CENSUS_PROTOCOL.md` · `EVIDENCE_FLEET_SPEC.md` · `FINDINGS.md` | Per-practice recipe · evidence-fleet spec · cross-session synthesis. |
| `SESSION_LOG.md` | Append-only audit trail of every working session. |
| **`HANDOFF_CODEX_COORDINATOR_20260621.md`** | Codex architect's role + how-we-got-here + the exact prompts it hands out. |
| **`HANDOFF_GATE_OWNER_20260622.md`** | **The current Gate Owner resume doc (supersedes `_20260621`).** |
| **`HANDOFF_MAIN_AO_20260621.md`** · **`HANDOFF_FLEET_B_20260621.md`** · **`HANDOFF_QA_20260621.md`** | The other three sessions' role docs. |
| `../consolidation_candidate_manifest_20260621.json` | **The canonical 7-bucket work product.** |
| `../_ready_to_validate_wave3_fixed_20260621.json` | The 310-row validator-native ready set. |
| `../ownership_manifest_QA_wave3_reqa5_20260621.json` | Latest passing QA verdict (RE-QA #5). |
| `../_active_lane_{main,qa_new_session,evidence_fleet_b,reset_consolidation_gate}_20260621.md` | The 4 session lane markers. |
| `../_wave4_20260621/` | Wave-4 sprint: intake register, gate-normalized partitions, rollup, AUTH, QA verdicts. |

---

## 9. How to resume — open the replica session and pick up exactly where it left off

When you (the user) come back, decide **which seat** to refill. Each Claude session is a separate context; paste that seat's prompt into a fresh Claude Code session in this repo.

> **First, always:** the fresh session should read this file + that seat's handoff, then run the read-only freeze check below and confirm all four invariants before doing anything.

**Freeze re-verify (read-only, run from repo root):**
```bash
cd /Users/suleman/dental-pe-tracker && python3 -c "import sqlite3,json,hashlib; db='data/dental_pe_tracker.db'; \
print('db_md5', hashlib.md5(open(db,'rb').read()).hexdigest()); c=sqlite3.connect(db); \
print('PL_tier', c.execute('SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('P_tier', c.execute('SELECT COUNT(*) FROM practices WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('LEDGER', sum(1 for _ in open('data/dso_research/RESEARCH_HOME/LEDGER.jsonl'))); \
print('undet', json.load(open('data/dso_research/RESEARCH_HOME/PROGRESS.json'))['tier_tally']['undetermined_unreviewed'])"
# expect: db_md5 0dec26135bb4d6ee490dc16cfe892ca6 · PL_tier 0 · P_tier 0 · LEDGER 1 · undet 4439
```

### ▶ To re-open THIS session (the Gate Owner — recommended primary resume):
Paste into a fresh Claude Code session:
```
You are resuming the RESET + CONSOLIDATION GATE OWNER role — one of 4 Claude sessions
under Codex orchestration on the dental-pe-tracker Chicagoland ownership census.
Read in full, in order:
  data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_ORCHESTRATION.md
  data/dso_research/RESEARCH_HOME/HANDOFF_GATE_OWNER_20260622.md
Then run the read-only freeze check and report all four invariants.
You are a merger/validator/gatekeeper ONLY: no evidence research, no agent fleets, no web
search, no DB writes. Consolidation stays FROZEN until I type exactly:
"consolidate approved manifest". Boston/MA is parked. When ready, tell me the current Wave-4
state and wait for Codex's next instruction (which I will paste).
```

### ▶ To re-open the other seats:
Same pattern, swapping the handoff file and one-line role reminder:
- **Main AO** → `HANDOFF_MAIN_AO_20260621.md` — "AO/network-intelligence; AO reach = signal not proof; no broad reach=2 long tail; files-only."
- **Fleet B** → `HANDOFF_FLEET_B_20260621.md` — "deterministic DB-only mining is exhausted; only Phase-C web-verify the authorized lead band (51–100 next); files-only."
- **QA** → `HANDOFF_QA_20260621.md` — "independent adversarial review-only; re-derive from canonical files, never trust summaries; write a NEW verdict file."
- **Codex (architect)** is a GPT/Codex session, not Claude — its resume doc is `HANDOFF_CODEX_COORDINATOR_20260621.md`.

### ▶ The single command that ends the freeze (only the user, only when ready):
Type to the Gate Owner session, verbatim: **`consolidate approved manifest`**. That — and only that — authorizes `consolidate_census.py --allow-db-write` on the 310-row ready file. Everything before that is files-only.

---

*This file is additive documentation — no DB, manifest, ready-file, LEDGER, PROGRESS, `ownership_tier`, `entity_classification`, or `ownership_status` was mutated to produce it. Freeze invariant re-verified intact at authoring (db_md5 `0dec26135bb4d6ee490dc16cfe892ca6`, tier 0/0, LEDGER 1, undetermined 4439).*
