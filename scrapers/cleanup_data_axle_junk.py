"""Purge unverifiable Data-Axle-only records from the GP denominator and clean
junk Data-Axle corporate-linkage labels (2026-06-12 data-integrity audit).

Background: the Data Axle importer created practice rows keyed `DA_<hash>`
(no federal NPI), and `dedup_practice_locations.py` emitted locations whose
ONLY evidence is those synthetic rows — 430 in the watched ZIPs. The census
agent (Census ZBP NAICS 621210 cross-check) found the watched GP denominator
inflated ~12-25%, driven primarily by these: 163 DA_-only `solo_inactive`
(97% of ALL solo_inactive — no phone, no website, no NPI → almost certainly
closed/phantom) and 32 rows whose normalized_address is the literal string
'nan' (Data Axle address parsing failed; not a real location row at all).
Four of the nan rows plus two junk-address rows sat INSIDE the corporate
floor (duplicates of NPI-evidenced corporate rows, an Ohio billing-HQ
address, and a brandless `dso_national` with no DSO).

What this script does (idempotent — only touches rows still in the bad state):
  1. Reclassifies the purge set to the new `da_unverified` class (kept, never
     deleted): watched locations whose NPIs are ALL DA_-prefixed AND
     (solo_inactive OR normalized_address='nan' OR explicit-verdict purge).
     merge_and_score now excludes `da_unverified` from every denominator.
  2. Flips the underlying DA_ `practices` rows the same way (updated_at bump —
     raw sqlite3 bypasses the ORM onupdate).
  3. Fixes junk affiliated_dso labels: Data Axle's franchise field held the
     SPECIALTY ("General Dentistry", "Orthodontics", ...). Corporate rows
     whose reasoning proves a real parent (Western Dental / Sonrava) get the
     real brand; everything else junk-labeled gets NULL. (Root cause fixed in
     data_axle_importer.py: JUNK_FRANCHISE_VALUES blocklist + the
     parent_iusa all-zeros placeholder skip.)
  4. Writes the DA_-only solo_high_volume locations (real-looking Data Axle
     businesses, but no NPI at the address) to a REVIEW QUEUE — kept in the
     denominator pending paid verification, NOT purged.
  5. Recomputes the affected zip_scores columns for ALL watched ZIPs from
     practice_locations (same bucketing as merge_and_score), fraction scale.
  6. Writes a full audit JSON (purged ids + evidence, corporate keepers,
     label fixes, before/after floor + denominators).

DA_-only corporate verdicts (location-level, from the 2026-06-12 review):
  PURGE (6): 4 'nan'-address rows — Aspen 60074 (duplicate of ADMI/Maya Dental
  at 968 E Dundee), Aspen 60077 (duplicate of Mena Dental at 5225 Touhy),
  Affordable Dentures 60404 (duplicate of the Brook Forest rows), Smile First
  60659 (no brand, dso=None, nan address) — plus the 2 EXPLICIT_PURGE below.
  KEEP (4): Midwest Dental Shorewood, ClearChoice Downers Grove, Aspen Oswego,
  DentalWorks Plainfield — real brand evidence, no duplicate row.
"""
import json
import sqlite3
import sys

DB = "data/dental_pe_tracker.db"
AUDIT = "data/dso_research/da_junk_cleanup_20260612.json"
REVIEW_QUEUE = "data/dso_research/da_only_high_volume_review_20260612.json"
RUN_DATE = "2026-06-12"

# Corporate rows purged by explicit verdict (address present but junk).
EXPLICIT_PURGE = {
    "6b3a3d97e72ccc9b": (
        "Dental Works (60173): address '15166 neo pkwy' is DentalWorks' "
        "Garfield Heights OH billing HQ, not an IL location; Data-Axle-only, "
        "no NPI. Five NPI-evidenced corporate locations already exist in 60173."
    ),
    "d8bc7fb6a7d58c67": (
        "Dental Dreams (60411): duplicate of NPI-evidenced corporate location "
        "DENTAL EXPERTS, LLC at 567 w 14th st (Dental Dreams' verified friendly "
        "PC; this row is the same building, '567 w 14th pl'). Keeping the "
        "NPI-evidenced row only — the floor is strictly location-deduped."
    ),
}

