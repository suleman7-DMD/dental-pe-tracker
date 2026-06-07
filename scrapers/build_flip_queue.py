"""Phase C-prep — union the Phase B detectors into ONE ranked flip-candidate
triage queue.

The Phase B detectors each surface corporate evidence from an independent angle:

  B1 (detect_name_chains.py)      same distinctive brand across 3+ watched ZIPs
  B2 (detect_corporate_clusters)  shared parent-TIN / officer / mailing / EIN
  B7 (detect_psc_registry.py)     IDFPR friendly-PC registry + DBA brand reveals
  scoreboard (il_dso_scoreboard)  web-verified DSO present-in-IL self-report

This script joins all four against the live SQLite `practices` table, keeps only
watched-IL NPIs that are CURRENTLY classified independent (the actionable flips),
attaches every corroborating signal, and ranks them into confidence tiers.

  high   — a KNOWN DSO brand is attached (scoreboard / B7-DBA reveal) AND/OR
           ≥2 independent structural signals corroborate. Web-verify is a
           formality; these are the floor-raising core.
  medium — brand-confirmed by a single source, OR ≥2 structural signals with no
           known brand (real multi-location entity, brand still unidentified).
  low    — a SINGLE weak signal (one name-chain hit or one PSC multi-city match)
           with no brand confirmation. Could easily be a coincidental common
           name or an independent group that merely incorporated. These need the
           HEAVIEST scrutiny and many will correctly stay independent.

CRITICAL — this is a TRIAGE queue, NOT a promotion list. It writes NO database
changes. Phase C web-verifies each candidate (top tiers first) before
`reclassify_verified_corporate_il.py` promotes only the confirmed ones. The
"never promote on a single weak signal" rule is encoded directly in the tiering:
`low` = single weak signal, explicitly flagged for verification, never auto-flipped.

READ-ONLY: opens SQLite in ro mode + reads the four detector JSONs.
Output: data/dso_research/flip_queue_b_union.json

Usage: python3 scrapers/build_flip_queue.py
"""
import glob
import json
import os
import sqlite3
from collections import defaultdict

from detect_name_chains import normalize_brand
from dso_brands import NATIONAL_DSO_BRANDS, match_dso_brand
from reclassify_locations import _norm_addr  # canonical location-address normalizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "data", "dso_research")
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(RES, "flip_queue_b_union.json")

B1 = os.path.join(RES, "chain_candidates_b1.json")
B2 = os.path.join(RES, "cluster_candidates_b2.json")
B7 = os.path.join(RES, "psc_candidates_b7.json")

CORPORATE_CLASSES = ("dso_regional", "dso_national")
# GP-independent classes — these are the locations that sit INSIDE the published
# GP floor denominator (zip_scores.total_gp_locations) as "independent". Flipping
# one of these to corporate raises the GP corporate share without changing the
# denominator. Specialist / non_clinical / org_only locations are NOT in the GP
# denominator, so a specialist flip (e.g. an ortho DSO) belongs to a separate
# specialist track and must NOT inflate the headline GP floor.
GP_INDEPENDENT_CLASSES = ("solo_established", "solo_new", "solo_inactive",
                          "solo_high_volume", "family_practice", "small_group",
                          "large_group")


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _latest_scoreboard():
    cands = sorted(glob.glob(os.path.join(RES, "il_dso_scoreboard_*.json")))
    return _load(cands[-1]) if cands else {}


