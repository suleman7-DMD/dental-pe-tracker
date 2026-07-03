# DECISIONS — Census consolidation gate (user-delegated, 2026-07-02)

**Authority:** The user, presented with the decision list in
`PROOF_PACKAGE_CONSOLIDATION_GATE_20260702.md`, delegated: *"make the best
answers to the decisions. you have answering abilities. then proceed."*
Decisions below are made by Fable (PM of record) under that delegation and are
binding for this consolidation run. Any of them can be reversed later by the
user; every affected row carries an in-row audit note, and `--allow-rereview`
plus the ledger make reversals mechanical.

## R1 — Affordable Dentures & Implants: **YES (ADI = T5, stays in GP denominator)**
ADI offices carry general-dentist taxonomy, are staffed by GPs performing
extractions/dentures/implants, and sit in the GP universe today. The network is
a national brand operated by Affordable Care LLC, PE-backed (Harvest Partners,
~$2.7B, 2021) — the definition of T5 `branded_dso`. Evidence per row is strong:
per-location affordabledentures.com locator URLs + Harvest Partners portfolio
page + press. **Effect:** the 3 held Affordable rows (`199841c7ee233c17`,
`bd77120df3018393`, `23db306c0cb65354`) are reinstated as classified T5,
`pe_backed=true`. All three are `dso_national` in the detector already, so
they are corroborations — zero floor lift, +3 coverage.

## R2 — ClearChoice: **YES (scope ejection path ratified)**
Implant-only surgical centers are clinically specialist-scope. Any ClearChoice
row found inside the GP universe is a specialist-classification miss → routed
to the scope-correction queue (denominator lane), bucket `hold_scope_policy`,
never tiered while mis-scoped. **Checked this run: 0 ClearChoice rows in the
candidate set** (the one "CLEAR" text hit was the word "clearly" in a Dental
Dreams rationale). No effect on the current file; the rule binds future waves.

## R3 — FQHC / hospital / university clinics: **YES (T6 semantics ratified)**
T6 `institutional` counts as census **coverage** but is never consolidated
(consolidated = T2–T5) and never DSO/PE (headline = T4–T5). Evidence bar: HRSA
listing, hospital/university site, or state registry. The 10 T6 rows in the
candidate set follow this semantics.

## R4 — Protected networks: **YES (procedure ratified) + named networks decided**
Procedure: AO/name clusters ≥10 locations get one-network-one-decision review;
gate-owner self-release is never sign-off; AO reach alone never produces T4/T5.
Named networks (all rows keep `r4_flag` as audit trail):
- **NITTINGER_RACHEL — ACCEPT T5 (11 rows).** DOL EBSA MEWA filing evidence is
  strong and structural (a multi-employer welfare arrangement across the
  locations is corporate-network behavior, not coincidence). 10 of 11 are
  corroborations of already-corporate locations; 1 is net-new floor lift.
- **LABINOV_BORIS — ACCEPT T5 (7 rows, Destiny/ProSmile).** The brand is a
  known PE-backed DSO from prior verified work (2026-06-07 Phase-4 evidence);
  all 7 are net-new floor lift.
- **SHAFI_SOHAIL — ACCEPT T3 (18 rows, Two Rivers Dental).** Dentist-owned
  multi-location; T3 never touches the DSO/PE headline, so the acceptance is
  consolidation-coverage only.

## R5 — Operating status: **YES (closure-hold rule ratified) + 2 adjudications**
The census does not classify ownership of likely-closed sites: any candidate in
the closure queue's `mark_likely_closed` set is held (`hold_operating_status`)
unless the closure item is adjudicated. The cross-check is now ENFORCED in the
normalizer (it was not previously run — running it found 2 hits out of 340).
Both closure flags are contradicted by stronger direct evidence and are
**adjudicated ACTIVE** (documented in-row and in the closure lane):
- `8acd52381e465e57` **Geneva Dental Ltd** — the closure evidence itself says
  the CLOSED Yelp listing is the *prior* address (401 Williamsburg Ave) and the
  practice relocated TO this row's address (2172 Blackberry Dr); intel dossier
  (2026-04-26) + live site (drtingzon.com) confirm active. The closure-queue
  entry is a relocation misread — a false positive of the Metropolitan Dental
  Care type already flagged in the closure-queue review.
- `b2445373c7020d73` **MetroSmiles Archer Heights** — closure flag cites BBB
  complaints/negative reviews (reputation evidence, not operating status);
  address confirmed on the brand's own current locator page. Stays classified
  T3 (`ao:TSALIAGOS_CHRISTOS`).

## Consolidation authorization: **YES**
Run `consolidate_census.py <consolidated file> --session
fable_pm_consolidation_20260702 --allow-db-write` after the regenerated file
passes `--validate-only` with 0 errors. SQLite only; Supabase sync is the next
step after SQLite verification (per the standing gate). Expected file shape
after R1/R5: **343 classified** (340 + 3 ADI reinstated, − 0 R5 holds) and
**6 holds** (9 − 3 ADI; Archer + Shorewood DA_ + 4 weak-68 + 1 North Ave — see
holds file; Archer resolution research is in flight and folds in later via
`--allow-rereview` or a follow-up candidate file).

## Repo hygiene: **YES (both commits authorized by "then proceed")**
- Root repo: commit census infrastructure, evidence files, decision docs.
- Nested `dental-pe-nextjs` repo: commit + push the frontend honesty fixes
  (build ✓, F27 vitest ✓ — PM-verified 2026-07-02); production deploys on push.

## Standing constraints that did NOT change
No `entity_classification` flips from census work; no denominator mutations
(closure/duplicate/scope queues stay review-only pending their own lanes);
Boston/MA parked; no Fleet B 101+ fan-out; never print `.env` values.
