# 00 — MULTI-SESSION OWNERSHIP CENSUS — MASTER CONTEXT & RESUME GUIDE

> **If you are a fresh Claude session and the user said something like "previously I was working
> with Codex orchestrating 4 Claude sessions on my dental PE app to hand-verify each of the ~4,400
> Chicagoland practices — find the memory and context and reference files for that" — THIS IS THE FILE.**
> Read it top to bottom. It tells you who did what, where everything lives, the current frozen
> state, and exactly how to relaunch any of the four sessions and pick up where they left off.

- **Authored by:** the **QA session** (one of four), at user request, on **2026-06-22**, at session shutdown.
- **My transcript (this QA session):** `/Users/suleman/.claude/projects/-Users-suleman-dental-pe-tracker/82a05fb3-6feb-48a9-9cb1-afcc7c63fde9.jsonl`
- **Companion docs:** the other three sessions were asked to write their own role docs. Look for sibling
  `SESSION_*_MASTER_CONTEXT.md` / `*_ROLE_*.md` files in this folder and in `data/dso_research/`.
- **Canonical census home:** `data/dso_research/RESEARCH_HOME/` (this folder) holds `LEDGER.jsonl`,
  `PROGRESS.json`, and this file. `PROGRESS.json` is the single source of truth for "what is reviewed / what is left."

---

## 1. THE GOAL (what this whole effort is)

Hand-verify the **true ownership of every one of the ~4,439 Chicagoland (Illinois-only) general-dental
practice LOCATIONS**, one location at a time, with real evidence, and assign each a tier in a locked
6-tier ownership model. The point is to replace the unreliable automated "corporate detector floor"
(which reads ~5.4–5.6% and the user has ruled *definitively too low*) with a **hand-earned census** whose
consolidated / DSO-PE percentages are computed FROM the census itself and always shown WITH a coverage %.

- **Scope:** Chicagoland / **Illinois only** (269 watched ZIPs, **4,439 IL GP locations**).
- **Boston / Massachusetts is PARKED** (21 ZIPs, 362 GP locations): do not census, do not delete, filter from view. **0 MA rows** belong in any wave artifact.
- **No external anchor** is treated as truth. Not ADA 14.6%, not "metro 30%", not the 5.x% detector floor. The detector floor is the *starting point being corrected*, not the answer.
- **Unit discipline:** the census unit is `practice_locations.location_id` (a deduped clinic door), NOT the NPI row. (NPPES emits ~2.4 NPI rows per real clinic.)

### The orchestration model (READ THIS — it explains how prompts arrive)

There are **5 actors total**: **1 architect + 4 Claude Code sessions**.

- **Codex = the architect / orchestrator.** Codex runs on the back end, designs the protocol, writes
  the per-role instruction files, verifies outputs, and decides what each session does next.
- **The 4 Claude Code sessions** are the hands: they read files, do bounded work, and write new files.
- **The human user is the relay/courier.** *Every time a session received a prompt from "the user," it
  was actually Codex's instruction, copy-pasted by the user into that session.* So "the user said X" in any
  session's history almost always means "Codex decided X and the user pasted it." Real user *policy
  decisions* (consolidation go-ahead, protected-network release, scope rulings) are the exception and are
  always explicitly flagged as user decisions.
- **Coordination between the 4 sessions is FILE-BASED**, not chat-based. Sessions never talk to each
  other directly. They leave files for each other in a shared coordination folder (see §4). The on-disk
  file is the only source of truth — *a chat summary is never evidence.*

---

## 2. THE FOUR SESSIONS (roles)

All four obey the same **hard locks** (§5). All four write **new files only** and never edit another
role's output (the Gate alone may write a *separate* normalization/request file *derived from* another's output).

