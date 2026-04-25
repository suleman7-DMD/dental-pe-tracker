import os
import shutil
from datetime import datetime, date

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    event,
    func,
    inspect,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from scrapers.logger_config import get_logger

log = get_logger("database")

# Works both locally (~/) and on Streamlit Cloud (relative to package)
BASE_DIR = os.environ.get("DENTAL_PE_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "dental_pe_tracker.db")
DB_GZ_PATH = DB_PATH + ".gz"
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# Postgres dual-mode support: only active when both URL and USE_POSTGRES flag are set
_POSTGRES_URL = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
_USE_POSTGRES = bool(_POSTGRES_URL) and os.environ.get("USE_POSTGRES", "").lower() in ("1", "true", "yes")


def _ensure_db_decompressed():
    """If only the .gz file exists (e.g. Streamlit Cloud), decompress it."""
    if not os.path.exists(DB_PATH) and os.path.exists(DB_GZ_PATH):
        import gzip
        tmp_path = DB_PATH + ".tmp"
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            log.info("Decompressing %s → %s", DB_GZ_PATH, DB_PATH)
            with gzip.open(DB_GZ_PATH, "rb") as f_in:
                with open(tmp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.rename(tmp_path, DB_PATH)
            log.info("Database decompressed (%d MB)", os.path.getsize(DB_PATH) // (1024 * 1024))
        except Exception as e:
            log.error("Failed to decompress database: %s", e)
            raise
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


_ensure_db_decompressed()

Base = declarative_base()


# ── Models ──────────────────────────────────────────────────────────────────


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deal_date = Column(Date)
    platform_company = Column(Text, nullable=False)
    pe_sponsor = Column(Text)
    target_name = Column(Text)
    target_city = Column(Text)
    target_state = Column(Text)
    target_zip = Column(Text)
    deal_type = Column(Text)  # buyout, add-on, recapitalization, growth, de_novo, partnership, other
    deal_size_mm = Column(Float)
    ebitda_multiple = Column(Float)
    specialty = Column(Text)
    num_locations = Column(Integer)
    source = Column(Text, nullable=False)
    source_url = Column(Text)
    notes = Column(Text)
    raw_text = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # UNIQUE on (platform_company, target_name, deal_date) only when target_name is not null
    # Handled via conditional index below


class Practice(Base):
    __tablename__ = "practices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    npi = Column(Text, unique=True, nullable=False)
    practice_name = Column(Text)
    doing_business_as = Column(Text)
    entity_type = Column(Text)
    address = Column(Text)
    city = Column(Text)
    state = Column(Text)
    zip = Column(Text)
    phone = Column(Text)
    taxonomy_code = Column(Text)
    taxonomy_description = Column(Text)
    enumeration_date = Column(Date)
    last_updated = Column(Date)
    ownership_status = Column(Text)  # independent, dso_affiliated, pe_backed, unknown
    affiliated_dso = Column(Text)
    affiliated_pe_sponsor = Column(Text)
    notes = Column(Text)
    data_source = Column(Text)  # nppes, data_axle, manual
    latitude = Column(Float)
    longitude = Column(Float)
    # Data Axle enrichment fields
    year_established = Column(Integer)
    employee_count = Column(Integer)
    estimated_revenue = Column(Float)
    num_providers = Column(Integer)
    location_type = Column(Text)
    buyability_score = Column(Float)
    classification_confidence = Column(Float)
    classification_reasoning = Column(Text)
    data_axle_raw_name = Column(Text)
    data_axle_import_date = Column(Date)
    raw_record_count = Column(Integer)
    import_batch_id = Column(Text)
    # Data Axle high-value fields
    parent_company = Column(Text)
    parent_iusa = Column(Text)
    ein = Column(Text)
    franchise_name = Column(Text)
    iusa_number = Column(Text)
    website = Column(Text)
    # Phase 1: Provider last name (populated from NPPES "Provider Last Name" for individuals)
    provider_last_name = Column(Text, nullable=True)
    # Phase 1: Entity classification (populated by dso_classifier.py second pass)
    # Values: solo_established, solo_new, solo_inactive, solo_high_volume,
    #         family_practice, small_group, large_group,
    #         dso_regional, dso_national, specialist, non_clinical
    entity_classification = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ZipOverview(Base):
    __tablename__ = "zip_overviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zip_code = Column(Text, unique=True, nullable=False)
    overview_html = Column(Text)
    created_at = Column(DateTime, default=func.now())


class PracticeChange(Base):
    __tablename__ = "practice_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    npi = Column(Text, ForeignKey("practices.npi"), nullable=False)
    change_date = Column(Date)
    field_changed = Column(Text)
    old_value = Column(Text)
    new_value = Column(Text)
    change_type = Column(Text)  # acquisition, name_change, relocation, closure, new_practice, unknown
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())


class PESponsor(Base):
    __tablename__ = "pe_sponsors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    also_known_as = Column(Text)
    hq_city = Column(Text)
    hq_state = Column(Text)
    aum_estimate_bn = Column(Float)
    healthcare_focus = Column(Boolean, default=False)
    notes = Column(Text)


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    pe_sponsor_name = Column(Text)
    hq_state = Column(Text)
    estimated_locations = Column(Integer)
    states_active = Column(Text)
    specialties = Column(Text)
    founded_year = Column(Integer)
    notes = Column(Text)


class ADAHPIBenchmark(Base):
    __tablename__ = "ada_hpi_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_year = Column(Integer, nullable=False)
    state = Column(Text, nullable=False)
    career_stage = Column(Text, nullable=False)  # all, early_career_lt10, mid_career_10_25, late_career_gt25
    total_dentists = Column(Integer)
    pct_dso_affiliated = Column(Float)
    pct_solo_practice = Column(Float)
    pct_group_practice = Column(Float)
    pct_large_group_10plus = Column(Float)
    source_file = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("data_year", "state", "career_stage", name="uix_ada_hpi"),
    )


class DSOLocation(Base):
    __tablename__ = "dso_locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dso_name = Column(Text, nullable=False)
    location_name = Column(Text)
    address = Column(Text)
    city = Column(Text)
    state = Column(Text)
    zip = Column(Text)
    phone = Column(Text)
    scraped_at = Column(DateTime, default=func.now())
    source_url = Column(Text)


class ZipScore(Base):
    __tablename__ = "zip_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zip_code = Column(Text, nullable=False)
    city = Column(Text)
    state = Column(Text)
    metro_area = Column(Text)
    total_practices = Column(Integer)
    pe_backed_count = Column(Integer)
    dso_affiliated_count = Column(Integer)
    independent_count = Column(Integer)
    unknown_count = Column(Integer)
    institutional_count = Column(Integer)
    raw_npi_count = Column(Integer)
    classified_count = Column(Integer)
    consolidation_pct = Column(Float)
    consolidation_pct_of_total = Column(Float)
    independent_pct_of_total = Column(Float)      # independent_count / total_practices * 100
    pe_penetration_pct = Column(Float)
    pct_unknown = Column(Float)
    recent_changes_90d = Column(Integer)
    state_deal_count_12m = Column(Integer)
    score_date = Column(Date)
    opportunity_score = Column(Float)
    data_confidence = Column(Text)
    # New columns for address-level dedup and consolidation analysis
    consolidated_count = Column(Integer)          # pe_backed_count + dso_affiliated_count
    unclassified_pct = Column(Float)              # unknown_count / total_practices * 100
    # Phase 1: Saturation metrics (computed by merge_and_score.py)
    total_gp_locations = Column(Integer, nullable=True)
    total_specialist_locations = Column(Integer, nullable=True)
    dld_gp_per_10k = Column(Float, nullable=True)
    dld_total_per_10k = Column(Float, nullable=True)
    people_per_gp_door = Column(Integer, nullable=True)
    # Ownership structure metrics
    buyable_practice_count = Column(Integer, nullable=True)
    buyable_practice_ratio = Column(Float, nullable=True)
    corporate_location_count = Column(Integer, nullable=True)
    corporate_share_pct = Column(Float, nullable=True)
    family_practice_count = Column(Integer, nullable=True)
    specialist_density_flag = Column(Boolean, nullable=True)
    # Data quality
    entity_classification_coverage_pct = Column(Float, nullable=True)
    data_axle_enrichment_pct = Column(Float, nullable=True)
    metrics_confidence = Column(Text, nullable=True)
    # Market classification
    market_type = Column(Text, nullable=True)
    market_type_confidence = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("zip_code", "score_date", name="uq_zip_score_date"),
    )


