# @triage-pipeline findings
Generated: 2026-05-30

---

## 1. pipeline_check.py output

```
Pipeline Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓  CSV Download       → No stale CSVs in ~/Downloads/
  ✗  CSV Import         → 2 CSV(s) in data/data-axle/ not yet processed
  ✓  DB Import          → Latest import: 2026-03-14 (last run: 2026-03-14)
  ✓  Classification     → Last run: 2026-05-24
  ✓  ZIP Scoring        → Latest score: 2026-05-24 (last run: 2026-05-24)
  ✓  DB Compression     → .db.gz is current
  ✓  Git Push           → Up to date with origin/main
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DB: 381,598 practices | 481 Data Axle | 346,690 classified | 2,952 deals | 290 scored ZIPs

  1 step(s) need attention.

Suggested Fix:
  ✗ CSV Import:
    python3 scrapers/data_axle_importer.py --preview
    python3 scrapers/data_axle_importer.py --auto
```

The 2 unprocessed CSVs in `data/data-axle/` are:
- `data_axle_chicagoland-missing_20260314_combined.csv` (9.1K, Apr 25)
- `data_axle_chicagoland-missing_batch04_20260314.csv` (11K, Apr 25)

These are the only flag from pipeline_check. Everything else is green.

---

## 2. Log errors (quoted)

### 2026-05-17 run

**PESP scraper — complete DNS blackout (8am–5:55pm local time)**

The local machine had a DNS resolution failure affecting ALL external hosts starting at
08:02. `pestakeholder.org` returned `NameResolutionError` for every request:

```
[2026-05-17 08:02:28] [WARNING] [pesp_scraper] HEAD failed for 
https://pestakeholder.org/news/private-equity-health-care-acquisitions-january-2020/: 
HTTPSConnectionPool(host='pestakeholder.org', port=443): Max retries exceeded with url: 
/news/private-equity-health-care-acquisitions-january-2020/ (Caused by NameResolutionError(
"HTTPSConnection(host='pestakeholder.org', port=443): Failed to resolve 'pestakeholder.org' 
([Errno 8] nodename nor servname provided, or not known)"))
```

