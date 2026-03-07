"""Self-test for dental PE tracker database layer."""

import os
import sys
import tempfile
from datetime import date, datetime

# Allow imports from project root
sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.database import (
    init_db,
    get_session,
    insert_deal,
    insert_or_update_practice,
    log_practice_change,
    get_deals,
    get_practices,
    get_practice_changes,
    get_deal_stats,
    get_consolidation_score,
)


def run_tests():
    # Use a temporary database
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    try:
        # 1. Initialize
        print("1. Initializing test database...")
        init_db(db_path)
        session = get_session(db_path)

        # 2. Insert 5 sample deals
        print("2. Inserting 5 sample deals...")
        deals_data = [
            dict(
                deal_date=date(2024, 6, 1),
                platform_company="Aspen Dental",
                pe_sponsor="Ares Management",
                target_name="SmileCare Associates",
                target_city="Naperville",
                target_state="IL",
                target_zip="60540",
                deal_type="add-on",
                deal_size_mm=45.0,
                ebitda_multiple=12.5,
                specialty="general",
                num_locations=3,
                source="pitchbook",
                source_url="https://example.com/deal1",
                notes="Chicagoland expansion",
            ),
            dict(
                deal_date=date(2024, 7, 1),
                platform_company="Heartland Dental",
                pe_sponsor="KKR",
                target_name="Boston Smiles",
                target_city="Boston",
                target_state="MA",
                target_zip="02116",
                deal_type="buyout",
                deal_size_mm=120.0,
                ebitda_multiple=14.0,
                specialty="multi_specialty",
                num_locations=8,
                source="press_release",
            ),
            dict(
                deal_date=date(2024, 8, 1),
                platform_company="Pacific Dental Services",
                pe_sponsor=None,
                target_name="OrthoFirst",
                target_city="Aurora",
                target_state="IL",
                target_zip="60504",
                deal_type="growth",
                deal_size_mm=30.0,
                ebitda_multiple=10.0,
                specialty="orthodontics",
                num_locations=2,
                source="gdn",
            ),
            dict(
                deal_date=date(2024, 9, 1),
                platform_company="Dental Care Alliance",
                pe_sponsor="Harvest Partners",
                target_name="Perio Pros LLC",
                target_city="Cambridge",
                target_state="MA",
                target_zip="02138",
                deal_type="recapitalization",
                deal_size_mm=80.0,
                ebitda_multiple=11.0,
                specialty="periodontics",
                num_locations=5,
                source="pesp",
            ),
            dict(
                deal_date=date(2024, 10, 1),
                platform_company="MB2 Dental",
                pe_sponsor="Charlesbank",
                target_name="Joliet Family Dental",
                target_city="Joliet",
                target_state="IL",
                target_zip="60431",
                deal_type="de_novo",
                deal_size_mm=15.0,
                ebitda_multiple=8.5,
                specialty="general",
                num_locations=1,
                source="other",
            ),
        ]
        for d in deals_data:
            result = insert_deal(session, **d)
            assert result is True, f"Failed to insert deal: {d['target_name']}"

        # 3. Insert 10 sample practices
        print("3. Inserting 10 sample practices...")
        practices_data = [
            dict(npi="1234567890", practice_name="Naperville Family Dental", entity_type="organization",
                 address="123 Main St", city="Naperville", state="IL", zip="60540",
                 ownership_status="independent", data_source="nppes"),
            dict(npi="1234567891", practice_name="Heartland - Naperville", entity_type="organization",
                 address="456 Ogden Ave", city="Naperville", state="IL", zip="60540",
                 ownership_status="dso_affiliated", affiliated_dso="Heartland Dental",
                 affiliated_pe_sponsor="KKR", data_source="nppes"),
            dict(npi="1234567892", practice_name="Smile Dental Lemont", entity_type="organization",
                 address="789 State St", city="Lemont", state="IL", zip="60439",
                 ownership_status="independent", data_source="nppes"),
            dict(npi="1234567893", practice_name="Aspen Dental Bolingbrook", entity_type="organization",
                 address="100 Boughton Rd", city="Bolingbrook", state="IL", zip="60440",
                 ownership_status="pe_backed", affiliated_dso="Aspen Dental",
                 affiliated_pe_sponsor="Ares Management", data_source="data_axle"),
            dict(npi="1234567894", practice_name="Dr. Smith DDS", entity_type="individual",
                 address="200 Elm St", city="Downers Grove", state="IL", zip="60515",
                 ownership_status="independent", data_source="nppes"),
            dict(npi="1234567895", practice_name="Boston Dental Group", entity_type="organization",
                 address="300 Boylston St", city="Boston", state="MA", zip="02116",
                 ownership_status="dso_affiliated", affiliated_dso="Boston Dental Group",
                 data_source="nppes"),
            dict(npi="1234567896", practice_name="Cambridge Endodontics", entity_type="organization",
                 address="50 Brattle St", city="Cambridge", state="MA", zip="02138",
                 ownership_status="independent", data_source="nppes"),
            dict(npi="1234567897", practice_name="PDS - Aurora", entity_type="organization",
                 address="400 N Lake St", city="Aurora", state="IL", zip="60504",
                 ownership_status="dso_affiliated", affiliated_dso="Pacific Dental Services",
                 data_source="data_axle"),
            dict(npi="1234567898", practice_name="Joliet Pediatric Dentistry", entity_type="organization",
                 address="500 Jefferson St", city="Joliet", state="IL", zip="60431",
                 ownership_status="independent", data_source="nppes"),
            dict(npi="1234567899", practice_name="MB2 - Joliet", entity_type="organization",
                 address="600 Larkin Ave", city="Joliet", state="IL", zip="60431",
                 ownership_status="pe_backed", affiliated_dso="MB2 Dental",
                 affiliated_pe_sponsor="Charlesbank", data_source="manual"),
        ]
        for p in practices_data:
            insert_or_update_practice(session, **p)

        # 4. Log 3 practice changes
        print("4. Logging 3 practice changes...")
        log_practice_change(session, npi="1234567890", change_date=date(2024, 9, 15),
                            field_changed="practice_name", old_value="Naperville Dental",
                            new_value="Naperville Family Dental", change_type="name_change")
        log_practice_change(session, npi="1234567892", change_date=date(2024, 10, 1),
                            field_changed="ownership_status", old_value="independent",
                            new_value="dso_affiliated", change_type="acquisition",
                            notes="Acquired by Heartland Dental")
        log_practice_change(session, npi="1234567894", change_date=date(2024, 11, 1),
                            field_changed="address", old_value="150 Elm St",
                            new_value="200 Elm St", change_type="relocation")

        # 5. Get deal stats
        print("\n5. Deal statistics:")
        stats = get_deal_stats(session)
        for key, val in stats.items():
            print(f"   {key}: {val}")

        # 6. Consolidation score
        print("\n6. Consolidation scores:")
        for z in ["60540", "60431", "60515"]:
            score = get_consolidation_score(session, z)
            print(f"   ZIP {z}: {score}% consolidated")

        # 7. Duplicate rejection
        print("\n7. Testing duplicate rejection...")
        dup_result = insert_deal(session, **deals_data[0])
        assert dup_result is False, "Duplicate deal should have been rejected!"
        print("   Duplicate correctly rejected.")

        # Verify counts
        all_deals = get_deals(session)
        assert len(all_deals) == 5, f"Expected 5 deals, got {len(all_deals)}"
        il_deals = get_deals(session, target_state="IL")
        assert len(il_deals) == 3, f"Expected 3 IL deals, got {len(il_deals)}"
        il_practices = get_practices(session, state="IL")
        assert len(il_practices) == 8, f"Expected 8 IL practices, got {len(il_practices)}"
        changes = get_practice_changes(session, since_date=date(2024, 10, 1))
        assert len(changes) == 2, f"Expected 2 changes since Oct 1, got {len(changes)}"

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)

    finally:
        # 8. Cleanup
        session.close()
        if os.path.exists(db_path):
            os.unlink(db_path)
            print("Test database cleaned up.")


if __name__ == "__main__":
    run_tests()
