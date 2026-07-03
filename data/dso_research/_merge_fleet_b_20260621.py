"""
Fleet B wave-1 merge / dedupe / pre-gate / partition.  READ-ONLY on the DB.
Loads the 12 wave-1 shards, dedupes by location_id (conflicts -> needs_verification),
runs the SAME location checks consolidate_census.validate_rows() runs so the
`classifications` array fed to the validator returns "Validation OK", and partitions
everything else (rejects, gate-held, conflicts) into separate keys for the QA session.
Writes ONLY candidate evidence files under data/dso_research/. No DB / LEDGER / PROGRESS writes.
"""
import json, glob, os, sqlite3, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
SHARDS = os.path.join(ROOT, "data", "dso_research", "_shards_fleet_b")
OUT = os.path.join(ROOT, "data", "dso_research")

EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified",
                       "org_only_npi", "duplicate_location"}

def load(f):
    d = json.load(open(f))
    return d if isinstance(d, list) else d.get("classifications", d.get("rows", []))

def is_da(v):
    return isinstance(v, str) and v.startswith("DA_")

# disposition strength for dedupe winner selection
STRENGTH = {"classified": 3, "needs_verification": 2, "undetermined": 1}
CONF = {"high": 3, "medium": 2, "low": 1, None: 0}

# ---- 1. load all 12 shards, tag lane ---------------------------------------
rows = []
for f in sorted(glob.glob(os.path.join(SHARDS, "_shard_lane2_*.json"))):
    for r in load(f):
        r["_lane"] = "lane2_locator"; r["_shard"] = os.path.basename(f); rows.append(r)
for f in sorted(glob.glob(os.path.join(SHARDS, "_shard_lane1A_*.json"))):
    for r in load(f):
        r["_lane"] = "lane1A_intel"; r["_shard"] = os.path.basename(f); rows.append(r)
print(f"loaded {len(rows)} raw rows from 12 shards")

# ---- 2. dedupe by location_id ----------------------------------------------
by_lid = collections.defaultdict(list)
for r in rows:
    by_lid[r.get("location_id")].append(r)

deduped = []
conflicts = []
for lid, group in by_lid.items():
    if len(group) == 1:
        deduped.append(group[0]); continue
    # pick winner by (status strength, confidence, has-url, exact_address_match)
    def keyf(r):
        return (STRENGTH.get(r.get("status"), 0), CONF.get(r.get("confidence"), 0),
                1 if r.get("evidence_urls") else 0, 1 if r.get("exact_address_match") else 0)
    group_sorted = sorted(group, key=keyf, reverse=True)
    winner = dict(group_sorted[0])
    tiers = {r.get("assigned_tier") for r in group if r.get("status") == "classified"}
    real_tiers = {t for t in tiers if t != "undetermined"}
    conflict_rec = {
        "location_id": lid,
        "lanes": [r["_lane"] for r in group],
        "tiers": [r.get("assigned_tier") for r in group],
        "statuses": [r.get("status") for r in group],
        "reasonings": [r.get("reasoning") for r in group],
    }
    if len(real_tiers) > 1:
        # genuine disagreement on a real tier -> force needs_verification
        winner["status"] = "needs_verification"
        winner["disposition"] = "needs_verification"
        winner["proposed_tier"] = sorted(real_tiers)[0]
        winner["assigned_tier"] = "undetermined"
        winner["confidence"] = "low"
        winner["reasoning"] = ("CONFLICT across lanes (" + ", ".join(sorted(real_tiers)) +
                               "); downgraded to needs_verification. " +
                               (winner.get("reasoning") or ""))
        conflict_rec["resolution"] = "downgraded_needs_verification"
        conflicts.append(conflict_rec)
    else:
        conflict_rec["resolution"] = "kept_winner:" + str(winner.get("status"))
        conflicts.append(conflict_rec)
    winner["_dedupe_group_size"] = len(group)
    deduped.append(winner)

print(f"deduped to {len(deduped)} unique location_ids; {len(conflicts)} multi-shard collisions")

