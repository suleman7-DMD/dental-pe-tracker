"""
Merge and Score — final analytical layer for the dental PE tracker.

Runs AFTER all scrapers/importers. Deduplicates deals, enriches reference
tables, scores ZIP-level consolidation, and produces exports + summary.

Usage:
    python3 scrapers/merge_and_score.py
"""

import argparse
import csv
import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import func, Column, Integer, Float, Text, Date, UniqueConstraint

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_engine, get_session, Base,
    Deal, Practice, PracticeChange, PESponsor, Platform,
    WatchedZip, DSOLocation, ADAHPIBenchmark, ZipScore,
    table_exists, backup_database, DB_PATH, BACKUP_DIR,
)
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error
from scrapers.dso_classifier import _normalize_address_for_grouping

log = get_logger("merge_and_score")

COMBINED_DIR = os.path.expanduser("~/dental-pe-tracker/data/combined")


# ZipScore model is now imported from scrapers.database


# ═══════════════════════════════════════════════════════════════════════════
# PART 1 — DEAL DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════


def deduplicate_deals(session):
    all_deals = session.query(Deal).all()
    total_deals = len(all_deals)
    if total_deals == 0:
        return {"total_deals": 0, "duplicates_found": 0, "duplicates_merged": 0, "needs_review": 0}

    consumed = set()
    duplicates_found = 0
    duplicates_merged = 0
    needs_review = 0

    def _domain(url):
        if not url:
            return None
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return None

    def _non_null_count(d):
        cols = [d.deal_date, d.platform_company, d.pe_sponsor, d.target_name,
                d.target_city, d.target_state, d.target_zip, d.deal_type,
                d.deal_size_mm, d.ebitda_multiple, d.specialty, d.num_locations,
                d.source, d.source_url, d.notes, d.raw_text]
        return sum(1 for v in cols if v is not None)

    def _merge_sources(a, b):
        if not a:
            return b
        if not b:
            return a
        parts = sorted(set(a.lower().split("+")) | set(b.lower().split("+")))
        return "+".join(parts)

    mergeable = ["deal_date", "platform_company", "pe_sponsor", "target_name",
                 "target_city", "target_state", "target_zip", "deal_type",
                 "deal_size_mm", "ebitda_multiple", "specialty", "num_locations",
                 "source_url", "notes", "raw_text"]

    # Group deals by normalized platform prefix for faster dedup (avoid O(n²) full scan)
    platform_groups = defaultdict(list)
    for d in all_deals:
        key = (d.platform_company or "").lower()[:4]  # first 4 chars as bucket key
        platform_groups[key].append(d)

    for key, group in platform_groups.items():
        for i in range(len(group)):
            a = group[i]
            if a.id in consumed:
                continue
            for j in range(i + 1, len(group)):
                b = group[j]
                if b.id in consumed:
                    continue

                # Primary match
                if not (a.platform_company and b.platform_company and a.target_name and b.target_name):
                    continue
                if fuzz.ratio(a.platform_company.lower(), b.platform_company.lower()) <= 85:
                    continue
                if fuzz.ratio(a.target_name.lower(), b.target_name.lower()) <= 80:
                    continue
                if not (a.deal_date and b.deal_date):
                    continue
                if abs((a.deal_date - b.deal_date).days) > 60:
                    continue

                duplicates_found += 1

                # Secondary confirmation
                confirmed = False
                if a.target_state and b.target_state and a.target_state.upper() == b.target_state.upper():
                    confirmed = True
                elif a.pe_sponsor and b.pe_sponsor and a.pe_sponsor.lower() == b.pe_sponsor.lower():
                    confirmed = True
                elif _domain(a.source_url) and _domain(b.source_url) and _domain(a.source_url) == _domain(b.source_url):
                    confirmed = True

                if not confirmed:
                    log.warning("Possible duplicate not merged — needs review: deal %s (%s/%s) <-> deal %s (%s/%s)",
                                a.id, a.platform_company, a.target_name, b.id, b.platform_company, b.target_name)
                    needs_review += 1
                    continue

                # Merge: keep most complete
                if _non_null_count(b) > _non_null_count(a):
                    keeper, donor = b, a
                else:
                    keeper, donor = a, b

                for attr in mergeable:
                    if getattr(keeper, attr) is None and getattr(donor, attr) is not None:
                        setattr(keeper, attr, getattr(donor, attr))

                keeper.source = _merge_sources(keeper.source, donor.source)
                log.info("Merged duplicate: keep deal %s, remove deal %s (%s / %s)",
                         keeper.id, donor.id, keeper.platform_company, keeper.target_name)
                session.delete(donor)
                consumed.add(donor.id)
                duplicates_merged += 1

    session.commit()
    log.info("Dedup: %d total, %d found, %d merged, %d need review",
             total_deals, duplicates_found, duplicates_merged, needs_review)
    return {"total_deals": total_deals, "duplicates_found": duplicates_found,
            "duplicates_merged": duplicates_merged, "needs_review": needs_review}


# ═══════════════════════════════════════════════════════════════════════════
# PART 2 — PLATFORM AND SPONSOR ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════


