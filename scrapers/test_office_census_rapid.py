"""Tests for the rapid-validation queue, routing and record rules (no DB, no network).

    python3 -m pytest scrapers/test_office_census_rapid.py -q
"""
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census_rapid as rv  # noqa: E402

PROVIDERS = {"1": ("Carla Francis", None), "2": ("Kimberly Sheppard", "perio"), "3": ("James Sislow", None)}


def cand(cid="loc:aaaaaaaaaaaaaaaa", name="Main Street Dental", address="100 w main st", zip_code="60100",
         phone="(630) 555-0100", website=None, flags=(), npis=(), **kw):
    c = {"candidate_id": cid, "origin": "directory_row", "zip": zip_code, "city": "SPRINGFIELD",
         "name": name, "address": address, "suite": None, "suites_seen": [], "phone": phone,
         "website": website, "entity_classification": "solo_established", "provider_count": len(npis),
         "flags": list(flags), "queue_state": "EXISTING_EVIDENCE_NO_CURRENT_CONTRADICTION",
         "prior_evidence": {}, "source_refs": {"npis": list(npis)}}
    c.update(kw)
    return c


def card(**kw):
    return rv.make_card(cand(**kw), PROVIDERS)


# ---- query generation ----------------------------------------------------------
def test_address_phrase_drops_suffix_keeps_directional():
    assert rv.address_phrases("3426 w armitage ave") == ["3426 W Armitage"]
    assert rv.address_phrases("2421 183rd st") == ["2421 183rd"]


def test_run_together_street_is_split_and_saint_variant_added():
    assert rv.address_phrases("4209stcharles rd") == ["4209 St Charles", "4209 Saint Charles"]


def test_grid_address_kept_intact():
    assert rv.address_phrases("2s676 state route 59") == ["2S676 State Route 59"]


def test_no_house_number_gives_no_phrase():
    assert rv.address_phrases("po box 12") == []


def test_generated_name_is_never_searched():
    c = card(name="Sharma Dental", flags=["name_possibly_generated"], npis=["1"])
    qs = " ".join(q["q"] for q in c["queries"])
    assert "Sharma Dental" not in qs
    assert c["queries"][0]["kind"] == "ADDR"


def test_person_style_names_are_untrusted():
    assert not rv.name_is_trusted("Nisbeth Basit G DDS", [])
    assert not rv.name_is_trusted("ERIKA L KROUTH DDS PC", [])
    assert not rv.name_is_trusted("TIMOTHY L. STRAKA D.D.S., L.L.C.", [])
    assert not rv.name_is_trusted("JAMES L ORRINGTON DDS,PC", [])
    assert not rv.name_is_trusted("Francis Carla", [], ["Carla Francis"])
    assert rv.name_is_trusted("Krafcisin & Assoc", [])
    assert rv.name_is_trusted("AMERICAN FAMILY DENTAL CARE P.C", [])


def test_untrusted_name_routes_address_then_provider():
    c = card(name="Francis Carla", npis=["1"])
    assert c["route"] == "untrusted_name"
    assert [q["kind"] for q in c["queries"]][:2] == ["ADDR", "PROVIDER"]
    assert '"Carla Francis"' in c["queries"][1]["q"]


def test_legal_name_without_providers_searches_the_person():
    c = card(name="TIMOTHY L. STRAKA D.D.S., L.L.C.")
    prov = [q["q"] for q in c["queries"] if q["kind"] == "PROVIDER"]
    assert prov and prov[0].startswith('"Timothy L Straka"')


def test_moved_note_searches_name_first():
    c = card(name="Creekside Dental", flags=["prior_note_moved"])
    assert c["route"] == "moved_or_successor"
    assert c["queries"][0]["kind"] == "NAME"


def test_home_like_and_non_il_phone_route_to_provider():
    c = card(name="Rifai Sarah Amr DDS", address="1564 wind energy pass", phone="(856) 505-7302", npis=["1"])
    assert c["home_like"] and c["non_il_phone"] and c["route"] == "home_like"


