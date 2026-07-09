-- job_hunt_verification — website-verified job-hunt layer over practice_locations.
--
-- One row per verified location: what the practice's OWN website says (public
-- name, current doctors, owner statement, hiring page), independent of the
-- census/registry record. The frontend job-hunt lanes (dental-pe-nextjs
-- src/lib/census/job-lane.ts) key off verification_status; the display-name
-- precedence (display-name.ts verifiedDisplayName) keys off public_practice_name.
--
-- Recreate/update via: python3 -m scrapers.import_job_hunt_verification
-- Seed artifact:       data/job_hunt_verification_seed.json
-- Runbook:             JOB_HUNT_VERIFICATION_RUNBOOK.md
--
-- Matches the live Supabase table exactly (schema dumped 2026-07-09).
-- RLS is intentionally not enabled, matching the sibling census tables.

CREATE TABLE IF NOT EXISTS job_hunt_verification (
    location_id               text PRIMARY KEY
                              REFERENCES practice_locations(location_id),
    public_practice_name      text,
    website_url               text,
    website_status            text NOT NULL
                              CHECK (website_status IN
                                ('live', 'dead', 'parked', 'social_only', 'none_found')),
    doctors                   jsonb NOT NULL DEFAULT '[]'::jsonb,
    provider_count_website    integer,
    owner_operator_stated     text,
    ownership_evidence_status text NOT NULL DEFAULT 'no_statement'
                              CHECK (ownership_evidence_status IN
                                ('consistent', 'conflict', 'no_statement')),
    careers_page_url          text,
    has_hiring_page           boolean NOT NULL DEFAULT false,
    openings                  jsonb NOT NULL DEFAULT '[]'::jsonb,
    verification_status       text NOT NULL
                              CHECK (verification_status IN
                                ('roster_verified', 'hiring_page_found', 'call_required',
                                 'no_usable_website', 'ownership_conflict', 'stale_recheck')),
    evidence_urls             jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes                     text,
    last_checked_at           timestamptz NOT NULL DEFAULT now(),
    checked_by                text NOT NULL DEFAULT 'job-hunt-sprint',
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now()
);