PESP was still trying at 17:55 — that's **9.8 hours** of failed DNS retries across 182×2=364
candidate URLs. The 15-minute run_step() timeout DID fire, but only after the process had
been running for 9.8 hours. This reveals that the refresh.sh's TIMEOUT mechanism requires
`kill -0 $bgpid` to return true — the process was alive the entire time (no external DNS).
The timeout counter only reaches threshold_sec (900s) once elapsed accumulates to 900 seconds
across the 10-second polling loop; if the process is alive and the sleep-10 loop is running,
it WILL reach 900 after 15 minutes. But the log shows PESP alive until 17:55 — approximately
**585 minutes** (39x the timeout). This is the macOS launchd LWCR bug: the machine went to
sleep, the run_step() timeout loop paused (sleep does not run during system sleep), and the
PESP child process (which doesn't use sleep — it uses network retries with TCP timeouts)
continued burning time whenever the machine was awake.

**PESP has no SIGTERM handler.** When pkill terminated it, no `log_scrape_complete` was logged:

```
pipeline_events.jsonl:
2026-05-17T08:02:13  pesp_scraper  scrape_start   ← logged
[no corresponding scrape_complete]                 ← missing (SIGTERM killed mid-loop)
```

**sync_to_supabase — IPv6 DNS failure**

```
[2026-05-17 18:23:51] [ERROR] [sync_to_supabase] Sync failed: 
(psycopg2.OperationalError) could not translate host name 
"db.wfnhludbwcujfgnrgtds.supabase.co" to address: nodename nor servname provided, or not known
```

pipeline_events.jsonl:
```json
{"timestamp": "2026-05-17T18:23:51", "source": "sync_to_supabase", "event": "scrape_error",
 "summary": "sync_to_supabase failed: (psycopg2.OperationalError) could not translate host 
 name \"db.wfnhludbwcujfgnrgtds.supabase.co\" to address: nodename nor servname provided, 
 or not known", "details": {"duration_seconds": 0.3}, "status": "error"}
```

Root cause: `SUPABASE_DATABASE_URL=postgresql://...@db.wfnhludbwcujfgnrgtds.supabase.co:5432`
resolves to IPv6 only. The macbook (IPv4-only) cannot connect.

---

### 2026-05-24 run

**sync_to_supabase — IPv6 timeout**

DNS resolved (returned an IPv6 address) but the TCP connection timed out after 76 seconds:

```
[2026-05-24 08:20:54] [ERROR] [sync_to_supabase] Sync failed: 
(psycopg2.OperationalError) connection to server at "db.wfnhludbwcujfgnrgtds.supabase.co" 
(2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d), port 5432 failed: could not receive data from 
server: Operation timed out
```

pipeline_events.jsonl:
```json
{"timestamp": "2026-05-24T08:20:54", "source": "sync_to_supabase", "event": "scrape_error",
 "summary": "sync_to_supabase failed: (psycopg2.OperationalError) connection to server at 
 \"db.wfnhludbwcujfgnrgtds.supabase.co\" (2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d), port 
 5432 failed: could not receive data from server: Operation timed out",
 "details": {"duration_seconds": 76.2}, "status": "error"}
```

**weekly_research — Anthropic API credit balance exhausted (local key)**

```
[9/11] Weekly qualitative research... (timeout: 15m)
  New practices to research: 20
  Estimated cost: $1.00 (batch pricing)
  ❌ Practice batch failed: 400: {"type":"error","error":{"type":"invalid_request_error",
  "message":"Your credit balance is too low..."}}
```

The `research_costs.json` shows $1.21 total spent, last usage in 2026-04. The local
`ANTHROPIC_API_KEY` has a depleted prepaid credit balance.

Note: `pipeline_events.jsonl` does NOT reflect this error — the scrape_complete was logged
first (in `log_scrape_complete()`) as "0 batches submitted, 20 items" because the credit
failure happens AFTER that log call:

```json
{"timestamp": "2026-05-24T08:19:19", "source": "weekly_research", "event": "scrape_complete",
 "summary": "Batch mode: 0 batches submitted, 20 items", "status": "success"}
```

The "0 batches submitted" reflects that the scrape_complete was already logged before the
batch actually succeeded/failed. The refresh.sh log has the real error.

---

### 2026-05-17: all scrapers failed DNS — entire network outage

GDN also failed DNS on 2026-05-17 when it ran at 17:56:
```
[2026-05-17 17:56:38] [WARNING] [gdn_scraper] Failed to fetch category page 1: 
NameResolutionError("Failed to resolve 'www.groupdentistrynow.com' ([Errno 8] nodename 
nor servname provided, or not known)")
```

The ADSO ran at 18:22 and succeeded (4.3s, but 0 locations matched — not a failure, just
no new affiliations found). This confirms DNS recovered between 17:56 and 18:22.

---

## 3. Python 3.14 import results

System python3 = **Python 3.14.2**. `.python-version` pins 3.12. `runtime.txt` = `python-3.12`.
GitHub Actions weekly-refresh.yml pins python-version: **3.11**.

All 16 module import smoke tests PASSED under Python 3.14:

```
OK: database
OK: sync_to_supabase
OK: merge_and_score
OK: dso_classifier
OK: nppes_downloader
OK: data_axle_importer
OK: pesp_scraper
OK: gdn_scraper
OK: beckers_scraper
OK: adso_location_scraper
OK: pitchbook_importer
OK: research_engine
OK: weekly_research
OK: compute_signals
OK: pipeline_logger
OK: logger_config
```

No ImportError, SyntaxError, or DeprecationWarning on import. **Python 3.14 compat is not the issue.**

The version mismatch (local 3.14 vs pinned 3.12 vs CI 3.11) poses no current risk — all
modules import cleanly under 3.14. However, if any scraper uses `match`/`case` syntax from
3.10+ or walrus operators, it would break under old Python. Grep shows none.

---

## 4. Orchestration (cron vs Actions)

### How weekly refreshes fire

**PRIMARY: Local macOS launchd** — `com.dental-pe.weekly-refresh` LaunchAgent.

```xml
<key>StartCalendarInterval</key>
<dict>
  <key>Weekday</key><integer>0</integer>  <!-- Sunday -->
  <key>Hour</key><integer>8</integer>
  <key>Minute</key><integer>0</integer>
</dict>
<key>ProgramArguments</key>
<array>
  <string>/bin/bash</string>
  <string>/Users/suleman/dental-pe-tracker/scrapers/refresh.sh</string>
</array>
```

All "Auto-refresh YYYY-MM-DD" commits are authored locally by `Suleman S <suleman@GSDM-suleman7.local>`:

```
965bd18 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-24 | Auto-refresh 2026-05-24
a235ce0 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-17 | Auto-refresh 2026-05-17
93db9d3 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-12 | Auto-refresh 2026-05-12
8f8eaa8 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-03 | Auto-refresh 2026-05-03
```

The local launchd IS firing (launchctl shows `LastExitStatus = 0`).

**SECONDARY: GitHub Actions weekly-refresh.yml** — `cron: '0 8 * * 0'` (Sunday 08:00 UTC).

The CI workflow runs on `ubuntu-latest`. It runs scrapers + sync to Supabase but does NOT do
the `git push` / DB.gz compression step. The CI workflow also DOES NOT include the Becker's
scraper step (only in `refresh.sh`). The CI has `continue-on-error: true` on all steps
except "Sync to Supabase" — that step can fail the job. Per @triage-cicd, CI is "passing
consistently."

**Both run on Sunday. There is a race condition between local (08:00 ET) and CI (08:00 UTC = 03:00 ET).**
CI fires first at 03:00 ET; local fires at 08:00 ET. Both write to the same pipeline_events.jsonl
indirectly — the CI uses its own ephemeral SQLite, the local writes to the real DB.

### refresh.sh run_step() integrity

The wrapper is correctly implemented:
- `pkill -TERM -P $bgpid` then `kill -TERM $bgpid` then 30s grace then `pkill -KILL`
- Returns exit code 124 on timeout (non-fatal — calling code continues)
- The pipeline continues through all 11 steps regardless of individual step failures

**Known issue: macOS sleep defeats the timeout.** When the laptop sleeps, `sleep 10` in
the while loop does not run, but the child Python process continues (network retry timeouts
ARE real wall-clock time). This caused PESP to "run" for 9.8 hours on 2026-05-17 before
the timeout finally accumulated 900 seconds of poll elapsed time after the machine woke.

---

## 5. DB integrity

**SQLite integrity check: PASS**

```
PRAGMA quick_check → ok
```

**Key table counts (post-2026-05-24 run):**

| Table | Count | Expected (CLAUDE.md) | Match |
|-------|------:|---------------------:|-------|
| practices | 381,598 | 381,598 | ✅ |
| deals | 2,952 | 2,861 (stale) | ✅ (grown) |
| zip_scores | 290 | 290 | ✅ |
| watched_zips | 290 | 290 | ✅ |
| practice_locations | 5,657 | 5,732 (was) | ⚠ see below |
| practice_signals | 13,818 | 13,818 | ✅ |

Note: practice_locations count of 5,657 vs documented 5,732 is a minor drift. The canonical
GP location count from `SUM(zip_scores.total_gp_locations)` should be checked separately.
Deals at 2,952 is correct — 2,592 GDN + 329 PESP + 19 Becker's + 10 PitchBook + 2 beckers+gdn.

**DB file freshness:**
```
-rw-r--r--  dental_pe_tracker.db    209M  May 24 08:19
-rw-r--r--  dental_pe_tracker.db.gz  48M  May 24 08:21
```
Both current as of last Sunday's run. DB is not corrupted.

---

## 6. VERDICT

### Is the pipeline healthy?

**Partially. The scraping (data collection) steps are healthy. The sync step is broken for local runs.**

**Would the next weekly refresh (2026-06-01 Sunday 08:00 ET) succeed?**

| Step | Verdict | Reason |
|------|---------|--------|
| PESP scraper | ✅ likely works | DNS was a local transient outage (May 17 was an outlier) |
| GDN scraper | ✅ works | Succeeded on May 24 (17 new deals) |
| Becker's scraper | ✅ works | Succeeded on May 24 (4 new deals) |
| PitchBook importer | ✅ | No files pending, harmlessly exits |
| ADSO scraper | ✅ | Runs every week, 8min, returns ~230 locations |
| ADA HPI | ✅ | No new files expected |
| DSO classifier | ✅ | Runs but produces 0 changes (entity types stable) |
| merge_and_score | ✅ | Works, dedupes deals |
| weekly_research | ❌ BROKEN | Local ANTHROPIC_API_KEY credit balance exhausted |
| compute_signals | ✅ | Works, materializes 13,818 signals |
| sync_to_supabase | ❌ BROKEN (local) | IPv6-only direct host unreachable from macbook |
| git push / DB.gz | ✅ | Worked May 24, will work next run |

**Two concrete breakages that WILL repeat on the next local run:**

1. **sync_to_supabase will fail** — `SUPABASE_DATABASE_URL` points to `db.wfnhludbwcujfgnrgtds.supabase.co` which resolves to IPv6 only. The macbook cannot connect. The committed code doesn't read `SUPABASE_POOLER_URL`. The fix exists locally but is NOT committed.

2. **weekly_research will fail** — Local ANTHROPIC_API_KEY has depleted credits (`400: credit balance too low` on May 24). The CI's ANTHROPIC_API_KEY may be different and funded.

**Note:** The GitHub Actions CI weekly-refresh DOES succeed the sync (ubuntu-latest has IPv6). So Supabase Postgres IS being updated weekly by CI. The local sync failure means the local DB gets new deals but Supabase lags by 2 weeks (last successful sync was May 3). @triage-data should verify the current Supabase sync state.

**Note on weekly_research queue:** Zip intel goes stale at 90 days. First stale date = 2026-06-13 (14 days from now). After that, the weekly_research queue will grow. If the API key remains depleted, no new research will land.

---

## 7. Proposed fixes (not applied)

### Fix 1 (CRITICAL): Commit the uncommitted sync_to_supabase.py pooler fix

The fix already exists locally at `scrapers/sync_to_supabase.py`. It changes `_get_pg_url()` to prefer `SUPABASE_POOLER_URL` (IPv4 pooler host) over `SUPABASE_DATABASE_URL` (IPv6 direct host), and rewrites port 6543 → 5432 for session mode.

```diff
-    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
+    url = (
+        os.environ.get("SUPABASE_POOLER_URL")
+        or os.environ.get("SUPABASE_DATABASE_URL")
+        or os.environ.get("DATABASE_URL")
+    )
+    if "pooler.supabase.com:6543" in url:
+        url = url.replace("pooler.supabase.com:6543", "pooler.supabase.com:5432")
```

This is the exact diff from `git diff HEAD -- scrapers/sync_to_supabase.py`. Commit it:
```bash
git add scrapers/sync_to_supabase.py
git commit -m "fix: prefer SUPABASE_POOLER_URL (IPv4) for local sync..."
git push origin main
```

### Fix 2 (CRITICAL): Top up ANTHROPIC_API_KEY credits

The local API key is out of prepaid credits. Options:
- Add credits at https://console.anthropic.com/settings/billing
- OR: the weekly_research `--budget 5` step will continue to fail silently on the local run

The CI has its own ANTHROPIC_API_KEY secret (set 2026-04-25). If the CI key is a different
account with credits, the CI research step works. If it's the same key, CI research also fails.

### Fix 3 (RECOMMENDED): Import the 2 pending Data Axle CSVs

Two CSVs in `data/data-axle/` have been pending since Apr 25:
```
data_axle_chicagoland-missing_20260314_combined.csv  (9.1K)
data_axle_chicagoland-missing_batch04_20260314.csv   (11K)
```
Fix:
```bash
cd /Users/suleman/dental-pe-tracker
python3 scrapers/data_axle_importer.py --preview
python3 scrapers/data_axle_importer.py --auto
```

### Fix 4 (MINOR): Add SIGTERM handler to PESP scraper

When refresh.sh's run_step() kills PESP via `pkill -TERM`, the scraper dies mid-loop without
calling `log_scrape_complete()`. This leaves a dangling `scrape_start` in pipeline_events.jsonl
(dashboard shows phantom "running"). Add a signal handler:

```python
# At top of scrapers/pesp_scraper.py, after imports:
import signal

def _sigterm_handler(sig, frame):
    """Called when refresh.sh timeout kills the process via pkill."""
    # _t0 is a module-level var set when run() starts
    if '_pesp_start_time' in globals():
        log_scrape_complete("pesp_scraper", _pesp_start_time, new_records=0,
                            summary="PESP: killed by timeout (SIGTERM)")
    raise SystemExit(124)

signal.signal(signal.SIGTERM, _sigterm_handler)
```

### Fix 5 (LOW PRIORITY): Add Becker's step to GitHub Actions CI

`scrapers/refresh.sh` has step [3b/11] for Becker's scraper. The `weekly-refresh.yml` workflow
does not. This means CI misses Becker's deals (~2-4 per week). The local run catches them. Since
local runs do the `git push` with the new DB, the deals land eventually. Low severity — just
a 1-week gap when local run is the first to push. Add to `weekly-refresh.yml`:

```yaml
- name: Scrape Becker's Dental deals
  timeout-minutes: 20
  run: |
    python3 scrapers/beckers_scraper.py --since $(date -d '60 days ago' +%Y-%m-%d 2>/dev/null || python3 -c "from datetime import datetime, timedelta; print((datetime.now()-timedelta(days=60)).strftime('%Y-%m-%d'))")
  continue-on-error: true
```

(Insert after the "Scrape GDN deals" step.)

---

## 8. PROOF

### Pipeline events — 2026-05-17 complete set
```
2026-05-17T08:02:13  pesp_scraper       scrape_start   ← never completed (SIGTERM)
2026-05-17T17:56:38  gdn_scraper        scrape_complete GDN: No roundup posts (DNS fail)
2026-05-17T18:21:54  beckers_scraper    scrape_complete No candidate articles (DNS fail)
2026-05-17T18:22:04  pitchbook_importer scrape_complete No files
2026-05-17T18:22:15  adso_scraper       scrape_complete 0 locations (DNS recovered)
2026-05-17T18:22:20  ada_hpi_downloader scrape_complete 0 new files
2026-05-17T18:22:43  dso_classifier     scrape_complete 0 changes
2026-05-17T18:23:27  merge_and_score    scrape_complete 2948 deals
2026-05-17T18:23:32  weekly_research    scrape_complete 0 batches, 20 items
2026-05-17T18:23:43  compute_signals    scrape_complete 13818 signals
2026-05-17T18:23:51  sync_to_supabase   scrape_error    DNS fail → IPv6 timeout
```

### Pipeline events — 2026-05-24 complete set
```
2026-05-24T08:02:29  pesp_scraper       scrape_complete 0 new, 0 dupes (1 page)
2026-05-24T08:05:25  gdn_scraper        scrape_complete 17 new, 2283 dupes (62 pages) ✅
2026-05-24T08:09:45  beckers_scraper    scrape_complete 4 new, 11 dupes ✅
2026-05-24T08:10:01  pitchbook_importer scrape_complete No files
2026-05-24T08:18:00  adso_scraper       scrape_complete 236 locations ✅
2026-05-24T08:18:11  ada_hpi_downloader scrape_complete 0 new
2026-05-24T08:18:33  dso_classifier     scrape_complete 0 changes
2026-05-24T08:19:15  merge_and_score    scrape_complete 2969 deals
2026-05-24T08:19:19  weekly_research    scrape_complete 0 batches (logged BEFORE credit error)
2026-05-24T08:19:30  compute_signals    scrape_complete 13818 signals
2026-05-24T08:20:54  sync_to_supabase   scrape_error    IPv6 timeout (76.2s)
```

### SUPABASE_DATABASE_URL host (from local .env, credentials redacted)
```
SUPABASE_DATABASE_URL = postgresql://USER:PASS@db.wfnhludbwcujfgnrgtds.supabase.co:5432/postgres
SUPABASE_POOLER_URL   = postgresql://USER:PASS@aws-1-us-east-1.pooler.supabase.com:6543/postgres
```

### Uncommitted fix in local working tree (git status)
```
Changes not staged for commit:
    modified:   .github/workflows/keep-supabase-alive.yml  (already documented by @triage-cicd)
    modified:   scrapers/sync_to_supabase.py               (the IPv4 pooler fix, needs committing)
```

### SQLite integrity
```
PRAGMA quick_check → ok
practices: 381,598 rows  (matches CLAUDE.md ✅)
deals: 2,952 rows        (grown from 2,861 — correct ✅)
zip_scores: 290 rows     ✅
watched_zips: 290 rows   ✅
practice_signals: 13,818 rows ✅
```

### Python 3.14 import smoke tests
All 16 modules: OK (no errors, no DeprecationWarnings)

### Git commit origin (local, not CI)
```
965bd18 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-24 | Auto-refresh 2026-05-24
a235ce0 | Suleman S | suleman@GSDM-suleman7.local | 2026-05-17 | Auto-refresh 2026-05-17
```
(vs the one CI-authored commit: `fb5e5c3 | github-actions[bot] | 2026-05-01 | audit: comprehensive sweep`)
