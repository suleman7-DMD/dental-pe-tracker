# PROOF PACKAGE — Census Consolidation Gate (user sign-off request)
**Date:** 2026-07-02 · **Author:** Fable (PM of record) · **Status:** ✅ DECIDED + EXECUTED
(2026-07-02, same day). The user delegated all decisions ("make the best answers to the
decisions… then proceed"); the PM's rulings are in `DECISIONS_PM_20260702.md` (R1–R5, R4
networks, consolidation YES, repo hygiene YES). **The final written shape is 343 classified +
6 holds** (this package's 340/9 was pre-R1: the 3 Affordable policy-holds were reinstated as T5,
and the enforced R5 closure cross-check adjudicated Geneva Dental + MetroSmiles ACTIVE).
Executed: `consolidate_census.py --session fable_pm_consolidation_20260702 --allow-db-write` →
343 locations + 1,037 NPIs; LEDGER 344 lines; PROGRESS 343/4,439 = 7.73%; detector floor
untouched (268/1,152/4,801). Supabase synced + read-back verified both legs
(`_sync_floor_tables_only` + new `_sync_census_columns_practices`): live = SQLite exactly.
Historical content below is preserved as the at-decision evidence base.

---
**Original package as presented (pre-decision):**
Nothing in this package has touched the DB: `ownership_tier` notnull is still 0/0, LEDGER 1 line,
PROGRESS 0 reviewed / 4,439 undetermined. Everything below is file-evidence + validated candidates.

---

## 1. What is ready

**`data/dso_research/_census_candidate_consolidated_20260702.json` — 340 candidate rows —
passes the hardened fail-closed validator with 0 errors:**

```
python3 scrapers/consolidate_census.py \
  data/dso_research/_census_candidate_consolidated_20260702.json \
  --session fable_pm_normalization_20260702 --validate-only
# → Validation OK (340 rows, 0 errors)
```

Holds companion: `_census_holds_20260702.json` (9 rows). Generator (deterministic, re-runnable):
`data/dso_research/_normalize_census_candidates_20260702.py`.

## 2. Final arithmetic (one table, supersedes 346/341/337 estimates)

| Source | In | To candidates | To holds | Notes |
|---|---:|---:|---:|---|
| Ready-310 (2026-06-21) | 310 | **303** | 7 | URL hygiene repaired on all rows; weak-68 verdicts applied: 4 → hold (evidence conflicts), 3 Affordable → policy hold (R1), 4 retiered T5→T3 (stay) |
| Wave-4 partition-1 merge-eligible | 19 | **19** | 0 | 17 T3 + 2 T5, schema-converted |
| Lane-2 partition | 15 | **15** | 0 | 1 new T5 (Dentologie) + 12 T5 corroborations of already-corporate + 2 T1 |
| Lane-3 51–100 merge-eligible | 5 | **3** | 2 | Archer (rank 83) held per QA — ownership unconfirmed; Advanced Family Dental (rank 100) held — **DA_ synthetic NPI**, see §4 |
| **Total** | 349 | **340** | 9 | |

**Tier tally of the 340:** branded_dso 99 · stealth_dso 21 · dentist_multi 171 · single_loc_group 7 ·
true_independent 32 · institutional 10. `pe_backed=true`: 75 rows.

**Coverage vs floor-lift (never conflate):**

| Effect class | Rows |
|---|---:|
| T4/T5 **net-new** DSO/PE (location not currently corporate in detector) | **42** |
| T4/T5 corroborates already-corporate location (coverage, zero floor lift) | 78 |
| T3 dentist-owned multi (consolidated coverage, **not** DSO/PE headline) | 171 |
| T2 single-location group | 7 |
| T1 true independent (coverage) | 32 |
| T6 institutional (coverage, not consolidated) | 10 |

Of the 42 net-new T4/T5, **8 are R4-protected-network rows** (7 LABINOV + 1 NITTINGER) that need
your explicit sign-off (§5); 34 are unencumbered.

## 3. What consolidation would do (when you authorize it)

