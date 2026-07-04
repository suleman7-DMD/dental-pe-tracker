# SESSION CHARTER — Fable Truth-Safe App Redesign
**Author:** Fable (PM) · 2026-07-04 · Status: EXECUTION CONTRACT for the dedicated Fable-only session
**Supersedence:** live code/tests > this charter > DECISION_TRUE_INDEPENDENT_HEADLINE_20260703.md > older handoffs.
**Companion docs (read-only references, do not re-derive):** `MASTER_RESUME_LANE_A_FLEET_20260702.md` §6m (census state), `DECISION_TRUE_INDEPENDENT_HEADLINE_20260703.md` (headline buckets, labeling law), `PLAN_FABLE_DISTILLATION_20260703.md` (Opus succession), CLAUDE.md (invariants).

---

## 0. Mission (the user's + Codex's governing line, verbatim in spirit)

> The goal is not just redesign. It is to create a **truth-safe product architecture** so the app
> **cannot accidentally present detector/legacy/partial data as final census truth.**
> Do not just make the UI prettier. Redesign the app so it is **impossible to confuse** legacy
> detector estimates, unsynced candidate files, and live reviewed census truth.

One product spine: **a master Chicagoland dental practice directory** where each practice has a
truth-backed ownership record, evidence, job-hunt usefulness, acquisition relevance, and review
status. Every page is a lens on that spine.

Page priority (user-ratified): **1) Directory → 2) Job Hunt → 3) Ownership → 4) Acquisition
Scout → 5) Review Desk → then the rest** (PE Deals, Evidence, Research Notes, Methodology,
System, Home).

---

## 1. Ground state as of 2026-07-04 (verify, don't trust — recheck commands included)

### 1a. Census truth layer — LOCAL SQLite (written + verified 2026-07-04)
- `practice_locations.ownership_tier` notnull = **3,180** of 4,439 IL GP scope = **71.64% reviewed coverage**.
- Tier tally: **T1 1,471 / T2 934 / T3 537 / T4 28 / T5 151 / T6 59**; `pe_backed` = 118 locations.
- NPI mirror: **6,754** `practices` rows carry ownership_tier.
- Remaining: **91 held** (52 dso_verify + 30 unresolved + 9 duplicate_suspect, `_lane_a_20260702/` + `_census_holds_20260702.json`), **649 triage**, ~477 undetermined-researched, ~950 never-researched (wave-5 queue). These are FUTURE census work — the app must SHOW them as unresolved, not hide them.
- Recheck: `python3 -c "import sqlite3; c=sqlite3.connect('data/dental_pe_tracker.db'); print(c.execute(\"SELECT ownership_tier, COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL GROUP BY 1\").fetchall())"`

### 1b. Supabase (live app backend) — ⚠️ CHECK FIRST, EVERY SESSION
As of charter authoring the live Supabase has only the **343-row 2026-07-02 write**, NOT the
2,837-row wave-1 write. The two sync legs were pending user authorization:
```bash
python3 -m scrapers._sync_floor_tables_only          # leg 1: practice_locations full_replace (carries census cols)
python3 -m scrapers._sync_census_columns_practices   # leg 2: surgical 6-col UPDATE on practices
```
Read-back expectation after sync: Supabase practice_locations ownership_tier notnull = 3,180;
practices mirror = 6,754; detector floor still 268 corp locations / 1,152 corp NPIs.
**If sync has not run: PHASE 1+ IS BLOCKED for census-driven UI (the frontend reads Supabase
only). Phase 0 honesty work is NOT blocked. /system must state the sync gap honestly.**

### 1c. Legacy detector axis (context layer — NEVER conflate with census)
Detector floor: **268 corp locations / 1,152 corp NPIs / 4,801 GP denominator** (watched, post-2026-06-19). CI guards `FLOOR expect_min=268`, `FLOOR_NPI expect_min=1152`. The census write did not and must never move these.

