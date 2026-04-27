-- Frontend performance indexes for the Next.js/Supabase dashboard.
--
-- Root cause observed 2026-04-26: Supabase REST calls against practices,
-- practice_signals, and practice_intel were timing out even for narrow reads.
-- These indexes cover the filters/orderings used by the app's hot paths.
--
-- Safe to re-run. On a busy production database, run during a quiet window.

-- practices: legacy/global NPI table. Still used by admin/manual-update paths,
-- SQL explorer presets, and detail fallbacks.
CREATE INDEX IF NOT EXISTS ix_practices_zip_npi
  ON practices (zip, npi);

CREATE INDEX IF NOT EXISTS ix_practices_entity_classification
  ON practices (entity_classification);

CREATE INDEX IF NOT EXISTS ix_practices_buyability_score
  ON practices (buyability_score DESC)
  WHERE buyability_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_practices_data_axle_import_date
  ON practices (data_axle_import_date)
  WHERE data_axle_import_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_practices_updated_at_desc
  ON practices (updated_at DESC);

-- practice_locations: canonical frontend table for clinic-level surfaces.
CREATE INDEX IF NOT EXISTS ix_practice_locations_zip_residential
  ON practice_locations (zip, is_likely_residential);

CREATE INDEX IF NOT EXISTS ix_practice_locations_entity_residential
  ON practice_locations (entity_classification, is_likely_residential);

CREATE INDEX IF NOT EXISTS ix_practice_locations_buyability_residential
  ON practice_locations (buyability_score DESC, is_likely_residential)
  WHERE buyability_score IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_practice_locations_updated_at_desc
  ON practice_locations (updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_practice_locations_primary_npi
  ON practice_locations (primary_npi);

-- signals/intel: optional evidence layers. These should never block first
-- paint, but indexed lookups keep drawers and AI routes responsive.
CREATE INDEX IF NOT EXISTS ix_practice_signals_zip_code
  ON practice_signals (zip_code);

CREATE INDEX IF NOT EXISTS ix_practice_signals_npi
  ON practice_signals (npi);

CREATE INDEX IF NOT EXISTS ix_practice_signals_flagged
  ON practice_signals (zip_code)
  WHERE stealth_dso_flag
     OR phantom_inventory_flag
     OR family_dynasty_flag
     OR micro_cluster_flag
     OR retirement_combo_flag
     OR last_change_90d_flag
     OR high_peer_retirement_flag;

CREATE INDEX IF NOT EXISTS ix_practice_intel_research_date_desc
  ON practice_intel (research_date DESC);

CREATE INDEX IF NOT EXISTS ix_practice_intel_readiness
  ON practice_intel (acquisition_readiness);

CREATE INDEX IF NOT EXISTS ix_practice_intel_verification_quality
  ON practice_intel (verification_quality);

-- supporting sort/filter paths
CREATE INDEX IF NOT EXISTS ix_deals_deal_date_desc
  ON deals (deal_date DESC);

CREATE INDEX IF NOT EXISTS ix_deals_target_zip_date
  ON deals (target_zip, deal_date DESC);

CREATE INDEX IF NOT EXISTS ix_practice_changes_change_date_desc
  ON practice_changes (change_date DESC);

CREATE INDEX IF NOT EXISTS ix_practice_changes_type_date
  ON practice_changes (change_type, change_date DESC);

CREATE INDEX IF NOT EXISTS ix_zip_scores_zip_code
  ON zip_scores (zip_code);

CREATE INDEX IF NOT EXISTS ix_zip_signals_zip_code
  ON zip_signals (zip_code);

ANALYZE practices;
ANALYZE practice_locations;
ANALYZE practice_signals;
ANALYZE practice_intel;
ANALYZE deals;
ANALYZE practice_changes;
ANALYZE zip_scores;
ANALYZE zip_signals;

