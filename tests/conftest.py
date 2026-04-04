"""Shared fixtures for dental-pe-tracker test suite."""

import os
import sys
import tempfile

import pytest

# Allow imports from project root
sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.database import init_db, get_session


@pytest.fixture(scope="session")
def db_path():
    """Create a temporary SQLite database for the entire test session."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def session(db_path):
    """Get a fresh database session per test, with rollback after each test."""
    s = get_session(db_path)
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def make_nppes_row():
    """Factory fixture to build an NPPES-style CSV row dict."""
    def _make(taxonomy_1="", taxonomy_2="", **extra):
        row = {
            "NPI": extra.get("npi", "1234567890"),
            "Entity Type Code": extra.get("entity_type_code", "2"),
            "Provider Organization Name (Legal Business Name)": extra.get("org_name", "Test Dental"),
            "Provider First Name": extra.get("first_name", ""),
            "Provider Last Name (Legal Name)": extra.get("last_name", ""),
            "Provider First Line Business Practice Location Address": extra.get("address", "123 Main St"),
            "Provider Business Practice Location Address City Name": extra.get("city", "Chicago"),
            "Provider Business Practice Location Address State Name": extra.get("state", "IL"),
            "Provider Business Practice Location Address Postal Code": extra.get("zip", "60601"),
            "Provider Business Practice Location Address Telephone Number": extra.get("phone", ""),
        }
        for i in range(1, 16):
            row[f"Healthcare Provider Taxonomy Code_{i}"] = ""
        if taxonomy_1:
            row["Healthcare Provider Taxonomy Code_1"] = taxonomy_1
        if taxonomy_2:
            row["Healthcare Provider Taxonomy Code_2"] = taxonomy_2
        return row
    return _make