def test_specialty_tag_shown_and_gp_provider_preferred():
    c = card(name="Sheppard Dental", flags=["name_possibly_generated"], npis=["2", "3"])
    assert "Kimberly Sheppard (perio)" in c["providers"]
    assert '"James Sislow"' in [q for q in c["queries"] if q["kind"] == "PROVIDER"][0]["q"]


def test_live_site_check_url_beats_wrong_vendor_url():
    c = card(website="Decisiononedental.Com",
             prior_evidence={"job_hunt_check": {"website_status": "live", "public_name": "Hamilton Lakes Dentistry",
                                                "website_url": "https://www.hamiltonlakesdentistry.com/"}})
    assert c["website"] == "https://www.hamiltonlakesdentistry.com/"
    assert c["public_name"] == "Hamilton Lakes Dentistry"


def test_prior_status_notes_surface_verbatim():
    c = card(prior_evidence={"historical_observations": [{"evidence": {
        "red_flags": json.dumps(["Practice owner deceased as of January 22, 2026; practice closed in 2023.",
                                 "Minimal online review presence."])}}]})
    assert c["status_notes"] == ["Practice owner deceased as of January 22, 2026; practice closed in 2023."]


# ---- lanes -------------------------------------------------------------------------
def test_lanes():
    assert rv.lane_of(cand(zip_code="60611"), set(), set())[0] == "building"
    assert rv.lane_of(cand(flags=["high_provider_count"]), set(), set())[0] == "building"
    assert rv.lane_of(cand(suites_seen=["1", "2", "3"]), set(), set())[0] == "building"
    assert rv.lane_of(cand(), {"loc:aaaaaaaaaaaaaaaa"}, set())[0] == "census_done"
    assert rv.lane_of(cand(), set(), {"60100"})[0] == "census_done"
    assert rv.lane_of(cand(flags=["multi_org_multi_phone"]), set(), set())[0] == "rapid"


# ---- record validation -------------------------------------------------------------
SITE = {"kind": "first_party_site", "url": "https://mainstreetdental.com/contact"}


def rec(**kw):
    r = {"candidate_id": "loc:aaaaaaaaaaaaaaaa", "decision": "VALID", "gp_scope": "gp",
         "evidence": [SITE], "searches": 1, "fetches": 0}
    r.update(kw)
    return r


def errs(r, done=False):
    return rv.validate(r, card(), done)


def test_valid_with_first_party_site_passes():
    assert errs(rec()) == []


def test_listing_alone_cannot_validate():
    assert any("Listings alone" in e for e in
               errs(rec(evidence=[{"kind": "listing", "url": "https://www.yelp.com/biz/x"}])))


def test_valid_with_changed_field_must_be_corrected():
    assert any("VALID_CORRECTED" in e for e in errs(rec(observed={"phone": "630-555-0199"})))
    assert errs(rec(decision="VALID_CORRECTED", observed={"phone": "630-555-0199"})) == []


def test_corrected_needs_a_real_difference():
    e = errs(rec(decision="VALID_CORRECTED", observed={"phone": "630.555.0100", "name": "MAIN STREET DENTAL"}))
    assert any("at least one observed field" in x for x in e)


def test_closure_needs_quoted_positive_evidence():
    r = rec(decision="NOT_CURRENT_GP", reason="closed", ties_by=["name"],
            evidence=[{"kind": "listing", "url": "https://www.yelp.com/biz/x"}])
    assert any("positive evidence" in e for e in errs(r))
    r["evidence"][0]["quote"] = "DENTAL CORNER - CLOSED"
    assert errs(r) == []


def test_no_web_evidence_needs_two_searches_and_note():
    e = errs(rec(decision="NO_WEB_EVIDENCE", evidence=[], searches=1))
    assert any("2 searches" in x for x in e) and any("needs a note" in x for x in e)


def test_every_row_needs_a_fresh_search():
    assert any("fresh search" in e for e in errs(rec(searches=0)))


def test_duplicate_needs_supersede():
    assert any("supersede" in e for e in errs(rec(), done=True))
    assert errs(rec(supersede=True), done=True) == []


