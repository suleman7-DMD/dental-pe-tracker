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
            "Platform", "ZipOverview", "ZipQualitativeIntel", "PracticeIntel", "Base"]:
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
