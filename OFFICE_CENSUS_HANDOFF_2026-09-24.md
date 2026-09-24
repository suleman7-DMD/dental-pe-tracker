# Office Census Handoff — 2026-09-24

> Historical checkpoint. The pilot continuation is implemented in rules 2026-09-24.2.
> Start with `data/office_census/README.md` and the generated manifest. The old task
> list below is not an execution directive; source-count scoring, table recreation,
> generalized relinking and promotion-preview were deliberately not adopted.

This is a checkpoint only. The QC and P1–P4 redesign is **not implemented**. Nothing is on `main`, and nothing has been deployed.

## 1. Checkpoint branches: `office-census-foundation-2026-09-24`

| Repo | Base (`main`) | Foundation commit | Pushed |
|---|---|---|---|
| `dental-pe-tracker` | `7f4b9c2` | `9fc122e9a38f31fc9f0a333ce4cff58f749eec28`. This handoff is the next commit, at the branch tip. | origin, branch only |
| `dental-pe-nextjs` | `ff0eb70` | `e67ca0a822561c5376486509b73b7204360d28da` | origin, branch only. Vercel may build a *preview*, but production is untouched. |

Both working trees remain on `main`, and HEAD was not moved. This matters because `refresh.sh` runs a plain `git push` of the current branch on Sundays. The files are present in the working trees as untracked or modified copies, byte-identical to the branch commits.

Before running `git checkout <branch>`, move those copies aside, because git refuses to overwrite untracked files. Alternatively, keep working in place on `main`'s tree.

## 2. Files

**Parent repo (all new):**
- `scrapers/office_census.py` — builder, `check-ledger`, `next-batch`, `status`
- `scrapers/office_census_publish.py`
- `scrapers/office_census_schema.sql`
- `scrapers/test_office_census.py`
- `data/office_census/{.gitignore, candidates.jsonl, manifest.json, research_ledger.jsonl (meta line only), zip_coverage.csv}`

**Frontend repo:**
- New: `src/app/office-census/page.tsx`
- New: `src/app/office-census/_components/office-census-shell.tsx`
- New: `src/lib/supabase/queries/office-census.ts`
- Modified: `src/components/layout/sidebar.tsx` (adds the "Office Census" nav item)

**Deliberately excluded:**
- `data/job_hunt_verification_seed.json` (an unrelated reorder)
- `DIRECTORY_RECOVERY_PLAN_2026-09-20.md`
- `data/directory_foundation_audit_20260920_complete.json`
- `data/chicagoland_directory_export_manifest_20260920.csv`
- `scripts/audit_directory_foundation.py`

## 3. Commands that pass (run 2026-09-24 at checkpoint)

- `python3 -m pytest scrapers/test_office_census.py -q` → 18 passed
- `python3 scrapers/office_census.py check-ledger` → `OK: 0 error(s)`
- `python3 scrapers/office_census_publish.py --verify` → `OK: live office census matches the generated files exactly` (read-only)
- `npm run build` and `npx vitest run` (156) in `dental-pe-nextjs` → passed earlier this session. They were not re-run at the checkpoint, and the frontend code is unchanged since then.
- Not yet verified: that two consecutive `build` runs produce identical IDs.

## 4. Supabase (own additive tables only, no FK, not in `sync_to_supabase` or `refresh.sh`)

| Table | Contents |
|---|---|
| `office_census_candidates` | 5,798 rows |
| `office_census_zip_coverage` | 269 rows |
| `office_census_builds` | Append-only. Latest build **`e1382b7dff2c`**, rules `2026-09-24.1` |

- RLS is set to anon SELECT only; an anon write returns 401.
- The `/office-census` page is **not** live in production. It exists only on the frontend branch.
- Keep these tables as-is until task 8 below.

## 5. Counts (build `e1382b7dff2c`) and derivation

**By origin:** `directory_row` 4,439 / `excluded_row` 750 / `data_axle_unrepresented` 561 / `dso_locator_unrepresented` 32 / `nppes_unrepresented` 16.

