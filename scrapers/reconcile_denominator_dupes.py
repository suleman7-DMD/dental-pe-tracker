"""
READ-ONLY row-level reconciliation of the two conflicting IL-GP duplicate counts:
  - denominator_audit_20260620.json  : 48 clusters keyed (zip, phone, street_core)
  - il_denominator_pressure_test_*   : 87 excess rows keyed same-address + shared phone/EIN

Neither is "wrong" — they use different keys. This script recomputes BOTH definitions
directly from the live DB over IL watched GP locations, then reports ONE reconciled
high-confidence collapse set (union of the two) with row-level location_ids, so any
future denominator collapse rests on a single auditable list. FLAGS ONLY — zero writes.

Output: data/dso_research/denominator_reconciliation_20260621.json
"""
import json
import os
import re
import sqlite3
from collections import defaultdict

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(ROOT, "data", "dso_research", "denominator_reconciliation_20260621.json")
EXCLUDED = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 10 else ""


def norm_ein(e):
    d = re.sub(r"\D", "", e or "")
    return d if d and d not in ("0", "000000000") else ""


def street_core(addr):
    if not addr:
        return ""
    a = re.split(r"\b(STE|SUITE|UNIT|#|APT|FL|FLOOR|BLDG)\b", addr.upper())[0]
    return " ".join(re.findall(r"[A-Z0-9]+", a)[:3])


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    il_zips = [r[0] for r in c.execute("SELECT zip_code FROM watched_zips WHERE state='IL'")]
    qm = ",".join("?" * len(il_zips))
    exq = ",".join("?" * len(EXCLUDED))
    rows = c.execute(f"""
        SELECT location_id, normalized_address, zip, phone, ein, practice_name,
               primary_npi, org_npi, entity_classification, ownership_tier
        FROM practice_locations
        WHERE state='IL' AND zip IN ({qm}) AND entity_classification NOT IN ({exq})
    """, il_zips + sorted(EXCLUDED)).fetchall()

    # ── Method A: (zip, phone, street_core), phone required ──
    a_groups = defaultdict(list)
    for r in rows:
        ph = norm_phone(r["phone"])
        if not ph:
            continue
        a_groups[(r["zip"], ph, street_core(r["normalized_address"]))].append(r["location_id"])
    A = {frozenset(v) for v in a_groups.values() if len(set(v)) > 1}

    # ── Method B: same (zip, street_core) [address-core, suite-insensitive],
    #    rows linked when they SHARE phone OR EIN (the pressure-test definition) ──
    addr_groups = defaultdict(list)
    for r in rows:
        sc = street_core(r["normalized_address"])
        if sc:
            addr_groups[(r["zip"], sc)].append(r)
    B, multitenant_kept = set(), 0
    for key, members in addr_groups.items():
        if len(members) < 2:
            continue
        # within a same-address group, link rows that share phone or EIN
        link = defaultdict(set)
        for m in members:
            sig = (norm_phone(m["phone"]), norm_ein(m["ein"]))
            if sig[0]:
                link[("p", sig[0])].add(m["location_id"])
            if sig[1]:
                link[("e", sig[1])].add(m["location_id"])
        dup_here = {frozenset(s) for s in link.values() if len(s) > 1}
        if dup_here:
            for s in dup_here:
                B.add(s)
        else:
            multitenant_kept += 1   # same address, no shared owner-id → distinct practices

    def excess(clusters):
        return sum(len(s) - 1 for s in clusters)

    union = set(A) | set(B)
    # merge overlapping clusters across methods into connected components
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union_(a, b):
        parent[find(a)] = find(b)
    for s in union:
        members = list(s)
        for m in members:
            find(m)
        for m in members[1:]:
            union_(members[0], m)
    comp = defaultdict(set)
    for s in union:
        for m in s:
            comp[find(m)].add(m)
    reconciled = [sorted(v) for v in comp.values() if len(v) > 1]

    name_by_id = {r["location_id"]: r["practice_name"] for r in rows}
    cls_by_id = {r["location_id"]: r["entity_classification"] for r in rows}

    out = {
        "_doc": "READ-ONLY row-level reconciliation of the 48-vs-87 IL-GP duplicate conflict. "
                "FLAGS ONLY, no DB writes. The two source artifacts used different keys; "
                "this unifies them into one connected-component collapse set.",
        "il_gp_rows_considered": len(rows),
        "method_A_zip_phone_streetcore": {"clusters": len(A), "excess_rows_if_collapsed": excess(A)},
        "method_B_sameaddr_shared_phone_or_ein": {"clusters": len(B), "excess_rows_if_collapsed": excess(B),
                                                  "multitenant_clusters_kept": multitenant_kept},
        "reconciled_union": {
            "clusters": len(reconciled),
            "excess_rows_if_collapsed": sum(len(s) - 1 for s in reconciled),
            "note": "Connected components across BOTH methods. Collapsing would reduce the "
                    "4,439 IL GP denominator by at most excess_rows_if_collapsed (~1-2%). "
                    "This is a minor refinement; the census numerator remains the main driver.",
        },
        "clusters": [
            {"location_ids": s,
             "names": [name_by_id.get(x) for x in s],
             "classes": [cls_by_id.get(x) for x in s]}
            for s in sorted(reconciled, key=lambda x: -len(x))
        ],
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"IL GP rows: {len(rows)}")
    print(f"Method A (zip,phone,street): {len(A)} clusters, {excess(A)} excess")
    print(f"Method B (sameaddr+shared id): {len(B)} clusters, {excess(B)} excess; "
          f"{multitenant_kept} multitenant kept")
    print(f"RECONCILED union: {len(reconciled)} clusters, "
          f"{sum(len(s)-1 for s in reconciled)} excess rows if collapsed")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
