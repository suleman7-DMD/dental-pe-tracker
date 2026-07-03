# Chicagoland Corporate-Floor → Reality Plan (2026-06-20)

> ⛔ **SUPERSEDED 2026-06-20 (later same day) — read `data/dso_research/RESEARCH_HOME/` FIRST.** That folder is now the authoritative cross-session operating system for this work (README → MASTER_PLAN → PROGRESS.json → LEDGER.jsonl → CENSUS_PROTOCOL → FINDINGS → SESSION_LOG). This file is kept for HISTORY only. **Two user rulings post-date everything below:**
> 1. **NO ANCHOR.** Stop anchoring "consolidated %" to the ADA 14.6% (or any external number). The 5% floor is "definitively false" (too low). The true % is derived ONLY from the per-practice census of all ~4,439 IL GP practices, published WITH coverage %. The "floor→anchor band" framing in §0 and §9 below is **revoked** — do not use it.
> 2. **Model:** 6 ownership tiers + a `pe_backed` flag + Undetermined, via a new `ownership_tier` column. Two headlines: Consolidated % (T2+T3+T4+T5) and DSO/PE % (T4+T5). Hand-verified census of all ~4,439 is a first-class deliverable. See RESEARCH_HOME/README.md.

**Author:** Opus 4.8 session, 2026-06-20. **Status:** APPROVED-TO-PLAN, NOT-YET-EXECUTING (user chose "plan first, don't flip yet"). No classification changes have been made. This document is the execution contract for the next working session(s).

---

## 0. Objective

Move the **Chicagoland corporate GP-location share** from the documented **5.58% floor** toward defensible reality, where *corporate = branded DSO (e.g., Aspen) OR stealth/friendly-PC DSO (e.g., a Heartland office under a local name)* and *independent = any non-corporate GP practice*. **Scope: general dental practices only.** End state: accurate per-ZIP corporate %, honest floor→anchor band, accurate maps/charts, every Chicagoland GP location classified true-independent / stealth-DSO / branded-DSO with documentary evidence. **Boston is PARKED** (see §6).

---

## 1. Verified ground truth (reconciled 2026-06-20)

- **Floor: 268 / 4,801 GP locations = 5.58%.** IL/CHI **249 / 4,439 = 5.6%**; MA/BOS 19 / 362 = 5.25%.
- **Supabase = SQLite (synced, live, read-back verified):** corp locations 268, corp NPIs 1,152, da_unverified 179, total practice_locations 5,657. **The 2026-06-19 work IS live; the CLAUDE.md "sync must be verified" caveat is stale.** No sync action outstanding.
- **NPI-level corporate:** 1,152 (dso_regional 680 + dso_national 472). **Location-level corporate:** 268 (dso_national 186 + dso_regional 82).
- **The undercount is structural and provable:** **119 of 245 IL ZIPs (49%) read exactly 0% corporate**, including the densest/most affluent markets — Lincoln Park 60614 (0/48), Wicker Park 60622 (0/48), Park Ridge 60068 (0/49), Arlington Heights 60005 (0/39), Buffalo Grove 60089 (0/38), Northbrook 60062 (0/28). Median ZIP = 2.33%; mean 5.59% is carried by 15 ZIPs >20%. Zero corporate in a 48-practice Lincoln Park is a **detector coverage gap, not reality.**
- **ADA HPI per-dentist anchor (honest upper bound, different unit):** IL 14.6%. Never present the floor as "the rate"; keep the band.

## 2. What is already done (do not redo)

- **DSO-locator exact-match promotions (committed a08e538, 2026-06-19):** 14 GP locations via normalized street+ZIP match against DSO locator pages (Heartland ×2, Dental 360 ×2, Dental Dreams ×3, All Family/UDP ×7). Evidence: `data/dso_research/il_verified_locator_promotions_20260619.json`.
- **Duplicate-location cleanup (2026-06-19):** 5 suite/unit variants → `duplicate_location`, excluded from all denominators. Evidence: `data/dso_research/duplicate_location_cleanup_20260619.json`.
- **flip_queue HIGH tier (21): fully worked** — 15 promoted to corporate, 5 specialist/excluded, 1 no-location. **0 pending.**
- **False-positive discipline already applied:** Evenly (placeholder EIN `000000000`/`125555555`), Data-Axle synthetics (`da_unverified`, 179), Trinity Health flagged as hospital (not PE-DSO).