### 1d. Repo topology + concurrency
- **Main repo** `/Users/suleman/dental-pe-tracker` (data, scrapers, runbooks). Bank milestones here.
- **Frontend** `dental-pe-nextjs/` is its OWN git repo (not tracked by main); push to its `main` auto-deploys Vercel (~30s). Recent Codex commits there: 62564cb "Redesign app around verified practice directory", 7f60f7a honest floor framing, 7a5e8ce census-first map redesign plan.
- **Codex works concurrently** in both repos. Before editing any frontend file: `git -C dental-pe-nextjs log --oneline -5` + `git -C dental-pe-nextjs status`. Coordination rule (ratified): no full `sync_to_supabase.py`, no `refresh.sh`, no practices-table sync while a census merge chain is running.

### 1e. Sidebar map (labels are ALREADY the user's names — routes are legacy)
| Label | Route | Label | Route |
|---|---|---|---|
| Home | `/` | Directory | `/job-market` |
| Ownership | `/market-intel` | Job Hunt | `/launchpad` |
| Acquisition Scout | `/buyability` | Review Desk | `/warroom` |
| PE Deals | `/deal-flow` | Evidence | `/research` |
| Research Notes | `/intelligence` | Methodology | `/data-breakdown` |
| System | `/system` | Practice page | `/practice/[locationId]` (EXISTS) |

### 1f. Census columns already live on BOTH DBs (ORM-mapped in `scrapers/database.py`)
`practice_locations` + `practices`: `ownership_tier` (text: true_independent / single_loc_group /
dentist_multi / stealth_dso / branded_dso / institutional), `pe_backed` (bool), `ownership_evidence_basis`,
`ownership_evidence_urls` (JSON list of http(s) URLs), `ownership_confidence` (high/medium/low),
`network_id`. Legacy: `entity_classification` (13-value detector), `ownership_status`, `affiliated_pe_sponsor`.

---

## 2. HARD TRUTH RULES (binding; violating any = regression, revert)

1. **No hardcoded census numbers** in frontend code. Every count/percentage computes from live Supabase queries. (Constants files may hold external anchors like ADA 14.6% with citation — never our own census tallies.)
2. **No legacy detector numbers presented as ownership truth.** `entity_classification` / detector floor may appear ONLY labeled as "legacy detector estimate (context)".
3. **Every displayed number states its source class**: `census-reviewed` / `unreviewed` / `undetermined` / `held` / `legacy detector` / `PE deal context`.
4. **`ownership_tier` = the ONLY ownership truth layer** once synced. `entity_classification` = context only, never primary in any census-era surface.
5. Tier semantics (ratified): **T1** = one dentist who BOTH owns AND operates one location; **T2/T3** = dentist-owned not solo; **T4/T5** = DSO/PE/corporate; **T6** = institutional.
6. **Undetermined and holds stay VISIBLE** — never rolled into another bucket, never hidden.
7. **Labeling law:** the broad headline is **"Not Solo Owner-Operated %"** — NEVER "DSO-affiliated %". Conventional DSO/PE = T4+T5 only; only THAT number may sit next to the ADA 14.6% per-dentist anchor (with the unit caveat).
8. Headline buckets (exactly five, from DECISION doc): True Solo Owner-Operated (T1) / Dentist-Owned Not Solo (T2+T3) / DSO-PE-Corporate (T4+T5) / Institutional (T6) / Unresolved (undetermined + holds + unreviewed). Never collapse into a single "corporate %".
9. **No fake precision from thin data**: no 100-point job scores off empty intel; cap scores and say why; "Needs research" is an honest state.
10. **Unit discipline stands**: NPI rows ≠ locations ≠ GP denominator (CLAUDE.md cheat-sheet). MA/Boston stays parked. Never DELETE from practices. Floor CI guards untouched.

---

## 3. The six deliverables (Codex brief — all must exist by end of the session arc)