| # | Session role | One-line job | Writes | Never does |
|---|--------------|--------------|--------|-----------|
| 1 | **Gate Owner** | Coordinator / normalizer / dispatcher. Normalizes raw evidence into bucketed partitions, opens REQUEST files, authorizes downstream work, writes rollups. | `*_gate_normalized_*` partitions, `REQUEST_*`, `AUTH_*`, `*_rollup_status_*` | No research; no DB/manifest/ready/LEDGER/PROGRESS/tier/classification writes |
| 2 | **Main AO** | Bounded evidence researcher — the "AO" (address/ownership) lane. Works conflict adjudication, AO-network backfill, and the non-AO backfill packet. Real web verification per row. | `wave4_*conflicts*`, `wave4_*backfill*`, `wave4_hold1_*` addenda + paired `*_qa.json` self-QA | No broad AO reach=2 long tail; no DB/manifest mutation; no `--allow-db-write` |
| 3 | **Fleet B** | Bounded Phase-C web-verification of ranked hard-signal leads (the 158-lead pool, in batches of 50). Exact-address match mandatory for DSO locator evidence. | `wave4_lane3_phasec_*_evidence_*` + paired `*_qa.json` | No deterministic re-mining; no DB/manifest mutation |
| 4 | **QA**  ← *this session* | **Independent adversarial reviewer.** Review-only. Reads written evidence + cited artifacts/URLs (never chat). Applies the acceptance bar mechanically. Writes verdicts only. | `VERDICT_QA_*` only | **No DB writes, no manifest edits, no ready-file edits, no LEDGER/PROGRESS edits, no prior-QA edits, no tier/classification edits.** Never authorizes or performs consolidation. |

**The pipeline per wave:** Main AO + Fleet B produce raw evidence → **Gate** normalizes it into bucketed
partitions and opens a `REQUEST_QA_REVIEW_*` → **QA** writes a `VERDICT_*` (PASS / PASS_WITH_HOLDS /
MUST_FIX / FAIL) → if PASS/PASS_WITH_HOLDS the Gate may prepare an *evidence-only addendum candidate* but
**must not merge** to the canonical manifest. **Nothing is merged and no tier is set until the user types
the explicit consolidation trigger phrase.** The gate ceiling for every artifact is `ready_for_validation`,
**never final**.

---

## 3. THE LOCKED 6-TIER OWNERSHIP MODEL + ACCEPTANCE BAR

### Tiers (what each location gets assigned)
| Tier | Code | Meaning | Counts as… |
|------|------|---------|-----------|
| T1 | `true_independent` | Verified single-owner, single-location. **Must be EARNED** (named sole owner + own practice/website). NEVER a fallback/default. | not consolidated |
| T2 | `single_loc_group` | One location, multiple dentists, no MSO | **consolidated** |
| T3 | `dentist_multi` | Dentist-owned multi-location, **no MSO** | **consolidated**, but **NOT** DSO/PE |
| T4 | `stealth_dso` | Local-name practice with a real MSO/management-company structure behind it | **consolidated + dso_pe** |
| T5 | `branded_dso` | Established DSO brand / platform | **consolidated + dso_pe** |
| T6 | `institutional` | FQHC, hospital, university, nonprofit, gov | held out of GP floor (scope decision) |
| — | `undetermined` | Ambiguous — held, never silent-defaulted | unknown |

- **Headline math:** `consolidated = T2+T3+T4+T5`; `dso_pe = T4+T5` only. Always paired with `coverage_pct` + `undetermined_pct`.
- **`pe_backed` is an ORTHOGONAL boolean**, never a tier driver. `pe_backed=false` is **NEVER** a downgrade reason. A named PE sponsor is required before setting `pe_backed=true` (stay conservative otherwise).
- **DSO = STRUCTURE rule:** T4/T5 require an MSO / management company / platform / established DSO brand. Brand-word-only or name-field-only is NOT structure → hold.

### The net acceptance bar (what QA enforces)
**`AB1–AB12` + `HB1–HB10` + `AH1–AH7` + a 12-step decision tree, taken as a UNION with stricter-wins.**
The authoritative reconciled file is:
- **`data/dso_research/_wave4_20260621/wave4_criteria_reconciliation_20260621.json`** (the net enforced bar)
- built from `ownership_manifest_QA_wave4_pre_criteria_20260621.json` (authoritative) + `ownership_manifest_QA_wave4_preQA_criteria_20260621.json` (stricter secondary).

