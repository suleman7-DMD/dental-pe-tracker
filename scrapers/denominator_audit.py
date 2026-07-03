"""
Phase 1 (Chicagoland Ownership Census) — DENOMINATOR AUDIT. READ-ONLY.
Confirms the ~4,439 IL GP location base is clean before the census assigns
ownership_tier. Flips NOTHING. Writes data/dso_research/denominator_audit_<date>.json.

Checks:
  1. Official denominator (SUM zip_scores.total_gp_locations, IL) vs direct
     GP location count, global + per-ZIP. Reports any mismatch.
  2. Duplicate candidates: GP IL locations sharing ZIP + phone + street-core
     (the 2026-06-19 cleanup signal) under DIFFERENT location_ids. FLAGS only —
     does not collapse. Distinguishes "same normalized_address" (normalizer miss)
     from "suite variants" (genuine review needed).
  3. Location-level classification distribution (IL GP) for the record.
"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
AUDIT_DATE = "20260620"  # stamp passed explicitly (no Date.now in this project's tooling spirit)
OUT = os.path.join(ROOT, "data", "dso_research", f"denominator_audit_{AUDIT_DATE}.json")

# GP = everything except these non-GP / excluded classes
EXCLUDED = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

il_zips = [r[0] for r in c.execute("SELECT zip_code FROM watched_zips WHERE state='IL'")]
qmarks = ",".join("?" * len(il_zips))

# ── 1. Denominator reconciliation ────────────────────────────────────────
official = c.execute(
    f"SELECT SUM(total_gp_locations) FROM zip_scores WHERE zip_code IN ({qmarks})", il_zips
).fetchone()[0]

# direct GP location count, and per-ZIP
direct_rows = c.execute(f"""
    SELECT zip, entity_classification, COUNT(*) n
    FROM practice_locations
    WHERE state='IL' AND zip IN ({qmarks})
    GROUP BY zip, entity_classification
""", il_zips).fetchall()

direct_per_zip = defaultdict(int)
class_dist = defaultdict(int)
for r in direct_rows:
    class_dist[r["entity_classification"]] += r["n"]
    if r["entity_classification"] not in EXCLUDED:
        direct_per_zip[r["zip"]] += r["n"]
direct_total = sum(direct_per_zip.values())

# per-ZIP official
official_per_zip = {
    r["zip_code"]: (r["total_gp_locations"] or 0)
    for r in c.execute(
        f"SELECT zip_code, total_gp_locations FROM zip_scores WHERE zip_code IN ({qmarks})", il_zips
    )
}
mismatches = []
for z in il_zips:
    o, d = official_per_zip.get(z, 0), direct_per_zip.get(z, 0)
    if o != d:
        mismatches.append({"zip": z, "official_gp": o, "direct_gp": d, "delta": d - o})

# ── 2. Duplicate candidates (FLAG ONLY) ──────────────────────────────────
gp = c.execute(f"""
    SELECT location_id, normalized_address, zip, phone, practice_name,
           entity_classification
    FROM practice_locations
    WHERE state='IL' AND zip IN ({qmarks})
      AND entity_classification NOT IN ({",".join("?"*len(EXCLUDED))})
""", il_zips + sorted(EXCLUDED)).fetchall()

def street_core(addr):
    if not addr:
        return ""
    a = addr.upper()
    # drop suite/unit tails
    a = re.split(r'\b(STE|SUITE|UNIT|#|APT|FL|FLOOR|BLDG)\b', a)[0]
    toks = re.findall(r'[A-Z0-9]+', a)
    return " ".join(toks[:3])  # house number + first two street tokens

def norm_phone(p):
    if not p:
        return ""
    d = re.sub(r'\D', '', p)
    return d[-10:] if len(d) >= 10 else d

# high-confidence: same zip + same phone + same street_core, >1 location_id
by_key = defaultdict(list)
for r in gp:
    ph = norm_phone(r["phone"])
    if not ph:
        continue
    key = (r["zip"], ph, street_core(r["normalized_address"]))
    by_key[key].append(dict(r))

dup_clusters = []
dup_loc_count = 0
for key, rows in by_key.items():
    ids = {x["location_id"] for x in rows}
    if len(ids) < 2:
        continue
    same_norm = len({x["normalized_address"] for x in rows}) == 1
    dup_loc_count += len(ids) - 1  # extras beyond the first
    dup_clusters.append({
        "zip": key[0], "phone": key[1], "street_core": key[2],
        "n_locations": len(ids),
        "kind": "normalizer_miss" if same_norm else "suite_variant",
        "locations": [
            {"location_id": x["location_id"], "name": x["practice_name"],
             "addr": x["normalized_address"], "class": x["entity_classification"]}
            for x in rows
        ],
    })
dup_clusters.sort(key=lambda x: -x["n_locations"])

# ── assemble + write ─────────────────────────────────────────────────────
audit = {
    "_meta": {
        "audit_date": AUDIT_DATE, "scope": "Chicagoland IL watched GP locations",
        "read_only": True, "flips": 0,
        "purpose": "Confirm the ~4,439 IL GP denominator is clean before the ownership census.",
    },
    "denominator": {
        "official_sum_zip_scores_total_gp": official,
        "direct_gp_location_count": direct_total,
        "match": official == direct_total,
        "per_zip_mismatches": mismatches,
        "per_zip_mismatch_count": len(mismatches),
    },
    "classification_distribution_il_loc": dict(sorted(class_dist.items(), key=lambda kv: -kv[1])),
    "excluded_classes": sorted(EXCLUDED),
    "corporate_locations_legacy": class_dist.get("dso_national", 0) + class_dist.get("dso_regional", 0),
    "duplicate_candidates": {
        "method": "same ZIP + same 10-digit phone + same street-core, >1 location_id (2026-06-19 signal)",
        "cluster_count": len(dup_clusters),
        "extra_locations_if_collapsed": dup_loc_count,
        "by_kind": {
            "normalizer_miss": sum(1 for d in dup_clusters if d["kind"] == "normalizer_miss"),
            "suite_variant": sum(1 for d in dup_clusters if d["kind"] == "suite_variant"),
        },
        "note": "FLAGGED, not collapsed. normalizer_miss = strong dup (same normalized_address). "
                "suite_variant = review (could be genuinely distinct practices in one building). "
                "Collapsing would reduce the 4,439 base by at most extra_locations_if_collapsed.",
        "clusters": dup_clusters,
    },
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(audit, f, indent=2)

# console summary
print(f"DENOMINATOR: official={official}  direct={direct_total}  match={official == direct_total}")
print(f"PER-ZIP MISMATCHES: {len(mismatches)}")
print(f"CORPORATE (legacy dso_*): {audit['corporate_locations_legacy']}")
print(f"DUP CANDIDATES: {len(dup_clusters)} clusters, "
      f"{dup_loc_count} extra locations if collapsed "
      f"({audit['duplicate_candidates']['by_kind']})")
print(f"Wrote {OUT}")
