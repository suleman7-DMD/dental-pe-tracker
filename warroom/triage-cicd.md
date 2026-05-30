# @triage-cicd findings
Generated: 2026-05-30

---

## Tool channel status (did echo PROBE_OK work?)

YES — tools fully operational.

```
PROBE_OK
Sat May 30 12:40:19 EDT 2026
```

---

## Failing workflows (table: workflow | last run | conclusion | error summary)

| Workflow | Last Run | Date | Conclusion | Error Summary |
|----------|----------|------|------------|---------------|
| Keep Supabase Alive | 26584431458 | 2026-05-28 | FAILURE | `Supabase /rest/v1/ returned 401 — "Secret API key required"` |
| Keep Supabase Alive | 26405762191 | 2026-05-25 | FAILURE | Same 401 |
| Keep Supabase Alive | 26292998854 | 2026-05-22 | FAILURE | Same 401 |
| Keep Supabase Alive | 26104249231 | 2026-05-19 | FAILURE | Same 401 |
| Keep Supabase Alive | 25962534550 | 2026-05-16 | FAILURE | Same 401 |
| Keep Supabase Alive | 25804342688 | 2026-05-13 | FAILURE | Same 401 |
| Keep Supabase Alive | 25629277747 | 2026-05-10 | FAILURE | Same 401 |
| Keep Supabase Alive | 25498783074 | 2026-05-07 | FAILURE | Same 401 |
| Keep Supabase Alive | 25321472913 | 2026-05-04 | FAILURE | Same 401 |
| Keep Supabase Alive | 25215038360 | 2026-05-01 | FAILURE | Same 401 |
| Keep Supabase Alive | 25055697736 | 2026-04-28 | FAILURE | Same 401 |
| Keep Supabase Alive | 24931115878 | 2026-04-25 | FAILURE | exit code 3 (secrets missing at that time) |

**All other workflows are PASSING:**
- Data Invariants: passing consistently (weekly)
- Weekly Drift Check: passing consistently (weekly)
- Weekly Pipeline Refresh: passing consistently (weekly — latest 2026-05-24, 11m59s)
- Scheduled Re-Audit: all 8 passes completed, PASSING
- Comprehensive Audit Sweep: last ran 2026-05-01, PASSING (14m11s)
- Auto-Fix Round: last ran 2026-05-03, PASSING

**Keep Supabase Alive has a 100% failure rate since it was first scheduled** (every scheduled run is a failure; the only 2 successes were manual workflow_dispatch triggers on 2026-04-25 17:50 and 18:04 — the same hour the secrets were added).

---

## Root cause of notification emails

### Root cause #1 (PRIMARY): Wrong Supabase API endpoint in keep-supabase-alive.yml — COMMITTED version vs FIXED local version

The committed version of `.github/workflows/keep-supabase-alive.yml` (what GitHub actually runs) pings the **bare root endpoint** `/rest/v1/`, which rejects the anon key with HTTP 401:

```
"message":"Secret API key required","hint":"Only secret API keys can be used for this endpoint."
```

The Supabase REST root (`/rest/v1/`) requires the `service_role` (secret) key — it does NOT accept the anon key. This is a Supabase API design constraint, not a credentials problem. The anon key is valid and works for table queries (proven by the fact that `data-invariants.yml` — which hits `/rest/v1/practices?...` — passes every single week with the same anon key).

**Twist:** The fix already exists in the **local working tree**. `keep-supabase-alive.yml` in the working directory has been corrected to hit `/rest/v1/deals?select=deal_date&limit=1` instead of `/rest/v1/`. But **this fix was never committed and pushed** — `git status` shows it as an unstaged modification. GitHub has been running the original broken version continuously.

```
git diff HEAD -- .github/workflows/keep-supabase-alive.yml
-            "${SUPABASE_URL}/rest/v1/" \
+            "${SUPABASE_URL}/rest/v1/deals?select=deal_date&limit=1" \
```

### Root cause #2 (SECONDARY): sync_to_supabase.py has an uncommitted fix for IPv6/pooler URL

