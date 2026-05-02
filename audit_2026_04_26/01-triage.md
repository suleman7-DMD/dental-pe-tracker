# @triage findings
Generated: 2026-04-26 ~21:15 local (ET). Read-only investigation — no code modified.

---

## Top-line verdict

**The data pipeline ran successfully today and Supabase is largely current.** The last completed sync finished at 20:40 (verified 40,420 rows across 15 tables, 0 errors). A third sync is still running as of this writing (started 20:53, currently writing `practice_signals`). There are two genuine P0/P1 issues: (1) `practice_signals` and `zip_signals` show **0 rows in Supabase right now** because the in-progress sync is mid-TRUNCATE CASCADE — the app is serving stale/empty signal data during this window. (2) The CLAUDE.md **canonical number documentation is stale** — today's pipeline produced a significantly different entity_classification distribution (solo_established dropped by 918, non_clinical jumped +726, a new `org_only_npi` class appeared with 580 rows). The headline GP location count dropped from the documented 4,889 to 4,833. Corporate location count (225) still matches.

---

## Row count comparison table

| Table | SQLite count | Supabase count | Last updated_at (SQLite) | Last updated_at (Supabase) | Verdict |
|-------|-------------:|---------------:|---|---|---|
| practices | 381,598 global / **13,818 watched** | **13,818** | 2026-04-26 12:21:01 | 2026-04-26T12:21:01 | **FRESH** |
| practice_locations | 5,732 | 5,732 | 2026-04-26T04:01:16 | (no separate ts) | **FRESH** |
| deals | 2,907 | 2,916 | 2026-04-27 00:52:31 (UTC) | 2026-04-27T00:52:31 (UTC) | **DRIFT** (+9) — sync in progress will add 20 more |
| practice_changes | 9,293 (global) / **737 watched** | **737** | 2026-04-26 12:16:15 | 2026-04-24T21:59:21 | **FRESH** (737 is by-design filter to watched ZIPs) |
| zip_scores | 290 | 290 | score_date: 2026-04-26 | score_date: 2026-04-26 | **FRESH** |
| watched_zips | 290 | 290 | — | — | **FRESH** |
| dso_locations | 249 | 249 | scraped_at: 2026-04-26 16:20:21 | scraped_at: 2026-04-26T16:20:21 | **FRESH** |
| ada_hpi_benchmarks | 918 | 918 | 2026-04-23 23:59:01 | 2026-04-23T23:59:01 | **FRESH** |
| practice_signals | 13,818 | **0 / TIMEOUT** | created_at: 2026-04-26T12:22:10 | — | **MISSING** (mid-sync TRUNCATE CASCADE) |
| zip_signals | 290 | **0** | (no updated_at col) | — | **MISSING** (mid-sync; will recover when 20:53 sync completes) |
| pe_sponsors | 106 | 106 | — | — | **FRESH** |
| platforms | 491 | 491 | — | — | **FRESH** |
| zip_overviews | 12 | 12 | — | — | **FRESH** |
| zip_qualitative_intel | 290 | 290 | 2026-04-25 16:59:12 | 2026-04-25T16:59:12 | **FRESH** |
| practice_intel | 3,370 | **TIMEOUT** (count unavailable) | 2026-04-26 15:06:35 | — | **UNKNOWN** — Supabase query times out; 20:40 sync verified 3,370 rows |

**Notes on apparent discrepancies:**
- `practice_changes`: 9,293 SQLite vs 737 Supabase is **by design** — sync explicitly filters to watched ZIPs (`9293 → 737 rows` logged).
- `deals`: Supabase count was 2,916 when measured, SQLite is 2,907 at that moment. The gap is 9 deals synced in the 20:08 run but not yet reflected in SQLite timestamp. The running 20:53 sync pushes 20 more incremental deals.
- `practice_signals` / `zip_signals`: Supabase shows 0 rows — this is a live outage window. TRUNCATE CASCADE ran at 20:53:33, the new data hasn't landed yet (write in progress at 21:09 as of log tail).

---

## Pipeline event log analysis

Last 10 entries from `logs/pipeline_events.jsonl` (most recent first):