def enrich_platforms_and_sponsors(session):
    stats = {"platforms_updated": 0, "sponsors_updated": 0}

    # Pre-load all deals with platform_company in one query (avoid N+1)
    all_deals = session.query(Deal).filter(Deal.platform_company.isnot(None)).all()
    deals_by_platform = defaultdict(list)
    for d in all_deals:
        deals_by_platform[d.platform_company].append(d)

    # Platforms
    for name, deals in deals_by_platform.items():
        states = sorted({d.target_state for d in deals if d.target_state})
        specialties = {}
        for d in deals:
            if d.specialty:
                specialties[d.specialty] = specialties.get(d.specialty, 0) + 1
        primary_spec = max(specialties, key=specialties.get) if specialties else None

        # Most recent PE sponsor
        sponsor = None
        for d in sorted(deals, key=lambda x: x.deal_date or date.min, reverse=True):
            if d.pe_sponsor:
                sponsor = d.pe_sponsor
                break

        existing = session.query(Platform).filter_by(name=name).first()
        if existing:
            existing.pe_sponsor_name = sponsor or existing.pe_sponsor_name
            existing.states_active = ", ".join(states) if states else existing.states_active
            existing.specialties = primary_spec or existing.specialties
            existing.estimated_locations = max(len(deals), existing.estimated_locations or 0)
        else:
            session.add(Platform(name=name, pe_sponsor_name=sponsor,
                                 states_active=", ".join(states) if states else None,
                                 specialties=primary_spec, estimated_locations=len(deals)))
        stats["platforms_updated"] += 1

    # Sponsors
    for (name,) in session.query(Deal.pe_sponsor).filter(Deal.pe_sponsor.isnot(None)).distinct():
        deal_count = session.query(func.count(Deal.id)).filter(Deal.pe_sponsor == name).scalar()
        plat_count = session.query(func.count(func.distinct(Deal.platform_company))).filter(Deal.pe_sponsor == name).scalar()

        existing = session.query(PESponsor).filter_by(name=name).first()
        if existing:
            existing.notes = f"{deal_count} deals across {plat_count} platforms"
            existing.healthcare_focus = True
        else:
            session.add(PESponsor(name=name, healthcare_focus=True,
                                   notes=f"{deal_count} deals across {plat_count} platforms"))
        stats["sponsors_updated"] += 1

    session.commit()
    log.info("Enrichment: %d platforms, %d sponsors", stats["platforms_updated"], stats["sponsors_updated"])
    return stats


# ═══════════════════════════════════════════════════════════════════════════
# PART 3 — CONSOLIDATION SCORING
# ═══════════════════════════════════════════════════════════════════════════


def deduplicate_practices_in_zip(session, zip_code):
    """Deduplicate practices by address within a ZIP code.

    Multiple NPIs at the same address usually represent one practice (e.g., a
    dental school with 256 registered dentists should count as 1 entity, not 256).

    Grouping rules:
      - 50+ NPIs at one address  → 1 institutional entity (excluded from
        consolidation calculations)
      - 2-49 NPIs with at least one organization NPI → 1 practice, using the
        org NPI's ownership_status
      - Multiple individual-only NPIs at same address → each counts as 1
        practice (e.g. solo practitioners sharing a building)
      - Single NPI at address → 1 practice

    Returns dict with deduplicated counts.
    """
    practices = session.query(Practice).filter(Practice.zip == zip_code).all()
    raw_npi_count = len(practices)

    if raw_npi_count == 0:
        return {
            "total_deduplicated": 0,
            "pe_backed_count": 0,
            "dso_affiliated_count": 0,
            "independent_count": 0,
            "unknown_count": 0,
            "institutional_count": 0,
            "raw_npi_count": 0,
        }

    # Group by normalized (address, city)
    addr_groups = defaultdict(list)
    for p in practices:
        addr = (p.address or "").upper().strip()
        city = (p.city or "").upper().strip()
        key = (addr, city)
        addr_groups[key].append(p)

    # Walk each group and produce deduplicated practice entries
    # Each entry is an ownership_status string (or "institutional")
    deduped_statuses = []

    for (addr, city), group in addr_groups.items():
        n = len(group)

        if n >= 50:
            # Large institution (dental school, hospital dental dept, etc.)
            deduped_statuses.append("institutional")

        elif n >= 2:
            # Check if any org NPI is present
            org_npis = [p for p in group if p.entity_type == "organization"]
            if org_npis:
                # Use the org NPI's ownership_status as representative
                # Pick the most "specific" status among org NPIs
                # Priority: pe_backed > dso_affiliated > independent > unknown
                status_priority = {"pe_backed": 4, "dso_affiliated": 3,
                                   "independent": 2, "unknown": 1, None: 0}
                best_org = max(org_npis,
                               key=lambda p: status_priority.get(p.ownership_status, 0))
                deduped_statuses.append(best_org.ownership_status or "unknown")
            else:
                # All individual NPIs — each is a separate practitioner
                # sharing the same building (e.g. a professional office building)
                for p in group:
                    deduped_statuses.append(p.ownership_status or "unknown")

        else:
            # Single NPI at this address
            deduped_statuses.append(group[0].ownership_status or "unknown")

    # Tally counts
    pe_backed_count = sum(1 for s in deduped_statuses if s == "pe_backed")
    dso_affiliated_count = sum(1 for s in deduped_statuses if s == "dso_affiliated")
    independent_count = sum(1 for s in deduped_statuses if s == "independent")
    institutional_count = sum(1 for s in deduped_statuses if s == "institutional")
    unknown_count = sum(1 for s in deduped_statuses if s in ("unknown", None))
    total_deduplicated = len(deduped_statuses)

    return {
        "total_deduplicated": total_deduplicated,
        "pe_backed_count": pe_backed_count,
        "dso_affiliated_count": dso_affiliated_count,
        "independent_count": independent_count,
        "unknown_count": unknown_count,
        "institutional_count": institutional_count,
        "raw_npi_count": raw_npi_count,
    }


# ── Phase 3: Saturation Metrics & Market Type Classification ──────────────

