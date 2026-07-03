# PROOF — ORM census-column mapping + Supabase migration verification
**Date:** 2026-07-02 · **Author:** Fable (PM) · **Blockers cleared:** B1 (ORM/sync stripping), B2 (Supabase migration unverified)

## B1 — ORM mapping fixed (silent sync-strip blocker)

**Defect:** `scrapers/database.py` `Practice` and `PracticeLocation` ORM models did not map the 6
hand-verified ownership census columns, while both physical DBs already had them.
`sync_to_supabase.py` serializes via ORM introspection (`_get_column_names` / `_model_to_dict`),
so any sync after a census write would have **silently dropped every census value** — "we wrote
the census" locally, invisible in the app, no error raised.

**Fix (2026-07-02):** added to BOTH models in `scrapers/database.py`:
`ownership_tier` (Text), `pe_backed` (Boolean), `ownership_evidence_basis` (Text),
`ownership_evidence_urls` (Text), `ownership_confidence` (String(10)), `network_id` (Text) —
with a comment warning that unmapping them re-opens the silent-strip failure.

**Verification run (all PASS):**
- ORM mapper exposes all 6 on `Practice` and `PracticeLocation` ✅
- SQLite `PRAGMA table_info` has all 6 on both tables ✅
- No ORM column absent from SQLite (would break SELECTs): none ✅
- Live ORM smoke query on both models returns rows, `ownership_tier=None` ✅
- **Sync path direct proof:** `sync_to_supabase._get_column_names(Practice)` and
  `(PracticeLocation)` now include all 6 census columns ✅

## B2 — Supabase (Postgres) migration verified LIVE

Queried `information_schema.columns` + `pg_indexes` over `SUPABASE_DATABASE_URL` (2026-07-02):

| Table | 6 census columns | Types | ownership_tier notnull | Index |
|---|---|---|---|---|
| `practices` | all present | text ×4, boolean, varchar | **0** | `ix_practices_ownership_tier` ✅ |
| `practice_locations` | all present | text ×4, boolean, varchar | **0** | `ix_practice_locations_ownership_tier` ✅ |

No migration run was needed — `migrate_ownership_tier_cols.py`'s Postgres leg had already been
applied. Frozen-state invariant holds: **0 census rows written anywhere** (SQLite and Supabase
both 0/0 notnull).

## Consequence

The write path SQLite → sync → Supabase → Next.js is now structurally sound for census data.
Remaining pre-consolidation gates are evidence-side, not plumbing-side: validator URL hardening,
weak-row spot review, Fleet B 51-100 QA, and the consolidation proof package.