```
2026-04-26T20:53:26 | sync_to_supabase | scrape_start  — [STILL RUNNING as of 21:15]
2026-04-26T20:40:23 | sync_to_supabase | scrape_complete — "Synced 40420 total rows to Supabase (15 tables, 0 errors)"
                      table_results: practices=13818, deals=9, practice_changes=737, zip_scores=290,
                      watched_zips=290, dso_locations=249, ada_hpi_benchmarks=918, pe_sponsors=106,
                      platforms=491, zip_overviews=12, zip_qualitative_intel=290, practice_intel=3370,
                      practice_signals=13818, zip_signals=290, practice_locations=5732
                      verified_row_counts: matches table_results exactly — CLEAN
2026-04-26T20:08:12 | sync_to_supabase | scrape_start  (completed at 20:40)
2026-04-26T12:22:14 | compute_signals  | scrape_complete — 13818 practice rows, 290 ZIP rows
2026-04-26T12:22:10 | compute_signals  | scrape_start
2026-04-26T12:22:01 | weekly_research  | scrape_complete — "Batch mode: 1 batches submitted, 20 items"
2026-04-26T12:22:00 | weekly_research  | scrape_start
2026-04-26T12:21:57 | merge_and_score  | scrape_complete — dedup: 18 dupes found, 14 merged. practices=381598
2026-04-26T12:21:21 | merge_and_score  | scrape_start
2026-04-26T12:21:04 | dso_classifier  | scrape_complete — "0 changes — PE:0, DSO:0, Indep:0, Unk:34908"
```

**Errors found in `logs/dental_tracker_2026-04-26.log`:**

| Time | Severity | Component | Error |
|------|----------|-----------|-------|
| 00:05 | ERROR | fast_sync_locations_and_scores | Batch 2000-2500 FAILED: QueryCanceled (statement timeout) |
| 00:06 | ERROR | fast_sync_locations_and_scores | Batches 2500-3000 and 3000-3500 FAILED: UniqueViolation on `practice_locations_pkey` → aborted |
| 00:20 | ERROR | fast_sync | practice_intel: canceling statement due to statement timeout |
| 00:24 | ERROR | fast_sync | practice_intel: value too long for type character varying(20) |
| 00:27 | ERROR | sync_to_supabase | practice_intel: StringDataRightTruncation — value too long for character varying(20) |
| 10:54 | ERROR | fast_sync | zip_qualitative_intel: is_synthetic boolean vs integer mismatch |
| 11:17 | ERROR | sync_to_supabase | zip_qualitative_intel: DatatypeMismatch is_synthetic |
| 12:35 | ERROR | sync_to_supabase | zip_qualitative_intel: DatatypeMismatch is_synthetic (again) |

**The is_synthetic errors were fixed by commit `077ef00` at 12:37 and do not recur in the 20:08 and 20:53 syncs.**

The `practice_intel` varchar(20) truncation error at 00:27 is NOT shown to have been fixed. It did not recur in the 20:08 sync (which succeeded for practice_intel: 3370 rows). Likely the offending row was not re-encountered in the incremental window.

The midnight `fast_sync_locations_and_scores` errors are from a separate script (not `sync_to_supabase.py`), likely a manual run. The UniqueViolation on `practice_locations_pkey` means a dedup problem in `practice_locations` — some `location_id` values are duplicated across batches in that script's insert path. The main sync (`sync_to_supabase.py`) handles `practice_locations` via TRUNCATE+INSERT and does NOT have this problem.

---

## Last successful sync

**20:40:23 local time (2026-04-26)** — sync started 20:08:12, completed 20:40:23 (32 min 11 sec), 40,420 rows across 15 tables, 0 errors. Verified by `sync_to_supabase | scrape_complete` event in `logs/pipeline_events.jsonl`.

Evidence trail:
- `logs/pipeline_events.jsonl` line: `"Synced 40420 total rows to Supabase (15 tables, 0 errors)"`
- `logs/dental_tracker_2026-04-26.log`: line `[2026-04-26 20:40:23] [INFO] [sync_to_supabase]   practice_signals   13818 rows (verified: 13818)`

