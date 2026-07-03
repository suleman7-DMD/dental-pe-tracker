"""
Fleet B — Lane 1B Wave-2 worker prep.  READ-ONLY on the DB.
1. Union the 350 unique lids from _feed_w2_lane1B_*.json (carry pre-mined evidence).
2. Re-gate: drop excluded GP class / DA / already-tiered / non-IL / in-exclusion-set /
   already in wave-1 queue, Lane 3 queue, the 43-row backfill, or Main's AO/reach5 networks.
3. Enrich survivors with full DB evidence: practice_intel prose (all NPIs at the location),
   practices ownership fields (parent_company, affiliated_dso, affiliated_pe_sponsor, ein,
   franchise_name, da_legal_name, authorized_official, parent_org_lbn), and AO cross-location
   reach within watched IL.
4. Write balanced worker shards (evidence-rich) for the agent fleet.
NO DB writes, NO LEDGER/PROGRESS writes.
"""
import json, glob, os, re, sqlite3, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
SH = os.path.join(DR, "_shards_fleet_b")
WORK = os.path.join(SH, "_lane1B_worker")
os.makedirs(WORK, exist_ok=True)
EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# ---- 1. union the feed rows -------------------------------------------------
def load(f):
    d = json.load(open(f)); return d if isinstance(d, list) else d.get("rows", [])
feeds = sorted(glob.glob(os.path.join(SH, "_feed_w2_lane1B_*.json")))
union = {}
for f in feeds:
    for r in load(f):
        lid = r.get("location_id")
        if not lid: continue
        # keep the richer record (prefer one carrying _signal_kinds)
        if lid not in union or (r.get("_signal_kinds") and not union[lid].get("_signal_kinds")):
            union[lid] = r
print(f"union feed rows: {len(union)} unique location_ids")

