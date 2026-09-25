# Dental PE Intelligence Platform — Claude Code Guide

> **Keep this file short.** It loads at every session start AND is re-injected after every
> auto-compaction, so every KB here is paid over and over. Dated session logs, ship logs, and
> handoffs belong in `data/dso_research/RESEARCH_HOME/` or repo-root handoff docs — not here.
> Slimmed 2026-09-25 (71k → ~10k chars). Verbatim prior versions: `CLAUDE_ARCHIVE_2026-09.md`
> (everything through 2026-07-09, incl. all dated banners) and `CLAUDE_ARCHIVE.md` (April 2026).

## Route first — load the skill before acting

| Task | Load / read |
|------|-------------|
| Anything touching `ownership_tier`, census tiers T1–T6, Lane A, holds, `consolidate_census.py` | skill `dental-pe-census-operating-protocol`, then `data/dso_research/RESEARCH_HOME/SESSION_PROTOCOL_FABLE_PM_20260702.md` |
| Quoting ANY count or % | skill `dental-pe-data-unit-discipline`; run `python3 .claude/skills/dental-pe-skill-drift-check/check_claims.py` (read-only). A fresh query beats any number in this file |
| Any SQLite→Supabase sync, ORM column change, `refresh.sh` | skill `dental-pe-supabase-sync-and-orm` |
| Weird counts / "why is X labeled Y" / failing CI floor | skill `dental-pe-failure-archaeology` |
| Before saying done/fixed/verified, or committing | skill `dental-pe-validation-and-qa` |
| Resuming a major workstream | skill `dental-pe-plans` |
| Frontend ownership display | `RESEARCH_HOME/SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md` §2 (binding truth rules); canonical module `dental-pe-nextjs/src/lib/census/ownership-truth.ts` — reconcile against it, never rebuild it |
| Scrapers / Streamlit / Data Axle / pipeline failures | skills `scraper-dev`, `dashboard-dev`, `data-axle-workflow`, `debug-pipeline` |

Newest work-in-progress handoffs live at repo root (e.g. `OFFICE_CENSUS_HANDOFF_2026-09-24.md`,
`DIRECTORY_RECOVERY_PLAN_2026-09-20.md`) — `ls -t *.md | head` finds the latest.

## Standing directives

1. **Boston (MA) is parked.** Work Chicagoland/IL only. MA rows (21 ZIPs, 362 GP locations) stay in the DB and app as-is — don't investigate, classify, or delete them.
2. **Two separate ownership axes — never merge them.**
   - **Census** `practice_locations.ownership_tier` (T1–T6, hand-verified with evidence URLs) is the ONLY ownership truth layer. `census_review_status` (`held`/`undetermined`/NULL) is Review-Desk metadata, not a tier; a tier always wins.
   - **Detector floor** = `entity_classification IN (dso_regional, dso_national)` — a documented FLOOR, not the consolidation rate. ADA HPI (IL 14.6%, MA 14.9%) is a per-DENTIST anchor, a different unit. Never present the floor as "the consolidation rate"; never invent a precise number between floor and anchor (frontend band: `consolidation-honesty.ts` `getCorporateBand`).
3. **Census columns are ORM-mapped in `scrapers/database.py` — never remove them** (re-opens a silent sync-strip bug). `consolidate_census.py` writes only with `--allow-db-write` and rejects non-http(s) evidence URLs. Back up the DB before any census write.
4. **Never run `sync_to_supabase.py --tables practices` alone** — `TRUNCATE practices CASCADE` wipes `practice_changes`/`practice_intel`/`practice_signals`. Use the surgical scripts (`_sync_floor_tables_only.py`, `_sync_census_columns_practices.py`, `_sync_practices_changed_rows.py`) and read back Supabase afterward. `_sync_practices_changed_rows.py` does NOT carry census columns.
5. **CI floors** (`scripts/check_data_invariants.py`): `FLOOR` ≥268, `FLOOR_NPI` ≥1152, `CENSUS` ≥3692, `CENSUS_NPI` ≥8133. A drop means something reverted work — an incident, not doc debt. A downward re-base is legal only with an evidence JSON documenting the demotions.
6. Raw-SQL flip scripts MUST bump `updated_at`. Commit/push only when the user asks.

## What this project is

Pipeline + dashboards tracking PE consolidation in US dentistry: scrapes deal announcements, monitors federal NPPES dental NPI records, classifies ownership, scores markets. Primary metro Chicagoland (269 IL ZIPs); Boston (21 MA ZIPs) parked; 290 watched ZIPs total.

- **Next.js (primary):** dental-pe-nextjs.vercel.app — `dental-pe-nextjs/` (own CLAUDE.md)
- **Streamlit (legacy):** suleman7-pe.streamlit.app — `dashboard/app.py`, still `ownership_status`-primary
- **Repo:** github.com/suleman7-DMD/dental-pe-tracker. Push to `main` auto-deploys Vercel + Streamlit.

```
Federal/Web → scrapers/ (Python) → SQLite data/dental_pe_tracker.db → sync_to_supabase.py → Supabase → Next.js
                                                                    ↘ gzip → git push → Streamlit Cloud
```

## Numbers — units matter (drift-checked 2026-09-25)

NPPES emits one NPI per provider AND per organization at the same address, so NPI rows ≈ 2.4× real clinics. Say "NPI records," never "practices," for NPI counts. Headline KPIs use the **GP-location** denominator.