A third sync began at 20:53 and was still in progress (~21:09 writing practice_signals) at investigation time. When it finishes it will push 20 incremental deals + full-replace all 15 tables again.

**Earlier today (cron run):** `cron_refresh.log` shows the automated Sunday pipeline completed at 08:43:40 with 40,902 total rows synced (15 tables, 0 errors). This is the canonical weekly run.

---

## SQLite DB compression status

```
dental_pe_tracker.db    218,718,208 bytes  mtime: Apr 26 20:52
dental_pe_tracker.db.gz  50,312,221 bytes  mtime: Apr 26 12:52
```

**The .gz is 8 hours older than the .db.** The compressed file reflects the state after the morning cron run (12:52), not the afternoon runs. If Streamlit Cloud pulls git and decompresses, it will see morning data (missing the 20:08 and 20:53 sync results and any afternoon practice_intel updates). This gap only matters for the Streamlit legacy app; Next.js reads Supabase directly.

---

## CLAUDE.md canonical numbers check

### Structural invariants (MATCH)
| Invariant | CLAUDE.md | SQLite actual | Supabase actual | Status |
|-----------|----------:|-------------:|----------------:|--------|
| Global practices | 381,598 | 381,598 | 13,818 watched only* | OK |
| Watched NPI rows | 13,818 | 13,818 | 13,818 | **MATCH** |
| Watched locations | 5,732 | 5,732 | 5,732 | **MATCH** |
| Watched ZIPs | 290 | 290 | 290 | **MATCH** |
| IL ZIPs | 269 | 269 | — | **MATCH** |
| MA ZIPs | 21 | 21 | — | **MATCH** |
| Corporate GP locations | 225 | 225 | — | **MATCH** |
| ada_hpi_benchmarks rows | 918 | 918 | 918 | **MATCH** |

*Supabase `practices` only holds watched NPIs (13,818) — global 381k is never synced, by design.

### Canonical numbers with drift
| Invariant | CLAUDE.md says | SQLite actual | Delta | Status |
|-----------|---------------:|-------------:|------:|--------|
| GP locations (zip_scores SUM) | 4,889 | **4,833** | **-56** | STALE DOC |
| CHI GP locations | 4,575 | **4,520** | **-55** | STALE DOC |
| BOS GP locations | 314 | **313** | **-1** | STALE DOC |
| Corporate NPIs (watched) | 882 | **875** | **-7** | STALE DOC |
| Total deals | 2,895 (2532+353+10) | **2,907** | **+12** | STALE DOC |
| GDN deals | 2,532 | **2,568** | **+36** | STALE DOC |
| PESP deals | 353 | **329** | **-24** | STALE DOC |

### Entity classification distribution — MAJOR DRIFT

CLAUDE.md documents the following as canonical NPI-row counts for watched practices. **These are significantly wrong as of today's run (2026-04-26 12:21):**

| Classification | CLAUDE.md | SQLite actual | Delta |
|---|---:|---:|---:|
| solo_established | 3,575 | **2,657** | **-918** |
| small_group | 2,727 | **2,830** | +103 |
| large_group | 2,456 | **2,326** | -130 |
| specialist | 2,353 | **1,419** | **-934** |
| family_practice | 1,701 | **1,334** | -367 |
| solo_high_volume | 709 | **873** | +164 |
| dso_national | 222 | **404** | **+182** |
| solo_inactive | 170 | **165** | -5 |
| dso_regional | 244 | **471** | **+227** |
| solo_new | 17 | 17 | 0 |
| non_clinical | 16 | **742** | **+726** |
| org_only_npi | (NOT IN CLAUDE.MD) | **580** | NEW |
| NULL | 0 | 0 | 0 |

**Root cause:** Today's `dso_classifier` run at 08:16 produced `DSO:+475, Indep:-448` changes, followed by a second run at 12:21. Additionally, `org_only_npi` is a 12th entity_classification value not documented in CLAUDE.md's 11-value list — it exists in `dedup_practice_locations.py` and `reclassify_locations.py`, and Next.js handles it (classifies as "unknown"), but CLAUDE.md's canonical table omits it.

