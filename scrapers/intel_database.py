"""
CRUD functions for qualitative intelligence tables.

Uses SQLAlchemy models from scrapers.database (ZipQualitativeIntel, PracticeIntel).
Tables are created by Base.metadata.create_all() in init_db().
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from scrapers.database import get_session, DB_PATH, ZipQualitativeIntel, PracticeIntel
from scrapers.logger_config import get_logger

logger = get_logger("intel_database")

DEFAULT_CACHE_TTL_DAYS = 90


# ── Backward Compatibility Stubs ──────────────────────────────────────────


def get_db_path():
    """Backward compatibility. Callers should migrate to get_session()."""
    return DB_PATH


def ensure_intel_tables(db_path=None):
    """No-op stub. Tables are now created by Base.metadata.create_all() in init_db()."""
    pass


# ── Storage Functions ────────────────────────────────────────────────────


def store_zip_intel(zip_code: str, research_data: Dict, db_path=None):
    """Store ZIP qualitative research results. Upserts via session.merge()."""
    session = get_session(db_path)
    try:
        meta = research_data.get("_meta", {})
        now = datetime.now().isoformat()

        housing = research_data.get("housing", {})
        schools = research_data.get("schools", {})
        retail = research_data.get("retail", {})
        commercial = research_data.get("commercial", {})
        dental = research_data.get("dental_news", {})
        re_data = research_data.get("real_estate", {})
        zoning = research_data.get("zoning", {})
        pop = research_data.get("population", {})
        emp = research_data.get("employers", {})
        comp = research_data.get("competitors", {})

        obj = ZipQualitativeIntel(
            zip_code=zip_code,
            research_date=now,
            housing_status=housing.get("status"),
            housing_developments=_jdump(housing.get("developments")),
            housing_summary=housing.get("summary"),
            school_district=schools.get("district"),
            school_rating=schools.get("rating"),
            school_source=schools.get("source"),
            school_note=schools.get("note"),
            retail_premium=_jdump(retail.get("premium")),
            retail_mass=_jdump(retail.get("mass")),
            retail_income_signal=retail.get("income_signal"),
            commercial_status=commercial.get("status"),
            commercial_projects=_jdump(commercial.get("projects")),
            commercial_note=commercial.get("note"),
            dental_new_offices=_jdump(dental.get("new_offices")),
            dental_dso_moves=_jdump(dental.get("dso_moves")),
            dental_note=dental.get("note"),
            median_home_price=_safe_int(re_data.get("median_price")),
            home_price_trend=re_data.get("trend"),
            home_price_yoy_pct=_safe_float(re_data.get("yoy_pct")),
            real_estate_source=re_data.get("source"),
            zoning_items=_jdump(zoning.get("items")),
            zoning_note=zoning.get("note"),
            pop_growth_signals=_jdump(pop.get("growth_signals")),
            pop_demographics=pop.get("demographics"),
            pop_note=pop.get("note"),
            major_employers=_jdump(emp.get("major_nearby")),
            insurance_signal=emp.get("insurance_signal"),
            competitor_new=_jdump(comp.get("new_opens")),
            competitor_closures=_jdump(comp.get("closures")),
            competitor_note=comp.get("note"),
            demand_outlook=research_data.get("demand_outlook"),
            supply_outlook=research_data.get("supply_outlook"),
            investment_thesis=research_data.get("investment_thesis"),
            confidence=research_data.get("confidence"),
            sources=_jdump(research_data.get("sources")),
            research_method=f"claude_api_{meta.get('model','unknown').split('-')[1] if '-' in meta.get('model','') else 'unknown'}",
            raw_json=json.dumps(research_data, default=str),
            cost_usd=meta.get("cost_usd", 0),
            model_used=meta.get("model"),
        )
        session.merge(obj)
        session.commit()
        logger.info("Stored ZIP intel for %s", zip_code)
    except Exception as e:
        session.rollback()
        logger.error("Failed to store ZIP intel for %s: %s", zip_code, e)
        raise
    finally:
        session.close()


def store_practice_intel(npi: str, research_data: Dict, db_path=None):
    """Store practice deep dive results. Upserts via session.merge()."""
    session = get_session(db_path)
    try:
        meta = research_data.get("_meta", {})
        now = datetime.now().isoformat()

        web = research_data.get("website", {})
        svc = research_data.get("services", {})
        tech = research_data.get("technology", {})
        prov = research_data.get("providers", {})
        goog = research_data.get("google", {})
        hire = research_data.get("hiring", {})
        acq = research_data.get("acquisition_news", {})
        soc = research_data.get("social", {})
        hg = research_data.get("healthgrades", {})
        zd = research_data.get("zocdoc", {})
        doc = research_data.get("doctor", {})
        ins = research_data.get("insurance", {})
        ver = research_data.get("verification", {}) or {}

        obj = PracticeIntel(
            npi=npi,
            research_date=now,
            website_url=web.get("url"),
            website_era=web.get("era"),
            website_last_update=web.get("last_update"),
            website_analysis=web.get("analysis"),
            services_listed=_jdump(svc.get("listed")),
            services_high_rev=_jdump(svc.get("high_revenue")),
            services_note=svc.get("note"),
            technology_listed=_jdump(tech.get("listed")),
            technology_level=tech.get("level"),
            provider_count_web=_safe_int(prov.get("web_count")),
            owner_career_stage=prov.get("owner_stage"),
            provider_notes=prov.get("notes"),
            google_review_count=_safe_int(goog.get("reviews")),
            google_rating=_safe_float(goog.get("rating")),
            google_recent_date=goog.get("recent_date"),
            google_velocity=goog.get("velocity"),
            google_sentiment=goog.get("sentiment"),
            hiring_active=1 if hire.get("active") else 0,
            hiring_positions=_jdump(hire.get("positions")),
            hiring_source=hire.get("source"),
            acquisition_found=1 if acq.get("found") else 0,
            acquisition_details=acq.get("details"),
            social_facebook=soc.get("facebook"),
            social_instagram=soc.get("instagram"),
            social_other=soc.get("other"),
            healthgrades_rating=_safe_float(hg.get("rating")),
            healthgrades_reviews=_safe_int(hg.get("reviews")),
            zocdoc_listed=1 if zd.get("listed") else 0,
            doctor_publications=1 if doc.get("publications") else 0,
            doctor_speaking=1 if doc.get("speaking") else 0,
            doctor_associations=_jdump(doc.get("associations")),
            doctor_notes=doc.get("notes"),
            accepts_medicaid=_bool_to_int(ins.get("medicaid")),
            ppo_heavy=_bool_to_int(ins.get("ppo_heavy")),
            insurance_note=ins.get("note"),
            red_flags=_jdump(research_data.get("red_flags")),
            green_flags=_jdump(research_data.get("green_flags")),
            overall_assessment=research_data.get("assessment"),
            acquisition_readiness=research_data.get("readiness"),
            confidence=research_data.get("confidence"),
            sources=_jdump(research_data.get("sources")),
            research_method=f"claude_api_{meta.get('model','unknown').split('-')[1] if '-' in meta.get('model','') else 'unknown'}",
            escalated=1 if research_data.get("_escalated") else 0,
            escalation_findings=research_data.get("escalation_findings"),
            raw_json=json.dumps(research_data, default=str),
            cost_usd=meta.get("cost_usd", 0),
            model_used=meta.get("model"),
            # Launchpad Phase 3 — job-hunt grad-specific fields
            succession_intent_detected=research_data.get("succession_intent"),
            new_grad_friendly_score=_safe_int(research_data.get("new_grad_friendly_score")),
            mentorship_signals=_jdump(research_data.get("mentorship_signals")),
            associate_runway=research_data.get("associate_runway"),
            compensation_signals=_jdump(research_data.get("compensation_signals")),
            red_flags_for_grad=_jdump(research_data.get("red_flags_for_grad")),
            green_flags_for_grad=_jdump(research_data.get("green_flags_for_grad")),
            # Anti-hallucination verification block (April 2026)
            verification_searches=_safe_int(ver.get("searches_executed")),
            verification_quality=ver.get("evidence_quality"),
            verification_urls=_jdump(ver.get("primary_sources")),
            is_verified=bool(ver and _safe_int(ver.get("searches_executed", 0))),
        )
        session.merge(obj)
        session.commit()
        logger.info("Stored practice intel for NPI %s", npi)
    except Exception as e:
        session.rollback()
        logger.error("Failed to store practice intel for NPI %s: %s", npi, e)
        raise
    finally:
        session.close()


# ── Retrieval Functions ──────────────────────────────────────────────────


def get_zip_intel(zip_code: str, db_path=None) -> Optional[Dict]:
    """Retrieve cached ZIP intel. Returns dict or None."""
    session = get_session(db_path)
    try:
        row = session.get(ZipQualitativeIntel, zip_code)
        if row:
            return {c.key: getattr(row, c.key) for c in ZipQualitativeIntel.__table__.columns}
        return None
    finally:
        session.close()


def get_practice_intel(npi: str, db_path=None) -> Optional[Dict]:
    """Retrieve cached practice intel. Returns dict or None."""
    session = get_session(db_path)
    try:
        row = session.get(PracticeIntel, npi)
        if row:
            return {c.key: getattr(row, c.key) for c in PracticeIntel.__table__.columns}
        return None
    finally:
        session.close()


def is_cache_fresh(research_date_str: Optional[str], ttl_days: int = DEFAULT_CACHE_TTL_DAYS) -> bool:
    """Check if cached research is still fresh."""
    if not research_date_str:
        return False
    try:
        dt = datetime.fromisoformat(research_date_str)
        return (datetime.now() - dt) < timedelta(days=ttl_days)
    except Exception:
        return False


def get_all_zip_intel(db_path=None) -> List[Dict]:
    """Get all ZIP intel records (for dashboard display)."""
    session = get_session(db_path)
    try:
        rows = session.query(ZipQualitativeIntel).order_by(ZipQualitativeIntel.zip_code).all()
        return [
            {c.key: getattr(row, c.key) for c in ZipQualitativeIntel.__table__.columns}
            for row in rows
        ]
    finally:
        session.close()


def get_researched_practice_npis(db_path=None) -> List[str]:
    """Get list of NPIs that have been researched."""
    session = get_session(db_path)
    try:
        rows = session.query(PracticeIntel.npi).all()
        return [r[0] for r in rows]
    finally:
        session.close()


# ── Helpers ──────────────────────────────────────────────────────────────




def _safe_int(val):
    """Safely convert to int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        import re as _re
        m = _re.search(r"[0-9]+", str(val))
        return int(m.group()) if m else None


def _safe_float(val):
    """Safely convert to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        import re as _re
        m = _re.search(r"[0-9.]+", str(val))
        return float(m.group()) if m else None
def _jdump(val):
    """JSON-dump a value if it's a list/dict, otherwise return as-is."""
    if isinstance(val, (list, dict)):
        return json.dumps(val)
    return val


def _bool_to_int(val):
    """Convert boolean/None to int for SQLite."""
    if val is None:
        return None
    return 1 if val else 0
