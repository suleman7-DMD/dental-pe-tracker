-- Directory web checks -- the "is this row a current GP office, as listed?" overlay.
--
-- One row per directory location: the latest rapid-validation check from
-- data/office_census/rapid/checks.jsonl (protocol: data/office_census/RAPID_VALIDATION_RUNBOOK.md).
-- The Directory page applies `effect` at read time:
--   removed          hidden from the directory list and map (NOT_CURRENT_GP, positive evidence)
--   open_corrected   web-seen name / phone / website / address shown (VALID_CORRECTED)
--   open_verified    VALID
--   listed_only      IDENTITY_ONLY (listings only, no current signal)
--   needs_review     IDENTITY_PROBLEM / ESCALATE
--   no_web_evidence  NO_WEB_EVIDENCE (never counts against the row)
--
-- Published by: python3 scrapers/directory_web_checks_publish.py --allow-db-write --verify
--
-- Deliberately NO foreign key to practice_locations (full_replace syncs TRUNCATE it) and not
-- part of sync_to_supabase.py / refresh.sh. practice_locations, ownership tiers and every
-- pipeline count are untouched; emptying this table restores the page exactly.
-- RLS on, anon/authenticated read-only; writes only via the publisher's Postgres connection.

CREATE TABLE IF NOT EXISTS directory_web_checks (
    location_id     text PRIMARY KEY,
    candidate_id    text NOT NULL,
    zip             text NOT NULL,
    effect          text NOT NULL CHECK (effect IN (
                        'removed', 'open_corrected', 'open_verified', 'listed_only',
                        'needs_review', 'no_web_evidence')),
    decision        text NOT NULL,
    reason          text,
    duplicate_of    text,
    gp_scope        text,
    observed        jsonb NOT NULL DEFAULT '{}'::jsonb,
    as_seen         jsonb NOT NULL DEFAULT '{}'::jsonb,
    signals         jsonb NOT NULL DEFAULT '[]'::jsonb,
    ties_by         jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence        jsonb NOT NULL DEFAULT '[]'::jsonb,
    leads           jsonb NOT NULL DEFAULT '[]'::jsonb,
    note            text,
    checked_at      date NOT NULL,
    recorded_at     timestamptz NOT NULL,
    session         text,
    researcher      text,
    rules           text,
    publish_id      text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_directory_web_checks_zip ON directory_web_checks (zip);
CREATE INDEX IF NOT EXISTS ix_directory_web_checks_effect ON directory_web_checks (effect);

-- Append-only publish log: what the live page received and when.
CREATE TABLE IF NOT EXISTS directory_web_check_publishes (
    publish_id      text PRIMARY KEY,
    published_at    timestamptz NOT NULL DEFAULT now(),
    rows            integer NOT NULL,
    by_effect       jsonb NOT NULL,
    checks_sha256   text NOT NULL,
    rules           text
);

ALTER TABLE directory_web_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE directory_web_check_publishes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'directory_web_checks' AND policyname = 'directory_web_checks_read') THEN
        CREATE POLICY directory_web_checks_read ON directory_web_checks FOR SELECT TO anon, authenticated USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'directory_web_check_publishes' AND policyname = 'directory_web_check_publishes_read') THEN
        CREATE POLICY directory_web_check_publishes_read ON directory_web_check_publishes FOR SELECT TO anon, authenticated USING (true);
    END IF;
END $$;

GRANT SELECT ON directory_web_checks, directory_web_check_publishes TO anon, authenticated;
