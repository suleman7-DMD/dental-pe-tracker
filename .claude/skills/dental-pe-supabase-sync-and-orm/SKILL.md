---
name: dental-pe-supabase-sync-and-orm
description: MANDATORY before running or modifying ANY SQLite→Supabase sync (sync_to_supabase.py, _sync_floor_tables_only, _sync_census_columns_practices, _sync_practices_changed_rows), diagnosing local-vs-live count mismatches or staleness, adding/altering ORM columns in scrapers/database.py, or touching refresh.sh. Encodes the TRUNCATE CASCADE trap, the census-column strip bug, and the mandatory read-back protocol.
---

# Supabase Sync + ORM Safety

SQLite (`data/dental_pe_tracker.db`) is truth; Supabase Postgres is the live mirror the site
reads. Every sync path here is destructive-by-design (full_replace = TRUNCATE CASCADE) or
surgical (per-row UPDATE). Using the wrong one, or skipping read-back, has caused silent weeks-
long staleness and near data loss. All syncs are HUMAN-GATED: get explicit user approval first.

## 1. Strategy table (verified against `scrapers/sync_to_supabase.py` SYNC_CONFIG, 2026-07-04)

| Table | Strategy | Notes |
|---|---|---|
| `practices` | `watched_zips_only` | TRUNCATE CASCADE + reinsert of 13,818 watched rows — **also wipes/repopulates practice_changes and other FK dependents** |
| `deals` | `incremental_updated_at` | |
| `practice_changes` | `incremental_id` | filtered to watched ZIPs |
| `zip_scores`, `watched_zips`, `dso_locations`, `ada_hpi_benchmarks`, `pe_sponsors`, `platforms`, `zip_overviews`, `zip_qualitative_intel`, `zip_signals`, `practice_locations` | `full_replace` | TRUNCATE CASCADE + INSERT in one transaction |
| `practice_intel`, `practice_signals` | `full_replace` | filtered to watched-ZIP NPIs |

`MIN_ROWS_THRESHOLD` floors pre-check each full_replace (refuses to replace a table with a
suspiciously small row set), and each sync does a post-write COUNT assertion. Those guards are
necessary, not sufficient — see §4 read-back.

## 2. The TRUNCATE CASCADE trap

**Never run a sync scoped to `--tables practices` alone.** Its TRUNCATE CASCADE clears FK
dependents (`practice_changes`, `practice_intel`, `practice_signals`) and only the full path
repopulates them. If you need to move `practices` data surgically, use a per-row script (§3).
Before ANY full_replace, know what CASCADE touches — `_sync_floor_tables_only` prints the FK
dependents per table for exactly this reason.

## 3. The census-column paths (get these exactly right)

Six census columns exist on BOTH `practices` and `practice_locations`: `ownership_tier`,
`pe_backed`, `ownership_evidence_basis`, `ownership_evidence_urls`, `ownership_confidence`,
`network_id`. They are ORM-mapped in `scrapers/database.py` (Practice ~line 189,
PracticeLocation ~line 1027). **If a refactor unmaps them, every full_replace silently strips
census data from Supabase** — that bug shipped once (caught 2026-07-02, fixed + proven in
`PROOF_ORM_SYNC_MIGRATION_20260702.md`). Any change to `database.py` must preserve these
mappings; verify with:

```bash
grep -n "ownership_tier" scrapers/database.py   # expect hits in BOTH model classes
```

After a census consolidation, sync EXACTLY two legs (proven 2026-07-04, runbook §6m):

```bash
python3 -m scrapers._sync_floor_tables_only
# Carries practice_locations census cols via ORM full_replace (+ zip_scores, dso_locations).
# Proven output: practice_locations 5,657 / zip_scores 290 / dso_locations 633;
# "LIVE Supabase floor: 268/4801 = 5.58%"

python3 -m scrapers._sync_census_columns_practices
# Surgical per-NPI UPDATE of the 6 census cols on practices. Idempotent.
# Proven output (2026-07-09): "Updated 8133 rows in Supabase (0 not present there)" +
# "VERIFY census NPIs: Supabase=8133  SQLite truth=8133  MATCH" + identical tier tallies
```

