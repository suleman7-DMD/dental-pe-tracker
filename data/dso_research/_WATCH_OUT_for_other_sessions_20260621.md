# ⚠️ WATCH-OUT NOTES FOR OTHER SESSIONS — 2026-06-21

Written by Lane 1 / main session (Opus 4.8) while the **reach≥5 AO wave 2 is running**
(Workflow task `wqkeb5c3l`, runner `scrapers/ao_network_evidence.js`). Read this before you
touch the ownership census, consolidate anything, or quote a corporate/consolidated %.

---

## 0. THE ONE HARD GATE — CONSOLIDATION IS STILL FROZEN (reset DONE; now waiting on manifest + user approval)

**Do NOT write `ownership_tier`. Do NOT run `consolidate_census.py --allow-db-write`. Do NOT quote a
headline consolidated/DSO %.**
- ✅ **Wave-1 reset is COMPLETE (Gate Owner, 2026-06-21):** `practice_locations` AND `practices`
  `ownership_tier` non-null = **0/0**; `RESEARCH_HOME/LEDGER.jsonl` = **header-only**; `PROGRESS.json`
  reviewed = **0/4,439**. The old pollution (349/349/350/349) is gone. Evidence gathering may continue
  cleanly. (See §12.)
- ⛔ **But consolidation stays FROZEN** — the freeze now waits on the **Gate Owner's canonical taxonomy/
  manifest + validate-only pass AND explicit user approval**, NOT on the reset. Nobody writes
  `ownership_tier`/LEDGER/PROGRESS until both land.
- **`ownership_tier IS NULL` is now the post-reset baseline, NOT a remaining-work queue** — do not build
  target queues from it (every row is NULL by design). Build queues from `entity_classification` +
  watched-IL filter instead (`scrapers/build_evidence_targets.py`, opens DB `mode=ro`).

## 1. AO reach is a SIGNAL, not proof (corrected standard — do not regress)

A shared authorized official across NPIs is *federally-observed shared owner/officer/admin identity* —
a **high-value multi-location ownership CANDIDATE**, never ownership proof by itself. It becomes
`dentist_multi`/`stealth_dso` ONLY with a documentary corroborator (group site, owner bio, shared legal
entity, locator + exact address, PE/MSO filing). The runner enforces this in a defensive re-gate; don't
loosen it. Highest status any agent may emit is **`ready_for_validation`**, never "final".

## 2. QA corrections — ⚠️ the Belkic/Aqel "no-PE → dentist_multi" rule is SUPERSEDED (2026-06-21)

- **TAXONOMY CORRECTION (gate-owner, 2026-06-21 — overrides the old rule below):** `pe_backed=false` does
  **NOT** auto-downgrade `branded_dso`/`stealth_dso` to `dentist_multi`. The DSO tier is decided by
  **MSO / management-services / platform / DSO-brand STRUCTURE**, not by private equity. A non-PE, even
  family-owned, brand WITH an MSO/management layer stays `branded_dso`/`stealth_dso` with `pe_backed=false`.
  Downgrade to `dentist_multi` only when there is **no** MSO/management/platform/DSO-brand evidence.
  Full detail + which rows changed: `_taxonomy_correction_and_pause_20260621.md`. The runner
  (`ao_network_evidence.js`) re-gate now uses `hasPlatformEvidence()` instead of the blunt pe_backed rule.
  - **OLD (now wrong) rule, for history:** "branded_dso → dentist_multi when pe_backed !== true" — QA had
    applied this to Belkic/1st Family ×13 + Aqel/Brite ×12. Under the corrected taxonomy those must be
    re-checked for an MSO/management layer; if one exists they are DSO-tier with pe_backed=false. (1st Family
    is explicitly on the gate-owner watch list.)
- **41 of 85 wave-1 AO rows are `needs_more_evidence`** per QA (`ao_network_evidence_QA_20260621.json`) —
  they are NOT consolidation-ready. Only 44 are `pass_ready_for_validator`, and even those need QA sign-off
  before `classified`.

