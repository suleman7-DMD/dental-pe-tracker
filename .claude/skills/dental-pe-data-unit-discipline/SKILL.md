---
name: dental-pe-data-unit-discipline
description: MANDATORY whenever stating, comparing, or displaying ANY count or percentage from this repo — practices, NPIs, locations, GP universe, corporate %, consolidation %, census coverage, DSO share, or the ADA 14.6% anchor. Load before writing headlines, KPI labels, report numbers, or commit messages containing counts. Prevents the NPI-row-vs-location conflation and illegal denominator/label combinations.
---

# Data Unit Discipline (counts, denominators, labels)

This repo has FOUR different units that all get casually called "practices". Most historical
data bugs here were unit confusion, not bad data. Never state a number without its unit and
denominator.

## 1. The four units

| Unit | What it is | Where | Scale (2026-07-04) |
|---|---|---|---|
| **NPI row** | One federal NPI record (NPI-1 provider OR NPI-2 org). ~2.4× the clinic count | `practices` table | 402k total; 13,818 in watched ZIPs |
| **Location** | One physical clinic (deduped by normalized address+ZIP) | `practice_locations` | 5,657 all-class watched; 4,801 GP |
| **GP universe** | The census denominator: GP locations only, excl. specialist/non_clinical/da_unverified/org_only_npi | `SUM(zip_scores.total_gp_locations)` | 4,801 total = **4,439 IL** + 362 MA (parked) |
| **Census row** | One reviewed GP location with an earned `ownership_tier` | `practice_locations.ownership_tier` | 3,180 (71.64% of IL universe) |

Rules:
- **Never say "practices" for NPI counts.** Say "NPI rows". Headline KPIs use location-deduped
  counts; NPI counts belong in subtitles.
- The census denominator is ALWAYS the IL GP universe (4,439), never 4,801 (includes parked MA),
  never 5,657 (includes specialists), never 13,818 (NPI rows).
- MA/Boston is PARKED: filter from view, never census, never delete.

## 2. Numbers cheat-sheet (verified 2026-07-04 — recheck, don't trust)

```bash
sqlite3 data/dental_pe_tracker.db "
SELECT SUM(total_gp_locations) FROM zip_scores;                              -- 4801 (IL+MA)
SELECT SUM(total_gp_locations) FROM zip_scores z
  JOIN watched_zips w ON z.zip_code=w.zip_code WHERE w.state='IL';           -- 4439 (census universe)
SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL;    -- 3180 (census reviewed)
SELECT COUNT(*) FROM practice_locations
  WHERE entity_classification IN ('dso_regional','dso_national');            -- 268 (detector floor, locations)
SELECT COUNT(*) FROM practices
  WHERE entity_classification IN ('dso_regional','dso_national')
  AND zip IN (SELECT zip_code FROM watched_zips);                            -- 1152 (detector floor, NPIs)
"
```

**Scoping trap:** the NPI floor is 1,152 only when scoped to watched ZIPs (Supabase `practices`
holds ONLY the 13,818 watched rows). The unscoped SQLite count is 1,153 — one corporate NPI
sits outside the watched set. If you see 1,153 vs 1,152, that is the explanation, not drift.

## 3. Two ownership numbers that must never be conflated

1. **Detector floor** (`entity_classification`): 268/4,801 = **5.58%** "confirmed corporate".
   A FLOOR from automated detection + verified promotions. It is the starting point the census
   corrects, NOT the answer.
2. **Census tiers** (`ownership_tier`): hand-verified per-location conclusions with coverage
   71.64%. Census percentages are computed FROM reviewed rows and must always be shown WITH
   coverage.

Floor ≠ true consolidation rate. Census-reviewed rates ≠ whole-universe rates. Present partial-
census reviewed rates and whole-universe confirmed floors separately, labeled.

## 4. The five headline buckets + labeling law (user-ratified)

The ONLY legal presentation of census ownership (code gate:
`dental-pe-nextjs/src/lib/census/ownership-truth.ts` — pages import it, never reimplement):

| Bucket | Tiers |
|---|---|
| True Solo Owner-Operated | T1 |
| Dentist-Owned, Not Solo | T2+T3 |
| DSO / PE / Corporate Controlled | T4+T5 |
| Institutional | T6 |
| Unresolved | undetermined + holds + unreviewed — ALWAYS visible, never rolled in |

**Labeling law:**
- The broad top-line is **"Not Solo Owner-Operated %"** — NEVER "DSO-affiliated %". T2/T3 are
  dentist-owned; calling them DSO is defamatory to the data.
- Only the T4+T5 bucket may sit next to the ADA 14.6% anchor — and ADA counts DENTISTS while
  we count LOCATIONS. State the unit caveat; compare direction, not magnitude.
- NEVER validate the Not-Solo % against ADA 14.6%. They measure different things; agreement or
  disagreement is meaningless.
- T6 institutional is never "consolidated", never DSO, never PE.

## 5. Presentation rules

- Every displayed number states its source class (census_reviewed / held / undetermined /
  unreviewed / legacy_detector / pe_deal_context — see `ownership-truth.ts`).
- No fake precision: a 71.64%-coverage census yields ranges and floors, not point estimates of
  the universe.
- Date-stamp volatile numbers and attach a one-line recheck command (as done here).
- Deals count is VOLATILE — a 2026-07-04 deal-quality cleanup cut it 2,827 → 527 (gdn 357 /
  pesp 153 / beckers 14 / beckers+gdn 3; backup `pre_deal_quality_cleanup_20260703.db`).
  Always query fresh. Deals are DEAL-ANNOUNCEMENT context — never a location-level ownership
  fact.

## 6. Common hasty-model failures

- Quoting the 13,818 NPI count as "practices in Chicagoland" (it's ~2.9× the GP clinic count).
- Computing census % with 4,801 as denominator (includes parked MA — the universe is 4,439).
- Labeling Not-Solo % as "DSO share" — violates the ratified labeling law.
- "Fixing" 1,153 vs 1,152 as if it were sync drift (it's watched-ZIP scoping, §2).
- Copying a count from CLAUDE.md or an older doc without rerunning the query — several docs
  carry historical numbers superseded by dated notes.

## 7. Minimum proof before continuing

Any statement of a count/percentage in a deliverable requires: (1) the query you ran, (2) its
output, (3) unit + denominator + date in the sentence itself. If you inherited the number from
a doc, rerun the recheck command first.