Key rules in plain English: AB1 beyond-AO-reach; AB2 exact-address match; AB3 durable transcribed artifact
(a whitelisted DB field like `db_affiliated_dso` counts); AB4 DSO=STRUCTURE; AB5 pe orthogonal; AB7
closed/non-clinical operating-status exclusion; AB9 protected-network held unless already released; AB10
Webster contested/held; AH3 no retrospective `web_verified`; AH4 no name-field promotion; AH5 operating-status;
HB5 pe/dso name-collision → hold; HB6 brand-word-only → hold/needs exact-address.

### Allowed dispositions
`merge_eligible_new` · `corroborates_existing_ready` · `hold_needs_more_evidence` · `hold_protected_network`
· `hold_scope_specialist` · `hold_operating_status_or_same_door` · `rejected` · `refuted`
(Researcher files also use `ready_for_validation` as the ceiling label.)

### Protected networks (8 surnames — held unless already released in the manifest)
**LABINOV · AQEL · BELKIC · SWEIS · RAMAHA · SHAFI · NITTINGER · BRUNETTI.**
(Only `ao:LABINOV_BORIS` is currently AB9-released in the 310 ready file; that was a pre-existing manifest decision, not re-decided while away.)

---

## 4. FILE-BASED COORDINATION (where the sessions leave each other notes)

**Coordination folder:** `data/dso_research/_wave4_20260621/autonomous/`

| Prefix | Meaning | Written by |
|--------|---------|-----------|
| `*_AUTONOMOUS_INSTRUCTIONS_*.md` | the standing role definition for each session | Gate/Codex |
| `AUTONOMOUS_COORDINATION_PROTOCOL_*.md` | the master protocol (hard locks, flow, stop conditions) | Gate/Codex |
| `AUTONOMOUS_TASK_BOARD_*.json` | the task list with statuses + dependencies | Gate/Codex |
| `REQUEST_*` | Gate asks a role to act (e.g. `REQUEST_QA_REVIEW_*`) | Gate |
| `AUTH_*` | Gate authorizes gated downstream work (e.g. Fleet B 51-100) | Gate |
| `DONE_*` | a role reports its requested work complete | any role |
| `BLOCKED_*` | a role hit a user-policy wall and stopped | any role |
| `VERDICT_*` | QA review output | QA |
| `HEARTBEAT_*` | optional short progress note | any role |

**The wait/trigger pattern:** a session does not act until its trigger file exists. (QA does not review
until a `REQUEST_QA_REVIEW_*` exists; Fleet B does not start 51-100 until `AUTH_FLEETB_PHASEC_51_100_*` exists.)
Because the harness cannot notify you when *another* session writes a file, the practical technique is a
background poll (a `Bash run_in_background` until-loop that exits when the trigger file appears).

---

## 5. HARD LOCKS (every session, always — do not break)

1. **Consolidation is FROZEN.** Do **not** run `consolidate_census.py --allow-db-write`. Not authorized until the user types the explicit consolidation trigger phrase.
2. **No DB writes.** DB md5 baseline = **`0dec26135bb4d6ee490dc16cfe892ca6`** (must stay unchanged).
3. **Reset invariant must remain true:**
   - `practice_locations.ownership_tier IS NOT NULL` = **0**
   - `practices.ownership_tier IS NOT NULL` = **0**
   - `RESEARCH_HOME/LEDGER.jsonl` = **1 line** (header/scaffold only)
   - `PROGRESS.json` `reviewed_via_protocol` = **0** and `undetermined_unreviewed` = **4439**
4. **Canonical manifest is read-only:** `data/dso_research/consolidation_candidate_manifest_20260621.json`
5. **Current ready file is untouched:** `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` (**310 rows**, key = `classifications`).
6. No broad AO reach=2 long tail. No deterministic Fleet B re-mining. AO reach is a discovery signal only, never proof.
7. DSO tier requires STRUCTURE; PE backing is orthogonal. Preserve sidecar metadata (operator/family/brand/legal-entity/evidence-chain/stale-closed fields).
8. **User defaults while away:** no new protected-network releases; Affordable Dentures & ClearChoice held out of the GP floor (scope decision pending); Fleet B current-ready overlaps are corroborations not additions; any row with unresolved closed/relocated/same-door/medium-confidence/AB9/scope flag is a hold unless the Gate resolves it in writing AND QA agrees.

