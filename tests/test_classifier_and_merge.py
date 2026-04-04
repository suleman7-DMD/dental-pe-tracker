"""Tests for dso_classifier.py and merge_and_score.py fixes.

Covers: NON_CLINICAL_KEYWORDS protection for DSO-affiliated practices,
MGMT_KEYWORDS narrowing, and _normalize_address_for_grouping correctness.
"""

import os
import sys

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.dso_classifier import (
    NON_CLINICAL_KEYWORDS,
    MGMT_KEYWORDS,
    _classify_single_entity,
    _normalize_address_for_grouping,
)


# ── NON_CLINICAL_KEYWORDS ──────────────────────────────────────────────────


class TestNonClinicalKeywords:
    def test_non_clinical_keywords_contains_management_group(self):
        assert "MANAGEMENT GROUP" in NON_CLINICAL_KEYWORDS


# ── MGMT_KEYWORDS ──────────────────────────────────────────────────────────


class TestMgmtKeywords:
    def test_mgmt_keywords_contains_dental_partners_management(self):
        assert "dental partners management" in MGMT_KEYWORDS

    def test_mgmt_keywords_excludes_bare_dental_partners(self):
        # Bare "dental partners" should NOT be present -- it is too broad
        # and causes false positives on legitimate practice names.
        assert "dental partners" not in MGMT_KEYWORDS


# ── _classify_single_entity ────────────────────────────────────────────────


class TestClassifySingleEntity:
    def test_dso_affiliated_not_overridden_by_non_clinical(self):
        """A practice with 'MANAGEMENT GROUP' in its name should NOT be
        classified as non_clinical when it has dso_affiliated ownership."""
        row = {
            "practice_name": "T MANAGEMENT GROUP",
            "ownership_status": "dso_affiliated",
            "affiliated_dso": "T Management Group",
            "classification_confidence": 90,
        }
        result = _classify_single_entity(row, [], {}, {})
        classification = result[0]
        assert classification != "non_clinical", (
            f"DSO-affiliated practice was incorrectly classified as "
            f"non_clinical: {result}"
        )

    def test_non_clinical_when_independent(self):
        """An independent practice whose name matches a non-clinical keyword
        should be classified as non_clinical."""
        row = {
            "practice_name": "DENTAL LAB SERVICES INC",
            "ownership_status": "independent",
            "phone": "555-1234",
            "website": "http://example.com",
        }
        result = _classify_single_entity(row, [], {}, {})
        classification = result[0]
        assert classification == "non_clinical", (
            f"Independent non-clinical entity was not classified correctly: "
            f"{result}"
        )


# ── _normalize_address_for_grouping ────────────────────────────────────────


class TestNormalizeAddressForGrouping:
    def test_expands_abbreviations(self):
        result = _normalize_address_for_grouping("123 N Main St")
        assert result == "123 NORTH MAIN STREET"

    def test_expands_south_and_avenue(self):
        result = _normalize_address_for_grouping("456 S Oak Ave Ste 200")
        assert "SOUTH" in result
        assert "AVENUE" in result

    def test_handles_none(self):
        result = _normalize_address_for_grouping(None)
        assert result == ""

    def test_handles_empty_string(self):
        result = _normalize_address_for_grouping("")
        assert result == ""

    def test_preserves_suite_number(self):
        result = _normalize_address_for_grouping("789 E Elm Blvd Suite 100")
        assert "SUITE 100" in result
        assert "EAST" in result
        assert "BOULEVARD" in result
