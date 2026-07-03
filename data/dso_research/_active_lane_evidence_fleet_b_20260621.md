# ACTIVE LANE — Evidence Fleet B (throughput evidence gathering, non-colliding)

**Session role:** second evidence-gathering session ("Evidence Fleet B"). **Date:** 2026-06-21. **Model:** Opus 4.8.

## Write boundary (collision-safe — read before anything)
- **No DB writes.** No `ownership_tier`. No `entity_classification`. No reset.
- **No mutation** of `LEDGER.jsonl`, `PROGRESS.json`, or `SESSION_LOG.md`.
- **No** `consolidate_census.py --allow-db-write`. `--validate-only` ONLY.
- **No** schema migration / sync scripts / frontend edits.
- I do NOT use `ownership_tier IS NULL` as remaining-work state (wave-1 reset may be incomplete).
- I write **candidate evidence files ONLY**, all under `data/dso_research/`. Every row is
  candidate/evidence, never final truth (`status` ∈ ready_for_validation | needs_verification | reject).

## What this lane OWNS (the only files I write)
- `data/dso_research/evidence_practice_intel_mined_fleet_b_20260621.json` — Lane 1
- `data/dso_research/evidence_locator_exact_fleet_b_20260621.json` — Lane 2
- `data/dso_research/evidence_zip_sweep_fleet_b_20260621.json` — Lane 3
- `data/dso_research/ownership_evidence_queue_fleet_b_20260621.json` — unified, deduped
- `data/dso_research/ownership_evidence_queue_fleet_b_validation_20260621.txt` — validator output
- `data/dso_research/_exclusion_set_fleet_b_20260621.json` — working exclusion set (read-only artifact)
- This lane file.

## Target lanes
1. **practice_intel mining** — harvest ownership language from existing `practice_intel` dossiers
   (DB prose + verification URLs already on disk; no web needed).
2. **Exact-address DSO locator evidence** — only brands NOT in the active AO wave; exact street+ZIP.
3. **Zero-corp ZIP sweep** — dense ZIPs not currently being processed by the main session.

## Non-collision contract
- **Will NOT touch the 8 AO networks claimed by the main session** (unless main explicitly leaves
  them unclaimed): Sohail Shafi, Vesna Belkic, Rachel Nittinger, Fadi Aqel, Robert Brunetti,
  Jubrail Sweis, Boris Labinov, Ahmed Ramaha.
- I exclude every `location_id` already appearing in: `census_results_wave1_20260620.json`,
  `census_evidence_candidates_validation_20260621.json`, any `*evidence*20260621*.json`, and the
  8 claimed AO-network location lists from `ownership_evidence_targets_20260621.json`.
- I do NOT write the QA session's files (`ownership_evidence_QA_*`, `evidence_denominator_review_*`).
- IL / Chicagoland ONLY. Boston/MA parked.

## Quality rules I enforce on my own output
- AO reach alone ≠ ownership proof.
- stealth_dso / branded_dso require exact documentary evidence (locator/website/affiliated_dso/EIN
  cluster w/ corroborating corporate member). Brand-substring alone = candidate, never final.
- pe_backed requires real PE/MSO/DSO evidence, not size.
- true_independent must be POSITIVELY earned (single-loc owner-operated evidence OR a saved
  negative-search artifact) — "no DSO language" is NOT enough.
- Data-Axle synthetic (`DA_`/`da_unverified`) rows cannot be final classifications.
- Uncertain → `needs_verification` / `undetermined`.
