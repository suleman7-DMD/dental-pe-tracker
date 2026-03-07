import os
import shutil
from datetime import datetime, date

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
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


def _ensure_db_decompressed():
    """If only the .gz file exists (e.g. Streamlit Cloud), decompress it."""
    if not os.path.exists(DB_PATH) and os.path.exists(DB_GZ_PATH):
        import gzip
        log.info("Decompressing %s → %s", DB_GZ_PATH, DB_PATH)
        with gzip.open(DB_GZ_PATH, "rb") as f_in:
            with open(DB_PATH, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        log.info("Database decompressed (%d MB)", os.path.getsize(DB_PATH) // (1024 * 1024))


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


class WatchedZip(Base):
    __tablename__ = "watched_zips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zip_code = Column(Text, nullable=False)
    city = Column(Text)
    state = Column(Text)
    metro_area = Column(Text)
    notes = Column(Text)


# ── Engine / Session ────────────────────────────────────────────────────────


def get_engine(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    return engine


def get_session(db_path=None) -> Session:
    engine = get_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db(db_path=None):
    """Create all tables, indexes, and populate watched_zips if empty."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        # Partial unique index for deals dedup
        conn.execute(__import__("sqlalchemy").text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_deal_no_dup "
            "ON deals (platform_company, target_name, deal_date) "
            "WHERE target_name IS NOT NULL"
        ))
        # Performance indexes
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
        conn.commit()

    # Seed watched_zips
    session = get_session(db_path)
    try:
        if session.query(WatchedZip).count() == 0:
            _seed_watched_zips(session)
    finally:
        session.close()

    log.info("Database initialized at %s", db_path or DB_PATH)


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


def insert_deal(session: Session, **kwargs) -> bool:
    """Insert a deal. Returns True if inserted, False if duplicate."""
    # Dedup: same platform_company + deal_date + source
    platform = kwargs.get("platform_company")
    deal_date = kwargs.get("deal_date")
    source = kwargs.get("source")
    if platform and deal_date:
        existing = session.query(Deal).filter(
            Deal.platform_company == platform,
            Deal.deal_date == deal_date,
            Deal.source == source,
        ).first()
        if existing:
            log.warning("Duplicate deal skipped: %s on %s", platform, deal_date)
            return False
    try:
        deal = Deal(**kwargs)
        session.add(deal)
        session.commit()
        log.info("Inserted deal: %s / %s", kwargs.get("platform_company"), kwargs.get("target_name"))
        return True
    except Exception as e:
        session.rollback()
        if "UNIQUE constraint" in str(e):
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