## 3. What's left — three tranches

### Tranche A — finish in-flight documentary work (highest confidence, smallest effort)

**A1. 18 medium-tier flip_queue candidates still independent today** (live-checked 2026-06-20). Verify each cluster via WebSearch/locator, promote confirmed, HOLD the rest:
- **Two Rivers Dental / Elgin 60120** — Bushra Zafar, Filza Zaidi, Samar Syed, Two Rivers Dental PC. (Dr. Reem Shafi friendly-PC group — the "Eco Dental" pattern.) Likely PROMOTE on verification.
- **EIN-731689410 Pulaski cluster / Chicago 60629** — Brite Dental Marquette Pulaski, Siddharth Bansal, Dental 360 Pulaski. Already corroborated: the 2026-06-19 promotions flipped Dental 360 Armitage + Kimball, which share EIN 731689410. Strong PROMOTE candidate.
- **Carol Stream 60188** — John Sullivan, Nicole Nimry, Samreen Ahmed, Simply Dental. Verify shared ownership.
- **Mt Prospect 60056** — Chiambas, Khan, Ryan ×2, Pollina. ⚠️ Previously flagged as a genuine single multi-specialty building (EIN 363676741), NOT a chain. Verify carefully; default HOLD.
- **Align Dental Group Chicago 60618**, **Smile Town Addison 60101** — verify.

**A2. PE-platform scratch leads → formalize into evidence JSON, then promote** (the "connect-the-dots" work the previous session opened in the loose `data/*.txt` files):
| PE sponsor | Platform brand | Action |
|---|---|---|
| Gryphon Investors | Midwest Dental | Map all watched-IL GP locations via `affiliated_pe_sponsor`/`affiliated_dso=GRYPHON` or brand=Midwest Dental; locator-verify each; promote GP+watched only |
| Shore Capital | Great Lakes Dental Partners | Same (Chicago 60659/60602, Geneva, Naperville, Palos Heights) |
| JLL Partners | DCA | Verify Ferdman/Izzo Cumberland Ave; ⚠️ resolve the Izzo 4501-vs-4701 N Cumberland split before flipping |
| Calera Capital | Panos Dentistry 60630 | Verify |
| ADMI Corp | Aspen Dental | Ensure the Emily-Chen Schaumburg Aspen office location is corporate |

**Gating for A2 (all required):** drop placeholder EINs (`000000000`, `125555555`); GP only; ≥1 corroborating already-corporate member at the EIN/brand OR a locator/web hit on the specific office. Exclude Evenly (junk) and Trinity Health (hospital).

### Tranche B — sweep the 119 zero-corporate ZIPs (the real gap-closer)

Prioritize dense/affluent ZIPs first (60614, 60622, 60068, 60005, 60089, 60062, 60187, 60613…). Per ZIP, run all four free/documentary methods, loop until swept, **log what was checked and found (no silent caps):**
1. **Name-chain (deterministic):** re-run `detect_name_chains.py` across ALL watched ZIPs; surface names in 3+ ZIPs (proven live example: **PROCARE DENTAL GROUP P.C.** in 60614/60068/60005, all currently independent). Web-verify single ownership → promote.
2. **DSO-locator scraping expansion (the proven 06-19 method):** extend `dso_web_locators.py` to brands operating north-side/north-shore + suburbs (Dental Dreams, Dentologie, Brighter Dental, Elite Dental Partners, DecisionOne, Specialty Dental Brands, plus nationals Aspen/Heartland/Western). Exact street+ZIP match → promote with locator provenance.
3. **Per-candidate WebSearch verification (free, done in-session):** for highest-buyability independent GP locations in zero-corp ZIPs, search "&lt;name&gt; &lt;city&gt; dentist owner / DSO / acquired / parent company." Promote only on documentary hit. Parallelizable via subagents returning structured evidence rows that the main session gates before any flip.
4. **Group-billing / NPPES re-mine:** exploit `parent_org_lbn`/`parent_org_tin`/provider-reassignment columns already present.

### Tranche C — frontend truth pass (after the floor stabilizes)

- Re-audit every page/tab/map/chart against the new per-ZIP distribution. **Maps (user is skeptical of the dots):** confirm dot/hex counts come from deduped GP locations (not NPI rows); confirm per-ZIP coloring = `corporate_location_count / total_gp_locations`.
- Keep the honest band; update `consolidation-honesty.ts` `CONFIRMED_PER_DENTIST_CORPORATE` as flips land.
- IL-only default scope everywhere (Boston parked, §6).
- `npm run build` + F27 vitest green.

