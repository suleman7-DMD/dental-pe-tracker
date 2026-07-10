#!/usr/bin/env python3
"""
test_job_hunt_durability.py — Unit tests for the job_hunt_verification
survival hooks around the practice_locations full_replace (2026-07-09).

Background: job_hunt_verification.location_id has an FK →
practice_locations(location_id) — the ONLY FK dependent of practice_locations
(verified live 2026-07-09) — so the TRUNCATE ... CASCADE inside
_sync_full_replace wipes the 48-row job-hunt layer on every
practice_locations full_replace. The hooks under test make that lossless:

  _snapshot_job_hunt_seed          (best-effort export BEFORE the truncate)
  _restore_job_hunt_verification   (hard re-import + verify AFTER the replace)

Both CASCADE paths (weekly sync_to_supabase.py AND _sync_floor_tables_only.py)
run through _sync_full_replace, so hooking there covers both — tested here.

Tests use mocks and do NOT touch any real database.
Run:   python3 scrapers/test_job_hunt_durability.py

Exit 0 = all pass, Exit 1 = failures.
"""

import sys
import os
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap path + stub heavy imports (same pattern as test_sync_resilience.py)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))


def _make_stub(name):
    return types.ModuleType(name)


for stub_name in [
    "scrapers.database",
    "scrapers.pipeline_logger",
    "scrapers.logger_config",
    "dotenv",
]:
    sys.modules.setdefault(stub_name, _make_stub(stub_name))

db_mod = sys.modules["scrapers.database"]
for sym in ["get_session", "Practice", "Deal", "PracticeChange", "ZipScore",
            "WatchedZip", "DSOLocation", "ADAHPIBenchmark", "PESponsor",
            "Platform", "ZipOverview", "ZipQualitativeIntel", "PracticeIntel",
            "PracticeSignal", "ZipSignal", "PracticeLocation", "Base"]:
    if not hasattr(db_mod, sym):
        setattr(db_mod, sym, MagicMock())

pl_mod = sys.modules["scrapers.pipeline_logger"]
if not hasattr(pl_mod, "log_scrape_start"):
    pl_mod.log_scrape_start = MagicMock(return_value="t0")
    pl_mod.log_scrape_complete = MagicMock()
    pl_mod.log_scrape_error = MagicMock()
    pl_mod.LOG_FILE = "/dev/null"

lc_mod = sys.modules["scrapers.logger_config"]
import logging
if not hasattr(lc_mod, "get_logger"):
    lc_mod.get_logger = lambda name: logging.getLogger(name)

if "sqlalchemy" not in sys.modules:
    sa_mod = types.ModuleType("sqlalchemy")
    sa_mod.create_engine = MagicMock()
    sa_mod.text = lambda s: s
    sa_mod.inspect = MagicMock()
    sa_mod.or_ = lambda *args: args
    sa_mod.and_ = lambda *args: args
    sa_exc = types.ModuleType("sqlalchemy.exc")
    sa_exc.IntegrityError = Exception
    sa_orm = types.ModuleType("sqlalchemy.orm")
    sa_orm.sessionmaker = MagicMock()
    sys.modules["sqlalchemy"] = sa_mod
    sys.modules["sqlalchemy.exc"] = sa_exc
    sys.modules["sqlalchemy.orm"] = sa_orm

import importlib
sync_mod = importlib.import_module("scrapers.sync_to_supabase")
sync_mod.text = lambda s: s


# ---------------------------------------------------------------------------
# Fake session/engine helpers (mirrors test_sync_resilience.py)
# ---------------------------------------------------------------------------

def _make_fake_session(rows):
    q = MagicMock()
    q.all.return_value = rows
    q.filter.return_value = q
    q.order_by.return_value = q
    session = MagicMock()
    session.query.return_value = q
    return session


def _make_fake_engine(row_count=0):
    engine = MagicMock()
    conn = MagicMock()
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = row_count
    conn.execute.return_value = scalar_result
    conn.__enter__ = lambda self: self
    conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = conn
    begin_ctx = MagicMock()
    begin_ctx.__enter__ = lambda self: conn
    begin_ctx.__exit__ = MagicMock(return_value=False)
    engine.begin.return_value = begin_ctx
    return engine


