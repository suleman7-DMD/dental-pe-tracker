# P3 — Practice-Intel Backfill for Lane A Waves 1–2 (authored 2026-07-04)

**Goal:** backfill `practice_intel` for the practices researched in Lane A waves 1+2 (units
001–128), which ran the census-only v1 workflow and captured NO intel. Waves 3+4 ran v2 with
opportunistic intel capture — those are done. This is Option A from the source plan
(intel-only workflow), the recommended path.

**Source of truth:** `RESEARCH_HOME/PLAN_INTEL_BACKFILL_WAVES_1_2_20260702.md`.

**Iron rules:**
- **DO NOT re-run census research.** Result files are ground truth; `ownership_tier` is not
  touched by this plan in any way.
- **Never overwrite existing `practice_intel` rows** — the converter is UPSERT-keyed by
  `primary_npi` and skips NPIs that already have intel; keep it that way.
- Intel written here is marked `verification_quality='partial'` (opportunistic capture, not
  the full 4-layer dossier gate).

**Write-set:** one new workflow script `data/dso_research/_wf_lane_a_intel_backfill.js`, its
`intel_unit_NNN.json` outputs, a glob adjustment to the converter, SQLite `practice_intel`
rows (gated), and the practice_intel sync leg (gated).

---

## Phase 0 — Preflight: build the target list

```bash
# Which wave-1/2 practices already have intel? (skip list)
sqlite3 data/dental_pe_tracker.db "SELECT COUNT(*) FROM practice_intel;"
python3 - <<'EOF'
# Target = locations in result_unit_001..128 whose primary NPI is NOT in practice_intel
# print count + write data/dso_research/_intel_backfill_targets_<date>.json
EOF
```

**Verification:** target count + skip-list count printed; targets ∩ skip-list = 0.
**Trap:** deriving targets from the DB instead of the result files (the result files define
who waves 1–2 actually researched).

## Phase 1 — v3 intel-only workflow

Clone `_wf_lane_a_census_v2_intel_20260702.js` → `_wf_lane_a_intel_backfill.js`, strip the
census-classification stages, keep the intel capture. Output shape per unit
(`intel_unit_NNN.json`):

```json
{"unit_id": "...", "classifications": [
  {"location_id": "...", "practice_name": "...", "zip": "...", "intel": {...}, "searched": true}
]}
```

Model/cost choice is the USER's at launch: the source plan ran Sonnet agents (~6 concurrent);
a Batch-API Haiku pass is the cheaper alternative (~$0.008/practice, see the anti-hallucination
section of root CLAUDE.md for the batch recipe + validation gate). Present both with cost
estimates before spawning anything that spends money.

**Verification:** first unit's output validates against the shape above with real URLs in
`intel`; only then scale out. **Trap:** letting the workflow "helpfully" also emit tier
opinions — strip that field if present; it must never reach a merge script.

## Phase 2 — Convert into practice_intel (gated)

Adjust the glob in `_merge_lane_a_intel_20260702.py` (commit `a95656f`) to include
`intel_unit_*.json`. It UPSERTs `practice_intel` keyed by `primary_npi`,
`verification_quality='partial'`, idempotent, never overwrites existing rows.

```bash
python3 data/dso_research/_merge_lane_a_intel_20260702.py   # after user approves the DB write
sqlite3 data/dental_pe_tracker.db "SELECT COUNT(*) FROM practice_intel;"   # expect old + new_upserts
```

**Verification:** predict the post-count before running; re-run the converter — second run
must report 0 new rows (idempotency proof). **Trap:** "fixing" the never-overwrite behavior
to refresh stale intel — refresh is a different, TTL-governed pipeline (`weekly_research.py`).

## Phase 3 — HUMAN GATE → sync leg + read-back

`practice_intel` syncs `full_replace` filtered to watched NPIs (see the sync skill). With user
approval, sync ONLY that table, then read back the live count vs SQLite. **Trap:** any sync
touching `practices` (TRUNCATE CASCADE wipes practice_intel itself — order of operations
matters; never run them together mid-backfill).

---

## Stop conditions

- Target list overlaps the skip list, or a unit output contains tier fields.
- Converter reports overwrites (>0 existing rows changed) — that's a bug, not a feature.
- Spend approval absent — no agents, no batches, no API calls that cost money.
