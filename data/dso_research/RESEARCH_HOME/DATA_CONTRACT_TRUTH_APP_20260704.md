# DATA CONTRACT — Truth-Safe App (Frontend ↔ Census)
**Author:** Fable (PM) · 2026-07-04 · Deliverable 2 of SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md
**The code IS the contract:** `dental-pe-nextjs/src/lib/census/ownership-truth.ts` (locked by
`src/__tests__/ownership-truth.test.ts`, 11 assertions). This doc explains the module; if they
ever disagree, the module + its tests win, and the disagreement is itself a regression to fix.

**Prime directive (charter §0):** the app must make it *structurally impossible* to present
detector/legacy/partial data as final census truth. This contract is the mechanism: every page
imports the module; no page reimplements tier→bucket mapping, source classes, or labels.

---

## 1. Source-of-truth hierarchy (highest wins)

1. **Census truth** — `ownership_tier` + evidence columns, hand-reviewed. The ONLY ownership truth layer.
2. **Holds / triage** — reviewed-but-blocked or researched-but-thin. Visible as open work, never a conclusion.
3. **Legacy detector** — `entity_classification` (13-value automated signal). Context ONLY, always
   labeled "Legacy detector estimate (context)". Never primary in any census-era surface.
4. **PE deal context** — deal announcements (`pe_deals` etc.). Market context, not a location-level fact.

Frontend reads **Supabase only** (never local SQLite). Local SQLite is upstream of Supabase via
the two sync legs (charter §1b) — until a sync runs, Supabase lags local and the app must say so.

## 2. Tables and fields the frontend may interpret

### `practice_locations` (unit: physical location) — census columns
| Column | Type / values | Meaning |
|---|---|---|
| `ownership_tier` | `true_independent` (T1) / `single_loc_group` (T2) / `dentist_multi` (T3) / `stealth_dso` (T4) / `branded_dso` (T5) / `institutional` (T6) / NULL | THE truth layer. NULL = no census conclusion. |
| `pe_backed` | bool | PE sponsorship documented for the controlling entity. |
| `ownership_evidence_basis` | text | Human-readable evidence summary. Only meaningful when a tier is set. |
| `ownership_evidence_urls` | JSON list of http(s) URLs | Citations. Only meaningful when a tier is set. |
| `ownership_confidence` | `high` / `medium` / `low` | Reviewer confidence. Only meaningful when a tier is set. |
| `network_id` | text | Groups sibling locations of one operator/network. |
| `entity_classification` | 13 detector values | LEGACY detector output. Context only (rule §2.2). |

`practices` (unit: NPI row, ≠ locations) mirrors the same six census columns.

### `zip_scores` (unit: ZIP aggregate)
- `total_gp_locations` — summed over IL = the GP-location **universe** denominator.
- `corporate_location_count` — LEGACY detector floor input. Context only.

### Tier semantics (ratified, charter §2.5)
- **T1** = one dentist who BOTH owns AND operates one location. This is the only "solo owner-operated" tier.
- **T2/T3** = dentist-owned, not solo (single-location group / multi-location dentist network). **NOT DSOs.**
- **T4/T5** = DSO/PE/corporate control (stealth / branded).
- **T6** = institutional (hospital, university, public health, corrections).

## 3. The five headline buckets (exactly these — never collapsed)

| Bucket key | Label | Tiers | Notes |
|---|---|---|---|
| `true_solo_owner_operated` | True Solo Owner-Operated | T1 | |
| `dentist_owned_not_solo` | Dentist-Owned, Not Solo | T2+T3 | NOT independent-solo, NOT DSO |
| `dso_pe_corporate` | DSO / PE / Corporate Controlled | T4+T5 | the ONLY ADA-comparable number |
| `institutional` | Institutional | T6 | |
| `unresolved` | Unresolved | (none) | undetermined + holds + unreviewed. ALWAYS visible. |

**Labeling law (charter §2.7):** the broad top-line is **"Not Solo Owner-Operated %"** =
(reviewed − T1)/reviewed — NEVER "DSO-affiliated %". Only the T4+T5 share may sit next to the
ADA 14.6% IL anchor, and always with the unit caveat (ADA counts dentists; census counts locations).
Constants `NOT_SOLO_HEADLINE_LABEL`, `ADA_IL_PER_DENTIST_DSO_PCT`, `ADA_ANCHOR_UNIT_CAVEAT` live in
the module; the ADA number is an external anchor with citation — the only literal number allowed
(rule §2.1 bans hardcoding OUR census tallies, not cited external anchors).

## 4. The six source classes (every displayed number states one)

| Class | When | Display label |
|---|---|---|
| `census_reviewed` | `ownership_tier` is one of the six tiers | Census-reviewed |
| `held` | reviewed, blocked (dso_verify / unresolved / dup-suspect) | Held for adjudication |
| `undetermined` | researched, evidence too thin | Undetermined (researched) |
| `unreviewed` | census hasn't reached it | Not yet reviewed |
| `legacy_detector` | `entity_classification` / detector floor surfaces | Legacy detector estimate (context) |
| `pe_deal_context` | deal-announcement data | PE deal context |

