# Phase 1 — Data Axle Corporate-Signal Expansion: Design

> Written 2026-06-07 (Opus 4.8). Synthesizes Phase 0 investigation. **Mission:** close the hidden/stealth-DSO undercount by ingesting Data Axle's corporate-signal columns (currently discarded), use that evidence to confirm hidden corporate practices, and raise the documented corporate floor as far as hard evidence allows. This is the written design that gates implementation.

## 0. Phase 0 findings (what the investigation proved)

**On-disk corpus.** 184 raw CSV files on disk (`data/data-axle/processed/*.csv` + `data/data-axle/*.csv`), **every one carries the full 383 columns**. 46,953 total rows (inflated by combined+batch double-listing; dedup by address key at parse time). The importer (`data_axle_importer.py`) persists only ~25 of 383 columns. **Re-parse, do NOT re-download.**

**Current enrichment ceiling.** Only 2,981/13,818 watched NPIs (21.6%, all IL, MA=0%) carry any Data Axle data today. Raw files cover ~245/269 IL ZIPs; 0/21 MA ZIPs (Boston needs a separate export — out of scope for this pass, flagged as residual).

**Corporate-signal columns — verified exact headers, non-sentinel fill (whole corpus):**

| Header | idx | non-sentinel fill | imported today? | use |
|---|---:|---:|---|---|
| `Parent Company Name` | 1 | 692 (1.5%) | ✅ yes | E1 known-DSO/PE map |
| `EIN 1` | 109 | 11,102 (23.6%) | ✅ yes (no sentinel strip) | E3 EIN cluster |
| `EIN 2` | 110 | 3,010 (6.4%) | ❌ **NEW** | E3 EIN cluster |
| `EIN 3` | 111 | 822 (1.8%) | ❌ **NEW** | E3 EIN cluster |
| `Mailing Address` | 357 | 2,481 (5.3%) | ❌ **NEW** | E2 back-office cluster |
| `Mailing City/State/Zip Code` | 358-360 | 12,145 (25.9%) | ❌ **NEW** | E2 back-office cluster |
| `Legal Name` | 381 | 4,681 (10.0%) | ❌ **NEW** | E6 legal-entity reveal |
| `Subsidiary IUSA Number` | 107 | trace (sentinel-heavy) | ❌ **NEW** | E1 corporate-tree linkage |
| `Corporate Employee Size Actual` | 100 | 35 (0.1%) | ❌ **NEW** | E4 corporate-scale confirm |
| `Corporate Sales Volume Actual` | 102 | 35 (0.1%) | ❌ **NEW** | E4 corporate-scale confirm |
| `Executive First/Last/Title 1-10` | 141-178 | #1=92.6%…#10=0.3% | ❌ **NEW** (read transiently, never persisted) | E5 shared-officer cluster |
| `Franchise Description 1` | 88 | 32,311 (68.8%) | ✅ yes | corroboration |

**CLUSTERING POTENTIAL — proven across the corpus (distinct practice addresses sharing a signal):**
- **Parent Company:** ADMI CORP (28 addrs = Aspen), SONRAVA HEALTH (19), 1ST FAMILY DENTAL (13), WEBSTER DENTAL MANAGEMENT (9), KOS SERVICES (13), GRYPHON INVESTORS (12, PE), SHORE CAPITAL (8, PE), BERKSHIRE PARTNERS (6, PE). 10 parents span ≥3 addrs.
- **Shared mailing address:** 26 mailing addrs span ≥2 distinct practices, 10 span ≥3 (e.g. `1730 PARK ST 106, 60563` → 10 offices; `350 N CLARK ST 600, 60654` → 8). Classic stealth-DSO back-office.
- **Shared EIN (1/2/3):** 100 EINs span ≥2 addrs, 10 span ≥3.
- **Shared officer#1:** 742 officers across ≥2 addrs, 97 across ≥3.

**CORRECTION to the mission brief.** `Affiliated Records` (idx 376) / `Affiliated Locations` (idx 378) — the mission named these as a near-direct sibling-location count. **They are sentinel-empty** (≈0.02% real fill, sentinel "000000"). **Do NOT rely on them.** The sibling count is reconstructed instead from shared EIN/mailing/officer/parent clustering (above), which is richer and verifiable.

