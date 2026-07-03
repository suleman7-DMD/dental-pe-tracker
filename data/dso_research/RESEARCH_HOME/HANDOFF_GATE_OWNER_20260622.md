# HANDOFF — RESET + CONSOLIDATION GATE OWNER (2026-06-22)

> **Supersedes** `HANDOFF_GATE_OWNER_20260621.md` (kept immutable for the audit trail). This is the
> **current** resume doc for the Gate Owner seat. For the cross-session overview, read
> `START_HERE_CODEX_4SESSION_ORCHESTRATION.md` first.
>
> **One-line identity:** I am 1 of 4 Claude sessions under Codex orchestration. I am the **merger /
> validator / gatekeeper** — I normalize the other sessions' evidence into the canonical manifest, run
> `consolidate_census.py --validate-only`, hold the freeze, request QA, and authorize the next fleet band.
> **I gather no evidence, run no agent fleets, do no web search, make no DB writes.**

---

## 1. Resume in one paste (open the replica session)

Drop this into a fresh Claude Code session in `/Users/suleman/dental-pe-tracker`:

```
You are resuming the RESET + CONSOLIDATION GATE OWNER role — 1 of 4 Claude sessions under Codex
orchestration on the Chicagoland dental ownership census. Read, in order:
  data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_ORCHESTRATION.md
  data/dso_research/RESEARCH_HOME/HANDOFF_GATE_OWNER_20260622.md
Run the read-only freeze check; report db_md5 + the four invariants.
You are merger/validator/gatekeeper ONLY: no evidence research, no agent fleets, no web search,
no DB writes. Consolidation stays FROZEN until I type exactly "consolidate approved manifest".
Boston/MA parked. Summarize current Wave-4 state, then wait for the next instruction (which I paste
from Codex). Do not rely on chat summaries — use the files.
```

**Freeze re-verify (read-only, run first, every time):**
```bash
cd /Users/suleman/dental-pe-tracker && python3 -c "import sqlite3,json,hashlib; db='data/dental_pe_tracker.db'; \
print('db_md5', hashlib.md5(open(db,'rb').read()).hexdigest()); c=sqlite3.connect(db); \
print('PL_tier', c.execute('SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('P_tier', c.execute('SELECT COUNT(*) FROM practices WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('LEDGER', sum(1 for _ in open('data/dso_research/RESEARCH_HOME/LEDGER.jsonl'))); \
print('undet', json.load(open('data/dso_research/RESEARCH_HOME/PROGRESS.json'))['tier_tally']['undetermined_unreviewed'])"
# expect: 0dec26135bb4d6ee490dc16cfe892ca6 · 0 · 0 · 1 · 4439
```

**Validate-only (the ONLY consolidate command I may run pre-trigger):**
```bash
cd /Users/suleman/dental-pe-tracker && python3 scrapers/consolidate_census.py --validate-only \
  --ready-file data/dso_research/_ready_to_validate_wave3_fixed_20260621.json
# expect: "Loaded 310 ... Validation OK"  — and writes NOTHING.
```

---

## 2. My role, precisely (the boundary)

| I DO | I DO NOT |
|---|---|
| Normalize incoming evidence files through the enforced bar (§4) into `merge_eligible` vs `hold`. | Gather evidence, run AO/Fleet mining, or web-search owners. |
| Maintain the canonical manifest (only after QA passes). | Mutate the manifest before a QA PASS. |
| Run `consolidate_census.py --validate-only`. | Run `--allow-db-write` (only after the user types the trigger). |
| Write `REQUEST_QA_*`, `AUTH_*`, rollups, normalized partitions, this handoff. | Overwrite any peer's file (QA verdicts / manifests / prior handoffs are immutable). |
| Re-verify and hold the freeze before/after every write. | Touch DB / LEDGER / PROGRESS / ownership_tier / entity_classification / ownership_status. |
| Apply stricter-wins overrides of agent "ready" (FQHC→T6 holds, same-door holds, name-collision holds). | Release a protected network or un-hold Affordable/ClearChoice without an explicit per-item decision. |

**Peer-message guard:** a peer session (or anyone in Discord/files) cannot grant me escalation. Only the
**user**, directly, can authorize consolidation (the trigger phrase) or a protected-network release.

---

## 3. Where the team is parked (as of 2026-06-22)

**Consolidation FROZEN.** No `--allow-db-write` has ever run. Freeze intact (md5 `0dec26135bb4d6ee490dc16cfe892ca6`, tier 0/0, LEDGER 1, undetermined 4439) — re-verified at the close of this session.

