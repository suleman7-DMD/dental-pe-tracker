-- Office census research queue -- the "does this office exist and operate?" axis.
--
-- Separate from ownership (ownership_tier / LEDGER.jsonl) and from the job-hunt
-- website layer. Rows are RESEARCH ITEMS, not offices: only a research-ledger
-- decision (data/office_census/research_ledger.jsonl) puts a candidate in
-- CONFIRMED_OPERATING_GP.
--
-- Built by:     python3 scrapers/office_census.py build
-- Published by: python3 scrapers/office_census_publish.py --allow-db-write
-- Protocol:     data/office_census/README.md
--
-- Deliberately NO foreign key to practice_locations: that table is rebuilt by
-- full_replace (TRUNCATE CASCADE) syncs, which would silently wipe this queue.
-- Not part of sync_to_supabase.py. The publisher replaces both tables' contents
-- in one transaction from the committed generated files, so the live queue is
-- always reproducible from the repo.
--
-- RLS on, anon/authenticated read-only. Writes happen only through the
-- publisher's direct Postgres connection.

CREATE TABLE IF NOT EXISTS office_census_candidates (
    candidate_id           text PRIMARY KEY,
    zip                    text NOT NULL,
    city                   text,
    origin                 text NOT NULL CHECK (origin IN (
                               'directory_row', 'excluded_row', 'data_axle_unrepresented',
                               'nppes_unrepresented', 'dso_locator_unrepresented',
                               'external_discovery')),
    in_directory           boolean NOT NULL,
    location_id            text,
    name                   text,
    address                text,
    suite                  text,
    suites_seen            jsonb NOT NULL DEFAULT '[]'::jsonb,
    phone                  text,
    website                text,
    entity_classification  text,
    queue_state            text NOT NULL CHECK (queue_state IN (
                               'CONFIRMED_OPERATING_GP', 'NEEDS_CURRENT_VERIFICATION',
                               'IDENTITY_REVIEW', 'OPERATING_STATUS_UNRESOLVED',
                               'GP_SCOPE_UNRESOLVED', 'LOCATION_INCOMPLETE',
                               'PROBABLE_NON_OFFICE', 'LIKELY_SPECIALIST_ONLY',
                               'SOURCE_CANDIDATE_UNREPRESENTED', 'EXTERNAL_DISCOVERY',
                               'RESEARCHED_UNRESOLVED', 'RESOLVED_EXCLUDED', 'RESOLVED_SPLIT')),
    priority               smallint NOT NULL,
    effort                 text NOT NULL,
    flags                  jsonb NOT NULL DEFAULT '[]'::jsonb,
    gp_scope_taxonomy      text,
    provider_count         integer,
    org_npis_at_street     integer,
    phones_at_street       integer,
    da_records_at_street   integer,
    da_latest_update       text,
    prior_evidence_level   text NOT NULL,
    prior_evidence         jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_refs            jsonb NOT NULL DEFAULT '{}'::jsonb,
    latitude               double precision,
    longitude              double precision,
    coord_status           text NOT NULL,
    observations           integer NOT NULL DEFAULT 0,
    sources_checked        jsonb NOT NULL DEFAULT '[]'::jsonb,
    decision               jsonb,
    batch_rank             integer,
    build_id               text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_office_census_candidates_zip ON office_census_candidates (zip, priority);
CREATE INDEX IF NOT EXISTS ix_office_census_candidates_state ON office_census_candidates (queue_state);

ALTER TABLE office_census_candidates ADD COLUMN IF NOT EXISTS research_priority text;
ALTER TABLE office_census_candidates ADD COLUMN IF NOT EXISTS lead_quality text;
ALTER TABLE office_census_candidates DROP CONSTRAINT IF EXISTS office_census_candidates_queue_state_check;
ALTER TABLE office_census_candidates ADD CONSTRAINT office_census_candidates_queue_state_check CHECK (queue_state IN (
    'CONFIRMED_OPERATING_GP', 'NEEDS_CURRENT_VERIFICATION', 'EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION',
    'IDENTITY_REVIEW', 'OPERATING_STATUS_UNRESOLVED', 'GP_SCOPE_UNRESOLVED', 'LOCATION_INCOMPLETE',
    'PROBABLE_NON_OFFICE', 'LIKELY_SPECIALIST_ONLY', 'SOURCE_CANDIDATE_UNREPRESENTED', 'EXTERNAL_DISCOVERY',
    'RESEARCHED_UNRESOLVED', 'RESOLVED_EXCLUDED', 'RESOLVED_SPLIT'));

CREATE TABLE IF NOT EXISTS office_census_zip_coverage (
    zip                        text PRIMARY KEY,
    city                       text,
    pilot                      boolean NOT NULL DEFAULT false,
    stage                      text NOT NULL CHECK (stage IN (
                                   'not_started', 'in_progress', 'rows_validated',
                                   'discovery_done', 'recall_audited')),
    batch_rank                 integer NOT NULL,
    directory_rows             integer NOT NULL,
    excluded_rows              integer NOT NULL,
    source_candidates          integer NOT NULL,
    external_discoveries       integer NOT NULL,
    confirmed                  integer NOT NULL,
    needs_verification         integer NOT NULL,
    identity_review            integer NOT NULL,
    status_unresolved          integer NOT NULL,
    gp_scope_unresolved        integer NOT NULL,
    location_incomplete        integer NOT NULL,
    probable_non_office        integer NOT NULL,
    likely_specialist_only     integer NOT NULL,
    source_unrepresented       integer NOT NULL,
    external_pending           integer NOT NULL,
    researched_unresolved      integer NOT NULL,
    resolved_excluded          integer NOT NULL,
    dir_with_coords            integer NOT NULL,
    dir_missing_coords         integer NOT NULL,
    dir_coords_recoverable     integer NOT NULL,
    dir_coords_suspect         integer NOT NULL,
    dir_site_checked_live      integer NOT NULL,
    dir_prior_web_research     integer NOT NULL,
    dir_ownership_review_only  integer NOT NULL,
    dir_no_prior_research      integer NOT NULL,
    dir_identity_flagged       integer NOT NULL,
    open_items                 integer NOT NULL,
    review_items               integer NOT NULL,
    sources_searched           jsonb NOT NULL DEFAULT '[]'::jsonb,
    last_activity              date,
    build_id                   text NOT NULL
);

-- One row per publish: the build manifest (inputs fingerprints, totals,
-- state definitions). Append-only history of queue progress.
CREATE TABLE IF NOT EXISTS office_census_builds (
    build_id       text PRIMARY KEY,
    rules_version  text NOT NULL,
    built_at       timestamptz NOT NULL,
    published_at   timestamptz NOT NULL DEFAULT now(),
    manifest       jsonb NOT NULL
);

-- Additive migration keeps the checkpoint reader compatible during deployment.
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS p1_items integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS p1_clean integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS p2_items integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS p4_deferred integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS candidate_decisions integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS historical_evidence_rows integer NOT NULL DEFAULT 0;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS discovery_passes jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS discovery_status text NOT NULL DEFAULT 'not_searched';
ALTER TABLE office_census_zip_coverage ADD COLUMN IF NOT EXISTS last_discovery_at date;

ALTER TABLE office_census_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE office_census_zip_coverage ENABLE ROW LEVEL SECURITY;
ALTER TABLE office_census_builds ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'office_census_candidates' AND policyname = 'office_census_candidates_read') THEN
        CREATE POLICY office_census_candidates_read ON office_census_candidates FOR SELECT TO anon, authenticated USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'office_census_zip_coverage' AND policyname = 'office_census_zip_coverage_read') THEN
        CREATE POLICY office_census_zip_coverage_read ON office_census_zip_coverage FOR SELECT TO anon, authenticated USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'office_census_builds' AND policyname = 'office_census_builds_read') THEN
        CREATE POLICY office_census_builds_read ON office_census_builds FOR SELECT TO anon, authenticated USING (true);
    END IF;
END $$;

GRANT SELECT ON office_census_candidates, office_census_zip_coverage, office_census_builds TO anon, authenticated;