**By queue state:**

| State | Count |
|---|---:|
| NEEDS_CURRENT_VERIFICATION | 3,635 |
| IDENTITY_REVIEW | 633 |
| SOURCE_CANDIDATE_UNREPRESENTED | 541 |
| LIKELY_SPECIALIST_ONLY | 456 |
| PROBABLE_NON_OFFICE | 214 |
| OPERATING_STATUS_UNRESOLVED | 142 |
| GP_SCOPE_UNRESOLVED | 104 |
| LOCATION_INCOMPLETE | 73 |
| CONFIRMED | **0** |

### Directory rows (4,439)

A directory row is an IL-watched `practice_locations` row whose `entity_classification` is in `GP_CLASSES` and which is not `is_likely_residential`. The builder reads SQLite with `mode=ro`.

- **By state:** NEEDS_CURRENT_VERIFICATION 3,635 / IDENTITY_REVIEW 633 / OPERATING_STATUS_UNRESOLVED 142 / LOCATION_INCOMPLETE 22 / GP_SCOPE_UNRESOLVED 7.
- **By prior evidence:** none 409 / ownership_review_only 1,441 / researched 2,211 / site_checked_live 378.
- **By coordinates:** stored_unverified 2,311 / none 1,454 / recoverable 674.

### Excluded rows (750)

These are all other IL-watched `practice_locations` rows: LIKELY_SPECIALIST_ONLY 456 / PROBABLE_NON_OFFICE 196 / GP_SCOPE_UNRESOLVED 97 / LOCATION_INCOMPLETE 1.

### Source candidates (609)

A source candidate is a normalized street key that appears in no IL-watched `practice_locations` row, whether that row is in the directory or excluded. The normalizer is AST-extracted from `scrapers/dedup_practice_locations.py`.

**Sources:**
- Data Axle raw CSVs, deduped by IUSA, keeping the latest "Last Updated On"
- NPPES 10-digit NPIs
- `dso_locations`

Origin priority is dso > da > nppes.

**State assignment:**
- A PO box or no house number → LOCATION_INCOMPLETE (DA 50).
- All DA SICs non-dental, with no DSO or NPPES record → PROBABLE_NON_OFFICE (DA 18).
- Everything else → **SOURCE_CANDIDATE_UNREPRESENTED 541** (DA 493 / DSO 32 / NPPES 16).

### The 541 are discovery candidates, NOT missing offices

- **By source family:** DA-only 492 / DSO-only 27 / NPPES-only 16 / DA+DSO 5 / DA+NPPES 1.
- **228 match an existing row:** 211 by phone, 77 by address variant (60 match on both).
- **Weak-signal flags:** `da_individual_listings_only` 150, `da_record_pre_2024` 94, `name_suggests_specialty` 64, `da_zip_centroid_only` 58, `no_gp_taxonomy` 1.
- **161 are clean:** no row match and no weak flag (DA 133 / DSO 21 / NPPES 7).
- The 541 span 177 ZIPs.

## 6. Known defects (in the checkpoint code)

1. **Confirmation is a source count.** `SINGLE_SOURCE_SUFFICIENT` (phone_call or dso_locator), otherwise ≥2 families. QC rejected this; it needs a per-axis, claim- and source-weighted model.
2. **Ordinary rows look evidence-free.** The 3,635 ordinary directory rows sit in NEEDS_CURRENT_VERIFICATION, which implies no evidence. They should be the provisional state EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION. The prior-evidence level "none" should read "registry_only".
3. **Prior research is only summarized, not imported.** The following appear only as truncated summaries on candidates, not as dated historical observations:
   - JHV seed (642)
   - `practice_intel`
   - ownership `LEDGER.jsonl` (3,692)
   - `practice_manual_corrections` (6)
   - IL `dso_locations`