`git status` also shows `scrapers/sync_to_supabase.py` modified but not committed. The diff shows a fix for Supabase's IPv4/IPv6 pooler routing — adding `SUPABASE_POOLER_URL` as the preferred connection env var, fixing what the diff calls "the exact errors that silently broke the weekly sync on 2026-05-17 and 2026-05-24." The weekly-refresh runs on those dates show 11m59s and 11m35s runtimes (successful), so the sync step may have been timing out silently (with `continue-on-error: true`) rather than hard-failing. This fix is also not committed.

### Root cause #3 (CONTRIBUTING): DISCORD_WEBHOOK_URL secret is not set

The workflow tries to ping Discord on failure, but `DISCORD_WEBHOOK_URL` is empty, so failure notifications only go to GitHub's built-in email/notification system. No Discord alert fires. This is non-blocking but means the owner gets GitHub notification emails rather than a Discord ping.

### Why the 2 manual triggers succeeded (2026-04-25)

The `workflow_dispatch` triggers on 2026-04-25 at 17:50 and 18:04 UTC succeeded — but that run date is the SAME DAY and SAME HOUR the secrets were added (secrets show `2026-04-25T17:50:47Z`). Reviewing the successful run logs is not possible without fetching them, but likely one of two things: (a) a different version of the workflow file was committed at that moment that hit a working endpoint, or (b) the pre-secrets failure at 12:39 on that same day got `exit code 3` (not a 401) — suggesting the secrets were not yet set. After secrets were set at 17:50, manual dispatches succeeded because the curl to `/rest/v1/` happened to return 200 briefly, or the workflow was temporarily different. Since then, every scheduled run has been 401.

**The Supabase project itself is NOT paused** — the weekly refresh (which syncs data to Supabase via direct Postgres connection) has been running successfully every Sunday.

---

## Missing secrets / config

| Secret | Status | Notes |
|--------|--------|-------|
| SUPABASE_URL | SET (2026-04-25) | Correct |
| SUPABASE_ANON_KEY | SET (2026-04-25) | Correct — but the workflow was hitting an endpoint that rejects anon keys |
| SUPABASE_DATABASE_URL | SET (2026-04-25) | Used by weekly-refresh sync step |
| SUPABASE_POOLER_URL | SET (2026-04-25) | Now prioritized by the local (uncommitted) sync_to_supabase.py fix |
| ANTHROPIC_API_KEY | SET (2026-04-25) | Used by weekly-research, drift, audit |
| DISCORD_WEBHOOK_URL | NOT SET | Optional — only for Discord failure notifications. Not causing the 401 failures. |

**No missing secrets are causing the 401 failure.** The root cause is the wrong endpoint in the committed workflow file.

---

## Recommended fixes (do NOT implement yet — exact commands/edits)

### Fix 1 (CRITICAL — stops all the "Broken" emails): Commit and push the already-written endpoint fix

The local file already has the correct fix. Just commit and push it:

```bash
cd /Users/suleman/dental-pe-tracker
git add .github/workflows/keep-supabase-alive.yml
git commit -m "fix: keep-alive ping /rest/v1/deals not bare root (anon key 401)

The bare /rest/v1/ endpoint requires service_role key — anon key always 401.
Switch to /rest/v1/deals?select=deal_date&limit=1 which returns 200 with
the anon key and also counts as real DB activity (the actual keep-alive goal).

This has been failing on every scheduled run since the workflow was created.
Fix was already written locally but never committed/pushed."
git push origin main
```

After this push, the next scheduled run (every 3 days, `0 12 */3 * *`) will succeed. To verify immediately, manually trigger:
```bash
gh workflow run keep-supabase-alive.yml
```

### Fix 2 (RECOMMENDED): Commit the sync_to_supabase.py IPv4/pooler fix

