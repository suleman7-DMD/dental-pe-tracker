"""Reclassify the verified-corporate IL locations that the name/EIN classifier
missed, raising the documented corporate FLOOR from its undercounted 4.02%.

Background: the headline floor (zip_scores.corporate_location_count /
total_gp_locations = 200/4,970 = 4.02%) only counts locations the classifier
could PROVE corporate by brand/EIN match. DSOs routinely operate IL offices
under local P.C. names (Heartland -> "Dental Professionals of Illinois, P.C.",
1st Family -> local DBA, etc.) that name-matching can't see, so those land in
solo_/small_group/large_group and undercount the floor.

scrapers/seed_il_dso_locations.py unioned three REAL address sources (federal
NPPES brand-mine, web-search-VERIFIED friendly-PC NPPES clusters, and the DSOs'
own public locator pages) and cross-referenced them against practice_locations.
This script promotes the watched-ZIP GP locations that are (a) in that verified
set AND (b) currently in an independent class -> corporate, then RECOMPUTES
zip_scores from practice_locations so the floor reflects them.

Idempotent: the promotion only touches independent-class rows; after the first
run those rows are dso_*, so re-running finds nothing to flip and the zip_scores
recompute (a COUNT of current dso_* per ZIP) is stable.

Confidence is HIGH for every promoted row (web-verified cluster, DSO's own
public claim, or federal brand match). Reasoning + source provenance + the prior
class are written to classification_reasoning for full auditability.

GATED: raises a headline number. Run only on explicit user confirmation.
After running, sync zip_scores + practice_locations + practices to Supabase for
the live site to reflect the new floor.
"""
import glob
import json
import os
import sqlite3

from scrapers.seed_il_dso_locations import xref_key

DB = "data/dental_pe_tracker.db"
MERGED = "data/dso_research/il_dso_locations_merged.json"
# Phase C web-verification output (verify_flip_candidates.py). Additive: confirmed
# DSO friendly-PC locations that name/EIN/PSC detectors surfaced and a forced-search
# Claude pass then CONFIRMED with source URLs. Same schema as MERGED; unioned below.
PHASEC = "data/dso_research/il_dso_phasec_verified.json"
# Phase 4 Data-Axle structural-verification output (build_data_axle_verified.py).
# Additive: GP locations the Data-Axle-powered detector fleet (B1 name-chain +
# B2 EIN/parent/officer + B7 PSC) surfaced and FREE WebSearch / already-corporate
# EIN-member cross-validation then confirmed. Each row's `address` is the
# location's own practice_locations.normalized_address, so xref_key matches
# exactly. Dict-shaped ({"locations": [...]}); unioned below.
DATA_AXLE = "data/dso_research/il_dso_data_axle_verified.json"
# False-corporate demotion audits (demote_false_corporate_il.py round 1,
# demote_false_corporate_round2.py, and any future rounds). Every location_id in
# a `demotions` list was WEB-VERIFIED independent (Evenly parent_iusa placeholder
# / landlord-name / bad-seed / franchise-name-collision false positives) — NEVER
# re-promote them, even when a seed file still matches their address (several
# demoted locations sit at addresses present in UDP/cluster seed rows whose
# attribution turned out to be wrong, e.g. Comfort Dental Care 96ef01b3b198c50b
# and 1st Choice 6af9e37687d09b08 in round 2).
DEMOTIONS_GLOB = "data/dso_research/il_false_corporate_demotions_*.json"

INDEP = ("solo_established", "solo_new", "solo_inactive", "solo_high_volume",
         "family_practice", "small_group", "large_group")

# Known national brands -> dso_national; everything else brand-matched ->
# dso_regional. (Both count as corporate; this only affects the sub-split, not
# the floor, so the exact partition is cosmetic.)
NATIONAL = {
    "Heartland Dental", "Aspen Dental", "Affordable Care",
    "Affordable Dentures & Implants", "Western Dental", "Smile Doctors",
    "Dental Dreams", "Comfort Dental", "Access Dental",
}


