# GP-Scope & Special-Network Policy — DRAFT for user sign-off
**Date:** 2026-07-02 · **Author:** Fable (PM) · **Status:** DRAFT — no row is consolidated under this policy until the user ratifies it. Until then, affected rows stay in `hold_scope_policy` / `hold_protected_network` buckets.

## The principle that resolves most cases

**Denominator membership and ownership tier are separate decisions, decided in separate lanes.**
The census universe is the 4,439 IL GP locations as defined by `entity_classification` (specialist/
non_clinical/da_unverified/duplicate_location excluded). The ownership census may NOT eject a row
from that universe — if evidence shows a row is mis-scoped (actually specialist-only, actually
closed, actually a duplicate), that is an `entity_classification`/denominator correction, which
goes to the evidence-documented cleanup lane (closure queue, duplicate queue, scope-correction
queue), never through `ownership_tier`. The census's only job for in-universe rows is: assign a
tier or hold.

## Rulings requested (R1–R5)

### R1 — Affordable Dentures & Implants (ADI)
- **Scope:** ADI offices carry general-dentist taxonomy and sit in the GP universe today. They are
  tooth-replacement-focused but are staffed by GPs performing extractions/dentures/implants —
  **keep them in the GP denominator** (no scope ejection).
- **Tier:** ADI is a national branded network in which affiliated practices operate under a common
  brand with centralized lab/business support (MSO-style). **Proposed: T5 `branded_dso`** per
  location, with exact-locator or equivalent documentary evidence per row (no blanket flip).
- **pe_backed:** set per documented source at normalization time (ADI's corporate ownership must
  be cited in the row's evidence; if not documented, `pe_backed=false` never guessed).

### R2 — ClearChoice Dental Implant Centers
- Implant-only surgical centers; clinically specialist-scope. **Proposed: any ClearChoice row found
  inside the GP universe is a specialist-classification miss** → route to the scope-correction
  queue (denominator lane). Census bucket until resolved: `hold_scope_policy`. Never tiered while
  mis-scoped, so the GP consolidated % is never touched by implant-center rows.

### R3 — FQHCs / hospital / university clinics (e.g., Loyola)
- In-universe rows that are federally-qualified health centers, hospital outpatient dental, or
  university clinics: **T6 `institutional`**. T6 counts as census **coverage** but is **not**
  consolidated (consolidated = T2–T5) and **not** DSO/PE. Evidence bar: HRSA listing, hospital/
  university site, or state registry. Specialist-only academic clinics (e.g., grad perio/endo)
  are scope-correction candidates instead.

### R4 — Protected networks (NITTINGER, SHAFI, and any AO cluster ≥10 locations)
- Stay `hold_protected_network`. These are large AO/name clusters where a wrong call moves many
  rows at once. They get a dedicated evidence dossier each (own locator? MSO registration? press?)
  and a one-network-one-decision review by the PM, then user sign-off before any write. AO reach
  alone NEVER produces T4/T5 for these.

### R5 — Operating status (closure-flagged rows)
- Rows with strong closure evidence (from the closure queue) are **denominator-lane** items. The
  census does not classify ownership of likely-closed sites: bucket `hold_operating_status`,
  excluded from coverage math until the closure lane resolves them (either removed from the
  denominator with evidence, or confirmed open and returned to the census queue).

## What this unblocks once ratified
- Lane-2/Wave-4 `hold_scope_*` rows get deterministic routing.
- ADI rows can be normalized T5 with per-row locator evidence (no blanket action).
- The consolidated-% definition stays clean: T2–T5 over the (cleaned) GP denominator, DSO/PE %
  = T4–T5, floor-lift vs coverage never conflated, T6 visible but never inflating consolidation.

**Sign-off needed from user:** R1 tier ruling (ADI = T5), R2 scope ejection path, R3 T6 semantics,
R4 protected-network procedure, R5 closure-hold rule. Yes/no per item is enough.
