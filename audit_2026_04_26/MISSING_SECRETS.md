# Missing GitHub Repo Secrets

**Action required by repo owner (suleman7@bu.edu)**

Two GitHub Actions workflows are failing because `SUPABASE_URL` and `SUPABASE_ANON_KEY` secrets are not set in the repo:

## Failing Workflows

1. **`keep-supabase-alive.yml`** (cron: every 3 days) — Last run 2026-04-25T12:39:55Z FAILED with exit code 3. Without this, the Supabase free-tier project may auto-pause after 7 days of API inactivity.

2. **`data-invariants.yml`** (cron: Monday 13:00 UTC) — Requires the same secrets to authenticate to Supabase REST API for the weekly data integrity check.

## How to Fix

1. Go to: https://github.com/suleman7-DMD/dental-pe-tracker/settings/secrets/actions
2. Click **"New repository secret"** for each of the following:

| Secret name | Value to set |
|-------------|-------------|
| `SUPABASE_URL` | `https://wfnhludbwcujfgnrgtds.supabase.co` |
| `SUPABASE_ANON_KEY` | `sb_publishable_vbQmrE8hZSdJBClAUnKCBg_XRZVWI11` |

## Note on existing secrets

The main weekly pipeline sync uses `SUPABASE_DATABASE_URL` (which IS correctly set), so the weekly data refresh continues to work. Only the keep-alive ping and the invariants CI need the REST API secrets.

## Why these are different secrets

- `SUPABASE_DATABASE_URL` — direct Postgres connection string (used by `sync_to_supabase.py` via psycopg2)
- `SUPABASE_URL` — REST API base URL (used by Supabase JS client and curl-based health checks)
- `SUPABASE_ANON_KEY` — publishable API key for REST/auth requests

Evidence: `scrapers/05-pipeline.md` §"GitHub Actions status": `"keep-supabase-alive.yml: FAILED on 2026-04-25T12:39:55Z — SUPABASE_URL and SUPABASE_ANON_KEY secrets are empty strings in the GitHub repo."`