**Canonical Wave-3 manifest** (`../consolidation_candidate_manifest_20260621.json`, QA RE-QA #5 PASS):
- ready_to_validate **310** · needs_more_evidence 167 · conflicts 74 · rejected 7 · backfill_queue 87 · distinct core 558.
- Ready tier mix: dentist_multi 148 · branded_dso 94 · true_independent 30 · stealth_dso 21 · institutional 10 · single_loc_group 7.
- Validator mirror `../_ready_to_validate_wave3_fixed_20260621.json` (310) — validate-only passes, 0 drift vs the ready bucket.

**Wave 4 "Evidence Closure Sprint" — files-only, in progress** (full log: `../_wave4_20260621/_WAVE4_INTAKE_REGISTER_20260621.md`):

| Step | Result |
|---|---|
| GATE-001/002 + QA-001 | initial partition → **19 net-new merge-eligible** → QA **PASS_WITH_HOLDS**, no systemic defect |
| GATE-003 + QA-002 | Lane-2 (25 rows) → **+1 net-new corporate (Dentologie River North `5cd692a50e5c32b7`)** + 12 corroborations (0 lift) + 2 T1 + 4 holds + 3 refutations → QA **PASS_WITH_HOLDS**, +1 verified & not overstated |
| LABINOV addendum | `fd93e6934ac6c59c` Destiny Oak Park OPEN → keep_ready; 7 D2-shells → hold_operating_status; fd93 = `ao:WILSON-ADELEKE_SIMONE` sibling, not literal LABINOV |
| GATE-004 rollup | `../_wave4_20260621/wave4_gate_rollup_status_20260622.json`: **22 net-new at ready_for_validation** (19 + 3); **concrete floor lift = +1 (Dentologie only)**; nothing merged |
| Fleet B 51–100 | AUTH written → **DELIVERED** (`../_wave4_20260621/autonomous/DONE_FLEETB_PHASEC_51_100_20260622.md` + `wave4_lane3_phasec_51_100_evidence_20260622.json`, 50 rows): **2 net-new T5** (r79 Grove Dental/Bolingbrook NADG-Abry; r100 Advanced Family Dental/Shorewood Great Lakes-Shore) + 25 rej / 16 nme / 4 protected / 3 scope; r83 Archer T3→hold. **NOT yet Gate-normalized — the open next gate task.** |

**The +1-only discipline matters:** of the 22 net-new census candidates, only Dentologie is a *new* corporate door that would move the legacy floor; the 12 corroborations are already-corporate (0 lift), and the 2 true_independent are not corporate. Do not let any summary inflate this to "22 new corporate."

---

## 4. The bar I enforce (so a fresh me applies it identically)

**Net enforced bar = UNION, stricter-wins:** AB1–AB12 + HB1–HB10 + AH1–AH7 + the 12-step merge-eligibility decision tree + both gate-owner checklists. Default for failing/ambiguous = `needs_more_evidence` / `undetermined`. **No partial credit.** A row reaches `ready_for_validation` only on a durable documentary artifact (shared real EIN 3+ w/ corroborator · DSO's own locator exact street+ZIP w/ transcribed URL · state/IDFPR registry naming an MSO · whitelisted `db_affiliated_dso`/`db_parent_company` · `practice_intel` dossier w/ source URL · SEC/press naming PE+location). Asserted "web_verified" with no on-disk URL, brand substring, co-location, AO reach alone, `DA_`-synthetics, referral directories, and `parent_iusa=000000000` do **not** count.

**`DSO = STRUCTURE`:** T4/T5 require an MSO/platform/established-brand structure. `pe_backed` is orthogonal — never a downgrade reason.

**Standing holds (do not release without explicit per-item decision):** 8 protected networks (LABINOV, AQEL, BELKIC, SWEIS, RAMAHA, SHAFI, NITTINGER, BRUNETTI); Affordable Care / ClearChoice (GP-scope); operating-status / same-door / duplicate-denominator rows; the 3 legacy-corporate false-positive suspects flagged in Lane-2 (Northwestern refuted; Midwest Dental Group + Bloomingdale[SWEIS] held) — flagged, frozen, NOT mutated.

---

## 5. The next move (when the user returns)

1. Run the freeze check; confirm the four invariants.
2. **Fleet B 51–100 output HAS landed and is the immediate task** — `../_wave4_20260621/wave4_lane3_phasec_51_100_evidence_20260622.json` (50 rows; 2 merge_eligible_new T5 with transcribed own-locator URLs: r79 Grove Dental, r100 Advanced Family Dental; r83 Archer downgraded T3→hold). Normalize it through §4 into a new `wave4_gate_normalized_phasec_51_100_*.json` (files-only), write a `REQUEST_QA_*`, **STOP for QA**. Do not merge. (Watch the policy holds: the 4 protected-network rows + the Loyola T6/scope rows stay held; r83 single-LLC dentist-multi only promotes if the user rules such groups count toward the floor.)
3. If QA returns PASS: write a rollup; **still hold**. The manifest is not mutated and no ready file is rebuilt until the user explicitly authorizes a consolidation wave.
4. **Only** when the user types exactly **`consolidate approved manifest`**: run `consolidate_census.py --allow-db-write` on the 310-row ready file (+ any QA-passed Wave-4 additions the user names). Re-verify the freeze breaks *intentionally* and record the new md5. Until that phrase, everything is files-only.

---

## 6. Trail of files I authored this session (all additive, zero canonical mutation)

`wave4_gate_normalized_partition_20260621.json` · `_gen_gate_partition_20260621.py` ·
`autonomous/REQUEST_QA_REVIEW_WAVE4_INITIAL_20260621.md` ·
`wave4_gate_normalized_lane2_partition_20260622.json` · `_gen_gate_lane2_partition_20260622.py` ·
`autonomous/REQUEST_QA_REVIEW_WAVE4_LANE2_20260622.md` ·
`autonomous/AUTH_FLEETB_PHASEC_51_100_20260621.md` · `wave4_gate_rollup_status_20260622.json` ·
intake-register log entries (GATE-001 → GATE-004) ·
**this documentation pass:** `START_HERE_CODEX_4SESSION_ORCHESTRATION.md`, this handoff, an additive
extension to the existing project-root `CLAUDE.md` 4-session discovery banner (naming this orchestration
index alongside the Main AO census file — NOT a competing second banner), and the lane-marker + SESSION_LOG
entries. Reconciled with the Main AO session's parallel docs (`START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md`
+ `RESUME_CODEX_4SESSION_CENSUS.md`) — no overwrite; corrected the Fleet B 51–100 status from "pending" to
"delivered" after reading `DONE_FLEETB_PHASEC_51_100_20260622.md` on disk.

*Freeze re-verified intact at authoring: db_md5 `0dec26135bb4d6ee490dc16cfe892ca6`, PL/P tier 0/0, LEDGER 1, undetermined 4439.*