4. **Coverage implies a ZIP can be "done".**
   - The `zip_coverage.stage` progression (not_started → recall_audited) suggests a finished ZIP.
   - `next-batch` skips swept ZIPs ("No unswept ZIPs remain.").
   - There is no tracking of discovery passes per source family, and no outcome metrics.
5. **IDs and evidence links are unstable.**
   - `source_refs` is truncated: `npis[:60]`, `iusa[:40]`, `phones[:3]`, `da_names[:10]`, `same_phone_rows[:5]`, `address_variant_rows[:5]`.
   - When a `src:` candidate gets represented in `practice_locations`, its ledger research is orphaned, because there is no alias registry and no relink entry.
6. **No P1/P2/P4 ordering.** There is no `research_priority`; priority is just 1/2/3 by state.
7. **The 541 are unexplained.** The UI and manifest label them "unrepresented" with no derivation, and there is no `source_candidate_breakdown`.
8. **A referenced README is missing.** The code, the ledger meta line and the TS comment all reference `data/office_census/README.md`, which does not exist.
9. **The coverage schema is rigid.**
   - `cov_params` int-casts every unlisted coverage column.
   - The jsonb template covers only `sources_searched`.
   - The schema CHECK pins the `stage` values.

   So any coverage-column change needs a DROP and recreate of the two replaceable tables inside the publish transaction, plus a lockstep frontend deploy, because the shell reads `stage`.

## 7. Agreed strategy: risk-based triage, not universal re-verification

- **P1 — absent candidates.** Work the 541, then the source rows in LOCATION_INCOMPLETE and PROBABLE_NON_OFFICE, plus `ext:` discoveries. Classify each as one of:
  - a distinct missing GP office
  - a duplicate or alternate representation
  - a specialist
  - closed, moved or stale
  - a provider or admin record
  - not an office
- **P2 — high-risk existing rows.**
  - the 633 in IDENTITY_REVIEW
  - the 142 in OPERATING_STATUS_UNRESOLVED
  - specialist, admin, GP-scope and location-incomplete rows
  - rows with contradictory name, suite, phone, website or source records
- **P3 — independent discovery, per researched ZIP.** Find GP offices absent from both the directory and every source. Record which source families and strategies were exhausted, with dates.
- **P4 — ordinary rows (~3,635).** No individual re-verification now.
  - Their state is EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION, with prior evidence and dates surfaced.
  - They get verified later through stale-evidence refresh, stratified precision samples, contradictions found during research, and opportunistic checks.
- **Batch = 1 ZIP.** Each batch should:
  - reconcile P1
  - resolve P2
  - run P3 discovery
  - touch P4 only opportunistically
  - record unresolved cases
  - measure what changed
- **First batch: 60602, as a full reconciliation including all P4 rows.** It measures old-directory precision, old-directory recall, source-recovery value, and independent-search value.
- **Per-ZIP outputs:**
  - new GP offices absent from the directory
  - new GP offices absent from all sources
  - directory rows rejected
  - duplicates collapsed
  - merged rows split
  - moved or closed offices
  - unresolved cases
  - best-estimate active GP count
  - discovery coverage
  - provenance
- **Historical evidence never auto-confirms.** The ledger starts at zero new adjudications, not zero evidence.

## 8. Remaining tasks, in dependency order

1. **Ledger model** (`office_census.py`):
   - Set `RULES_VERSION` to `2026-09-24.2`.
   - Axes: identity, exists_at_address, current_operation, gp_scope, address_suite, contact. Alias the old claims onto them.
   - Source strength:
     - strong = office_website, phone_call, dso_locator, hrsa_fqhc
     - moderate = google_business_profile, street_view
     - weak = everything else
   - An axis is established by ≥1 strong source, or ≥2 moderate, or moderate + weak, with no un-rebutted stronger contradiction.
   - Confirmation requires identity + exists + current_operation (≤365 days old) + gp_scope.
   - Remove `SINGLE_SOURCE_SUFFICIENT`.
   - Add a `relink` entry type (merged_into / supersedes / split_into).
   - Add `pass_type` to `zip_sweep`, still accepting `stage`.
