"""Rule tests for office_census_v2_rules: each rule fires on its case and abstains on the look-alike
case that misfired in calibration (2026-09-27). Synthetic packets; no I/O."""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census_v2_rules as R  # noqa: E402

TODAY = datetime.date(2026, 9, 27)
RECENT = [{"publishTime": "2026-08-01T00:00:00Z"}]
STALE = [{"publishTime": "2025-01-01T00:00:00Z"}]


def place(name, phone="(630) 555-0100", status="OPERATIONAL", at_site=True, reviews=RECENT, zip_code="60100",
          ptype="dentist", rows_here=(), addr="100 W Main St, Springfield, IL 60100"):
    return {"id": name, "displayName": {"text": name}, "nationalPhoneNumber": phone, "businessStatus": status,
            "types": [ptype], "primaryType": ptype, "reviews": reviews, "_at_site": at_site, "_zip": zip_code,
            "_rows_here": list(rows_here), "formattedAddress": addr, "googleMapsUri": "https://maps.google.com/?cid=1"}


def packet(at_site=(), phone_listings=(), elsewhere=(), licenses=(), iema_site=(), home=False, base=None,
           name="Main Street Dental", providers=("Jane Smith",), iema_dentist_elsewhere=(), other_rows=()):
    return {"cid": "loc:aaaa", "role": "unresolved",
            "card": {"name": name, "public_name": name, "address": "100 W Main St", "city": "Springfield",
                     "zip": "60100", "phone": "(630) 555-0100", "providers": list(providers), "home_like": home},
            "base": base or {"decision": "IDENTITY_ONLY"},
            "iema_site": list(iema_site), "iema_dentist_elsewhere": list(iema_dentist_elsewhere),
            "iema_phone_elsewhere": [], "licenses": list(licenses), "browser": [], "row_hosts": [],
            "other_rows_site": list(other_rows),
            "places": {"probed": True, "at_site": list(at_site), "phone_listings": list(phone_listings),
                       "elsewhere_listings": list(elsewhere)}}


def run(p):
    ev = R.evaluate(p, TODAY)
    return ev, ev["proposal"], R.publish_tier(p, ev)


# ---- open rules ---------------------------------------------------------------------------------
def test_pl_recent_valid_and_publishable():
    ev, pr, (ok, _) = run(packet(at_site=[place("Main Street Dental")]))
    assert pr["rule_id"] == "PL-RECENT" and pr["decision"] == "VALID" and pr["confidence"] == "auto" and ok


def test_pl_recent_abstains_on_stale_reviews():
    ev, pr, _ = run(packet(at_site=[place("Main Street Dental", reviews=STALE)]))
    assert "PL-RECENT" not in ev["fired"]


def test_practitioner_listing_with_other_phone_is_not_a_tie():
    ev, pr, _ = run(packet(at_site=[place("Dr. Jane Smith, DDS", phone="(630) 555-0999")]))
    assert not pr or pr["decision"] not in ("VALID", "VALID_CORRECTED") or pr["rule_id"] == "SUCCESSOR"
    assert "PL-RECENT" not in ev["fired"]


def test_place_only_tie_is_a_successor_correction_never_published():
    ev, pr, (ok, why) = run(packet(at_site=[place("Bright Valley Dental")]))
    assert pr["decision"] == "VALID_CORRECTED" and pr["observed"]["name"] == "Bright Valley Dental"
    assert set(pr["signals"]) & {"successor_practice", "rebranded"}
    assert not ok


def test_successor_in_a_multi_tenant_building_goes_to_review():
    ev, pr, _ = run(packet(at_site=[place("Bright Valley Dental"), place("Oak Dental", phone="(630) 555-0222")]))
    assert not pr or pr["confidence"] == "review" or pr["decision"] == "NOT_CURRENT_GP"


def test_dentist_only_tie_does_not_publish_a_wrong_row_name():
    p = packet(name="Peacock Dental", providers=("Jon Nickelsen",),
               at_site=[place("Nickelsen Family Dental", phone="(630) 555-0100")])
    ev, pr, (ok, why) = run(p)
    assert pr and not ok


def test_identity_problem_rows_are_held_for_an_agent():
    p = packet(at_site=[place("Main Street Dental")], base={"decision": "IDENTITY_PROBLEM"})
    ev, pr, (ok, why) = run(p)
    assert pr["decision"] == "VALID" and not ok


