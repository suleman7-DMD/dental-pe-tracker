# Qualitative Intelligence Integration — Consensus Implementation Plan

**Date:** 2026-03-15
**Status:** APPROVED (deep audit + independent rebuttal + evidence-based resolution, both sides aligned on all 14 items)
**Scope:** Python pipeline integration only. Frontend React components are a separate future session.
**Audit trail:** `.claude/plans/jiggly-squishing-orbit.md` (full audit report, rebuttal, verification agent findings)

## Context

Six Python files implementing an AI-powered qualitative research layer were built in isolation and placed in the project root. They need to be integrated into the `scrapers/` pipeline package with fixes identified during a deep audit and subsequent rebuttal exchange between the auditor (Claude Code) and the original code author.

The audit found 16 potential fixes. After rebuttal and evidence-based verification (3 investigation agents deployed), both sides agreed on 14 items. Two items were removed as overengineered for v1.

## CRITICAL REQUIREMENT

`sync_to_supabase.py` requires SQLAlchemy model classes for every synced table. It uses `sqlite_session.query(model).all()` (line 344) and `inspect(model_class)` (line 183-186) for column discovery. Raw sqlite3 tables CANNOT sync. The SQLAlchemy rewrite is NOT optional — proven by @sync-mechanism-verifier agent reading every line of the sync script.

## Key Decisions (All Resolved)

| Decision | Answer | Rationale |
|---|---|---|
| SQLAlchemy rewrite of intel_database.py | **YES** | sync_to_supabase.py requires ORM models — proven by code inspection |
| Model location | **scrapers/database.py** | One Base, one create_all(), consistent with Practice/Deal/ZipScore |
| CRUD function location | **scrapers/intel_database.py** (rewritten) | Models define schema; CRUD is business logic. Uses get_session() from database.py |
| Pipeline events sync gap | **Separate task** | Pre-existing gap affecting all scrapers. System Health 80% functional (only pipeline log viewer dark) |
| Frontend components | **Separate session** | Two separate git repos (dental-pe-tracker vs dental-pe-nextjs). Pipeline first. |
| Escalation bug fix | **Guard clause** | `if readiness in ("unlikely", "unknown"): return False` — preserves OR logic for valid targets |
| Cache TTL | **Flat 90 days for v1** | Tiered TTL rejected: 6x cost increase ($60/yr → $377/yr) for marginal signal freshness |

## File Structure After Integration

```
scrapers/database.py            — All models (existing + ZipQualitativeIntel, PracticeIntel) + Base + get_session()
scrapers/intel_database.py      — store_zip_intel(), get_zip_intel(), is_cache_fresh(), etc.
                                  (REWRITTEN: uses get_session() from database.py, not raw sqlite3)
scrapers/research_engine.py     — API client (moved from root, escalation guard + circuit breaker added)
scrapers/qualitative_scout.py   — ZIP CLI (moved from root, SQL injection fixed, pipeline_logger added)
scrapers/practice_deep_dive.py  — Practice CLI (moved from root, pipeline_logger added)
scrapers/weekly_research.py     — Automation runner (moved from root, --retrieve implemented, pipeline_logger added)
```

**Deleted:** `dashboard_intel.py` (Streamlit-specific, replaced by React), `INTEGRATION_GUIDE.md` (superseded by this document)

---

## PHASE 1 — Schema & Models (Do First)

**Files modified:** `scrapers/database.py`, `scrapers/intel_database.py`, `scrapers/schema_postgres.sql`, `scrapers/sync_to_supabase.py`

### 1. Add SQLAlchemy models to `scrapers/database.py` (~80 lines)

Add `ZipQualitativeIntel` model (~40 lines):
- PK: `zip_code` (TEXT), FK to watched_zips.zip_code
- 30+ columns matching current intel_database.py CREATE TABLE schema
- Add `updated_at` DateTime column
- JSON fields stay as Text columns (stored as JSON strings, consistent with existing practice)

Add `PracticeIntel` model (~40 lines):
- PK: `npi` (TEXT), FK to practices.npi
- 40+ columns matching current intel_database.py CREATE TABLE schema
- Add `escalation_findings` TEXT column (caught by auditor — missing from original)
- Add `updated_at` DateTime column

### 2. Rewrite `intel_database.py` CRUD to use SQLAlchemy sessions

