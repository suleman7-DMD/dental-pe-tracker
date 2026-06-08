# @verify-state Audit Report — 2026-05-30

Read-only fact-check of concurrent session commits. All evidence is raw command output.

---

## 1. KEEP-ALIVE FIX STATE — FIXED (committed, pushed)

**Command:** `git show HEAD:.github/workflows/keep-supabase-alive.yml | grep -n "rest/v1"`

```
29:          # NOTE: ping a real table, NOT the /rest/v1/ root. As of 2026 the
36:            "${SUPABASE_URL}/rest/v1/deals?select=deal_date&limit=1" \
41:            echo "::error::Supabase /rest/v1/deals returned ${STATUS} — project may be paused or credentials invalid."
49:            "${SUPABASE_URL}/rest/v1/deals?select=deal_date&order=deal_date.desc&limit=1" \
```

**Verdict: FIXED in committed HEAD.** Pings `/rest/v1/deals?select=deal_date&limit=1`, NOT the bare `/rest/v1/` root. HEAD == origin/main (703215e), so this IS pushed to GitHub.

**HOWEVER: The most recent run (2026-05-28T15:27:56Z) pre-dates commit 9cefd7f (2026-05-30T15:14:20).** That run still ran the OLD code and got `401 "Secret API key required"` from the bare root. No green run has happened with the new code yet. Next scheduled run is 2026-05-31T12:00Z.

**Additional blocker: SUPABASE_URL and SUPABASE_ANON_KEY repo secrets.** The May-28 run log shows secrets ARE present (`env: SUPABASE_URL: ***`) — but it still got 401, meaning the OLD code hit the bare root. With the new code now pushed, the next run should pass IF the anon key has table-level access (which the local curl test confirms it does).

---

## 2. SYNC FIX STATE — FIXED (committed, pushed)

**Command:** `git show HEAD:scrapers/sync_to_supabase.py | sed -n '/def _get_pg_url/,/raise RuntimeError/p'`

```python
def _get_pg_url():
    """Get the Postgres connection URL from environment.

    Order of preference:
      1. SUPABASE_POOLER_URL              — Supavisor connection pooler (IPv4)
      2. SUPABASE_DATABASE_URL / DATABASE_URL — legacy direct connection
    ...
    """
    url = (
        os.environ.get("SUPABASE_POOLER_URL")
        or os.environ.get("SUPABASE_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError(
```

**Verdict: FIXED.** Prefers `SUPABASE_POOLER_URL` (IPv4, Supavisor SESSION mode) before falling back to direct `SUPABASE_DATABASE_URL`. Fix committed in `9cefd7f` (2026-05-30T15:14:20). HEAD == origin/main, PUSHED.

---

## 3. PUSH STATE — BOTH REPOS: 0 AHEAD, 0 BEHIND (fully pushed)

**Root repo:**
```
git fetch origin  # clean
git log origin/main..HEAD --oneline  # (empty — 0 commits ahead)
git status -sb
## main...origin/main
?? data/dental_pe_tracker.db.bak_audit_20260530
```

HEAD = origin/main = `703215e` (docs: update floor 4.02%→5.27% across CLAUDE.md after IL DSO seeding)

**Next.js repo:**
```
git fetch origin  # clean
git log origin/main..HEAD --oneline  # (empty — 0 commits ahead)
git status -sb
## main...origin/main
?? playwright.config.ts
?? playwright.vercel.config.ts
?? playwright/
?? tests/
```

HEAD = origin/main = `274430c` (docs: update corporate floor 4.02%→5.27%)

**Verdict: BOTH REPOS FULLY PUSHED. 0 unpushed commits. Only untracked files remain locally (db.bak and playwright test scaffolding — not committed).**

The keep-alive fix AND the pooler-URL sync fix are LIVE on GitHub origin/main.

---

## 4. WHAT THE CONCURRENT SESSION CHANGED

**`9cefd7f` (2026-05-30T15:14:20) — "fix(data-integrity): location-level classification + honest corporate floor"**
15 files, 2,791 insertions. Key: **`keep-supabase-alive.yml` FIXED** (bare root → /rest/v1/deals), **`sync_to_supabase.py` FIXED** (pooler URL preference added), `reclassify_locations.py` rewritten, `dso_brands.py` added, 5 new warroom triage docs.

**`18e2adc` (2026-05-30) — "chore(dso): refresh dso_locations (real ADSO run) + surgical single-table sync"**
2 files. Added `scrapers/_sync_dso_locations_only.py`. No keep-alive or sync_to_supabase changes.

**`2610a44` (2026-05-30) — "feat: extensive IL DSO seeding + verified-corporate reclassification (floor 4.02%→5.27%)"**
10 files, 10,880 insertions. DSO research data files + new scrapers (seed_il_dso_locations.py, dso_web_locators.py, mine_il_dso_from_nppes.py, reclassify_verified_corporate_il.py, _sync_floor_tables_only.py). No keep-alive or sync_to_supabase changes.