## 4. Binding rules for every promotion batch (do not regress)

- **GP only.** Corporate = `dso_regional` + `dso_national`. Specialists tracked separately, NEVER in the GP denominator.
- **Documentary evidence per flip.** Acceptable: DSO locator exact street+ZIP match; PE-sponsor + real shared EIN across 3+ ZIPs with ≥1 corroborating corporate member; the NPI's own legal/parent name = a DSO; a web-verified brand. **Never single weak signal. Never re-promote a demoted location_id** (`reclassify_verified_corporate_il.py` globs `il_false_corporate_demotions_*.json`).
- **Free/student data only.** No paid Anthropic batch — verification is done in-session via WebSearch/WebFetch.
- **Headline KPI = per-LOCATION floor** from `zip_scores`; denominator = total GP locations. Never the floor as "the consolidation rate"; never fabricate a number between floor and ADA anchor.
- **Raw-SQL flips bump `updated_at`.** Sync via `_sync_floor_tables_only.py` + `_sync_practices_changed_rows.py --since DATE`; **never `--tables practices` alone** (TRUNCATE CASCADE). Read-back verify both legs.
- **CI:** rebase `FLOOR` / `FLOOR_NPI` `expect_min` UP with the new evidence file; DOWN only with demotion evidence.
- `entity_classification` canonical. Keep F27 vitest green.
- Each batch writes a dated `data/dso_research/il_*_YYYYMMDD.json` evidence file and a git commit referencing it.

## 5. Expected trajectory

- **Tranche A:** ~+10–25 GP locations → floor ~5.6% → ~6.0–6.5%.
- **Tranche B:** the bridge toward reality — eliminates zero-corp dense ZIPs, produces honest per-ZIP variance. flip_queue's all-tiers upper bound was ~13.35% per-location, but that requires verifying the long tail; documentary-only outcome will land below that but well above 5.58%, with NO implausible 0% dense ZIPs. The ADA 14.6% per-dentist anchor stays the band's upper bound (different unit).

## 6. Boston (MA) — PARKED (user directive 2026-06-20)

> User: "leave as-is, focus IL … I want it removed from distractions on all workings of this app … Boston eventually, but it's gonna take a long time to get Chicagoland correctly."

- **Do NOT delete MA data** (21 ZIPs, 362 GP locations). It stays functional in the live app.
- **Do NOT investigate, debug, classify, or promote MA rows** until Chicagoland is declared complete by the user.
- **All analysis/tooling defaults to IL scope.** When a future session hits an MA row while debugging, that is out-of-scope noise — skip it, don't chase it.
- A CLAUDE.md banner records this so future sessions don't waste time on Boston.

## 7. Open items / pending decisions

- **`scrapers/merge_and_score.py` (uncommitted):** adds a `state` filter to per-ZIP denominators. Verified impact = 1 location + 3 practices (safe near-no-op). Decision: commit only after a `merge_and_score.py` run confirms the floor stays 268. Until then, held.
- **Loose research artifacts** (`data/*.txt`, evidence JSONs): organize under `data/dso_research/` with a README and commit for durability (non-destructive) — do at start of execution.
- **Boston cordon mechanism:** doc-only for now (CLAUDE.md banner + IL-default scope). An optional `watched_zips.active` flag (MA=0) is available if the user later wants MA hidden from the UI too — not done now ("leave as-is").

---

# 8. ⏸️ PAUSED-STATE RECORD — 2026-06-20 (durable continuation block)

> **Read this first on resume.** The user paused mid-investigation to wait for usage to reset. Four read-only agent teams are intelligently paused. **Nothing in the DB, no classifications, no commits, no files (other than this plan) were changed** — all work so far is read-only investigation. Resume only when the user explicitly says **"green light"** (or equivalent go-ahead).

## 8.1 THE MAJOR REFRAME — this is now the real objective (supersedes §0's "raise the floor" framing)

The user re-scoped the whole effort. **The task is NOT incrementally nudging a single "corporate %" floor from 5.58% toward ADA's ~15%.** It is a **complete architectural transformation** of the live app (dental-pe-nextjs.vercel.app) from a binary *corporate (PE-backed) vs independent* model into a **detailed, investigated ownership DIRECTORY** of every Chicagoland watched-ZIP GP practice, each classified into a real ownership hierarchy.

