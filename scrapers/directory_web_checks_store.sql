-- Rapid-validation shared store: lets several sessions (local or Claude Code cloud) work one
-- queue and publish each check the moment it is recorded.
--
--   directory_web_check_log     append-only: every recorded check (the durable record)
--   directory_web_check_claims  which session is working which row (expires after 4 h)
--   rapid_tokens                sha256 of the session tokens allowed to call the rapid_* functions
--
-- Sessions never hold the Supabase secret key. They call these SECURITY DEFINER functions through
-- PostgREST with the public anon key plus RAPID_TOKEN; a leaked token can only claim rows and
-- record checks (overlay rows, brake-limited, revocable), never touch any other table.
--   rapid_next     claim the next unchecked rows for a session (atomic, no double claims)
--   rapid_record   log one check and apply it live (newer check wins; removal brake)
--   rapid_release  hand back a session's unrecorded claims
--   rapid_pull     page through the log (status / local mirror)
--   rapid_status   live counts, open claims, held removals
-- Installed by: python3 scrapers/directory_web_checks_publish.py --install-store
-- Requires directory_web_checks_schema.sql (directory_web_checks) first.

CREATE TABLE IF NOT EXISTS directory_web_check_log (
    entry_id      text PRIMARY KEY,
    candidate_id  text NOT NULL,
    location_id   text NOT NULL,
    session       text,
    recorded_at   timestamptz NOT NULL,
    decision      text NOT NULL,
    searches      integer NOT NULL DEFAULT 0,
    entry         jsonb NOT NULL,
    outcome       text NOT NULL CHECK (outcome IN ('live', 'held', 'stale', 'backfill')),
    held_reason   text,
    logged_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dwc_log_candidate ON directory_web_check_log (candidate_id);
CREATE INDEX IF NOT EXISTS ix_dwc_log_session ON directory_web_check_log (session);

CREATE TABLE IF NOT EXISTS directory_web_check_claims (
    candidate_id  text PRIMARY KEY,
    session       text NOT NULL,
    claimed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dwc_claims_session ON directory_web_check_claims (session);

CREATE TABLE IF NOT EXISTS rapid_tokens (
    token_sha256  text PRIMARY KEY,
    label         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    revoked_at    timestamptz
);

ALTER TABLE directory_web_check_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE directory_web_check_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE rapid_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON directory_web_check_log, directory_web_check_claims, rapid_tokens FROM anon, authenticated;

CREATE OR REPLACE FUNCTION rapid_auth(p_token text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    IF p_token IS NULL OR NOT EXISTS (
        SELECT 1 FROM rapid_tokens
        WHERE token_sha256 = encode(sha256(convert_to(p_token, 'UTF8')), 'hex') AND revoked_at IS NULL) THEN
        RAISE EXCEPTION 'rapid: invalid or revoked RAPID_TOKEN' USING ERRCODE = '28000';
    END IF;
END $$;

-- Claim up to p_n rows for p_session. p_ids is the eligible queue in order; rows with any logged
-- check, or claimed by another session in the last 4 hours, are skipped. The session's own open
-- claims come back first. No new claims once the session has a held removal or its logged
-- searches reach p_budget.
CREATE OR REPLACE FUNCTION rapid_next(p_token text, p_session text, p_ids text[], p_n integer,
                                      p_budget integer DEFAULT 170)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_cutoff timestamptz := now() - interval '4 hours';
    v_used integer; v_held integer; v_mine text[]; v_new text[] := '{}'; v_remaining integer;
BEGIN
    PERFORM rapid_auth(p_token);
    IF coalesce(p_session, '') = '' THEN RAISE EXCEPTION 'rapid: session required'; END IF;
    PERFORM pg_advisory_xact_lock(hashtext('directory_web_check_claims'));
    SELECT coalesce(sum(searches), 0) INTO v_used FROM directory_web_check_log WHERE session = p_session;
    SELECT count(*) INTO v_held FROM directory_web_check_log WHERE session = p_session AND outcome = 'held';
    SELECT coalesce(array_agg(id ORDER BY ord), '{}') INTO v_mine FROM (
        SELECT q.id, q.ord FROM unnest(p_ids) WITH ORDINALITY AS q(id, ord)
        JOIN directory_web_check_claims c ON c.candidate_id = q.id AND c.session = p_session
                                         AND c.claimed_at > v_cutoff
        WHERE NOT EXISTS (SELECT 1 FROM directory_web_check_log l WHERE l.candidate_id = q.id)
        ORDER BY q.ord LIMIT greatest(p_n, 0)) s;
    IF v_held = 0 AND v_used < p_budget AND cardinality(v_mine) < p_n THEN
        SELECT coalesce(array_agg(id ORDER BY ord), '{}') INTO v_new FROM (
            SELECT q.id, q.ord FROM unnest(p_ids) WITH ORDINALITY AS q(id, ord)
            WHERE NOT EXISTS (SELECT 1 FROM directory_web_check_log l WHERE l.candidate_id = q.id)
              AND NOT EXISTS (SELECT 1 FROM directory_web_check_claims c
                              WHERE c.candidate_id = q.id AND c.claimed_at > v_cutoff)
            ORDER BY q.ord LIMIT p_n - cardinality(v_mine)) s;
        INSERT INTO directory_web_check_claims (candidate_id, session, claimed_at)
        SELECT unnest(v_new), p_session, now()
        ON CONFLICT (candidate_id) DO UPDATE SET session = EXCLUDED.session, claimed_at = EXCLUDED.claimed_at;
    END IF;
    SELECT count(*) INTO v_remaining FROM unnest(p_ids) AS q(id)
    WHERE NOT EXISTS (SELECT 1 FROM directory_web_check_log l WHERE l.candidate_id = q.id);
    RETURN jsonb_build_object('picked', to_jsonb(v_mine || v_new), 'resumed', cardinality(v_mine),
                              'searches_used', v_used, 'held', v_held, 'remaining', v_remaining);
END $$;

-- Log one check and apply it to directory_web_checks. p_entry is the check as the tool wrote it;
-- p_row is the directory_web_checks row it produces. Outcomes:
--   live  applied to the page       stale  a newer check for the row is already live (logged only)
--   held  removal brake tripped: logged, NOT applied (removals > 35% of live rows, or > 50% of
--         this session's live rows, once either has >= 20 rows)
--   rejected (nothing written): unknown location, or the row already has a check and the entry
--         does not say "supersede": true
-- Retrying the same entry_id is a no-op that returns the first outcome.
CREATE OR REPLACE FUNCTION rapid_record(p_token text, p_entry jsonb, p_row jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    -- brake limits live here, not in the call, so a caller cannot loosen them
    c_max_removed constant numeric := 0.35;
    c_max_session_removed constant numeric := 0.50;
    c_min_rows constant integer := 20;
    v_cid text := p_entry->>'candidate_id';
    v_loc text := p_row->>'location_id';
    v_session text := p_row->>'session';
    v_prev text; v_outcome text; v_reason text;
    v_n integer; v_rm integer; v_sn integer; v_srm integer;
BEGIN
    PERFORM rapid_auth(p_token);
    PERFORM pg_advisory_xact_lock(hashtext('directory_web_checks'));
    SELECT outcome INTO v_prev FROM directory_web_check_log WHERE entry_id = p_entry->>'entry_id';
    IF FOUND THEN
        RETURN jsonb_build_object('outcome', v_prev, 'duplicate', true);
    END IF;
    IF v_cid IS NULL OR v_loc IS NULL OR v_cid <> 'loc:' || v_loc OR p_row->>'candidate_id' <> v_cid THEN
        RETURN jsonb_build_object('outcome', 'rejected', 'error', 'candidate_id / location_id mismatch');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM practice_locations WHERE location_id = v_loc) THEN
        RETURN jsonb_build_object('outcome', 'rejected', 'error',
            'location_id not in practice_locations (if the weekly sync is running, retry in a few minutes)');
    END IF;
    IF EXISTS (SELECT 1 FROM directory_web_check_log WHERE candidate_id = v_cid)
       AND coalesce((p_entry->>'supersede')::boolean, false) IS NOT TRUE THEN
        RETURN jsonb_build_object('outcome', 'rejected',
                                  'error', 'this row already has a check; add "supersede": true to replace it');
    END IF;
    BEGIN
        INSERT INTO directory_web_checks AS d
        SELECT * FROM jsonb_populate_record(NULL::directory_web_checks, p_row)
        ON CONFLICT (location_id) DO UPDATE SET
            candidate_id = EXCLUDED.candidate_id, zip = EXCLUDED.zip, effect = EXCLUDED.effect,
            decision = EXCLUDED.decision, reason = EXCLUDED.reason, duplicate_of = EXCLUDED.duplicate_of,
            gp_scope = EXCLUDED.gp_scope, observed = EXCLUDED.observed, as_seen = EXCLUDED.as_seen,
            signals = EXCLUDED.signals, ties_by = EXCLUDED.ties_by, evidence = EXCLUDED.evidence,
            leads = EXCLUDED.leads, note = EXCLUDED.note, checked_at = EXCLUDED.checked_at,
            recorded_at = EXCLUDED.recorded_at, session = EXCLUDED.session,
            researcher = EXCLUDED.researcher, rules = EXCLUDED.rules, publish_id = EXCLUDED.publish_id
        WHERE d.recorded_at <= EXCLUDED.recorded_at;
        IF NOT FOUND THEN
            v_outcome := 'stale';
        ELSE
            v_outcome := 'live';
            IF p_row->>'effect' = 'removed' THEN
                SELECT count(*), count(*) FILTER (WHERE effect = 'removed') INTO v_n, v_rm
                FROM directory_web_checks;
                SELECT count(*), count(*) FILTER (WHERE effect = 'removed') INTO v_sn, v_srm
                FROM directory_web_checks WHERE session IS NOT DISTINCT FROM v_session;
                IF (v_n >= c_min_rows AND v_rm > c_max_removed * v_n)
                   OR (v_sn >= c_min_rows AND v_srm > c_max_session_removed * v_sn) THEN
                    v_reason := format('removals would be %s/%s of live rows and %s/%s of session %s',
                                       v_rm, v_n, v_srm, v_sn, v_session);
                    RAISE EXCEPTION USING ERRCODE = 'RB001', MESSAGE = v_reason;
                END IF;
            END IF;
        END IF;
    EXCEPTION WHEN SQLSTATE 'RB001' THEN
        v_outcome := 'held';   -- the upsert above is rolled back; the check is still logged below
    END;
    INSERT INTO directory_web_check_log (entry_id, candidate_id, location_id, session, recorded_at,
                                         decision, searches, entry, outcome, held_reason)
    VALUES (p_entry->>'entry_id', v_cid, v_loc, v_session, (p_entry->>'recorded_at')::timestamptz,
            p_entry->>'decision', coalesce((p_entry->>'searches')::integer, 0), p_entry, v_outcome, v_reason);
    DELETE FROM directory_web_check_claims WHERE candidate_id = v_cid;
    RETURN jsonb_build_object('outcome', v_outcome, 'held_reason', v_reason);
END $$;

CREATE OR REPLACE FUNCTION rapid_release(p_token text, p_session text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_n integer;
BEGIN
    PERFORM rapid_auth(p_token);
    DELETE FROM directory_web_check_claims WHERE session = p_session;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $$;

CREATE OR REPLACE FUNCTION rapid_pull(p_token text, p_offset integer DEFAULT 0, p_limit integer DEFAULT 500)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_out jsonb;
BEGIN
    PERFORM rapid_auth(p_token);
    SELECT coalesce(jsonb_agg(x ORDER BY recorded_at, entry_id), '[]'::jsonb) INTO v_out FROM (
        SELECT entry_id, recorded_at, entry || jsonb_build_object('outcome', outcome) AS x
        FROM directory_web_check_log ORDER BY recorded_at, entry_id
        OFFSET greatest(p_offset, 0) LIMIT least(greatest(p_limit, 1), 1000)) s;
    RETURN v_out;
END $$;

CREATE OR REPLACE FUNCTION rapid_status(p_token text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    PERFORM rapid_auth(p_token);
    RETURN jsonb_build_object(
        'log_rows', (SELECT count(*) FROM directory_web_check_log),
        'held', (SELECT count(*) FROM directory_web_check_log WHERE outcome = 'held'),
        'live', (SELECT coalesce(jsonb_object_agg(effect, n), '{}'::jsonb)
                 FROM (SELECT effect, count(*) AS n FROM directory_web_checks GROUP BY effect) e),
        'claims', (SELECT coalesce(jsonb_object_agg(session, n), '{}'::jsonb)
                   FROM (SELECT session, count(*) AS n FROM directory_web_check_claims
                         WHERE claimed_at > now() - interval '4 hours' GROUP BY session) c));
END $$;

REVOKE ALL ON FUNCTION rapid_auth(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION rapid_next(text, text, text[], integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION rapid_record(text, jsonb, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rapid_release(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rapid_pull(text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION rapid_status(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rapid_next(text, text, text[], integer, integer) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION rapid_record(text, jsonb, jsonb) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION rapid_release(text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION rapid_pull(text, integer, integer) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION rapid_status(text) TO anon, authenticated;
