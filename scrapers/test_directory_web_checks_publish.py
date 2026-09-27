"""Tests for the Directory web-check publisher (no DB, no network).

    python3 -m pytest scrapers/test_directory_web_checks_publish.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import directory_web_checks_publish as pub  # noqa: E402
import office_census_rapid as rv  # noqa: E402
from test_office_census_rapid import card, rec  # noqa: E402


def check(cid, decision, session="s1", **kw):
    e = {"candidate_id": cid, "zip": "60100", "decision": decision, "checked_at": "2026-09-25",
         "recorded_at": "2026-09-25T21:10:46+00:00", "session": session, "as_seen": {"name": "X"}}
    e.update(kw)
    return e


def rows(*checks):
    return pub.build_rows({c["candidate_id"]: c for c in checks}, "dwc-test")


def test_every_decision_maps_to_an_effect():
    assert set(pub.EFFECT) == set(rv.DECISIONS)
    assert pub.EFFECT["NOT_CURRENT_GP"] == "removed"
    assert pub.EFFECT["NO_WEB_EVIDENCE"] == "no_web_evidence"   # never a removal


def test_row_strips_location_prefixes_and_defaults_json():
    r = rows(check("loc:aaaa", "NOT_CURRENT_GP", reason="duplicate", duplicate_of="loc:bbbb"))[0]
    assert r["location_id"] == "aaaa" and r["duplicate_of"] == "bbbb" and r["effect"] == "removed"
    assert r["observed"] == {} and r["signals"] == [] and r["ties_by"] == []
    assert set(r) == set(pub.COLS)


def test_latest_check_wins(tmp_path):
    rv.P.set(tmp_path)
    (tmp_path / "checks.jsonl").write_text(
        '{"candidate_id":"loc:a","decision":"IDENTITY_ONLY"}\n{"candidate_id":"loc:a","decision":"VALID","supersede":true}\n')
    assert rv.latest_checks()["loc:a"]["decision"] == "VALID"


def test_high_removal_share_blocks_publish():
    rs = rows(*[check(f"loc:{i:04d}", "NOT_CURRENT_GP" if i < 10 else "VALID", session=f"s{i % 3}")
                for i in range(25)])
    errs = pub.problems(rs, [])
    assert any("of checked rows" in e for e in errs)
    assert pub.problems(rs, [], allow_high_removal=True) == []


def test_runaway_session_blocks_publish():
    good = [check(f"loc:g{i:03d}", "VALID", session="good") for i in range(60)]
    bad = [check(f"loc:b{i:03d}", "NOT_CURRENT_GP" if i < 15 else "VALID", session="bad") for i in range(20)]
    errs = pub.problems(rows(*good, *bad), [])
    assert len(errs) == 1 and "session bad" in errs[0]


def test_validation_errors_block_publish():
    assert pub.problems(rows(check("loc:a", "VALID")), ["line 3 loc:a: bad"]) == ["check: line 3 loc:a: bad"]


# ---- ties_by rule (rules .2) -----------------------------------------------------------
CLOSED = {"decision": "NOT_CURRENT_GP", "reason": "closed", "evidence": [
    {"kind": "listing", "url": "https://www.yelp.com/biz/x", "quote": "X - CLOSED - 100 W Main St"}]}


def test_removal_needs_ties_by():
    assert any("ties_by" in e for e in rv.validate(rec(**CLOSED), card(), False))
    assert rv.validate(rec(ties_by=["dentist"], **CLOSED), card(), False) == []


def test_closure_tied_only_by_address_is_rejected():
    errs = rv.validate(rec(ties_by=["address"], **CLOSED), card(), False)
    assert any("beyond the address" in e for e in errs)
    home = dict(CLOSED, reason="home_or_registration")
    assert rv.validate(rec(ties_by=["address"], **home), card(), False) == []


def test_checks_recorded_under_old_rules_stay_valid():
    assert rv.validate(rec(**CLOSED), card(), False, rules="rapid-2026-09-25.1") == []