**User's verbatim end state:** *"a directory of all chicagoland watched zip practices that classifies all practices into its correct ownership structure as single owner true independent, stealth dso of owner dentist who actually owns multiple practices with diff branding or even same branding whether pe backed or not, group practice single location whether pe backed or not, all those ownership nuances."*

**The app serves 3 goals (user's framing):**
- **Goal 1 — PE deal-flow + ownership NPI tracking** ("which is NOT what ur working on").
- **Goal 2 — full directory DB of all watched-ZIP Chicagoland practices + their ownership hierarchy** ← **THE CURRENT WORK.**
- **Goal 3 — use that DB later for job search + acquisition-potential scoring** (future).
- *"inbetween these goals are consolidation maps and dashboard numbers and other stats that are very helpful but must be truthfully accurate."*

**Methodology demands (user, verbatim intent):** deploy agent teams with ultrathink; coordinate; integrate ALL info from every analyst transcript + agent; cross-reference; consider every blind spot; *"dig deep before we get close to formulating a plan."* Identify what's been over-investigated minute detail vs higher-order levers. The final plan must include a **revamped app** — what warroom / launchpad / market-intel / job-market / etc. display, what to remove, what to fix. **NEVER silent-default to independent; mark genuinely ambiguous cases "undetermined."**

## 8.2 Target ownership data model (designed this session — the spine of the revamp)

Store **atomic orthogonal axes** per location, **derive the tier**. Four axes:
- **Reach:** single-location / 2–4 locations / 5+ locations (the core lever; detectable FREE from shared owner identity).
- **Control-capital:** dentist-owned / MSO-managed friendly-PC / PE-backed / other-corporate.
- **Branding:** unified brand / local names (the "stealth" axis).
- **Location-structure:** solo / family group / unrelated-dentist group.

**Derived tiers:**
- **T1 True Independent** — single-location, dentist-owned, solo or family. The NARROWEST tier; **EARNED, never defaulted.**
- **T2 Doctor-owned consolidation, non-PE** — T2a single-location group of unrelated dentists; T2b multi-location dentist-owned mini-chain.
- **T3 Stealth DSO** — PE/MSO-backed, operating under local names.
- **T4 Branded DSO** — unified national/regional brand (Aspen, Heartland…).
- **Undetermined** — explicit; never collapsed into independent.

**Derived metrics:** Consolidated % = T2+T3+T4; DSO/PE penetration % = T3+T4 (the ADA-comparable ~15% number); True-independent % = T1; Undetermined % shown explicitly.

**Schema decision (settled):** add a **separate `ownership_tier` column** (+ the atomic-axis columns), NOT new `entity_classification` enum values. Rationale: blast radius — a new column touches ~3–5 files; new enum values touch ~22 TS files with no detection chokepoint (5 CORPORATE_CLASSIFICATIONS copies + inline string literals across 10+ sites; `entity_classification` typed as bare string) → silent-failure-prone. Triple-supported (separation-of-concerns + Agent A blast-radius analysis + the binary model is what we're replacing, not extending).

## 8.3 Corrected load-bearing findings (do NOT revert to the old stories)

- **Engine A (affiliated_dso propagation) is a DEAD bulk lever — corrected from the "117 clean / +2.6pts / 8.24%" claim in analyst Sessions 1 & 3.** Forensics: of 121 candidates only **1** (Southland Smiles → Heartland, 60422) is `dso_regional` at NPI level; the other 120 carry only the noisy Pass-2 `affiliated_dso` address-match tag. Address match vs current `dso_locations`: exact 2, street-core 4, **no-match 115**. Obvious co-location leaks (Kim Dental→Aspen, Leahy→Comfort, Dental Limited→Familia — brands that never run under local names). **117 is a VERIFICATION QUEUE, not a flip set. Only 1 free defensible flip.**
- **The denominator is SOUND (Analyst 3 + Agent B, file-line-verified).** The 558 "org-shells" are REAL NPPES organizations (provider_count=0 is an NPI-1→address linkage artifact, not a phantom). Only ~87 true-duplicate rows (~2%, 79 clusters) need collapsing. **The floor is a NUMERATOR / detector-coverage problem, NOT denominator inflation** → close the gap by FINDING real corporate practices, not by shrinking the base. Evidence: `data/dso_research/il_denominator_pressure_test_20260620.json`.
- **The freeze (not a race) is the durability mechanism, correctly understood.** `dedup_practice_locations.py` and `reclassify_locations.py` are NOT in `refresh.sh` → `practice_locations` is frozen at last manual build. `merge_and_score.py` [8/11] recomputes `zip_scores.corporate_location_count` FROM `practice_locations.entity_classification` every run; nothing in `refresh.sh` rebuilds that table → **setting location-level classification directly is durable.** (Earlier "pipeline-race" story was WRONG; corrected.)
- **Transitive-chaining is the trap for Engine B.** Naive union-find that hard-merges all 5 owner-identity keys chains unrelated entities via weak keys (surname PATEL → 71-loc blob; shared registered-agent mailing → BDD/KKR+Gryphon 50-loc blob), reproducing the documented 1,072-false-positive disaster (`dso_classifier.py:742`). Agent B's de-chaining fix (for the eventual Engine B rebuild): EIN-anchored grouping; demote authorized-official / mailing / phone to corroboration-only; surname block-list; mailing-hub suppression (≥5 entities ⇒ suppress); multi-PE invalidation; **pair-level (not cluster-level) scoring.**

## 8.4 Ground-truth vs stale docs (fix during execution, AFTER green light)

- **DB truth (verified 2026-06-20):** floor **268 / 4,801 GP = 5.58%** (IL 249/4,440 = 5.61%, MA 19/362 = 5.25%); **1,152 corp NPIs** (dso_regional 680 + dso_national 472).
- **CLAUDE.md (root, status M) is STALE:** cheat-sheet still says 261/4,811 = 5.43% / 1,119 NPIs. Also wrongly references `practice_to_location_xref` — **that table does NOT exist**; the practice↔location link is `practice_locations.primary_npi` / `org_npi`. `scrapers/CLAUDE.md` is even staler (5.27%). Reconcile all three on execution.
- **Durability-spine cleanup (non-destructive, do at start of execution):** commit the 22 untracked `data/*.txt` PE-platform scratch leads + evidence JSONs + `build_ownership_census.py` under `data/dso_research/` with a README; `.gitignore` the 230 MB `data/dental_pe_tracker.db.pre_phase4_bak` (do NOT commit it).

## 8.5 The four PAUSED agent teams (resume protocol below)

All four are **read-only**, launched in one parallel batch this session, then paused via SendMessage. **Session/agent namespace: `@session-fdca4c9e`.** Each was told: stop investigating immediately, checkpoint (done / partial findings / remaining TODO), return the checkpoint, come to rest, and **NOT resume until an explicit message containing "GREEN LIGHT".** All four acknowledged (`success:true`).

> ✅ **ALL FOUR AGENTS COMPLETE — full findings persisted to disk (verified 2026-06-20).** Every agent finished its charter and came to rest; nothing is still in flight. The two Explore agents cannot write files, so the team-lead persisted their full verbatim reports. **No green light is blocking any further investigation — the agents are DONE, not mid-task.** Green light now governs only (a) any *follow-up* drill-downs and (b) starting EXECUTION (synthesis → flips → revamp). The persisted artifacts are sufficient to do the full synthesis without resuming any agent.

| # | Agent name | Type | Charter | Persisted artifact (COMPLETE) |
|---|---|---|---|---|
| 1 | **DataMagnitude** | general-purpose | Deterministic ownership-tier distribution + classification ceiling; **de-chained** owner-identity clustering (EIN-anchored, per Agent B fix); rough consolidated-% magnitude from free signals | `_pause_DataMagnitude_20260620.md` (checkpoint) + **`ownership_magnitude_20260620.json`** (24KB, 7-task full deliverable: column inventory, owner clustering, distribution, branded-DSO coverage, group-at-single-loc, deterministic ceiling, headline magnitude) |
| 2 | **FrontendOwnership** | Explore (read-only) | IA teardown of **/warroom, /launchpad, /job-market, /market-intel** — every ownership/corporate surface with file:line, G1/G2/G3 tags, what changes / adds / removes for the directory model | **`_report_FrontendOwnership_20260620.md`** (40KB, full verbatim report — persisted by team-lead) |
| 3 | **FrontendCrossCut** | Explore (read-only) | IA teardown of **/, /deal-flow, /buyability, /research, /intelligence, /system, /data-breakdown** + cross-cutting machinery (`consolidation-honesty.ts`, `entity-classifications.ts`, `scoring.ts`, `design-tokens.ts`, every corporate-% surface, all CORPORATE_CLASSIFICATIONS copies) | **`_report_FrontendCrossCut_20260620.md`** (21KB, full verbatim report — persisted by team-lead) |
| 4 | **ContradictionSweep** | general-purpose | Doc-vs-DB contradiction ledger; ownership data-asset inventory; blind-spots / over- vs under-investigated audit | `_pause_ContradictionSweep_20260620.md` (comprehensive checkpoint incl. full key findings) |

All artifact paths are under `data/dso_research/`. Supporting earlier scratch (same session): `ownership_census_20260620.json` (582KB — transitive union-find census, **needs de-chaining before use**, §8.3) and `il_denominator_pressure_test_20260620.json` (12KB — denominator soundness evidence, §8.3).

**Headline magnitude finding (DataMagnitude, task7):** DSO/PE penetration (T3+T4) = 5.61% confirmed floor, likely **6.9–7.9%**; Consolidated (T2+T3+T4) = **10–19%** range. Core reframe confirmed empirically: the binary model only ever captured branded T4 — **T2 dentist-owned multi-site groups (an additional ~5–13%) were never surfaced by the taxonomy.** ~84.2% of locations are confidently tier-assignable from in-DB data alone; ~700 (15.8%) are genuinely ambiguous T2-vs-T3 and need the web-verification last mile. Priority T3 candidates (corporate-officer titles on independent-classed locs): BRUNETTI/R (7 locs, PROCARE DENTAL), GONZALEZ/S (7 locs, DENTAL TOWN), JORBIN/J (5 locs, BDD chain).

**Highest-leverage free lever (ContradictionSweep + DataMagnitude agree):** **`practice_intel` mining** — **289 independently-classified IL practices already carry AI dossiers naming a specific DSO or stating "NOT a solo/independent"** (with web citations attached), and 1,062 rows contain "acqui*" language; none of it feeds back into `entity_classification`. Plus `mailing_address` (95.6% coverage) and `authorized_official_last_name` (3,409 rows) clustering — all free, deterministic, in-DB, currently unmined.

> ⚠️ **flip_queue correction (ContradictionSweep):** root `CLAUDE.md` says `flip_queue_b_union.json` holds 315 candidates (17/15/283); the actual file has **1,264 candidates (21/89/1,154)** with a stale 5.27%/4,608 floor projection. Reconcile during execution.

**Agent IDs:** `DataMagnitude@session-fdca4c9e`, `FrontendOwnership@session-fdca4c9e`, `FrontendCrossCut@session-fdca4c9e`, `ContradictionSweep@session-fdca4c9e`.

**Resume protocol (on user green light):**
1. `SendMessage` containing **"GREEN LIGHT"** + any refined instructions to each of the four agent IDs (they hold their full context — do NOT relaunch; relaunching loses their in-progress findings).
2. If an agent's session is gone (TaskStop/TaskList showed these Agent-tool background agents are NOT in the task registry — only SendMessage by name worked), fall back to relaunching with the same charter from this table.
3. Collect all four checkpoints + the two earlier agents' outputs (pipeline-map "Agent A", census-engine "Agent B").
4. **Synthesize everything into the final integrated plan:** the `ownership_tier` data model (§8.2), the deterministic-first census build (de-chained Engine B per §8.3), per-practice web verification for the last mile (PE-vs-dentist on multi-loc clusters; ambiguous solos), and the full app revamp (§8.1 G1/G2/G3 IA, what to remove/fix, maps/numbers truth pass).
5. Only THEN, with user sign-off, begin execution (durability spine → ~87-row dedup → Engine B rebuild → verification → tier population → frontend revamp → sync → CI rebase).

## 8.6 Hard constraints still binding (carry into every step)

Boston PARKED (§6); "plan first, don't flip yet" (no classification changes without sign-off); never DELETE from `practices`; every flip carries documentary evidence, GP-only, never single-weak-signal, bumps `updated_at`; never present the floor as "the consolidation rate" and never fabricate a number between floor and ADA anchor; sync via `_sync_floor_tables_only.py` + `_sync_practices_changed_rows.py --since DATE`, **never `--tables practices` alone**; DB gzipped for git push; **commit/push only when the user asks.**

---

# 9. ▶️ EXECUTION PLAN — post-green-light synthesis (2026-06-20)

> **Green light received 2026-06-20.** User: *"green light. go. take extensive time to review the task at hand and dont just blindly start. make sure to be rigorous in knowing what needs to be done then continue exactly as you were. restart the agents with fresh context."* The four investigation agents are COMPLETE (§8.5); their findings are fully persisted. This section is the synthesized, rigorously-reviewed execution contract that integrates ALL four agent reports + the two earlier engine agents. Fresh execution agents launched per the user's "restart with fresh context" directive.

## 9.0 Two-layer tier model (the key architectural insight that resolves the whole effort)

The ownership tier is **NOT** a pure function of `entity_classification`. A T2b dentist mini-chain hides as 5 separate `solo_established` rows; a T3 stealth DSO hides as `small_group`/`large_group`/`solo`. So we build the tier in **two layers**:

- **Layer 1 — STRUCTURAL tier (`classifyTier(ec)`), free & immediate, no new data.** Maps existing classes onto the honest hierarchy using the `ENTITY_CLASSIFICATIONS.category` field that ALREADY exists: `solo`→**T1**, `group`→**T2a** (single-loc group), `dso_regional`→**T3**, `dso_national`→**T4**. This alone replaces the dishonest binary "corporate/independent" with a 4-tier directory on every surface — a massive honesty upgrade shippable before any investigation lands.
- **Layer 2 — INVESTIGATED tier (`ownership_tier` column + atomic axes), evidence-driven.** Refines Layer 1 using the de-chained ownership census (REACH: moves clustered solos → **T2b** mini-chains) + verification (CONTROL-CAPITAL: moves confirmed PE/MSO-under-local-name → **T3**). Genuinely ambiguous → **Undetermined** (never silent-defaulted to independent). PE flag (`affiliated_pe_sponsor`) is an **orthogonal cross-cutting badge**, never a tier.

**Schema (greenfield — verified no tier column exists today):** add `ownership_tier` (+ atomic axis cols: `reach`, `control_capital`, `branding`, `loc_structure`) to BOTH `practices` and `practice_locations`, on BOTH SQLite + Supabase. NOT new `entity_classification` enum values (blast radius: new column ≈3–5 files; new enum ≈22 TS files w/ no chokepoint). Durability: `ownership_tier` is set on `practice_locations` (frozen table, §8.3) → survives weekly refresh exactly like the existing floor.

## 9.1 Magnitude targets (DataMagnitude, empirical — what "done" looks like)

- **DSO/PE penetration (T3+T4):** floor 5.61% → likely **6.9–7.9%** (true ~6–9%). ADA 14.6% is per-DENTIST (different unit), partly density-driven.
- **Consolidated (T2+T3+T4):** **10–19%** — the entire band the old binary HID (it only ever caught branded T4).
- **84.2%** of IL GP locations are confidently tier-assignable from in-DB data; **15.8% (~700)** need the web-verify last mile; **41.6% (1,846)** have NO owner anchor = the hard ceiling → many legitimately **Undetermined**.

## 9.2 Phased roadmap (dependencies explicit; gates marked)

**Phase 0 — Durability spine (SAFE, file-prep only; NO git commit until user asks).** `.gitignore` the 230MB `*_bak` ✅done. Defer root/`scrapers` `CLAUDE.md` doc reconciliation to AFTER flips settle (else rewrite twice). Stage scratch-file README; hold the actual `git add/commit` for explicit user request.

**Phase 1 — Data build (READ-ONLY DB; produces evidence JSONs; NO flips, NO live-app impact). ← FRESH AGENTS RUNNING NOW (§9.3).** Three parallel workstreams (W1/W2/W3). Independent.

**Phase 2 — Schema + Layer-1 population (additive DB writes, reversible).** Add `ownership_tier`+axes to both DBs; populate STRUCTURAL tier for all 4,440 IL GP locs from `category`. This is deterministic and safe — it only re-expresses existing classes.

**Phase 3 — Verification last mile (web search; gated on API credits).** Web-verify Phase-1 candidates (PE-vs-dentist on multi-loc clusters; the practice_intel-named DSOs; the 6 priority clusters). Confirmed → documentary evidence rows.

**Phase 4 — Apply investigated tiers / flips (DB writes WITH evidence).** Promote confirmed candidates: set `entity_classification` (where it moves independent→corporate) AND `ownership_tier`/axes at LOCATION level, bump `updated_at`, recompute `zip_scores`. Each flip carries a citation. Ambiguous→Undetermined. This is the durable floor/penetration move.

**Phase 5 — Pipeline emit (the multiplier).** `merge_and_score.py`: emit `t1/t2/t3t4_share_pct` (+ counts) on `zip_scores`. Per FrontendCrossCut: ~19 map/table surfaces read `corporate_share_pct` as-is → emitting tier shares unlocks tier-aware maps with **zero frontend logic changes**.

**Phase 6 — Frontend revamp (LIVE deploy — ⚠️ USER CHECKPOINT before deploy).** Foundation first (entity-classifications.ts `classifyTier` + T1/T2/T3/T4 arrays, kill the 5 `CORPORATE_CLASSIFICATIONS` shadows + ~15 inline literals; consolidation-honesty.ts `getCorporateTierBand`; design-tokens.ts 4-tier colors T1 #2563EB/T2 #6366F1/T3 #D4920B/T4 #C23B3B + PE badge). Then per-route (warroom tier KPIs+filters & split the "Confirmed Corporate" card into T3/T4; job-market T1/T2 split + tier columns; market-intel tier breakdown + 2nd map mode; home consolidated-% vs penetration-%; buyability "dead-end" split so T2≠dead-end). `npm run build` + F27 vitest each step.

**Phase 7 — Truth pass + sync + CI + docs.** Reconcile every number; sync (`_sync_floor_tables_only.py` + `_sync_practices_changed_rows.py --since 2026-06-20`); rebase CI guards (FLOOR/FLOOR_NPI + new tier guards); fix the 3 stale docs; gzip DB. **Commit/push only when user asks.**

## 9.3 Fresh execution agents launched now (Phase 1 — all read-only, write only their evidence JSON)

| Agent | Charter | Output |
|---|---|---|
| **IntelMiner** | Mine `practice_intel` (3,370 IL rows) for the 289 independently-classed practices whose dossier NAMES a DSO or states "NOT solo/independent," + the 1,062 "acqui*" rows. Extract npi, location_id, current ec, named brand/parent, exact snippet + citation URL, proposed tier (T3/T4), confidence. The single highest-leverage FREE lever. | `data/dso_research/intel_mined_candidates_20260620.json` |
| **CensusEngine** | REBUILD the ownership census **de-chained** (Agent B rules: EIN-anchored grouping; official/mailing/phone = corroboration-only; surname block-list; mailing-hub suppression ≥5; **multi-PE & multi-brand invalidation**; pair-level not cluster-level scoring). The existing 582KB `ownership_census_20260620.json` is the FLAWED transitive one (c2456 = 71 locs / 49 ZIPs / 4 brands / 3 PE sponsors) — DO NOT use it. Output clean REACH clusters → T2b mini-chains (reach 2–4 / 5+) and T3 stealth candidates, separately. | `data/dso_research/ownership_census_dechained_20260620.json` + rebuilt `scrapers/build_ownership_census.py` |
| **DeterministicCandidates** | Materialize actionable NPI/location_id lists: (a) 9 exact ZIP+phone `dso_locations` matches → T4; (b) 65 corporate-title-on-independent → T3 screen; (c) the 6 priority clusters (BRUNETTI/PROCARE, GONZALEZ-S/DENTAL TOWN, JORBIN/BDD, GONZALEZ-O/PRAIRIE, TSALIAGOS/METROSMILES, LABINOV/D2) with member rows. Screen EVERY candidate against the false-corporate demotion blocklist + placeholder-EIN traps (Evenly `000000000`, Gryphon `125555555`). | `data/dso_research/deterministic_candidates_20260620.json` |

After all three land: I (team-lead) dedup/union their candidates into a single evidence-graded queue, then proceed to Phase 2 (schema) and gate Phases 3/4/6 appropriately.

## 9.4 Hard gates (do NOT cross without an explicit user checkpoint)

1. **Live frontend deploy (Phase 6)** — outward-facing, hard to reverse. Checkpoint first.
2. **Any `git commit`/`git push`** — standing constraint; user must ask.
3. **Classification flips (Phase 4)** are evidence-gated per row but are still DB writes that move the public floor; proceed once Phase-1 evidence is synthesized, surface the diff to the user before sync-to-live.
4. Boston stays PARKED throughout. Never silent-default to independent — ambiguous = Undetermined.
