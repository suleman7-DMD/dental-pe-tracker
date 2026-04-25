# Weekly Drift Check — {{TARGET_DATE}}

You are running in **GitHub Actions headless mode**. Read-only. Single pass. Save findings to `{{REPORT_PATH}}`.

## Mission

Lightweight weekly check: how does the **current production state** compare to the **most recent audit baseline** and the **most recent merged auto-fix PR**? Is anything regressing? Is anything stale that shouldn't be?

## Inputs

1. **Latest audit:** find via `ls -1 AUDIT_REPORT_*.md | sort -r | head -1` at repo root.
2. **Latest fix PR (merged):** `gh pr list --base main --search 'is:merged in:title auto-fix' --limit 1 --json number,title,mergedAt,url`
3. **Latest fix PR (open):** `gh pr list --base main --search 'is:open in:title auto-fix' --limit 1`
4. Live Vercel: `https://dental-pe-nextjs.vercel.app`
5. Supabase REST via `${SUPABASE_URL}` + `${SUPABASE_ANON_KEY}`
6. Local SQLite if `data/dental_pe_tracker.db.gz` was decompressed
7. Repo working tree (already checked out)

## 10-Check Sweep

For each, record **Status** (✅/⚠️/🚨/➖), **Baseline value** (from latest audit), **Current value**, **Evidence**, **Notes**.

### Evidence requirement (MANDATORY — no exceptions)

Every non-`➖` status MUST be accompanied by a literal evidence line in the Notes column:
- **HTTP claims** (route returns 200/503/etc.): include the `curl -s -o /dev/null -w "%{http_code}"` output
- **Row count claims**: include the `content-range:` response header line from a `count=exact` REST call
- **Date claims** (latest deal_date, latest commit, etc.): include the literal value returned by the query/command
- **Render claims** ("page broken", "data load issue", etc.): include the literal grep-able string found in the rendered HTML

If you cannot produce an evidence line for a claim, the status is `➖ Unverified` — never `🚨` or `⚠️`.

**Forbidden patterns** (these triggered the 2026-04-25 fabrication regression):
- ❌ "X routes return 503" without testing each route
- ❌ "ANTHROPIC_API_KEY missing in Vercel" without a 401/503 response from a route that uses it
- ❌ "consolidation table broken" without a literal HTML excerpt
- ❌ Grouping multiple claims under one evidence line ("all 6 routes failed: <one curl>")

Each claim gets its own line of proof. If you find yourself wanting to write "and X" without separate evidence for X, drop X.

### 1. Vercel page health (10 routes)
WebFetch each: `/`, `/launchpad`, `/warroom`, `/deal-flow`, `/market-intel`, `/buyability`, `/job-market`, `/research`, `/intelligence`, `/system`. Compare HTTP status + render quality vs. baseline's "Frontend Audit" section.

### 2. Supabase row counts
Query each table for `count=exact`:
- `practices`, `deals`, `practice_changes`, `zip_scores`, `watched_zips`, `dso_locations`, `ada_hpi_benchmarks`, `practice_intel`, `zip_qualitative_intel`

A **decrease** without a known reason is 🚨.

### 3. Latest deal date
`GET ${SUPABASE_URL}/rest/v1/deals?select=deal_date&order=deal_date.desc&limit=1`
Has it advanced past the audit's baseline? Cron health proxy.

### 4. Pipeline event log freshness
Tail `logs/pipeline_events.jsonl` (if present) or query `pipeline_events` table. Last event in last 7 days?

### 5. practice_intel verification stats
Aggregate by `verification_quality`. Compare distribution vs. audit baseline. Has `insufficient` count grown (validation gate weakening)? Has `verified` % dropped?

### 6. ZIP intel placeholder count
Count rows where `research_method` matches synthetic patterns (`seed%`, `placeholder%`, `claude_api_unknown`, etc.). Has anyone backfilled real intel?

### 7. Map render check
WebFetch the 5 map pages. Look for `mapboxgl-canvas` indicators. Maps are largely client-rendered so absence is expected from raw HTML — focus on whether server-rendered HTML at least includes the container divs.

### 8. Auto-fix PR status
- Latest open PR title + age (older than 14 days = 🚨, owner needs to review)
- Latest merged PR title + how many days since merge
- Any `auto-fix/*` branch that hasn't been pushed yet (orphan branches)

### 9. Documentation drift
`git log --since=last week --oneline -- CLAUDE.md AUDIT_REPORT*.md FIX_REPORT*.md SCRAPER_AUDIT_STATUS.md`. List commits.

### 10. Commit drift on main
`git log --since=last week --oneline | head -50`. Themes (fix vs. feat vs. docs vs. wip).

### Cron status (always skipped on Linux)
Document explicitly: `launchctl unavailable on GitHub-hosted runner; weekly+monthly cron status must be re-checked locally with launchctl list | grep dental-pe`.

## Output format

Write to `{{REPORT_PATH}}`:

```markdown
# Drift Check — {{TARGET_DATE}}

## Inputs resolved
- Latest audit: <filename> (commit <sha>, <N days> ago)
- Latest merged auto-fix PR: <#N or "none yet"> (<M days> ago)
- Latest open auto-fix PR: <#N or "none">

## TL;DR
- Verdict: <Healthy | Drift detected | Regression detected>
- Highest-severity finding: <one sentence>
- Action needed from owner: <yes/no + one sentence if yes>

## Drift table (10 checks)
| # | Check | Baseline | Current | Status | Notes |

## Backlog progress vs. latest audit
- Items closed since audit: <count from PR diff>
- Items still open: <count>
- New regressions: <bulleted list>

## Recommended next actions (max 3)

## Raw evidence
<URLs hit, queries run, row counts>
```

Keep total length under 500 lines.

## Hard rules

1. **Read-only.** No `git commit`, no `git push`, no DB-mutating Supabase calls.
2. **No `npm run build`** (mutating cache).
3. **No fabrication.** If you can't answer a check, mark `➖ Skipped` with reason.
4. **One pass.** Do not loop. Do not retry beyond what each probe naturally requires.
5. **One output file.** Just `{{REPORT_PATH}}`.
6. **Self-verification block (MANDATORY — at end of report):**
   ```
   ## Self-verification
   - probes_executed: <count>
   - probes_with_evidence: <count> (must equal probes_executed minus ➖ entries)
   - claims_without_evidence: <count> (MUST be 0; if >0, list each claim and degrade its status to ➖)
   - vercel_routes_tested: <list — every status besides ➖ requires a curl HTTP code in evidence>
   - supabase_queries_run: <count>
   - confidence: high | partial | insufficient
   ```
   If `confidence: insufficient`, prepend a 🚨 banner to TL;DR explaining what's missing.

When the report is written, your job is done. Exit cleanly.