**Next.js `50df352` (2026-05-30) — "fix(frontend): unify GP denominator + confirmed-floor/ADA-band honesty"**
21 files, 595 insertions. Frontend honesty layer: `consolidation-honesty.ts` (new), GP denominator unification across home/job-market/market-intel/warroom, Sitrep KPI strip update. No keep-alive or sync changes.

---

## 5. CONCURRENT ACTIVITY NOW — IDLE (playwright MCP only, no scrapers running)

**Command:** `ps aux | grep -E "python3|playwright|node|next|scrapers" | grep -v grep`

```
suleman  6927  node .../playwright-mcp      (S+, 11:19AM, 0:00.85)
suleman  6913  node .../context7-mcp         (S+, 11:19AM, 0:00.90)
suleman  6871  npm exec @playwright/mcp@latest (S+, 11:19AM, 0:01.04)
```

**Verdict: No active scraper, sync, or Python processes. Three idle MCP server processes (playwright + context7) from the concurrent session. These are dormant — not writing data.**

---

## 6. SUPABASE DATA RESTORED — YES (all tables healthy)

**Command:** curl -m 12 with `Prefer: count=exact` on each table, reading `content-range` header.

| Table | Count | Expected | Status |
|-------|------:|------:|--------|
| `practice_signals` | **13,818** | ~13,818 | GOOD |
| `practice_intel` | **3,370** | ~3,370 | GOOD |
| `practices` | **13,818** | ~13,818 | GOOD (watched-ZIP slice) |
| `deals` | **2,960** | ~2,861+ | GOOD (slightly higher, may include new batch) |
| `zip_signals` | **290** | 290 | GOOD (previously 0 in Supabase — NOW RESTORED) |

**Verdict: ALL TABLES RESTORED. zip_signals was previously flagged as 0-row sync gap — it now shows 290 rows, meaning the concurrent session's `_sync_floor_tables_only.py` run fixed it. No data holes.**

---

## 7. KEEP-ALIVE LIVE STATUS — ALL RUNS STILL FAILURE (pre-fix runs only)

**Command:** `gh run list --workflow=keep-supabase-alive.yml --limit 5`

```
completed  failure  Keep Supabase Alive  main  schedule  26584431458  9s  2026-05-28T15:27:56Z
completed  failure  Keep Supabase Alive  main  schedule  26405762191  7s  2026-05-25T14:34:10Z
completed  failure  Keep Supabase Alive  main  schedule  26292998854  9s  2026-05-22T14:15:36Z
completed  failure  Keep Supabase Alive  main  schedule  26104249231  9s  2026-05-19T14:36:47Z
completed  failure  Keep Supabase Alive  main  schedule  25962534550  8s  2026-05-16T12:58:29Z
```

**Root cause confirmed from run 26584431458 log:**
```
Supabase REST responded with status: 401
::error::Supabase /rest/v1/ returned 401 — project may be paused or credentials invalid.
{"message":"Secret API key required","hint":"Only secret API keys can be used for this endpoint."}
```

All 5 failures were the OLD code hitting the bare `/rest/v1/` root. The fix landed 2026-05-30T15:14:20. Next scheduled run: `0 12 */3 * *` → 2026-05-31T12:00Z. **No green run yet** — expected on next cron trigger.

---

## Summary State Table

| # | Item | Verdict | Evidence |
|---|------|---------|---------|
| 1 | Keep-alive fix (committed) | **FIXED** | grep confirms `/rest/v1/deals` not bare root |
| 2 | Sync pooler-URL fix (committed) | **FIXED** | `_get_pg_url()` prefers SUPABASE_POOLER_URL |
| 3 | Keep-alive fix (pushed to origin) | **PUSHED** | HEAD==origin/main=703215e, 0 commits ahead |
| 3 | Sync fix (pushed to origin) | **PUSHED** | Same, committed in 9cefd7f which is at origin/main |
| 4 | Concurrent commits summary | 3 root + 1 nextjs | 9cefd7f had both infra fixes; 2610a44/18e2adc were data-only |
| 5 | Other session activity | **IDLE** | Only dormant playwright/context7 MCP node procs |
| 6 | Supabase data state | **RESTORED** | practice_signals=13,818; practice_intel=3,370; zip_signals=290 |
| 7 | Keep-alive green run | **NOT YET** | All 5 runs pre-date the fix; next cron ~2026-05-31T12:00Z |

### One open action required
The keep-alive workflow will pass on next cron only if `SUPABASE_ANON_KEY` repo secret has table-level read access (not a service role key). Local curl confirms the anon key in `.env.local` returns 200 on `/rest/v1/deals`. If the repo secret uses the same anon key, next run should be GREEN.