`--allow-db-write` on the 340 writes `ownership_tier` + 5 companion columns to 340
`practice_locations` rows and mirrors to **1,033 federal NPIs** in `practices` (writer fixed
2026-07-02 to include the provider_npis roster — was primary/org only, which would have left ~693
provider NPIs blank; DA_ synthetics skipped). Ledger +340 lines, PROGRESS → 340/4,439 = 7.66%
coverage. It does **not** touch `entity_classification`, the 5.43–5.61% detector floor, any
denominator, or any public percentage. SQLite only; Supabase sync is a separate later step.

## 4. PM catch this session: the validator earned its keep

Lane-3's rank-100 "Advanced Family Dental (Shorewood) → Great Lakes Dental Partners/Shore Capital,
+1 T5 floor lift" was accepted by the gate agent AND its QA pass. The fail-closed validator then
refused it: the candidate row `6c31d482e9a63431` carries a **DA_ synthetic NPI** (Data-Axle
remnant, no phone). The real practice — `0d376204167d44a6`, ADVANCED FAMILY DENTAL OF SHOREWOOD,
P.C., federal NPI 1932386810, same house number/ZIP — is **already dso_regional**. The GLDP/Shore
evidence is credible but corroborates an already-counted corporate practice. **Lane-3 accepted
floor impact is +1 T5 (Grove Dental → NADG/Abry+Jacobs), not +2.** The synthetic row goes to the
scope-correction queue (da_unverified reclass + possible duplicate_location merge).

## 5. Decisions needed from you (yes/no each)

**R1–R5** — see `GP_SCOPE_POLICY_DRAFT_20260702.md` (ADI=T5 → reinstates 3 held Affordable rows;
ClearChoice scope ejection; T6 semantics; protected-network procedure; closure-hold rule).

**R4 named networks** (all were "released" by the former gate-owner seat itself — self-release is
not user sign-off, so they come to you; rows are IN the 340, flagged `r4_flag`, and can be pulled
before write if you say so):
- **NITTINGER_RACHEL — 11 rows T5.** DOL EBSA MEWA filing evidence is strong. 10 of 11 corroborate
  already-corporate locations; only 1 is net-new. **PM recommends ACCEPT.**
- **LABINOV_BORIS — 7 rows T5 (Destiny/ProSmile), all 7 net-new floor lift.** Brand is a known
  PE-backed DSO from prior verified work. **PM recommends ACCEPT.**
- **SHAFI_SOHAIL — 18 rows T3** (Two Rivers Dental, dentist-owned multi). T3 never touches the
  DSO/PE headline. **PM recommends ACCEPT as T3.**

**Consolidation authorization** — after R-decisions: authorize
`--allow-db-write --session <name>` on the 340 (minus any rows you pull)?

## 6. Adjacent queues (review-only, NO mutations proposed)

- **Closure queue** (`closure_candidates_review_20260702.json`): 61 mark_likely_closed are
  candidates for human adjudication only — at least one (Metropolitan Dental Care) shows
  conflicting active signals. Known gap: coverage bridged primary-NPI only (2,069 vs 2,330 if
  bridging org+provider NPIs) — improvement queued for the next closure pass.
- **Duplicate queue** (`duplicate_candidates_review_20260702.json`): mutation candidates are ONLY
  the 125 explicit `mark_duplicate_location` row actions — never whole combos.
- **Scope-correction queue**: 19 DA_/DIR_ synthetic zero-contact rows from the closure pass + the
  Shorewood DA_ row (§4) — da_unverified-style reclass, evidence-documented, separate user gate.

## 7. Repo hygiene (recommendation)

Census scripts/docs/candidate files are untracked in the root repo, and the frontend honesty edits
(build ✓, F27 vitest ✓) live in the **nested** `dental-pe-nextjs` repo — production stays old
until that repo is committed and pushed (root commits do not deploy it). PM recommends you
authorize: (a) root commit of census infrastructure + evidence files, (b) nested-repo commit/push
of the honesty fixes. No commits made — per standing rule, awaiting your word.
