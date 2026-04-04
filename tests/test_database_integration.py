"""Integration tests for database.py fixes — dedup logic, error handling, engine caching."""

import inspect
import os
import sys
import tempfile
from datetime import date

import pytest

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.database import init_db, get_session, get_engine, insert_deal, Deal, _cached_engines


# ── Dedup Tests ────────────────────────────────────────────────────────────


def test_insert_deal_dedup_allows_different_states(session):
    """Different target_state passes Python dedup but the DB unique index on
    (platform_company, target_name, deal_date) still catches it.  The except
    block returns False — verify that path works without raising."""
    result1 = insert_deal(
        session,
        platform_company="Heartland",
        target_name="Smile Care",
        deal_date=date(2024, 6, 1),
        target_state="IL",
        source="test",
    )
    result2 = insert_deal(
        session,
        platform_company="Heartland",
        target_name="Smile Care",
        deal_date=date(2024, 6, 1),
        target_state="TX",
        source="test",
    )
    assert result1 is True
    # DB unique index on (platform_company, target_name, deal_date) rejects this
    # even though Python-level dedup (which includes target_state) would allow it.
    # The except block catches the UNIQUE constraint error and returns False.
    assert result2 is False


def test_insert_deal_dedup_catches_exact_duplicate(session):
    """Identical deal inserted twice should return True then False."""
    kwargs = dict(
        platform_company="Aspen",
        target_name="Test Practice",
        deal_date=date(2024, 3, 1),
        target_state="CA",
        source="test",
    )
    result1 = insert_deal(session, **kwargs)
    result2 = insert_deal(session, **kwargs)
    assert result1 is True
    assert result2 is False


def test_insert_deal_dedup_null_target_name(session):
    """Two deals with target_name=None but same platform/date/source should dedup."""
    kwargs = dict(
        platform_company="NullCo",
        target_name=None,
        deal_date=date(2024, 5, 15),
        target_state="NY",
        source="test",
    )
    result1 = insert_deal(session, **kwargs)
    result2 = insert_deal(session, **kwargs)
    assert result1 is True
    assert result2 is False


# ── Error Handling ─────────────────────────────────────────────────────────


def test_insert_deal_error_handling_covers_duplicate_key():
    """Verify the except block handles both SQLite and Postgres duplicate errors."""
    source = inspect.getsource(insert_deal)
    assert "duplicate key" in source, "Postgres duplicate-key error handling missing"
    assert "UNIQUE constraint" in source, "SQLite UNIQUE constraint error handling missing"


# ── Engine Caching ─────────────────────────────────────────────────────────


def test_engine_caching_works():
    """get_engine() with the same path should return the cached engine object."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()
    cache_key = (path, False)

    # Clear any prior entry for this path
    _cached_engines.pop(cache_key, None)

    try:
        engine1 = get_engine(path)
        engine2 = get_engine(path)
        assert cache_key in _cached_engines, "_cached_engines should have an entry for the db path"
        assert engine1 is engine2, "Same path should return the exact same engine object"
    finally:
        _cached_engines.pop(cache_key, None)
        os.unlink(path)
