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
         "fields": {"office_name": "Main Street Dental"}}
    e.update(kw)
    return e


def run(*entries, known=KNOWN):
    return oc.check_ledger(list(enumerate(entries, 1)), known, TODAY)


def test_website_alone_cannot_confirm():
    errors, led = run(obs("o1"), dec("d1", ["o1"]))
    assert any("2 independent source families" in e for e in errors)


def test_two_families_confirm():
    errors, led = run(obs("o1"), obs("o2", family="google_business_profile"), dec("d1", ["o1", "o2"]))
    assert errors == []
    assert led["decisions"]["loc:aaaaaaaaaaaaaaaa"]["terminal_status"] == "OPERATING_GP_CONFIRMED"


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
