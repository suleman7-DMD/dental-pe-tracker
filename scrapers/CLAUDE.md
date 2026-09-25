# scrapers/ — Pipeline Code Guide

> **Keep this file short** — it is re-injected after every auto-compaction once any file in
> `scrapers/` is read. Project-wide rules, numbers, and routing live in the root `../CLAUDE.md`.
> Slimmed 2026-09-25 (23k → ~4k chars); the full verbatim prior version is `CLAUDE_ARCHIVE.md` in
> this directory. Use skill `scraper-dev` when modifying a scraper; `dental-pe-supabase-sync-and-orm`
> for anything sync/ORM.

## Scraper contract

- Import `scrapers.pipeline_logger`; call `log_scrape_start()` / `log_scrape_complete()` in `run()`. **Every `return` after `log_scrape_start()` must call `log_scrape_complete()` first** (else phantom "running" status). Put it in `finally` for scrapers with hard timeouts.
- `log_scrape_error(source, error, start_time)` — that argument order, not `(source, start_time, error)`.
- Wrap DB work in `try/except/finally`: `except` → `log_scrape_error` + re-raise; `finally` → `session.close()`.
- Logging via `scrapers.logger_config.get_logger("scraper_name")`.
- New columns: `Base.metadata.create_all()` does NOT alter existing tables — explicit `ALTER TABLE` on SQLite AND Supabase, and map it in the ORM (`database.py`) or full_replace syncs silently drop it.

## Data-integrity gotchas

- Use `insert_or_update_practice()` / `insert_deal()` — never raw INSERT. Never DELETE from `practices`.
- **`insert_deal()` dedup is asymmetric:** Python checks 5 fields (platform, date, source, target, state); the DB unique index `uix_deal_no_dup` covers 3 (platform, target, date). Multi-state deals hit the constraint — per-row `begin_nested()` savepoints in the sync handle it; don't "fix" by tightening Python dedup.
- **NPPES taxonomy:** only prefix `1223` is Dentist. Never `1224` (denturist), `124Q` (hygienist), `1268` (assistant) — F32 purged 20k leaked rows.
- **CASCADE trap:** `TRUNCATE practices CASCADE` wipes `practice_changes` (and intel/signals). The sync resets `practice_changes` sync_metadata afterward; adding a new FK to `practices` requires updating that reset.
- `database.normalize_punctuation()` maps curly quotes → ASCII at the GDN/PESP boundary (F19) so "Smith’s" and "Smith's" dedupe.
- `_normalize_address_for_grouping` (STE→SUITE, directionals, street types) drives `deduplicate_practices_in_zip()`.
- **Classifier ordering:** `non_clinical` runs before DSO matching; ambiguous keywords (`MANAGEMENT GROUP/COMPANY/SERVICES`) skip non_clinical when the name also has dental keywords. Every location match (PE or not) must set `classification_confidence` + `classification_reasoning`. `dso_classifier` Pass 3 only fills `entity_classification IS NULL` — no `--force` in `refresh.sh`.
- Raw-SQL flip scripts must bump `updated_at`; promotions/demotions need an evidence JSON in `data/dso_research/`.
- Adding a deal type → also add it to `DEAL_TYPE_COLORS` + the sidebar filter in `dashboard/app.py`.

## Per-scraper invariants (April 2026 audit — do not regress)

- `refresh.sh::run_step()` reaps with `pkill -TERM -P $bgpid` (then `-KILL`) — plain `kill` orphans the python child behind `tee`.
- `pesp_scraper.py` — DNS/HTTP retry with backoff + 40+ `COMMENTARY_PATTERNS` prefilter.
- `gdn_scraper.py` — `MAX_RETRIES=3`, `_is_roundup_link()` guard, `_PASS_THROUGH_SET`, `_DEAL_VERB_SET`, `_PARTNERS_VERB_NEXT={"with","to","and"}` (F21).
- `adso_location_scraper.py` — `HTTP_TIMEOUT=(10,30)`, `MAX_SECONDS_PER_DSO=300`, `MAX_SECONDS_TOTAL=1500`, `log_scrape_complete()` in `finally`; 14/18 DSOs are `needs_browser` (skipped without Playwright); delete-then-reinsert is per `dso_name` and gated on a non-aborted run.
- `sync_to_supabase.py` — `deals` uses `incremental_updated_at` (not `incremental_id`), so dedup fixes must land in both incremental paths; `MIN_ROWS_THRESHOLD` floors; post-sync `_verify_table_count()`.
- `ada_hpi_benchmarks` freshness: check which timestamp column is populated before wiring a freshness query (`created_at` is the reliable one).
- `weekly_research.py` — `validate_dossier()` gate before store; `DRIFT_REMAP` coerces `verification_quality` drift, off-spec values quarantine (F33).

## Tests

```bash
python3 -m pytest scrapers/test_sync_resilience.py scrapers/test_gdn_parser.py
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" scrapers/<file>.py   # quick syntax check
```