def main(apply=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    # ---- before snapshot ----
    gp, corp0 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    print(f"BEFORE  corporate floor = {corp0}/{gp} = {100*corp0/gp:.2f}%")

    # ---- index practice_locations (watched IL) by xref_key ----
    pl = {}
    for r in c.execute("""
        SELECT pl.location_id, pl.normalized_address, pl.zip, pl.city,
               pl.entity_classification, pl.practice_name,
               pl.primary_npi, pl.org_npi, pl.provider_npis
        FROM practice_locations pl
        JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
        WHERE w.state='IL'"""):
        k = xref_key(r["normalized_address"], r["zip"])
        if k and k not in pl:   # first wins; collisions rare within a ZIP
            pl[k] = r

    # ---- derive the promote set: verified-corporate ∩ currently-independent ----
    merged = json.load(open(MERGED))
    # Union in Phase C web-verified confirmed locations (same schema), if present.
    if os.path.exists(PHASEC):
        phasec = json.load(open(PHASEC))
        print(f"  + {len(phasec)} Phase C web-verified records unioned from {PHASEC}")
        merged = merged + phasec
    # Union in Phase 4 Data-Axle structural-verified locations, if present. File is
    # dict-shaped ({"locations":[...]}); each record's `address` is already the
    # location's normalized_address so xref_key matches exactly.
    if os.path.exists(DATA_AXLE):
        da = json.load(open(DATA_AXLE))
        da_locs = da.get("locations", da) if isinstance(da, dict) else da
        print(f"  + {len(da_locs)} Data-Axle structural-verified records unioned from {DATA_AXLE}")
        merged = merged + da_locs
    # Exclusion set: web-verified false-corporate demotions are final. Union
    # every demotion round so no future seed/verify pass can re-promote them.
    exclude = set()
    for path in sorted(glob.glob(DEMOTIONS_GLOB)):
        data = json.load(open(path))
        ids = {d["location_id"] for d in data.get("demotions", [])}
        exclude |= ids
        print(f"  - {len(ids)} verified false-corporate locations excluded via {path}")
    promote = {}   # location_id -> dict
    for loc in merged:
        if not loc.get("in_watched"):
            continue
        k = xref_key(loc["address"], loc["zip"])
        row = pl.get(k)
        if not row or row["entity_classification"] not in INDEP:
            continue
        lid = row["location_id"]
        if lid in promote or lid in exclude:
            continue
        brand = loc["dso_name"]
        promote[lid] = {
            "row": row, "brand": brand,
            "sponsor": loc.get("pe_sponsor"),
            "sources": "+".join(loc.get("_sources", [])),
            "ec": "dso_national" if brand in NATIONAL else "dso_regional",
            "old": row["entity_classification"],
        }

    print(f"PROMOTE {len(promote)} watched-IL GP locations independent -> corporate")
    if not promote:
        print("nothing to promote (already applied?) — recomputing zip_scores anyway")

    if not apply:
        for lid, p in list(promote.items())[:80]:
            r = p["row"]
            print(f"  [{p['old']:16}->{p['ec']:12}] {r['normalized_address'][:30]:30} "
                  f"{r['zip']}  {p['brand']}  ({p['sources']})")
        c.close()
        return

    # ---- apply: practice_locations ----
    cur = c.cursor()
    npis_to_flip = {}   # npi -> promote-record (dicts aren't hashable in a set)
    for lid, p in promote.items():
        r = p["row"]
        sp = p["sponsor"]
        own = "pe-backed" if sp else "dso-affiliated"
        reason = (f"IL DSO seeding 2026-05-30: verified-corporate "
                  f"({p['brand']}{'/'+sp if sp else ''}) via {p['sources']}; "
                  f"was {p['old']} — friendly-PC/local-name hid DSO ownership "
                  f"from name/EIN classifier.")
        cur.execute("""
            UPDATE practice_locations
               SET entity_classification=?, ownership_status=?,
                   affiliated_dso=?, affiliated_pe_sponsor=?,
                   classification_reasoning=?, classification_confidence=90,
                   updated_at=datetime('now')
             WHERE location_id=?""",
                    (p["ec"], own, p["brand"], sp, reason, lid))
        for col in ("primary_npi", "org_npi"):
            if r[col]:
                npis_to_flip[r[col]] = p
        if r["provider_npis"]:
            try:
                for n in json.loads(r["provider_npis"]):
                    if n:
                        npis_to_flip[n] = p
            except Exception:
                pass

    # ---- apply: underlying practices NPIs (only if currently independent) ----
    flipped_npi = 0
    for npi, p in npis_to_flip.items():
        sp = p["sponsor"]
        own = "pe-backed" if sp else "dso-affiliated"
        # updated_at bump is REQUIRED: raw sqlite3 bypasses the ORM's
        # onupdate=func.now(), and a stale updated_at leaves the flip
        # invisible to any incremental sync path + corrupts the audit trail.
        res = cur.execute("""
            UPDATE practices
               SET entity_classification=?, ownership_status=?,
                   updated_at=datetime('now')
             WHERE npi=? AND (entity_classification IS NULL
                   OR entity_classification IN
                   ('solo_established','solo_new','solo_inactive',
                    'solo_high_volume','family_practice','small_group',
                    'large_group','org_only_npi'))""",
                          (p["ec"], own, npi))
        flipped_npi += res.rowcount

    # ---- recompute zip_scores from practice_locations (idempotent) ----
    for r in c.execute("SELECT zip_code FROM zip_scores WHERE state='IL'").fetchall():
        z = r["zip_code"]
        n = c.execute("""SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=? AND entity_classification
            IN ('dso_regional','dso_national')""", (z,)).fetchone()[0]
        # FRACTION scale (0-1), matching merge_and_score.compute_saturation_metrics.
        # (A 100.0* here once wrote percent-scale rows that the next merge pass
        # silently re-masked — keep this in fraction scale.)
        cur.execute("""UPDATE zip_scores
            SET corporate_location_count=?,
                corporate_share_pct=CASE WHEN total_gp_locations>0
                    THEN ROUND(1.0*?/total_gp_locations,4) ELSE 0 END
            WHERE zip_code=?""", (n, n, z))
    c.commit()

    gp2, corp1 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    print(f"AFTER   corporate floor = {corp1}/{gp2} = {100*corp1/gp2:.2f}%  "
          f"(+{corp1-corp0} locations, +{100*corp1/gp2 - 100*corp0/gp:.2f} pts)")
    print(f"  practices NPI rows flipped to corporate: {flipped_npi}")
    # sanity: location-level corporate by class
    print("  location-level corporate now:",
          dict(c.execute("""SELECT entity_classification, COUNT(*) FROM practice_locations pl
              JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
              WHERE w.state='IL' AND entity_classification IN ('dso_regional','dso_national')
              GROUP BY entity_classification""").fetchall()))
    print("\nNEXT: sync to Supabase so the live floor updates:")
    print("  python3 -m scrapers._sync_dso_locations_only   # DSO overlay")
    print("  (and zip_scores + practice_locations + practices for the floor)")
    c.close()


if __name__ == "__main__":
    import sys
    main(apply="--dry-run" not in sys.argv)