The `non_clinical` explosion (16→742) and `org_only_npi` emergence (0→580) represent real reclassification that happened in today's pipeline. These values all have `updated_at = 2026-04-26 12:21:01`, confirming they were set by today's run.

**Impact on headline metrics:** `merge_and_score.py` includes `org_only_npi` in GP counts (not excluded in the `gp_locations` bucket loop at line 382-390). Next.js's `classifyPractice()` maps `org_only_npi → "unknown"`. So zip_scores reports 4,833 GP locations that include 584 `org_only_npi` entries, but the frontend calls those "unknown" rather than GP. This is an internal inconsistency: the pipeline denominator includes them, the frontend display doesn't count them as any ownership category.

---

## Critical issues found (P0/P1)

- **[P0] practice_signals and zip_signals are EMPTY in Supabase right now** — The 20:53 sync issued TRUNCATE CASCADE at 20:53:33 and was still writing practice_signals (13,818 rows) at 21:09. Until the sync completes (~21:20 estimated), any Warroom page that reads `practice_signals` for its 8-flag overlay returns 0 rows. This will self-heal when the sync completes. Evidence: `log: [2026-04-26 21:09:07] practice_signals Full replace: 13818 rows` still in progress; Supabase REST API returns empty/timeout for practice_signals.

- **[P0] practice_intel table times out on every Supabase REST query** — Every attempt to query `practice_intel` via the REST API returns `{"code":"57014","message":"canceling statement due to statement timeout"}`. This table has 3,370 rows; it timed out even for `limit=1`. The 20:40 sync verified 3,370 rows were written, but the table is not queryable from the API (missing index on a frequently-queried column, or a large TOAST column causing slow sequential scan). The Launchpad compound-narrative route and the Intelligence page practice dossiers depend on this table being queryable.

- **[P1] CLAUDE.md canonical numbers are stale** — Entity classification distribution has shifted dramatically since the documented values (solo_established -918, non_clinical +726, org_only_npi appears as new 12th class with 580 rows, dso_regional +227, dso_national +182). GP location counts are 56 fewer than documented. Anyone quoting the CLAUDE.md numbers is giving wrong figures. The documentation needs to be updated to reflect the post-2026-04-26 pipeline run.

- **[P1] org_only_npi is counted as GP in zip_scores but as "unknown" in Next.js** — 584 locations classified as `org_only_npi` (organization NPI with 0 individual providers — billing/admin only entities) are included in `total_gp_locations` by `merge_and_score.py`'s else-catch but mapped to "unknown" by `classifyPractice()` in the frontend. This means the headline GP count (4,833) is inflated by up to 584 phantom GP locations. If these were excluded, real GP count would be ~4,249.

- **[P1] zip_qualitative_intel had 3 sync failures today before fix** — The `is_synthetic` Integer→Boolean schema drift caused `DatatypeMismatch` errors at 10:54, 11:17, and 12:35. Each time the TRUNCATE was rolled back, so 290 rows remained live from the previous run. Commit `077ef00` fixed this at 12:37. The 20:08 and 20:53 syncs both succeeded. No current data loss, but it burned 3 sync cycles.

- **[P1] .db.gz is 8 hours stale** — `data/dental_pe_tracker.db.gz` was last compressed at 12:52 (after the morning cron). The afternoon runs (which updated practice_intel with 20 new batch results, added ~20 deals, recomputed signals) are not in the gzip. Streamlit Cloud will see morning data. The git log shows `c13c595 Auto-refresh 2026-04-26` was committed, which compressed the DB — but subsequent runs after 12:52 are not captured.

- **[P1] Midnight fast_sync_locations_and_scores had UniqueViolation crash** — At 00:06, `fast_sync_locations_and_scores` failed with `UniqueViolation: duplicate key value violates unique constraint "practice_locations_pkey"` and aborted after 3 batch failures. This is a separate script from the main sync. The main `sync_to_supabase.py` uses TRUNCATE+INSERT which is immune to this, but the fast_sync script has a dedup bug in its insert path.
