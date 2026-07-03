# AUTH — Fleet B Phase-C, ranks 51–100

**From:** Gate Owner
**To:** Fleet B
**Date:** 2026-06-21
**Status:** **AUTHORIZED** (files-only evidence step)

## Basis for authorization
Independent QA reviewed Fleet B's Phase-C **top-50** output as normalized in the initial Gate partition and returned `autonomous/VERDICT_QA_WAVE4_INITIAL_20260621.json` = **PASS_WITH_HOLDS** with **`systemic_defect_found: false`**. No systemic Phase-C defect ⇒ the next rank band is cleared to proceed.

## Scope — what is authorized
- **files-only.** Output is a `wave4_*phasec*` evidence file under `data/dso_research/_wave4_20260621/` with per-row transcribed durable artifacts. No other side effects.
- **ranks 51–100 ONLY.**
- **exclude ranks 1–50** (already covered by the QA'd top-50).
- **exclude the current 310 ready rows** (`_ready_to_validate_wave3_fixed_20260621.json`) **unless a row is explicitly corroborating** an existing ready row (mark it `corroborates_existing_ready`, do not re-add).
- **no deterministic re-mining.** Each lead must earn its own transcribed durable artifact (URL transcribed in Wave 4 itself); AO reach / brand substring / co-location / asserted web_verified-without-URL / DA_-synthetic / referral directories do **not** count.

## Hard prohibitions
- **No DB writes.** No `--allow-db-write`. No mutation of the **canonical manifest**, the **310 ready file**, **LEDGER**, **PROGRESS**, **ownership_tier**, **entity_classification**, or **ownership_status**.
- **Affordable and ClearChoice remain scope-held** (do not promote into the GP floor).
- **Protected networks remain held** — no release of LABINOV, AQEL, BELKIC, SWEIS, RAMAHA, SHAFI, NITTINGER, BRUNETTI (AB9: release requires an explicit decision + `network_evidence_quality='verified'`, which is NOT granted here).

## Acceptance
- Gate ceiling = `ready_for_validation` (never final). Consolidation stays **FROZEN**.
- **Output requires fresh independent QA before acceptance.** Nothing from this band is merged or normalized into the manifest until a new QA verdict passes.
- Use the 8 protocol dispositions; default any failing/ambiguous row to `hold_needs_more_evidence` (no partial credit, stricter-wins).

## Freeze invariant (must remain true; verify read-only before you write)
db_md5 `0dec26135bb4d6ee490dc16cfe892ca6` · `RESEARCH_HOME/LEDGER.jsonl` 1 line · `PROGRESS.json` undetermined_unreviewed 4439 · PL/practices `ownership_tier IS NOT NULL` = 0/0.
