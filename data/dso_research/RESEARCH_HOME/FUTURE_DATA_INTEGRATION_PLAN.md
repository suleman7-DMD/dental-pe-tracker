# Future App Plan: Chicagoland Ownership Directory

**Status:** future product/build plan. Do not implement until the ownership census data model and first verified consolidation manifest are stable.

## Goal

Transform the live app from a mostly percentage/map dashboard into a **Chicagoland dental ownership intelligence directory**: one evidence-backed record per watched-ZIP GP practice location, with the ownership structure, how it was found, confidence, QA status, and notes visible in the app.

This should support the user's core goal: a "god view" of every general dental practice across the ~4,439 Chicagoland GP locations.

## Product Principles

- Show the ownership census with coverage. Never imply all 4,439 practices are fully known until reviewed.
- Every ownership claim should have an evidence trail.
- `true_independent` is earned, not assumed.
- Ambiguous practices stay `undetermined` / `needs_verification`.
- Percentages are secondary to directory accuracy and must always show coverage.
- Keep `pe_backed` separate from DSO/platform structure. Non-PE DSOs can still be DSO/platform entities if evidence shows MSO, management-company, DSO brand, or support-organization structure.

## Core Views

### 1. Ownership Directory

One row per GP practice/location.

Recommended fields:

- practice name
- DBA / local brand
- address, city, ZIP
- ownership tier
- PE-backed: yes/no/unknown
- owner or network name
- confidence
- QA status
- reviewed status
- last reviewed date
- source count
- short evidence summary

Example row:

```text
ProCare Dental Group - Park Ridge
Tier: dentist_multi
Owner/network: Robert Brunetti / ProCare
PE-backed: No
Evidence: AO cluster + ProCare website + multi-location source
Confidence: High
Reviewed: 2026-06-21
```

### 2. Practice Detail Drawer / Page

For each practice, show:

- ownership tier and owner/network
- why it was classified that way
- evidence trail:
  - official locator URL
  - NPPES authorized-official / EIN / name-chain artifact
  - practice website
  - practice_intel source URLs
  - QA notes
- conflict flags:
  - duplicate-door issue
  - stale/closed NPI suspicion
  - exact-address mismatch
  - needs verification
  - possible co-location / brand-substring trap
- timeline:
  - first detected
  - evidence gathered
  - QA reviewed
  - consolidated into census

### 3. Coverage Dashboard

Show the state of the census honestly:

- reviewed: N / 4,439
- verified / ready: N
- needs more evidence: N
- undetermined: N
- rejected / closed / duplicate: N
- untouched remaining: N

Example:

```text
Reviewed: 812 / 4,439
Coverage: 18.3%
Unreviewed: 3,627
```

### 4. Ownership Map

Map colors should use the new ownership tiers, not only legacy `entity_classification`.

Suggested categories:

- true independent
- single-location group
- dentist-owned multi-location
- stealth DSO / MSO-backed local brand
- branded DSO
- institutional
- undetermined / unreviewed

Map labels must distinguish:

- reviewed practices
- unreviewed practices
- exact geocode vs ZIP-centroid/jittered location

### 5. Evidence Mode

Add a tab or toggle such as **Ownership Evidence**.

For each practice or ZIP, show:

- "How was this found?"
- DSO locator
- AO cluster
- EIN cluster
- name-chain
- practice_intel
- web verification
- QA correction
- duplicate warning

## Metrics To Show

Publish multiple metrics, each with coverage:

- true independent %
- all-consolidation % = single_loc_group + dentist_multi + stealth_dso + branded_dso
- DSO/platform % = stealth_dso + branded_dso
- PE-backed % = `pe_backed=true`
- institutional %
- undetermined / unreviewed %

Example wording:

```text
Consolidated: 38% of reviewed practices
Coverage: 812 / 4,439 reviewed
Unreviewed: 3,627
```

Do not present any metric as the total Chicagoland truth unless coverage is effectively complete.

## Data Model Needed Before Build

Build only after these are stable:

- ownership tier per location
- PE-backed flag
- owner/network name
- confidence
- evidence basis
- evidence URLs
- local evidence artifacts / query refs
- QA status
- reviewed_at
- reviewer/session source
- duplicate/closed/specialist exclusion flags
- notes / reasoning

Likely DB targets:

- keep `practice_locations.ownership_tier` and related columns for the current final tier
- create or materialize an ownership evidence / ledger table for source details
- sync the new fields/tables to Supabase

## Implementation Order

1. Finish the evidence pipeline and first verified consolidation manifest.
2. Decide final DB shape for evidence notes and QA status.
3. Sync ownership fields/evidence tables to Supabase.
4. Build the Ownership Directory page.
5. Add practice detail drawer evidence view.
6. Update maps and dashboards to use ownership tiers with coverage.
7. Remove or de-emphasize old corporate-only framing.
8. Add filters:
   - tier
   - PE-backed
   - reviewed status
   - confidence
   - evidence basis
   - ZIP
   - network/owner

## Future Claude Prompt

Use this when asking a future Claude/Codex session to build the app feature:

```text
Please read `data/dso_research/RESEARCH_HOME/FUTURE_APP_OWNERSHIP_DIRECTORY_PLAN.md` and the current ownership census files. Build the live Next.js app toward this Ownership Directory vision, but only after verifying the current DB/Supabase ownership data model and evidence tables are stable. Do not expose candidate/unclean evidence as final. Preserve coverage honesty and show evidence notes behind ownership claims.
```

