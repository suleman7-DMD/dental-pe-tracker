-- ============================================================================
-- Dental PE Intelligence Platform — Postgres Schema (Supabase)
-- Generated from SQLAlchemy models in scrapers/database.py
-- Tables ordered by dependency (parents before children)
-- ============================================================================

-- 1. practices (400k+ rows) — the largest table, referenced by practice_changes FK
CREATE TABLE IF NOT EXISTS practices (
    id                       SERIAL PRIMARY KEY,
    npi                      TEXT NOT NULL UNIQUE,
    practice_name            TEXT,
    doing_business_as        TEXT,
    entity_type              TEXT,
    address                  TEXT,
    city                     TEXT,
    state                    TEXT,
    zip                      TEXT,
    phone                    TEXT,
    taxonomy_code            TEXT,
    taxonomy_description     TEXT,
    enumeration_date         DATE,
    last_updated             DATE,
    ownership_status         TEXT,           -- independent, dso_affiliated, pe_backed, unknown
    affiliated_dso           TEXT,
    affiliated_pe_sponsor    TEXT,
    notes                    TEXT,
    data_source              TEXT,           -- nppes, data_axle, manual
    latitude                 DOUBLE PRECISION,
    longitude                DOUBLE PRECISION,
    year_established         INTEGER,
    employee_count           INTEGER,
    estimated_revenue        DOUBLE PRECISION,
    num_providers            INTEGER,
    location_type            TEXT,
    buyability_score         DOUBLE PRECISION,
    buyability_confidence    DOUBLE PRECISION,   -- exists in SQLite, not yet in SQLAlchemy model
    classification_confidence DOUBLE PRECISION,
    classification_reasoning TEXT,
    data_axle_raw_name       TEXT,
    data_axle_import_date    DATE,
    raw_record_count         INTEGER,
    import_batch_id          TEXT,
    parent_company           TEXT,
    parent_iusa              TEXT,
    ein                      TEXT,
    franchise_name           TEXT,
    iusa_number              TEXT,
    website                  TEXT,
    provider_last_name       TEXT,
    entity_classification    TEXT,           -- solo_established, solo_new, solo_inactive, solo_high_volume,
                                            -- family_practice, small_group, large_group,
                                            -- dso_regional, dso_national, specialist, non_clinical
    created_at               TIMESTAMP DEFAULT NOW(),
    updated_at               TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_practices_zip    ON practices (zip);
CREATE INDEX IF NOT EXISTS ix_practices_state  ON practices (state);
CREATE INDEX IF NOT EXISTS ix_practices_status ON practices (ownership_status);
CREATE INDEX IF NOT EXISTS ix_practices_updated ON practices (updated_at);


-- 2. deals (2,500+ rows)
CREATE TABLE IF NOT EXISTS deals (
    id                SERIAL PRIMARY KEY,
    deal_date         DATE,
    platform_company  TEXT NOT NULL,
    pe_sponsor        TEXT,
    target_name       TEXT,
    target_city       TEXT,
    target_state      TEXT,
    target_zip        TEXT,
    deal_type         TEXT,                 -- buyout, add-on, recapitalization, growth, de_novo, partnership, other
    deal_size_mm      DOUBLE PRECISION,
    ebitda_multiple   DOUBLE PRECISION,
    specialty         TEXT,
    num_locations     INTEGER,
    source            TEXT NOT NULL,
    source_url        TEXT,
    notes             TEXT,
    raw_text          TEXT,
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

-- Partial unique index: dedup deals only when target_name is non-null
CREATE UNIQUE INDEX IF NOT EXISTS uix_deal_no_dup
    ON deals (platform_company, target_name, deal_date)
    WHERE target_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_deals_state  ON deals (target_state);
CREATE INDEX IF NOT EXISTS ix_deals_date   ON deals (deal_date);
CREATE INDEX IF NOT EXISTS ix_deals_source ON deals (source);


-- 3. practice_changes (5,100+ rows) — FK to practices.npi
CREATE TABLE IF NOT EXISTS practice_changes (
    id            SERIAL PRIMARY KEY,
    npi           TEXT NOT NULL REFERENCES practices(npi),
    change_date   DATE,
    field_changed TEXT,
    old_value     TEXT,
    new_value     TEXT,
    change_type   TEXT,                     -- acquisition, name_change, relocation, closure, new_practice, unknown
    notes         TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_practice_changes_npi ON practice_changes (npi);


-- 4. zip_scores (290 rows)
CREATE TABLE IF NOT EXISTS zip_scores (
    id                                SERIAL PRIMARY KEY,
    zip_code                          TEXT NOT NULL,
    city                              TEXT,
    state                             TEXT,
    metro_area                        TEXT,
    total_practices                   INTEGER,
    pe_backed_count                   INTEGER,
    dso_affiliated_count              INTEGER,
    independent_count                 INTEGER,
    unknown_count                     INTEGER,
    institutional_count               INTEGER,
    raw_npi_count                     INTEGER,
    classified_count                  INTEGER,
    consolidation_pct                 DOUBLE PRECISION,
    consolidation_pct_of_total        DOUBLE PRECISION,
    independent_pct_of_total          DOUBLE PRECISION,
    pe_penetration_pct                DOUBLE PRECISION,
    pct_unknown                       DOUBLE PRECISION,
    recent_changes_90d                INTEGER,
    state_deal_count_12m              INTEGER,
    score_date                        DATE,
    opportunity_score                 DOUBLE PRECISION,
    data_confidence                   TEXT,
    -- Address-level dedup and consolidation analysis
    consolidated_count                INTEGER,
    unclassified_pct                  DOUBLE PRECISION,
    -- Saturation metrics (computed by merge_and_score.py)
    total_gp_locations                INTEGER,
    total_specialist_locations        INTEGER,
    dld_gp_per_10k                    DOUBLE PRECISION,
    dld_total_per_10k                 DOUBLE PRECISION,
    people_per_gp_door                INTEGER,
    -- Ownership structure metrics
    buyable_practice_count            INTEGER,
    buyable_practice_ratio            DOUBLE PRECISION,
    corporate_location_count          INTEGER,
    corporate_share_pct               DOUBLE PRECISION,
    family_practice_count             INTEGER,
    specialist_density_flag           BOOLEAN,
    -- Data quality
    entity_classification_coverage_pct DOUBLE PRECISION,
    data_axle_enrichment_pct          DOUBLE PRECISION,
    metrics_confidence                TEXT,
    -- Market classification
    market_type                       TEXT,
    market_type_confidence            TEXT,

    CONSTRAINT uq_zip_score_date UNIQUE (zip_code, score_date)
);


-- 5. watched_zips (290 rows)
CREATE TABLE IF NOT EXISTS watched_zips (
    id                      SERIAL PRIMARY KEY,
    zip_code                TEXT NOT NULL UNIQUE,
    city                    TEXT,
    state                   TEXT,
    metro_area              TEXT,
    notes                   TEXT,
    -- Demographic columns (populated by census_loader.py)
    population              INTEGER,
    median_household_income INTEGER,
    population_growth_pct   DOUBLE PRECISION,
    demographics_updated_at TIMESTAMP
);


-- 6. dso_locations (408 rows)
CREATE TABLE IF NOT EXISTS dso_locations (
    id            SERIAL PRIMARY KEY,
    dso_name      TEXT NOT NULL,
    location_name TEXT,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip           TEXT,
    phone         TEXT,
    scraped_at    TIMESTAMP DEFAULT NOW(),
    source_url    TEXT
);


-- 7. ada_hpi_benchmarks (918 rows)
CREATE TABLE IF NOT EXISTS ada_hpi_benchmarks (
    id                     SERIAL PRIMARY KEY,
    data_year              INTEGER NOT NULL,
    state                  TEXT NOT NULL,
    career_stage           TEXT NOT NULL,       -- all, early_career_lt10, mid_career_10_25, late_career_gt25
    total_dentists         INTEGER,
    pct_dso_affiliated     DOUBLE PRECISION,
    pct_solo_practice      DOUBLE PRECISION,
    pct_group_practice     DOUBLE PRECISION,
    pct_large_group_10plus DOUBLE PRECISION,
    source_file            TEXT,
    created_at             TIMESTAMP DEFAULT NOW(),
    updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uix_ada_hpi UNIQUE (data_year, state, career_stage)
);


-- 8. pe_sponsors (33 rows)
CREATE TABLE IF NOT EXISTS pe_sponsors (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    also_known_as    TEXT,
    hq_city          TEXT,
    hq_state         TEXT,
    aum_estimate_bn  DOUBLE PRECISION,
    healthcare_focus BOOLEAN DEFAULT FALSE,
    notes            TEXT
);


-- 9. platforms (69 rows)
CREATE TABLE IF NOT EXISTS platforms (
    id                  SERIAL PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    pe_sponsor_name     TEXT,
    hq_state            TEXT,
    estimated_locations INTEGER,
    states_active       TEXT,
    specialties         TEXT,
    founded_year        INTEGER,
    notes               TEXT
);


-- 10. zip_overviews (12 rows)
CREATE TABLE IF NOT EXISTS zip_overviews (
    id            SERIAL PRIMARY KEY,
    zip_code      TEXT NOT NULL UNIQUE,
    overview_html TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);


-- 11. sync_metadata (NEW — tracks incremental sync state per table)
CREATE TABLE IF NOT EXISTS sync_metadata (
    id              SERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL UNIQUE,
    last_sync_at    TIMESTAMP NOT NULL,
    last_sync_value TEXT,
    rows_synced     INTEGER,
    sync_type       TEXT,
    notes           TEXT
);


-- 12. zip_qualitative_intel — ZIP-level qualitative market research
CREATE TABLE IF NOT EXISTS zip_qualitative_intel (
    zip_code             TEXT NOT NULL PRIMARY KEY REFERENCES watched_zips(zip_code),
    research_date        TEXT NOT NULL,
    -- Housing & Development
    housing_status       TEXT,
    housing_developments TEXT,
    housing_summary      TEXT,
    -- Schools
    school_district      TEXT,
    school_rating        TEXT,
    school_source        TEXT,
    school_note          TEXT,
    -- Retail & Income Signals
    retail_premium       TEXT,
    retail_mass          TEXT,
    retail_income_signal TEXT,
    -- Commercial Development
    commercial_status    TEXT,
    commercial_projects  TEXT,
    commercial_note      TEXT,
    -- Dental-Specific News
    dental_new_offices   TEXT,
    dental_dso_moves     TEXT,
    dental_note          TEXT,
    -- Real Estate
    median_home_price    INTEGER,
    home_price_trend     TEXT,
    home_price_yoy_pct   DOUBLE PRECISION,
    real_estate_source   TEXT,
    -- Zoning & Planning
    zoning_items         TEXT,
    zoning_note          TEXT,
    -- Population Signals
    pop_growth_signals   TEXT,
    pop_demographics     TEXT,
    pop_note             TEXT,
    -- Employment & Insurance
    major_employers      TEXT,
    insurance_signal     TEXT,
    -- Competition
    competitor_new       TEXT,
    competitor_closures  TEXT,
    competitor_note      TEXT,
    -- Synthesis
    demand_outlook       TEXT,
    supply_outlook       TEXT,
    investment_thesis    TEXT,
    confidence           TEXT,
    sources              TEXT,
    -- Metadata
    research_method      TEXT,
    raw_json             TEXT,
    cost_usd             DOUBLE PRECISION,
    model_used           TEXT,
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zip_intel_date ON zip_qualitative_intel(research_date);


-- 13. practice_intel — Practice-level due diligence research
CREATE TABLE IF NOT EXISTS practice_intel (
    npi                  TEXT NOT NULL PRIMARY KEY REFERENCES practices(npi),
    research_date        TEXT NOT NULL,
    -- Website Analysis
    website_url          TEXT,
    website_era          TEXT,
    website_last_update  TEXT,
    website_analysis     TEXT,
    -- Services & Technology
    services_listed      TEXT,
    services_high_rev    TEXT,
    services_note        TEXT,
    technology_listed    TEXT,
    technology_level     TEXT,
    -- Provider Info
    provider_count_web   INTEGER,
    owner_career_stage   TEXT,
    provider_notes       TEXT,
    -- Google Reviews
    google_review_count  INTEGER,
    google_rating        DOUBLE PRECISION,
    google_recent_date   TEXT,
    google_velocity      TEXT,
    google_sentiment     TEXT,
    -- Hiring Signals
    hiring_active        INTEGER DEFAULT 0,
    hiring_positions     TEXT,
    hiring_source        TEXT,
    -- Acquisition News
    acquisition_found    INTEGER DEFAULT 0,
    acquisition_details  TEXT,
    -- Social Media
    social_facebook      TEXT,
    social_instagram     TEXT,
    social_other         TEXT,
    -- Other Profiles
    healthgrades_rating  DOUBLE PRECISION,
    healthgrades_reviews INTEGER,
    zocdoc_listed        INTEGER DEFAULT 0,
    -- Doctor Profile
    doctor_publications  INTEGER DEFAULT 0,
    doctor_speaking      INTEGER DEFAULT 0,
    doctor_associations  TEXT,
    doctor_notes         TEXT,
    -- Insurance Signals
    accepts_medicaid     INTEGER,
    ppo_heavy            INTEGER,
    insurance_note       TEXT,
    -- Assessment
    red_flags            TEXT,
    green_flags          TEXT,
    overall_assessment   TEXT,
    acquisition_readiness TEXT,
    confidence           TEXT,
    sources              TEXT,
    -- Metadata
    research_method      TEXT,
    escalated            INTEGER DEFAULT 0,
    escalation_findings  TEXT,
    raw_json             TEXT,
    cost_usd             DOUBLE PRECISION,
    model_used           TEXT,
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_practice_intel_date ON practice_intel(research_date);