1. **Route-by-route redesign spec** — for every page: actual purpose, what data it shows, what legacy/fake must be removed or relabeled, what actions a user takes, which components are reusable, and rename/merge/hide/demote verdicts. Write to `RESEARCH_HOME/SPEC_TRUTH_APP_ROUTES_20260704.md` (or dated successor).
2. **Frontend data contract** — tables, fields, status meanings, source-of-truth hierarchy (census > holds/triage > legacy detector > PE deal context), the five headline buckets, the six source classes, and the canonical helper API (e.g. `getOwnershipRecord(location)` returning `{tier, bucket, statusClass, confidence, evidence[]}`). Write as BOTH a doc and a typed module `dental-pe-nextjs/src/lib/census/ownership-truth.ts` — the code IS the contract; every page imports it, none reimplements it.
3. **Legacy purge list** — every UI claim/component presenting detector output as ownership truth, each with fix = remove / relabel / demote. (Known suspects: corporate-share KPIs off `zip_scores.corporate_location_count`, `classifyPractice()`-driven "Corporate/Independent" chips in census surfaces, CorporateBandBar as a headline, scoring.ts ownership points from entity_classification, consolidation map colors.)
4. **Phased implementation plan** (see §4) with per-step verification commands.
5. **Future-session protocol** — harden `PLAN_FABLE_DISTILLATION_20260703.md` into actual skills + this charter's rules so Opus/Codex successors cannot regress truth rules. Includes the dry-run test loop.
6. **Codex handoff note** — what Codex implements next, file-by-file, with the data contract as the interface.

## 4. Phases (execute in order; each ends with `npm run build` ✓ + a banking commit)

- **Phase 0 — Honesty fixes (works even pre-sync).** Kill/relabel every truth-rule violation reachable today: source-class labels on all KPIs, /system sync-state honesty ("Lane A wave 1 written locally, live sync pending" if applicable), demote detector claims. Small diffs, big integrity.
- **Phase 1 — Directory + Job Hunt on synced census.** Directory (`/job-market`) becomes the front door: search + filters (tier, confidence, evidence status, network, sponsor, city/ZIP, status class); rows link to `/practice/[locationId]`. Job Hunt (`/launchpad`) rebuilt for a D4 seeking a Chicagoland associate job: three honest lanes (Verified job targets / Promising leads / Needs research), capped explainable scores.
- **Phase 2 — Practice page + global search.** `/practice/[locationId]` as THE core object: tabs Ownership & evidence / Job hunt intel / Acquisition-succession / Network siblings / Raw source audit.
- **Phase 3 — Ownership truth bar, Acquisition Scout reframe, Review Desk.** Ownership (`/market-intel`): the five-bucket stacked truth bar. Acquisition Scout (`/buyability`): acquisition/succession framing on census T1/T2 + age + intel. Review Desk (`/warroom`): ops/QA workbench — holds (91), triage (649), unresolved, duplicate/closure queues, audit failures, PM decisions.
- Then: PE Deals demoted to context; Home recomposed from truth components; Methodology updated.

## 5. Session discipline

- **Fable-direct, no agent fleets.** This is design + surgical code work; agents burn tokens and add drift. At most one Explore agent for a codebase question you can't answer with 2–3 greps.
- **Budget order if tokens run short:** data contract module (deliverable 2) > Phase 0 > Directory > succession protocol (deliverable 5) > everything else. Reserve ≥10% of the session for deliverable 5 — it pays for every future session.
- Bank per milestone: frontend commits in `dental-pe-nextjs` (small, buildable, each passes `npm run build` + F27 vitest), spec/protocol docs in main repo. Push frontend only when the user says deploy (push = live).
- Numbers in specs get a recheck command next to them, never a bare value.
- If Supabase sync is still pending at session start: do Phase 0 + deliverables 1–3 (docs + contract module compile without live data), and surface the sync commands to the user again.

## 6. Kickoff prompt (paste this to start the new Fable session)

> Read `data/dso_research/RESEARCH_HOME/SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md` and execute it.
> First verify ground state §1 (local census counts, Supabase sync status, frontend git log), then
> proceed: deliverable 2 (data contract doc + `ownership-truth.ts`), Phase 0 honesty fixes, then
> Phase 1 Directory + Job Hunt, banking each milestone. Hard rules §2 are binding. Reserve budget
> for deliverable 5 (Opus succession protocol per PLAN_FABLE_DISTILLATION). Do not run agent
> fleets. Do not run any Supabase sync without my explicit go.
