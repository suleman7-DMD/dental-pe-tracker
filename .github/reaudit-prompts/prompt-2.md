# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

You are running in **GitHub Actions headless mode**. Read-only sweep. No clarifying questions. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

48 hours after the baseline audit. Today's emphasis: **diff against yesterday's re-audit** to detect overnight regressions, and verify that any short-cycle fixes from `FIX_REPORT_2026-04-25.md` have actually shipped to production.

## Inputs

- `AUDIT_REPORT_2026-04-25.md` — baseline (origin truth)
- `FIX_REPORT_2026-04-25.md` — intended-state contract (may be missing if fix session hasn't run yet)
- Yesterday's run: download via `gh run list --workflow=reaudit.yml --limit=2 --json databaseId,createdAt` if you have `gh` available; otherwise skip the diff and treat this as a standalone repeat of the Day-1 sweep.
- Live Vercel: `https://dental-pe-nextjs.vercel.app`
- Supabase REST via `${SUPABASE_URL}` + `${SUPABASE_ANON_KEY}`
- Local DB at `data/dental_pe_tracker.db` (if present)

## 10-Check Sweep (same as Day 1, with diff-emphasis)

For each, record **Status / Yesterday / Today / Δ / Notes**.

1. **Live Vercel page health** — 10 routes. Flag any route that flipped Healthy→Broken or vice versa.
2. **Supabase row counts** — 9 tables. Flag any negative delta. Positive delta on `practices` is expected if NPPES ran; flag if `deals` decreased (data loss).
3. **Latest deal date** — Has it advanced past 2026-03-02? Note: weekly cron was dead at baseline.
4. **Pipeline event log** — Did any new scrape run between yesterday and today?
5. **practice_intel verification stats** — counts by quality. Flag if `insufficient` count rose (validation gate weakened).
6. **ZIP intel synthetic count** — Has anyone backfilled real intel? Baseline was 258 synthetic.
7. **Map render** — Warroom living-map specifically. Did the bundle fix ship?
8. **Launchpad AI routes** — 503 status of the 6 routes. Are they all 200 yet?
9. **Documentation drift** — `git log --since=yesterday`. Note any new docs.
10. **Commit drift** — All commits in the last 24h on main. Theme: `fix:` / `feat:` / `chore:`.

## Specific signals to watch (Day 2)

- **Vercel deploy log:** if accessible via the Vercel API key, check for failed deploys since 2026-04-25. Otherwise infer from the homepage commit hash in HTML source.
- **Anti-hallucination defense health:** sample 5 random rows from `practice_intel` where `verification_quality = 'high'`. The audit flagged this as enum drift (model returned "high" instead of "verified|partial|insufficient"). Has the prompt been tightened?
- **Cron status:** still `➖ Skipped` on Linux runner. Note that the user must verify locally with `launchctl list | grep dental-pe`.

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Direction: <improving | stable | degrading>
- Items closed since baseline: <N of 27>
- New regressions: <count + one-line each>

## 24h diff table
| # | Check | Yesterday | Today | Δ | Status |

## Backlog items resolved
<reference items from "Prioritized Debug Backlog" in baseline>

## New findings (not in baseline, not in yesterday)
<list>

## Recommended next actions (max 5)

## Raw evidence
```

Max 500 lines. Read-only. Do not edit code. Do not commit. Done = file at `{{REPORT_PATH}}`.

## Hard rules

Same as Day 1. Read-only. No fabrication. No loops. Stop at one pass.