# ---- 2. build exclusion universe -------------------------------------------
EX = set()
def add_lids_from(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "location_id" and isinstance(v, str): EX.add(v)
            else: add_lids_from(v)
    elif isinstance(obj, list):
        for x in obj: add_lids_from(x)

excl_files = [
    "_exclusion_set_fleet_b_20260621.json",
    "ownership_evidence_queue_fleet_b_20260621.json",        # wave 1
    "ownership_evidence_queue_fleet_b_lane3_20260621.json",  # lane 3
    "ownership_evidence_queue_fleet_b_backfill_20260621.json",  # 43-row backfill (just done)
    "ao_network_evidence_reach5_20260621.json",              # Main reach5
]
for fn in excl_files:
    p = os.path.join(DR, fn)
    if os.path.exists(p):
        try: add_lids_from(json.load(open(p)))
        except Exception as e: print(f"  warn: {fn}: {e}")
# explicit excluded_location_ids dict in the exclusion set
es = os.path.join(DR, "_exclusion_set_fleet_b_20260621.json")
if os.path.exists(es):
    d = json.load(open(es))
    for lid in d.get("excluded_location_ids", {}): EX.add(lid)
print(f"exclusion universe: {len(EX)} location_ids")

# ---- gate helper (mirror validate_rows location checks) --------------------
def gate(lid):
    loc = conn.execute("""
        SELECT pl.state, pl.zip, pl.primary_npi, pl.org_npi,
               pl.entity_classification AS ec, pl.ownership_tier, wz.state AS ws
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()
    if not loc: return "no_loc"
    if loc["ws"] != "IL" or (loc["state"] or "").upper() != "IL": return "not_IL"
    if loc["ec"] in EXCLUDED_GP_CLASSES: return f"excluded:{loc['ec']}"
    if loc["ownership_tier"]: return "already_tiered"
    if str(loc["primary_npi"] or "").startswith("DA_") and str(loc["org_npi"] or "").startswith("DA_"):
        return "da_only"
    return "ok"

# ---- 3. gate + enrich -------------------------------------------------------
INTEL_COLS = ("overall_assessment", "acquisition_details", "red_flags", "green_flags",
              "website", "hiring", "doctor_profile", "verification_urls", "verification_quality")
survivors, drop = [], collections.Counter()
for lid, fr in union.items():
    if lid in EX: drop["in_exclusion_set"] += 1; continue
    g = gate(lid)
    if g != "ok": drop[g] += 1; continue
    loc = conn.execute("""
        SELECT location_id, practice_name, city, state, zip, primary_npi, org_npi,
               provider_npis, entity_classification, affiliated_dso, parent_company
        FROM practice_locations WHERE location_id=?""", (lid,)).fetchone()
    # collect NPIs at the location (only real 10-digit NPIs; drop DA_/JSON artifacts)
    raw = set()
    for n in (fr.get("npis") or []):
        raw |= set(re.findall(r"\d{10}", str(n)))
    for k in ("primary_npi", "org_npi", "provider_npis"):
        if loc[k]: raw |= set(re.findall(r"\d{10}", str(loc[k])))
    npis = sorted(n for n in raw if not n.startswith("DA_"))
    # practices ownership fields
    own = []
    if npis:
        qm = ",".join("?" * len(npis))
        for p in conn.execute(f"""
            SELECT npi, practice_name, parent_company, affiliated_dso, affiliated_pe_sponsor,
                   ein, franchise_name, da_legal_name, parent_org_lbn,
                   authorized_official_first_name, authorized_official_last_name
            FROM practices WHERE npi IN ({qm})""", npis).fetchall():
            own.append({k: p[k] for k in p.keys() if p[k] not in (None, "", "nan")})
    # practice_intel prose
    intel = []
    if npis:
        qm = ",".join("?" * len(npis))
        for p in conn.execute(f"SELECT * FROM practice_intel WHERE npi IN ({qm})", npis).fetchall():
            d = dict(p)
            intel.append({"npi": d.get("npi"), **{c: d.get(c) for c in INTEL_COLS if d.get(c)}})
    # AO cross-location reach within watched IL (distinct address/zip from practices)
    ao_reach = []
    aos = {(o.get("authorized_official_first_name"), o.get("authorized_official_last_name"))
           for o in own if o.get("authorized_official_last_name")}
    for fn_, ln in aos:
        if not ln: continue
        rows = conn.execute("""
            SELECT DISTINCT p.address, p.zip, p.practice_name
            FROM practices p
            JOIN watched_zips wz ON wz.zip_code = substr(p.zip,1,5) AND wz.state='IL'
            WHERE p.authorized_official_last_name=? AND (?='' OR p.authorized_official_first_name=?)
              AND p.address IS NOT NULL AND p.address!=''
            """, (ln, fn_ or "", fn_ or "")).fetchall()
        locs = sorted({(rr["address"], rr["zip"], rr["practice_name"]) for rr in rows})
        if len(locs) >= 2:
            ao_reach.append({"ao": f"{fn_ or ''} {ln}".strip(), "reach": len(locs),
                             "addresses": [{"address": a, "zip": b, "name": c} for a, b, c in locs[:8]]})
    survivors.append({
        "location_id": lid,
        "practice_name": loc["practice_name"], "city": loc["city"], "zip": loc["zip"],
        "entity_classification": loc["entity_classification"],
        "loc_affiliated_dso": loc["affiliated_dso"], "loc_parent_company": loc["parent_company"],
        "feed_signal_kinds": fr.get("_signal_kinds"),
        "feed_multi": fr.get("multi"), "feed_acq": fr.get("acq"), "feed_acq_details": fr.get("acq_details"),
        "feed_brands": fr.get("brands"), "feed_brand_pe": fr.get("brand_pe"),
        "feed_vq": fr.get("vq"), "feed_urls": fr.get("urls"),
        "feed_explicit_snippets": fr.get("_explicit_ownership_snippets"),
        "feed_intel_urls": fr.get("_intel_urls"),
        "npis": npis,
        "db_practices_ownership": own,
        "db_practice_intel": intel,
        "db_ao_cross_location_reach": ao_reach,
    })

print(f"survivors after gate: {len(survivors)} | dropped: {dict(drop)}")

# ---- 4. balanced worker shards ---------------------------------------------
# sort so explicit-signal rows cluster; ~30 rows per shard
def has_signal(s):
    return bool(s.get("feed_signal_kinds") or s.get("feed_brands") or s.get("feed_acq")
                or s.get("db_ao_cross_location_reach")
                or any(o.get("parent_company") or o.get("affiliated_dso") or o.get("affiliated_pe_sponsor")
                       for o in s.get("db_practices_ownership", [])))
survivors.sort(key=lambda s: (not has_signal(s), s.get("zip") or ""))
PER = 30
shards = [survivors[i:i+PER] for i in range(0, len(survivors), PER)]
for i, sh in enumerate(shards, 1):
    json.dump(sh, open(os.path.join(WORK, f"_w_lane1B_{i:02d}.json"), "w"), indent=1)
manifest = {
    "total_survivors": len(survivors), "shards": len(shards), "per_shard": PER,
    "dropped": dict(drop), "union_input": len(union),
    "with_explicit_signal": sum(1 for s in survivors if has_signal(s)),
}
json.dump(manifest, open(os.path.join(WORK, "_manifest.json"), "w"), indent=1)
print(f"wrote {len(shards)} worker shards to {WORK}")
print(json.dumps(manifest, indent=1))