- Replace `sqlite3.connect()` with `from scrapers.database import get_session`
- `store_zip_intel()` → `session.merge()` instead of `INSERT OR REPLACE`
- `get_zip_intel()` → `session.query(ZipQualitativeIntel).get(zip_code)`
- `store_practice_intel()` → `session.merge()`
- `get_practice_intel()` → `session.query(PracticeIntel).get(npi)`
- Remove `ensure_intel_tables()` — replaced by `Base.metadata.create_all()`
- **BUG FIX:** Define `DEFAULT_CACHE_TTL_DAYS = 90` at module top (currently undefined → ImportError)
- Keep `is_cache_fresh()`, `get_all_zip_intel()`, `get_researched_practice_npis()` — rewrite to use sessions

Estimated delta: ~150 lines changed, ~100 lines removed (raw SQL strings)

### 3. Add tables to `scrapers/schema_postgres.sql` (~60 lines)

CREATE TABLE statements for both intel tables, matching SQLAlchemy models. Include indexes on research_date.

### 4. Add to `scrapers/sync_to_supabase.py` SYNC_CONFIG (~10 lines)

```python
{"table": "zip_qualitative_intel", "model": ZipQualitativeIntel, "strategy": "full_replace"},
{"table": "practice_intel", "model": PracticeIntel, "strategy": "full_replace"},
```

Import models: `from scrapers.database import ZipQualitativeIntel, PracticeIntel`

### 5. Create Supabase Postgres tables

Run the new CREATE TABLE SQL from schema_postgres.sql in Supabase SQL editor (existing pattern — no automated migration tooling).

---

## PHASE 2 — Code Quality & File Move

**Files modified:** All 5 Python files being moved to `scrapers/`

### 6. Fix SQL injection in `qualitative_scout.py:93`

```python
# BEFORE (vulnerable f-string interpolation):
query += f" AND wz.metro_area LIKE '{pattern}'"

# AFTER (parameterized):
query += " AND wz.metro_area LIKE ?"
# Add pattern to params tuple
```

Note: After SQLAlchemy rewrite, this may become a `session.query().filter()` call instead. Fix whichever pattern exists after Phase 1.

### 7. Fix escalation guard in `research_engine.py:229`

```python
def _should_escalate(self, r):
    readiness = r.get("readiness", r.get("acquisition_readiness", "unknown"))
    if readiness in ("unlikely", "unknown"):
        return False  # Never escalate non-targets
    confidence = r.get("confidence", "low")
    greens = r.get("green_flags", [])
    if readiness in ("high", "medium") and confidence != "high":
        return True
    if len(greens) >= 3:
        return True
    return False
```

### 8. Add pipeline_logger to CLI scripts

In `qualitative_scout.py`, `practice_deep_dive.py`, and `weekly_research.py`:

```python
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error
```

Call `log_scrape_start("qualitative_scout")` at entry, `log_scrape_complete()` at exit, `log_scrape_error()` on failure.

### 9. Replace `logging.basicConfig()` with `get_logger()` in all 5 files

```python
from scrapers.logger_config import get_logger
logger = get_logger("research_engine")  # or "qualitative_scout", etc.
```

### 10. Move files from root to `scrapers/`, remove `sys.path.insert()` hacks

Move: `research_engine.py`, `intel_database.py`, `qualitative_scout.py`, `practice_deep_dive.py`, `weekly_research.py`

Delete originals from root. Also delete `dashboard_intel.py` and `INTEGRATION_GUIDE.md`.

