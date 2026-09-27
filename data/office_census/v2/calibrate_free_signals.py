#!/usr/bin/env python3
"""Reproduce the free-signal calibration tables in V2_PLAN_2026-09-27.md. Read-only.

  python3 data/office_census/v2/calibrate_free_signals.py

Inputs: rapid/queue.jsonl, rapid/checks.jsonl (local mirror; run `office_census_rapid.py pull`
first for fresh numbers), the unresolved audit CSV, and the two public registries saved under
staging/public_registries_20260927/ (IEMA X-ray facility export, IDFPR dental licenses).

Controls are rows the rapid loop already decided: VALID / VALID_CORRECTED = known open,
NOT_CURRENT_GP closed / moved / home_or_registration = known not open here. A signal is useful
as "current operation" evidence only if it fires often on known-open rows and almost never on
known-not-open rows. All counts are rapid-queue ROWS, not offices.
"""
import collections
import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OC = ROOT / "data" / "office_census"
REG = OC / "staging" / "public_registries_20260927"
sys.path.insert(0, str(ROOT / "scrapers"))
import office_census_address as oca  # noqa: E402

NEG_SIGNALS = {"real_estate_listing", "home_address", "website_dead", "owner_deceased", "owner_retired",
               "practice_sold", "successor_practice", "phone_belongs_elsewhere", "website_wrong_business"}


def d10(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else None


def addr_key(addr, zip_code):
    try:
        p = oca.parse_physical_address(addr or "")
    except Exception:
        return None
    return (str(zip_code)[:5], p["house"], p["street"]) if p.get("house") else None


def load_iema():
    import openpyxl
    rows = list(openpyxl.load_workbook(REG / "iema_radhealth_facilities_20260927.xlsx",
                                       read_only=True).active.iter_rows(values_only=True))
    dental = [dict(zip(rows[0], r)) for r in rows[1:] if r[rows[0].index("Category")] in ("Dental Clinic", "Dentist")]
    by_addr = collections.defaultdict(list)
    for r in dental:
        k = addr_key(r["Physical Address"], r["Zip"])
        if k:
            by_addr[k].append(r)
    return dental, by_addr


def name_key(first, last):
    f = (first or "").lower().split()
    return (re.sub(r"[^a-z]", "", f[0]) if f else "", re.sub(r"[^a-z]", "", (last or "").lower()))


def load_idfpr():
    lic = json.loads((REG / "idfpr_dental_licenses_20260927.json").read_text())
    by_name = collections.defaultdict(list)
    for r in lic:
        by_name[name_key(r.get("first_name"), r.get("last_name"))].append(r)

    def status(provider):
        parts = provider.replace(",", " ").split()
        if len(parts) < 2:
            return None
        hits = by_name.get(name_key(parts[0], parts[-1]), [])
        if not hits:
            return None
        return "ACTIVE" if any(h["license_status"] == "ACTIVE" for h in hits) else "NONACTIVE"
    return status


def latest_checks():
    out = {}
    for line in (OC / "rapid" / "checks.jsonl").open():
        e = json.loads(line)
        if e.get("type") == "rapid_check" and (e["candidate_id"] not in out or
                                                e["recorded_at"] >= out[e["candidate_id"]]["recorded_at"]):
            out[e["candidate_id"]] = e
    return out


def main():
    queue = {json.loads(l)["cid"]: json.loads(l) for l in (OC / "rapid" / "queue.jsonl").open()}
    checks = latest_checks()
    _, iema = load_iema()
    lic = load_idfpr()

    def features(q, e):
        ph, k = d10(q["phone"]), addr_key(q["address"], q["zip"])
        at_site = iema.get(k, []) if k else []
        same = [r for r in at_site if ph and d10(r["Phone Number"]) == ph]
        sts = [lic(p) for p in q.get("providers") or []]
        neg = bool(set(e.get("signals") or []) & NEG_SIGNALS) or bool(q.get("status_notes"))
        return at_site, same, sts, neg

    print("== Controls: how often each free signal fires, by rapid decision (rows) ==")
    grp = collections.defaultdict(collections.Counter)
    for cid, e in checks.items():
        q = queue.get(cid)
        if not q:
            continue
        label = e["decision"] + (":" + e["reason"] if e.get("reason") else "")
        at_site, same, sts, neg = features(q, e)
        g = grp[label]
        g["n"] += 1
        g["iema_same"] += bool(same)
        g["rule_open_a"] += bool(same) and "ACTIVE" in sts and not neg
        if len(q.get("providers") or []) == 1:
            g["solo"] += 1
            g["solo_nonactive"] += sts == ["NONACTIVE"]
    print(f"{'decision':36} {'rows':>5} {'IEMA addr+phone':>16} {'OPEN-A rule':>12} {'solo lic non-active':>20}")
    for label, v in sorted(grp.items(), key=lambda kv: -kv[1]["n"]):
        n, s = v["n"], max(v["solo"], 1)
        print(f"{label:36} {n:5} {v['iema_same']:6} ({v['iema_same'] / n:4.0%})   {v['rule_open_a']:4} ({v['rule_open_a'] / n:4.0%})"
              f"   {v['solo_nonactive']:4}/{v['solo']:<4} ({v['solo_nonactive'] / s:4.0%})")

    print("\n== Free-signal triage of the checked-unresolved pile (rows) ==")
    unresolved = list(csv.DictReader((OC / "audits" / "2026-09-27_unresolved" / "unresolved_all.csv").open()))
    tri = collections.Counter()
    for u in unresolved:
        q, e = queue[u["candidate_id"]], checks[u["candidate_id"]]
        at_site, same, sts, neg = features(q, e)
        if same and "ACTIVE" in sts and not neg:
            t = "OPEN-A: IEMA addr+phone + active dentist license + no negative signal"
        elif same or (at_site and not neg):
            t = "OPEN-pending: IEMA facility at the site, needs a second signal"
        elif sts and all(s == "NONACTIVE" for s in sts) and not at_site:
            t = "CLOSED-candidate: every row dentist non-active, no IEMA facility at the site"
        else:
            t = "needs Places / browser"
        tri[t] += 1
    for t, n in tri.most_common():
        print(f"  {n:5}  {n / len(unresolved):5.1%}  {t}")
    print(f"  {len(unresolved):5}  total checked-unresolved rows in the audit snapshot")


if __name__ == "__main__":
    main()