class WatchedZip(Base):
    __tablename__ = "watched_zips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zip_code = Column(Text, nullable=False, unique=True)
    city = Column(Text)
    state = Column(Text)
    metro_area = Column(Text)
    notes = Column(Text)
    # Phase 1: Demographic columns (populated by census_loader.py)
    population = Column(Integer, nullable=True)
    median_household_income = Column(Integer, nullable=True)
    population_growth_pct = Column(Float, nullable=True)
    demographics_updated_at = Column(DateTime, nullable=True)


class ZipQualitativeIntel(Base):
    __tablename__ = "zip_qualitative_intel"

    zip_code = Column(Text, ForeignKey("watched_zips.zip_code"), primary_key=True)
    research_date = Column(Text, nullable=False)
    # Housing & Development
    housing_status = Column(Text)
    housing_developments = Column(Text)
    housing_summary = Column(Text)
    # Schools
    school_district = Column(Text)
    school_rating = Column(Text)
    school_source = Column(Text)
    school_note = Column(Text)
    # Retail & Income Signals
    retail_premium = Column(Text)
    retail_mass = Column(Text)
    retail_income_signal = Column(Text)
    # Commercial Development
    commercial_status = Column(Text)
    commercial_projects = Column(Text)
    commercial_note = Column(Text)
    # Dental-Specific News
    dental_new_offices = Column(Text)
    dental_dso_moves = Column(Text)
    dental_note = Column(Text)
    # Real Estate
    median_home_price = Column(Integer)
    home_price_trend = Column(Text)
    home_price_yoy_pct = Column(Float)
    real_estate_source = Column(Text)
    # Zoning & Planning
    zoning_items = Column(Text)
    zoning_note = Column(Text)
    # Population Signals
    pop_growth_signals = Column(Text)
    pop_demographics = Column(Text)
    pop_note = Column(Text)
    # Employment & Insurance
    major_employers = Column(Text)
    insurance_signal = Column(Text)
    # Competition
    competitor_new = Column(Text)
    competitor_closures = Column(Text)
    competitor_note = Column(Text)
    # Synthesis
    demand_outlook = Column(Text)
    supply_outlook = Column(Text)
    investment_thesis = Column(Text)
    confidence = Column(Text)
    sources = Column(Text)
    # Metadata
    research_method = Column(Text)
    raw_json = Column(Text)
    cost_usd = Column(Float)
    model_used = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PracticeIntel(Base):
    __tablename__ = "practice_intel"

    npi = Column(Text, ForeignKey("practices.npi"), primary_key=True)
    research_date = Column(Text, nullable=False)
    # Website Analysis
    website_url = Column(Text)
    website_era = Column(Text)
    website_last_update = Column(Text)
    website_analysis = Column(Text)
    # Services & Technology
    services_listed = Column(Text)
    services_high_rev = Column(Text)
    services_note = Column(Text)
    technology_listed = Column(Text)
    technology_level = Column(Text)
    # Provider Info
    provider_count_web = Column(Integer)
    owner_career_stage = Column(Text)
    provider_notes = Column(Text)
    # Google Reviews
    google_review_count = Column(Integer)
    google_rating = Column(Float)
    google_recent_date = Column(Text)
    google_velocity = Column(Text)
    google_sentiment = Column(Text)
    # Hiring Signals
    hiring_active = Column(Integer, default=0)
    hiring_positions = Column(Text)
    hiring_source = Column(Text)
    # Acquisition News
    acquisition_found = Column(Integer, default=0)
    acquisition_details = Column(Text)
    # Social Media
    social_facebook = Column(Text)
    social_instagram = Column(Text)
    social_other = Column(Text)
    # Other Profiles
    healthgrades_rating = Column(Float)
    healthgrades_reviews = Column(Integer)
    zocdoc_listed = Column(Integer, default=0)
    # Doctor Profile
    doctor_publications = Column(Integer, default=0)
    doctor_speaking = Column(Integer, default=0)
    doctor_associations = Column(Text)
    doctor_notes = Column(Text)
    # Insurance Signals
    accepts_medicaid = Column(Integer)
    ppo_heavy = Column(Integer)
    insurance_note = Column(Text)
    # Launchpad Phase 3 — job-hunt grad-specific fields
    succession_intent_detected = Column(String(20), index=True)   # "active_seeking"|"receptive"|"unclear"|"not_considering"|"unknown"
    new_grad_friendly_score = Column(Integer)                      # 0-100
    mentorship_signals = Column(Text)                              # JSON array stringified
    associate_runway = Column(String(32))                          # "immediate"|"0-2 years"|"2-5 years"|"succession path"|"unclear"
    compensation_signals = Column(Text)                            # JSON object stringified
    red_flags_for_grad = Column(Text)                              # JSON array stringified
    green_flags_for_grad = Column(Text)                            # JSON array stringified
    # Anti-hallucination verification (April 2026)
    verification_searches = Column(Integer)                        # actual web_search count Haiku reported running
    verification_quality = Column(String(20), index=True)          # "verified" | "partial" | "insufficient"
    verification_urls = Column(Text)                               # JSON array of primary source URLs cited
    is_verified = Column(Boolean, default=False, nullable=False)   # True iff generated with forced-search anti-hallucination protocol
    # Assessment
    red_flags = Column(Text)
    green_flags = Column(Text)
    overall_assessment = Column(Text)
    acquisition_readiness = Column(Text)
    confidence = Column(Text)
    sources = Column(Text)
    # Metadata
    research_method = Column(Text)
    escalated = Column(Integer, default=0)
    escalation_findings = Column(Text)
    raw_json = Column(Text)
    cost_usd = Column(Float)
    model_used = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PracticeSignal(Base):
    __tablename__ = "practice_signals"

    npi = Column(Text, primary_key=True)
    practice_id = Column(Integer)
    zip_code = Column(Text, nullable=False)
    practice_name = Column(Text)
    city = Column(Text)
    state = Column(Text)
    entity_classification = Column(Text)
    ownership_status = Column(Text)
    buyability_score = Column(Float)
    stealth_dso_flag = Column(Boolean, default=False)
    stealth_dso_cluster_id = Column(Text)
    stealth_dso_cluster_size = Column(Integer)
    stealth_dso_zip_count = Column(Integer)
    stealth_dso_basis = Column(Text)
    stealth_dso_reasoning = Column(Text)
    phantom_inventory_flag = Column(Boolean, default=False)
    phantom_inventory_reasoning = Column(Text)
    revenue_default_flag = Column(Boolean, default=False)
    revenue_default_reasoning = Column(Text)
    family_dynasty_flag = Column(Boolean, default=False)
    family_dynasty_reasoning = Column(Text)
    micro_cluster_flag = Column(Boolean, default=False)
    micro_cluster_id = Column(Text)
    micro_cluster_size = Column(Integer)
    micro_cluster_reasoning = Column(Text)
    intel_quant_disagreement_flag = Column(Boolean, default=False)
    intel_quant_disagreement_type = Column(Text)
    intel_quant_disagreement_reasoning = Column(Text)
    retirement_combo_score = Column(Integer, default=0)
    retirement_combo_flag = Column(Boolean, default=False)
    retirement_combo_reasoning = Column(Text)
    deal_catchment_24mo = Column(Integer, default=0)
    deal_catchment_reasoning = Column(Text)
    last_change_90d_flag = Column(Boolean, default=False)
    last_change_date = Column(Text)
    last_change_type = Column(Text)
    last_change_reasoning = Column(Text)
    buyability_pctile_zip_class = Column(Float)
    buyability_pctile_class = Column(Float)
    retirement_pctile_zip_class = Column(Float)
    retirement_pctile_class = Column(Float)
    high_peer_buyability_flag = Column(Boolean, default=False)
    high_peer_retirement_flag = Column(Boolean, default=False)
    peer_percentile_reasoning = Column(Text)
    zip_white_space_flag = Column(Boolean, default=False)
    zip_compound_demand_flag = Column(Boolean, default=False)
    zip_contested_zone_flag = Column(Boolean, default=False)
    zip_ada_benchmark_gap_flag = Column(Boolean, default=False)
    data_limitations = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ZipSignal(Base):
    __tablename__ = "zip_signals"

    zip_code = Column(Text, primary_key=True)
    city = Column(Text)
    state = Column(Text)
    metro_area = Column(Text)
    population = Column(Integer)
    total_practices = Column(Integer)
    total_gp_locations = Column(Integer)
    total_specialist_locations = Column(Integer)
    dld_gp_per_10k = Column(Float)
    people_per_gp_door = Column(Integer)
    corporate_share_pct = Column(Float)
    buyable_practice_ratio = Column(Float)
    stealth_dso_practice_count = Column(Integer, default=0)
    stealth_dso_cluster_count = Column(Integer, default=0)
    phantom_inventory_count = Column(Integer, default=0)
    phantom_inventory_pct = Column(Float)
    revenue_default_count = Column(Integer, default=0)
    family_dynasty_count = Column(Integer, default=0)
    micro_cluster_count = Column(Integer, default=0)
    micro_cluster_practice_count = Column(Integer, default=0)
    intel_quant_disagreement_count = Column(Integer, default=0)
    retirement_combo_high_count = Column(Integer, default=0)
    last_change_90d_count = Column(Integer, default=0)
    deal_count_all_time = Column(Integer, default=0)
    deal_count_24mo = Column(Integer, default=0)
    deal_catchment_sum_24mo = Column(Integer, default=0)
    deal_catchment_max_24mo = Column(Integer, default=0)
    compound_demand_flag = Column(Boolean, default=False)
    compound_demand_score = Column(Integer, default=0)
    compound_demand_reasoning = Column(Text)
    mirror_pair_flag = Column(Boolean, default=False)
    mirror_pair_count = Column(Integer, default=0)
    top_mirror_zip = Column(Text)
    top_mirror_similarity = Column(Float)
    top_mirror_corporate_gap_pp = Column(Float)
    mirror_zips_json = Column(Text)
    mirror_reasoning = Column(Text)
    white_space_flag = Column(Boolean, default=False)
    white_space_score = Column(Integer, default=0)
    white_space_reasoning = Column(Text)
    contested_zone_flag = Column(Boolean, default=False)
    contested_platform_count = Column(Integer, default=0)
    contested_platforms_json = Column(Text)
    contested_zone_reasoning = Column(Text)
    ada_benchmark_pct = Column(Float)
    ada_benchmark_gap_pp = Column(Float)
    ada_benchmark_gap_flag = Column(Boolean, default=False)
    ada_benchmark_reasoning = Column(Text)
    high_peer_buyability_count = Column(Integer, default=0)
    high_peer_retirement_count = Column(Integer, default=0)
    data_limitations = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Engine / Session ────────────────────────────────────────────────────────