## 3. The validator/fleet schema mismatch is SOLVED — but PASS ≠ approved

QA's `_validator_handshake_result_20260621.json` proves AO rows validate cleanly against
`consolidate_census.py` once translated (81/85 zero-flag; the 4 ProCare "fails" are just the re-review
guard agreeing with the DB). **Translation is required first** — fleet emits `candidate_tier`/`gate_status`/
`signal_vs_evidence`/`db_artifact`; the gate wants `assigned_tier`/`status`/`evidence_basis`/`evidence_urls`/
`evidence_artifacts`. Full map: `_schema_bridge_ao_to_consolidate_20260621.md`. Key rules:
`ready_for_validation → classified` ONLY after QA; `candidate` never classified; `ao_reach → ao_cluster`
(artifact-grade but **not** final-sufficient alone — prefer a `web_verified` URL as the deciding evidence).
**Validator PASS only checks schema + DB eligibility; it does NOT re-judge evidence.** QA is the
evidence-sufficiency authority.

## 4. Wave-1 `ownership_tier` is internally CONTRADICTORY (new QA finding)

`evidence_denominator_review_20260621.json` found **8 HIGH-severity** cases where the SAME physical door
(shared phone/owner) carries **conflicting** wave-1 tiers on its duplicate rows (e.g. Barrett Dental /
Park Ridge Dentistry: `stealth_dso` vs `dentist_multi`). Wave-1 wrote tiers per NPI/DA row, not per
deduped door. **Reconcile to one-tier-per-door before any tier tally or headline %.** Another reason not
to trust the existing 349 rows.

## 5. Denominator discipline

- IL GP denominator = **~4,439** (`SUM(zip_scores.total_gp_locations) WHERE state=IL`; one CA stray
  excluded correctly). Defensible duplicate-collapse ceiling is only **75 rows → 4,364** (≤1.69% impact),
  and that's **FLAG-ONLY** — nothing has been collapsed; needs separate authorization.
- The pressure-test "**87**" dup figure is **half-unverifiable** (39 of 79 claimed clusters were never
  written to disk). Do NOT treat 87 as a confirmed collapse target.
- **No anchor.** Per the user: do NOT anchor the "true" consolidated % to ADA 14.6% or any external number.
  The 5.43%/5.61% detector floor is "definitively false / too low" — a *starting point being corrected*,
  not the answer. Compute % FROM the census WITH `coverage_pct`, label reviewed-rate vs whole-universe-floor
  separately.

## 6. Specialist exclusion (GP-only census)

