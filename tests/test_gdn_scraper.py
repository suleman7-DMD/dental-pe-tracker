"""Tests for GDN scraper fixes — each test targets a specific bug fix."""

import os
import sys

import pytest

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.gdn_scraper import (
    extract_target,
    extract_platform,
    extract_deal_blocks,
    _is_roundup_link,
    is_deal_block,
    KNOWN_PLATFORMS,
)
from bs4 import BeautifulSoup


# ── extract_target ────────────────────────────────────────────────────────────


def test_extract_target_with_digits_in_name():
    """Digits in target name must not break the character class."""
    result = extract_target(
        "Heartland Dental acquired Smile123 Dental Group in Illinois.",
        "Heartland Dental",
    )
    assert result is not None, "Target with digits in name should be extracted"


def test_extract_target_inverted_was_acquired_by():
    """'X was acquired by Platform' should return X as target."""
    result = extract_target(
        "North Shore Family Dental was acquired by Heartland Dental.",
        "Heartland Dental",
    )
    assert result == "North Shore Family Dental"


def test_extract_target_inverted_has_joined():
    """'X has joined Platform' should return X as target."""
    result = extract_target(
        "Perio Partners has joined Aspen Dental in Florida.",
        "Aspen Dental",
    )
    assert result is not None, "Inverted 'has joined' pattern should extract a target"
    assert "Perio" in result


# ── extract_deal_blocks ──────────────────────────────────────────────────────


def test_extract_deal_blocks_li_separate_blocks():
    """Each <li> of sufficient length should be its own deal block, not merged."""
    html = """
    <html><body>
    <div class="entry-content">
      <ul>
        <li>Heartland Dental acquired ABC Dental Group in Springfield, Illinois in a landmark deal.</li>
        <li>Aspen Dental partnered with XYZ Family Practice in Denver, Colorado for growth.</li>
        <li>Pacific Dental Services opened a new location in Phoenix, Arizona last month.</li>
      </ul>
    </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks = extract_deal_blocks(soup)
    assert len(blocks) >= 3, (
        f"Expected at least 3 separate blocks for 3 <li> items, got {len(blocks)}"
    )


# ── extract_platform ─────────────────────────────────────────────────────────


def test_extract_platform_word_boundary_no_false_positive():
    """'Tend' must not match inside 'extended'."""
    result = extract_platform(
        "The firm extended its reach into dental services."
    )
    assert result is None, (
        f"Should not false-match 'Tend' inside 'extended', got '{result}'"
    )


def test_extract_platform_word_boundary_true_positive():
    """'Tend' as a standalone word should match."""
    result = extract_platform("Tend Dental opened a new location in Austin.")
    assert result == "Tend", f"Expected 'Tend', got '{result}'"


def test_extract_platform_fallback_verbs():
    """Fallback heuristic should detect leading entity + deal verb."""
    result = extract_platform(
        "Sparkle Dental Holdings merged with a local practice in Ohio."
    )
    assert result is not None, (
        "Fallback heuristic should extract 'Sparkle Dental Holdings' via 'merged' verb"
    )


# ── KNOWN_PLATFORMS ──────────────────────────────────────────────────────────


def test_known_platforms_no_duplicates():
    """KNOWN_PLATFORMS must have no case-insensitive duplicates."""
    lowered = [p.lower() for p in KNOWN_PLATFORMS]
    assert len(set(lowered)) == len(lowered), (
        f"Found case-insensitive duplicates in KNOWN_PLATFORMS: "
        f"{[p for p in lowered if lowered.count(p) > 1]}"
    )


# ── _is_roundup_link ─────────────────────────────────────────────────────────


def test_is_roundup_link_excludes_pure_top10_listicle():
    """Pure top-10 listicle (no roundup keywords) should be excluded."""
    result = _is_roundup_link(
        "https://example.com/top-10-dsos-to-watch-2025/",
        "Top 10 DSOs to Watch",
    )
    assert result is False, "Pure top-10 listicle should be excluded"


def test_is_roundup_link_keeps_top10_roundup():
    """A top-10 link that IS a deal roundup should still be included."""
    result = _is_roundup_link(
        "https://example.com/dso-deal-roundup-top-10-2025/",
        "Top 10 DSO Deals",
    )
    assert result is True, "Top-10 deal roundup should be kept (has roundup keyword in URL)"


def test_is_roundup_link_allows_normal_roundup():
    """Normal monthly roundup URLs should pass."""
    result = _is_roundup_link(
        "https://example.com/dso-deal-roundup-march-2026/",
        "DSO Deal Roundup March 2026",
    )
    assert result is True, "Normal roundup link should be accepted"


# ── is_deal_block ─────────────────────────────────────────────────────────────


def test_is_deal_block_rejects_short_text():
    """Short text fragments should not count as deal blocks."""
    result = is_deal_block("Acquired two practices.")
    assert result is False, "Text under 40 chars should be rejected"


def test_is_deal_block_accepts_valid_deal():
    """A well-formed deal sentence should pass."""
    result = is_deal_block(
        "Heartland Dental acquired Smith Pediatric Practice in Colorado Springs for expansion."
    )
    assert result is True, "Valid deal text with deal verb and sufficient length should pass"