def build_brand_confirmation(scoreboard, b7):
    """brand_key -> {dso, pe_sponsor, sources:set, confidence} for every brand we
    can tie to a KNOWN DSO with external confirmation."""
    conf = {}

    def add(key, dso, sponsor, source, confidence):
        if not key:
            return
        e = conf.setdefault(key, {"dso": dso, "pe_sponsor": sponsor,
                                  "sources": set(), "confidence": confidence})
        e["sources"].add(source)
        # keep the strongest confidence seen
        order = {"low": 0, "medium": 1, "high": 2}
        if order.get(confidence, 0) > order.get(e["confidence"], 0):
            e["confidence"] = confidence
        if dso and not e.get("dso"):
            e["dso"] = dso

    # 1) scoreboard self-report (web-verified DSO present in IL)
    for entry in scoreboard.get("confirmed_present_il", []):
        dso = entry.get("dso")
        sponsor = entry.get("pe_sponsor")
        c = entry.get("confidence", "medium")
        for bk in entry.get("b1_brand_keys", []):
            add(bk.upper(), dso, sponsor, "scoreboard", c)
        for nm in (entry.get("friendly_pc_names", []) +
                   entry.get("local_brand_names", [])):
            k, d = normalize_brand(nm)
            if k and d:
                add(k, dso, sponsor, "scoreboard", c)

    # 2) B7 DBA brand reveals (PC's assumed name IS a known DSO brand)
    for rev in b7.get("dba_brand_reveals", []):
        dso = rev.get("matched_dso")
        sponsor = rev.get("pe_sponsor")
        # strong when the DBA carried the brand; both names map regardless
        for src_name in (rev.get("business_name"), rev.get("businessdba")):
            k, d = normalize_brand(src_name)
            if k and d:
                add(k, dso, sponsor, "b7_dba_reveal", "high")

    # 3) B7 shared-DBA clusters with an identified DSO
    for cl in b7.get("shared_dba_clusters", []):
        dso = cl.get("matched_dso")
        if not dso:
            continue
        sponsor = (match_dso_brand(None, cl.get("dba_display")) or (None, None))[1]
        add(cl.get("dba_key"), dso, sponsor, "b7_shared_dba", "high")
        for nm in cl.get("distinct_legal_names", []):
            k, d = normalize_brand(nm)
            if k and d:
                add(k, dso, sponsor, "b7_shared_dba", "high")

    return conf