**NPPES Phase A is closed.** The B2 detector's TIN/authorized-official/mailing passes depend on 11 NPPES ownership columns that are 100% NULL. Backfilling them needs the 330-col full NPPES dissemination file (~30 GB uncompressed > 18 GB free) — disk-blocked. The cached dental snapshot (`nppes_dental_2026-03.csv`) has only 15 columns and lacks officer/mailing/TIN. **So Data Axle is the sole viable source for officer/mailing/secondary-EIN signals** — exactly this mission's lever.

## 1. Schema additions (`practices`, idempotent, BOTH DBs)

All new columns are **`da_`-prefixed** so Data Axle never silently overwrites an NPPES-sourced field (NPPES has no `da_*` columns; the existing `mailing_*`/`authorized_official_*` NPPES columns are left untouched — we write the parallel `da_mailing_*`). Provenance is preserved by construction.

| Column | Type | Source header | Sentinel rule |
|---|---|---|---|
| `da_ein2` | TEXT | EIN 2 | digits only; all-zero → NULL |
| `da_ein3` | TEXT | EIN 3 | digits only; all-zero → NULL |
| `da_mailing_address` | TEXT | Mailing Address | blank/nan → NULL |
| `da_mailing_city` | TEXT | Mailing City | blank/nan → NULL |
| `da_mailing_state` | TEXT | Mailing State | blank/nan → NULL |
| `da_mailing_zip` | TEXT | Mailing Zip Code | blank/nan → NULL |
| `da_legal_name` | TEXT | Legal Name | blank/nan → NULL |
| `da_subsidiary_iusa` | TEXT | Subsidiary IUSA Number | all-zero → NULL |
| `da_corporate_employees` | INTEGER | Corporate Employee Size Actual | all-zero/$0 → NULL |
| `da_corporate_sales` | INTEGER | Corporate Sales Volume Actual | all-zero/$0 → NULL |
| `da_officers` | TEXT (JSON) | Executive First/Last/Title 1-10 | JSON array of `{first,last,title}`, sentinel names dropped; NULL if empty |

`ein` (EIN 1), `parent_company`, `parent_iusa`, `iusa_number`, `franchise_name` already exist — kept. (EIN 1 gains sentinel-stripping in the shared extractor.)

## 2. Importer changes (`data_axle_importer.py`) — exact-match, fuzzy-free

The existing `detect_columns()` fuzzy matcher (`token_sort_ratio ≥ 80`) is **dangerous** for the new headers — "EIN 2" vs "EIN 1", "Mailing Address" vs "Address", "Executive … 1" vs "… 2" would cross-contaminate. So the corporate-signal block uses a **dedicated exact-match path**, decoupled from `FIELD_CANDIDATES`:

- `detect_corp_signal_columns(header) -> dict` — exact (case-insensitive, whitespace-collapsed) header→canonical map.
- `extract_corp_signals(row, colmap) -> dict` — pulls the new fields with sentinel filtering; builds `da_officers` JSON from exec slots 1-10 (dedupe by (last,first), drop sentinel/empty, keep title).
- Shared by BOTH the importer's `validate_record()` (attach to record) and the standalone backfill (DRY).
- `_collapse_cluster()`: first-non-NULL for scalars; **union** for `da_officers`.
- `upsert_doors_to_db()`: null-guarded persistence of all `da_*` (matched rows enrich only; never touch NPPES identity fields).
- `ensure_data_axle_columns()`: append the 11 `da_*` columns to `new_cols`.

This keeps the live importer correct for future manual DA runs (Data Axle is NOT in the weekly cron — manual workflow only).

## 3. Surgical backfill (`scrapers/backfill_data_axle_corporate_signals.py`)

The immediate enrichment of existing rows is done by a focused, additive, re-runnable script (mirrors the proven `backfill_ownership_cols` pattern) — **no synthetic rows, no `practice_changes` churn, no `entity_classification`/`ownership_status`/`buyability` writes**:

1. Re-parse all 184 on-disk files; dedup raw rows by normalized (address, zip5).
2. Build two signal maps: `loc_map[normaddr|zip5]` and `phone_map[phone10]` (reusing the importer's `normalize_address`/`normalize_phone`/`extract_corp_signals`). Merge: first-non-NULL scalars, officer union.
3. For every watched practice, look up loc_map (then phone_map fallback); UPDATE only the `da_*` columns (+ EIN 1/parent if currently NULL). Attach to **all** co-located NPIs at the matched (normaddr, zip5) so org + individual NPIs both carry the signal (location-level detection needs it on whichever NPI the detector keys on).
4. Apply to BOTH SQLite and (via sync) Supabase. Report coverage: rows touched, per-signal fill, IL/MA split.

Recall is measured after the first run; if location+phone key recall is weak, add a fuzzy fallback. Target: lift enriched corporate-signal coverage well above today's 2,981.

## 4. Detection (`scrapers/detect_corporate_clusters.py` B2 — extend)

Add four **DA-sourced** passes (the NPPES-dependent passes stay inert but harmless). Each emits candidates **with documentary evidence** (named field + value + corroborating-sibling count), location-aware (aggregate `da_*` across `practice_locations.provider_npis`):

- **B2-EIN:** EIN ∈ {ein, da_ein2, da_ein3} shared across **≥3 distinct watched locations** → corporate cluster. (Existing definitive criterion, now multi-EIN.)
- **B2-MAIL:** `da_mailing_address`+`da_mailing_zip` shared across **≥3 distinct practice addresses** (mailing ≠ own address) → back-office cluster. Out-of-area/PO-box weighted higher.
- **B2-OFFICER:** normalized officer (last,first) shared across **≥3 distinct-NAME practices** → shared back-office owner/manager. Excludes same-name family practices to avoid false positives.
- **B2-PARENT:** `parent_company` (or `da_legal_name`) matching a known DSO/PE platform, or `da_corporate_employees`/`da_corporate_sales` present (E4) → corporate. High precision.

B1 (`detect_name_chains.py`) gains da_ein2/3 + parent_company corroboration. B7 (PSC registry) re-runs unchanged. `build_flip_queue.py` re-runs to union all evidence into `flip_queue_b_union.json` with tiers (high/medium/low).

## 5. Verification (Phase 4) — free tools, no billed batch

The deterministic detectors produce candidates already carrying documentary evidence. Verification gate:
- **Adversarial agent fan-out:** independent verifier agents prompted to **REFUTE** each high/medium candidate; a candidate survives only if it retains a documented signal (named DA field + value + ≥N corroborating siblings).
- **Free WebSearch/WebFetch spot-check** on a representative sample (confirm the brand/parent/officer maps to a real DSO/PE platform).
- The **billed Phase C batch (`verify_flip_candidates.py`) is NOT run** — free session tools are the correct, zero-cost tool for sample verification. (If the user later wants the full billed sweep, it's available and budget-gated.)
- **Rule:** never auto-flip on a single weak signal. Multi-sibling structural clusters (≥3 shared EIN/mailing/officer addrs) and known-brand parents qualify; low-tier single-signal candidates do NOT.

## 6. Durable promotion + sync sequence

Survivors → `data/dso_research/il_dso_data_axle_verified.json` (new file, clean provenance tag `data_axle_structural_verified`). Extend `reclassify_verified_corporate_il.py` to union this file (alongside the merged + phasec files). Then:

```
reclassify_verified_corporate_il.py   # flips BOTH practices + practice_locations.entity_classification, recomputes zip_scores inline
merge_and_score.py                    # recomputes corporate_location_count FROM practice_locations (durability invariant)
_sync_floor_tables_only.py            # pushes zip_scores + practice_locations + dso_locations to Supabase (LIVE floor)
```

**Specialist DSOs (ortho/OMS/etc.) stay OUT of the GP floor denominator** — tracked separately, never inflate the GP floor.

**Durability:** flips land in `practice_locations.entity_classification`, which `merge_and_score` reads (not rebuilds) and `dedup_practice_locations.py` (not in refresh.sh) would rebuild — so the FLOOR CI guard's `expect_min` is bumped to the new minimum to catch any regression.

## 7. Definition-of-done proofs (produced at the end)

1. Before/after floor table (locations + %, CHI/BOS/ALL).
2. Evidence manifest: every flip → practice → DA field + value → corroborating siblings (no single-weak-signal flips).
3. Coverage accounting: columns added, rows enriched, per-signal fill, IL/MA residual.
4. Honest residual to the ADA per-dentist anchor — no fabricated middle number.
5. Durability proof: survives merge_and_score recompute path; FLOOR CI `expect_min` reflects new minimum.
6. Deployed both repos; `npm run build` + vitest green.