def _run_full_replace(table, n_rows, engine, snapshot, restore):
    """Drive _sync_full_replace for `table` with hooks patched to the given mocks."""
    rows = [MagicMock() for _ in range(n_rows)]
    session = _make_fake_session(rows)
    config = {"table": table, "model": MagicMock(), "conflict_col": None}
    with patch.object(sync_mod, "_get_column_names", return_value=["a", "b"]), \
         patch.object(sync_mod, "_build_insert_sql", return_value="INSERT ..."), \
         patch.object(sync_mod, "_model_to_dict", return_value={"a": 1, "b": 2}), \
         patch.object(sync_mod, "_update_sync_state"), \
         patch.object(sync_mod, "_snapshot_job_hunt_seed", snapshot), \
         patch.object(sync_mod, "_restore_job_hunt_verification", restore), \
         patch.dict(sync_mod.MIN_ROWS_THRESHOLD, {table: 0}):
        return sync_mod._sync_full_replace(session, engine, config)


# ---------------------------------------------------------------------------
# Test 1 — hooks fire for practice_locations, in the right order
# ---------------------------------------------------------------------------

class TestHooksFireForPracticeLocations(unittest.TestCase):
    def test_snapshot_before_truncate_restore_after(self):
        """practice_locations full_replace must snapshot BEFORE engine.begin()
        (i.e., before the TRUNCATE CASCADE) and restore AFTER it."""
        engine = _make_fake_engine(row_count=10)
        order = []
        snapshot = MagicMock(side_effect=lambda *_: order.append("snapshot"))
        restore = MagicMock(side_effect=lambda *_: order.append("restore"))
        real_begin = engine.begin

        def _tracked_begin(*a, **k):
            order.append("truncate_txn")
            return real_begin(*a, **k)

        engine.begin = _tracked_begin

        result = _run_full_replace("practice_locations", 10, engine, snapshot, restore)

        self.assertEqual(result, 10)
        snapshot.assert_called_once_with(engine)
        restore.assert_called_once_with()
        self.assertEqual(order, ["snapshot", "truncate_txn", "restore"],
                         "snapshot must precede the TRUNCATE txn; restore must follow it")
        print("  PASS  practice_locations: snapshot → TRUNCATE txn → restore")

    def test_hooks_not_called_for_other_tables(self):
        """No other full_replace table may trigger the JHV hooks."""
        engine = _make_fake_engine(row_count=10)
        snapshot, restore = MagicMock(), MagicMock()
        _run_full_replace("zip_scores", 10, engine, snapshot, restore)
        snapshot.assert_not_called()
        restore.assert_not_called()
        print("  PASS  other tables (zip_scores): JHV hooks untouched")

    def test_restore_failure_propagates(self):
        """A failed restore must raise (fail the sync step loudly), not be swallowed."""
        engine = _make_fake_engine(row_count=10)
        snapshot = MagicMock()
        restore = MagicMock(side_effect=RuntimeError("live != seed"))
        with self.assertRaises(RuntimeError):
            _run_full_replace("practice_locations", 10, engine, snapshot, restore)
        print("  PASS  restore failure raises out of _sync_full_replace")

    def test_no_snapshot_when_replace_aborts_on_empty_source(self):
        """The 0-row abort fires BEFORE the snapshot hook — no seed churn on a no-op."""
        engine = _make_fake_engine(row_count=0)
        snapshot, restore = MagicMock(), MagicMock()
        result = _run_full_replace("practice_locations", 0, engine, snapshot, restore)
        self.assertEqual(result, 0)
        snapshot.assert_not_called()
        restore.assert_not_called()
        print("  PASS  0-row abort: hooks not invoked")


# ---------------------------------------------------------------------------
# Test 2 — _restore_job_hunt_verification hard-gates on the importer
# ---------------------------------------------------------------------------

