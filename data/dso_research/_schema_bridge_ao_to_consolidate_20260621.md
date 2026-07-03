# SCHEMA BRIDGE — AO evidence fleet → `consolidate_census.py`

**Author:** Lane 1 / main session (Opus 4.8), 2026-06-21. **Read-only/file-only — no DB writes.**
**Purpose:** map the field names my AO-network wave emits onto the exact field names Codex's
gate (`scrapers/consolidate_census.py`) validates, so QA can run `--validate-only` without a
second translation pass. **The fleet output is NOT consolidate-ready as-is** — the field names
differ, and (more importantly) nothing should reach `status=classified` until QA approves.

Source files this bridges:
- raw fleet: `data/dso_research/ao_network_evidence_20260621.json` (85 `classifications`)
- QA-normalized: `data/dso_research/ao_network_evidence_20260621_qa.json` (85 `rows`, bridge pre-applied under `_bridge`)

---

## 1. Field-name map (fleet → consolidate_census)

`consolidate_census.py` reads each input row from `{"classifications":[...]}` and validates against:
`VALID_TIERS`, `VALID_BASES`, `VALID_STATUS`, `VALID_CONFIDENCE`, `URL_BASES`, `ARTIFACT_BASES`.

| consolidate_census field | type / allowed values | AO fleet source | mapping rule |
|--------------------------|-----------------------|-----------------|--------------|
| `location_id` | string | `location_id` | identity |
| `assigned_tier` | `VALID_TIERS` = {true_independent, single_loc_group, dentist_multi, stealth_dso, branded_dso, institutional, undetermined} | `candidate_tier` | identity — fleet enum is a subset (no `true_independent`/`single_loc_group`, correct: an AO network is multi-loc by definition) |
| `status` | `VALID_STATUS` = {classified, undetermined, needs_verification} | `gate_status` | **NOT 1:1 — see §2.** `ready_for_validation`→`classified` **only after QA**; `candidate`→hold (do not pass); `undetermined`→`undetermined` |
| `evidence_basis` | `VALID_BASES` = {locator, web_verified, ein_cluster, ao_cluster, name_chain, intel_dossier, structural, none} | derived (fleet has none on AO rows) | URL present → `web_verified`; else AO artifact only → `ao_cluster`; else → `none`. **`ao_reach` is NOT a valid basis string — it maps to `ao_cluster`.** |
| `evidence_urls` | string[] | `evidence_urls` | identity. Required non-empty when `evidence_basis ∈ URL_BASES` {locator, web_verified, intel_dossier} |
| `evidence_artifacts` | list (truthy) | `[db_artifact]` | wrap the single `db_artifact` (the `ao_reach` federal fact) in a list. Required non-empty when `evidence_basis ∈ ARTIFACT_BASES` {ein_cluster, ao_cluster, name_chain, structural} |
| `confidence` | `VALID_CONFIDENCE` = {high, medium, low} | `confidence` | identity. **Constraint:** a `classified` row may NOT be `low` (gate rejects). 0 AO rows are low+ready, so none blocked today. |
| `pe_backed` | bool/null | `pe_backed` | identity |
| `network_id` | string/null | `network_id` | identity (`ao:LAST_FIRST`) |
| `owner_identity` | string/null | `owner_identity` | identity |
| `reasoning` | string | `reasoning` | identity |
| `practice_name`, `city`, `zip`, `current_entity_classification` | backfilled from DB by `validate_rows` if absent | annotated on fleet rows | already present; gate will re-confirm from DB |

The QA-normalized file pre-computes `assigned_tier`, `evidence_basis`, `evidence_artifacts`, and a
proposed `consolidate_status` under each row's `_bridge` object, plus a row-level `signal`/`evidence`
split and `evidence_scope`. It deliberately sets `_bridge.consolidate_ready=false` on **every** row.

---

## 2. The status bridge is the whole point — `final_ready`/`ready_for_validation` ≠ `classified`

Per the user (Option-4) and Codex correction #4, **highest the fleet may emit is a proposal.**

