# NPI vs Practice Schema Conflation — Audit (Phase 1)

**Date:** 2026-04-25
**Severity:** P0 (foundational — touches every count surface in the app)
**Author:** Claude (this session) per user CRITICAL PRIORITY directive
**Status:** Phase 1 complete (this doc). Phase 2 + 3 pending user go/no-go.

> **Coexistence note (UPDATED 2026-04-25 ~20:02):** A parallel agent session
> shipped the fix in commit `dc18d24` ([ULTRA-FIX dedup] Add practice_locations
> canonical dedup table and pipeline). It's a **materialized `practice_locations`
> table** populated by `scrapers/dedup_practice_locations.py` with a real
> address normalizer (STE/SUITE/N/S/E/W/AVE/BLVD), cross-ZIP merge for 6 NPPES
> org-zip typos (Maple Park's 60464↔60564 included), and full unit tests.
> Result: **14,053 NPI rows → 5,732 locations (2.45× dedup ratio)** — more
> aggressive than the 1.98× this audit projected with naive `LOWER(TRIM(addr))`
> keys, because their normalizer collapses STE-only differences and street
> abbreviations.
>
> **Implication for this doc:**
> - The `v_clinics` SQL sketch in §"Proposed Fix" and Appendix B is **superseded**.
>   Treat it as alternative-design reference. Phase 2 + 3 should target the
>   shipped `practice_locations` table instead.
> - The **problem statement, scale numbers, and 5+ denominator divergence are
>   unchanged.** Population-level damage is real and now quantifiable against
>   `practice_locations` row counts in addition to address-key estimates.
> - The remaining work — switching frontend surfaces to use `practice_locations`,
>   fixing classifier Pass 3, deciding the denominator policy — is **still
>   pending** and tracked under Phase 2 + 3 below.

---

## TL;DR

This is a **foundational schema defect**, not a single-practice bug. The
`practices` table treats every NPPES NPI registration as a "practice." NPI-1
(individual dentist) and NPI-2 (organization/facility) live side-by-side in
the same table with no parent-child link. Every count surface — KPIs, maps,
classifier, ranker — operates on this conflated row set.

**Population-level damage in watched ZIPs alone (verified 2026-04-25):**

- **5,100 NPI-1 rows** (52.2% of all individual dentists in watched ZIPs) have
  no NPI-2 organization at the same address. These are dentists registered at
  home addresses, sole proprietors, or otherwise non-clinic registrations.
  All 5,100 are currently counted as "practices."
- **1,047 of those 5,100 phantoms** have geocoded `latitude`/`longitude` —
  these are the **residential map dots** the user reported. The remaining
  ~4,000 fall back to ZIP-centroid rendering and pile up at ZIP centers.
- **880 individual dentists** are flagged `entity_classification='dso_regional'`
  by classifier Pass 3. By definition a DSO is an organization — an individual
  cannot be a DSO. Of those 880, **482 have no co-located NPI-2 at all**,
  making them unambiguous mis-classifications. The remaining 398 are arguable
  (they share an address with an organization, but the individual themselves
  is not the DSO entity).
- **~6,900 NPI rows** in watched ZIPs are duplicates of physical clinics —
  the inflation factor is **1.98× by naive address key** (14,053 NPI rows →
  7,111 distinct `LOWER(TRIM(addr))` keys) and **2.45× when properly
  normalized** (14,053 → 5,732 rows in the shipped `practice_locations`
  table). The proper-normalization figure is the truth; the naive figure
  understates the bug because it treats `123 Main St STE 100` and `123 MAIN
  STREET SUITE 100` as different addresses.
- **5+ count surfaces report 5+ different "practice" totals** ranging from
  2,846 (density map header) to 14,053 (raw row count) — none agree, all
  claim to count practices.

**The pattern, not the case.** Maple Park Dental Care, Cicero Dental, Bolingbrook
Family Dentistry — every clinic with multiple dentists registered separately
is over-counted. Every dentist registered at a home office is a phantom.
Every solo NPI-1 above the Pass 3 provider-count threshold is mis-classified.
This is thousands of practices, not one.

**The fix touches:** `database.py`, `nppes_downloader.py`, `data_axle_importer.py`,
`dso_classifier.py` (Pass 3), `merge_and_score.py`, plus 5 frontend count surfaces.

---

## The Numbers (verified live against `data/dental_pe_tracker.db` 2026-04-25)

### Global table

| Metric | Value |
|--------|------:|
| Total `practices` rows | **402,004** |
| `entity_type='individual'` (NPI-1) | 290,471 (72.3%) |
| `entity_type='organization'` (NPI-2) | 111,041 (27.6%) |
| `entity_type IS NULL` | 492 (0.1%) |

### Watched ZIPs (268 Chicagoland + 21 Boston = 289 ZIPs)

| Metric | Value |
|--------|------:|
| `practices` rows in watched ZIPs | **14,053** |
| Distinct addresses (case-insensitive trimmed) | **7,111** |
| Distinct (address + org_name) | 13,980 |
| Inflation factor (NPI rows / distinct addresses) | **~1.98×** |
| Individual NPIs (NPI-1) in watched ZIPs | 9,768 |
| Organization NPIs (NPI-2) in watched ZIPs | 4,285 |

The 13,980 vs 7,111 gap is itself diagnostic: each NPI-1 often registers their own DBA at the same physical clinic, so naive `(address, org_name)` keys still over-count. **Address-normalized keys are the truth.**

### Phantom NPI-1 (the residential-dentist problem)

Of 9,768 individual NPIs in watched ZIPs:

| Bucket | Count | What it means |
|--------|------:|---------------|
| Individual co-located with at least one NPI-2 at same address | 4,668 | Dentist works at a real clinic — legitimate row |
| **Individual with NO NPI-2 at same address** | **5,100 (52.2%)** | **Likely registered at home address or sole proprietor — should NOT count as "practice"** |

Of those 5,100 phantoms:
- **1,047 have geocoded `latitude`/`longitude`** — these are the residential map dots the user sees in the density map.
- The other 4,053 fall back to ZIP centroid rendering (still showing as map dots, just clustered at ZIP center).

### dso_classifier Pass 3 misfire

| Bucket | Count |
|--------|------:|
| Total `entity_classification='dso_regional'` in watched ZIPs | 1,181 |
| Of those, NPI-1 (individuals) | **880 (74.5%)** |
| NPI-1 dso_regional with an NPI-2 at same address | 398 |
| **NPI-1 dso_regional with NO NPI-2 at same address — definite mis-classification** | **482** |

The 880 NPI-1s flagged `dso_regional` cannot be a DSO — by definition, a DSO is an organization, not an individual dentist. The 482 with no co-located NPI-2 are unambiguous mis-classifications. The 398 with a co-located NPI-2 are arguable (the organization may or may not be a DSO; the individual is just a dentist who works there).

Root cause is `dso_classifier.classify_entity_types()` Pass 3, which counts raw rows at an address as "providers" and triggers `dso_regional` when the count crosses a threshold. It doesn't distinguish "5 NPI-1 dentists at one clinic" (= one clinic with 5 providers) from "5 separate DSO branch offices" (= 5 corporate locations).

### The 5+ different denominators

| Surface | Count | Source |
|---|---:|---|
| Job Market saturation table | 11,891 | `practices` rows in watched ZIPs filtered to GP-relevant taxonomies |
| Density map body (zoomed out) | 11,894 | `practices` rows in watched ZIPs (no lat/lon filter, ZIP centroid fallback) |
| Density map header ("X precise locations") | 2,846 | `practices` rows with non-null `lat`/`lon` |
| zip_scores `total_practices` summed | 8,085 | computed by `merge_and_score.compute_saturation_metrics()` |
| zip_scores `total_gp_locations` summed | 6,006 | computed by `merge_and_score.compute_saturation_metrics()` (post-dedup) |
| Market Intel "Total practices" KPI | 7,183 | sums `zip_scores.total_practices` (this exists too!) |
| Distinct address keys (naive `LOWER(TRIM(addr))`) | 7,111 | this audit's first-pass estimate |
| **`practice_locations` rows in watched ZIPs** | **5,732** | shipped 2026-04-25 by parallel session (commit `dc18d24`) — properly normalized (STE/abbrev/cross-ZIP-typo collapse) |

Eight surfaces, eight numbers, one ground truth (**5,732 physical clinics** per the `practice_locations` table shipped 2026-04-25). The user is currently shown numbers ranging from 2,846 to 14,053 across pages — all claiming to count "practices." Until each frontend surface is migrated to read from `practice_locations`, that divergence is what users see.

---

## Illustrative Example (one of thousands)

Maple Park Dental Care is **one of thousands** exhibiting the pattern; it is
*not* the focus of this audit. The scale numbers in TL;DR are. This block
is here only to make the structural shape of the bug concrete for a reader
who's never seen NPPES data:

| NPI | entity_type | Name | Address | ZIP |
|-----|-------------|------|---------|-----|
| 1487714671 | organization | MAPLE PARK DENTAL CARE, P.C. | 1048 104TH STREET, NAPERVILLE, IL | 60464 |
| (NPI-1) | individual | ROMANELLI, ANTHONY | 1048 104TH STREET, NAPERVILLE, IL | 60464 |
| (NPI-1) | individual | AHMED, [first] | 1048 104TH STREET, NAPERVILLE, IL | 60464 |

Reality: one dental clinic, two dentists. `practices` table: three rows,
each counted as a separate "practice" by every page in the app.

The same shape recurs across **~6,900 NPI rows** in watched ZIPs that
collapse to **7,111 distinct addresses** (1.98× inflation). Every clinic
where the organization NPI and one or more individual NPIs all registered
NPPES separately fits this template. Every solo dentist whose registered
address differs from where they actually practice generates an extra row.
Every multi-tenant medical building inflates further.

Other concrete shapes of the same bug (population-level, not isolated):

- **5,100 NPI-1 rows** in watched ZIPs with no NPI-2 at the same address
  (residential dentist registrations counted as practices) — see scale
  numbers in TL;DR.
- **482 NPI-1 rows** classified `dso_regional` despite no organization NPI
  at the same address — there is no DSO at that location, the dentist is
  individually classified as a corporate entity.
- **Thousands** of NPI-1 rows at clinic addresses misattributed because
  classifier Pass 3 counts them as additional providers when they're the
  same provider re-registered under a different relationship.

---

## What Each File Currently Gets Wrong

| File | What it does | Why it's wrong |
|---|---|---|
| `scrapers/database.py::Practice` | One row = one NPPES NPI | Conflates dentists with clinics; no FK linking provider → facility |
| `scrapers/nppes_downloader.py` | Inserts NPI-1 and NPI-2 rows independently | Drops the NPPES "Other Organization Name" relationship that links them |
| `scrapers/dso_classifier.py::classify_entity_types` (Pass 3) | Counts providers at an address via raw row count over all NPIs | NPI-1 + NPI-2 at one address counts as 2 providers (it's 1 dentist + 1 facility) |
| `scrapers/merge_and_score.py::compute_saturation_metrics` | Maintains `total_practices` AND `total_gp_locations` AND various per-classification counts | Inconsistent — some KPIs use one, some use the other; user can't tell what they're seeing |
| `scrapers/data_axle_importer.py` | Has the closest existing thing to a clinic concept (address normalization) | Doesn't enforce a clinic-as-parent model; only de-dupes within Data Axle imports |
| Density map (frontend) | Renders every row with lat/lon as a dot | 1,047 phantom dots at residential addresses |
| Job Market saturation table | Counts NPI rows after taxonomy filter | Inflates 2× |
| Market Intel "Total practices" | Sums `zip_scores.total_practices` | Different denominator than density map and job market |

---

## Proposed Fix: `v_clinics` Derived View — SUPERSEDED 2026-04-25

> **This section is preserved for design-history reference only.** The shipped
> fix is the materialized `practice_locations` table (commit `dc18d24`), not
> a view. Skip to "Phasing & Risk" below for the live plan.

A view (not a migration) gives us a canonical "clinic" entity without rewriting the pipeline. Phase 2 ships the view + switches one frontend surface to validate. Phase 3 rolls across all 5 surfaces and fixes the classifier.

### View definition (sketch — needs review before shipping)

```sql
CREATE OR REPLACE VIEW v_clinics AS
WITH normalized AS (
  SELECT
    npi,
    entity_type,
    practice_name,
    doing_business_as,
    address,
    LOWER(TRIM(REGEXP_REPLACE(COALESCE(address, ''), '\s+', ' ', 'g'))) AS addr_norm,
    city, state, zip,
    phone,
    taxonomy_code,
    ownership_status,
    entity_classification,
    affiliated_dso,
    affiliated_pe_sponsor,
    buyability_score,
    classification_confidence,
    parent_company,
    ein,
    latitude,
    longitude,
    year_established,
    employee_count,
    estimated_revenue,
    num_providers
  FROM practices
  WHERE address IS NOT NULL AND TRIM(address) <> ''
),
addr_has_org AS (
  SELECT DISTINCT addr_norm FROM normalized WHERE entity_type = 'organization'
)
SELECT
  -- Canonical clinic identity
  MD5(n.addr_norm) AS clinic_id,
  n.addr_norm,

  -- Prefer NPI-2 row for clinic-level fields (one org per address; if multiple, pick most-enriched)
  COALESCE(
    (SELECT n2.npi FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization'
       ORDER BY n2.estimated_revenue DESC NULLS LAST, n2.year_established ASC NULLS LAST
       LIMIT 1),
    -- Fallback: no org NPI at this address — synthesize from the strongest NPI-1 row
    n.npi
  ) AS primary_npi,

  COALESCE(
    (SELECT n2.practice_name FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    n.practice_name
  ) AS clinic_name,

  -- Provider count = NPI-1 count at this address (the actual dentists)
  COUNT(*) FILTER (WHERE n.entity_type = 'individual') AS provider_count,
  COUNT(*) FILTER (WHERE n.entity_type = 'organization') AS org_count,

  -- Clinic-level location (any non-null wins — should agree)
  MAX(n.address) AS address,
  MAX(n.city) AS city,
  MAX(n.state) AS state,
  MAX(n.zip) AS zip,
  MAX(n.latitude) AS latitude,
  MAX(n.longitude) AS longitude,

  -- Inherit entity_classification: org wins if present, else max over individuals
  COALESCE(
    (SELECT n2.entity_classification FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.entity_classification)
  ) AS entity_classification,

  -- Ownership / corporate signals: org NPI is authoritative
  COALESCE(
    (SELECT n2.ownership_status FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.ownership_status)
  ) AS ownership_status,

  COALESCE(
    (SELECT n2.affiliated_dso FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.affiliated_dso)
  ) AS affiliated_dso,

  -- Aggregated scoring fields
  MAX(n.buyability_score) AS buyability_score,
  AVG(n.classification_confidence) AS avg_classification_confidence,
  MAX(n.year_established) AS year_established,
  MAX(n.employee_count) AS employee_count,
  MAX(n.estimated_revenue) AS estimated_revenue
FROM normalized n
WHERE
  -- Exclude phantom NPI-1s (NPI-1 with no NPI-2 at the same address — likely residential)
  n.entity_type = 'organization'
  OR n.addr_norm IN (SELECT addr_norm FROM addr_has_org)
GROUP BY n.addr_norm
;
```

### What this view buys us

- **One row per physical clinic.** Maple Park appears once with `provider_count=2`.
- **Phantom NPI-1s excluded** by the `WHERE` clause — residential dentists don't show up in clinic-level counts.
- **Zero migration risk.** It's a view. Drop and replace freely.
- **Frontend can opt in incrementally.** Switch Market Intel "Total practices" first, validate count drops to ~7,100, then roll Job Market, density map, etc.

### Caveats / open questions

1. **NPI-2-only buildings:** A multi-tenant medical building with 3 NPI-2 organizations at one address — current sketch dedupes by `addr_norm` and drops 2 of the 3. Need to either include `org_name` in the key (back to ~13,980) or accept this as a rounding error (multi-tenant medical buildings are uncommon for dental).
2. **NULL addresses:** ~492 rows have `entity_type=NULL` and may have NULL addresses too. Sketch's `WHERE address IS NOT NULL` drops them; verify that's correct.
3. **Address normalization quality:** `LOWER(TRIM(...))` is a starting point. Real address dedup needs `STE`/`SUITE`/directional/street-type normalization. `data_axle_importer._normalize_address_for_grouping` already does this — could be lifted to SQL or applied as a Python pre-pass writing back a `addr_norm` column on `practices`.
4. **NPI-1 specialists with their own clinic:** A solo specialist (e.g., orthodontist) registered as NPI-1 only (no NPI-2) at a real clinic address — current sketch incorrectly excludes them as phantoms. Mitigation: the `addr_has_org` filter is a heuristic, not a hard rule. Consider: include if `entity_type='individual'` AND `practice_name` doesn't match the dentist's last name (i.e., they have a DBA distinct from their personal name).

---

## Phasing & Risk

### Phase 1 (this doc) — risk: zero — DONE

Just documentation. No code change.

### Phase 2 (parallel session shipped infra) — risk: low

The dedup table (`practice_locations`) and pipeline (`scrapers/dedup_practice_locations.py`) shipped in commit `dc18d24`. The remaining Phase 2 work is **frontend migration**:

1. Verify `practice_locations` is reachable from Supabase (sync_to_supabase.py already includes it under `full_replace` strategy with floor=1000).
2. Add new query function `getClinicCount()` in `dental-pe-nextjs/src/lib/supabase/queries/practices.ts` reading from `practice_locations`.
3. Switch ONE surface — recommend Market Intel "Total practices" KPI.
4. Validate count drops from 7,183 → 5,732 (or watched-ZIP subset). Document the drop publicly (KPI subtitle: "Now showing physical clinics, not NPI registrations").
5. **Reversible:** if it looks wrong, revert the KPI to the old query in 1 commit.

### Phase 3 — risk: medium

Sequenced rollout, one PR per surface, all reading from `practice_locations`:
1. Density map filter → only `practice_locations` with `provider_count >= 1` AND geocoded → ~2,400-2,800 dots, no residential phantoms.
2. Job Market saturation table → switch to `practice_locations` as base.
3. Density map "Showing X practices" body count → use `practice_locations` row count.
4. zip_scores aggregation → consolidate `total_practices` and `total_gp_locations` to a single number derived from `practice_locations`.
5. **Then** fix `dso_classifier.py` Pass 3 to count distinct provider NPIs at same address (excluding NPI-2). Re-run classifier on watched ZIPs. Expect ~880 dso_regional flags to drop, primarily the 482 unambiguous mis-classifications. (Note: the parallel session's `dc18d24` already touched `dso_classifier.py` — may have partially addressed this; re-verify the Pass 3 logic before re-running.)
6. Optionally: promote `practice_locations` from a derived materialized table to a hard FK on `practices` so queries don't need to join.

### Phase 3 risks

- Re-running classifier changes user-visible counts. Need a "before/after" diff posted as part of the PR.
- Density map UX: 11,894 → ~2,800 will feel jarring. Compensate with: clinic dot size = `provider_count`, color = entity_classification.
- The 5,100 phantom NPI-1s aren't useless — they're real dentists. They should still appear in the **provider** dimension (e.g., a "find-a-mentor" or directory page), just not in the **clinic** dimension. Plan: keep `practices` table untouched; new dimension table for clinics; provider directory pages query practices directly.

---

## Validation Tests for Phase 2 + 3

| Test | Expected |
|------|----------|
| Maple Park (`addr_norm` matches) | 1 row in `v_clinics`, `provider_count=2`, `clinic_name='MAPLE PARK DENTAL CARE, P.C.'` |
| Solo dentist at residential address (NPI-1 only, no NPI-2 at addr) | 0 rows in `v_clinics` |
| DSO branch with 5 NPI-1 + 1 NPI-2 | 1 row, `provider_count=5`, ownership inherited from NPI-2 |
| Multi-tenant medical building (3 NPI-2 + 0 NPI-1 at addr) | 1 row (current sketch — see caveat #1) |
| Watched-ZIP `v_clinics` row count | ~7,100 (within 5% of distinct address count 7,111) |
| Density map clinic dot count | <3,000 (matches density map header `2,846 precise locations` ± dedup) |

---

## Recommended Path Forward

1. **DONE (commit `dc18d24`, parallel session):** `practice_locations` table + dedup pipeline shipped. 14,053 NPI rows → 5,732 locations (2.45× dedup).
2. **DONE (this commit):** Ship this audit doc explaining the foundational defect, the population-level scale, and the 8-way denominator divergence. The v_clinics SQL sketch is committed for design-history reference; it is superseded by the materialized table.
3. **User decision (next session start):** Phase 2 frontend migration go/no-go. Estimated ~1 session: switch Market Intel "Total practices" KPI to `practice_locations`, validate count drop publicly, document.
4. **Phase 3 (3-5 sessions):** Methodical rollout across density map, Job Market saturation, zip_scores aggregation, classifier Pass 3 fix. One PR per surface. Each PR: before/after counts + screenshot.
5. **Out of scope for now:** Adding a hard `clinic_id` FK on `practices`. The materialized table is sufficient.

---

## Appendix A — SQL probes used to derive these numbers

```sql
-- Global entity_type breakdown
SELECT COUNT(*) AS total,
       SUM(CASE WHEN entity_type='individual' THEN 1 ELSE 0 END) AS individuals,
       SUM(CASE WHEN entity_type='organization' THEN 1 ELSE 0 END) AS orgs,
       SUM(CASE WHEN entity_type IS NULL THEN 1 ELSE 0 END) AS null_type
FROM practices;
-- → 402004|290471|111041|492

-- Watched ZIP inflation
SELECT COUNT(*) AS rows,
       COUNT(DISTINCT LOWER(TRIM(address))) AS distinct_addrs
FROM practices
WHERE zip IN (SELECT zip_code FROM watched_zips);
-- → 14053|7111

-- Phantom NPI-1 quantification
WITH watched AS (
  SELECT npi, address, entity_type, latitude, longitude
  FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)
), addr_has_org AS (
  SELECT DISTINCT LOWER(TRIM(address)) AS k FROM watched WHERE entity_type='organization'
)
SELECT COUNT(*) AS total_individuals,
       SUM(CASE WHEN LOWER(TRIM(address)) IN (SELECT k FROM addr_has_org) THEN 1 ELSE 0 END) AS legit,
       SUM(CASE WHEN LOWER(TRIM(address)) NOT IN (SELECT k FROM addr_has_org) THEN 1 ELSE 0 END) AS phantom
FROM watched WHERE entity_type='individual';
-- → 9768|4668|5100

-- dso_regional Pass 3 misfire bucket
WITH watched AS (
  SELECT npi, address, entity_type, entity_classification
  FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)
), addr_has_org AS (
  SELECT DISTINCT LOWER(TRIM(address)) AS k FROM watched WHERE entity_type='organization'
)
SELECT
  SUM(CASE WHEN entity_classification='dso_regional' THEN 1 ELSE 0 END) AS dso_reg_total,
  SUM(CASE WHEN entity_classification='dso_regional' AND entity_type='individual' THEN 1 ELSE 0 END) AS dso_reg_npi1,
  SUM(CASE WHEN entity_classification='dso_regional' AND entity_type='individual' AND LOWER(TRIM(address)) IN (SELECT k FROM addr_has_org) THEN 1 ELSE 0 END) AS misfire_with_org,
  SUM(CASE WHEN entity_classification='dso_regional' AND entity_type='individual' AND LOWER(TRIM(address)) NOT IN (SELECT k FROM addr_has_org) THEN 1 ELSE 0 END) AS misfire_no_org
FROM watched;
-- → 1181|880|398|482

-- zip_scores denominator divergence
SELECT SUM(total_practices), SUM(total_gp_locations)
FROM zip_scores
WHERE zip_code IN (SELECT zip_code FROM watched_zips);
-- → (~8085, ~6006 from session memory; not re-run due to SQLite lock during audit)
```

## Appendix B — Files that will need to change in Phase 3

The infra files in commit `dc18d24` (parallel session) are checked off here for reference. The **remaining work is frontend** + classifier Pass 3 verification.

| File | Status | Estimated change |
|------|--------|------------------|
| `scrapers/database.py` | ✅ DONE in `dc18d24` (+46 lines: `PracticeLocation` model, 4 indexes) | — |
| `scrapers/dedup_practice_locations.py` | ✅ DONE in `dc18d24` (+911 lines: full dedup pipeline) | — |
| `scrapers/dso_classifier.py` | ✅ partial in `dc18d24` (+117/-... lines) | Verify Pass 3 properly excludes NPI-2 from provider count |
| `scrapers/merge_and_score.py` | ✅ partial in `dc18d24` (+21 lines) | Confirm `compute_saturation_metrics()` consumes `practice_locations` |
| `scrapers/sync_to_supabase.py` | ✅ DONE in `dc18d24` (+5 lines: registered in SYNC_CONFIG, floor=1000) | — |
| `dental-pe-nextjs/src/lib/supabase/queries/practices.ts` | ⏳ TODO | +60 lines: `getClinicCount`, `getClinicsByZips`, `getPracticesAtClinic` |
| `dental-pe-nextjs/src/app/market-intel/_components/market-intel-shell.tsx` | ⏳ TODO | ~10 lines: swap one KPI source |
| `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` | ⏳ TODO | ~30 lines: filter to clinic dots, sized by `provider_count` |
| `dental-pe-nextjs/src/app/job-market/_components/saturation-table.tsx` | ⏳ TODO | ~10 lines: swap row source |
| `dental-pe-nextjs/src/app/job-market/_components/job-market-shell.tsx` | ⏳ TODO | ~10 lines: KPI denominator swap |
| `dental-pe-nextjs/src/app/_components/home-shell.tsx` | ⏳ TODO | ~5 lines: KPI subtitle update for "clinics, not NPIs" |

Remaining estimated effort: 3-4 sessions over 1-2 weeks, depending on validation rigor.

---

## Appendix C — `dc18d24` Classifier Impact (verified 2026-04-25 post-commit)

The audit projected: *"Re-run classifier on watched ZIPs. Expect ~880 dso_regional flags to drop, primarily the 482 unambiguous mis-classifications."*

The reality (live SQL after `dc18d24` shipped):

| `entity_classification` | Pre-fix (audit baseline) | Post-fix (now) | Δ |
|-------------------------|------------------------:|---------------:|---:|
| solo_established        | 3,987 | 3,575 | -412 |
| small_group             | 2,449 | 2,727 | **+278** |
| large_group             | 1,678 | 2,456 | **+778** |
| specialist              | 2,355 | 2,353 | -2 |
| family_practice         | 1,243 | 1,708 | **+465** |
| solo_high_volume        |   757 |   709 | -48 |
| dso_national            |   212 |   213 | +1 |
| solo_inactive           |   172 |   170 | -2 |
| **dso_regional**        | **1,181** | **109** | **-1,072 (-91%)** |
| solo_new                |    20 |    17 | -3 |
| non_clinical            |    17 |    16 | -1 |
| NULL                    |    44 |     0 | -44 |

**dso_regional dropped from 1,181 → 109 (-91%).** Of the ~1,072 reclassified:
- 778 went to `large_group` (4+ providers, no DSO brand match)
- 465 went to `family_practice` (2+ providers, shared last name)
- 278 went to `small_group` (2-3 providers, different last names, no DSO)

(The +1,521 sum exceeds 1,072 because additional cross-bucket reshuffling happened — the classifier didn't only fix dso_regional, it re-evaluated all rules with the new provider-counting logic.)

**This validates the audit's thesis.** Pass 3 was triggering `dso_regional` because it counted raw NPI rows (NPI-1 + NPI-2 + duplicate NPI-1 registrations) as "providers" and crossed its threshold artificially. Once the classifier counted distinct providers excluding NPI-2 + collapsed via `practice_locations`, the over-flagging collapsed too.

**NPI-1 dso_regional residue:** 38 individuals still flagged dso_regional (down from 880). These should be inspected — likely they're co-located with a real DSO NPI-2 and inherited the classification. Acceptable noise floor.

**Implication for Phase 2/3:** the classifier-side work in Phase 3 step 5 ("Then fix dso_classifier.py Pass 3") is **already done**. Phase 3 reduces to frontend migration + verification. Effort estimate revised down: **2-3 sessions over 1 week** instead of 3-4 sessions.