The runner now flags specialist-dominant networks (ortho/endo/perio/OMS/pedo/implant-only) as
`undetermined` + "exclude from GP denominator." **Watch the RAJAN SHARMA reach-5 cluster** ("The Dental
Specialists" / "Implant Solutions") — likely specialist; do not count it toward GP corporate.

## 7. Terminology (user ruling — do not drift)

- `dentist_multi` = **"non-independent / consolidated candidate"**, NOT "corporate."
- **"DSO/PE candidate"** only for `stealth_dso`/`branded_dso` **with documentary PE/MSO/DSO evidence**.
- Two-headline model: **Consolidated** = single_loc_group + dentist_multi + stealth_dso + branded_dso;
  **DSO/PE** = stealth_dso + branded_dso ONLY. A dentist-owned brand with no PE is Consolidated but NOT DSO/PE.
- Confirmed PE subset so far: **Nittinger/Sonrava** + **Labinov/Destiny→ProSmile**. Everything else in
  wave 1 is dentist-owned-multi or dentist-branded (`pe_backed=false`).

## 8. evidence_scope — AO evidence is NETWORK-LEVEL

AO documentary evidence proves the *owner/owner-type* for the group, not that a specific address belongs
to them. In `ao_network_evidence_20260621_qa.json`: 55/85 rows are `network_level`, 30 `location_specific`.
Per-address locator confirmation is the recommended follow-up before a `location_specific` `classified`.

## 9. Lane boundaries (don't double-gather, don't collide)

- **Lane 1 / main (me):** AO/network evidence. Owns the 8 wave-1 AOs + the 14 reach≥5 AOs now running.
  Evidence files only, no DB writes.
- **Lane 2 / QA:** adversarial validation + denominator/dup review. `--validate-only` only. Don't ask QA
  to gather evidence.
- **Lane 3 / Fleet B:** practice_intel mining, exact-address DSO locator, zero-corp ZIP sweeps. Files at
  `*_fleet_b_20260621.json`. Fleet B must NOT target the AO networks I've claimed.
- **MA / Boston is PARKED** — do not census, classify, or delete; filter from view.

## 10. reach≥5 wave 2 RESULTS — DONE (workflow `wqkeb5c3l`, 14 networks / 84 locations)

Raw: `ao_network_evidence_reach5_20260621.json`. QA-normalized+bridged: `..._reach5_qa.json`
(83/84 documentary-corroborated; consolidate_ready=false on every row). **Every row is
`ready_for_validation` MAX — QA still owns adversarial sign-off; consolidation stays frozen (§0).**

Gate tally: **70 ready_for_validation / 9 candidate / 5 undetermined.** Tier tally (post 2026-06-21 taxonomy
correction): dentist_multi **42**, branded_dso **17**, stealth_dso 16, undetermined 9 (was dentist_multi 52 /
branded_dso 7 before the Hussain/Dental Dreams re-grade — see §11). **23 pe_backed=true rows across 4
documentary PE networks; Dental Dreams ×10 is branded_dso with pe_backed=false (DSO structure, no PE).**

**HARD DSO/PE findings (documentary PE evidence — the high-value corporate hits):**
- **CELIA HAYES ×7** — Heartland Dental (KKR-backed) friendly-PCs *Tru Dental Illinois P.C.* / *Dental
  Professionals of IL P.C.* (Tru Family Dental acq. Dec 2020). branded_dso. Mostly already dso_national in DB.
- **ALAN ACIERNO ×6** — DecisionOne Dental Partners (Smile Brands PE strategic investment), local trade
  names (Village Smiles, Route 64 Dental, PPD North Avenue). stealth_dso. Some already dso_regional (Park Place).
- **JAY JORBIN ×5** — Bright Direction Dental / BDD (PE: PNC Mezzanine Capital, 2024), *BDD … P.C.* shells.
  stealth_dso. (My wave-1 "BDD shells" suspicion = confirmed.)
- **DAVID RUBIS ×5** — Great Lakes Dental Partners (PE: **Shore Capital**), friendly-PCs Advanced Family
  Dental / Avid / Dental Roots / Montrose. stealth_dso. 3 already carry GLDP/Shore in federal data.
  ↳ This is the **Shore→Great Lakes** scratch lead from CHICAGOLAND_FLOOR_PLAN — now documented.

**Dentist/family-owned multi (Consolidated, NOT DSO/PE — pe_backed=false):** Gonzalez/Dental Town ×9,
Nourahmadi/Shining Smiles ×6, Tsaliagos/MetroSmiles ×6, Korkus/**Sonrisa** ×5, Khurana/Valley View ×5,
Palella/Modern Dental ×5 (site says "independently owned, not corporate"), Chang/**Precision Dental Care** ×5.
↳ **Two earlier DSO suspects CLEARED:** Korkus/Sonrisa and Chang/Precision Dental Care are dentist-owned, NO
PE — even though some Chang rows are `dso_regional` in the DB. Do not call them PE/DSO. (Several Chang/Precision
rows are dso_regional in DB but should be dentist_multi — flag for re-review, NOT a new PE finding.)

**Unresolved / excluded:**
- **RAJAN SHARMA ×5 → undetermined, EXCLUDE FROM GP.** Endodontist; "The Dental Specialists" / "Implant
  Solutions" are specialist brands. Specialist-exclusion rule fired correctly. Do NOT count toward GP corporate.
- **MILAN RONCEVIC ×5** — non-dentist CEO ("Dental Profile" / "Chicago Tooth Fairy") as AO across local-name
  practices. 1 row (1st Family Dental, Addison) ready; 4 are `candidate` (moderate stealth-DSO signal, **no
  documentary PE/MSO**). Held as candidate — do NOT promote to stealth_dso without a management-services doc.

## 11. ✅ RESOLVED — Dental Dreams (Hussain) re-graded branded_dso (gate-owner taxonomy correction 2026-06-21)

**SAMEERA HUSSAIN ×10 = Dental Dreams**, a 65+ location multi-state **family-owned DSO** with a real MSO layer
(**KOS Services LLC** runs all business ops), friendly-PC entities (*Dental Experts LLC*, *The Dental Clinic
LLC*). **All 10 are already `dso_national` in the DB.** The old blunt re-gate had forced tier=dentist_multi
because there's no PE. **The gate owner's 2026-06-21 taxonomy correction confirms my recommendation:** an MSO/
management layer = DSO structure regardless of PE, so Dental Dreams is **`branded_dso`, `pe_backed=false`**.
- **Applied** in `ao_network_evidence_reach5_20260621.json` + `..._qa.json` (rows carry `_taxonomy_corrected`;
  `_meta.taxonomy_correction_2026_06_21` documents it). New reach≥5 tier tally: dentist_multi 42 / branded_dso 17 /
  stealth_dso 16 / undetermined 9. `consolidate_ready` stays false (QA sign-off still required).
- **Runner fixed:** the blunt `branded_dso & !pe_backed → dentist_multi` rule is gone; replaced by
  `hasPlatformEvidence()` (downgrade only when NO MSO/management/platform/DSO-brand evidence). Full record:
  `_taxonomy_correction_and_pause_20260621.md`.
- **Still for QA under the corrected rule:** Webster, 1st Family (Roncevic ×1, left as-is — no MSO doc),
  Family Dental Care, Brite, and the Chang/Precision `dso_regional`-in-DB rows — re-test each for an MSO/
  management/platform layer before settling the tier.

## 12. ⛔ AO evidence gathering paused after reach≥5 pending Gate Owner manifest. reach=4 staged, not launched.

**Status 2026-06-21 (final):** the Reset/Gate Owner has **completed the wave-1 reset** — `practice_locations`
and `practices` `ownership_tier` non-null = **0/0**, LEDGER header-only, PROGRESS **0/4,439** — and is now
building the **canonical taxonomy/manifest + validate-only pass**. Evidence gathering may continue without the
old `ownership_tier` pollution, **but the bottleneck is no longer AO evidence volume — it is consolidating and
reconciling the evidence already gathered.** So the Main/AO lane is HELD:
- **Do NOT launch reach=4.** It is staged (14 clusters: Huerta, Groh, O.Gonzalez, Napier, Waheed, Takla,
  Bearden, Rempas, Pal, Nagaraj, Haralampopoulos, Parikh, Kural, Hoffman) in `ao_network_evidence.js` behind the
  ⛔ PAUSED banner. (It was briefly cleared then re-held in the same coordination turn — net: not launched.)
- **Do NOT run the reach 2–3 long tail.** No new AO agents until the manifest shows what is actually ready,
  blocked, or duplicated.
- **Consolidation STILL frozen** even though the reset is done: do NOT write `ownership_tier` / LEDGER / PROGRESS,
  do NOT run `consolidate_census.py --allow-db-write`, until the Gate Owner finishes the manifest + validate-only
  AND the user explicitly approves consolidation. (Supersedes §0's "reset not confirmed" — reset IS now confirmed;
  the freeze now waits on the manifest + user approval, not the reset.)
- Current global priorities: **Gate Owner** finishes taxonomy/manifest/validate-only · **QA** reviews only new
  files / addendum questions · **Fleet B** runs the zero-corp ZIP sweep only if explicitly cleared, else holds ·
  **Main** holds AO fan-out after reach≥5. Broadcast: `_GLOBAL_priorities_correction_20260621.md`.
