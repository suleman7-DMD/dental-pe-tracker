# ACTIVE LANE — MAIN SESSION (Lane 1: active evidence gathering)

**Role:** Lane 1 / main session. Active evidence gathering, **AO/network wave**.
**Date:** 2026-06-21. **Standard:** corrected (AO reach = candidate signal, NOT ownership proof).
**Output discipline:** evidence/review files only under `data/dso_research/`. **No DB writes. No consolidation.**

---

## WHAT THIS LANE OWNS (do not gather over these — claimed)

### A. AO/network wave — top-8 ✅ COMPLETE · reach≥5 wave 2 ✅ COMPLETE · ⛔ fan-out PAUSED after reach≥5

**⛔ AO evidence gathering paused after reach≥5 pending Gate Owner manifest. reach=4 staged but not launched.**

Gate-owner ruling 2026-06-21 (final): the Reset/Gate Owner has completed the wave-1 reset (practice_locations &
practices `ownership_tier` non-null = 0; LEDGER header-only; PROGRESS 0/4,439) and is building the canonical
taxonomy/manifest + validate-only pass. **The bottleneck is no longer AO evidence volume — it is consolidating
and reconciling the evidence already gathered.** reach=4 was briefly cleared then re-held in the same coordination
turn; the standing order is: **do NOT launch reach=4** (the 14-cluster batch stays staged in `ao_network_evidence.js`
behind the ⛔ PAUSED banner), do NOT run the reach 2–3 long tail, do NOT launch new agents, do NOT consolidate.
This lane now: hold AO fan-out · keep runner/tooling corrected · keep reach=4 staged · respond only if Gate Owner /
QA asks for clarification on AO evidence. Detail: `_taxonomy_correction_and_pause_20260621.md`,
`_GLOBAL_priorities_correction_20260621.md`.

