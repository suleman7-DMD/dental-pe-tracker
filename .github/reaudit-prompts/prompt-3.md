# Re-Audit — {{MILESTONE}} ({{TARGET_DATE}})

GitHub Actions headless mode. Read-only. Single pass. Save to `{{REPORT_PATH}}`.

## Mission

Day 3. Add **deeper validation** beyond the 10-check sweep — specifically targeting categories the baseline audit called out as "untested in production":
- The 4-layer anti-hallucination defense actually rejecting fabrications in fresh runs (not just the historical 200-practice batch)
- Sync resilience after `_sync_watched_zips_only` got the TRUNCATE CASCADE fix
- Parser improvements to GDN/PESP catching new deal patterns

## Inputs

Same as Day 1/2. Reference `AUDIT_REPORT_2026-04-25.md` Section "Hallucination Audit" and "Pipeline Audit — April 23, 2026".

## 10-Check Sweep + Deep-Dive Probes

### Standard 10 (carry over)
Run the same 10 checks as Day 1. Record drift table.

### Deep probe A — Hallucination defense end-to-end test

Without spending budget: query `practice_intel` for the **5 most recently stored rows**:
```
GET ${SUPABASE_URL}/rest/v1/practice_intel?select=npi,research_date,verification_quality,verification_searches,verification_urls&order=research_date.desc&limit=5
```
For each row, validate:
- `verification_searches >= 1` (forced search proof)
- `verification_quality IN ('verified','partial','high')` — note `high` is enum drift but currently passing the gate
- `verification_urls` is non-null and contains at least one URL OR the literal `"no_results_found"`

Flag any row that has: searches=0, quality='insufficient' (shouldn't be stored), or NULL urls.

### Deep probe B — Sync resilience artifact check

Look for the failure mode the audit described: `practice_signals` FK violation referencing NPI `1316509367`. Query:
```
GET ${SUPABASE_URL}/rest/v1/practice_signals?npi=eq.1316509367&select=npi,signal_type,created_at
```
If still present, flag as 🚨 (open `practice_signals` orphan known issue).
Also tail the sync log if any recent run is captured in `logs/`.

### Deep probe C — GDN/PESP parser pattern stability

Query last 50 deals to see if any have suspicious truncation in `platform_company` (e.g., names ending in " Dental" with no further word — the audit's "Partners" ambiguity bug):
```
GET ${SUPABASE_URL}/rest/v1/deals?select=platform_company,target_name,deal_date,deal_source&order=deal_date.desc&limit=50
```
Look for known-broken patterns:
- `platform_company` is exactly `<Word> Dental` (1 word + Dental, suggesting truncation past "Partners")
- `target_name` contains "Onboarded", "Strengthens", "Deepens" (audit added these verbs to `_DEAL_VERB_SET`; if they appear in target_name, the verb cleanup didn't ship)

### Deep probe D — Apostrophe normalization regression check

`SELECT DISTINCT platform_company FROM deals WHERE platform_company LIKE '%''%' OR platform_company LIKE '%' || chr(8217) || '%'`
Use Supabase REST equivalent. Audit flagged duplicates with U+2019 vs U+0027 not deduped. Count how many distinct names exist with apostrophe variants.

## Output

```markdown
# Re-Audit Report — {{MILESTONE}} ({{TARGET_DATE}})

## TL;DR

## Standard 10-check drift table

## Deep probes
### A — Hallucination defense
### B — Sync FK orphans
### C — Parser pattern stability
### D — Apostrophe normalization

## Backlog progress (vs. baseline 27 items)

## Recommended next actions (max 5)

## Raw evidence
```

Max 700 lines. Read-only. Done = `{{REPORT_PATH}}` exists.

## Hard rules

No code edits. No commits. No batch-API spend. Do not call `practice_deep_dive.py` or `qualitative_scout.py` — those cost real $. If the Supabase REST API rate-limits you, back off and skip the affected check with `➖ Skipped`.