| fleet `gate_status` | count | → consolidate `status` | who flips it | gate preconditions to become `classified` |
|---------------------|------:|------------------------|--------------|--------------------------------------------|
| `ready_for_validation` | 76 | **`classified` ONLY after QA approves** (until then: do not write) | QA / Codex gate | `confidence!=low`; if basis∈URL_BASES → `evidence_urls` non-empty; if basis∈ARTIFACT_BASES → `evidence_artifacts` non-empty; stealth_dso/branded_dso → URL **or** artifact |
| `candidate` | 7 | **not consolidated** — held in queue | nobody (signal-only) | n/a. A `needs_verification` row in the gate must carry `assigned_tier=undetermined`, so a candidate `dentist_multi` cannot be written with its tier — it simply stays out until a corroborator is found |
| `undetermined` | 2 | `undetermined` | gate (no-op tier) | n/a |

**Hard rule for QA / the gate operator:** do NOT mass-map `ready_for_validation → classified`. Each
`ready_for_validation` row is a *proposal backed by ≥1 corroborator*; QA still adversarially checks the
corroborator before it earns `classified`. `candidate` rows must never become `classified`.

### `ao_cluster` basis is artifact-grade but NOT final-sufficient alone
`ao_cluster` ∈ `ARTIFACT_BASES`, so the gate will accept it structurally — but the corrected standard
(Codex #2/#3) says **AO reach alone is a signal, not ownership proof.** So for AO rows that earn
`classified`, prefer `evidence_basis=web_verified` with the corroborating URL (group site / owner bio /
PE filing) as the deciding evidence, keeping the `ao_reach` object in `evidence_artifacts` as the
*structural* support. 83/85 rows carry a documentary URL, so `web_verified` is available for nearly all.

---

## 3. What QA must resolve before any consolidate run (the "fleet/validator mismatch")

1. **Field rename** — fleet uses `candidate_tier`/`gate_status`/`signal_vs_evidence`/`db_artifact`;
   gate wants `assigned_tier`/`status`/`evidence_basis`/`evidence_artifacts`. The `_qa.json` `_bridge`
   block does this rename, but a tiny adapter is still needed to emit a gate-shaped
   `{"classifications":[...]}` payload — **I have NOT written that adapter** (it would imply readiness
   to consolidate; consolidation is held).
2. **`evidence_scope`** — AO documentary evidence is **network-level** (it proves the *owner/owner-type*,
   not that a specific address belongs to them). 55/85 rows are `network_level`; 30 are `location_specific`
   (the network summary cited an exact-address match). The federal AO link attaches the owner to each
   location_id, but per-address locator confirmation is the recommended QA/Fleet-B follow-up before a
   `location_specific` `classified`. This is exactly the over-confidence Codex flagged — surfaced, not hidden.
3. **Re-review flag** — 4 ProCare/Brunetti location_ids still carry a non-null `ownership_tier`
   (wave-1 reset gap, already reported). The gate **blocks** non-null `ownership_tier` rows unless
   `--allow-rereview`. QA/Codex must confirm the reset completes (those go to NULL) OR pass
   `--allow-rereview` knowingly. Lane 1 will not touch `ownership_tier`.
4. **DA_ synthetics** — gate rejects classifying any `DA_`-prefixed NPI. None of the 85 AO rows are
   DA synthetics (all are real federal NPIs), so none are blocked on this rule.

---

## 4. One-line summary for the QA lane

> The AO wave produced **76 ready_for_validation + 7 candidate + 2 undetermined** ownership proposals
> across 8 networks. Treat every `ready_for_validation` as *needs your adversarial sign-off*, not as
> `classified`. Rename per §1, gate per §2, and confirm §3 (esp. the 4 ProCare `ownership_tier` rows and
> the network-level vs location-specific evidence scope) before any `--allow-db-write`. The DSO/PE subset
> needing the hardest look is **Nittinger/Sonrava (pe_backed)** and **Labinov/Destiny→ProSmile (pe_backed)**;
> everything else is dentist-owned-multi or dentist-branded (`pe_backed=false`) — i.e. *non-independent /
> consolidated candidates*, **not** "corporate/DSO" in the PE sense.