# Entity classification categories for metric computation
BUYABLE_TYPES = {'solo_established', 'solo_inactive', 'solo_high_volume'}
CORPORATE_TYPES = {'dso_regional', 'dso_national'}


def compute_saturation_metrics(session, zip_code, population, mhi=None, pop_growth=None):
    """Compute ZIP-level saturation metrics using entity_classification data.

    GP vs specialist separation: A location (unique normalized address) counts
    as GP if it contains at least one practice where entity_classification is
    NOT 'specialist' and NOT 'non_clinical'. Specialist-only locations are those
    where ALL practices at the address are specialists.

    CRITICAL: buyable_practice_ratio denominator uses GP-only locations, NOT all
    dental locations. Specialists don't compete for the same patients.

    Args:
        session: SQLAlchemy session
        zip_code: ZIP code string
        population: ZIP population (int, must be > 0)
        mhi: median household income (int or None)
        pop_growth: population growth percentage (float or None)

    Returns:
        dict with all computed metrics and a 'warnings' list
    """
    practices = session.query(Practice).filter(Practice.zip == zip_code).all()
    total_practices = len(practices)

    if total_practices == 0:
        return {
            'total_gp_locations': 0, 'total_specialist_locations': 0,
            'dld_gp_per_10k': 0.0, 'dld_total_per_10k': 0.0,
            'people_per_gp_door': None,
            'buyable_practice_count': 0, 'buyable_practice_ratio': 0.0,
            'corporate_location_count': 0, 'corporate_share_pct': 0.0,
            'family_practice_count': 0, 'specialist_density_flag': False,
            'entity_classification_coverage_pct': 0.0,
            'data_axle_enrichment_pct': 0.0,
            'metrics_confidence': 'low', 'warnings': [],
        }

    # Group by normalized address (same normalization as entity classification)
    addr_groups = defaultdict(list)
    for p in practices:
        norm_addr = _normalize_address_for_grouping(p.address)
        city = (p.city or "").upper().strip()
        key = (norm_addr, city)
        addr_groups[key].append(p)

    # Classify each location as GP, specialist-only, or non-clinical-only
    gp_locations = []      # (key, [practices]) — has at least one GP
    spec_locations = []    # (key, [practices]) — all specialist

    for key, pracs_at_addr in addr_groups.items():
        classifications = [p.entity_classification for p in pracs_at_addr]
        non_null = [c for c in classifications if c is not None]

        if not non_null:
            # No classification data — treat as GP (conservative)
            gp_locations.append((key, pracs_at_addr))
            continue

        all_non_clinical = all(c == 'non_clinical' for c in non_null)
        if all_non_clinical:
            continue  # skip non-clinical-only addresses

        has_gp = any(c not in ('specialist', 'non_clinical') for c in non_null)
        if has_gp:
            gp_locations.append((key, pracs_at_addr))
        else:
            # All classified practices are specialist
            spec_locations.append((key, pracs_at_addr))

    total_gp = len(gp_locations)
    total_spec = len(spec_locations)

    log.info("ZIP %s: %d practices at %d unique addresses → %d GP locations, "
             "%d specialist-only locations. Method: entity_classification field match.",
             zip_code, total_practices, len(addr_groups), total_gp, total_spec)

    # DLD metrics (require population)
    pop_10k = population / 10000.0 if population and population > 0 else None
    dld_gp = (total_gp / pop_10k) if pop_10k and total_gp > 0 else 0.0
    dld_total = ((total_gp + total_spec) / pop_10k) if pop_10k else 0.0
    people_per_door = (population // total_gp) if total_gp > 0 and population else None

    # Buyable locations: GP locations with at least one buyable-classified practice
    buyable_count = sum(
        1 for _, pracs in gp_locations
        if any(p.entity_classification in BUYABLE_TYPES for p in pracs)
    )
    buyable_ratio = (buyable_count / total_gp) if total_gp > 0 else 0.0

    # Corporate locations: GP locations with at least one corporate-classified practice
    corporate_count = sum(
        1 for _, pracs in gp_locations
        if any(p.entity_classification in CORPORATE_TYPES for p in pracs)
    )
    corporate_share = (corporate_count / total_gp) if total_gp > 0 else 0.0

    # Family practice locations
    family_count = sum(
        1 for _, pracs in gp_locations
        if any(p.entity_classification == 'family_practice' for p in pracs)
    )

    # Specialist density flag
    spec_density_flag = total_spec > 3

    # Coverage metrics
    classified_count = sum(1 for p in practices if p.entity_classification is not None)
    coverage_pct = (classified_count / total_practices * 100) if total_practices else 0.0
    enriched_count = sum(1 for p in practices if p.data_axle_import_date is not None)
    enrichment_pct = (enriched_count / total_practices * 100) if total_practices else 0.0

    # Metrics confidence
    unknown_ownership_count = sum(
        1 for p in practices if p.ownership_status in ('unknown', None)
    )
    unknown_pct = (unknown_ownership_count / total_practices * 100) if total_practices else 100.0

    if coverage_pct > 80 and unknown_pct < 20:
        confidence = 'high'
    elif coverage_pct > 50 and unknown_pct < 40:
        confidence = 'medium'
    else:
        confidence = 'low'

    # Data quality warnings
    warnings = []

    # Warning 1: Capacity-substitution signal
    if people_per_door and people_per_door > 2500:
        emp_values = [p.employee_count for p in practices
                      if p.employee_count is not None and p.employee_count > 0]
        if emp_values:
            avg_emp = sum(emp_values) / len(emp_values)
            if avg_emp > 12:
                w = (f"Capacity substitution detected in {zip_code}: {total_gp} GP offices "
                     f"but average {avg_emp:.0f} employees per office. "
                     f"Few offices with large capacity — actual supply may be "
                     f"higher than door count suggests.")
                warnings.append(w)
                log.warning(w)

    # Warning 2: High income attracting high supply
    if mhi and mhi > 120000 and dld_gp > 8.0:
        w = (f"High-income high-supply in {zip_code}: ${mhi:,} MHI with "
             f"{dld_gp:.1f}/10k dental density. Wealthy areas attract more "
             f"providers, increasing competition despite affluence.")
        warnings.append(w)
        log.warning(w)

    return {
        'total_gp_locations': total_gp,
        'total_specialist_locations': total_spec,
        'dld_gp_per_10k': round(dld_gp, 2),
        'dld_total_per_10k': round(dld_total, 2),
        'people_per_gp_door': people_per_door,
        'buyable_practice_count': buyable_count,
        'buyable_practice_ratio': round(buyable_ratio, 4),
        'corporate_location_count': corporate_count,
        'corporate_share_pct': round(corporate_share, 4),
        'family_practice_count': family_count,
        'specialist_density_flag': spec_density_flag,
        'entity_classification_coverage_pct': round(coverage_pct, 1),
        'data_axle_enrichment_pct': round(enrichment_pct, 1),
        'metrics_confidence': confidence,
        'warnings': warnings,
    }


def classify_market_type(dld_gp, bhr, mhi, corporate_share, family_count,
                         total_gp, population, metrics_confidence,
                         population_growth_pct=None):
    """Assign a market type label based on computed metrics.

    Returns (market_type, market_type_confidence, explanation).

    market_type_confidence:
    - 'confirmed': metrics_confidence is 'high', all required inputs available
    - 'provisional': metrics_confidence is 'medium', label assigned but may change
    - 'insufficient_data': metrics_confidence is 'low', label NOT assigned

    IMPORTANT: If metrics_confidence is 'low', market_type is set to NULL.
    All underlying metrics are still stored — nothing is lost.
    """
    # Confidence gate
    if metrics_confidence == 'low':
        return (None, 'insufficient_data',
                "Insufficient data quality for market classification. "
                "Individual metrics are still stored for reference.")

    mt_conf = 'confirmed' if metrics_confidence == 'high' else 'provisional'

    # Rule 1: Low resident commercial hub
    if dld_gp > 15.0 and population and population < 15000:
        return ('low_resident_commercial', mt_conf,
                f"Very high dental density ({dld_gp:.1f}/10k) relative to small "
                f"residential population ({population:,}). Likely a commercial/office "
                f"hub where demand is driven by non-residents.")

    # Rule 2: High saturation corporate
    if dld_gp > 8.0 and bhr < 0.25 and corporate_share > 0.30:
        return ('high_saturation_corporate', mt_conf,
                f"High dental density ({dld_gp:.1f}/10k) dominated by corporate "
                f"chains ({corporate_share:.0%} corporate). Competitive for patients, "
                f"limited ownership access.")

    # Rule 3: Corporate dominant
    if corporate_share > 0.50 and bhr < 0.20:
        return ('corporate_dominant', mt_conf,
                f"Over half of GP locations are corporate-affiliated "
                f"({corporate_share:.0%}). Market structure favors employment "
                f"over ownership.")

    # Rule 4: Family concentrated
    if bhr > 0.40 and total_gp > 0:
        buyable_count = int(bhr * total_gp)
        if buyable_count > 0 and family_count > 0.30 * buyable_count:
            return ('family_concentrated', mt_conf,
                    f"Many independent practices are family-operated with apparent "
                    f"internal succession. Nominal ownership availability "
                    f"({bhr:.0%}) overstates real opportunity.")

    # Rule 5: Low density high income
    if (dld_gp < 5.0 and bhr > 0.40 and mhi and mhi > 120000
            and population and population > 15000):
        return ('low_density_high_income', mt_conf,
                f"Below-average dental supply ({dld_gp:.1f}/10k) in a high-income "
                f"area (${mhi:,}). High share of independent practices "
                f"({bhr:.0%} buyable).")

    # Rule 6: Low density independent
    if (5.0 <= dld_gp <= 7.0 and bhr > 0.50 and corporate_share < 0.10
            and population and population < 30000):
        return ('low_density_independent', mt_conf,
                f"Moderate density ({dld_gp:.1f}/10k), predominantly independent "
                f"practices ({bhr:.0%} buyable), low corporate presence "
                f"({corporate_share:.0%}). Patient retention likely high.")

    # Rule 7: Growing undersupplied
    if dld_gp < 5.0 and population_growth_pct and population_growth_pct > 10:
        return ('growing_undersupplied', mt_conf,
                f"Below-average dental supply ({dld_gp:.1f}/10k) in a growing "
                f"population area ({population_growth_pct:.1f}% growth). "
                f"Supply may lag demand.")

    # Rule 8: Balanced mixed (widened thresholds to reflect actual data)
    if 4.0 <= dld_gp <= 12.0 and 0.20 <= bhr <= 0.60 and 0.05 <= corporate_share <= 0.35:
        return ('balanced_mixed', mt_conf,
                f"Balanced mix of independent ({bhr:.0%} buyable) and corporate "
                f"({corporate_share:.0%}) practices at moderate density "
                f"({dld_gp:.1f}/10k).")

    # Rule 9: High density independent
    if dld_gp > 8.0 and bhr > 0.50 and corporate_share < 0.15:
        return ('high_density_independent', mt_conf,
                f"High dental density ({dld_gp:.1f}/10k) but dominated by "
                f"independent practices ({bhr:.0%} buyable, {corporate_share:.0%} "
                f"corporate). Competition is high but ownership access is strong.")

    # Rule 10: Independent suburban
    if (4.0 <= dld_gp <= 15.0 and bhr > 0.60 and corporate_share < 0.15
            and population and population > 15000):
        return ('independent_suburban', mt_conf,
                f"Predominantly independent suburban market ({bhr:.0%} buyable) "
                f"with limited corporate presence ({corporate_share:.0%}). "
                f"Density {dld_gp:.1f}/10k.")

    # Rule 11: Default
    return ('mixed', mt_conf,
            "Market does not fit a clear pattern. Review individual metrics.")


def ensure_chicagoland_watched(session):
    """Ensure all Chicagoland ZIPs are in watched_zips (not just the original 28)."""
    ALL_CHICAGOLAND_ZIPS = [
        "60004", "60005", "60007", "60008", "60010", "60015", "60016", "60017",
        "60018", "60022", "60025", "60026", "60035", "60037", "60038", "60040",
        "60045", "60053", "60056", "60061", "60062", "60067", "60068", "60069",
        "60070", "60074", "60076", "60077", "60089", "60090", "60091", "60093",
        "60101", "60103", "60104", "60106", "60107", "60108", "60110", "60118",
        "60119", "60120", "60121", "60122", "60123", "60124", "60126", "60130",
        "60131", "60133", "60134", "60137", "60138", "60139", "60143", "60144",
        "60148", "60151", "60153", "60154", "60155", "60160", "60161", "60162",
        "60163", "60164", "60165", "60171", "60172", "60173", "60174", "60175",
        "60176", "60181", "60185", "60186", "60187", "60188", "60189", "60190",
        "60191", "60193", "60194", "60195", "60201", "60202", "60203", "60301",
        "60302", "60304", "60305", "60402", "60403", "60404", "60406", "60409",
        "60410", "60411", "60412", "60415", "60416", "60418", "60419", "60421",
        "60422", "60423", "60425", "60426", "60428", "60429", "60430", "60431",
        "60432", "60433", "60434", "60435", "60436", "60438", "60439", "60440",
        "60441", "60442", "60443", "60445", "60446", "60447", "60448", "60449",
        "60450", "60451", "60452", "60453", "60454", "60455", "60456", "60457",
        "60458", "60459", "60461", "60462", "60463", "60464", "60465", "60466",
        "60467", "60468", "60469", "60471", "60472", "60473", "60475", "60476",
        "60477", "60478", "60480", "60481", "60482", "60484", "60487", "60490",
        "60491", "60501", "60502", "60503", "60504", "60505", "60506", "60510",
        "60511", "60512", "60513", "60514", "60515", "60516", "60517", "60519",
        "60521", "60523", "60525", "60526", "60527", "60532", "60534", "60536",
        "60537", "60538", "60539", "60540", "60541", "60542", "60543", "60544",
        "60545", "60546", "60548", "60554", "60555", "60558", "60559", "60560",
        "60563", "60564", "60565", "60585", "60586", "60601", "60602", "60603",
        "60604", "60605", "60606", "60607", "60608", "60609", "60610", "60611",
        "60612", "60613", "60614", "60615", "60616", "60617", "60618", "60619",
        "60620", "60621", "60622", "60623", "60624", "60625", "60626", "60628",
        "60629", "60630", "60631", "60632", "60633", "60634", "60636", "60637",
        "60638", "60639", "60640", "60641", "60642", "60643", "60644", "60645",
        "60646", "60647", "60649", "60651", "60652", "60653", "60654", "60655",
        "60656", "60657", "60659", "60660", "60661", "60706", "60707", "60712",
        "60714", "60803", "60804", "60805", "60827",
    ]
    existing = {w.zip_code for w in session.query(WatchedZip).filter_by(metro_area="Chicagoland").all()}
    missing = [z for z in ALL_CHICAGOLAND_ZIPS if z not in existing]
    if not missing:
        return 0
    added = 0
    for zc in missing:
        p = session.query(Practice.city, Practice.state).filter(Practice.zip == zc).first()
        city = p[0].title() if p and p[0] else None
        state = p[1] if p and p[1] else "IL"
        session.add(WatchedZip(zip_code=zc, city=city, state=state, metro_area="Chicagoland"))
        added += 1
    session.commit()
    log.info("Added %d missing Chicagoland ZIPs to watched_zips (total: %d)", added, len(ALL_CHICAGOLAND_ZIPS))
    return added


def score_watched_zips(session):
    Base.metadata.create_all(bind=session.get_bind())

    today = date.today()
    ninety_ago = today - timedelta(days=90)
    twelve_mo_ago = today - timedelta(days=365)

    watched = session.query(WatchedZip).all()
    has_dso_locs = table_exists("dso_locations")

    # Pre-load DSO locations by ZIP for efficiency
    dso_loc_by_zip = {}
    if has_dso_locs:
        for loc in session.query(DSOLocation).all():
            if loc.zip:
                dso_loc_by_zip.setdefault(loc.zip, []).append(loc)

    zips_scored = 0
    total_consol = 0.0
    total_opp = 0.0
    all_warnings = []       # Phase 3: collect data quality warnings
    market_type_dist = defaultdict(int)  # Phase 3: market type distribution
    confidence_dist = defaultdict(int)   # Phase 3: metrics confidence distribution

    for wz in watched:
        zc = wz.zip_code

        # Cross-reference DSO locations — upgrade unknowns before counting
        if zc in dso_loc_by_zip:
            unknowns = session.query(Practice).filter(
                Practice.zip == zc, Practice.ownership_status == "unknown"
            ).all()
            for practice in unknowns:
                if not practice.address:
                    continue
                for dloc in dso_loc_by_zip[zc]:
                    if not dloc.address:
                        continue
                    if fuzz.token_sort_ratio(practice.address.lower(), dloc.address.lower()) >= 85:
                        practice.ownership_status = "dso_affiliated"
                        practice.affiliated_dso = dloc.dso_name
                        break
            session.flush()

        # Count practices (address-deduplicated)
        counts = deduplicate_practices_in_zip(session, zc)
        raw = counts["raw_npi_count"]
        total = counts["total_deduplicated"]
        pe = counts["pe_backed_count"]
        dso = counts["dso_affiliated_count"]
        indep = counts["independent_count"]
        unk = counts["unknown_count"]
        institutional = counts["institutional_count"]
        classified = total - unk - institutional

        dedup_ratio = raw / total if total > 0 else 1.0
        log.info("ZIP %s: %d raw NPIs -> %d deduplicated practices (%.1fx dedup, %d institutional)",
                 zc, raw, total, dedup_ratio, institutional)

        consolidated_count = pe + dso
        consol_pct = (consolidated_count / classified * 100) if classified > 0 else 0.0
        consol_total = (consolidated_count / total * 100) if total > 0 else 0.0
        indep_pct_total = (indep / total * 100) if total > 0 else 0.0
        pe_pct = (pe / classified * 100) if classified > 0 else 0.0
        unk_pct = (unk / total * 100) if total > 0 else 0.0

        # Recent changes
        recent = session.query(func.count(PracticeChange.id)).join(
            Practice, PracticeChange.npi == Practice.npi
        ).filter(Practice.zip == zc, PracticeChange.change_date >= ninety_ago).scalar() or 0

        # State deals last 12 months
        st = wz.state
        state_deals = 0
        if st:
            state_deals = session.query(func.count(Deal.id)).filter(
                Deal.target_state == st, Deal.deal_date >= twelve_mo_ago
            ).scalar() or 0

        # Opportunity score
        opp = 100 - consol_pct
        if unk_pct < 10:
            opp += 5
        elif unk_pct < 20:
            opp += 3
        if state_deals > 20:
            opp += 5
        elif state_deals > 10:
            opp += 3
        if unk_pct > 60:
            opp -= 15
        opp = max(0.0, min(100.0, opp))

        confidence = "high" if unk_pct < 20 else ("medium" if unk_pct <= 50 else "low")

        # ── Phase 3: Saturation metrics & market type classification ──
        sat_vals = {}
        if wz.population and wz.population > 0:
            sat = compute_saturation_metrics(
                session, zc, wz.population,
                wz.median_household_income,
                wz.population_growth_pct,
            )
            mt, mt_conf, mt_explanation = classify_market_type(
                sat['dld_gp_per_10k'], sat['buyable_practice_ratio'],
                wz.median_household_income, sat['corporate_share_pct'],
                sat['family_practice_count'], sat['total_gp_locations'],
                wz.population, sat['metrics_confidence'],
                wz.population_growth_pct,
            )
            sat_vals = {
                'total_gp_locations': sat['total_gp_locations'],
                'total_specialist_locations': sat['total_specialist_locations'],
                'dld_gp_per_10k': sat['dld_gp_per_10k'],
                'dld_total_per_10k': sat['dld_total_per_10k'],
                'people_per_gp_door': sat['people_per_gp_door'],
                'buyable_practice_count': sat['buyable_practice_count'],
                'buyable_practice_ratio': sat['buyable_practice_ratio'],
                'corporate_location_count': sat['corporate_location_count'],
                'corporate_share_pct': sat['corporate_share_pct'],
                'family_practice_count': sat['family_practice_count'],
                'specialist_density_flag': sat['specialist_density_flag'],
                'entity_classification_coverage_pct': sat['entity_classification_coverage_pct'],
                'data_axle_enrichment_pct': sat['data_axle_enrichment_pct'],
                'metrics_confidence': sat['metrics_confidence'],
                'market_type': mt,
                'market_type_confidence': mt_conf,
            }
            # Track distributions and warnings
            market_type_dist[mt or 'NULL'] += 1
            confidence_dist[sat['metrics_confidence']] += 1
            all_warnings.extend(sat['warnings'])
            if mt:
                log.info("ZIP %s → market_type=%s (%s): %s", zc, mt, mt_conf, mt_explanation)
        else:
            # No population data — store what we can
            sat = compute_saturation_metrics(session, zc, 0)
            sat_vals = {
                'total_gp_locations': sat['total_gp_locations'],
                'total_specialist_locations': sat['total_specialist_locations'],
                'entity_classification_coverage_pct': sat['entity_classification_coverage_pct'],
                'data_axle_enrichment_pct': sat['data_axle_enrichment_pct'],
                'metrics_confidence': 'low',
                'market_type': None,
                'market_type_confidence': 'insufficient_data',
            }
            market_type_dist['NULL'] += 1
            confidence_dist['low'] += 1

        # Upsert
        existing = session.query(ZipScore).filter_by(zip_code=zc).first()
        vals = dict(city=wz.city, state=st, metro_area=wz.metro_area,
                    total_practices=total, pe_backed_count=pe, dso_affiliated_count=dso,
                    independent_count=indep, unknown_count=unk,
                    institutional_count=institutional, raw_npi_count=raw,
                    classified_count=classified,
                    consolidation_pct=round(consol_pct, 2), consolidation_pct_of_total=round(consol_total, 2),
                    independent_pct_of_total=round(indep_pct_total, 2),
                    consolidated_count=consolidated_count, unclassified_pct=round(unk_pct, 2),
                    pe_penetration_pct=round(pe_pct, 2), pct_unknown=round(unk_pct, 2),
                    recent_changes_90d=recent, state_deal_count_12m=state_deals,
                    opportunity_score=round(opp, 2), data_confidence=confidence,
                    **sat_vals)
        if existing:
            for k, v in vals.items():
                setattr(existing, k, v)
            existing.score_date = today
        else:
            session.add(ZipScore(zip_code=zc, score_date=today, **vals))

        zips_scored += 1
        total_consol += consol_pct
        total_opp += opp

    session.commit()
    avg_c = round(total_consol / zips_scored, 2) if zips_scored else 0.0
    avg_o = round(total_opp / zips_scored, 2) if zips_scored else 0.0
    log.info("Scored %d ZIPs (avg consolidation=%.1f%%, avg opportunity=%.1f)", zips_scored, avg_c, avg_o)

    # Phase 3 summary logging
    log.info("── Phase 3 Saturation Summary ──")
    log.info("Market type distribution: %s",
             ", ".join(f"{k}={v}" for k, v in sorted(market_type_dist.items(), key=lambda x: -x[1])))
    log.info("Metrics confidence: %s",
             ", ".join(f"{k}={v}" for k, v in sorted(confidence_dist.items(), key=lambda x: -x[1])))
    log.info("ZIPs with NULL market_type: %d", market_type_dist.get('NULL', 0))
    if all_warnings:
        log.info("Data quality warnings (%d total):", len(all_warnings))
        for w in all_warnings:
            log.info("  %s", w)
    else:
        log.info("No data quality warnings generated.")

    return {"zips_scored": zips_scored, "avg_consolidation": avg_c, "avg_opportunity": avg_o}


# ═══════════════════════════════════════════════════════════════════════════
# PART 4 — METRO AREA ROLLUP
# ═══════════════════════════════════════════════════════════════════════════


def metro_rollup(session):
    today = date.today()
    metros = session.query(WatchedZip.metro_area).distinct().all()
    results = []

    for (metro,) in metros:
        if not metro:
            continue

        # Get all ZIP scores for this metro from today
        scores = session.query(ZipScore).filter(
            ZipScore.metro_area == metro, ZipScore.score_date == today
        ).all()

        if not scores:
            log.info("No scores for metro %s today, skipping.", metro)
            continue

        # Aggregate counts
        total = sum(s.total_practices or 0 for s in scores)
        pe = sum(s.pe_backed_count or 0 for s in scores)
        dso = sum(s.dso_affiliated_count or 0 for s in scores)
        indep = sum(s.independent_count or 0 for s in scores)
        unk = sum(s.unknown_count or 0 for s in scores)
        classified = total - unk

        consolidated_count = pe + dso
        consol = (consolidated_count / classified * 100) if classified > 0 else 0.0
        consol_total = (consolidated_count / total * 100) if total > 0 else 0.0
        indep_pct_total = (indep / total * 100) if total > 0 else 0.0
        unk_pct = (unk / total * 100) if total > 0 else 0.0
        confidence = "high" if unk_pct < 20 else ("medium" if unk_pct <= 50 else "low")
        avg_opp = sum(s.opportunity_score or 0 for s in scores) / len(scores) if scores else 0

        # Primary state
        state = scores[0].state if scores else None

        # QoQ change — look for previous score > 30 days ago
        qoq = None
        prev_scores = session.query(ZipScore).filter(
            ZipScore.metro_area == metro, ZipScore.score_date < today - timedelta(days=30)
        ).all()
        if prev_scores:
            prev_total = sum(s.total_practices or 0 for s in prev_scores)
            prev_pe = sum(s.pe_backed_count or 0 for s in prev_scores)
            prev_dso = sum(s.dso_affiliated_count or 0 for s in prev_scores)
            prev_classified = prev_total - sum(s.unknown_count or 0 for s in prev_scores)
            prev_consol = ((prev_pe + prev_dso) / prev_classified * 100) if prev_classified > 0 else 0.0
            qoq = round(consol - prev_consol, 1)
        else:
            log.info("First scoring run for %s — no QoQ comparison available", metro)

        # ADA HPI benchmark
        ada_benchmark = None
        if state and table_exists("ada_hpi_benchmarks"):
            row = session.query(ADAHPIBenchmark).filter(
                ADAHPIBenchmark.state == state,
                ADAHPIBenchmark.career_stage == "all"
            ).order_by(ADAHPIBenchmark.data_year.desc()).first()
            if row:
                ada_benchmark = row.pct_dso_affiliated

        # Top DSO in this metro
        zips_in_metro = [s.zip_code for s in scores]
        top_dso = None
        if zips_in_metro:
            dso_row = session.query(Practice.affiliated_dso, func.count(Practice.id).label("cnt")).filter(
                Practice.zip.in_(zips_in_metro),
                Practice.affiliated_dso.isnot(None)
            ).group_by(Practice.affiliated_dso).order_by(func.count(Practice.id).desc()).first()
            if dso_row:
                top_dso = dso_row[0]

        results.append({
            "metro_area": metro, "state": state, "zip_count": len(scores),
            "total_practices": total, "pe_backed": pe, "dso_affiliated": dso,
            "independent": indep, "unknown": unk,
            "consolidation_pct": round(consol, 1), "consolidation_pct_of_total": round(consol_total, 1),
            "independent_pct_of_total": round(indep_pct_total, 1),
            "data_confidence": confidence, "qoq_change": qoq,
            "ada_hpi_benchmark": ada_benchmark, "top_dso": top_dso,
            "opportunity_score": round(avg_opp, 1),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# PART 5 — EXPORTS AND BACKUP
# ═══════════════════════════════════════════════════════════════════════════


def export_and_backup(session):
    os.makedirs(COMBINED_DIR, exist_ok=True)

    deals_df = pd.read_sql(session.query(Deal).statement, session.bind)
    deals_path = os.path.join(COMBINED_DIR, "all_dental_pe_deals.csv")
    deals_df.to_csv(deals_path, index=False)

    practices_df = pd.read_sql(session.query(Practice).statement, session.bind)
    practices_path = os.path.join(COMBINED_DIR, "all_dental_practices.csv")
    practices_df.to_csv(practices_path, index=False)

    scores_exported = 0
    if table_exists("zip_scores"):
        scores_df = pd.read_sql("SELECT * FROM zip_scores", session.bind)
        scores_df.to_csv(os.path.join(COMBINED_DIR, "zip_consolidation_scores.csv"), index=False)
        scores_exported = len(scores_df)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"dental_pe_tracker_{date.today()}.db")
    shutil.copy2(DB_PATH, backup_path)

    log.info("Exported %d deals, %d practices, %d scores. Backup: %s",
             len(deals_df), len(practices_df), scores_exported, backup_path)
    return {"deals_exported": len(deals_df), "practices_exported": len(practices_df),
            "scores_exported": scores_exported, "backup_path": backup_path}


# ═══════════════════════════════════════════════════════════════════════════
# PART 6 — TERMINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


def print_summary(session, metro_results, dedup_stats, export_stats):
    total_deals = session.query(Deal).count()
    total_practices = session.query(Practice).count()

    print()
    print("=" * 55)
    print("  CONSOLIDATION INTELLIGENCE SUMMARY")
    print("=" * 55)
    print(f"  Total deals in database:    {total_deals:,}")
    print(f"  Total practices tracked:    {total_practices:,}")

    if total_practices > 0:
        for status in ("pe_backed", "dso_affiliated", "independent", "unknown"):
            cnt = session.query(Practice).filter(Practice.ownership_status == status).count()
            pct = cnt / total_practices * 100
            label = status.replace("_", "-").title()
            print(f"    {label:20} {cnt:>8,}  ({pct:5.1f}%)")
    else:
        print("  No practice data loaded. Run NPPES downloader first.")

    # Metro sections
    if metro_results:
        for m in metro_results:
            print()
            print(f"  {m['metro_area'].upper()} ({m['zip_count']} ZIPs tracked):")
            unk_pct = (m['unknown'] / m['total_practices'] * 100) if m['total_practices'] > 0 else 0
            print(f"    Total practices:              {m['total_practices']:,}")
            print(f"    Consolidated:                 {m['consolidation_pct_of_total']:.1f}% of total practices (DSO + PE)")
            print(f"    Independent:                  {m['independent_pct_of_total']:.1f}% of total practices")
            print(f"    Unclassified:                 {unk_pct:.1f}%")
            ada = f"{m['ada_hpi_benchmark']:.1f}%" if m.get("ada_hpi_benchmark") is not None else "not loaded"
            print(f"    ADA HPI {m['state'] or '??'} benchmark:       {ada}")
            qoq = f"{m['qoq_change']:+.1f}%" if m.get("qoq_change") is not None else "first run"
            print(f"    QoQ change:                   {qoq}")
            print(f"    Top DSO presence:             {m.get('top_dso') or 'none detected'}")
            print(f"    Opportunity score:            {m['opportunity_score']:.1f}")
    elif total_practices > 0:
        print("\n  No watched ZIPs scored (run NPPES + classifier first).")

    # Footer
    print()
    dd = dedup_stats
    print(f"  Deals: {dd['total_deals']:,} total, {dd['duplicates_merged']} merged, {dd['needs_review']} flagged for review")
    ex = export_stats
    print(f"  Exports: {ex['deals_exported']:,} deals, {ex['practices_exported']:,} practices, {ex['scores_exported']} scores → /data/combined/")
    print(f"  Backup: {ex['backup_path']}")
    print("=" * 55)
    print()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


def run():
    _t0 = log_scrape_start("merge_and_score")
    log.info("=" * 60)
    log.info("Merge and Score starting")
    log.info("=" * 60)

    init_db()
    session = get_session()

    # Part 1
    log.info("Part 1: Deduplicating deals...")
    dedup_stats = deduplicate_deals(session)

    # Part 2
    log.info("Part 2: Enriching platforms and sponsors...")
    enrich_platforms_and_sponsors(session)

    # Part 3 + 4 — only if practices exist
    metro_results = []
    practice_count = session.query(Practice).count()
    if practice_count > 0:
        log.info("Part 3: Scoring watched ZIPs...")
        ensure_chicagoland_watched(session)
        score_watched_zips(session)

        log.info("Part 4: Metro area rollup...")
        metro_results = metro_rollup(session)
    else:
        log.info("No practices loaded — skipping Parts 3-4.")

    # Part 5
    log.info("Part 5: Exporting and backing up...")
    export_stats = export_and_backup(session)

    # Part 6
    print_summary(session, metro_results, dedup_stats, export_stats)

    session.close()
    log_scrape_complete("merge_and_score", _t0,
                        summary=f"Merge & Score: dedup={dedup_stats}, practices={practice_count}",
                        extra={"dedup_stats": str(dedup_stats), "practice_count": practice_count})
    log.info("Merge and Score complete.")


if __name__ == "__main__":
    run()