_cached_engines = {}


def get_engine(db_path=None, force_postgres=False):
    cache_key = (db_path, force_postgres)
    if cache_key in _cached_engines:
        return _cached_engines[cache_key]
    if force_postgres or (_USE_POSTGRES and db_path is None):
        if not _POSTGRES_URL:
            raise RuntimeError(
                "Postgres requested but no SUPABASE_DATABASE_URL or DATABASE_URL set"
            )
        engine = create_engine(
            _POSTGRES_URL,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=False,
        )
        _cached_engines[cache_key] = engine
        return engine
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    _cached_engines[cache_key] = engine
    return engine


def get_session(db_path=None, force_postgres=False) -> Session:
    engine = get_engine(db_path, force_postgres=force_postgres)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db(db_path=None, force_postgres=False):
    """Create all tables, indexes, and populate watched_zips if empty."""
    engine = get_engine(db_path, force_postgres=force_postgres)
    Base.metadata.create_all(engine)

    dialect = engine.dialect.name  # "sqlite" or "postgresql"

    with engine.connect() as conn:
        if dialect == "sqlite":
            # Partial unique index for deals dedup (SQLite syntax)
            conn.execute(__import__("sqlalchemy").text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uix_deal_no_dup "
                "ON deals (platform_company, target_name, deal_date) "
                "WHERE target_name IS NOT NULL"
            ))
        else:
            # Postgres: CREATE INDEX IF NOT EXISTS works the same way
            conn.execute(__import__("sqlalchemy").text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uix_deal_no_dup "
                "ON deals (platform_company, target_name, deal_date) "
                "WHERE target_name IS NOT NULL"
            ))
        # Performance indexes (syntax identical for SQLite and Postgres)
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_practices_zip ON practices (zip)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_practices_status ON practices (ownership_status)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_practices_state ON practices (state)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_practice_changes_npi ON practice_changes (npi)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_deals_state ON deals (target_state)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_deals_date ON deals (deal_date)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS ix_deals_source ON deals (source)"
        ))
        # Intel table indexes
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS idx_zip_intel_date ON zip_qualitative_intel(research_date)"
        ))
        conn.execute(__import__("sqlalchemy").text(
            "CREATE INDEX IF NOT EXISTS idx_practice_intel_date ON practice_intel(research_date)"
        ))
        # Migrate existing intel tables (may lack new columns if created by old raw sqlite3 code)
        for alter_stmt in [
            "ALTER TABLE zip_qualitative_intel ADD COLUMN created_at TIMESTAMP",
            "ALTER TABLE zip_qualitative_intel ADD COLUMN updated_at TIMESTAMP",
            "ALTER TABLE practice_intel ADD COLUMN created_at TIMESTAMP",
            "ALTER TABLE practice_intel ADD COLUMN updated_at TIMESTAMP",
            "ALTER TABLE practice_intel ADD COLUMN escalation_findings TEXT",
            "ALTER TABLE ada_hpi_benchmarks ADD COLUMN updated_at TIMESTAMP",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(alter_stmt))
            except Exception:
                pass  # Column already exists
        conn.commit()

    # Seed watched_zips
    session = get_session(db_path, force_postgres=force_postgres)
    try:
        if session.query(WatchedZip).count() == 0:
            _seed_watched_zips(session)
    finally:
        session.close()

    target = "Postgres" if (force_postgres or (_USE_POSTGRES and db_path is None)) else (db_path or DB_PATH)
    log.info("Database initialized at %s", target)


