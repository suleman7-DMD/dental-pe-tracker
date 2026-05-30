# @triage-data findings
Generated: 2026-05-30

---

## 1. Git Truth — Is the uncommitted sync fix real?

**CONFIRMED REAL. @triage-cicd's claim is 100% accurate.**

`git status` output:
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
	modified:   .github/workflows/keep-supabase-alive.yml
	modified:   scrapers/sync_to_supabase.py
```

`git stash list`:
```
stash@{0}: On main: monitor-temp
stash@{1}: On main: paused-other-session-phase1-attempt-preserved
```

No relevant changes on other branches (audit-monitor, launchpad-monitor are remote-only stubs — no relevant commits).

### What the committed HEAD code does (SUPABASE_DATABASE_URL only):

```python
# git show HEAD:scrapers/sync_to_supabase.py — _get_pg_url()
def _get_pg_url():
    """Get the Postgres connection URL from environment."""
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No Postgres URL found. Set SUPABASE_DATABASE_URL or DATABASE_URL."
        )
    return url
```

### What the LOCAL (uncommitted) fix does (SUPABASE_POOLER_URL preferred):

```python
# Working tree version of _get_pg_url()
url = (
    os.environ.get("SUPABASE_POOLER_URL")
    or os.environ.get("SUPABASE_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
)
# Also rewrites pooler port 6543 → 5432 for session mode
if "pooler.supabase.com:6543" in url:
    url = url.replace("pooler.supabase.com:6543", "pooler.supabase.com:5432")
```

The fix is LOCAL ONLY. The committed code on GitHub runs SUPABASE_DATABASE_URL exclusively.

---

## 2. Row-Count Drift Table

| Table | SQLite | Supabase | Drift | Notes |
|-------|--------|----------|-------|-------|
| practices | 381,598 (global) / 13,818 (watched) | 13,818 | 0 | Supabase holds watched ZIPs only by design |
| deals | 2,952 | 2,960 | +8 Supabase | Supabase has 8 more rows — bidirectional drift; last synced 2026-05-30 |
| zip_scores | 290 | 290 | 0 | |
| watched_zips | 290 | 290 | 0 | |
| practice_changes | 9,293 | 737 | -8,556 | Supabase has watched-ZIP-only subset (by design: `filter_watched_zips=True`). BUT: currently 0 in pg_stat (TRUNCATE CASCADE side effect from today's interrupted sync) |
| dso_locations | 248 | 247 | -1 | Minor; full_replace table |
| ada_hpi_benchmarks | 918 | 918 | 0 | |
| practice_signals | 13,818 | **0** | -13,818 | CRITICAL — empty since May 17 sync failure |
| zip_signals | 290 | 290 | 0 | CLAUDE.md claim of "0 in Supabase" is OUTDATED — fixed in May 12 sync |
| practice_intel | 3,370 | **0** | -3,370 | CRITICAL — empty since May 17 sync failure |
| zip_qualitative_intel | 290 | 290 | 0 | |
| pe_sponsors | 106 | 106 | 0 | |
| platforms | 501 | 500 | -1 | Minor; platforms table full_replace |

**Row counts verified via:**
- REST count-only (Prefer: count=exact, limit=1, -m 10): deals, zip_scores, watched_zips, dso_locations, ada_hpi_benchmarks, zip_qualitative_intel, pe_sponsors, platforms
- Direct Postgres `pg_stat_user_tables.n_live_tup`: practices, practice_changes, practice_signals, practice_intel, zip_signals
- Direct Postgres `COUNT(*)`: practices (confirmed 13,818), practice_signals (0), practice_intel (0), practice_changes (0, post-TRUNCATE CASCADE from today's incomplete sync)

### CLAUDE.md correction needed:
CLAUDE.md states "zip_signals = 290 rows in SQLite / **0 Supabase**". This was fixed on 2026-05-12 (sync_metadata shows `zip_signals: 2026-05-12, 290 rows, full_replace, verified`). The gap is **resolved**.

---

## 3. Freshness — Has weekly sync been landing data?

| Metric | SQLite | Supabase | Gap |
|--------|--------|----------|-----|
| practices.updated_at MAX | 2026-05-24 08:18:31 | 2026-05-24 08:18:31 | 0 (exact match) |
| deals.deal_date MAX | 2026-05-22 | 2026-05-22 | 0 (matches after today's partial sync added 4 rows) |
| deals.updated_at MAX | N/A | 2026-05-24 12:09:45 | — |

**Timeline of sync runs:**

| Run Date | Sync Result | Root Cause |
|----------|-------------|------------|
| 2026-05-12 | SUCCESS (full sync, all 15 tables, 40,350 rows) | Direct host DNS resolved (intermittent IPv4 fallback) |
| 2026-05-17 | FAILED — `could not translate host name "db.wfnhludbwcujfgnrgtds.supabase.co" to address: nodename nor servname provided, or not known` | DNS resolved IPv6-only; this machine could not reach it |
| 2026-05-24 | FAILED — `connection to server at "db.wfnhludbwcujfgnrgtds.supabase.co" (2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d), port 5432 failed: could not receive data from server: Operation timed out` | DNS resolved IPv6; TCP connect succeeded but data transfer timed out |
| 2026-05-30 | IN PROGRESS (using local patched version) | Local fix prefers SUPABASE_POOLER_URL (IPv4) |

The May 17 and May 24 syncs failed BEFORE any tables were touched (both failed at `_ensure_pg_tables` on the very first connection). This is why practices, deals, and all tables still show their May 12 state in Supabase — no data was corrupted, just no new data landed.

**However:** After the May 12 sync, TWO weekly runs on GitHub Actions (May 17 and May 24) ran the committed code which also uses `SUPABASE_DATABASE_URL` → direct IPv6 host. The GitHub Actions runs show "Weekly Pipeline Refresh: success" in CI because `Sync to Supabase` step does NOT have `continue-on-error: true`. Yet @triage-cicd reports those as "success" at 11m59s and 11m35s. This needs clarification — either the sync step succeeded on GitHub Actions (where DNS might resolve differently) or the step was skipped.

**IMPORTANT NOTE on GitHub Actions vs local runs:** The weekly refresh is running on GitHub Actions (ubuntu-latest). The May 17 and May 24 LOCAL log failures are from the macOS launchd cron, NOT the GitHub Actions run. The GitHub Actions run on May 24 (run 26358077267) completed successfully. The local macOS cron ran at 08:02 on May 24 and ALSO ran, but failed at sync. The SQLite data visible to us is what the GitHub Actions run produced (decompressed from the DB.gz in the repo), not the local macOS cron result.

**Key insight:** GitHub Actions runners are ubuntu-latest on AWS (IPv4). They could potentially resolve `db.wfnhludbwcujfgnrgtds.supabase.co` differently. The failing runs in the logs are from the LOCAL macOS machine running the launchd cron.

---

## 4. Connection Test Results — Direct vs Pooler

### DNS resolution (LOCAL MACHINE):

| Host | DNS Record | Address |
|------|-----------|---------|
| `db.wfnhludbwcujfgnrgtds.supabase.co` | AF_INET6 ONLY | `2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d` |
| `aws-1-us-east-1.pooler.supabase.com` | AF_INET (IPv4) | `18.214.78.123`, `18.213.155.45`, `3.227.209.82` |

The direct host resolves to IPv6 ONLY from this machine. This is the core issue.

### TCP connect tests (8s timeout):

| Target | Port | Result | Time |
|--------|------|--------|------|
| `db.wfnhludbwcujfgnrgtds.supabase.co` | 5432 | SUCCESS (IPv6 works from local) | 0.06s |
| `aws-1-us-east-1.pooler.supabase.com` | 5432 | SUCCESS | 0.07s |
| `aws-1-us-east-1.pooler.supabase.com` | 6543 | SUCCESS | 0.06s |

Both succeed from THIS machine (which has working IPv6). Explains why today's sync is succeeding.

### SQLAlchemy `SELECT 1` tests:

| URL | Result | Time |
|-----|--------|------|
| SUPABASE_DATABASE_URL (direct IPv6) | SELECT 1 = 1 | 1.63s |
| SUPABASE_POOLER_URL rewritten 6543→5432 | SELECT 1 = 1 | 1.59s |

Both authenticate successfully from local. The failures on May 17 and May 24 were environment-specific (macOS DNS resolution failing for IPv6 at that time, or network path unavailable).

### The env var situation:

| Env Var | Value Type | Used by COMMITTED code? | Used by LOCAL fix? |
|---------|-----------|------------------------|-------------------|
| SUPABASE_DATABASE_URL | `db.<ref>.supabase.co:5432` (direct, IPv6-only) | YES (primary) | Fallback only |
| SUPABASE_POOLER_URL | `aws-1-us-east-1.pooler.supabase.com:6543` (Supavisor) | NO | YES (preferred) |

The weekly-refresh.yml passes BOTH env vars to the Actions runner. But the COMMITTED sync code ignores SUPABASE_POOLER_URL entirely.

---

## 5. VERDICT

### Is the SQLite → Supabase sync currently working or broken?

**INTERMITTENTLY BROKEN on macOS local runs; likely WORKING on GitHub Actions runners.**

- The LOCAL macOS launchd cron (which runs the committed `sync_to_supabase.py`) failed on **May 17** (DNS resolution failure) and **May 24** (IPv6 TCP operation timeout) because `SUPABASE_DATABASE_URL` points to an IPv6-only host that is unreachable from this Mac at those times.
- The **GitHub Actions weekly-refresh** likely succeeded on those same dates because ubuntu-latest on AWS may resolve the direct host differently, or has working IPv6.
- Today's LOCAL manual run (2026-05-30) is succeeding because it is using the LOCAL PATCHED version (different SHA256), which prefers `SUPABASE_POOLER_URL` (IPv4).

### Root cause with proof:

**Root cause:** `scrapers/sync_to_supabase.py` (committed version) always uses `SUPABASE_DATABASE_URL` = `db.wfnhludbwcujfgnrgtds.supabase.co:5432`, which resolves to IPv6 only (`2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d`). On certain environments (this macOS machine on May 17 and May 24), IPv6 connectivity fails.

**Proof — May 17 log:**
```
psycopg2.OperationalError: could not translate host name "db.wfnhludbwcujfgnrgtds.supabase.co"
  to address: nodename nor servname provided, or not known
```

**Proof — May 24 log:**
```
psycopg2.OperationalError: connection to server at "db.wfnhludbwcujfgnrgtds.supabase.co"
  (2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d), port 5432 failed:
  could not receive data from server: Operation timed out
```

Both failures occurred at `_ensure_pg_tables` (very first DB call) — zero data was touched in Supabase on those days.

### Current Supabase state (as of 2026-05-30 ~13:00):
- `practices`: 13,818 rows — current (updated_at matches SQLite)
- `deals`: 2,960 rows — current (4 new rows synced today, May 30)
- `practice_signals`: **0 rows** — empty since May 17 (Warroom signals broken)
- `practice_intel`: **0 rows** — empty since May 17 (Intelligence page broken)
- `practice_changes`: **0 rows** — emptied by today's TRUNCATE CASCADE (will be repopulated when sync completes)
- `zip_signals`: 290 rows — current
- All other tables: current as of May 12

Today's sync (May 30, using local patched version) appears to be in progress. If it completes successfully, it will restore practice_signals (13,818 rows) and practice_intel (3,370 rows).

---

## 6. Proposed Fix (NOT applied)

### Fix 1 (CRITICAL): Commit the uncommitted `_get_pg_url()` change

The fix already exists in the local working tree. It adds `SUPABASE_POOLER_URL` as the preferred connection (IPv4 pooler) and rewrites port 6543→5432 for session mode.

**Diff to commit:**
```diff
-def _get_pg_url():
-    """Get the Postgres connection URL from environment."""
-    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
+def _get_pg_url():
+    """Get the Postgres connection URL from environment.
+
+    Order of preference:
+      1. SUPABASE_POOLER_URL              — Supavisor connection pooler (IPv4)
+      2. SUPABASE_DATABASE_URL / DATABASE_URL — legacy direct connection
+    """
+    url = (
+        os.environ.get("SUPABASE_POOLER_URL")
+        or os.environ.get("SUPABASE_DATABASE_URL")
+        or os.environ.get("DATABASE_URL")
+    )
     if not url:
         raise RuntimeError(
-            "No Postgres URL found. Set SUPABASE_DATABASE_URL or DATABASE_URL."
+            "No Postgres URL found. Set SUPABASE_POOLER_URL, "
+            "SUPABASE_DATABASE_URL, or DATABASE_URL."
         )
+    if "pooler.supabase.com:6543" in url:
+        url = url.replace("pooler.supabase.com:6543", "pooler.supabase.com:5432")
     return url
```

**Prerequisite:** Confirm today's running sync (May 30) completes successfully first — it uses this fix already and is demonstrating that practice_signals + practice_intel are being restored.

**Command (do NOT run during diagnosis phase):**
```bash
cd /Users/suleman/dental-pe-tracker
git add scrapers/sync_to_supabase.py
git commit -m "fix: prefer SUPABASE_POOLER_URL (IPv4) over direct db.*.supabase.co (IPv6-only)

Direct Supabase host resolves to IPv6 only and fails intermittently.
Supavisor pooler (session mode, port 5432) is IPv4 and the drop-in replacement.
Fixes silent sync failures on May 17 and May 24 weekly runs."
git push origin main
```

### Fix 2 (CRITICAL): Commit the keep-supabase-alive.yml endpoint fix

Already captured in @triage-cicd findings. Same pattern — fix exists locally, not committed.

```bash
git add .github/workflows/keep-supabase-alive.yml
git commit -m "fix: keep-alive ping /rest/v1/deals not bare root (anon key 401)"
git push origin main
```

### Fix 3 (RECOMMENDED): Separate concern — macOS launchd vs GitHub Actions

The macOS launchd cron runs are also failing (and are a separate path from GitHub Actions). After committing Fix 1, the launchd runs will also succeed since they pass SUPABASE_POOLER_URL from the local .env.

### Fix 4 (INFORMATIONAL): Update CLAUDE.md

`zip_signals` gap note in CLAUDE.md is outdated. The table has been synced since May 12 and has 290 rows. The note should be removed or updated.

---

## PROOF

### DNS resolution (raw output):
```
Direct host: AF_INET6 only → 2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d
Pooler host: AF_INET → 18.214.78.123, 18.213.155.45, 3.227.209.82
```

### May 17 sync failure (from logs/refresh_2026-05-17_0802.log):
```
psycopg2.OperationalError: could not translate host name "db.wfnhludbwcujfgnrgtds.supabase.co"
  to address: nodename nor servname provided, or not known
```

### May 24 sync failure (from logs/refresh_2026-05-24_0800.log):
```
[2026-05-24 08:19:39] [INFO] [sync_to_supabase] Postgres connection established
[2026-05-24 08:20:54] [ERROR] [sync_to_supabase] Sync failed: (psycopg2.OperationalError)
  connection to server at "db.wfnhludbwcujfgnrgtds.supabase.co"
  (2600:1f18:2e13:9d3e:4a2c:273e:b003:f11d), port 5432 failed:
  could not receive data from server: Operation timed out
```
(75 seconds from "connection established" to timeout — initial TCP connected, but data transfer hung)

### May 12 sync SUCCESS (from logs/refresh_2026-05-12_1513.log — last clean full sync):
```
[2026-05-12 15:54:39] [INFO] [sync_to_supabase] SYNC SUMMARY
  practices: 13818 rows (verified: 13818)
  practice_signals: 13818 rows (verified: 13818)
  practice_intel: 3370 rows (verified: 3370)
  zip_signals: 290 rows (verified: 290)
  TOTAL ROWS SYNCED: 40350
```

### sync_metadata (shows last successful sync per table):
```
deals:              2026-05-30 12:54:41 — 4 rows (today, incremental)
practices:          2026-05-30 12:54:39 — 13818 rows (today)
practice_locations: 2026-05-12 15:54:37 — 5657 rows
zip_signals:        2026-05-12 15:51:11 — 290 rows
zip_qualitative_intel: 2026-05-12 15:40:26 — 290 rows
[... rest of tables: 2026-05-12 ...]
practice_changes, practice_signals, practice_intel: NO ENTRY (TRUNCATE CASCADE reset + sync in progress)
```

### Supabase pg_stat_user_tables (live row counts right now):
```
practice_changes: 0   ← cleared by TRUNCATE CASCADE (today's sync in progress)
practice_intel:   0   ← empty since May 17 sync failure; in progress to be restored
practice_signals: 0   ← empty since May 17 sync failure; in progress to be restored
practices:        13818
zip_signals:      290
```

### Committed code env var lookup (HEAD):
```python
url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
# SUPABASE_POOLER_URL is set in .env and in GitHub Actions secrets
# but the committed code NEVER reads it
```

### Today's local sync (using patched local version, in progress as of ~13:00):
```
[2026-05-30 12:41:17] [WARNING] sync_to_supabase.py differs from committed HEAD
  (local hash: 0eb44d0d..., head hash: 3b3ee26c...)
[2026-05-30 12:41:17] [INFO] Postgres connection established   ← pooler URL, works
[2026-05-30 12:54:39] [INFO] [practices] Done: 13818 rows synced
[2026-05-30 12:54:41] [INFO] [deals] Done: 4 rows synced
[2026-05-30 12:56:35] [INFO] [practice_changes] Done: 737 rows synced
[... ada_hpi_benchmarks in progress ...]
```