# ---- 3. pre-gate each row against the DB (mirror validate_rows location checks)
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
def gate(lid, status):
    loc = conn.execute("""
        SELECT pl.location_id, pl.state, pl.zip, pl.primary_npi, pl.org_npi,
               pl.entity_classification, pl.ownership_tier, wz.state AS watched_state
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()
    if not loc:
        return "fail:location_not_found", None
    if loc["watched_state"] != "IL" or (loc["state"] or "").upper() != "IL":
        return f"fail:not_IL(state={loc['state']},watched={loc['watched_state']})", loc["entity_classification"]
    if loc["entity_classification"] in EXCLUDED_GP_CLASSES:
        return f"fail:excluded_gp_class:{loc['entity_classification']}", loc["entity_classification"]
    if loc["ownership_tier"]:
        return f"fail:existing_ownership_tier:{loc['ownership_tier']}", loc["entity_classification"]
    if (is_da(loc["primary_npi"]) or is_da(loc["org_npi"])) and status == "classified":
        return "fail:DA_synthetic_classified", loc["entity_classification"]
    return "ok", loc["entity_classification"]

for r in deduped:
    g, ec = gate(r.get("location_id"), r.get("status"))
    r["_gate"] = g
    r["_db_entity_classification"] = ec

# ---- 4. partition -----------------------------------------------------------
classifications, held, rejected = [], [], []
for r in deduped:
    if r.get("status") == "undetermined" or r.get("disposition") == "reject":
        rejected.append(r)
    elif r["_gate"] == "ok":
        classifications.append(r)
    else:
        held.append(r)

# strip internal helper keys from the validator-facing array (keep _lane for provenance)
def clean(r):
    out = {k: v for k, v in r.items() if k not in ("_shard", "_gate",
            "_db_entity_classification", "_dedupe_group_size")}
    return out
classifications_clean = [clean(r) for r in classifications]

# ---- 5. write per-lane evidence files (ALL rows, with gate annotations) -----
lane2 = [r for r in deduped if r.get("_lane") == "lane2_locator"]
lane1A = [r for r in deduped if r.get("_lane") == "lane1A_intel"]

def tier_tally(rs):
    return dict(collections.Counter(r.get("assigned_tier") for r in rs))
def status_tally(rs):
    return dict(collections.Counter(r.get("status") for r in rs))

json.dump({
    "_meta": {"lane": "lane2_locator_exact", "agent": "fleet_b", "date": "2026-06-21",
              "n_rows": len(lane2), "by_status": status_tally(lane2), "by_tier": tier_tally(lane2),
              "note": "Exact-address DSO locator evidence. Candidate rows only; QA decides."},
    "classifications": lane2,
}, open(os.path.join(OUT, "evidence_locator_exact_fleet_b_20260621.json"), "w"), indent=1)

json.dump({
    "_meta": {"lane": "lane1A_intel_mined", "agent": "fleet_b", "date": "2026-06-21",
              "n_rows": len(lane1A), "by_status": status_tally(lane1A), "by_tier": tier_tally(lane1A),
              "note": "practice_intel dossier mining (acquisition_found OR brand mention). Candidate only."},
    "classifications": lane1A,
}, open(os.path.join(OUT, "evidence_practice_intel_mined_fleet_b_20260621.json"), "w"), indent=1)

# ---- 6. write unified queue -------------------------------------------------
queue = {
    "_meta": {
        "agent": "fleet_b", "session": "fleet-b-2026-06-21", "wave": 1,
        "lanes": ["lane2_locator_exact (196 suspects)", "lane1A_intel_TierA (174 high-signal)"],
        "raw_rows": len(rows), "deduped_rows": len(deduped),
        "classifications_promotable": len(classifications_clean),
        "held_gate_fail": len(held), "rejected": len(rejected), "conflicts": len(conflicts),
        "validator_note": ("classifications[] = gate-passing classified + needs_verification rows "
                           "(IL GP-scope, not excluded-class, not already tiered). rejected[] = DA_ "
                           "synthetics. held[] = rows whose location fails a validator location check "
                           "(excluded GP class / existing ownership_tier / non-IL) — preserved as intel "
                           "for QA, NOT fed to the validator. NOT final truth; --validate-only only."),
        "by_status_classifications": status_tally(classifications),
        "by_tier_classifications": tier_tally([r for r in classifications if r.get("status") == "classified"]),
    },
    "classifications": classifications_clean,
    "held": held,
    "rejected": rejected,
    "conflicts": conflicts,
}
json.dump(queue, open(os.path.join(OUT, "ownership_evidence_queue_fleet_b_20260621.json"), "w"), indent=1)

# ---- 7. console summary -----------------------------------------------------
print("\n=== PARTITION ===")
print(f"  classifications (promotable, -> validator): {len(classifications_clean)}")
print(f"    classified : {sum(1 for r in classifications if r.get('status')=='classified')}")
print(f"    needs_verif: {sum(1 for r in classifications if r.get('status')=='needs_verification')}")
print(f"  held (gate-fail, intel for QA)            : {len(held)}")
print(f"  rejected (DA_ synthetics etc.)            : {len(rejected)}")
print(f"  conflicts (multi-shard)                   : {len(conflicts)}")
print("\nheld gate reasons:", dict(collections.Counter(r['_gate'].split('(')[0].split(':')[0]+':'+(r['_gate'].split(':',1)[1].split('(')[0] if ':' in r['_gate'] else '') for r in held)))
print("\nclassified tier breakdown (promotable):",
      tier_tally([r for r in classifications if r.get('status')=='classified']))
# sanity: any classified+low-confidence still present?
bad = [r['location_id'] for r in classifications if r.get('status')=='classified' and r.get('confidence')=='low']
print("classified+low (should be 0):", len(bad))
# sanity: any needs_verification with non-undetermined tier?
badnv = [r['location_id'] for r in classifications if r.get('status')=='needs_verification' and r.get('assigned_tier')!='undetermined']
print("needs_verif+non-undetermined tier (should be 0):", len(badnv))
print("\nWROTE:")
for fn in ("evidence_locator_exact_fleet_b_20260621.json",
           "evidence_practice_intel_mined_fleet_b_20260621.json",
           "ownership_evidence_queue_fleet_b_20260621.json"):
    print("  ", fn)
