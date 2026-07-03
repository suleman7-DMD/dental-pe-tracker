# PLAN — Intel backfill for Lane A waves 1+2 (~2,048 practices), upgraded search

**Authored 2026-07-02 (Fable PM). Status: APPROVED BY USER, deferred to a later session.**
User directive (2026-07-02): waves 1+2 ran census-only, so intel capture covers only waves 3+4
(~1,440 practices) — "thats only 1kish practices of the 4k practices total… missing 75% of easy
to gather intel." Backfill waves 1+2 later with an upgraded (dedicated) intel search. Also tracked
as session Task #5; THIS FILE is the durable copy (task lists do not survive session restarts).

## Context — why waves 1+2 have no intel

Lane A census waves (2026-07-02):
- **Wave 1** (units 001–064) + **Wave 2** (units 065–128) ran the v1 script
  (`lane-a-census-wave1-wf_b4f93973-e64.js`, session workflows dir) — ownership research ONLY.
- **Waves 3+4** (units 129–218) run the v2 script
  `data/dso_research/_wf_lane_a_census_v2_intel_20260702.js` — same census contract PLUS an
  optional per-practice `intel` object (opportunistic: website, services, technology, provider
  count/notes/career stage, Google rating+count, hiring, insurance, distinguishing notes; every
  block needs source URLs; google/hiring need their OWN source URL; no extra searches).
- Landing pipeline (already built + committed, `a95656f`):
  `data/dso_research/_merge_lane_a_intel_20260702.py` validates intel blocks and UPSERTs into
  `practice_intel` keyed by the location's `primary_npi` (fallback org_npi), with
  `verification_quality='partial'`, `research_method='lane_a_census_opportunistic'`,
  `verification_urls` = the block's sources. **Idempotent; never overwrites an existing
  practice_intel row** (full 4-layer dossier rows outrank opportunistic capture).
- Why this matters for the app: `practice_intel` feeds the Launchpad dossier tabs, and the
  Launchpad ranking signals gated by `SIGNALS_REQUIRING_INTEL` (hiring_now, succession_published,
  tech_modern, ffs_concierge, medicaid_mill) fire ONLY for practices that have an intel row.
  Every backfilled row directly unlocks job-hunt surface coverage.

## DO NOT re-run census research

Wave 1+2 classifications will already be merged/consolidated by the time this runs. Re-running
the v2 census script on units 001–128 would repeat the expensive ownership adjudication (and the
Opus verify pass) just to pick up the intel rider. Backfill is intel-ONLY.

## Option A (RECOMMENDED default — no API credits needed): v3 intel-only workflow wave

1. Author a v3 workflow script (new file, e.g.
   `data/dso_research/_wf_lane_a_intel_backfill.js`), modeled on the v2 script but stripped to
   one phase (no verify pass — no ownership claims are being made):
   - Input: the same unit files `_lane_a_20260702/unit_001.json` … `unit_128.json`.
   - Per practice: 1–2 dedicated searches purely for intel ("<name> <city> IL dentist",
     practice website, Google listing). This is the "upgraded search" — intel is the mission,
     not a rider, so coverage per practice will be far higher than the opportunistic yield.
   - Intel contract: copy the OPPORTUNISTIC INTEL field list + INTEL HARD RULES **verbatim**
     from `_wf_lane_a_census_v2_intel_20260702.js` (source-URL discipline, google/hiring need
     their own URL, omission over guessing).
   - Output shape (so the EXISTING converter lands it unchanged): write
     `_lane_a_20260702/intel_unit_NNN.json` as
     `{"unit_id": "...", "classifications": [{"location_id", "practice_name", "zip",
     "intel": {...}, "searched": [queries]}]}` — the converter only reads location_id, intel,
     searched; no tier fields needed. **Adjust the converter glob** (currently
     `result_unit_*.json`) to also sweep `intel_unit_*.json`, or run a copy pointed at the new
     prefix.
   - SKIP LIST: before launch, query SQLite for NPIs already in `practice_intel` and embed the
     already-covered location_ids per unit in args (or a skip file the agents read) — do not
     waste searches re-covering waves 3+4 captures or dossier-batch rows.
   - Model: Sonnet 5 research agents (`model: 'claude-sonnet-5'`), ~6 concurrent per workflow;
     128 units ≈ same wall-clock as one census wave since there is no verify stage.
2. Convert + land: `python3 data/dso_research/_merge_lane_a_intel_20260702.py --dry-run`,
   spot-QA 2–3 blocks against their source URLs, then run live.
3. Supabase leg: `scrapers/dossier_batch/upsert_practice_intel.py` (surgical UPSERT — never the
   full_replace TRUNCATE path for this).

## Option B (higher grade, needs ANTHROPIC_API_KEY credits): dossier batch pipeline

The purpose-built pipeline already exists: `scrapers/dossier_batch/launch.py` → `poll.py`.
Full 4-layer anti-hallucination gate, `verification_quality='verified'`-capable output, batch
API ≈ **$0.008/practice → ~$16 for ~2,048 practices**. Feed it the wave 1+2 NPI list (or just
target Chicagoland independents broadly — it dedups against existing intel). Prefer this if API
credits are available and the user wants dossier-grade intel rather than partial-grade.

## Decision input available before running: waves 3+4 yield data

The v2 script schema forces `n_intel` per unit, and the workflow return totals it. After waves
3+4 complete, read the opportunistic yield (intel rows / practices researched):
- High yield (≳50%) → Option A's dedicated search will do even better; run A.
- Low yield → argues the free-rider model under-delivers and the $16 Option B batch (forced
  dedicated searches + verified gate) is worth it.

## Sizing honesty

Lane A queue = 218 units ≈ 3,488 practices of ~4,096 remaining. Waves 3+4 with intel ≈ 1,440
(~41% of the queue, not 25%); waves 1+2 backfill adds ≈ 2,048. The remaining ~600 practices are
NOT in Lane A units yet — when a later lane covers them, use the v2 (intel-carrying) script so
they never need a backfill.
