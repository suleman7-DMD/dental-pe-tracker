"""Tests for NPPES downloader functions and sync_to_supabase config."""

import os
import sys

import pytest

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.nppes_downloader import is_dental_row, get_primary_taxonomy, get_taxonomy_specialty
from scrapers.sync_to_supabase import SYNC_CONFIG


# ── is_dental_row ──────────────────────────────────────────────────────────


def test_is_dental_row_accepts_1223_prefix(make_nppes_row):
    row = make_nppes_row(taxonomy_1="1223G0001X")
    assert is_dental_row(row) is True


def test_is_dental_row_accepts_1224_prefix(make_nppes_row):
    row = make_nppes_row(taxonomy_1="1224P0301X")
    assert is_dental_row(row) is True


def test_is_dental_row_rejects_non_dental_12_prefix(make_nppes_row):
    row = make_nppes_row(taxonomy_1="1257G0000X")
    assert is_dental_row(row) is False


def test_is_dental_row_checks_all_columns(make_nppes_row):
    row = make_nppes_row(taxonomy_1="9999999999", taxonomy_2="1223E0200X")
    assert is_dental_row(row) is True


def test_is_dental_row_empty_row(make_nppes_row):
    row = make_nppes_row()
    assert is_dental_row(row) is False


# ── get_primary_taxonomy ───────────────────────────────────────────────────


def test_get_primary_taxonomy_returns_1224(make_nppes_row):
    row = make_nppes_row(taxonomy_1="1224P0301X")
    assert get_primary_taxonomy(row) == "1224P0301X"


def test_get_primary_taxonomy_prefers_first_dental(make_nppes_row):
    row = make_nppes_row(taxonomy_1="1223G0001X", taxonomy_2="1223E0200X")
    assert get_primary_taxonomy(row) == "1223G0001X"


# ── get_taxonomy_specialty ─────────────────────────────────────────────────


def test_get_taxonomy_specialty_known_code():
    assert get_taxonomy_specialty("1223E0200X") == "endodontics"
    assert get_taxonomy_specialty("1223X0400X") == "orthodontics"
    assert get_taxonomy_specialty("1223P0300X") == "periodontics"


def test_get_taxonomy_specialty_fallback_1223():
    assert get_taxonomy_specialty("1223Z9999X") == "general"


def test_get_taxonomy_specialty_fallback_1224():
    assert get_taxonomy_specialty("1224Z9999X") == "general"


def test_get_taxonomy_specialty_rejects_non_dental():
    assert get_taxonomy_specialty("1257G0000X") is None
    assert get_taxonomy_specialty("9999999999") is None


# ── SYNC_CONFIG ────────────────────────────────────────────────────────────


def test_sync_config_deals_strategy():
    deals_config = next(c for c in SYNC_CONFIG if c["table"] == "deals")
    assert deals_config["strategy"] == "incremental_updated_at"
