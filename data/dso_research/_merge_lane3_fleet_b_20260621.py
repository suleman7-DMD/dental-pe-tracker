"""
Fleet B WAVE-2 Lane 3 (zero-corp ZIP sweep) merge / gate / partition.  READ-ONLY on the DB.
Loads the 6 Lane-3 shards (60089/60103/60148/60181/60613/60616), gates each row against the
SAME location checks consolidate_census.validate_rows() runs, partitions into
classifications / held / rejected, auto-surfaces QA flags from row prose, and writes:
  - evidence_zip_sweep_fleet_b_20260621.json          (Lane 3 evidence, all rows + gate notes)
  - ownership_evidence_queue_fleet_b_lane3_20260621.json (unified queue fed to --validate-only)
No DB / LEDGER / PROGRESS writes.  Does NOT mutate the wave-1 queue.
"""
import json, glob, os, sqlite3, collections, re

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
SH = os.path.join(ROOT, "data", "dso_research", "_shards_fleet_b")
OUT = os.path.join(ROOT, "data", "dso_research")
EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified",
                       "org_only_npi", "duplicate_location"}

def is_da(v):
    return isinstance(v, str) and v.startswith("DA_")

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# ---- 1. load 6 shards -------------------------------------------------------
rows = []
for f in sorted(glob.glob(os.path.join(SH, "_shard_lane3_*.json"))):
    z = os.path.basename(f).split("_")[-1].split(".")[0]
    for r in json.load(open(f)):
        r["_shard"] = os.path.basename(f); r["_feed_zip"] = z; rows.append(r)
print(f"loaded {len(rows)} rows from 6 Lane-3 shards")

# ---- 2. dedupe by location_id (defensive; feeds are ZIP-partitioned) --------
STRENGTH = {"classified": 3, "needs_verification": 2, "undetermined": 1}
CONF = {"high": 3, "medium": 2, "low": 1, None: 0}
by_lid = collections.defaultdict(list)
for r in rows:
    by_lid[r.get("location_id")].append(r)
deduped, conflicts = [], []
for lid, grp in by_lid.items():
    if len(grp) == 1:
        deduped.append(grp[0]); continue
    grp_sorted = sorted(grp, key=lambda r: (STRENGTH.get(r.get("status"), 0),
                        CONF.get(r.get("confidence"), 0),
                        1 if r.get("evidence_urls") else 0), reverse=True)
    winner = dict(grp_sorted[0])
    real = {r.get("assigned_tier") for r in grp
            if r.get("status") == "classified" and r.get("assigned_tier") != "undetermined"}
    if len(real) > 1:
        winner.update(status="needs_verification", disposition="needs_verification",
                      assigned_tier="undetermined", proposed_tier=sorted(real)[0],
                      confidence="low",
                      reasoning="CONFLICT(" + ",".join(sorted(real)) + "); " + (winner.get("reasoning") or ""))
        conflicts.append({"location_id": lid, "tiers": sorted(real),
                          "resolution": "downgraded_needs_verification"})
    deduped.append(winner)
print(f"deduped to {len(deduped)} unique location_ids; {len(conflicts)} multi-shard collisions")

