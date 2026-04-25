# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

Day 5 — half-week mark. Today's emphasis: **defense coverage breadth**. The baseline audit verified anti-hallucination on a 200-practice batch. By Day 5, more rows should have run through the gate. Verify the gate is still rejecting bad rows, not just rubber-stamping everything.

## Inputs

Same as prior days. Reference `AUDIT_REPORT_2026-04-25.md` Section "Hallucination Audit" + "Anti-Hallucination Defense (April 25, 2026)" in `CLAUDE.md`.

## 10-Check Sweep + Defense Audit

### Standard 10 (carry over)
Same as Day 1.

### Defense audit probes

**D1 — Validation gate active-rejection rate**
Compare:
- Rows in `practice_intel` (gate-survivors)
- Rows that should have been processed (look at `weekly_research.py` budget cap × $0.075/practice = expected count, derive from `data/research_costs.json` if checked in)

Baseline expectation: **13% rejection rate** (26 of 200 quarantined). If today's rate is ~0%, the gate may have been bypassed or the model is now over-confidently passing weak evidence.

**D2 — Verification quality histogram**
```
GET ${SUPABASE_URL}/rest/v1/practice_intel?select=verification_quality
```
Count by category. Baseline:
- verified: 26%
- partial: 57.5% (most common)
- high: 5%
- NULL: 11.5% (pre-gate rows)

Drift signal: if `verified` % drops < 15% or `partial` % grows > 75%, evidence quality is degrading.

**D3 — Verification searches distribution**
```
GET ${SUPABASE_URL}/rest/v1/practice_intel?select=verification_searches
```
Compute mean + p50 + p95. Baseline: avg 4.27 searches/practice, range 1-7. If mean drops below 3.0, the `force_search` `tool_choice` may have stopped firing.

**D4 — Source URL diversity sample**
Pick 10 random practice_intel rows. Inspect `verification_urls` (or load a single row's full record and look at `raw_json` for `_source_url` fields per section). Count distinct domains. Baseline: typical row has 3-5 distinct URLs (practice website, Google, HealthGrades, ZocDoc, news).

If many rows have only `"no_results_found"` everywhere, fabrication risk has gone up because researcher has nothing to ground in.

**D5 — Cost vs. row count check**
If `data/research_costs.json` is committed/visible, sum `cost_usd` for entries since 2026-04-25. Divide by count of new `practice_intel` rows since same date. Baseline: $0.075/practice. Flag if it dropped below $0.04 (suggests forced search stopped firing) or rose above $0.20 (suggests Sonnet escalations are running unbudgeted).

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR
- Defense health: <Holding | Degrading | Bypassed>
- Rejection rate: <X%> (baseline 13%)
- Avg searches/practice: <N> (baseline 4.27)

## Standard 10-check drift table

## Defense audit (D1-D5)

## Backlog progress

## Recommended next actions (max 5)

## Raw evidence
```

Max 700 lines. Read-only.

## Hard rules

Standard. No edits, no commits, no spend. If `practice_intel` has fewer than 10 new rows since baseline (i.e., no fresh batch ran), shrink D1-D4 to "insufficient sample, retesting later" and move on.