def _seed_watched_zips(session: Session):
    zips = [
        # Chicagoland
        ("60491", "Homer Glen", "IL", "Chicagoland"),
        ("60439", "Lemont", "IL", "Chicagoland"),
        ("60441", "Lockport", "IL", "Chicagoland"),
        ("60540", "Naperville", "IL", "Chicagoland"),
        ("60564", "Naperville", "IL", "Chicagoland"),
        ("60565", "Naperville", "IL", "Chicagoland"),
        ("60563", "Naperville", "IL", "Chicagoland"),
        ("60527", "Willowbrook", "IL", "Chicagoland"),
        ("60515", "Downers Grove", "IL", "Chicagoland"),
        ("60516", "Downers Grove", "IL", "Chicagoland"),
        ("60532", "Lisle", "IL", "Chicagoland"),
        ("60559", "Westmont", "IL", "Chicagoland"),
        ("60514", "Clarendon Hills", "IL", "Chicagoland"),
        ("60521", "Hinsdale", "IL", "Chicagoland"),
        ("60523", "Oak Brook", "IL", "Chicagoland"),
        ("60148", "Lombard", "IL", "Chicagoland"),
        ("60440", "Bolingbrook", "IL", "Chicagoland"),
        ("60490", "Bolingbrook", "IL", "Chicagoland"),
        ("60504", "Aurora", "IL", "Chicagoland"),
        ("60502", "Aurora", "IL", "Chicagoland"),
        ("60431", "Joliet", "IL", "Chicagoland"),
        ("60435", "Joliet", "IL", "Chicagoland"),
        ("60586", "Plainfield", "IL", "Chicagoland"),
        ("60585", "Plainfield", "IL", "Chicagoland"),
        ("60503", "Aurora", "IL", "Chicagoland"),
        ("60554", "Sugar Grove", "IL", "Chicagoland"),
        ("60543", "Oswego", "IL", "Chicagoland"),
        ("60560", "Yorkville", "IL", "Chicagoland"),
        # Boston Metro
        ("02116", "Boston-South End", "MA", "Boston Metro"),
        ("02115", "Boston-Back Bay", "MA", "Boston Metro"),
        ("02118", "Boston-South End", "MA", "Boston Metro"),
        ("02119", "Roxbury", "MA", "Boston Metro"),
        ("02120", "Mission Hill", "MA", "Boston Metro"),
        ("02215", "Fenway", "MA", "Boston Metro"),
        ("02134", "Allston", "MA", "Boston Metro"),
        ("02135", "Brighton", "MA", "Boston Metro"),
        ("02446", "Brookline", "MA", "Boston Metro"),
        ("02445", "Brookline", "MA", "Boston Metro"),
        ("02467", "Chestnut Hill", "MA", "Boston Metro"),
        ("02459", "Newton", "MA", "Boston Metro"),
        ("02458", "Newton", "MA", "Boston Metro"),
        ("02453", "Waltham", "MA", "Boston Metro"),
        ("02451", "Waltham", "MA", "Boston Metro"),
        ("02138", "Cambridge", "MA", "Boston Metro"),
        ("02139", "Cambridge", "MA", "Boston Metro"),
        ("02140", "Cambridge", "MA", "Boston Metro"),
        ("02141", "East Cambridge", "MA", "Boston Metro"),
        ("02142", "Kendall Sq", "MA", "Boston Metro"),
        ("02144", "Somerville", "MA", "Boston Metro"),
    ]
    for zip_code, city, state, metro in zips:
        session.add(WatchedZip(zip_code=zip_code, city=city, state=state, metro_area=metro))
    session.commit()
    log.info("Seeded %d watched ZIP codes", len(zips))