**`_sync_practices_changed_rows.py` does NOT carry census columns** — it pushes only the
entity_classification set. Using it for census sync leaves Supabase silently stale. The
inverse is also true: for DETECTOR-axis staleness (live corporate-NPI count behind SQLite),
`_sync_practices_changed_rows.py --since <date>` IS the correct surgical heal (idempotent
per-row UPDATE, proven in the 2026-06-12 incident) — never the census-column script, never a
full sync.

## 4. Read-back is mandatory (both legs, independent queries)

A sync is not done when the script exits 0. It is done when you have independently queried
Postgres and compared against SQLite:

1. Counts: tiered `practice_locations` (3,692), tiered `practices` (8,133) — live vs local.
2. Tier tallies GROUP BY ownership_tier — must match exactly, per table.
3. Floor: corp locations 268 / corp NPIs 1,152 / `SUM(zip_scores.total_gp_locations)` 4,801,
   live floor 268/4,801 = 5.58% (values as of 2026-07-09 — recheck locally first).
4. Paste the read-back output. "MATCH" printed by the script counts as leg-level verification;
   the independent read-back is still required.

History that justifies this: Supabase `practices` sat 875 rows stale for WEEKS because raw-SQL
flips didn't bump `updated_at`, so the incremental path skipped them — every sync "succeeded".

## 5. Known gaps + coordination rules

- `practice_locations.census_review_status` (`'held'|'undetermined'|NULL`) shipped 2026-07-04
  (commit `6b029d2`, runbook §6n): Review Desk metadata, NOT a tier — `ownership_tier` always
  wins; location-level only (no NPI mirror); written ONLY by
  `scrapers/backfill_census_review_status*.py` (dated per-wave copies, e.g. `_20260709`),
  never by `consolidate_census.py`; ORM-mapped so
  full_replace syncs carry it; deliberately NO CI floor (count drops as rows earn tiers).
  Current tallies (2026-07-09 P5 recovery): 742 undetermined + 5 held — post-P5 the DB counts
  no longer equal the wave-1 triage file's 477 (recovery added rows outside that file).
  Never write pseudo-tiers to represent review status.
- Supabase `practices` holds ONLY watched-ZIP rows (13,818). Local-vs-live NPI comparisons
  must scope SQLite to watched ZIPs or they'll be off by out-of-scope rows (1,153 vs 1,152).
- **Concurrency rule:** never run the weekly full sync, `refresh.sh`, or any practices-table
  sync while a census merge→consolidate→sync chain is in flight anywhere.
- `.env` holds `SUPABASE_DATABASE_URL` etc. Never print or commit env values.

## 6. Diagnosing a local-vs-live mismatch (in order)

1. Reproduce both sides with the SAME query, same scoping (watched ZIPs!), paste both outputs.
2. Check `updated_at` staleness on the live rows (the 875-row incident's signature).
3. Check which sync path last ran and whether it CARRIES the mismatched columns (§3).
4. Check FLOOR/FLOOR_NPI CI (`scripts/check_data_invariants.py`, needs SUPABASE_URL +
   SUPABASE_ANON_KEY env) — a floor FAIL means a pipeline step reverted promotions: re-run
   `scrapers/reclassify_verified_corporate_il.py` then re-sync floor tables (with approval).
5. Only after diagnosis, propose the minimal sync leg that heals it — to the user, not to cron.

## 7. Common hasty-model failures

- Running a full sync to fix a 6-column staleness (destructive overkill; also wipes FK
  dependents mid-census).
- Using `_sync_practices_changed_rows.py` for census columns (doesn't carry them).
- Declaring success from exit code 0 without read-back.
- Comparing unscoped SQLite counts to Supabase (watched-ZIP trap).
- Editing `database.py` models without checking the census mappings survive.
- Running any sync without explicit user approval in THIS session.

## 8. Minimum proof before continuing

Paste: the command run, its verification lines, and an independent Postgres read-back (counts +
tallies + floor) matching SQLite. If any number differs, STOP — diagnose per §6 before any
further writes.
