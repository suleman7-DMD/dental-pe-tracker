# fix-db incident report — 2026-05-30

## TASK 1 — Exact columns confirmed

### Activity-feed query (`practice_changes`)

File: `dental-pe-nextjs/src/lib/supabase/queries/changes.ts` (primary) and `queries/practice-changes.ts` (Home page variant).

**Column ordered by / filtered on:** `change_date` DESC

Both query paths use the same column:

```typescript
// changes.ts:79-84 — global path (no ZIP filter)
const { data, error } = await supabase
  .from("practice_changes")
  .select(CHANGE_COLS)
  .gte("change_date", sinceDateStr)
  .order("change_date", { ascending: false })
  .limit(500);

// practice-changes.ts:38 — Home activity-feed variant
.order('change_date', { ascending: false })
.limit(limit * 3)
```

Filter: `change_date >= <date 90 days ago>`, order: `change_date DESC`.

### enrichedCount query (`practices`)

File: `dental-pe-nextjs/src/lib/supabase/queries/practices.ts` lines 225-228.

**Column:** `data_axle_import_date`, **table:** `practices`.

```typescript
const { count: dataAxleCount, error: enrichErr } = await supabase
  .from("practices")
  .select("npi", { count: "exact", head: true })
  .not("data_axle_import_date", "is", null)
```

Translates to: `SELECT COUNT(npi) FROM practices WHERE data_axle_import_date IS NOT NULL`

---

## TASK 2 — Index status and EXPLAIN ANALYZE

### Finding: Both indexes already exist on prod Supabase

Inspection via direct connection (port 5432) revealed both required indexes were already in place — created by a prior `sync_to_supabase.py` schema migration run. The `CREATE INDEX IF NOT EXISTS` DDL would have been a no-op.

**Existing indexes on `practice_changes`:**

| Index name | Definition |
|---|---|
| `idx_practice_changes_date` | `CREATE INDEX ... ON practice_changes USING btree (change_date DESC)` |
| `ix_practice_changes_change_date_desc` | `CREATE INDEX ... ON practice_changes USING btree (change_date DESC)` |
| `ix_practice_changes_npi` | `CREATE INDEX ... ON practice_changes USING btree (npi)` |
| `ix_practice_changes_type_date` | `CREATE INDEX ... ON practice_changes USING btree (change_type, change_date DESC)` |

**Existing indexes on `practices` (data_axle relevant):**

| Index name | Definition |
|---|---|
| `idx_practices_data_axle` | `CREATE INDEX ... ON practices USING btree (data_axle_import_date) WHERE (data_axle_import_date IS NOT NULL)` |
| `ix_practices_data_axle_import_date` | `CREATE INDEX ... ON practices USING btree (data_axle_import_date) WHERE (data_axle_import_date IS NOT NULL)` |

Both indexes exist in the exact partial-index form requested (`WHERE data_axle_import_date IS NOT NULL`). The indexes match the task specification exactly — no DDL was needed.

### EXPLAIN ANALYZE — activity-feed query (practice_changes)

Query: `SELECT id,npi,change_date,... FROM practice_changes WHERE change_date >= '2026-02-28' ORDER BY change_date DESC LIMIT 500`

```
Limit  (cost=0.15..22.00 rows=500 width=153) (actual time=1.988..12.426 rows=500 loops=1)
  ->  Index Scan using ix_practice_changes_change_date_desc on practice_changes
        Index Cond: (change_date >= '2026-02-28'::date)
Planning Time: 30.232 ms
Execution Time: 13.292 ms
```

**Status: INDEX SCAN. Execution time 13ms. No seq scan, no timeout.**

### EXPLAIN ANALYZE — enrichedCount query (practices)

Query: `SELECT COUNT(npi) FROM practices WHERE data_axle_import_date IS NOT NULL`