# DA_-only corporate locations REVIEWED and kept (documented, asserted intact).
KEEP_CORPORATE = {
    "ae77af3bec252f8e": "Midwest Dental, Shorewood 60404 (220 channahon st) — real brand office, no duplicate",
    "b389a8c579980410": "ClearChoice Dental Implant Center, Downers Grove 60515 (2651 warrenville rd) — real brand office",
    "c08edf0c9ab2cced": "Aspen Dental, Oswego 60543 (2340 us hwy 34) — matches Aspen's own locator (dso_locations overlay)",
    "01f2175555fad385": "DentalWorks Plainfield 60544 (12720 illinois route 59) — brand-in-name evidence, no duplicate",
}

# Data Axle specialty strings that ended up in affiliated_dso (never DSOs).
JUNK_DSO_VALUES = (
    "General Dentistry", "Dentistry", "Dentists", "Dentist",
    "Orthodontics", "Oral Surgery", "Periodontics", "Endodontics",
    "Prosthodontics", "Pediatric Dentistry", "Pedodontics",
    "Cosmetic Dentistry", "Implant Dentistry", "Family Dentistry",
    "Dental Labs", "Dental Laboratories",
)

CORPORATE = ("dso_regional", "dso_national")
BUYABLE = ("solo_established", "solo_inactive", "solo_high_volume")


def attached_npis(row):
    out = []
    for col in ("primary_npi", "org_npi"):
        if row[col]:
            out.append(str(row[col]))
    if row["provider_npis"]:
        try:
            out += [str(n) for n in json.loads(row["provider_npis"]) if n]
        except Exception:
            pass
    return out


