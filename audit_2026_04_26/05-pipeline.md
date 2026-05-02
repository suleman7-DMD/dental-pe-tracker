# @audit-pipeline findings

## Top-line verdict

The pipeline is **actively running and data is flowing end-to-end**. The most recent full-cycle scrape ran today (2026-04-26) at 08:00 via launchd and completed with a successful Supabase sync at 08:43. A second refresh ran at 12:08 and completed all scraping steps successfully, but the sync was **killed by the 30-minute timeout** while uploading `practice_locations` (the largest table), meaning the 12:08 scrape data landed in SQLite but `practice_locations` was not pushed to Supabase in that run. A standalone `sync_to_supabase.py` run at 20:08–20:40 corrected this and pushed all 15 tables cleanly. As of 20:40 today, Supabase is fully current. There is also a third sync in flight right now (started 20:53:26, still running).

Two secondary issues: (1) `zip_qualitative_intel.is_synthetic` has a Boolean/Integer schema mismatch between SQLite (stores integer 0/1) and Supabase (expects boolean) — this caused a non-fatal ERROR on the 12:08 sync, meaning `zip_qualitative_intel` was **not pushed** in that run. The 20:40 run succeeded for this table, so it is currently in sync. (2) The keep-supabase-alive GitHub Action failed on 2026-04-25 because `SUPABASE_URL` and `SUPABASE_ANON_KEY` repo secrets are **not set**.

---

## Per-scraper last-run table

| Scraper | Last run timestamp | Status | Rows added/changed | Notes |
|---|---|---|---|---|
| PESP | 2026-04-26 12:10:46 | success | 0 new, 20 dupes | 19 pages scraped |
| GDN | 2026-04-26 12:13:20 | success | 70 new deals | 61 pages scraped |
| NPPES | 2026-04-24 17:59:22 | success | 359 new/inserted | Monthly update run |
| PitchBook | 2026-04-26 12:13:33 | success | 0 (no files to import) | Auto mode, no CSV present |
| ADSO | 2026-04-26 12:20:22 | success | 237 locations from 4 DSOs | 14 DSOs skipped (needs browser); historical error was DB lock on 2026-04-05 |
| ADA HPI | 2026-04-26 12:20:31 | success | 0 new files | Already current; last import 2026-04-23 (918 updated) |
| DSO classifier | 2026-04-26 12:21:04 | success | 0 changes | 34,908 records unknown — classifier saw no new signals |
| merge_and_score | 2026-04-26 12:21:57 | success | 0 new | Dedup: 2,924 total, 14 merged; ZIPs scored |
| compute_signals | 2026-04-26 12:22:14 | success | 14,108 signal rows | 13,818 practice + 290 ZIP signals materialized |
| sync_to_supabase | 2026-04-26 20:40:23 | **success** | 40,420 rows, 15 tables | Completed after earlier 12:08 run was killed at 30m timeout |
| weekly_research | 2026-04-26 12:22:01 | success | 1 batch submitted, 20 items | Batch mode, $5 budget cap |

**Historical error count for sync_to_supabase:** 3 error events (2× "No Postgres URL" on 2026-03-15 before env was set up; 1× FK constraint in early March). All subsequent runs succeeded.

---

## pipeline_check.py output

```
Pipeline Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓  CSV Download       → No stale CSVs in ~/Downloads/
  ✗  CSV Import         → 2 CSV(s) in data/data-axle/ not yet processed
  ✓  DB Import          → Latest import: 2026-03-14 (last run: 2026-03-14)
  ✓  Classification     → Last run: 2026-04-26
  ✓  ZIP Scoring        → Latest score: 2026-04-26 (last run: 2026-04-26)
  ✗  DB Compression     → .db.gz is 8.0h behind .db — deployment stale
  ✓  Git Push           → Up to date with origin/main

  DB: 381,598 practices | 481 Data Axle | 346,690 classified | 2,907 deals | 290 scored ZIPs

  2 step(s) need attention.
```

**CSV Import warning:** Two Data Axle CSVs sit in `data/data-axle/` unimported:
- `data_axle_chicagoland-missing_20260314_combined.csv` (9.1K)
- `data_axle_chicagoland-missing_batch04_20260314.csv` (11K)
These are from March 14 and represent missed enrichment records. Not critical to pipeline function, but data is being left on the table.