```
Aggregate  (cost=189.27..189.28 rows=1 width=8) (actual time=349.473..349.474 rows=1 loops=1)
  ->  Index Scan using ix_practices_data_axle_import_date on practices
        (actual time=3.677..347.838 rows=2981 loops=1)
Planning Time: 22.107 ms
Execution Time: 349.571 ms
```

**Status: INDEX SCAN over 2,981 rows. Execution time 350ms. No seq scan, no timeout.**

Note: 350ms is slower than the activity-feed query because it must aggregate all 2,981 matching rows (not a limit scan). This is the realistic cost of a `COUNT(*)` over an index — fast enough for a Next.js server component, not a timeout source.

### pg_indexes listing (both tables)

```
TABLE=practice_changes  INDEX=idx_practice_changes_date
TABLE=practice_changes  INDEX=ix_practice_changes_change_date_desc
TABLE=practice_changes  INDEX=ix_practice_changes_npi
TABLE=practice_changes  INDEX=ix_practice_changes_type_date
TABLE=practice_changes  INDEX=practice_changes_pkey
TABLE=practices  INDEX=idx_practices_buyability
TABLE=practices  INDEX=idx_practices_data_axle
TABLE=practices  INDEX=idx_practices_entity_classification
TABLE=practices  INDEX=idx_practices_year_est
TABLE=practices  INDEX=idx_practices_zip_entity
TABLE=practices  INDEX=ix_practices_buyability_score
TABLE=practices  INDEX=ix_practices_data_axle_import_date
TABLE=practices  INDEX=ix_practices_entity_classification
TABLE=practices  INDEX=ix_practices_status
TABLE=practices  INDEX=ix_practices_updated
TABLE=practices  INDEX=ix_practices_updated_at_desc
TABLE=practices  INDEX=ix_practices_zip
TABLE=practices  INDEX=ix_practices_zip_npi
TABLE=practices  INDEX=practices_npi_key
TABLE=practices  INDEX=practices_pkey
```

---

## TASK 3 — keep-supabase-alive.yml green run

**Workflow dispatched:** `gh workflow run keep-supabase-alive.yml` on `suleman7-DMD/dental-pe-tracker` main branch.

**Run URL:** https://github.com/suleman7-DMD/dental-pe-tracker/actions/runs/26694806987

**Run ID:** 26694806987

**Status:** `completed / success` (7s total)

**The 200 log line (verbatim):**
```
ping  Ping Supabase REST endpoint  2026-05-30T21:00:31.2025446Z  Supabase REST responded with status: 200
```

The workflow pinged `${SUPABASE_URL}/rest/v1/deals?select=deal_date&limit=1` with the anon key. Status 200 confirms Supabase project is live and anon key is valid.

**Deal freshness check (bonus output):**
```
ping  Check deal freshness  2026-05-30T21:00:31.4538070Z  Most recent deal_date: 2026-05-22 (8 days ago)
```

**Prior runs were failing** (schedule runs on 2026-05-25 and 2026-05-28 both `failure`) because the workflow was pinging the bare `/rest/v1/` root which rejects anon keys with 401. The fix committed to main changed the ping target to `/rest/v1/deals?select=deal_date&limit=1` — a real table query that 200s with the anon key. This `workflow_dispatch` run is the first green run.

---

## Summary

| Task | Result |
|------|--------|
| practice_changes order column | `change_date DESC` — confirmed in both query files |
| enrichedCount column/table | `data_axle_import_date` on `practices` — confirmed |
| Indexes needed | Both already existed on prod (`ix_practice_changes_change_date_desc`, `ix_practices_data_axle_import_date`) |
| DDL executed | None required (idempotent IF NOT EXISTS would be no-ops) |
| activity-feed EXPLAIN | Index Scan, 13ms — fast |
| enrichedCount EXPLAIN | Index Scan, 350ms — fast, no timeout |
| keep-alive run | Run 26694806987 — SUCCESS, `Supabase REST responded with status: 200` |