| Value | Unit | Source |
|------:|------|--------|
| 383,321 | NPI rows, global | `COUNT(*) FROM practices` (real US establishments ≈137k) |
| 13,860 | NPI rows, 290 watched ZIPs | `practices` ⋈ `watched_zips` |
| 5,657 | location rows, watched, all classes | `practice_locations` (UI excludes 179 `da_unverified` + 5 `duplicate_location`) |
| **4,801** | GP locations, watched (IL 4,439 + MA 362) | `SUM(zip_scores.total_gp_locations)` — headline denominator |
| **268** | corporate GP locations → **5.58% floor** | `zip_scores.corporate_location_count` (CHI 249/4,439 = 5.61%) |
| 1,158 | corporate NPI rows → 8.36% | NPI unit — only for "dentists working at corporate" |
| **3,692 / 4,439 = 83.17%** | IL GP locations with a census tier | `ownership_tier IS NOT NULL`; 747 remain (researched-inconclusive re-research pool) |
| 543 | deals | `deals` (column is `source`, not `data_source`) |

The floor is recomputed weekly FROM `practice_locations.entity_classification` (`merge_and_score.py`), which nothing in `refresh.sh` rebuilds — promotions survive refreshes. Dentagraphics' IL 3,961 has no disclosed methodology: don't claim we match it or that it's right.

## Database (SQLite, pipeline) — key tables

- `practices` — PK `npi`. `entity_classification` = canonical detector signal. **Never DELETE from `practices`.**
- `practice_locations` — address-deduped, PK `location_id`, joined via `practice_to_location_xref`. All headline location KPIs + census columns (`ownership_tier`, `census_review_status`, …) live here.
- `zip_scores` (290), `watched_zips` (290), `deals`, `practice_changes`, `dso_locations` (overlay only — does NOT feed the floor), `ada_hpi_benchmarks`, `practice_signals`, `zip_signals`, `practice_intel`, `zip_qualitative_intel`.
- `Base.metadata.create_all()` does NOT alter existing tables — new columns need explicit `ALTER TABLE` on BOTH SQLite and Supabase.

**Sync strategies:** `deals` = `incremental_updated_at`; `practices` = `watched_zips_only` (TRUNCATE CASCADE — directive 4); `practice_changes` = `incremental_id`; most others `full_replace`. Incremental paths use per-row `begin_nested()` savepoints (for the `uix_deal_no_dup` index).

## Entity classification (13 values)

Priority: non_clinical > specialist > dso_national > corporate signals > family_practice > large_group > small_group > solo variants.

- **Independent (7):** solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group
- **Corporate:** dso_regional, dso_national
- **Specialist:** specialist (taxonomy 1223D/E/P/S/X, or ortho/perio/endo/OMS/pedo/prostho name keywords)
- **Non-clinical:** non_clinical
- **Unknown / excluded:** `org_only_npi` (NPI-row only), `da_unverified` (Data-Axle synthetic `DA_` rows — excluded from EVERY denominator), `duplicate_location` (excluded everywhere)

Only NPPES taxonomy prefix `1223` is Dentist (never `1224`, `124Q`, `1268`).

## Critical rules

**Pipeline**
- Every scraper uses `scrapers.pipeline_logger` (`log_scrape_start`/`log_scrape_complete`; every early return after start must log complete) and `scrapers.logger_config.get_logger()`.
- `refresh.sh` wraps steps in `run_step()` (reaps descendants with `pkill -P`); one failing step doesn't kill the run.
- Schedules are **launchd agents**, not crontab: `com.dental-pe.weekly-refresh` (Sun 8am → `scrapers/refresh.sh`) and `com.dental-pe.nppes-refresh` (monthly NPPES, 6am). Events log to `logs/pipeline_events.jsonl`.
- `database.py` auto-decompresses `.db.gz` for Streamlit Cloud — never remove that.

**Data integrity**
- Use `insert_or_update_practice()` / `insert_deal()` — never raw INSERT.
- Consolidation % denominators are total GP locations, never `classified_count`. Label "Known Corporate"/"Known Consolidated"; show unknowns when >30%.

**Next.js** (details in `dental-pe-nextjs/CLAUDE.md`)
- `entity_classification` primary, `ownership_status` fallback only when NULL (F27 vitest enforces); `classifyPractice()` is the canonical helper.
- Supabase returns max 1000 rows — paginate with `.range()`.
- Run `npm run build` in `dental-pe-nextjs/` after every change.

**AI research layer** (`research_engine.py`, `weekly_research.py`, `practice_deep_dive.py`, `qualitative_scout.py`)
- Never fabricate — null + `_source_url="no_results_found"` when search finds nothing. 4-layer gate: forced web_search, per-claim source URLs, terminal `verification` block, `validate_dossier()` quarantine. `evidence_quality` ∈ {verified, partial, insufficient} exactly.
- Cost: plan ~$0.008/practice (batch). Trust the Anthropic console, not `poll.py` totals (~10× overcount).
- `research_engine.py` uses raw `requests`, not the `anthropic` SDK.

## Key commands

```bash
python3 .claude/skills/dental-pe-skill-drift-check/check_claims.py   # verify numbers (read-only)
python3 scripts/check_data_invariants.py                              # CI floors
python3 pipeline_check.py                                             # pipeline health
cd dental-pe-nextjs && npm run build && npx vitest run                # frontend gates
python3 -m pytest scrapers/test_sync_resilience.py scrapers/test_gdn_parser.py
```

Historical audit docs (only when needed): `CLAUDE_ARCHIVE_2026-09.md`, `CLAUDE_ARCHIVE.md`, `SCRAPER_AUDIT_STATUS.md`, `RECONCILIATION_VERDICT_2026_04_26.md`, `NPI_VS_PRACTICE_AUDIT.md`, `AUDIT_REPORT_2026-04-26_FULL.md`.