# ── Helper Functions ────────────────────────────────────────────────────────


# Curly/smart punctuation that leaks in from copy-pasted web prose.
# Normalizing at the scraper boundary keeps "Smith's Dental" (U+2019) and
# "Smith's Dental" (U+0027) from de-duplicating as different entities.
_PUNCT_TRANSLATIONS = str.maketrans({
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark
    "‚": "'",  # single low-9 quotation mark
    "‛": "'",  # single high-reversed-9 quotation mark
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "„": '"',  # double low-9 quotation mark
    "‟": '"',  # double high-reversed-9 quotation mark
})


def normalize_punctuation(text):
    """Translate curly quotes/apostrophes to ASCII. Pass None through unchanged."""
    if text is None:
        return None
    return text.translate(_PUNCT_TRANSLATIONS)


def insert_deal(session: Session, **kwargs) -> bool:
    """Insert a deal. Returns True if inserted, False if duplicate."""
    # Dedup: same platform_company + deal_date + source + target_name + target_state
    platform = kwargs.get("platform_company")
    deal_date = kwargs.get("deal_date")
    source = kwargs.get("source")
    target_name = kwargs.get("target_name")
    target_state = kwargs.get("target_state")
    if platform and deal_date:
        filters = [
            Deal.platform_company == platform,
            Deal.deal_date == deal_date,
            Deal.source == source,
        ]
        if target_name is None:
            filters.append(Deal.target_name.is_(None))
        else:
            filters.append(Deal.target_name == target_name)
        if target_state:
            filters.append(Deal.target_state == target_state)
        existing = session.query(Deal).filter(*filters).first()
        if existing:
            log.warning("Duplicate deal skipped: %s / %s on %s", platform, target_name, deal_date)
            return False
    try:
        deal = Deal(**kwargs)
        session.add(deal)
        session.commit()
        log.info("Inserted deal: %s / %s", kwargs.get("platform_company"), kwargs.get("target_name"))
        return True
    except Exception as e:
        session.rollback()
        if "UNIQUE constraint" in str(e) or "duplicate key" in str(e):
            log.warning("Duplicate deal skipped: %s / %s", kwargs.get("platform_company"), kwargs.get("target_name"))
            return False
        log.error("Failed to insert deal: %s", e)
        raise