**🟡 AO backfill queue EXPANDING 13 → 71 (await Gate Owner's REVISED list before scoping).** Per the
2026-06-21 QA-manifest-review verdict: of the 123 proposed rows, **65 are clean** (Gate Owner validates only
those), **58 protected AO-only rows are demoted** to `needs_more_evidence` with `protected_network_hold=true`
and routed to `AO_network` backfill. Routing reconciles exactly: original 56-row backfill queue (practice_intel 21
+ AO_network 13 + locator_exact 22) **+ 58 demoted = 114 total backfill**, of which **AO_network = 13 + 58 = 71**.
Main AO's ONLY next task (when cleared) is **targeted evidence repair of those 71 AO_network rows** — attach a real
documentary URL OR a durable **non-AO** ownership artifact (shared EIN cluster, shared legal entity, exact-address
DSO locator, parent/MSO filing); **AO reach alone is NOT enough.** NOT a broad wave, NOT reach 2–3, NOT reach=4.

  **Staged 13-row file is now SUPERSEDED/PRELIMINARY** — `ao_backfill_targets_13_20260621.json` covers only the
  original 13 (`_meta.status` flagged; 6 in a known AO cluster [Razzak/Image Dental, Al Azzawi/Perfect Dental
  Smile, Tsaliagos/MetroSmiles-Cicero, Bloom/Dental Mastrs Ravenswood, Salih/Teeth Matter Kedzie, Hao/Pulaski
  Smiling] + 7 need fresh discovery [Romo Dental III, Silva Dental Center, Monil P Shah, Compass Dental, Braam
  Dental, Molis Dental, Oak Park Dental Studio]). It will be **re-scoped against the revised 71-row AO_network
  list** when the Gate Owner publishes it. **No agents launched; waiting on the revised manifest/backfill list.**

**🟢 reach≥5 WAVE 2 DONE — 14 networks / 84 locations.** Raw → `ao_network_evidence_reach5_20260621.json`;
QA-normalized+bridged → `ao_network_evidence_reach5_20260621_qa.json` (consolidate_ready=false on all 84).
Gate: **70 ready_for_validation / 9 candidate / 5 undetermined**; tiers (post 2026-06-21 taxonomy correction)
dentist_multi **42** / branded_dso **17** / stealth_dso 16 / undetermined 9 (was dentist_multi 52 / branded_dso 7
before the Hussain/Dental Dreams re-grade); **23 pe_backed=true across 4 documentary PE networks.** Findings detailed
in `_WATCH_OUT_for_other_sessions_20260621.md` §§10-12.
- **DSO/PE (documentary PE):** Hayes/Heartland-KKR ×7 (branded_dso), Acierno/DecisionOne-SmileBrands ×6,
  Jorbin/BDD-PNC ×5, Rubis/Great Lakes-**Shore Capital** ×5 (all stealth_dso). Rubis = the Shore→Great Lakes
  floor-plan lead, now documented.
- **Dentist/family-owned multi (Consolidated, not PE):** Gonzalez/Dental Town ×9, Nourahmadi/Shining Smiles ×6,
  Tsaliagos/MetroSmiles ×6, Korkus/Sonrisa ×5, Khurana/Valley View ×5, Palella/Modern Dental ×5, Chang/Precision ×5.
  Korkus/Sonrisa + Chang/Precision = two earlier DSO suspects CLEARED (dentist-owned, no PE).
- **Excluded/held:** Sharma ×5 → undetermined (endodontist, specialist-exclusion fired); Roncevic ×5 → 1 ready +
  4 candidate (non-dentist CEO AO, no documentary PE/MSO — held; 1st Family on gate-owner watch list).
- **✅ RESOLVED (§11):** Hussain/**Dental Dreams** ×10 → re-graded **branded_dso, pe_backed=false** per the
  gate-owner taxonomy correction (KOS Services MSO = DSO structure; PE is a separate flag). Applied in both
  reach≥5 files (`_taxonomy_corrected` + `_meta.taxonomy_correction_2026_06_21`); tier tally updated. Runner's
  blunt rule replaced by `hasPlatformEvidence()`. consolidate_ready stays false (QA sign-off still required).

Same standard as top-8: every row `ready_for_validation` MAX, NOT final. Consolidation HELD (§ below).
Cross-session watch-out notes: `_WATCH_OUT_for_other_sessions_20260621.md`.
8 top authorized-official networks. **85 location_ids claimed/processed.** Output ->
`data/dso_research/ao_network_evidence_20260621.json` (76 ready_for_validation / 7 candidate / 2 undetermined).
Result: 4 dentist-owned-multi (Shafi/Two Rivers, Brunetti/ProCare, Sweis, Ramaha/Universal), 2 PE-backed
(Nittinger/Sonrava, Labinov/Destiny→ProSmile), 2 dentist-branded (Belkic/1st Family, Aqel/Brite). 50 of 83
**non-independent / consolidated-candidate** rows are currently independent-classed (candidate numerator
lift; NOT a floor change; the **DSO/PE** subset is only Nittinger/Sonrava + Labinov/Destiny→ProSmile).
Evidence gathering DONE — Fleet B need not re-gather; QA owns adversarial review.

**🟢 AO SCALING GO ISSUED (user 2026-06-21: "go reach >5") — wave 2 RAN & COMPLETED** as Workflow
`wqkeb5c3l` (runner `scrapers/ao_network_evidence.js`, 14 networks / 84 locations). Raw +
QA-normalized siblings written (see section above). Every row is `ready_for_validation` MAX, NOT final.
Cross-session watch-out notes written: `_WATCH_OUT_for_other_sessions_20260621.md`.

Runner re-gate (⚠️ UPDATED 2026-06-21 — the old blunt "branded_dso & pe_backed!==true → dentist_multi"
Belkic/Aqel rule is REMOVED): now uses `hasPlatformEvidence()` — downgrade branded_dso/stealth_dso →
dentist_multi ONLY when there is NO MSO/management/platform/DSO-brand evidence; a real DSO/MSO layer stays
DSO-tier even when pe_backed=false (pe_backed is a separate flag). SPECIALIST EXCLUSION retained
(ortho/endo/perio/OMS/pedo/implant-only → `undetermined`, exclude from GP).

Both original pause conditions were already CLEARED before the go:
- ✅ QA finished adversarial review → `ao_network_evidence_QA_20260621.json` (44 pass / 41 needs_more_evidence;
  25 tier corrections: all Belkic/1st Family + Aqel/Brite branded_dso→dentist_multi).
- ✅ Schema mismatch RESOLVED → QA's `_validator_handshake_result_20260621.json`: my rows validate cleanly
  against `consolidate_census.py` once translated (81/85 zero-flag; the 4 ProCare "fails" are the re-review
  guard agreeing with the DB). Confirms the user's thesis: prior mass-fail was schema-handshake, not bad rows.

Runner re-gate (2026-06-21): `scrapers/ao_network_evidence.js` — the old blunt `branded_dso & pe_backed!==true
→ dentist_multi` rule is GONE; replaced by `hasPlatformEvidence()` (downgrade only when no MSO/management/
platform/DSO-brand evidence). reach==4 targets staged in `NETWORKS` (14 clusters) behind a ⛔ PAUSED banner.

**Gate-owner ruling 2026-06-21: PAUSE AO fan-out after reach≥5.** Do NOT launch reach=4 (the staged batch) and
do NOT run the reach 2–3 long tail until the gate owner clears more gathering. (This lane never writes
ownership_tier / never uses `ownership_tier IS NULL` for queues, so it is technically safe to resume — but the
gate owner has paused it, so it stays paused.)

**⛔ CONSOLIDATION STILL HELD (separate gate).** Wave-1 reset is NOT confirmed: DB shows
`practice_locations`/`practices` ownership_tier non-null = **349** (not 0); LEDGER = 350 lines;
PROGRESS reviewed = 349. Plus 41/85 AO rows are needs_more_evidence + 25 tier corrections pending.
Nothing consolidates until Codex completes the reset and QA clears the evidence.

**Consumed QA denominator review** `evidence_denominator_review_20260621.json` (06:09): GP denominator
holds ~4,439, defensible dup-collapse ceiling only 75 rows → 4,364 (≤1.69%, FLAG-ONLY, no collapse).
Pressure-test "87" is half-unverifiable (39/79 clusters never enumerated). NEW HIGH-severity flag: 8
wave-1 `ownership_tier` contradictions at dup addresses (one door, conflicting tiers) — reinforces
reset-before-consolidate and "don't trust existing ownership_tier / IS NULL." Only 1 of my 85 AO
location_ids referenced (Shafi/Ashton overlap, consistent — no contradiction). **Does not release my AO
lane and does not unblock consolidation.** AO fan-out remains cleared-but-held per user "stage only."

**QA-prep deliverables written this session (no agents, no DB writes):**
- `data/dso_research/ao_network_evidence_20260621_qa.json` — QA-normalized: per-row signal-vs-evidence,
  `evidence_scope` (30 location_specific / 55 network_level), exact location_id/URLs/artifacts, proposed
  tier, pe_backed, status, and a `_bridge` block (`consolidate_ready=false` on every row).
- `data/dso_research/_schema_bridge_ao_to_consolidate_20260621.md` — maps fleet fields
  (`candidate_tier`/`gate_status`/`signal_vs_evidence`/`db_artifact`) → `consolidate_census.py`
  (`assigned_tier`/`status`/`evidence_basis`/`evidence_urls`/`evidence_artifacts`). Key rule:
  `ready_for_validation`→`classified` ONLY after QA; `candidate` never classified; `ao_reach`→`ao_cluster`
  (artifact-grade but not final-sufficient alone — prefer `web_verified` URL as deciding evidence).
- `data/dso_research/ao_network_next_reach5_targets_20260621.json` — **BUILT, NOT RUN.** 14 reach≥5
  clusters / 84 locations. High-priority DSO suspects flagged: Hussain (Dental Dreams), Hayes
  (Heartland/TruDental friendly-PC), Jorbin (BDD shells), Korkus (Sonrisa), Chang (Precision Dental Care).
  Caution: Sharma cluster may be specialist-dominant (verify GP vs specialist).

QA flags + reset gap (4 ProCare rows still carry `ownership_tier`) reported to Codex/QA.

| AO | network_id | reach | location_ids |
|----|-----------|------:|--------------|
| SOHAIL SHAFI | ao:SHAFI_SOHAIL | 17 | 1932e4cc87a3c456,3f2a1feba10ebd5d,cc396d3264541f15,f11458f91c91c4af,51274670f11ff36c,5a1771b772dff590,9f132406279447c6,0d9026fed63a1df0,ab575c87c6bb7249,9ee4df9470dec738,ace9e319256f2d7a,50eb637aaa38aa4b,192eeb357d406084,ad04ebea2ff68064,bb0b258dbdee424c,41e9efc177c3226c,97ce6e59218e0f7a |
| VESNA BELKIC | ao:BELKIC_VESNA | 15 | a4c2f6303bec1c06,13b38618b4b921be,00283d0319728697,d46481314c1f830f,76b01c890765d33f,6a7337dc1388e15d,0b9debb68c723377,0de79b98f75b7128,e286a73df0d2541b,dddb5ba57c531064,57f43b2b4923beb3,f4d9376d568f7c43,e0ee6d4ff57ad085,c42bbfd07106f9f2,c1526a81500dbd53 |
| RACHEL NITTINGER | ao:NITTINGER_RACHEL | 12 | e10809c55b2d7955,5ffc5f3c0a7b3102,2398f9e48e6578f9,1370e6f75164c141,f849d9ecf776fd7d,effac443b4839358,072d146be1bf9d80,056d1f180dcb8c9a,4396df02b95d7ad2,7542f13e98b7bd0d,8e92e63bee0c1cb7,902006615166d38e |
| FADI AQEL | ao:AQEL_FADI | 12 | 120e9b88cb476518,fec14748d3270a63,5a72d2c7fcf0262b,a34490266101cbd2,64e57c66fd098eed,401b88a09170a38e,0d76d8f9105e394d,8256bfff559b0760,a2fc3deda0b02a10,e24bd9e2dcfa6932,88ef34deb23c8a00,9974718d9adbc00f |
| ROBERT BRUNETTI | ao:BRUNETTI_ROBERT | 9 | 4133452316726b0d,5592bc247431d45a,d56f7d708eb28b77,2d248ca267e60284,bab0f0317a7ae69b,9abd864bb17f0358,fa6464c8c22f9bd9,7f65db0e6a313bb3,719b01502f151a50 |
| JUBRAIL SWEIS | ao:SWEIS_JUBRAIL | 7 | 5da23e850203188a,b41468a8c802391f,0f917daa7d21b189,ffe0a2b736d88ee3,06103ae3a6ed4ab0,e16ff3a9b55a8492,5e92660ad5b32980 |
| BORIS LABINOV | ao:LABINOV_BORIS | 7 | c2c46e94895cda83,d616036cc2145cf4,3f1051899da7b50d,d318648e80a552ff,9eb34e1dcb9933f8,ef079f1cfd53d7f0,e4fb4be6a4efee52 |
| AHMED RAMAHA | ao:RAMAHA_AHMED | 6 | 019f06d7def19049,9d4cd058e4525078,19c344d4755fd990,b4b2a9ed748734fb,10a173a568a7cd9f,93287e7e58ead8af |

**Fleet B must NOT target these 8 AOs** until main session finishes and releases them (per coordination update).

### B. Validation wave — already PROCESSED (candidate-grade, quarantined per Codex)
72 location_ids in `data/dso_research/census_evidence_candidates_validation_20260621.json`
(batches 60647-2, 60804-1, 60640-2, 60629-1). Fleet B should not re-gather over these; QA may adversarially
review the file. Four overlap with the AO claims above (Aqel/Brunetti) — both main-session, no conflict.

`047ce502ad2a0371,06b1a8eaf2654e4d,0884ff9f2ce7934f,0a54ab2bda7a5e9b,0c8f995db2124f57,0d76d8f9105e394d,144d631a4c4dce2b,1f895d2ecd0fdaef,2061979d9dc56775,226533cfa8898ef7,2498bbc43d47198a,28fab093c7a6a0d9,2ab7cdb707db8803,2bbd52b88750a5a8,2cb2cc7ecd4bc6ca,33bc890d9aed9341,3a2acb8b4e928c23,3bc304a7819a234f,3cee5bbb3560fda2,3d6d77fc02cdd7f6,47b29ee7e72213bb,48395fa30fb6bf6b,49d9c36c9fe9abb8,4d5aa903a1f34565,56e77b1a53f5ef7b,5cd49db66c4ee020,68ee57cb85d0f037,6bce9a480d76c1f6,6eeaf4643d34c9a4,71399b136dc5205a,719b01502f151a50,7495e79c66647036,774c59537eeee1c1,7e94b892a5388c62,7eaffe2b99d33968,8256bfff559b0760,8e5ba23753681cd3,921961e587c8ee15,99b7b4ad619fddf4,9c0581940572feb0,9c588fbf68114847,9df9c9dcb4c5f555,a31ca3008c75ab1f,a5714245bc2fae33,addadba0d25e3812,b18493944a3e66c9,b4ca7a72e2641e47,b73f749e8824d845,b7499322a2416c5d,bb6d4fb9d7b95ca4,bd13f919ca53afbc,be46a645a5533cf3,c01fc292b2a4aed8,c42bbfd07106f9f2,c469658e9024307c,c4b5b35fa16e44e5,c50218cf868c55f8,c6078e6641ef7f48,c769b00959fcdaf7,c8bcc4fb6201343a,d803fcfe4618e8a3,d97911df002def64,d9fb0c9f226a66f3,dc3d6faeeb510821,e002cdc63dfe02d2,e32ed1606301b785,e50dfc828412c437,e86d6e38d85a9aef,f3959b4a9ac8e139,fb2614131429927d,fbb43bb2a136f734,fc010516c3e5b18d`

---

## WHAT THIS LANE WILL NOT TOUCH

- **No DB writes of any kind.** No `entity_classification`, no `ownership_tier`, no `LEDGER.jsonl`, no `PROGRESS.json`, no `practices`/`practice_locations` mutations. (Reset verification is Codex's; I won't depend on `ownership_tier IS NULL` for queue scoping — my targets are built from `entity_classification` + watched-IL filter.)
- **No consolidation / promotion.** All my output is `ready_for_validation` at most; Codex's gate decides final.
- **No MA / Boston.** IL/Chicagoland only.
- **Fleet B's lanes (hands off):** practice_intel mining, exact-address DSO locator evidence, unclaimed zero-corp ZIP sweeps. I will not gather those.
- **QA's lane (hands off):** denominator/duplicate review, adversarial validation of candidate files.

## FILES THIS LANE WRITES
- `data/dso_research/ao_network_evidence_20260621.json` (AO wave output — DONE, ready_for_validation max)
- `data/dso_research/ao_network_evidence_20260621_qa.json` (QA-normalized + bridge — DONE)
- `data/dso_research/_schema_bridge_ao_to_consolidate_20260621.md` (fleet→gate field map — DONE)
- `data/dso_research/ao_network_next_reach5_targets_20260621.json` (reach≥5 target set — RAN as wave 2)
- `data/dso_research/ao_network_evidence_reach5_20260621.json` (wave-2 raw — DONE; Hussain re-graded branded_dso 2026-06-21)
- `data/dso_research/ao_network_evidence_reach5_20260621_qa.json` (wave-2 QA-normalized+bridge — DONE; Hussain re-graded)
- `data/dso_research/_taxonomy_correction_and_pause_20260621.md` (taxonomy correction + AO-pause record — DONE)
- `data/dso_research/_WATCH_OUT_for_other_sessions_20260621.md` (cross-session watch-out notes — DONE, §§11-12 updated)
- `data/dso_research/census_evidence_candidates_validation_20260621.json` (done, candidate-grade)
- `data/dso_research/RESEARCH_HOME/EVIDENCE_FLEET_SPEC.md`, `scrapers/ao_network_evidence.js`, `scrapers/census_evidence_fleet.js`, `scrapers/build_evidence_targets.py` (tooling)

## LANGUAGE STANDARD (adopted)
AO reach = **high-value AO/network candidate signal**, NOT proof of ownership. `dentist_multi`/`stealth_dso`
require documentary corroboration before anything above `candidate`. `true_independent` is earned, never assumed.