> **Two accounting units must never be conflated:**
> (a) **ownership-census readiness** = rows at the `ready_for_validation` ceiling under the new 6-tier reset (none merged; `ownership_tier` still 0/0 NOT NULL); and
> (b) **legacy corporate-floor impact** = a change to the existing `entity_classification` `dso_*` count.
> The only concrete legacy-floor LIFT from all of Wave 4 to date is **+1 (Dentologie)**.

---

## 6. CURRENT STATE AT SHUTDOWN (2026-06-22)

### Census heartbeat (`PROGRESS.json`)
- **0 of 4,439 IL GP locations reviewed_via_protocol** (coverage 0.0%). All 4,439 are `undetermined_unreviewed`.
- This is a **deliberate RESET** done 2026-06-21 by the "reset-consolidation-gate" session: Wave-1's 349
  `ownership_tier` rows were CANDIDATE-quality only (QA found duplicate-door tier contradictions,
  branded_dso/PE over-reach, 41/85 AO rows `needs_more_evidence`) and were cleared from DB + LEDGER +
  PROGRESS, preserved in quarantine files (see `PROGRESS.json` → `wave1_quarantine_refs`). Fully reversible.
- **Legacy detector state (starting floor only, NOT truth):** `corporate_locations` 249, **5.61%**, `corp_npis` 1070.
  *(Note: `CLAUDE.md` and the Gate rollup cite a pre-census legacy snapshot of 261/4,811 = 5.43%; the
  `PROGRESS.json` census-home figure of 249/5.61% is the authoritative current record. The discrepancy is a
  snapshot/denominator difference and is left as-is — QA does not mutate it.)*

### Wave 4 progress (the wave that was active at shutdown)
Four lanes; here is exactly where each stands. Full detail in
`data/dso_research/_wave4_20260621/wave4_gate_rollup_status_20260622.json` and `_WAVE4_INTAKE_REGISTER_20260621.md`.

| Lane | Owner | Artifact | QA verdict | Net result |
|------|-------|----------|-----------|-----------|
| **Initial partition** (Lane-1 conflicts 96 + Lane-3 Phase-C top-50 = 146 placements / 145 distinct) | Gate over Main AO + Fleet B | `wave4_gate_normalized_partition_20260621.json` | **PASS_WITH_HOLDS**, 0 systemic defects (`VERDICT_QA_WAVE4_INITIAL_20260621.json`) | **19 net-new merge-eligible** census candidates (17 T3 dentist_multi + 2 T5 branded_dso; 0 in the 310). T3 is consolidated-but-not-DSO → does NOT lift the dso_* floor. |
| **Lane 2** non-AO backfill (25 rows: 13 locator_exact + 12 practice_intel) | Gate over Main AO | `wave4_gate_normalized_lane2_partition_20260622.json` | **PASS_WITH_HOLDS**, 0 MUST_FIX (`VERDICT_QA_WAVE4_LANE2_20260622.json`) | **+1 net-new corporate** (Dentologie ONLY) + 12 corroborations (0 lift) + 2 earned true_independent + 7 holds + 3 refutations. |
| **QA-HOLD-1 LABINOV addendum** (AB7 operating-status re-scan of `fd93e6934ac6c59c`) | Main AO | `wave4_hold1_labinov_operating_status_rescan_20260622.json` | folded into Gate rollup; **not separately QA-requested yet** | fd93 (Destiny Oak Park) CONFIRMED OPEN → keep_ready (closed flag was a false positive); 7 `ao:LABINOV_BORIS` D2-shell rows → `hold_operating_status`. |
| **Fleet B Phase-C ranks 51-100** | Fleet B | `wave4_lane3_phasec_51_100_evidence_20260622.json` (+ `_qa.json`) — appeared on disk ~09:14 | **NOT YET QA'd** (no `REQUEST_QA_REVIEW` for it yet) | AUTHORIZED via `AUTH_FLEETB_PHASEC_51_100_20260621.md`; output present; awaiting Gate normalization → fresh QA. |