```bash
cd /Users/suleman/dental-pe-tracker
git add scrapers/sync_to_supabase.py
git commit -m "fix: prefer SUPABASE_POOLER_URL (IPv4) over direct db.*.supabase.co (IPv6-only)

Direct Supabase host is now IPv6-only and unreliable from IPv4 runners.
The Supavisor pooler (port 5432, session mode) is the drop-in replacement.
Prevents silent sync failures on weekly-refresh runs."
git push origin main
```

Note: these can be combined into a single commit if preferred.

### Fix 3 (OPTIONAL): Add DISCORD_WEBHOOK_URL secret for failure notifications

If Discord channel alerting is desired (vs just GitHub email notifications):
1. Create a Discord webhook URL for the target channel
2. `gh secret set DISCORD_WEBHOOK_URL` and paste the webhook URL

This won't change workflow pass/fail status but routes failure alerts to Discord.

### Fix 4 (INFORMATIONAL): The reaudit.yml scheduled cron entries are now all in the past

`reaudit.yml` has 8 cron entries covering 2026-04-26 through 2026-05-09. All have passed. The workflow will never fire again on schedule (cron entries with past dates/months only match that specific month each year — it will re-fire in April/May 2027). This is expected behavior and not a problem.

---

## PROOF (raw command outputs relied on)

### gh auth status
```
github.com
  Logged in to github.com account suleman7-DMD (keyring)
  - Active account: true
  - Git operations protocol: https
  - Token: gho_****
  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'
```

### gh run list --limit 30 (keep-alive is the ONLY failing workflow)
```
completed  failure  Keep Supabase Alive  main  schedule  26584431458  9s   2026-05-28T15:27:56Z
completed  success  Data Invariants      main  schedule  26408832758  14s  2026-05-25T15:50:37Z
completed  success  Weekly Drift Check   main  schedule  26408639635  34s  2026-05-25T15:45:42Z
completed  failure  Keep Supabase Alive  main  schedule  26405762191  7s   2026-05-25T14:34:10Z
completed  success  Weekly Pipeline Refresh  main  schedule  26358077267  11m59s  2026-05-24T09:53:07Z
... (all non-keep-alive workflows: success)
```

### Most recent failed run log (run 26584431458, 2026-05-28)
```
Supabase REST responded with status: 401
##[error]Supabase /rest/v1/ returned 401 — project may be paused or credentials invalid.
{"message":"Secret API key required","hint":"Only secret API keys can be used for this endpoint."}
##[error]Process completed with exit code 1.
DISCORD_WEBHOOK_URL not set — skipping Discord notify (non-blocking)
```

### git diff HEAD -- .github/workflows/keep-supabase-alive.yml (fix exists, not committed)
```diff
-            "${SUPABASE_URL}/rest/v1/" \
+            "${SUPABASE_URL}/rest/v1/deals?select=deal_date&limit=1" \
```

### git status (two uncommitted fixes)
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
	modified:   .github/workflows/keep-supabase-alive.yml
	modified:   scrapers/sync_to_supabase.py
```

### gh secret list (secrets are present)
```
ANTHROPIC_API_KEY     2026-04-25T16:55:23Z
SUPABASE_ANON_KEY     2026-04-25T17:50:47Z
SUPABASE_DATABASE_URL 2026-04-25T17:57:27Z
SUPABASE_POOLER_URL   2026-04-25T17:57:27Z
SUPABASE_URL          2026-04-25T17:50:45Z
```

### Keep Supabase Alive — full run history (100% failure rate on scheduled runs)
```
failure  26584431458  2026-05-28
failure  26405762191  2026-05-25
failure  26292998854  2026-05-22
failure  26104249231  2026-05-19
failure  25962534550  2026-05-16
failure  25804342688  2026-05-13
failure  25629277747  2026-05-10
failure  25498783074  2026-05-07
failure  25321472913  2026-05-04
failure  25215038360  2026-05-01
failure  25055697736  2026-04-28
success  24937205973  2026-04-25 (workflow_dispatch, same hour secrets added)
success  24936932231  2026-04-25 (workflow_dispatch, same hour secrets added)
failure  24931115878  2026-04-25 (scheduled, before secrets added — exit code 3)
```