def test_unknown_signal_and_bad_url_rejected():
    e = errs(rec(signals=["vibes"], evidence=[{"kind": "first_party_site", "url": "mainstreet.com"}]))
    assert any("signals" in x for x in e) and any("http(s)" in x for x in e)


# ---- record end-to-end (temp dir) ----------------------------------------------------
def setup_dir(tmp_path, monkeypatch):
    rv.P.set(tmp_path)
    c1 = card()
    c1.update(position=1, lane="calibration")
    c2 = rv.make_card(cand(cid="loc:bbbbbbbbbbbbbbbb", name="Other Dental", address="200 e oak st",
                           phone="(630) 555-0200"), PROVIDERS)
    c2.update(position=2, lane="zip_order")
    (tmp_path / "queue.jsonl").write_text(json.dumps(c1) + "\n" + json.dumps(c2) + "\n")
    idx = {"by_street": {"|".join(rv.oc.street_key("200 e oak st", "60100")): ["loc:bbbbbbbbbbbbbbbb"]},
           "by_phone": {"6305550200": ["loc:bbbbbbbbbbbbbbbb"]},
           "entries": {"loc:bbbbbbbbbbbbbbbb": ["loc:bbbbbbbbbbbbbbbb", "directory_row", "60100", "Other Dental",
                                                 "200 e oak st", None, "(630) 555-0200", "X"]}}
    (tmp_path / "index.json").write_text(json.dumps(idx))
    monkeypatch.setattr(rv, "load_ledger_state", lambda: (set(), set()))


def test_record_appends_and_flags_collision(tmp_path, monkeypatch, capsys):
    setup_dir(tmp_path, monkeypatch)
    moved = rec(decision="VALID_CORRECTED", observed={"address": "200 E Oak St", "suite": "5"})
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(moved)))
    assert rv.main(["--rapid-dir", str(tmp_path), "record", "--session", "t"]) == 0
    out = capsys.readouterr().out
    assert "COLLISION" in out and "loc:bbbbbbbbbbbbbbbb" in out
    line = json.loads((tmp_path / "checks.jsonl").read_text().splitlines()[0])
    assert line["type"] == "rapid_check" and line["as_seen"]["name"] == "Main Street Dental"
    assert line["collisions"][0]["via"] == "address"


def test_next_skips_checked_and_claimed_rows(tmp_path, monkeypatch, capsys):
    setup_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(rv, "dns_status", lambda urls: {})
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "a"]) == 0
    assert "loc:aaaaaaaaaaaaaaaa" in capsys.readouterr().out
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "b"]) == 0
    assert "loc:bbbbbbbbbbbbbbbb" in capsys.readouterr().out   # a's claim is respected
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "a"]) == 0
    assert "loc:aaaaaaaaaaaaaaaa" in capsys.readouterr().out   # a gets its own claim back


def test_multiple_pretty_printed_objects_parse():
    text = '{\n "a": 1\n}\n{\n "b": 2\n}'
    assert rv.parse_objects(text) == [{"a": 1}, {"b": 2}]


def test_search_budget_stops_new_claims_and_release_returns_rows(tmp_path, monkeypatch, capsys):
    setup_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(rv, "dns_status", lambda urls: {})
    monkeypatch.setattr(rv, "SEARCH_BUDGET", 3)
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "a"]) == 0
    assert "loc:aaaaaaaaaaaaaaaa" in capsys.readouterr().out
    (tmp_path / "checks.jsonl").write_text(json.dumps({"candidate_id": "loc:zzzz", "session": "a", "searches": 3,
                                                       "recorded_at": "2026-09-25T21:00:00+00:00"}) + "\n")
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "2", "--session", "a"]) == 0
    out = capsys.readouterr().out
    assert "loc:aaaaaaaaaaaaaaaa" in out and "loc:bbbbbbbbbbbbbbbb" not in out   # finishes its claim only
    assert rv.main(["--rapid-dir", str(tmp_path), "release", "--session", "a"]) == 0
    assert "released 1" in capsys.readouterr().out
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "a"]) == 0
    assert "SEARCH BUDGET REACHED" in capsys.readouterr().out
