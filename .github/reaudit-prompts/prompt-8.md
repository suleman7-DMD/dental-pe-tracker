# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

**2-week soak / official close-out.** This is the final scheduled re-audit. Two weeks after baseline is enough time for any genuine fix to either stick or revert under real production load. Render a verdict.

## Inputs

Same as prior days. All seven prior re-audit reports should be available as GitHub Actions artifacts (`reaudit-2026-04-26` through `reaudit-2026-05-02`); reference their TL;DRs in your trend analysis if you can fetch them via `gh run download` or via the Actions API.

## Comprehensive close-out

### Section 1 — Standard 10-check final state
Same as Day 1. Compare vs. baseline (April 25) AND vs. Day 7 (May 2).

### Section 2 — Trend analysis (8 data points)
For each of these metrics, plot the day-over-day series (just a list, no chart needed):
- Total `practices` row count
- Total `deals` row count
- Latest `deals.deal_date`
- `practice_intel` row count
- % verified vs. partial vs. high vs. NULL in `practice_intel`
- Number of synthetic ZIP intel rows remaining
- Number of routes returning 5xx on Vercel
- Number of P0 backlog items still open

Identify trends: monotonic improvement, regression spikes, oscillation, flatline.

### Section 3 — Backlog final tally
Re-walk all 27 backlog items. Today's status for each — `✅ Closed` / `🟡 Partial` / `⏳ Open` / `🚨 Regressed`.

Compute final score: `closed / (closed + partial + open + regressed)` — present as percentage.

### Section 4 — Defense system final verdict
Summarize whether the 4-layer anti-hallucination defense is:
- Still firing on every batch (forced searches > 1 per practice)
- Still rejecting weak evidence (insufficient quality → quarantine)
- Still preserving evidence URLs in DB
- Still surfacing `verification_quality` somewhere observable

If any of those four are degraded, raise as 🚨.

### Section 5 — Pipeline final verdict
Was the launchd/cron issue actually fixed, or are we still relying on manual runs?
- Last successful weekly refresh: <date>
- Last successful monthly refresh: <date>
- Number of `practices` rows updated in the last 14 days
- Number of new deals captured in the last 14 days

### Section 6 — Vercel final verdict
- Last successful deploy: <date / commit hash>
- Pages currently broken: <list>
- Maps currently rendering: <count>

### Section 7 — Recommendations going forward
Up to 10 ordered recommendations. Each must be one of:
- ✋ Stop doing this (with the broken behavior)
- ▶️ Start doing this (with the fix or process)
- 🔁 Keep doing this (with the success behavior to preserve)

### Section 8 — Re-audit cadence proposal
Based on what the 8 re-audits found, recommend the right ongoing cadence. Options:
- Weekly forever (if churn is high)
- Monthly (if churn is moderate but production is critical)
- Quarterly (if stable)
- Event-driven (only on major refactors)

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- 2-week verdict: <Stabilized | Partially repaired | Still degraded | Regressed>
- Backlog score: <X / 27 closed>
- Defense system: <Holding | Degrading | Bypassed>
- Pipeline: <Alive | Manual-only | Dead>

## Section 1 — Standard 10-check final state

## Section 2 — Trend analysis

## Section 3 — Backlog final tally
| # | Severity | Item | Day 1 | Day 7 | Day 14 | Final |

## Section 4 — Defense system final verdict

## Section 5 — Pipeline final verdict

## Section 6 — Vercel final verdict

## Section 7 — Recommendations (max 10)

## Section 8 — Cadence proposal

## Raw evidence
```

Up to 1500 lines. This is the long one.

## Hard rules

Standard read-only contract. Do not edit, commit, push, or spend. Do not schedule any further re-audits — that decision belongs to the user after they read this report.