Remove from each file:
```python
# DELETE THIS LINE:
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### 11. Implement `--retrieve <batch_id>` in `weekly_research.py`

Add argparse argument and handler. Call `engine.check_batch(batch_id)`, if complete call `engine.get_batch_results(batch_id)`, then store each result via `store_zip_intel()` or `store_practice_intel()` based on the `custom_id` prefix (zip_ or practice_).

---

## PHASE 3 — Pipeline Integration (Do After Testing)

### 12. Add to `scrapers/refresh.sh`

```bash
run_step "[9/N] Weekly qualitative research..." "$PYTHON $PROJECT/scrapers/weekly_research.py --budget 5"
```

Insert after merge_and_score, before sync_to_supabase.

### 13. Add circuit breaker to `research_engine.py`

Track consecutive failures. After 3 consecutive API errors, abort remaining items and log error. Prevents 290 items x 120s timeout = 9.6 hours of waiting if Anthropic is down.

---

## Critical Files & Estimated Changes

| File | Action | Lines Changed |
|---|---|---|
| `scrapers/database.py` (542 → ~620) | Add 2 SQLAlchemy models | +80 |
| `intel_database.py` (414 → ~300) | Rewrite CRUD to SQLAlchemy sessions | ~150 changed, ~100 removed |
| `research_engine.py` (388) | Fix escalation guard, add circuit breaker | ~15 |
| `qualitative_scout.py` (380) | Fix SQL injection, add pipeline_logger, get_logger | ~15 |
| `practice_deep_dive.py` (577) | Add pipeline_logger, get_logger | ~10 |
| `weekly_research.py` (243) | Add pipeline_logger, implement --retrieve | ~40 |
| `scrapers/sync_to_supabase.py` (451) | Add 2 SYNC_CONFIG entries + imports | ~10 |
| `scrapers/schema_postgres.sql` (260) | Add 2 CREATE TABLE statements | ~60 |
| `scrapers/refresh.sh` (76) | Add 1 run_step() | ~2 |
| `dashboard_intel.py` | DELETE | -546 |
| `INTEGRATION_GUIDE.md` | DELETE | -superseded |

## Existing Functions to Reuse

- `scrapers/database.py:get_session()` — session factory for all CRUD operations
- `scrapers/database.py:get_engine()` — dual-mode SQLite/Postgres engine
- `scrapers/database.py:Base` — declarative base for new models
- `scrapers/database.py:insert_or_update_practice()` — pattern for session.merge() upserts
- `scrapers/pipeline_logger:log_scrape_start/complete/error()` — structured event logging
- `scrapers/logger_config:get_logger()` — centralized logger factory
- `scrapers/sync_to_supabase.py:_sync_full_replace()` — sync pattern for small reference tables
- `scrapers/refresh.sh:run_step()` — error-tolerant pipeline step wrapper

## Verification Plan

1. **Schema:** `python3 -c "from scrapers.database import init_db; init_db()"` — new tables created in SQLite
2. **CRUD:** `python3 scrapers/qualitative_scout.py --zip 60491` then `--report 60491` — data stored
3. **Batch test:** Research 3 ZIPs (60491, 60439, 60441) and 3 practices
4. **Sync:** `python3 scrapers/sync_to_supabase.py` — verify data appears in Supabase
5. **Supabase SQL:** `SELECT * FROM zip_qualitative_intel` — rows present
6. **Pipeline check:** `python3 pipeline_check.py` — no regressions
7. **Logger:** Check `logs/pipeline_events.jsonl` for intel script events
8. **Cost:** Compare actual API costs against estimates ($0.008-0.014/ZIP actual vs $0.04-0.06 budgeted)

## Budget

- Phase 1: $0 (code changes only)
- Phase 2 testing: ~$0.30 (3 ZIPs + 3 practices)
- Phase 3 sync: $0 (no API calls)
- **Total: under $1**

## Backlog (Separate Sessions)

- [ ] Fix pipeline_events JSONL → Supabase sync (pre-existing gap, all scrapers affected, System Health page pipeline log viewer is dark but other sections work)
- [ ] Build React/TypeScript frontend components in dental-pe-nextjs/ (needs: `src/lib/supabase/queries/intel.ts`, TypeScript interfaces, React components for Market Intel/Job Market/Buyability pages)
- [ ] Add state dental board license lookup signal (v2 feature)
- [ ] Add retry logic with exponential backoff for weekly automation (v2 robustness)

## What Was Removed From Original Audit (And Why)

| Removed Item | Reason | Who Conceded |
|---|---|---|
| CostTracker atomic writes | Overkill for single-user JSON; Anthropic dashboard is authoritative | Auditor |
| PRAGMA foreign_keys | Writers are controlled code; Postgres enforces natively | Auditor |
| Tiered cache TTL | 6x cost increase ($60/yr → $377/yr) for marginal freshness | Auditor |
| Confidence degradation model | Premature for v1 | Auditor |
| New patient wait time signal | Not feasible via web search | Auditor |