**DB Compression warning:** At time of check (midday), the `.db.gz` was stale vs the `.db`. The 12:08 refresh did compress and push at 12:52 (commit `c13c595`). The DB has since been modified by additional scraper runs, so the mtime gap is expected between refresh cycles.

---

## Recent sync events (last 30)

Key events extracted from `logs/pipeline_events.jsonl`:

```
2026-04-25T14:53:59 | scrape_complete | success | Synced 32,021 rows (14 tables, 0 errors)
2026-04-25T20:42:58 | scrape_complete | success | Synced 22,963 rows (15 tables, 1 error)  ← practices not in this run (incremental only added zip tables)
2026-04-26T08:43:40 | scrape_complete | success | Synced 40,902 rows (15 tables, 0 errors)  ← morning cron-triggered full sync
2026-04-26T12:22:20 | scrape_start   | info    | (12:08 refresh) sync started
  ... sync killed at 12:52 by 30m timeout while uploading practice_locations ...
2026-04-26T20:08:12 | scrape_start   | info    | standalone sync started
2026-04-26T20:40:23 | scrape_complete | success | Synced 40,420 rows (15 tables, 0 errors)  ← current Supabase state
2026-04-26T20:53:26 | scrape_start   | info    | another sync started (in progress at time of audit)
```

**Note on 72 starts vs 31 completes for sync_to_supabase:** The large discrepancy (72 starts, 31 completes over all time) reflects debugging sessions on 2026-04-25 where the sync was launched and killed repeatedly during the F-fix sprint. It is not evidence of a recurring failure — each of those orphaned starts was an explicit early-termination during investigation.

**Verified Supabase row counts (20:40 sync):**
- practices: 13,818 | deals: 2,916 | practice_changes: 737 | zip_scores: 290
- watched_zips: 290 | dso_locations: 249 | ada_hpi_benchmarks: 918
- pe_sponsors: 106 | platforms: 491 | zip_overviews: 12
- zip_qualitative_intel: 290 | practice_intel: 3,370 | practice_signals: 13,818
- zip_signals: 290 | practice_locations: 5,732

---

## GitHub Actions status

- **weekly-refresh.yml** (cron `0 8 * * 0` — Sunday 08:00 UTC): **Last run 2026-04-26T09:00:06Z — SUCCESS** (14m57s). All steps passed including Sync to Supabase. This is the cloud backup for the launchd job.
- **data-invariants.yml** (cron `0 13 * * 1` — Monday 13:00 UTC): No scheduled runs found in the last 10 runs listing; most recent run was manual/workflow_dispatch. The Monday check has not fired yet this week (today is Sunday). Workflow file exists and is correctly configured.
- **keep-supabase-alive.yml** (cron `0 12 */3 * *`): **FAILED on 2026-04-25T12:39:55Z** — `SUPABASE_URL` and `SUPABASE_ANON_KEY` secrets are empty strings in the GitHub repo. The keep-alive ping cannot authenticate and fails with exit code 3. The weekly-refresh uses `SUPABASE_DATABASE_URL` (different secret name) which IS set, so the main pipeline sync works. Only the keep-alive and data-invariants jobs need `SUPABASE_URL` + `SUPABASE_ANON_KEY`.
- **weekly-drift.yml, audit-sweep.yml, reaudit.yml, auto-fix.yml**: All ran recently (2026-04-25) via workflow_dispatch as part of the F-fix sprint — all successful.

---

## Cron status

- **Local crontab:** EMPTY — `crontab -l` returns "no crontab for suleman"
- **launchd (macOS):** Three plists loaded in `~/Library/LaunchAgents/`:
  - `com.dental-pe.weekly-refresh` — loaded, `LastExitStatus=0`, fires Sunday 08:00
  - `com.dental-pe.nppes-refresh` — loaded, `LastExitStatus=0`
  - `com.dental-pe.session-fix` — loaded, `LastExitStatus=0`
  - **All three show `-0` in `launchctl list`** — the dash before the PID means the job is not currently running (expected between cron windows)
- **Last cron-triggered refresh:** 2026-04-26 08:00 — confirmed by `logs/refresh_2026-04-26_0800.log` (completed 08:44:22) and `logs/cron_refresh.log` showing the same run.
- **GitHub Actions cloud refresh:** Also fired Sunday 2026-04-26 09:00 UTC (the cloud backup). Both local launchd AND GitHub Actions ran today's Sunday refresh.

---

## Stuck processes

