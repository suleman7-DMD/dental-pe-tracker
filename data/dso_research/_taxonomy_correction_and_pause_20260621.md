# Taxonomy correction + AO fan-out PAUSE — 2026-06-21

**Author:** Lane 1 / main session (Opus 4.8). **Evidence-file/tooling only — no DB writes, consolidation HELD.**
For the Reset+Consolidation Gate Owner (4th session) building the canonical manifest, and for QA.

---

## 1. AO fan-out is PAUSED after reach≥5 (not reach=4)

Two coordination messages conflicted:
- Earlier (Codex): "Run the remaining reach=4 AO clusters if budget allows."
- Newer (Gate Owner, replacing Codex): **"Main session: Pause further AO fan-out after reach≥5. Do not run reach 2–3. Your outputs are staged for the gate owner."**

**Resolution: the newer Gate-Owner instruction governs → reach=4 was NOT launched.** The runner
`scrapers/ao_network_evidence.js` carries a ⛔ PAUSED banner; its `NETWORKS` array holds the staged
reach==4 batch (14 clusters) ready but un-run. Do not launch it, and do not run the reach 2–3 long tail,
until the gate owner explicitly clears more gathering.

- Waves complete: **wave 1** (top-8 AOs) + **wave 2** (reach≥5, 14 networks / 84 locations).
- Staged-but-paused: reach==4 (14 clusters). Not run.
- The reach=4 launch was conflicting; surfaced to the user for confirmation rather than guessed.

## 2. Taxonomy correction applied (gate-owner rule, "for everyone")

> pe_backed=false does **NOT** automatically mean `dentist_multi`. Non-PE DSOs/platforms can still be
> `branded_dso` or `stealth_dso` if there is MSO / DSO / platform / management-company evidence.
> `pe_backed` is a SEPARATE flag.

Corrected definitions now in force:
- **dentist_multi** — dentist-owned multi-location group, **no** separate DSO/MSO/platform/management structure.
- **branded_dso** — DSO/platform/management-company structure **or** an established DSO brand, even if family-owned / non-PE.
- **stealth_dso** — local/friendly-PC brand backed or managed by a DSO/MSO/PE platform.
- **pe_backed** — separate boolean; true only with documentary PE evidence; does not set the tier.

### 2a. Runner fixed (`scrapers/ao_network_evidence.js`)
- MODEL prompt tier defs rewritten to the corrected taxonomy (structure decides the DSO tier, not PE).
- Re-gate rewritten: the blunt `branded_dso & pe_backed!==true → dentist_multi` rule is **removed**. New
  helper `hasPlatformEvidence(c)` (negation-stripped scan of owner_identity/reasoning/verdict/evidence/
  signal/db_artifact for MSO/management/platform/DSO-brand/affiliated_dso/parent_company/entity_classification=dso…).
  - `branded_dso → dentist_multi` **only when no platform evidence**.
  - `stealth_dso → dentist_multi candidate` only when **no URL AND no platform evidence**.
  - Specialist exclusion retained; ready_for_validation remains the max status; AO reach = signal, not proof.

### 2b. Staged reach≥5 evidence files re-graded
Only **11 rows** were ever touched by the old blunt rule (verified via `_regated` scan). Corrected:

- **SAMEERA HUSSAIN ×10 = Dental Dreams → `branded_dso`, `pe_backed=false`.** Documentary basis: KOS
  Services LLC MSO (runs all business ops), established multi-state DSO brand, friendly-PC entity
  *Dental Experts LLC*, and all 10 already `dso_national` in the pipeline DB. This is a structural DSO that
  merely lacks PE — exactly the case the correction targets. Applied in BOTH:
  - `ao_network_evidence_reach5_20260621.json` (raw): rows carry `_taxonomy_corrected`; `_regated` marked SUPERSEDED.
  - `ao_network_evidence_reach5_20260621_qa.json` (gate-facing): `candidate_tier` + `_bridge.assigned_tier`/`best_guess_tier` → branded_dso.
  - `_meta.taxonomy_correction_2026_06_21` added to both. `consolidate_ready` stays **false** (QA sign-off still required).
  - **New reach≥5 tier tally:** dentist_multi 42 / **branded_dso 17** / stealth_dso 16 / undetermined 9. Gate tally unchanged (70 ready_for_validation / 9 candidate / 5 undetermined).

- **MILAN RONCEVIC ×1 (1st Family Dental, Addison)** was also downgraded by the old rule, but it has **no
  documentary MSO/PE** evidence (non-dentist CEO, "Dental Profile"; moderate stealth signal only). **Left as-is
  (not auto-promoted)** and FLAGGED for gate-owner judgment — "1st Family" is on the gate-owner watch list.

## 3. Gate-owner watch list to re-check under the corrected taxonomy

The gate owner named these as cases where pe_backed=false may have wrongly implied dentist_multi:
**Dental Dreams / KOS Services** (resolved above → branded_dso), **Webster, 1st Family, Family Dental Care,
Brite**. For QA / the manifest: re-test each for an MSO / management-company / platform layer — if present,
they are `branded_dso`/`stealth_dso` with `pe_backed=false`, NOT `dentist_multi`. Also re-review the
**Chang/Precision Dental Care** rows that are `dso_regional` in the DB but were graded `dentist_multi`
(dentist-owned, no PE found) — confirm there is no MSO layer before settling the tier.

## 4. Unchanged guardrails
No DB writes. `ownership_tier` untouched. LEDGER/PROGRESS untouched. `ownership_tier IS NULL` is NOT used as
remaining-work state. Consolidation HELD until the gate owner reports reset complete. MA/Boston PARKED.
