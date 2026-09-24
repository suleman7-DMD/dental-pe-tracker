"""Tests for the office-census ledger rules and key helpers (no DB access).

    python3 -m pytest scrapers/test_office_census.py -q
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census as oc  # noqa: E402

TODAY = datetime.date(2026, 9, 24)
KNOWN = {"loc:aaaaaaaaaaaaaaaa", "loc:bbbbbbbbbbbbbbbb", "src:60602:0123456789ab"}
BASE = {"researcher": "test", "recorded_at": "2026-09-24T12:00:00Z"}


def obs(eid, cid="loc:aaaaaaaaaaaaaaaa", family="office_website", claim="operating_at_address", **kw):
    e = {**BASE, "entry_id": eid, "type": "observation", "candidate_id": cid, "source_family": family,
         "claim": claim, "confidence": "high", "observed_at": "2026-09-24",
         "source_url": "https://example.com/contact", "evidence": "Contact page lists 1 Main St Ste 2"}
    e.update(kw)
    return e


def dec(eid, basis, status="OPERATING_GP_CONFIRMED", cid="loc:aaaaaaaaaaaaaaaa", **kw):
    e = {**BASE, "entry_id": eid, "type": "decision", "candidate_id": cid, "terminal_status": status,
         "confidence": "high", "decided_at": "2026-09-24", "basis_entry_ids": basis,
         "fields": {"office_name": "Main Street Dental", "address": "1 Main St", "suite_status": "Suite 2 confirmed"},
         "assessment": {axis: {"conclusion": "established", "rationale": "Official page explicitly establishes this fact at this site", "basis_entry_ids": basis} for axis in oc.AXES},
         "contradictions_reviewed": "No conflicting evidence found in the source bundle"}
    e.update(kw)
    return e


def run(*entries, known=KNOWN):
    return oc.check_ledger(list(enumerate(entries, 1)), known, TODAY)


def test_one_website_with_explicit_claim_adjudication_can_confirm():
    errors, led = run(obs("o1"), dec("d1", ["o1"]))
    assert errors == []


def test_two_families_without_adjudication_cannot_confirm():
    errors, led = run(obs("o1"), obs("o2", family="google_business_profile"), dec("d1", ["o1", "o2"], assessment={}))
    assert any("assessment.gp_scope" in e for e in errors)


def test_phone_call_alone_confirms_without_url():
    errors, _ = run(obs("o1", family="phone_call", source_url=None, evidence="Receptionist confirmed address"),
                    dec("d1", ["o1"]))
    assert errors == []


def test_every_observation_needs_evidence():
    errors, _ = run(obs("o1", evidence=""))
    assert any("needs evidence" in e for e in errors)


def test_absence_is_not_closure():
    errors, _ = run(obs("o1", claim="not_found"), dec("d1", ["o1"], status="CLOSED"))
    assert any("absence is not closure" in e for e in errors)


def test_confirmation_needs_office_name():
    errors, _ = run(obs("o1", family="phone_call"), dec("d1", ["o1"], fields={}))
    assert any("office_name" in e for e in errors)


def test_basis_must_be_same_candidate():
    errors, _ = run(obs("o1", cid="loc:bbbbbbbbbbbbbbbb", family="phone_call"), dec("d1", ["o1"]))
    assert any("same candidate" in e for e in errors)


def test_stale_basis_rejected():
    errors, _ = run(obs("o1", family="phone_call", observed_at="2025-01-01"), dec("d1", ["o1"]))
    assert any("older than" in e for e in errors)


def test_retracted_basis_breaks_decision():
    errors, _ = run(obs("o1", family="phone_call"),
                    {**BASE, "entry_id": "r1", "type": "retract", "target_entry_id": "o1", "reason": "wrong office"},
                    dec("d1", ["o1"]))
    assert any("missing/retracted" in e for e in errors)


def test_later_decision_supersedes():
    errors, led = run(obs("o1", family="phone_call"), dec("d1", ["o1"]),
                      obs("o2", claim="closed", evidence="Recording: office permanently closed"),
                      dec("d2", ["o2"], status="CLOSED"))
    assert errors == []
    assert led["decisions"]["loc:aaaaaaaaaaaaaaaa"]["entry_id"] == "d2"


def test_duplicate_needs_existing_target():
    errors, _ = run(obs("o1", claim="duplicate_of"), dec("d1", ["o1"], status="DUPLICATE", duplicate_of="loc:zz"))
    assert any("duplicate_of" in e for e in errors)


def test_add_candidate_rules():
    good = {**BASE, "entry_id": "a1", "type": "add_candidate", "candidate_id": "ext:60602:smile-bar-loop",
            "zip": "60602", "name": "Smile Bar", "address": "10 N State St", "discovered_via": "google_business_profile",
            "source_url": "https://maps.example/abc"}
    errors, led = run(good)
    assert errors == [] and "ext:60602:smile-bar-loop" in led["ext"]
    errors, _ = run({**good, "candidate_id": "ext:606:x"})
    assert any("ext:<zip>:<slug>" in e for e in errors)
    errors, _ = run({**good, "source_url": "maps"})
    assert any("http(s)" in e for e in errors)


def test_vanished_builder_ids_are_orphans_not_errors():
    errors, led = run(obs("o1", cid="loc:cccccccccccccccc"))
    assert errors == [] and led["orphans"][0]["candidate_id"] == "loc:cccccccccccccccc"
    errors, _ = run(obs("o2", cid="ext:60602:never-added"))
    assert any("unknown candidate" in e for e in errors)


def test_duplicate_entry_ids_and_bad_json():
    errors, _ = oc.check_ledger([(1, obs("o1")), (2, obs("o1")), (3, {"_parse_error": "x"})], KNOWN, TODAY)
    assert any("duplicate entry_id" in e for e in errors) and any("invalid JSON" in e for e in errors)


def test_zip_sweep_rules():
    sweep = {**BASE, "entry_id": "s1", "type": "zip_sweep", "zip": "60602", "stage": "current_rows",
             "sources_searched": ["office_website", "google_business_profile"], "completed_at": "2026-09-24"}
    errors, led = run(sweep)
    assert errors == [] and led["sweeps"]["60602"]
    errors, _ = run({**sweep, "sources_searched": ["yellowpages"]})
    assert any("unknown source family" in e for e in errors)


def test_suite_of_keeps_distinct_suites():
    assert oc.suite_of("1 Main St # 1115") == "1115"
    assert oc.suite_of("1 Main St Ste 200") == "200"
    assert oc.suite_of("1 Main St Suite 0200") == "200"
    assert oc.suite_of("1 Main St 2nd Floor") is None
    assert oc.suite_of("1 Main St FL 2") == "FL2"
    assert oc.suite_of("1 Main St") is None


def test_loose_key_catches_spelling_variants_only_within_zip():
    a = oc.loose_key("314 N York St", "60126")
    assert a == oc.loose_key("314 n york st uppr", "60126")
    assert a != oc.loose_key("314 N York St", "60127")
    assert a != oc.loose_key("316 N York St", "60126")
    assert oc.loose_key("PO Box 12", "60126") is None


def test_taxonomy_scope():
    assert oc.taxonomy_scope(["122300000X"]) == "gp"
    assert oc.taxonomy_scope(["122300000X", "1223X0400X"]) == "mixed_gp_specialist"
    assert oc.taxonomy_scope(["1223X0400X"]) == "specialist_only"
    assert oc.taxonomy_scope([None, ""]) == "unknown"


def test_priorities_and_provisional_state():
    for origin, state, priority in [("data_axle_unrepresented", "LOCATION_INCOMPLETE", 1),
                                    ("directory_row", "IDENTITY_REVIEW", 2),
                                    ("directory_row", "EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION", 4)]:
        c = {"origin": origin, "queue_state": state, "flags": []}
        oc.prioritize(c)
        assert c["priority"] == priority
        assert (c["effort"] == "deferred") == (priority == 4)


def test_historical_evidence_preserves_date_and_never_confirms():
    c = {"location_id": "a", "source_refs": {}, "queue_state": "IDENTITY_REVIEW"}
    records = oc.historical_evidence(c, {"a": {"last_checked_at": "2026-01-02", "website_url": "https://example.com"}}, {}, {})
    assert records[0]["observed_at"] == "2026-01-02"
    assert records[0]["historical"] is True
    assert c["queue_state"] == "IDENTITY_REVIEW"
    assert records == oc.historical_evidence(c, {"a": {"last_checked_at": "2026-01-02", "website_url": "https://example.com"}}, {}, {})


def test_discovery_does_not_complete_candidate_review():
    cov = oc.zip_coverage({"60602": "Chicago"}, [], {"60602": [{"stage": "discovery", "completed_at": "2026-09-24", "sources_searched": ["office_website"], "notes": "Search query", "findings": []}]})[0]
    assert cov["stage"] == "not_started"
    assert cov["discovery_status"] == "pass_recorded"
    assert cov["last_discovery_at"] == "2026-09-24"


def test_zip_centroid_cannot_become_verified_marker():
    errors, _ = run(obs("o1"), dec("d1", ["o1"], fields={"office_name": "Test", "address": "1 Main", "suite_status": "none", "latitude": 41.8, "longitude": -87.6, "geocode_precision": "zip_centroid"}))
    assert any("never a ZIP centroid" in e for e in errors)


def test_source_records_preserve_suite_and_provider_identity():
    records = oc.source_records([], [{"npi": "1", "address": "10 Main Suite 1"}, {"npi": "2", "address": "10 Main Suite 2"}], [])
    assert [r["address"] for r in records] == ["10 Main Suite 1", "10 Main Suite 2"]


def test_numeric_locator_fragments_are_not_clean_address_leads():
    assert not oc.usable_street_address("1921")
    assert not oc.usable_street_address("Suite 1921")
    assert not oc.usable_street_address("PO Box 1921")
    assert oc.usable_street_address("30 N Michigan Ave Suite 1921")
    c = {"origin": "dso_locator_unrepresented", "queue_state": "SOURCE_CANDIDATE_UNREPRESENTED", "flags": ["source_name_missing"]}
    oc.prioritize(c)
    assert c["lead_quality"] == "flagged"
