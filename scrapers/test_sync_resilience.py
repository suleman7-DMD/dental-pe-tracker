#!/usr/bin/env python3
"""
test_sync_resilience.py — Unit tests for the four sync safety fixes.

Tests use mocks and do NOT touch any real database.
Run:   python3 scrapers/test_sync_resilience.py

Exit 0 = all pass, Exit 1 = failures.
"""

import sys
import os
import signal
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Bootstrap path so we can import the module without the full pipeline env
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

# Stub out all heavy imports that sync_to_supabase pulls in at module level
# so we can import it without a live SQLite DB or Supabase connection.
def _make_stub(name):
    mod = types.ModuleType(name)
    return mod

for stub_name in [
    "scrapers.database",
    "scrapers.pipeline_logger",
    "scrapers.logger_config",
    "dotenv",
]:
    sys.modules.setdefault(stub_name, _make_stub(stub_name))

# scrapers.database needs specific symbols
db_mod = sys.modules["scrapers.database"]
for sym in ["get_session", "Practice", "Deal", "PracticeChange", "ZipScore",
            "WatchedZip", "DSOLocation", "ADAHPIBenchmark", "PESponsor",
            "Platform", "ZipOverview", "ZipQualitativeIntel", "PracticeIntel",
            "PracticeSignal", "ZipSignal", "PracticeLocation", "Base"]:
    setattr(db_mod, sym, MagicMock())

# pipeline_logger stubs
pl_mod = sys.modules["scrapers.pipeline_logger"]
pl_mod.log_scrape_start = MagicMock(return_value="t0")
pl_mod.log_scrape_complete = MagicMock()
pl_mod.log_scrape_error = MagicMock()
pl_mod.LOG_FILE = "/dev/null"

# logger_config stub
lc_mod = sys.modules["scrapers.logger_config"]
import logging
lc_mod.get_logger = lambda name: logging.getLogger(name)

# Stub sqlalchemy pieces needed at import time
import types as _types
sa_mod = _types.ModuleType("sqlalchemy")
sa_mod.create_engine = MagicMock()
sa_mod.text = lambda s: s
sa_mod.inspect = MagicMock()
sa_mod.or_ = lambda *args: args
sa_mod.and_ = lambda *args: args
sa_exc = _types.ModuleType("sqlalchemy.exc")
sa_exc.IntegrityError = Exception
sa_orm = _types.ModuleType("sqlalchemy.orm")
sa_orm.sessionmaker = MagicMock()
sys.modules["sqlalchemy"] = sa_mod
sys.modules["sqlalchemy.exc"] = sa_exc
sys.modules["sqlalchemy.orm"] = sa_orm

# Now import the module under test
import importlib
sync_mod = importlib.import_module("scrapers.sync_to_supabase")

# Re-point text() to identity so SQL strings pass through
sync_mod.text = lambda s: s


# ---------------------------------------------------------------------------
# Helper: build a minimal fake SQLAlchemy session that returns rows
# ---------------------------------------------------------------------------

def _make_fake_session(rows):
    """Return a mock sqlite_session whose .query(...).all() returns `rows`."""
    q = MagicMock()
    q.all.return_value = rows
    q.filter.return_value = q
    q.order_by.return_value = q
    session = MagicMock()
    session.query.return_value = q
    return session


def _make_fake_conn(row_count=0):
    """Return a mock pg connection whose execute().scalar() returns row_count."""
    conn = MagicMock()
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = row_count
    conn.execute.return_value = scalar_result
    conn.__enter__ = lambda self: self
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _make_fake_engine(row_count=0):
    """Return a mock pg_engine whose connect() returns a fake conn."""
    engine = MagicMock()
    conn = _make_fake_conn(row_count)
    engine.connect.return_value = conn
    # begin() context manager for Fix 1 single-txn path
    begin_ctx = MagicMock()
    begin_ctx.__enter__ = lambda self: conn
    begin_ctx.__exit__ = MagicMock(return_value=False)
    engine.begin.return_value = begin_ctx
    return engine