# ---- 3. gate each row (mirror validate_rows location checks) ----------------
def gate(lid, status):
    loc = conn.execute("""
        SELECT pl.state, pl.zip, pl.primary_npi, pl.org_npi,
               pl.entity_classification AS ec, pl.ownership_tier, wz.state AS ws
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()
    if not loc: return "fail:location_not_found", None
    if loc["ws"] != "IL" or (loc["state"] or "").upper() != "IL":
        return f"fail:not_IL(state={loc['state']},watched={loc['ws']})", loc["ec"]
    if loc["ec"] in EXCLUDED_GP_CLASSES:
        return f"fail:excluded_gp_class:{loc['ec']}", loc["ec"]
    if loc["ownership_tier"]:
        return f"fail:existing_ownership_tier:{loc['ownership_tier']}", loc["ec"]
    if (is_da(loc["primary_npi"]) or is_da(loc["org_npi"])) and status == "classified":
        return "fail:DA_synthetic_classified", loc["ec"]
    return "ok", loc["ec"]

for r in deduped:
    g, ec = gate(r.get("location_id"), r.get("status"))
    r["_gate"] = g; r["_db_entity_classification"] = ec

# ---- 4. partition -----------------------------------------------------------
classifications, held, rejected = [], [], []
for r in deduped:
    if r.get("status") == "undetermined" or r.get("disposition") == "reject":
        rejected.append(r)
    elif r["_gate"] == "ok":
        classifications.append(r)
    else:
        held.append(r)

def clean(r):
    return {k: v for k, v in r.items()
            if k not in ("_shard", "_feed_zip", "_gate", "_db_entity_classification")}
classifications_clean = [clean(r) for r in classifications]

# ---- 5. auto-surface QA flags from row prose --------------------------------
SPECIALIST_RE = re.compile(r"\b(orthodont|endodont|periodont|oral surg|maxillofacial|"
                           r"pediatric dent|pedodont|prosthodont|OMS|implant solution|"
                           r"get it straight|dental specialists)\b", re.I)
CLOSED_RE = re.compile(r"\b(closed|permanently closed|inactive|no longer|defunct|shut)\b", re.I)
qa_flags = []
def txt(r):
    return " ".join(str(r.get(k) or "") for k in
                    ("reasoning", "owner_identity", "network_id",
                     json.dumps(r.get("signal")) if isinstance(r.get("signal"), dict) else "signal"))
for r in deduped:
    blob = (str(r.get("reasoning") or "") + " " + json.dumps(r.get("signal") or {}) + " " +
            str(r.get("network_id") or "") + " " + str(r.get("owner_identity") or ""))
    pt = r.get("proposed_tier")
    lid = r.get("location_id"); nm = r.get("practice_name"); z = r.get("zip")
    if SPECIALIST_RE.search(blob) and pt in ("dentist_multi", "stealth_dso", "branded_dso"):
        qa_flags.append({"type": "specialist_network_in_GP_feed", "location_id": lid,
                         "practice_name": nm, "zip": z, "proposed_tier": pt,
                         "note": "AO/brand network appears specialist (ortho/OMS/etc.); EXCLUDE from GP corporate denominator if confirmed."})
    if CLOSED_RE.search(blob):
        qa_flags.append({"type": "possibly_closed_or_inactive", "location_id": lid,
                         "practice_name": nm, "zip": z,
                         "note": "Intel flags closure/inactivity; verify before counting in any denominator."})
# hardcoded cross-session reconciliation flags from agent summaries
qa_flags += [
    {"type": "reconcile_with_main", "location_id": "d96e2b15e57ec2c6",
     "practice_name": "RENOVATIO DENTAL INC", "zip": "60616", "proposed_tier": "stealth_dso",
     "note": "AO Nguyen links to 'Precision Dental Care' chain (dso_regional members across 7 ZIPs). "
             "Main reach-5 wave adjudicated Precision Dental Care as DENTIST-OWNED multi, NO PE → "
             "reconcile to dentist_multi, NOT stealth_dso. Held at needs_verification."},
    {"type": "institutional_vs_stealth", "location_id": "4ec51b1b",
     "practice_name": "PRIMEHEALTH OF ILLINOIS INC", "zip": "60089", "proposed_tier": "stealth_dso",
     "note": "5-state multi-specialty org (dental+podiatry+optometry+audiology), PrimeHealth Group LLC parent. "
             "Could be institutional rather than stealth_dso — QA judgment needed."},
    {"type": "db_data_anomaly", "location_id": "d027da6419b302cd",
     "practice_name": "John Katsis DDS", "zip": "60103",
     "note": "NPPES NPI 1962707620 actually belongs to RALPH DERANGO, not Katsis — likely DB label error. "
             "Data-quality flag for the reset/Gate owner, not an ownership finding."},
    {"type": "invalidated_signal", "location_id": None,
     "practice_name": "Albert Mategrano / Bartlett Dentistry", "zip": "60103",
     "note": "Intel '9 locations' came from bartlettdentalcareil.com which is registered to a DIFFERENT NPI "
             "(Sandra Song). Cross-contamination — multi-location signal INVALIDATED, do not promote."},
]

# ---- 6. write Lane 3 evidence file (all rows + gate notes) -------------------
def tally(rs, key): return dict(collections.Counter(r.get(key) for r in rs))
json.dump({
    "_meta": {"lane": "lane3_zero_corp_zip_sweep", "agent": "fleet_b", "date": "2026-06-21",
              "wave": 2, "zips_swept": ["60089", "60103", "60148", "60181", "60613", "60616"],
              "n_rows": len(deduped), "by_status": tally(deduped, "status"),
              "by_disposition": tally(deduped, "disposition"),
              "by_proposed_tier": tally(deduped, "proposed_tier"),
              "note": "Zero-corp dense-ZIP sweep. DB-only documentary evidence (intel dossiers, EIN/AO "
                      "clusters, name chains). Coverage-first: most rows needs_verification by design. "
                      "Candidate rows only; QA decides. No DB writes."},
    "rows": [clean(r) | {"_gate": r["_gate"]} for r in deduped],
}, open(os.path.join(OUT, "evidence_zip_sweep_fleet_b_20260621.json"), "w"), indent=1)

# ---- 7. write unified Lane 3 queue ------------------------------------------
queue = {
    "_meta": {
        "agent": "fleet_b", "session": "fleet-b-lane3-2026-06-21", "wave": 2,
        "lane": "lane3_zero_corp_zip_sweep",
        "zips_swept": ["60089", "60103", "60148", "60181", "60613", "60616"],
        "raw_rows": len(rows), "deduped_rows": len(deduped),
        "classifications_promotable": len(classifications_clean),
        "held_gate_fail": len(held), "rejected": len(rejected), "conflicts": len(conflicts),
        "by_status_classifications": tally(classifications, "status"),
        "by_tier_classified": tally([r for r in classifications if r.get("status") == "classified"], "assigned_tier"),
        "by_proposed_tier_needs_verification": tally(
            [r for r in classifications if r.get("status") == "needs_verification"], "proposed_tier"),
        "validator_note": ("classifications[] = gate-passing classified + needs_verification rows "
                           "(IL GP-scope, not excluded-class, not already tiered). rejected[] = DA_ "
                           "synthetics. held[] = location fails a validator location check. NOT final "
                           "truth; --validate-only only; consolidation FROZEN until Gate Owner + user."),
        "_qa_flags": qa_flags,
        "DO_NOT_MUTATE_WAVE1": "This is a SEPARATE Lane-3 queue. The wave-1 queue "
                               "(ownership_evidence_queue_fleet_b_20260621.json) is unchanged per QA.",
    },
    "classifications": classifications_clean,
    "held": [clean(r) | {"_gate": r["_gate"]} for r in held],
    "rejected": [clean(r) for r in rejected],
    "conflicts": conflicts,
}
json.dump(queue, open(os.path.join(OUT, "ownership_evidence_queue_fleet_b_lane3_20260621.json"), "w"), indent=1)

# ---- 8. console summary -----------------------------------------------------
print("\n=== LANE 3 PARTITION ===")
print(f"  classifications (-> validator): {len(classifications_clean)}")
print(f"    classified       : {sum(1 for r in classifications if r.get('status')=='classified')}")
print(f"    needs_verification: {sum(1 for r in classifications if r.get('status')=='needs_verification')}")
print(f"  held (gate-fail)   : {len(held)}  reasons={dict(collections.Counter(r['_gate'].split('(')[0] for r in held))}")
print(f"  rejected (DA_ etc) : {len(rejected)}")
print(f"  conflicts          : {len(conflicts)}")
print(f"\nclassified tier breakdown: {tally([r for r in classifications if r.get('status')=='classified'], 'assigned_tier')}")
print(f"needs_verif proposed-tier breakdown: {tally([r for r in classifications if r.get('status')=='needs_verification'], 'proposed_tier')}")
print(f"\nQA flags surfaced: {len(qa_flags)}")
for fl in qa_flags:
    print(f"  [{fl['type']}] {fl.get('practice_name')} ({fl.get('zip')})")
print("\nWROTE:")
for fn in ("evidence_zip_sweep_fleet_b_20260621.json",
           "ownership_evidence_queue_fleet_b_lane3_20260621.json"):
    print("  ", fn)