# ---- not-current rules --------------------------------------------------------------------------
def test_pl_closed_fires_on_tied_closed_listing():
    ev, pr, (ok, _) = run(packet(at_site=[place("Smith Jane DDS", status="CLOSED_PERMANENTLY")]))
    assert pr["rule_id"] == "PL-CLOSED" and pr["reason"] == "closed" and ok


def test_pl_closed_abstains_when_the_office_still_operates():
    ev, pr, _ = run(packet(at_site=[place("Main Street Dental", status="CLOSED_PERMANENTLY", phone="(630) 555-0777"),
                                    place("Main Street Dental")]))
    assert "PL-CLOSED" not in ev["fired"]


NOT_RENEWED = {"status": "NOT RENEWED", "name": "JANE SMITH DDS", "url": "https://data.illinois.gov/x",
               "description": "LICENSED DENTIST", "expiration_date": "09/30/2024"}


def test_lic_closed_needs_every_license_lapsed_and_nothing_at_site():
    ev, pr, (ok, _) = run(packet(licenses=[NOT_RENEWED]))
    assert pr["rule_id"] == "LIC-CLOSED" and ok
    ev, pr, _ = run(packet(licenses=[NOT_RENEWED, dict(NOT_RENEWED, status="ACTIVE")]))
    assert "LIC-CLOSED" not in ev["fired"]


def test_lic_closed_abstains_when_the_phone_answers_elsewhere():
    ev, pr, _ = run(packet(licenses=[NOT_RENEWED],
                           phone_listings=[place("Main Street Dental", at_site=False, zip_code="60200")]))
    assert "LIC-CLOSED" not in ev["fired"]


def test_home_needs_residential_form_and_nothing_dental():
    ev, pr, (ok, _) = run(packet(home=True))
    assert pr["rule_id"] == "HOME-R" and pr["reason"] == "home_or_registration" and ok
    ev, pr, _ = run(packet(home=True, at_site=[place("Other Dental", phone="(630) 555-0300", reviews=STALE)]))
    assert "HOME-R" not in ev["fired"]


def test_home_is_never_inferred_from_absence_alone():
    ev, pr, _ = run(packet(home=False))
    assert "HOME-R" not in ev["fired"] and not pr


def test_moved_ph_publishes_only_when_the_listing_name_ties():
    moved = place("Main Street Dental", at_site=False, zip_code="60200", addr="9 Oak Rd, Elsewhere, IL 60200")
    ev, pr, (ok, _) = run(packet(phone_listings=[moved]))
    assert pr["rule_id"] == "MOVED-PH" and pr["reason"] == "moved" and "name" in pr["ties_by"] and ok
    buyer = place("Van Beek Family Dental", at_site=False, zip_code="60200", addr="9 Oak Rd, Elsewhere, IL 60200")
    ev, pr, (ok, why) = run(packet(phone_listings=[buyer]))
    assert pr["rule_id"] == "MOVED-PH" and not ok


def test_moved_ph_abstains_on_an_in_zip_move_to_an_unlisted_address():
    near = place("Main Street Dental", at_site=False, zip_code="60100", addr="500 Elm St, Springfield, IL 60100")
    ev, pr, _ = run(packet(phone_listings=[near]))
    assert "MOVED-PH" not in ev["fired"]


def test_moved_ph_abstains_when_the_row_phone_still_answers_at_the_site():
    moved = place("Main Street Dental", at_site=False, zip_code="60200")
    ev, pr, _ = run(packet(phone_listings=[moved], at_site=[place("Main Street Dental")]))
    assert "MOVED-PH" not in ev["fired"]


def test_moved_by_dentist_name_is_review_only():
    fac = {"status": "Open", "active_units": 3, "mobile_only": False, "physical_address": "7 Far Rd, Far, IL 60300",
           "site_key": ("60300", "7", "far"), "name": "Far Dental", "administrator": "Jane Smith, DDS",
           "url": "https://public.iema.state.il.us/x", "phone": "(630) 555-0400"}
    ev, pr, (ok, _) = run(packet(iema_dentist_elsewhere=[fac]))
    assert pr and pr["rule_id"] == "MOVED-D" and pr["confidence"] == "review" and not ok