def main():
    b1 = _load(B1)
    b2 = _load(B2)
    b7 = _load(B7)
    scoreboard = _latest_scoreboard()

    brand_conf = build_brand_confirmation(scoreboard, b7)

    # ---- gather evidence keyed by NPI ----
    npi_ev = defaultdict(lambda: {"sources": set(), "brand_keys": set(),
                                  "b1": [], "b2": [], "b7": []})

    for cand in b1.get("candidates", []):
        bk = cand.get("brand_key")
        for npi in cand.get("npis", []):
            e = npi_ev[npi]
            e["sources"].add("b1_name_chain")
            if bk:
                e["brand_keys"].add(bk)
            e["b1"].append({
                "brand_key": bk, "display_name": cand.get("display_name"),
                "zip_count": cand.get("zip_count"), "npi_count": cand.get("npi_count"),
                "shared_ein_multi_zip": cand.get("shared_ein_multi_zip"),
                "shared_parent": cand.get("shared_parent"),
                "corroboration": cand.get("corroboration"),
            })

    for cl in b2.get("clusters", []):
        for m in cl.get("members", []):
            npi = m.get("npi")
            if not npi:
                continue
            e = npi_ev[npi]
            e["sources"].add("b2_structural")
            e["b2"].append({
                "cluster_kind": cl.get("cluster_kind"),
                "cluster_key": cl.get("cluster_key"),
                "npi_count": cl.get("npi_count"), "zip_count": cl.get("zip_count"),
                "strength": (cl.get("corroboration") or {}).get("strength"),
            })

    for nm in b7.get("watched_name_matches", []):
        bk = nm.get("brand_key")
        for w in nm.get("watched_matches", []):
            npi = w.get("npi")
            if not npi:
                continue
            e = npi_ev[npi]
            e["sources"].add("b7_psc")
            if bk:
                e["brand_keys"].add(bk)
            e["b7"].append({
                "brand_key": bk, "psc_name": nm.get("psc_name"),
                "psc_multi_city": nm.get("psc_multi_city"),
                "psc_dbas": nm.get("psc_dbas"),
            })

    if not npi_ev:
        print("No candidate NPIs found in B1/B2/B7 outputs — nothing to queue.")
        return

    # ---- join to live SQLite (read-only) ----
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(npi_ev))
    prows = {r["npi"]: dict(r) for r in conn.execute(f"""
        SELECT npi, practice_name, doing_business_as, address, city, zip,
               entity_classification, ein, parent_company
        FROM practices WHERE npi IN ({placeholders})
    """, list(npi_ev)).fetchall()}

    # npi -> location_id + location current class (for honest floor projection).
    # Also build a (zip, normalized-address) -> location_id index as an EXACT
    # fallback: sibling org NPIs (NPI-2) at a multi-NPI address often aren't the
    # location's chosen primary/org NPI, so they'd otherwise show NO-LOC. Both
    # sides run through _norm_addr, so the match is exact, never fuzzy.
    npi_loc = {}
    loc_class = {}
    loc_by_addr = {}
    for r in conn.execute("""
        SELECT pl.location_id, pl.entity_classification, pl.normalized_address,
               pl.zip, pl.primary_npi, pl.org_npi, pl.provider_npis
        FROM practice_locations pl JOIN watched_zips w ON pl.zip = w.zip_code
        WHERE w.state='IL'
    """).fetchall():
        lid = r["location_id"]
        loc_class[lid] = r["entity_classification"]
        if r["zip"] and r["normalized_address"]:
            loc_by_addr.setdefault((r["zip"], _norm_addr(r["normalized_address"])), lid)
        members = set()
        for v in (r["primary_npi"], r["org_npi"]):
            if v:
                members.add(str(v))
        if r["provider_npis"]:
            try:
                members.update(str(x) for x in json.loads(r["provider_npis"]))
            except (ValueError, TypeError):
                pass
        for npi in members:
            npi_loc.setdefault(npi, lid)

    # Canonical GP floor denominator + current corporate count (the exact basis
    # of the published 5.27%): IL sum of zip_scores.total_gp_locations.
    gp_row = conn.execute("""
        SELECT COALESCE(SUM(total_gp_locations), 0),
               COALESCE(SUM(corporate_location_count), 0)
        FROM zip_scores z JOIN watched_zips w ON z.zip_code = w.zip_code
        WHERE w.state='IL'
    """).fetchone()
    gp_denom, gp_cur_corp = int(gp_row[0]), int(gp_row[1])
    conn.close()

    # ---- assemble candidate records (still-independent only) ----
    candidates = []
    already_corp = 0
    not_in_watched = 0
    for npi, ev in npi_ev.items():
        prow = prows.get(npi)
        if not prow:
            not_in_watched += 1  # NPI not in practices (or non-watched)
            continue
        cur = prow.get("entity_classification") or ""
        if cur in CORPORATE_CLASSES:
            already_corp += 1
            continue  # confirms detector but already counted in the floor

        # collect candidate brand keys: detector keys + the NPI's own name/dba
        bkeys = set(ev["brand_keys"])
        for src in (prow.get("practice_name"), prow.get("doing_business_as")):
            k, d = normalize_brand(src)
            if k and d:
                bkeys.add(k)

        # brand confirmation: strongest hit across this NPI's brand keys
        confirmed = None
        for bk in bkeys:
            c = brand_conf.get(bk)
            if c and (confirmed is None or
                      {"low": 0, "medium": 1, "high": 2}.get(c["confidence"], 0) >
                      {"low": 0, "medium": 1, "high": 2}.get(confirmed["confidence"], 0)):
                confirmed = c

        signal_count = len(ev["sources"])
        brand_ok = confirmed is not None

        if brand_ok and (signal_count >= 2 or
                         "b7_dba_reveal" in confirmed["sources"] or
                         "scoreboard" in confirmed["sources"]):
            tier = "high"
        elif brand_ok or signal_count >= 2:
            tier = "medium"
        else:
            tier = "low"

        proposed_dso = confirmed["dso"] if confirmed else None
        if proposed_dso and proposed_dso.upper() in NATIONAL_DSO_BRANDS:
            proposed_class = "dso_national"
        elif brand_ok:
            proposed_class = "dso_national"
        else:
            proposed_class = "dso_regional"  # structural-only, lower confidence

        lid = npi_loc.get(npi)
        if not lid and prow.get("address"):
            lid = loc_by_addr.get((prow.get("zip"), _norm_addr(prow["address"])))
        candidates.append({
            "npi": npi,
            "name": prow.get("practice_name"),
            "dba": prow.get("doing_business_as"),
            "address": prow.get("address"),
            "city": prow.get("city"),
            "zip": prow.get("zip"),
            "current_class": cur or None,
            "location_id": lid,
            "location_current_class": loc_class.get(lid),
            "proposed_class": proposed_class,
            "proposed_dso": proposed_dso,
            "pe_sponsor": confirmed["pe_sponsor"] if confirmed else None,
            "tier": tier,
            "signal_count": signal_count,
            "signals": sorted(ev["sources"]),
            "brand_confirmed": brand_ok,
            "brand_confirmation_sources": sorted(confirmed["sources"]) if confirmed else [],
            "brand_keys": sorted(bkeys),
            "evidence": {"b1": ev["b1"], "b2": ev["b2"], "b7": ev["b7"]},
            "verification_status": "pending",  # Phase C fills this
        })

    tier_rank = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda c: (tier_rank[c["tier"]], -c["signal_count"],
                                   not c["brand_confirmed"], c["name"] or ""))

    # ---- honest location-level floor projection (GP denominator) ----
    # Use the SAME basis as the published 5.27%: IL GP locations only. Only count
    # a candidate's location delta when its location is currently an INDEPENDENT
    # GP location (so the flip moves an independent-GP into corporate-GP, numerator
    # +1, denominator unchanged). Specialist / non-clinical flips are tracked
    # separately and never touch the GP floor.
    def gp_locs_for(tiers):
        return {c["location_id"] for c in candidates
                if c["tier"] in tiers and c["location_id"]
                and c["location_current_class"] in GP_INDEPENDENT_CLASSES}

    def spec_locs_for(tiers):
        return {c["location_id"] for c in candidates
                if c["tier"] in tiers and c["location_id"]
                and c["location_current_class"] == "specialist"}

    high_locs = gp_locs_for({"high"})
    high_med_locs = gp_locs_for({"high", "medium"})
    all_locs = gp_locs_for({"high", "medium", "low"})
    spec_high_med = spec_locs_for({"high", "medium"})

    cur_corp_locs = gp_cur_corp  # 243 IL corporate GP locations
    total_il_locs = gp_denom     # 4,608 IL GP locations (canonical denominator)

    def pct(n):
        return round(100.0 * n / total_il_locs, 2) if total_il_locs else None

    # brand rollup
    by_brand = defaultdict(lambda: {"candidates": 0, "high": 0, "dso": None,
                                    "pe_sponsor": None})
    for c in candidates:
        key = c["proposed_dso"] or "(unidentified brand)"
        b = by_brand[key]
        b["candidates"] += 1
        if c["tier"] == "high":
            b["high"] += 1
        b["dso"] = c["proposed_dso"]
        b["pe_sponsor"] = b["pe_sponsor"] or c["pe_sponsor"]
    brand_rollup = sorted(
        [{"dso": k, **v} for k, v in by_brand.items()],
        key=lambda x: x["candidates"], reverse=True)

    tier_counts = {t: sum(1 for c in candidates if c["tier"] == t)
                   for t in ("high", "medium", "low")}

    result = {
        "generated_by": "build_flip_queue.py (Phase C-prep)",
        "note": ("TRIAGE queue only — NO promotions made. Phase C web-verifies "
                 "top tiers first, then reclassify_verified_corporate_il.py "
                 "promotes only confirmed candidates. 'low' tier = single weak "
                 "signal, never auto-flip."),
        "inputs": {"b1_candidates": len(b1.get("candidates", [])),
                   "b2_clusters": len(b2.get("clusters", [])),
                   "b7_name_matches": len(b7.get("watched_name_matches", [])),
                   "b7_dba_reveals": len(b7.get("dba_brand_reveals", [])),
                   "scoreboard_dsos": len(scoreboard.get("confirmed_present_il", [])),
                   "brand_confirmation_keys": len(brand_conf)},
        "candidate_count": len(candidates),
        "tier_counts": tier_counts,
        "already_corporate_corroborated": already_corp,
        "npis_not_in_practices": not_in_watched,
        "floor_projection_il_gp_locations": {
            "basis": "IL GP locations only (zip_scores.total_gp_locations) — "
                     "same denominator as the published 5.27% floor",
            "denominator_il_gp_locations": total_il_locs,
            "current_corporate_gp_locations": cur_corp_locs,
            "current_floor_pct": pct(cur_corp_locs),
            "if_high_confirmed": {
                "added_gp_locations": len(high_locs),
                "new_corporate_gp_locations": cur_corp_locs + len(high_locs),
                "projected_floor_pct": pct(cur_corp_locs + len(high_locs))},
            "if_high_plus_medium_confirmed": {
                "added_gp_locations": len(high_med_locs),
                "new_corporate_gp_locations": cur_corp_locs + len(high_med_locs),
                "projected_floor_pct": pct(cur_corp_locs + len(high_med_locs))},
            "if_all_tiers_confirmed_upper_bound": {
                "added_gp_locations": len(all_locs),
                "new_corporate_gp_locations": cur_corp_locs + len(all_locs),
                "projected_floor_pct": pct(cur_corp_locs + len(all_locs))},
            "specialist_track_separate": {
                "note": "Specialist-only DSO flips (ortho/OMS chains like "
                        "MyOrthos, Smile Doctors) — NOT in the GP denominator, "
                        "reported separately so they never inflate the GP floor.",
                "high_plus_medium_specialist_locations": len(spec_high_med)},
            "caveat": ("Projections are CONTINGENT on Phase C web-verification. "
                       "Location counts dedup NPIs that share an address. "
                       "ADA HPI per-dentist anchor (IL 14.6%) remains the honest "
                       "upper bound; this floor is GP locations, a different unit.")},
        "brand_rollup": brand_rollup,
        "candidates": candidates,
    }

    os.makedirs(RES, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Flip queue built -> {OUT}")
    print(f"  candidates (still-independent watched-IL NPIs): {len(candidates)}")
    print(f"  tiers: high={tier_counts['high']}  medium={tier_counts['medium']}  "
          f"low={tier_counts['low']}")
    print(f"  already-corporate corroborated (not queued): {already_corp}")
    print(f"\n  --- IL GP-floor projection (CONTINGENT on Phase C verify) ---")
    fp = result["floor_projection_il_gp_locations"]
    print(f"  denominator: {fp['denominator_il_gp_locations']} IL GP locations")
    print(f"  current:            {fp['current_corporate_gp_locations']:>4} = "
          f"{fp['current_floor_pct']}%")
    print(f"  + high confirmed:   {fp['if_high_confirmed']['new_corporate_gp_locations']:>4} "
          f"(+{fp['if_high_confirmed']['added_gp_locations']}) = "
          f"{fp['if_high_confirmed']['projected_floor_pct']}%")
    print(f"  + high+medium:      {fp['if_high_plus_medium_confirmed']['new_corporate_gp_locations']:>4} "
          f"(+{fp['if_high_plus_medium_confirmed']['added_gp_locations']}) = "
          f"{fp['if_high_plus_medium_confirmed']['projected_floor_pct']}%")
    print(f"  all-tiers (ceiling):{fp['if_all_tiers_confirmed_upper_bound']['new_corporate_gp_locations']:>4} "
          f"(+{fp['if_all_tiers_confirmed_upper_bound']['added_gp_locations']}) = "
          f"{fp['if_all_tiers_confirmed_upper_bound']['projected_floor_pct']}%")
    print(f"  (separate specialist-track flips, high+med: "
          f"{fp['specialist_track_separate']['high_plus_medium_specialist_locations']})")
    print(f"\n  --- brand rollup (top 14 by candidate count) ---")
    for b in brand_rollup[:14]:
        print(f"  {(b['dso'] or '(unidentified)')[:32]:<32} "
              f"cands={b['candidates']:>3}  high-tier={b['high']:>3}")
    print(f"\n  --- top 20 high-tier candidates ---")
    for c in [x for x in candidates if x["tier"] == "high"][:20]:
        print(f"  {(c['name'] or '')[:34]:<34} {c['zip']} "
              f"-> {c['proposed_dso'] or c['proposed_class']:<22} "
              f"sig={c['signal_count']} {','.join(c['signals'])}")
    return result


if __name__ == "__main__":
    main()
