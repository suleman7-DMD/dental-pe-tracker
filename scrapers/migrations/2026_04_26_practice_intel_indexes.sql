-- Task #4: practice_intel + signal table index backfill
-- Applied: 2026-04-26
--
-- Root cause: practice_intel table was missing a secondary btree index on npi
-- (the PK is a unique index but the REST API layer sometimes does seq-scan on
-- large TOAST rows). Also practice_signals and zip_signals were missing zip/npi
-- indexes, causing Warroom signal queries to seq-scan 13,818-row tables.
--
-- All indexes use IF NOT EXISTS — safe to re-run.

-- practice_intel: cover the main query paths used by Launchpad and Intelligence
CREATE INDEX IF NOT EXISTS idx_practice_intel_npi
    ON practice_intel (npi);

CREATE INDEX IF NOT EXISTS idx_practice_intel_verification_quality
    ON practice_intel (verification_quality);

CREATE INDEX IF NOT EXISTS ix_practice_intel_research_date_desc
    ON practice_intel (research_date DESC);

CREATE INDEX IF NOT EXISTS ix_practice_intel_readiness
    ON practice_intel (acquisition_readiness);

-- practice_signals: Warroom 8-flag overlay filters by zip_code and npi
CREATE INDEX IF NOT EXISTS ix_practice_signals_npi
    ON practice_signals (npi);

CREATE INDEX IF NOT EXISTS ix_practice_signals_zip_code
    ON practice_signals (zip_code);

-- Partial index covering all 7 boolean signal flags — narrow reads for
-- Warroom "any flag active" queries (Hunt / Investigate modes)
CREATE INDEX IF NOT EXISTS ix_practice_signals_flagged
    ON practice_signals (zip_code)
    WHERE stealth_dso_flag
       OR phantom_inventory_flag
       OR family_dynasty_flag
       OR micro_cluster_flag
       OR retirement_combo_flag
       OR last_change_90d_flag
       OR high_peer_retirement_flag;

-- zip_signals: single-column; 290-row table but still benefits from index
-- when joined to zip_scores or watched_zips
CREATE INDEX IF NOT EXISTS ix_zip_signals_zip_code
    ON zip_signals (zip_code);

ANALYZE practice_intel;
ANALYZE practice_signals;
ANALYZE zip_signals;