class TestRestoreHardGates(unittest.TestCase):
    def _with_jhv_stub(self, jhv):
        return patch.dict(sys.modules, {"scrapers.import_job_hunt_verification": jhv})

    def _make_jhv(self, rows=None, problems=None, verify_rc=0):
        jhv = types.ModuleType("scrapers.import_job_hunt_verification")
        jhv.load_seed = MagicMock(return_value=rows if rows is not None else [{"location_id": "L1"}])
        jhv.validate = MagicMock(return_value=problems or [])
        jhv.write = MagicMock()
        jhv.verify = MagicMock(return_value=verify_rc)
        jhv.export = MagicMock()
        return jhv

    def test_happy_path_writes_then_verifies(self):
        jhv = self._make_jhv()
        with self._with_jhv_stub(jhv):
            sync_mod._restore_job_hunt_verification()
        jhv.write.assert_called_once()
        jhv.verify.assert_called_once()
        print("  PASS  restore: write then verify on the seed rows")

    def test_seed_validation_problems_raise_before_write(self):
        jhv = self._make_jhv(problems=["L1: bad verification_status"])
        with self._with_jhv_stub(jhv):
            with self.assertRaises(RuntimeError):
                sync_mod._restore_job_hunt_verification()
        jhv.write.assert_not_called()
        print("  PASS  restore: invalid seed raises, nothing written")

    def test_verify_mismatch_raises(self):
        jhv = self._make_jhv(verify_rc=1)
        with self._with_jhv_stub(jhv):
            with self.assertRaises(RuntimeError):
                sync_mod._restore_job_hunt_verification()
        print("  PASS  restore: live != seed after re-import raises")


# ---------------------------------------------------------------------------
# Test 3 — _snapshot_job_hunt_seed is best-effort
# ---------------------------------------------------------------------------

class TestSnapshotBestEffort(unittest.TestCase):
    def test_export_failure_does_not_raise(self):
        """A failed pre-truncate export must warn and continue (repo seed is the
        fallback), never block the sync."""
        engine = _make_fake_engine(row_count=48)
        jhv = types.ModuleType("scrapers.import_job_hunt_verification")
        jhv.export = MagicMock(side_effect=OSError("disk full"))
        with patch.dict(sys.modules, {"scrapers.import_job_hunt_verification": jhv}):
            sync_mod._snapshot_job_hunt_seed(engine)  # must not raise
        print("  PASS  snapshot: export failure swallowed (best-effort)")

    def test_empty_live_table_skips_export(self):
        """If live JHV is empty/missing (already wiped), the export must be
        skipped so a good repo seed is not clobbered with nothing."""
        engine = _make_fake_engine(row_count=0)
        jhv = types.ModuleType("scrapers.import_job_hunt_verification")
        jhv.export = MagicMock()
        with patch.dict(sys.modules, {"scrapers.import_job_hunt_verification": jhv}):
            sync_mod._snapshot_job_hunt_seed(engine)
        jhv.export.assert_not_called()
        print("  PASS  snapshot: empty live table → seed preserved, no export")


# ---------------------------------------------------------------------------
# Test 4 — the surgical floor sync path inherits the hooks
# ---------------------------------------------------------------------------

class TestFloorSyncPathCovered(unittest.TestCase):
    def test_floor_sync_reuses_patched_full_replace(self):
        """_sync_floor_tables_only must route practice_locations through the SAME
        _sync_full_replace that carries the JHV hooks (no parallel copy)."""
        floor_mod = importlib.import_module("scrapers._sync_floor_tables_only")
        self.assertIn("practice_locations", floor_mod.TABLES)
        self.assertIs(floor_mod._sync_full_replace, sync_mod._sync_full_replace)
        print("  PASS  _sync_floor_tables_only routes through the hooked _sync_full_replace")


if __name__ == "__main__":
    print("job_hunt_verification durability tests\n" + "=" * 50)
    result = unittest.main(exit=False, verbosity=0).result
    sys.exit(0 if result.wasSuccessful() else 1)