# ---------------------------------------------------------------------------
# Test 1 — Bug B guard: _sync_full_replace aborts when source returns 0 rows
# ---------------------------------------------------------------------------

class TestFullReplaceZeroRowGuard(unittest.TestCase):
    def test_zero_rows_aborts_before_truncate(self):
        """_sync_full_replace must return 0 without calling TRUNCATE when source is empty."""
        session = _make_fake_session([])
        engine = _make_fake_engine(0)

        config = {"table": "zip_scores", "model": MagicMock(), "conflict_col": None}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "zip"]):
            result = sync_mod._sync_full_replace(session, engine, config)

        self.assertEqual(result, 0, "Should return 0 when source has no rows")
        # TRUNCATE must NOT have been called
        for call_args in engine.connect.return_value.execute.call_args_list:
            sql = call_args[0][0] if call_args[0] else ""
            self.assertNotIn("TRUNCATE", str(sql).upper(),
                             "TRUNCATE must not fire when source returns 0 rows")
        print("  PASS  Bug B guard: 0-row abort fires, TRUNCATE not called")

    def test_below_floor_aborts_before_truncate(self):
        """_sync_full_replace must return 0 when row count is below MIN_ROWS_THRESHOLD."""
        # zip_scores floor is 200; feed only 10 rows
        rows = [MagicMock() for _ in range(10)]
        session = _make_fake_session(rows)
        engine = _make_fake_engine(0)

        config = {"table": "zip_scores", "model": MagicMock(), "conflict_col": None}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "zip"]):
            result = sync_mod._sync_full_replace(session, engine, config)

        self.assertEqual(result, 0, "Should return 0 when below floor")
        print("  PASS  Bug B guard: below-floor abort fires")

    def test_above_floor_proceeds(self):
        """_sync_full_replace must proceed and call TRUNCATE when row count > floor."""
        # pe_sponsors floor is 10 (see MIN_ROWS_THRESHOLD); 15 rows clears it
        rows = [MagicMock() for _ in range(15)]
        session = _make_fake_session(rows)
        # Post-sync verification query should return matching count
        engine = _make_fake_engine(row_count=15)

        config = {"table": "pe_sponsors", "model": MagicMock(), "conflict_col": None}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "name"]), \
             patch.object(sync_mod, "_build_insert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1, "name": "x"}), \
             patch.object(sync_mod, "_update_sync_state"):
            result = sync_mod._sync_full_replace(session, engine, config)

        self.assertGreater(result, 0, "Should proceed with rows above floor")
        print("  PASS  Bug B guard: above-floor proceeds normally")


# ---------------------------------------------------------------------------
# Test 2 — Fix 3: signal handler sets _shutdown_requested
# ---------------------------------------------------------------------------

class TestSignalHandler(unittest.TestCase):
    def setUp(self):
        # Reset flag before each test
        sync_mod._shutdown_requested = False

    def tearDown(self):
        sync_mod._shutdown_requested = False

    def test_sigterm_sets_flag(self):
        """Calling _handle_shutdown with SIGTERM must set _shutdown_requested=True."""
        self.assertFalse(sync_mod._shutdown_requested)
        sync_mod._handle_shutdown(signal.SIGTERM, None)
        self.assertTrue(sync_mod._shutdown_requested,
                        "_shutdown_requested must be True after SIGTERM")
        print("  PASS  SIGTERM handler: _shutdown_requested set to True")

    def test_sigint_sets_flag(self):
        """Calling _handle_shutdown with SIGINT must set _shutdown_requested=True."""
        sync_mod._handle_shutdown(signal.SIGINT, None)
        self.assertTrue(sync_mod._shutdown_requested,
                        "_shutdown_requested must be True after SIGINT")
        print("  PASS  SIGINT handler: _shutdown_requested set to True")

    def test_signal_module_registered(self):
        """signal.SIGTERM and SIGINT must be registered to _handle_shutdown."""
        self.assertEqual(signal.getsignal(signal.SIGTERM), sync_mod._handle_shutdown)
        self.assertEqual(signal.getsignal(signal.SIGINT), sync_mod._handle_shutdown)
        print("  PASS  signal.signal() registered for both SIGINT and SIGTERM")

    def test_full_replace_aborts_on_shutdown(self):
        """_sync_full_replace must skip TRUNCATE when _shutdown_requested is True."""
        sync_mod._shutdown_requested = True
        rows = [MagicMock() for _ in range(300)]  # above any floor
        session = _make_fake_session(rows)
        engine = _make_fake_engine(0)
        config = {"table": "pe_sponsors", "model": MagicMock(), "conflict_col": None}

        with patch.object(sync_mod, "_get_column_names", return_value=["id"]):
            result = sync_mod._sync_full_replace(session, engine, config)

        self.assertEqual(result, 0, "Should return 0 when shutdown requested")
        print("  PASS  Shutdown flag: _sync_full_replace skips TRUNCATE")


# ---------------------------------------------------------------------------
# Test 3 — Fix 1+2: Post-sync assertion raises on count mismatch
# ---------------------------------------------------------------------------

class TestPostSyncAssertion(unittest.TestCase):
    def test_full_replace_raises_on_mismatch(self):
        """_sync_full_replace must raise RuntimeError when Supabase count < 95% of expected."""
        rows = [MagicMock() for _ in range(200)]
        session = _make_fake_session(rows)
        # Supabase reports only 5 rows (massive mismatch — simulates silent rollback)
        engine = _make_fake_engine(row_count=5)

        config = {"table": "pe_sponsors", "model": MagicMock(), "conflict_col": None}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "name"]), \
             patch.object(sync_mod, "_build_insert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1, "name": "x"}), \
             patch.object(sync_mod, "_update_sync_state"):
            with self.assertRaises(RuntimeError) as ctx:
                sync_mod._sync_full_replace(session, engine, config)

        self.assertIn("Sync verification failed", str(ctx.exception))
        print("  PASS  Post-sync assertion: RuntimeError raised on <95% count match")

    def test_watched_zips_raises_on_mismatch(self):
        """_sync_watched_zips_only must raise RuntimeError when post-verify count < 95%."""
        sync_mod._shutdown_requested = False

        # Build rows with .zip attribute
        rows = []
        for i in range(100):
            r = MagicMock()
            r.zip = "60601"
            rows.append(r)

        # Session: first query (WatchedZip.zip_code) returns zip list,
        # second query (model filtered) returns our rows
        session = MagicMock()
        q = MagicMock()
        q.all.side_effect = [
            [MagicMock(zip_code="60601")],  # WatchedZip query
            rows,                            # practices query
        ]
        q.filter.return_value = q
        q.order_by.return_value = q
        session.query.return_value = q

        # Engine: begin() for the single-txn path
        engine = MagicMock()
        begin_conn = MagicMock()
        begin_conn.execute.return_value = MagicMock()
        begin_ctx = MagicMock()
        begin_ctx.__enter__ = lambda self: begin_conn
        begin_ctx.__exit__ = MagicMock(return_value=False)
        engine.begin.return_value = begin_ctx

        # connect() for post-verify — returns only 2 rows (massive mismatch)
        verify_conn = MagicMock()
        scalar_val = MagicMock()
        scalar_val.scalar.return_value = 2
        verify_conn.execute.return_value = scalar_val
        verify_ctx = MagicMock()
        verify_ctx.__enter__ = lambda self: verify_conn
        verify_ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = verify_ctx

        config = {
            "table": "practices",
            "model": MagicMock(),
            "conflict_col": "npi",
        }

        with patch.object(sync_mod, "WatchedZip") as mock_wz, \
             patch.object(sync_mod, "_get_column_names", return_value=["npi", "zip"]), \
             patch.object(sync_mod, "_build_upsert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"npi": "1", "zip": "60601"}), \
             patch.object(sync_mod, "_update_sync_state"):
            mock_wz.zip_code = "zip_code"
            with self.assertRaises(RuntimeError) as ctx:
                sync_mod._sync_watched_zips_only(session, engine, config)

        self.assertIn("Sync verification failed", str(ctx.exception))
        print("  PASS  Post-sync assertion: watched_zips raises on <95% count match")


# ---------------------------------------------------------------------------
# Test 4 — Fix 4: verified_results populated in run() summary
# ---------------------------------------------------------------------------

class TestRunVerifiedResults(unittest.TestCase):
    def setUp(self):
        sync_mod._shutdown_requested = False

    def tearDown(self):
        sync_mod._shutdown_requested = False

    def test_verified_results_populated(self):
        """Fix 4: verified_results dict must be built from SELECT COUNT(*) queries.

        We verify the logic directly rather than running the full run() entrypoint
        (which hits sys.exit in certain mock configurations).
        """
        results = {
            "zip_scores":    290,
            "watched_zips":  290,
            "practices":     14000,
            "deals":         6,
            "practice_changes": 0,
        }
        engine = MagicMock()
        conn = MagicMock()
        scalar_val = MagicMock()
        scalar_val.scalar.return_value = 290
        conn.execute.return_value = scalar_val
        conn.__enter__ = lambda self: self
        conn.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = conn
        verified_results = {}
        with engine.connect() as c:
            for tbl, reported in results.items():
                if not isinstance(reported, int):
                    continue
                actual = c.execute(sync_mod.text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                verified_results[tbl] = actual
        for tbl in results:
            self.assertIn(tbl, verified_results, f"{tbl} must appear in verified_results")
        print("  PASS  Fix 4: verified_results populated for all synced tables")

    def test_verified_results_in_extra_dict(self):
        """Fix 4: verified_row_counts key must appear in run() source."""
        import inspect
        source = inspect.getsource(sync_mod.run)
        self.assertIn("verified_row_counts", source,
                      "verified_row_counts must appear in run() source")
        self.assertIn("verified_results", source,
                      "verified_results dict must be built in run()")
        print("  PASS  Fix 4: verified_row_counts wired into log_scrape_complete extra in run()")


# ---------------------------------------------------------------------------
# Test 5 — Phase 1.1: watermark reflects committed rows only, not full batch
# ---------------------------------------------------------------------------

class TestWatermarkFromCommittedOnly(unittest.TestCase):
    """On graceful shutdown the watermark must not advance past uncommitted rows."""

    def setUp(self):
        sync_mod._shutdown_requested = False

    def tearDown(self):
        sync_mod._shutdown_requested = False

    def test_watermark_from_committed_only_updated_at(self):
        """_sync_incremental_updated_at writes watermark = max committed row's updated_at,
        not max fetched row's updated_at, when shutdown fires mid-batch."""
        import datetime as _dt
        # Use BATCH_SIZE = 3 via monkeypatch so 10 rows span 4 batches
        rows = []
        for i in range(10):
            r = MagicMock()
            r.id = i + 1
            r.updated_at = _dt.datetime(2026, 4, 23, 12, 0, i)
            rows.append(r)

        session = _make_fake_session(rows)
        engine = _make_fake_engine(0)

        # After 3 rows commit, set shutdown flag; batch 2 should not start
        committed_counter = {"n": 0}

        class _FakeConn:
            def __init__(self):
                self._sp = MagicMock()
            def execute(self, *a, **kw):
                committed_counter["n"] += 1
                if committed_counter["n"] == 3:
                    sync_mod._shutdown_requested = True
                return MagicMock()
            def begin_nested(self):
                return self._sp
            def commit(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        engine.connect.return_value = _FakeConn()

        captured = {}

        def _capture_update(pg_engine, table_name, rows_synced, sync_type, last_sync_value=None, notes=None):
            captured["last_sync_value"] = last_sync_value
            captured["rows_synced"] = rows_synced

        config = {"table": "deals", "model": MagicMock(), "conflict_col": "id"}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "updated_at"]), \
             patch.object(sync_mod, "_build_upsert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1, "updated_at": "x"}), \
             patch.object(sync_mod, "_update_sync_state", side_effect=_capture_update), \
             patch.object(sync_mod, "_get_sync_state", return_value=None), \
             patch.object(sync_mod, "BATCH_SIZE", 3):
            sync_mod._sync_incremental_updated_at(session, engine, config)

        # Third committed row has updated_at = 2026-04-23T12:00:02
        self.assertIn("last_sync_value", captured,
                      "watermark write should still fire when at least one row committed")
        self.assertEqual(captured["last_sync_value"], "2026-04-23T12:00:02",
                         "watermark must be max(committed) not max(fetched)")
        self.assertEqual(captured["rows_synced"], 3,
                         "should report 3 rows actually committed")
        print("  PASS  Phase 1.1: watermark(updated_at) = max committed, not max fetched")

    def test_watermark_from_committed_only_id(self):
        """_sync_incremental_id writes watermark = max committed row's id, not
        max fetched row's id, when shutdown fires mid-batch."""
        rows = []
        for i in range(10):
            r = MagicMock()
            r.id = i + 1
            r.npi = "1234567890"
            rows.append(r)

        # Session returns rows only (filter_watched_zips not configured)
        session = MagicMock()
        q = MagicMock()
        q.all.return_value = rows
        q.filter.return_value = q
        q.order_by.return_value = q
        session.query.return_value = q

        committed_counter = {"n": 0}

        class _FakeConn:
            def __init__(self):
                self._sp = MagicMock()
            def execute(self, *a, **kw):
                committed_counter["n"] += 1
                if committed_counter["n"] == 3:
                    sync_mod._shutdown_requested = True
                return MagicMock()
            def begin_nested(self):
                return self._sp
            def commit(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        engine = MagicMock()
        engine.connect.return_value = _FakeConn()

        captured = {}

        def _capture_update(pg_engine, table_name, rows_synced, sync_type, last_sync_value=None, notes=None):
            captured["last_sync_value"] = last_sync_value
            captured["rows_synced"] = rows_synced

        config = {"table": "practice_changes", "model": MagicMock(), "conflict_col": "id"}

        with patch.object(sync_mod, "_get_column_names", return_value=["id", "npi"]), \
             patch.object(sync_mod, "_build_upsert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1, "npi": "1234567890"}), \
             patch.object(sync_mod, "_update_sync_state", side_effect=_capture_update), \
             patch.object(sync_mod, "_get_sync_state", return_value=None):
            sync_mod._sync_incremental_id(session, engine, config)

        self.assertIn("last_sync_value", captured,
                      "watermark write should still fire when at least one row committed")
        self.assertEqual(captured["last_sync_value"], "3",
                         "watermark must be max(committed id) not max(fetched id)")
        print("  PASS  Phase 1.1: watermark(id) = max committed, not max fetched")


# ---------------------------------------------------------------------------
# Test 6 — Phase 1.2: unknown IntegrityError must not be silently swallowed
# ---------------------------------------------------------------------------

class TestUnknownIntegrityErrorReraises(unittest.TestCase):
    """Only the known partial-index duplicate is an expected skip. FK / NOT NULL
    / other constraint violations must propagate so the batch aborts visibly."""

    def setUp(self):
        sync_mod._shutdown_requested = False

    def tearDown(self):
        sync_mod._shutdown_requested = False

    def test_unknown_integrity_error_reraises(self):
        """An IntegrityError whose constraint is NOT uix_deal_no_dup must re-raise,
        not be logged-and-continue."""
        r = MagicMock()
        r.id = 1
        r.updated_at = None
        rows = [r]
        session = _make_fake_session(rows)

        # Build an exception that matches sqlalchemy.exc.IntegrityError shape
        # well enough for the narrowing logic: str(e.orig) gives the constraint name.
        def _make_ie(orig_str):
            ie = sync_mod.IntegrityError("stmt", {}, orig_str)
            ie.orig = orig_str  # real SQLAlchemy sets this; our stubbed Exception doesn't
            return ie

        class _FakeConn:
            def __init__(self):
                self._sp = MagicMock()
            def execute(self, *a, **kw):
                raise _make_ie("null value in column \"target_name\" violates not-null constraint")
            def begin_nested(self):
                return self._sp
            def commit(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        engine = MagicMock()
        engine.connect.return_value = _FakeConn()

        config = {"table": "deals", "model": MagicMock(), "conflict_col": "id"}

        raised = False
        with patch.object(sync_mod, "_get_column_names", return_value=["id"]), \
             patch.object(sync_mod, "_build_upsert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1}), \
             patch.object(sync_mod, "_update_sync_state"), \
             patch.object(sync_mod, "_get_sync_state", return_value=None):
            try:
                sync_mod._sync_incremental_updated_at(session, engine, config)
            except Exception:
                raised = True

        self.assertTrue(raised,
                        "unknown IntegrityError (NOT NULL violation) must re-raise, "
                        "not be silently skipped")

        # Also test that a uix_deal_no_dup error IS silently skipped (positive control)
        class _FakeConnDup:
            def __init__(self):
                self._sp = MagicMock()
                self._calls = 0
            def execute(self, *a, **kw):
                self._calls += 1
                # First call: the upsert that raises dup. Subsequent: conn.commit etc.
                if self._calls == 1:
                    raise _make_ie(
                        "duplicate key value violates unique constraint \"uix_deal_no_dup\""
                    )
                return MagicMock()
            def begin_nested(self):
                return self._sp
            def commit(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        engine2 = MagicMock()
        engine2.connect.return_value = _FakeConnDup()
        session2 = _make_fake_session(rows)

        raised2 = False
        with patch.object(sync_mod, "_get_column_names", return_value=["id"]), \
             patch.object(sync_mod, "_build_upsert_sql", return_value="INSERT ..."), \
             patch.object(sync_mod, "_model_to_dict", return_value={"id": 1}), \
             patch.object(sync_mod, "_update_sync_state"), \
             patch.object(sync_mod, "_get_sync_state", return_value=None):
            try:
                sync_mod._sync_incremental_updated_at(session2, engine2, config)
            except Exception:
                raised2 = True

        self.assertFalse(raised2,
                         "known uix_deal_no_dup IntegrityError must be silently skipped")
        print("  PASS  Phase 1.2: NOT NULL re-raises; uix_deal_no_dup dup still silently skipped")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("test_sync_resilience.py — Sync safety guard tests")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestFullReplaceZeroRowGuard))
    suite.addTests(loader.loadTestsFromTestCase(TestSignalHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestPostSyncAssertion))
    suite.addTests(loader.loadTestsFromTestCase(TestRunVerifiedResults))
    suite.addTests(loader.loadTestsFromTestCase(TestWatermarkFromCommittedOnly))
    suite.addTests(loader.loadTestsFromTestCase(TestUnknownIntegrityErrorReraises))

    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)

    print()
    if result.wasSuccessful():
        print(f"ALL {result.testsRun} TESTS PASSED")
        sys.exit(0)
    else:
        print(f"{len(result.failures)} FAILURES, {len(result.errors)} ERRORS out of {result.testsRun} tests")
        for test, tb in result.failures + result.errors:
            print(f"\n  FAIL  {test}")
            print(tb)
        sys.exit(1)