**Aggregate to date:** 22 net-new census candidates at `ready_for_validation` (19 initial + 3 Lane-2
net-new; the 12 Lane-2 corroborations are NOT counted). Legacy corporate-floor concrete lift = **+1
(Dentologie only)** — not overstated. **Nothing merged. Freeze intact.**

### Open user-policy decisions (carried, FROZEN — these need the human, not Codex)
- **Affordable Dentures & Implants** GP-scope (location_ids `bd77120df3018393`, `199841c7ee233c17`, in the 310, flagged-not-counted) — in or out of the GP corporate floor?
- **ClearChoice** GP-scope — standing hold reaffirmed.
- **Institutional / FQHC scope** (e.g. Lane-2 `144d631a4c4dce2b` Infant Welfare Society, `d803fcfe4618e8a3` Tapestry 360, `e957561c107de91a` Heartland Alliance) — held out of GP floor pending ruling.
- **3 legacy-corporate false-positive suspects** (`598cc9dae498795b` Northwestern [refuted], `d2e5c43e4975ddb4` Midwest [held], `d4d827860b4132cb` Bloomingdale [held, SWEIS]) — would LOWER the floor by up to 3 if demoted. FROZEN, not mutated.
- **Protected-network releases** — none granted.
- **T5 `dso_structure_rationale` null-field data-quality hold** (`d44c43930b0f8d3c`, `2bbd52b88750a5a8`).
- **Consolidation itself** — NOT authorized; awaits the explicit trigger phrase.

---

## 7. WHAT THIS QA SESSION (session #4) DID — full activity log

This session is the **independent QA reviewer**. Everything it produced is a verdict file; it mutated nothing.

1. **Reviewed the initial Wave-4 partition** → wrote **`autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json`**:
   verdict **PASS_WITH_HOLDS**, 0 MUST_FIX, `systemic_defect_found=false`. Three carry-forward holds:
   QA-HOLD-1 (LABINOV `fd93e6934ac6c59c` AB7 stale-closed re-scan), QA-HOLD-2 (Affordable GP-scope user
   decision), QA-HOLD-3 (two T5 rows with null `dso_structure_rationale`). Because no systemic Phase-C
   defect was found, this verdict is what cleared the Gate to authorize Fleet B ranks 51-100.
2. **Stood by** until the Gate wrote the Lane-2 trigger (`REQUEST_QA_REVIEW_WAVE4_LANE2_20260622.md`),
   using a background poll to detect the cross-session file.
