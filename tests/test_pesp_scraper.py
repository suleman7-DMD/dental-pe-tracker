"""Tests for PESP scraper parsing functions.

Covers: _match_known_sponsor, extract_platform, detect_deal_type,
        _mentions_dental, extract_pe_sponsor, KNOWN_PLATFORMS, KNOWN_PE_SPONSORS.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.pesp_scraper import (
    _match_known_sponsor,
    extract_platform,
    detect_deal_type,
    _mentions_dental,
    extract_pe_sponsor,
    KNOWN_PLATFORMS,
    KNOWN_PE_SPONSORS,
)

# Conditionally import optional functions that may exist from analyst fixes
try:
    from scrapers.pesp_scraper import _is_international
except ImportError:
    _is_international = None

try:
    from scrapers.pesp_scraper import _is_credit_news
except ImportError:
    _is_credit_news = None


# ── _match_known_sponsor ──────────────────────────────────────────────────


class TestMatchKnownSponsor:
    def test_allows_kkr(self):
        """3-char sponsor must work — min length is 3 not 4."""
        result = _match_known_sponsor("KKR")
        assert result == "KKR"

    def test_rejects_short(self):
        """2-char strings are below the minimum length threshold."""
        result = _match_known_sponsor("AB")
        assert result is None

    def test_unidirectional(self):
        """sponsor.lower() in candidate.lower(), NOT the reverse.

        'Partners' must NOT match every sponsor that has 'Partners' in its name.
        The check is: does the full sponsor name appear inside the candidate?
        'Partners Group'.lower() is NOT inside 'partners', so no match.
        """
        result = _match_known_sponsor("Partners")
        assert result is None


# ── extract_platform ──────────────────────────────────────────────────────


class TestExtractPlatform:
    def test_word_boundary(self):
        """'Tend' must not match inside 'extended' — word-boundary required."""
        result = extract_platform("The firm extended its reach into dental services.")
        assert result is None

    def test_true_positive(self):
        """Known platform present as a standalone phrase must match."""
        result = extract_platform("Heartland Dental acquired three practices in Texas.")
        assert result == "Heartland Dental"


# ── detect_deal_type ──────────────────────────────────────────────────────


class TestDetectDealType:
    def test_default_unknown(self):
        """Generic text with no deal-type signals should return 'unknown'."""
        result = detect_deal_type("Something happened with dental stuff.", None)
        assert result == "unknown"

    def test_recapitalization(self):
        """Text containing 'recapitalization' should detect that deal type."""
        result = detect_deal_type(
            "Heartland Dental completes recapitalization backed by KKR.",
            "Heartland Dental",
        )
        assert result == "recapitalization"

    def test_de_novo(self):
        """'opened' signals a de novo deal."""
        result = detect_deal_type(
            "Aspen Dental opened a new location in Austin.",
            "Aspen Dental",
        )
        assert result == "de_novo"


# ── _mentions_dental ──────────────────────────────────────────────────────


class TestMentionsDental:
    def test_true_positive(self):
        """Text with a dental keyword AND a known platform should match."""
        result = _mentions_dental(
            "Heartland Dental acquired a practice in Texas for platform expansion."
        )
        assert result is True

    def test_false_negative(self):
        """Text with no dental keyword should not match."""
        result = _mentions_dental(
            "The investment fund expanded its healthcare portfolio."
        )
        assert result is False


# ── extract_pe_sponsor ────────────────────────────────────────────────────


class TestExtractPeSponsor:
    def test_parentheses_finditer(self):
        """Must check ALL parenthetical groups, not just the first.

        The first parenthetical '(IL-based)' is not a sponsor.
        The second '(KKR)' is. Even if the parenthetical regex only matches
        the first, the brute-force fallback should still find 'KKR'.
        """
        result = extract_pe_sponsor(
            "Heartland Dental (IL-based) (KKR) expanded into three states."
        )
        assert result == "KKR"


# ── KNOWN_PLATFORMS / KNOWN_PE_SPONSORS constant checks ───────────────────


class TestKnownConstants:
    def test_known_platforms_has_heartland(self):
        assert "Heartland Dental" in KNOWN_PLATFORMS

    def test_known_platforms_has_pds(self):
        assert "Pacific Dental Services" in KNOWN_PLATFORMS

    def test_known_platforms_minimum_count(self):
        """Platform list should have at least 35 entries (synced with GDN)."""
        assert len(KNOWN_PLATFORMS) >= 35

    def test_known_pe_sponsors_has_kkr(self):
        assert "KKR" in KNOWN_PE_SPONSORS

    def test_known_pe_sponsors_minimum_count(self):
        """PE sponsor list should have at least 30 entries."""
        assert len(KNOWN_PE_SPONSORS) >= 30


# ── Optional imports (analyst fixes) ──────────────────────────────────────


class TestOptionalFunctions:
    @pytest.mark.skipif(_is_international is None, reason="_is_international not exported")
    def test_is_international_exists(self):
        assert callable(_is_international)

    @pytest.mark.skipif(_is_credit_news is None, reason="_is_credit_news not exported")
    def test_is_credit_news_exists(self):
        assert callable(_is_credit_news)