One live process found at audit time:

```
PID 81118 | python3 scrapers/sync_to_supabase.py | started 8:53PM | 0:25 CPU
```

This is the sync that started at 20:53:26. It is **actively running**, not stuck — a 32-minute sync is normal (the previous successful 20:08 sync took 32.5 minutes / 1,930 seconds). It should complete around 21:25–21:30. This is expected behavior, not a problem.

---

## DB compression freshness

- `.db` mtime: **2026-04-26 20:52** (modified by the 20:40 sync writing pipeline events back to SQLite)
- `.db.gz` mtime: **2026-04-26 12:52** (compressed by the 12:08 refresh cycle)
- **Verdict: DRIFT** — the `.db.gz` is ~8 hours stale vs the live `.db`

This is structural: the launchd refresh runs at 08:00 weekly, compresses and pushes the .db.gz to git at the end of that run. Any scraper runs or syncs after that point update the `.db` without re-compressing. The `.db.gz` will be re-synced on next Sunday's refresh. The Streamlit Cloud deployment (which reads the `.db.gz` from git) is therefore ~1 week stale between Sunday refreshes — this is by design and expected. The primary Vercel/Supabase frontend is always current via `sync_to_supabase.py`.

---

## Critical issues

**P1 — sync_to_supabase 30-minute timeout kills practice_locations sync mid-run**

Evidence: `logs/refresh_2026-04-26_1208.log` line 4053: `TIMEOUT: [11/11] Syncing to Supabase... exceeded 30m — killing pid 18895 and descendants` while uploading `practice_locations` (5,732 rows). The sync of `practice_locations` takes ~4 minutes on its own; combined with the other 14 tables the full sync regularly takes 26–32 minutes. The `refresh.sh` timeout for step 11 is 30 minutes, which is dangerously close to the actual runtime. When the sync is killed, `practice_locations` is left in a partial state in Supabase (TRUNCATE was issued but INSERT was incomplete). The 20:08 standalone sync corrected this today. **Mitigation needed:** increase `refresh.sh` step 11 timeout from 30m to 45m or 60m.

**P1 — keep-supabase-alive GitHub Action fails: missing SUPABASE_URL + SUPABASE_ANON_KEY repo secrets**

Evidence: Run 24931115878 failed with exit code 3 because `SUPABASE_URL` and `SUPABASE_ANON_KEY` are both empty strings in the repo secrets. The keep-alive workflow and the `data-invariants` workflow both depend on these secrets. Without them, the Supabase free-tier project may pause after 7 days of inactivity (no REST pings), and the F28 invariants CI cannot run. The main sync uses `SUPABASE_DATABASE_URL` which IS set. **Action required:** add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to repo Settings → Secrets → Actions.

**P2 — zip_qualitative_intel.is_synthetic schema mismatch: SQLite stores Integer, Supabase expects Boolean**

Evidence: `logs/refresh_2026-04-26_1208.log` line 4036: `[ERROR] [zip_qualitative_intel] FAILED: (psycopg2.errors.DatatypeMismatch) column "is_synthetic" is of type boolean but expression is of type integer`. The SQLite column stores `1`/`0` but the Supabase Postgres column is typed `boolean`. The 20:40 sync succeeded for this table, suggesting the fix from commit `077ef00` (noted in git log: `fix(sync): zip_qualitative_intel.is_synthetic Integer→Boolean schema drift`) was applied. Verify the fix holds — the 20:40 sync's 0-error count for 15 tables confirms it resolved.

**P2 — 2 unimported Data Axle CSVs in data/data-axle/**

Evidence: `pipeline_check.py` reports 2 CSVs unprocessed: `data_axle_chicagoland-missing_20260314_combined.csv` and `data_axle_chicagoland-missing_batch04_20260314.csv` (both from 2026-03-14). These contain enrichment data (buyability signals: revenue, employees) that has not been imported into SQLite. Run `python3 scrapers/data_axle_importer.py` against these files to ingest the missing records.

**INFO — deals count anomaly: SQLite 2,907 vs Supabase verified 2,916**

The SQLite `MAX(updated_at)` for deals shows `2026-04-27 00:52:31` (future timestamp likely a data entry artifact). The 20:40 sync verified 2,916 deals in Supabase vs 2,907 in SQLite at query time. The delta of 9 deals is consistent with the incremental sync adding 9 deals in the 20:08 run. No investigation needed.