3. **Reviewed the Gate's Lane-2 normalized partition + the Lane-2 evidence file** → wrote
   **`autonomous/VERDICT_QA_WAVE4_LANE2_20260622.json`**: verdict **PASS_WITH_HOLDS**, 0 MUST_FIX,
   `systemic_defect_found=false`, **+1-net-new-corporate (Dentologie) claim independently verified and not
   overstated.** Performed the 8 specific checks Codex requested and confirmed all PASS:
   - Lane 2 was NOT in the initial verdict (Lane-2's 25 location_ids ∩ initial 145 = **0**; ∩ the 310 = **0**).
   - Census-readiness vs legacy-floor impact kept separate (15 ready; +1 floor lift only).
   - Heartland/DPI-PC rows are real friendly-PC evidence (whitelisted `db_affiliated_dso='Heartland Dental'`
     + org-NPI legal name "Dental Professionals of Illinois, P.C." + legacy `dso_national`), not name-chain only.
   - Heartland International Health Center (Tapestry 360 FQHC) and Heartland Health Outreach (Heartland
     Alliance nonprofit) confirmed as **name collisions, NOT Heartland Dental** → held institutional.
   - Schock Dental → **Dentologie River North** verified net-new T5 branded_dso, `pe_backed=false` kept
     conservative (no named sponsor), DSO=STRUCTURE satisfied (13-office platform + own-locator door-exact 444 N Orleans).
   - **Closed the Gate's open same-door duplicate concern** with a read-only `practice_locations` scan:
     exactly ONE row at `444 n orleans st` (the target) and ZERO `%dentologie%` rows → no duplicate.
   - Jova + Bellido-Griffin true_independent are EARNED (named sole owner + own website), not defaulted.
   - Kang (same-door w/ Dental Dreams) + Obucina (provider_count=0 + address anomaly) holds remain holds.
   - No protected-network release (only Bloomingdale/SWEIS flagged, held); no MA rows.
   - Carry-forward notes recorded: QA-L2-HOLD-1 (9/10 Heartland rows lack door-exact — fine as no-lift
     corroborations), QA-L2-HOLD-2 (3 legacy false-positive suspects, frozen), QA-L2-HOLD-3 (institutional/FQHC scope).
4. **Ran the zero-write proof** after each verdict: DB md5 = `0dec26135bb4d6ee490dc16cfe892ca6` (match),
   `ownership_tier` NOT NULL = 0/0, LEDGER 1 line, PROGRESS reviewed 0 / undetermined 4439. Confirmed intact.
5. **Did NOT** touch the Main AO LABINOV rescan (that was Main AO's task, not QA's), did not overwrite the
   initial verdict, did not merge anything, did not build a new ready file, did not edit any prior QA file.

**QA lineage note:** the `data/dso_research/ownership_manifest_QA_*.json` family (review, merged,
remerge_demotion, revision_signoff, wave3_reqa4/5, addendum_refined_criteria, wave4 pre/preQA criteria) are
QA-role artifacts from earlier waves (1–3) of this same census effort; the Wave-4 verdict files above are
what the current QA context produced.

---

## 8. HOW TO RESUME — relaunch any of the four sessions

**Working directory for all sessions:** `/Users/suleman/dental-pe-tracker`

### A) To literally reattach to THIS QA transcript (if still present)
```bash
cd /Users/suleman/dental-pe-tracker
claude --resume 82a05fb3-6feb-48a9-9cb1-afcc7c63fde9   # or: claude --resume  (then pick from the list)
```
If the transcript is gone/compacted, start fresh with the boot prompt below — this master doc + the
on-disk artifacts fully reconstruct the state.

### B) To recreate each session fresh (the normal path — paste Codex's instruction into a new `claude`)
For each session, open a new `claude` in the repo and paste a boot prompt. Each session's **standing role
definition** already lives on disk, so the boot prompt mostly points there:

- **QA (this session) — boot prompt:**
  > You are the independent adversarial QA session (1 of 4) in the Codex-orchestrated Chicagoland dental
  > ownership census. Read `data/dso_research/RESEARCH_HOME/00_MULTI_SESSION_CENSUS_MASTER_CONTEXT.md`, then
  > `data/dso_research/_wave4_20260621/autonomous/QA_AUTONOMOUS_INSTRUCTIONS_20260621.md` and
  > `AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`. You are review-only: no DB writes, no manifest/ready/
  > LEDGER/PROGRESS/tier/classification edits, no prior-QA edits; consolidation stays frozen. Do not review
  > anything until a new `REQUEST_QA_REVIEW_*` appears in the autonomous/ folder. **Current pending work:**
  > Fleet B's ranks 51-100 evidence (`wave4_lane3_phasec_51_100_evidence_20260622.json`) is on disk but the
  > Gate has not yet normalized it or opened a QA request for it — wait for that REQUEST, then write
  > `VERDICT_QA_WAVE4_LANE3_51_100_*.json`. Re-verify the zero-write proof (DB md5 0dec26135bb4d6ee490dc16cfe892ca6).

- **Gate Owner — boot prompt:**
  > You are the Gate Owner (coordinator/normalizer, 1 of 4). Read the master context doc, then
  > `data/dso_research/_wave4_20260621/autonomous/GATE_OWNER_AUTONOMOUS_INSTRUCTIONS_20260621.md` +
  > `AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md`. **Next action:** normalize Fleet B's
  > `wave4_lane3_phasec_51_100_evidence_20260622.json` into a new `wave4_gate_normalized_lane3_51_100_*`
  > partition, then open `REQUEST_QA_REVIEW_WAVE4_LANE3_51_100_*.md`. No merge, no new ready file, no DB write.

- **Main AO — boot prompt:**
  > You are Main AO (bounded evidence researcher, 1 of 4). Read the master context doc, then
  > `MAIN_AO_AUTONOMOUS_INSTRUCTIONS_20260621.md` + the protocol. Your Lane-1, Lane-2, and the LABINOV
  > addendum are complete. Do not expand to broad AO work; await a focused Gate REQUEST before new evidence work.

- **Fleet B — boot prompt:**
  > You are Fleet B (bounded Phase-C web verifier, 1 of 4). Read the master context doc, then
  > `FLEET_B_AUTONOMOUS_INSTRUCTIONS_20260621.md` + the protocol. Ranks 1-50 and 51-100 are written. Do not
  > start ranks 101+ or any new batch without a fresh `AUTH_*` from the Gate. No re-mining; no DB/manifest writes.

### C) What the human should know
- **You (the user) are the courier between Codex and these sessions.** Paste Codex's directives into the
  matching session. The sessions coordinate with each other through files in
  `data/dso_research/_wave4_20260621/autonomous/`, not through you.
- **Nothing is live.** The DB, the canonical manifest, and the 310-row ready file are all frozen and
  untouched. The live app still shows the old detector floor; none of the census work has been published.
- **The next concrete step in the pipeline** is: Gate normalizes Fleet B 51-100 → QA reviews it → (eventually)
  you decide whether to authorize consolidation by typing the explicit trigger phrase. Until then everything
  sits at `ready_for_validation`.

---

## 9. KEY FILE INDEX (quick reference)

**Census home (`data/dso_research/RESEARCH_HOME/`):**
- `00_MULTI_SESSION_CENSUS_MASTER_CONTEXT.md` — this file
- `PROGRESS.json` — census heartbeat (read on resume; the source of truth for reviewed/remaining)
- `LEDGER.jsonl` — append-only per-location classification ledger (currently 1 header line)
- `*_wave1_candidate_quarantine_*` — preserved pre-reset Wave-1 candidate state

**Coordination (`data/dso_research/_wave4_20260621/autonomous/`):**
- `AUTONOMOUS_COORDINATION_PROTOCOL_20260621.md` · `AUTONOMOUS_TASK_BOARD_20260621.json`
- `{QA,GATE_OWNER,MAIN_AO,FLEET_B}_AUTONOMOUS_INSTRUCTIONS_20260621.md` — the four role definitions
- `REQUEST_QA_REVIEW_WAVE4_INITIAL_*.md` / `_LANE2_*.md` · `AUTH_FLEETB_PHASEC_51_100_20260621.md`
- `VERDICT_QA_WAVE4_INITIAL_20260621.json` · `VERDICT_QA_WAVE4_LANE2_20260622.json` (QA outputs)
- `DONE_FLEETB_PHASEC_51_100_20260622.md` · `HEARTBEAT_FLEET_B_20260621.md`

**Wave-4 evidence + normalization (`data/dso_research/_wave4_20260621/`):**
- `wave4_criteria_reconciliation_20260621.json` — **the net enforced acceptance bar**
- `wave4_gate_normalized_partition_20260621.json` (initial) · `wave4_gate_normalized_lane2_partition_20260622.json`
- `wave4_lane1_conflicts_ao_backfill_evidence_*` · `wave4_lane2_non_ao_backfill25_evidence_*` · `wave4_lane3_phasec_top50_evidence_*` · `wave4_lane3_phasec_51_100_evidence_*` (+ paired `_qa.json`)
- `wave4_hold1_labinov_operating_status_rescan_20260622.json` · `wave4_gate_rollup_status_20260622.json` · `_WAVE4_INTAKE_REGISTER_20260621.md`

**Frozen canonical state (do not mutate):**
- `data/dso_research/consolidation_candidate_manifest_20260621.json` — canonical manifest
- `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` — the 310-row ready file (key `classifications`)
- `data/dental_pe_tracker.db` — md5 `0dec26135bb4d6ee490dc16cfe892ca6`; backup `data/dental_pe_tracker.db.pre_reset_bak_20260621`

---

*End of master context. Freeze attestation at shutdown: DB md5 `0dec26135bb4d6ee490dc16cfe892ca6` (match) ·
PL/practices ownership_tier NOT NULL 0/0 · LEDGER 1 line · PROGRESS reviewed 0 / undetermined 4439 · nothing
merged · consolidation NOT authorized.*