def insert_or_update_practice(session: Session, **kwargs) -> Practice:
    """Upsert a practice by NPI."""
    npi = kwargs.get("npi")
    existing = session.query(Practice).filter_by(npi=npi).first()
    if existing:
        for key, value in kwargs.items():
            if key != "npi" and value is not None:
                setattr(existing, key, value)
        existing.updated_at = datetime.now()
        session.commit()
        log.info("Updated practice NPI %s", npi)
        return existing
    else:
        practice = Practice(**kwargs)
        session.add(practice)
        session.commit()
        log.info("Inserted practice NPI %s", npi)
        return practice


def log_practice_change(session: Session, **kwargs):
    """Record a change in practice_changes."""
    change = PracticeChange(**kwargs)
    session.add(change)
    session.commit()
    log.info("Logged change for NPI %s: %s", kwargs.get("npi"), kwargs.get("field_changed"))


def get_deals(session: Session, **filters) -> list:
    """Flexible filtering on deals. Pass column_name=value pairs."""
    query = session.query(Deal)
    for key, value in filters.items():
        if hasattr(Deal, key):
            query = query.filter(getattr(Deal, key) == value)
    return query.all()


def get_practices(session: Session, zip_codes=None, state=None, ownership_status=None) -> list:
    query = session.query(Practice)
    if zip_codes:
        query = query.filter(Practice.zip.in_(zip_codes))
    if state:
        query = query.filter(Practice.state == state)
    if ownership_status:
        query = query.filter(Practice.ownership_status == ownership_status)
    return query.all()