def main(apply=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cur = c.cursor()

    gp0, corp0 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    npi_corp0 = c.execute("""SELECT COUNT(*) FROM practices p
        JOIN watched_zips w ON p.zip=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')""").fetchone()[0]
    print(f"BEFORE  floor {corp0}/{gp0} = {100*corp0/gp0:.2f}%   corp NPIs = {npi_corp0}")

    # ---- build the purge set ----
    rows = c.execute("""
        SELECT pl.* FROM practice_locations pl
        JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code""").fetchall()
    by_id = {r["location_id"]: r for r in rows}

    purge = {}   # location_id -> (row, reason)
    review_queue = []
    for r in rows:
        ns = attached_npis(r)
        if not ns or not all(n.startswith("DA_") for n in ns):
            continue   # NPI-evidenced — never purged here
        lid, ec = r["location_id"], r["entity_classification"]
        nan_addr = str(r["normalized_address"] or "").lower() == "nan"
        if lid in EXPLICIT_PURGE:
            purge[lid] = (r, EXPLICIT_PURGE[lid])
        elif nan_addr:
            purge[lid] = (r, "normalized_address is the literal string 'nan' "
                             "(Data Axle address parse failure) — not a "
                             "verifiable location row")
        elif ec == "solo_inactive":
            purge[lid] = (r, "Data-Axle-only solo_inactive: no federal NPI at "
                             "address, no phone, no website — almost certainly "
                             "closed/phantom (census-agent verdict)")
        elif ec == "solo_high_volume":
            review_queue.append({
                "location_id": lid, "practice_name": r["practice_name"],
                "normalized_address": r["normalized_address"], "zip": r["zip"],
                "phone": r["phone"], "website": r["website"],
                "employee_count": r["employee_count"],
                "estimated_revenue": r["estimated_revenue"],
                "note": "DA_-only solo_high_volume — real-looking Data Axle "
                        "business but no NPI at address; verify before trusting",
            })

    # sanity: keepers exist, are DA_-only corporate, and are NOT in the purge set
    for lid, why in KEEP_CORPORATE.items():
        r = by_id.get(lid)
        assert r is not None, f"keeper {lid} missing"
        assert r["entity_classification"] in CORPORATE, f"keeper {lid} not corporate: {r['entity_classification']}"
        assert lid not in purge, f"keeper {lid} landed in purge set"
    for lid in EXPLICIT_PURGE:
        assert lid in purge or by_id.get(lid, {"entity_classification": "da_unverified"})["entity_classification"] == "da_unverified", \
            f"explicit purge {lid} not found in purge set (and not already applied)"

    already = sum(1 for r in rows if r["entity_classification"] == "da_unverified")
    print(f"PURGE   {len(purge)} watched locations -> da_unverified "
          f"({already} already da_unverified)")
    corp_purged = {lid: p for lid, p in purge.items()
                   if p[0]["entity_classification"] in CORPORATE}
    print(f"        of which corporate (floor impact): {len(corp_purged)}")
    print(f"REVIEW  {len(review_queue)} DA_-only solo_high_volume queued (kept in denominator)")

    if not apply:
        for lid, (r, why) in list(purge.items())[:20]:
            print(f"  [{(r['entity_classification'] or ''):16}] {str(r['practice_name'])[:35]:35} "
                  f"{r['zip'][:5]}  {why[:60]}")
        print("  ... (dry run)")
        c.close()
        return

    # ---- 1+2. apply purge: locations + their DA_ practices rows ----
    audit_purged = []
    flipped_npi = 0
    for lid, (r, why) in purge.items():
        old_ec = r["entity_classification"]
        cur.execute("""
            UPDATE practice_locations
               SET entity_classification='da_unverified', ownership_status='unknown',
                   affiliated_dso=NULL, affiliated_pe_sponsor=NULL,
                   classification_reasoning=?, classification_confidence=80,
                   updated_at=datetime('now')
             WHERE location_id=?""",
                    (f"DA junk cleanup {RUN_DATE}: {why}; was {old_ec}.", lid))
        for npi in attached_npis(r):
            res = cur.execute("""
                UPDATE practices
                   SET entity_classification='da_unverified', ownership_status='unknown',
                       updated_at=datetime('now')
                 WHERE npi=? AND entity_classification IS NOT 'da_unverified'""", (npi,))
            flipped_npi += res.rowcount
        audit_purged.append({
            "location_id": lid, "practice_name": r["practice_name"],
            "zip": r["zip"], "normalized_address": r["normalized_address"],
            "was": old_ec, "evidence": why, "npis": attached_npis(r),
        })

    # ---- 3. junk affiliated_dso labels ----
    ph = ",".join("?" * len(JUNK_DSO_VALUES))
    relabeled = nulled = 0
    for table in ("practice_locations", "practices"):
        # corporate rows with a PROVEN parent in the reasoning get the real brand
        res = cur.execute(f"""
            UPDATE {table}
               SET affiliated_dso='Western Dental (Sonrava Health)',
                   updated_at=datetime('now')
             WHERE affiliated_dso IN ({ph})
               AND entity_classification IN ('dso_regional','dso_national')
               AND classification_reasoning LIKE '%Western Dental%'""",
                          JUNK_DSO_VALUES)
        relabeled += res.rowcount
        res = cur.execute(f"""
            UPDATE {table}
               SET affiliated_dso=NULL, updated_at=datetime('now')
             WHERE affiliated_dso IN ({ph})""", JUNK_DSO_VALUES)
        nulled += res.rowcount
    print(f"LABELS  {relabeled} junk corporate labels -> real brand, {nulled} junk labels -> NULL")

    # ---- 5. recompute affected zip_scores columns (mirrors merge_and_score) ----
    for w in c.execute("SELECT zip_code, population FROM watched_zips").fetchall():
        z, pop = w["zip_code"], w["population"]
        locs = c.execute("""SELECT entity_classification ec, is_specialist_only
            FROM practice_locations
            WHERE substr(zip,1,5)=? AND (is_likely_residential=0
                  OR is_likely_residential IS NULL)""", (z,)).fetchall()
        gp = [l for l in locs
              if l["ec"] not in ("non_clinical", "da_unverified")
              and not (l["ec"] == "specialist" or l["is_specialist_only"])]
        spec = [l for l in locs
                if l["ec"] not in ("non_clinical", "da_unverified")
                and (l["ec"] == "specialist" or l["is_specialist_only"])]
        n_gp, n_spec = len(gp), len(spec)
        n_corp = sum(1 for l in gp if l["ec"] in CORPORATE)
        n_buy = sum(1 for l in gp if l["ec"] in BUYABLE)
        n_fam = sum(1 for l in gp if l["ec"] == "family_practice")
        pop10k = pop / 10000.0 if pop and pop > 0 else None
        cur.execute("""UPDATE zip_scores SET
                total_gp_locations=?, total_specialist_locations=?,
                corporate_location_count=?,
                corporate_share_pct=?, buyable_practice_count=?,
                buyable_practice_ratio=?, family_practice_count=?,
                dld_gp_per_10k=?, dld_total_per_10k=?, people_per_gp_door=?
            WHERE zip_code=?""", (
            n_gp, n_spec, n_corp,
            round(n_corp / n_gp, 4) if n_gp else 0.0,
            n_buy,
            round(n_buy / n_gp, 4) if n_gp else 0.0,
            n_fam,
            round(n_gp / pop10k, 2) if pop10k and n_gp else 0.0,
            round((n_gp + n_spec) / pop10k, 2) if pop10k else 0.0,
            (pop // n_gp) if n_gp and pop else None,
            z))
    c.commit()

    gp1, corp1 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    npi_corp1 = c.execute("""SELECT COUNT(*) FROM practices p
        JOIN watched_zips w ON p.zip=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')""").fetchone()[0]
    il = c.execute("""SELECT SUM(corporate_location_count), SUM(total_gp_locations)
        FROM zip_scores WHERE state='IL'""").fetchone()
    ma = c.execute("""SELECT SUM(corporate_location_count), SUM(total_gp_locations)
        FROM zip_scores WHERE state='MA'""").fetchone()
    print(f"AFTER   floor {corp1}/{gp1} = {100*corp1/gp1:.2f}%   "
          f"(IL {il[0]}/{il[1]} = {100*il[0]/il[1]:.2f}%, MA {ma[0]}/{ma[1]} = {100*ma[0]/ma[1]:.2f}%)")
    print(f"        corp NPIs {npi_corp0} -> {npi_corp1}   "
          f"DA_ practice rows flipped: {flipped_npi}")

    # ---- 4+6. review queue + audit ----
    with open(REVIEW_QUEUE, "w") as f:
        json.dump({"run_date": RUN_DATE, "count": len(review_queue),
                   "note": "DA_-only solo_high_volume — kept in GP denominator "
                           "pending verification; purge candidates if web "
                           "verification finds them closed.",
                   "locations": review_queue}, f, indent=2)
    with open(AUDIT, "w") as f:
        json.dump({
            "run_date": RUN_DATE,
            "summary": "Purged Data-Axle-only unverifiable records from the GP "
                       "denominator; fixed junk affiliated_dso labels; root "
                       "causes fixed in data_axle_importer.py (JUNK_FRANCHISE_"
                       "VALUES + parent_iusa placeholder skip) and "
                       "merge_and_score.py (da_unverified excluded).",
            "floor_before": {"corp": corp0, "gp": gp0},
            "floor_after": {"corp": corp1, "gp": gp1},
            "npi_corporate_before": npi_corp0, "npi_corporate_after": npi_corp1,
            "purged_count": len(audit_purged),
            "purged_corporate": [p for p in audit_purged if p["was"] in CORPORATE],
            "kept_corporate_da_only": KEEP_CORPORATE,
            "junk_labels_relabeled": relabeled, "junk_labels_nulled": nulled,
            "review_queue_count": len(review_queue),
            "purged": audit_purged,
        }, f, indent=2)
    print(f"\nAudit: {AUDIT}\nReview queue: {REVIEW_QUEUE}")
    print("NEXT: update FLOOR/FLOOR_NPI guards, consolidation-honesty constants, "
          "then sync floor tables + practices to Supabase.")
    c.close()


if __name__ == "__main__":
    main(apply="--dry-run" not in sys.argv)
