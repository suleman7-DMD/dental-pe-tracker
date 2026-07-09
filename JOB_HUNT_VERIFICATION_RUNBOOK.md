# job_hunt_verification — durability runbook

The job-hunt verification layer records what each practice's **own website**
says: public practice name, current doctors, owner/operator statement, hiring
page, openings. It lives in Supabase (`public.job_hunt_verification`, one row
per `practice_locations.location_id`) and drives two frontend behaviors in
`dental-pe-nextjs`:

- **Job-hunt lanes** — `src/lib/census/job-lane.ts` maps `verification_status`
  to a verified lane (hiring_page_found > roster_verified > call_required >
  stale_recheck > ownership_conflict > no_usable_website) above the base
  census-derived lanes, and computes the honest "Still missing" list.
- **Display-name precedence** — `src/lib/census/display-name.ts`
  `verifiedDisplayName()`: `public_practice_name` outranks the census/legal
  name on the practice page, job-market directory, and detail drawer
  ("Eagle Falls Dentistry", not "MY DENTIST FAMILY, LTD").

## Durable artifacts (this repo)

| Artifact | Path |
|---|---|
| DDL (CREATE TABLE IF NOT EXISTS + checks + FK) | `scrapers/job_hunt_verification_schema.sql` |
| Full-row seed export (source of truth) | `data/job_hunt_verification_seed.json` |
| Import / upsert / verify / export script | `scrapers/import_job_hunt_verification.py` |

## Commands

```bash
cd ~/dental-pe-tracker

# Validate the seed file offline (no DB access)
python3 -m scrapers.import_job_hunt_verification

# Recreate or update the live table from the seed
# (applies the DDL if the table is missing, then upserts every row —
#  INSERT ... ON CONFLICT (location_id) DO UPDATE; idempotent)
python3 -m scrapers.import_job_hunt_verification --allow-db-write

# Count check: live counts by verification_status must equal the seed's
python3 -m scrapers.import_job_hunt_verification --verify

# After NEW verification rows land in Supabase: refresh the seed and commit it
python3 -m scrapers.import_job_hunt_verification --export
git add data/job_hunt_verification_seed.json && git commit
```

Connection comes from `SUPABASE_POOLER_URL` (fallback `SUPABASE_DATABASE_URL`)
in `.env`. The FK requires `practice_locations` to exist first.

## Expected counts — Codex QA baseline, 2026-07-09

48 rows total:

| verification_status | rows |
|---|---|
| roster_verified | 28 |
| no_usable_website | 12 |
| ownership_conflict | 4 |
| call_required | 2 |
| hiring_page_found | 2 |

`--verify` hard-fails when live ≠ seed, and reports (informationally) when
counts drift from this baseline — expected as later enrichment tiers land.
The rule after any change: **live and seed must always match**; whichever one
is truth, sync the other (`--export` when live is truth, `--allow-db-write`
when the seed is truth).

## Status vocabularies (enforced by CHECK constraints)

- `verification_status`: roster_verified, hiring_page_found, call_required,
  no_usable_website, ownership_conflict, stale_recheck
- `website_status`: live, dead, parked, social_only, none_found
- `ownership_evidence_status`: consistent, conflict, no_statement

Records older than 90 days fall to the `stale_recheck` lane in the frontend
(`STALE_AFTER_DAYS` in job-lane.ts) — recheck and upsert with a fresh
`last_checked_at` to restore their lane.