def get_practice_changes(session: Session, zip_codes=None, since_date=None) -> list:
    query = session.query(PracticeChange)
    if zip_codes:
        query = query.join(Practice, PracticeChange.npi == Practice.npi).filter(
            Practice.zip.in_(zip_codes)
        )
    if since_date:
        query = query.filter(PracticeChange.change_date >= since_date)
    return query.all()


def get_deal_stats(session: Session) -> dict:
    """Summary statistics for deals."""
    total = session.query(Deal).count()
    by_type = {}
    for row in session.query(Deal.deal_type, func.count(Deal.id)).group_by(Deal.deal_type).all():
        by_type[row[0]] = row[1]

    by_state = {}
    for row in session.query(Deal.target_state, func.count(Deal.id)).group_by(Deal.target_state).all():
        by_state[row[0]] = row[1]

    avg_size = session.query(func.avg(Deal.deal_size_mm)).filter(Deal.deal_size_mm.isnot(None)).scalar()
    avg_multiple = session.query(func.avg(Deal.ebitda_multiple)).filter(Deal.ebitda_multiple.isnot(None)).scalar()

    sponsors = session.query(Deal.pe_sponsor).distinct().filter(Deal.pe_sponsor.isnot(None)).count()

    return {
        "total_deals": total,
        "by_deal_type": by_type,
        "by_state": by_state,
        "avg_deal_size_mm": round(avg_size, 2) if avg_size else None,
        "avg_ebitda_multiple": round(avg_multiple, 2) if avg_multiple else None,
        "unique_pe_sponsors": sponsors,
    }


def get_consolidation_score(session: Session, zip_code: str) -> float:
    """Returns % of practices in a ZIP that are DSO-affiliated or PE-backed."""
    total = session.query(Practice).filter(Practice.zip == zip_code).count()
    if total == 0:
        return 0.0
    consolidated = (
        session.query(Practice)
        .filter(Practice.zip == zip_code)
        .filter(Practice.ownership_status.in_(["dso_affiliated", "pe_backed"]))
        .count()
    )
    return round((consolidated / total) * 100, 1)


def table_exists(table_name):
    """Check if a table exists in the database."""
    engine = get_engine()
    insp = inspect(engine)
    return table_name in insp.get_table_names()


def backup_database(db_path=None):
    """Copy database to backups/ with timestamp."""
    src = db_path or DB_PATH
    if not os.path.exists(src):
        log.warning("No database to backup at %s", src)
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"dental_pe_tracker_{timestamp}.db")
    shutil.copy2(src, dest)
    log.info("Backup created: %s", dest)
    return dest