2. **States and priority:**
   - Add EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION. It replaces NEEDS_CURRENT_VERIFICATION, including for expired confirmations, which also get the `confirmation_expired` flag.
   - Add `research_priority`: P1_absent_candidate / P2_high_risk_row / P4_deferred_ordinary.
   - Rename the prior-evidence level "none" to "registry_only".
3. **Historical import** → `data/office_census/historical_observations.jsonl`:
   - IDs of the form `hist:<system>:<id>`, with original dates and full URLs.
   - Add `verification_urls` to the `practice_intel` query.
   - Give each candidate an `evidence_axes` summary.
   - Historical observations never confirm.
4. **ID stability:**
   - Untruncate `source_refs`.
   - Add `id_registry.jsonl`, holding the street key per ID plus aliases.
   - Resolve IDs in the order exact → relink → alias → orphan.
5. **`zip_coverage` rework:**
   - Drop `stage`.
   - Add p1/p2 total and resolved, and p4 provisional and checked.
   - Add `discovery_passes` jsonb, `last_discovery_pass`, `recall_audit_at`, `building_tasks_open`.
   - Add `review_status`, which is never "done".
   - Add the outcome metrics and `best_estimate_active_gp`.
   - Add the precision/recall numerators and provenance counts.
6. **Manifest:** add `source_candidate_breakdown`, priority totals and outcome totals, replacing `zips_by_stage`.
7. **`next-batch`:**
   - Default to 1 ZIP and never exclude swept ZIPs.
   - Output P1 + P2 items, a discovery-task spec, and a compact `known_roster`.
   - `--full-reconciliation` adds P4.
   - Add a read-only `promotion-preview` subcommand.
8. **Schema and publisher:**
   - Add the new state to the CHECK, and add the new coverage columns.
   - The publisher drops and recreates the two replaceable tables inside its single transaction.
   - Generalize `cov_params` and the jsonb template, and update `verify()`.
9. **Tests:**
   - Rewrite `test_website_alone_cannot_confirm`.
   - Add tests for: one strong source beats two weak; historical observations never confirm; alias and relink; no "done" ZIP; priority tiers and the provisional state.
10. **Frontend:**
    - Update the types in `office-census.ts`.
    - Update the shell: priority views, the 541 labeled "discovery candidates — not missing offices", historical evidence, and outcome metrics.
11. **Write `data/office_census/README.md`.** Cover:
    - the unit
    - P1–P4
    - evidence and source-strength rules
    - the ledger schema, with examples
    - the terminal-state mapping
    - the batch protocol
    - the 60602 design
    - acceptance criteria: precision ≥98%, and recall at a 95% lower bound ≥92–95% from a held-out audit
    - map integrity
    - reversible cleanup
    - the 365-day refresh
    - the promotion path
    - the 541 derivation
    - ID rules
12. **Verify locally:**
    - Run `build` twice and confirm identical IDs.
    - Run `check-ledger` and pytest.
    - Run `npm run build` and `npx vitest run`.
13. **Publish and deploy:**
    - Run `office_census_publish.py --allow-db-write --verify`, then do an independent read-back.
    - Right away, merge both branches to `main` and push. The frontend must go out immediately after publishing, because the old shell reads `stage`.
    - Verify live `/office-census` and `/office-census?zip=60602`.
14. **Only then**, start the first research batch: 60602.

## 9. Local state not preserved in git

- `data/office_census/worklists/batch_60602.json` (27.6 KB). It is gitignored and can be regenerated with `python3 scrapers/office_census.py next-batch --zip 60602`. Its format changes in task 7.
- Design discussion that exists only in this session's transcript: `~/.claude/projects/-Users-suleman-dental-pe-tracker/05800273-8a00-490d-91c4-36ae54e66045.jsonl`. Sections 7 and 8 above capture it.
- The unrelated uncommitted files listed in section 2 were left untouched.