**KNOWN DATA GAP:** Supabase carries **no review-status column**, so `held` (91) and
undetermined-researched (~477) are indistinguishable from never-researched — all have NULL tier.
Until a `census_review_status` column syncs, `deriveSourceClass(NULL)` → `unreviewed`, and the
Review Desk sources holds/triage counts from main-repo artifacts (`_lane_a_20260702/`,
`_census_holds_20260702.json`), labeled as file-sourced. The helper takes an optional
`reviewStatus` param so the UI upgrades automatically when the column lands.

## 5. Canonical helper API (`@/lib/census/ownership-truth`)

- `getOwnershipRecord(row, reviewStatus?)` → `{ tier, tierCode, bucket, statusClass, peBacked,
  confidence, evidenceBasis, evidenceUrls[], networkId, isCensusTruth }` — the single per-location
  entry point. Strips evidence/confidence for non-census-truth rows so stale text can't leak.
- `summarizeBuckets(rows, universe)` → `BucketSummary` — counts, `pctOfUniverse` (sums to 100 with
  unresolved), `pctOfReviewed`, `notSoloOwnerOperatedPctOfReviewed`, `dsoPePctOfReviewed/OfUniverse`,
  `peBacked`. `universe` MUST come from a live query.
- `tierToBucket(tier)` — unknown/NULL/detector values → `unresolved`, never a truth bucket.
- `deriveSourceClass(tier, reviewStatus?)`, `isOwnershipTier(v)`.
- Display meta: `BUCKET_META`, `TIER_META`, `TIER_CODE`, `SOURCE_CLASS_META`,
  `LEGACY_DETECTOR_CONTEXT_LABEL`.

**Consumer rule:** pages/components import these; none may switch on `ownership_tier` strings,
regroup tiers, or invent labels. `src/lib/supabase/queries/census.ts` is reconciled (2026-07-04):
`CensusSummary.buckets` is a `BucketSummary`; its old `independentReviewed` field (which wrongly
counted T2 as independent) is REMOVED. Legacy detector fields it still exposes
(`legacyCorporateLocations/Pct`) are context-class only.

## 6. Expected values after sync (verify, don't trust)

| Claim | Value | Recheck |
|---|---|---|
| IL tier notnull (locations) | 3,180 | `python3 -c "import sqlite3;c=sqlite3.connect('data/dental_pe_tracker.db');print(c.execute(\"SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL\").fetchone())"` |
| Tier tally T1–T6 | 1,471 / 934 / 537 / 28 / 151 / 59 | same query GROUP BY ownership_tier |
| `pe_backed` locations | 118 | same file, `WHERE pe_backed=1` |
| NPI mirror rows | 6,754 | `practices WHERE ownership_tier IS NOT NULL` |
| Universe (IL GP locations) | 4,439 | `SELECT SUM(total_gp_locations) FROM zip_scores` (state='IL') |
| Detector floor (context) | 268 corp locations / 1,152 corp NPIs | CI guards `FLOOR expect_min=268`, `FLOOR_NPI expect_min=1152` |
| Supabase pre-sync state | 343 tier rows only | Supabase: `practice_locations` count where `ownership_tier not is null` |

Until both sync legs run (user-authorized, charter §1b), the live app shows the 343-row slice and
must label coverage honestly — never imply the 3,180 exists live before it does.

## 7. The GP denominator — 4,439 is a documented filter, not a choice (added 2026-07-08)

The census universe "IL GP locations = 4,439" is derived, exactly and reproducibly, as:

```
4,639   practice_locations in watched IL ZIPs that are NOT specialist-only
 −179   entity_classification = 'da_unverified'   (Data-Axle synthetics — no federal NPI, unverifiable)
 − 12   entity_classification = 'non_clinical'    (labs, billing, staffing at GP-flagged addresses)
 −  5   entity_classification = 'duplicate_location' (suite/unit variants of an already-counted office)
 −  4   entity_classification = 'specialist'      (specialist rows the GP-location flag missed)
= 4,439  = SUM(zip_scores.total_gp_locations) for watched IL ZIPs   ← exact match, 0 residual
```

Rules:
- **This is an exclusion FILTER with SQL provenance, not a strategic decision.** Nobody gets to
  "pick" a denominator; anyone recomputing it must reproduce the 200-row exclusion set above.
- Every headline census percentage (reviewed %, tier shares, Not Solo Owner-Operated %) uses
  4,439 (or its per-ZIP `zip_scores.total_gp_locations` decomposition) as denominator.
- The four excluded classes are excluded EVERYWHERE (counts, maps, search, exports) — a row may
  not be excluded from the denominator yet appear on a map surface.
- **Pre-sync invariant (recommended, W-item):** add a check to `scripts/check_data_invariants.py`
  asserting `SUM(zip_scores.total_gp_locations) [IL watched] == COUNT(practice_locations)` under
  the filter above; a mismatch means `merge_and_score.py` and the exclusion rule have diverged.
- The number will drift as rows are reclassified (e.g., a da_unverified row earns a federal NPI).
  That is healthy; re-derive and update this section rather than pinning 4,439 forever.
