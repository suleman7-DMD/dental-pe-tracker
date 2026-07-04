---
name: dental-pe-failure-archaeology
description: Load when debugging unexpected counts, weird classifications, local-vs-live drift, "why is this practice labeled X", failing CI floors, or BEFORE "fixing" anything that looks like bad data in this repo. The catalog of every costly past incident — symptom → root cause → the gate that now prevents it — so you recognize a known failure signature instead of re-introducing or re-fixing it.
---

# Failure Archaeology (what already went wrong here)

Before "fixing" data that looks wrong, check this catalog. Most anomalies you'll meet are
either (a) a known signature with an existing gate, or (b) the gate itself doing its job.
Removing a gate because it's inconvenient re-opens the incident that created it.

## Incident catalog (chronological)

### 1. NPI rows counted as practices (~2.7× inflation) — fixed 2026-04-25/26
- **Symptom:** "14,053 practices in Chicagoland" on some pages, ~4,900 on others.
- **Root cause:** NPPES emits provider (NPI-1) AND org (NPI-2) rows at the same address;
  raw row counts were presented as clinics.
- **Gate now:** `practice_locations` table (one row per address+ZIP), headline-denominator
  policy (location-deduped counts headline, NPI counts subtitle only), unit-discipline skill.

### 2. Phone-only DSO classification (1,181 → 109 dso_regional) — fixed 2026-04-25
- **Symptom:** ~9.9% "corporate" from practices sharing a front-desk switchboard.
- **Root cause:** classifier Pass 3 treated shared phone alone as a DSO signal.
- **Gate now:** phone-sharing is a flag (`shared_phone_flag`), never a sole trigger; F27
  vitest guards frontend classification-source discipline.

### 3. Hygienist leak — CI-guarded since 2026-04-26
- **Symptom:** non-dentist NPI rows contaminating practice counts.
- **Root cause:** NPPES import accepting non-1223 taxonomy codes.
- **Gate now:** invariant F02 (`check_data_invariants.py`): nppes rows with non-1223
  taxonomy = FAIL.

### 4. Data-Axle synthetic records in denominators (179-row purge) — 2026-06-12
- **Symptom:** "practices" with `DA_`-prefixed fake NPIs, no federal NPI at the address.
- **Root cause:** Data-Axle importer created records for unmatched rows.
- **Gate now:** `da_unverified` entity class excluded from EVERY denominator; importer
  root-fixed; merge gate rejects synthetic NPIs (`synthetic_npi`); consolidate script refuses
  DA_ rows as classification anchors.

### 5. Evenly placeholder → 13 false corporates — 2026-06-12
- **Symptom:** a cluster of "corporate" practices whose only signal was
  `parent_iusa='000000000'` (a Data-Axle placeholder, not a real parent).
- **Root cause:** placeholder value treated as parent-company linkage.
- **Gate now:** demotion audit files (`il_false_corporate_demotions_*.json`);
  `reclassify_verified_corporate_il.py` excludes every demoted id from re-promotion; rule:
  Data-Axle fields corroborate, never suffice (also ruling R6 for AO/EIN).

### 6. Weeks-long Supabase staleness (875 rows) — root-fixed 2026-06-10
- **Symptom:** live NPI corporate count stuck at 875 while SQLite said 1,089; every sync
  "succeeded".
- **Root cause:** raw-SQL classification flips didn't bump `updated_at`, so the incremental
  sync path skipped them forever.
- **Gate now:** FLOOR_NPI CI guard; mandatory both-leg read-back after every sync; surgical
  per-row sync scripts for healing.

### 7. Duplicate locations inflating the floor — cleaned 2026-06-19
- **Symptom:** same physical clinic counted 2–3× via suite-variant addresses.
- **Root cause:** address normalization gaps.
- **Gate now:** audited cleanup (`duplicate_location_cleanup_20260619.json`);
  `duplicate_location` class excluded from merges; adjudication holds for dup-suspects.

### 8. ORM census-column sync-strip (silent data loss) — fixed + proven 2026-07-02
- **Symptom:** census columns present in SQLite, NULL in Supabase after a full_replace.
- **Root cause:** the 6 census columns weren't ORM-mapped, so ORM-serialized full_replace
  wrote rows WITHOUT them — dropping data on every sync.
- **Gate now:** columns mapped on BOTH models (`scrapers/database.py`;
  `PROOF_ORM_SYNC_MIGRATION_20260702.md`); read-back protocol. Any `database.py` refactor
  must re-verify the mappings.

### 9. Model-clamp incident — 2026-07-02
- **Symptom:** every subagent (including verify passes) silently ran on a weaker model.
- **Root cause:** `CLAUDE_CODE_SUBAGENT_MODEL` pinned globally in settings; env is snapshotted
  at CLI startup, so even after removal the session kept the pin until restart.
- **Gate now:** never pin a global subagent model; set per-agent `model:` in workflow/Agent
  calls; after settings changes, restart the session before trusting env.

### 10. Aspen-as-T1 reverse rows — caught by §6h gate, 2026-07-03/04
- **Symptom:** research rows claiming branded-DSO locations (Aspen Dental) were
  `true_independent`.
- **Root cause:** agents pattern-matching a local dentist's name on a DSO location page;
  positive-proof standard not yet enforced.
- **Gate now:** §6h T1 positive-proof audit (`screen_true_independent_hardening.py` +
  `audit_lane_a_t1_t2.py` — held 52, downgraded 483 in the proven run); R4 one-network-one-
  decision for ≥10-location brands.

### 11. Sessions tripping over parked MA rows — recurring until 2026-07
- **Symptom:** censusing/deleting/counting Boston rows, breaking denominators.
- **Root cause:** MA is parked (21 ZIPs / 362 GP locations) but present in the DB.
- **Gate now:** merge gate rejects non-IL rows (`not_il_watched`); census universe is
  explicitly IL-only (4,439); rule: filter from view, never census, never delete.

### 12. TRUNCATE CASCADE near-miss — standing trap
- **Symptom (potential):** syncing `--tables practices` alone wipes `practice_changes`/
  `practice_intel`/`practice_signals` via FK CASCADE without repopulating them.
- **Gate now:** never sync practices alone; surgical scripts for column-level heals;
  `_sync_floor_tables_only` prints FK dependents before acting.

## How to use this catalog

1. Match your anomaly's signature against the symptoms above BEFORE forming a fix.
2. If a gate blocks you, the gate is probably right — bring evidence to the user instead of
   weakening the gate (evidence file + decision, per the validation skill §3).
3. If you find a genuinely NEW failure mode: fix root cause (not symptom), add/extend a code
   gate where possible, write the audit file, and append the incident here (symptom → root
   cause → gate) in the same change.

## Common hasty-model failures

- Re-promoting demoted rows because the corporate signal "looks real" (it's a placeholder or
  landlord — check the demotion audit files first).
- Deleting `da_unverified`/MA rows to "clean up" (they're excluded by design, kept on purpose).
- Treating a floor-guard FAIL as a number to re-base rather than a regression to investigate.
- Assuming Supabase is right and SQLite is wrong (truth flows SQLite → Supabase, never back).

## Minimum proof before continuing

Before shipping any data "fix": the incident number above it matches (or a statement that none
match), the root cause named, the existing gate consulted, and — for demotions/exclusions — a
dated audit file plus user approval.
