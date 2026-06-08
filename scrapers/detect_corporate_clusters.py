"""Phase B2 — Structural corporate-cluster detector (officer / mailing / parent-TIN / EIN).

The deepest free signal we own: NPPES discloses, for organization NPIs, the
Authorized Official (the human who legally controls the org), the back-office
MAILING address (DSOs route many local friendly-PCs to one MSO billing address),
the parent-organization TIN, and the subpart flag. Independently, both the
il-gov-data-scout and dso-scoreboard-scout ranked these as the #1 unextracted
lever for piercing the IL friendly-PC veil. This detector clusters watched
organization NPIs on those structural keys and surfaces the clusters whose
members are STILL classified independent — the corporate-flip opportunity.

Four clustering passes (each independent; a cluster can fire on several):
  TIN  — shared parent_org_tin across 2+ org NPIs  (gold standard; needs backfill)
  AO   — same Authorized Official (last,first) signing 3+ org NPIs at 2+ addresses
  MAIL — shared back-office MAILING address (!= practice address) across 3+ offices
  EIN  — shared ein across 2+ ZIPs  (works PRE-backfill, on existing column)
Plus a per-NPI corroboration flag:
  TITLE — Authorized Official title is a corporate-exec role (VP/Regional/COO/...)
          AND the AO credential is not clinical (DDS/DMD) — i.e. an MSO executive,
          not the owner-dentist signing for their own solo PC.

READ-ONLY + GATED-AWARE. Opens its own SQLite connection, SELECT-only, writes a
JSON candidate file. If the Phase A ownership columns are not yet backfilled it
runs the EIN pass only and says so — it never errors on a fresh DB. It NEVER
promotes anything: clusters are candidates for the Phase C web-verify gate, which
is the only thing allowed to flip independent -> corporate.

Output: data/dso_research/cluster_candidates_b2.json
Usage:  python3 scrapers/detect_corporate_clusters.py [--state IL|MA|all] [--min-cluster 2]
"""
import argparse
import json
import os
import re
import sqlite3
from collections import defaultdict

try:
    from dso_brands import match_dso_brand, NATIONAL_DSO_BRANDS
except ImportError:  # when imported as scrapers.detect_corporate_clusters
    from scrapers.dso_brands import match_dso_brand, NATIONAL_DSO_BRANDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(ROOT, "data", "dso_research", "cluster_candidates_b2.json")

CORPORATE = ("dso_regional", "dso_national")
INDEP = ("solo_established", "solo_new", "solo_inactive", "solo_high_volume",
         "family_practice", "small_group", "large_group", "org_only_npi")

# Institutions that legitimately share a mailing address / EIN / officer across
# many "offices" but are NOT DSOs — universities, hospitals, public-health, FQHCs,
# government, corrections. A cluster dominated by these is a false positive and is
# excluded (the UIC dental school at 801 S Paulina, county health depts, etc.).
INSTITUTIONAL_KW = (
    "UNIVERSITY", "COLLEGE", "HOSPITAL", "MEDICAL CENTER", "MEDICAL CTR",
    "HEALTH SYSTEM", "HEALTH DEPARTMENT", "DEPT OF HEALTH", "PUBLIC HEALTH",
    "FEDERALLY QUALIFIED", "FQHC", "COMMUNITY HEALTH", "COUNTY OF", "CITY OF",
    "STATE OF", "DEPARTMENT OF", "BOARD OF EDUCATION", "SCHOOL DISTRICT",
    "VETERANS", "ARMY", "NAVY", "AIR FORCE", "CORRECTIONAL", "PENITENTIARY",
    "INFIRMARY", "HEAD START", "MIGRANT", "SALVATION ARMY",
)
# A brand-LESS structural cluster spanning more than this many distinct practice
# addresses is almost certainly an institution or a national billing bureau, not a
# Chicagoland DSO — downgraded to "weak" so it can never reach a promotable tier.
OVERBROAD_ADDR_CAP = 25

# Authorized-Official titles that signal an MSO/corporate executive rather than an
# owner-dentist. Matched as substrings against the uppercased title.
EXEC_TITLE_KW = (
    "VICE PRESIDENT", " VP", "VP ", "REGIONAL", "DIRECTOR OF", "OPERATIONS",
    "CHIEF", " CEO", " CFO", " COO", "CONTROLLER", "ADMINISTRATOR", "CORPORATE",
    "DIVISION", "MARKET MANAGER", "AREA MANAGER", "GENERAL COUNSEL", "TREASURER",
    "SVP", "EVP", "MANAGING MEMBER", "MANAGING DIRECTOR",
)
CLINICAL_CRED = ("DDS", "DMD", "D.D.S", "D.M.D", "DENTIST")

_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")
_SUITE = re.compile(r"\b(STE|SUITE|UNIT|APT|#|FL|FLOOR|RM|ROOM|BLDG)\b.*$")


def norm_addr(a):
    """Coarse address key for grouping: upper, drop suite/unit tail, collapse."""
    if not a:
        return None
    s = _PUNCT.sub(" ", a.upper())
    s = _WS.sub(" ", s).strip()
    s = _SUITE.sub("", s).strip()
    s = _WS.sub(" ", s).strip()
    return s or None


def col_exists(conn, table, col):
    return col in {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def is_exec_title(title, cred):
    if not title:
        return False
    t = title.upper()
    if not any(k.strip() in t for k in EXEC_TITLE_KW):
        return False
    # An owner-dentist signing as "PRESIDENT" of their own PC with a DDS credential
    # is NOT a corporate signal. Require the credential to be non-clinical/blank.
    if cred and any(c in cred.upper() for c in CLINICAL_CRED):
        return False
    return True


def _cluster_summary(key, members, kind, corrob_extra=None):
    zips = sorted({m["zip"] for m in members if m["zip"]})
    classes = defaultdict(int)
    for m in members:
        classes[m["entity_classification"] or "NULL"] += 1
    corp_n = sum(v for k, v in classes.items() if k in CORPORATE)
    indep_n = sum(v for k, v in classes.items() if k in INDEP)
    return {
        "cluster_kind": kind,
        "cluster_key": key,
        "npi_count": len(members),
        "zip_count": len(zips),
        "zips": zips,
        "class_breakdown": dict(classes),
        "still_independent": indep_n,
        "already_corporate": corp_n,
        "corroboration": corrob_extra or {},
        # FULL membership (build_flip_queue keys on this so large clusters are not
        # truncated). The verbose `members` detail stays capped at 12 for the file.
        "all_npis": [m["npi"] for m in members],
        "members": [
            {"npi": m["npi"], "name": m["practice_name"], "addr": m["address"],
             "city": m["city"], "zip": m["zip"], "class": m["entity_classification"]}
            for m in members[:12]
        ],
    }


# ---------------------------------------------------------------------------
# Data-Axle-powered passes (B2-DA*). The 2026-06-07 importer expansion +
# backfill populated, on `practices`, the corporate-ownership signals Data Axle
# carries but the importer historically discarded: secondary EINs (da_ein2/3),
# the back-office MAILING address (da_mailing_*), the legal entity name
# (da_legal_name), and the executive/officer roster (da_officers, JSON). These
# pierce the friendly-PC veil structurally — independent-LOOKING practices that
# share a tax ID, a back-office, an owning officer, or a corporate-parent name.
# Unlike the NPPES passes above (org-NPI only), these run over ALL watched
# practices because the backfill attached each signal to every co-located NPI.
# ---------------------------------------------------------------------------

def _is_institutional(name):
    if not name:
        return False
    u = f" {name.upper()} "
    return any(kw in u for kw in INSTITUTIONAL_KW)


def _member_institutional(m):
    """A practice is institutional if its name OR its corporate-parent OR its
    legal name names a university/hospital/government/FQHC. Individual faculty
    NPIs carry a personal practice_name but a UNIVERSITY parent_company, so the
    name-only check misses them — check all three."""
    return (_is_institutional(m.get("practice_name")) or
            _is_institutional(m.get("parent_company")) or
            _is_institutional(m.get("da_legal_name")))


def _loc_key(addr, zipc):
    """Distinct-location key: normalized address + 5-digit ZIP."""
    a = norm_addr(addr)
    z = (zipc or "")[:5]
    if not a or not z:
        return None
    return f"{a}|{z}"


_EIN_JUNK = {"123456789", "987654321", "111111111", "000000000"}


def _clean_ein(v):
    if not v:
        return None
    d = re.sub(r"\D", "", str(v))
    if not d or len(d) < 9:
        return None
    d = d[-9:]
    # reject placeholders / sentinels: all-zero, classic sequences, or a single
    # digit dominating (e.g. 125555555 -> six 5s) — these are data-entry fillers,
    # not real tax IDs, and would manufacture phantom clusters.
    if d in _EIN_JUNK or set(d) <= {"0"}:
        return None
    if max(d.count(c) for c in set(d)) >= 6:
        return None
    return d


def _collect_eins(r):
    out = []
    for col in ("ein", "da_ein2", "da_ein3"):
        e = _clean_ein(r.get(col))
        if e and e not in out:
            out.append(e)
    return out


def _parse_officers(r):
    """Return list of (LAST, FIRST) full normalized officer keys from da_officers JSON.

    Full first name (not initial) — first-initial matching collapses common
    surnames (PATEL/KHAN/LEE) into phantom "one officer runs 60 practices"
    clusters. Even full names are an inherently weak identifier, so the officer
    pass is corroboration-only (never promotable on its own — see da_clusters)."""
    raw = r.get("da_officers")
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except (ValueError, TypeError):
        return []
    keys = []
    for o in arr if isinstance(arr, list) else []:
        if not isinstance(o, dict):
            continue
        last = (o.get("last") or "").strip().upper()
        first = (o.get("first") or "").strip().upper()
        if len(last) < 2 or len(first) < 2:
            continue
        keys.append((last, first))
    return list(dict.fromkeys(keys))


def _distinct_addrs(members):
    return {_loc_key(m["address"], m["zip"]) for m in members
            if _loc_key(m["address"], m["zip"])}


def _distinct_names(members):
    return {norm_addr(m["practice_name"]) for m in members if m["practice_name"]}


def _dedup_member_rows(members):
    """Collapse duplicate NPIs (a row can appear once per EIN it carries)."""
    seen, out = set(), []
    for m in members:
        if m["npi"] in seen:
            continue
        seen.add(m["npi"])
        out.append(m)
    return out


def da_clusters(rows, min_distinct=3):
    """Run the four Data-Axle structural passes over all watched practices."""
    clusters = []

    # --- DA-EIN: shared tax ID (ein / da_ein2 / da_ein3) across 3+ locations ---
    by_ein = defaultdict(list)
    for r in rows:
        for e in _collect_eins(r):
            by_ein[e].append(r)
    for ein, members in by_ein.items():
        members = _dedup_member_rows(members)
        addrs = _distinct_addrs(members)
        if len(addrs) < max(min_distinct, 3):
            continue
        inst = sum(1 for m in members if _member_institutional(m))
        if inst > len(members) / 2:
            continue  # institution-dominated EIN (university/hospital billing)
        overbroad = len(addrs) > OVERBROAD_ADDR_CAP
        brand = None
        for m in members:
            hit = (match_dso_brand(m.get("practice_name"), m.get("doing_business_as"))
                   or match_dso_brand(m.get("parent_company"))
                   or match_dso_brand(m.get("da_legal_name")))
            if hit:
                brand = hit[0]
                break
        # shared tax ID across 4+ distinct offices = strong (a real multi-office
        # operating company); exactly 3 = medium (could be a small local group —
        # needs a second signal or web-verify before it can promote).
        strength = ("weak" if overbroad
                    else "strong" if len(addrs) >= 4 else "medium")
        clusters.append(_cluster_summary(
            f"DAEIN:{ein}", members, "da_shared_ein",
            {"ein": ein, "distinct_locations": len(addrs),
             "matched_dso": brand, "over_broad": overbroad,
             "strength": strength,
             "evidence_field": "da_ein2/da_ein3/ein (Data Axle tax ID)"}))

    # --- DA-MAIL: shared back-office mailing addr (!= practice) across 3+ addrs ---
    by_mail = defaultdict(list)
    for r in rows:
        m_addr = norm_addr(r.get("da_mailing_address"))
        p_addr = norm_addr(r.get("address"))
        if m_addr and m_addr != p_addr:
            by_mail[(m_addr, (r.get("da_mailing_zip") or "")[:5])].append(r)
    for (m_addr, mzip), members in by_mail.items():
        members = _dedup_member_rows(members)
        addrs = _distinct_addrs(members)
        if len(addrs) < max(min_distinct, 3):
            continue
        if _is_institutional(m_addr):
            continue
        inst = sum(1 for m in members if _member_institutional(m))
        if inst > len(members) / 2:
            continue
        overbroad = len(addrs) > OVERBROAD_ADDR_CAP
        brand = None
        for m in members:
            hit = (match_dso_brand(m.get("practice_name"), m.get("doing_business_as"))
                   or match_dso_brand(m.get("parent_company")))
            if hit:
                brand = hit[0]
                break
        strength = "weak" if overbroad else ("strong" if len(addrs) >= 4 else "medium")
        clusters.append(_cluster_summary(
            f"DAMAIL:{m_addr} {mzip}".strip(), members, "da_shared_mailing",
            {"mailing_address": m_addr, "mailing_zip": mzip,
             "distinct_practice_addresses": len(addrs), "matched_dso": brand,
             "over_broad": overbroad, "strength": strength,
             "evidence_field": "da_mailing_address (Data Axle back-office)"}))

    # --- DA-OFFICER: same owning officer across 4+ distinct-NAME practices ---
    # Corroboration-ONLY. An officer name is a weak identifier (common surnames,
    # data drift), so this pass is capped at strength "weak": it can lift a
    # candidate that ALSO fires another signal, but never reaches a promotable
    # tier by itself. Bars are deliberately high (4+ distinct names, 3+ addrs).
    by_off = defaultdict(list)
    for r in rows:
        for key in _parse_officers(r):
            by_off[key].append(r)
    for (last, fn), members in by_off.items():
        members = _dedup_member_rows(members)
        names = _distinct_names(members)
        addrs = _distinct_addrs(members)
        if len(names) < 4 or len(addrs) < 3:
            continue
        inst = sum(1 for m in members if _member_institutional(m))
        if inst > len(members) / 2:
            continue
        if len(addrs) > OVERBROAD_ADDR_CAP:
            continue  # common name dominating many addresses — drop entirely
        brand = None
        for m in members:
            hit = match_dso_brand(m.get("practice_name"), m.get("doing_business_as"))
            if hit:
                brand = hit[0]
                break
        clusters.append(_cluster_summary(
            f"DAOFFICER:{last},{fn}", members, "da_shared_officer",
            {"officer": f"{last}, {fn}", "distinct_names": len(names),
             "distinct_addresses": len(addrs), "matched_dso": brand,
             "strength": "weak",
             "evidence_field": "da_officers (Data Axle executive roster)"}))

    # --- DA-PARENT: parent_company / da_legal_name IS a known DSO/PE brand ---
    by_brand = defaultdict(list)
    for r in rows:
        hit = (match_dso_brand(r.get("parent_company"))
               or match_dso_brand(r.get("da_legal_name")))
        if hit:
            by_brand[hit[0]].append((r, hit[1]))
    for brand, pairs in by_brand.items():
        members = _dedup_member_rows([p[0] for p in pairs])
        sponsor = next((p[1] for p in pairs if p[1]), None)
        clusters.append(_cluster_summary(
            f"DAPARENT:{brand}", members, "da_corporate_parent",
            {"matched_dso": brand, "pe_sponsor": sponsor,
             "distinct_locations": len(_distinct_addrs(members)),
             "strength": "strong",
             "evidence_field": "parent_company/da_legal_name (Data Axle corp tree)"}))

    return clusters


def main(state="all", min_cluster=2):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    have_tin = col_exists(conn, "practices", "parent_org_tin")
    have_ao = col_exists(conn, "practices", "authorized_official_last_name")
    have_mail = col_exists(conn, "practices", "mailing_address")
    have_cred = col_exists(conn, "practices", "authorized_official_credential")
    have_da = (col_exists(conn, "practices", "da_officers")
               and col_exists(conn, "practices", "da_mailing_address")
               and col_exists(conn, "practices", "da_ein2"))
    backfilled = have_tin and have_ao and have_mail

    sel = ["p.npi", "p.practice_name", "p.entity_type", "p.zip", "p.city",
           "p.state", "p.entity_classification", "p.ein", "p.parent_company",
           "p.address"]
    if have_tin:
        sel += ["p.parent_org_tin", "p.is_org_subpart", "p.parent_org_lbn"]
    if have_ao:
        sel += ["p.authorized_official_last_name", "p.authorized_official_first_name",
                "p.authorized_official_title"]
    if have_cred:
        sel += ["p.authorized_official_credential"]
    if have_mail:
        sel += ["p.mailing_address", "p.mailing_city", "p.mailing_state", "p.mailing_zip"]

    where_state = "" if state == "all" else f"AND w.state = '{state}'"
    rows = conn.execute(f"""
        SELECT {", ".join(sel)}
        FROM practices p
        JOIN watched_zips w ON p.zip = w.zip_code
        WHERE p.entity_type = 'organization'
          AND p.practice_name IS NOT NULL
          {where_state}
    """).fetchall()
    rows = [dict(r) for r in rows]
    conn.close()

    def g(r, k):
        return r.get(k) if backfilled or k in r else None

    clusters = []

    # --- Pass TIN: shared parent_org_tin ---
    if have_tin:
        by_tin = defaultdict(list)
        for r in rows:
            tin = (r.get("parent_org_tin") or "").strip()
            if tin and tin not in ("0", "000000000"):
                by_tin[tin].append(r)
        for tin, members in by_tin.items():
            if len(members) < min_cluster:
                continue
            lbns = sorted({m.get("parent_org_lbn") for m in members if m.get("parent_org_lbn")})
            clusters.append(_cluster_summary(
                f"TIN:{tin}", members, "parent_org_tin",
                {"parent_lbn": lbns, "strength": "strong"}))

    # --- Pass AO: same authorized official across 3+ org NPIs at 2+ addresses ---
    if have_ao:
        by_ao = defaultdict(list)
        for r in rows:
            ln = (r.get("authorized_official_last_name") or "").strip()
            fn = (r.get("authorized_official_first_name") or "").strip()
            if ln:
                by_ao[(ln, fn)].append(r)
        for (ln, fn), members in by_ao.items():
            addrs = {norm_addr(m["address"]) for m in members if m["address"]}
            if len(members) < max(3, min_cluster) or len(addrs) < 2:
                continue
            titles = sorted({m.get("authorized_official_title") for m in members
                             if m.get("authorized_official_title")})
            exec_flag = any(is_exec_title(m.get("authorized_official_title"),
                                          m.get("authorized_official_credential"))
                            for m in members)
            clusters.append(_cluster_summary(
                f"AO:{ln},{fn}", members, "authorized_official",
                {"titles": titles, "exec_title": exec_flag,
                 "distinct_addresses": len(addrs),
                 "strength": "strong" if exec_flag else "medium"}))

    # --- Pass MAIL: shared back-office mailing address != practice address ---
    if have_mail:
        by_mail = defaultdict(list)
        for r in rows:
            m_addr = norm_addr(r.get("mailing_address"))
            p_addr = norm_addr(r.get("address"))
            if m_addr and m_addr != p_addr:
                by_mail[(m_addr, (r.get("mailing_zip") or "")[:5])].append(r)
        for (m_addr, mzip), members in by_mail.items():
            prac_addrs = {norm_addr(m["address"]) for m in members if m["address"]}
            if len(prac_addrs) < max(3, min_cluster):
                continue
            clusters.append(_cluster_summary(
                f"MAIL:{m_addr} {mzip}".strip(), members, "shared_mailing",
                {"mailing_address": m_addr, "mailing_zip": mzip,
                 "distinct_practice_addresses": len(prac_addrs),
                 "strength": "medium"}))

    # --- Pass EIN: shared ein across 2+ ZIPs (works pre-backfill) ---
    by_ein = defaultdict(list)
    for r in rows:
        ein = (r.get("ein") or "").strip()
        if ein:
            by_ein[ein].append(r)
    for ein, members in by_ein.items():
        zips = {m["zip"] for m in members if m["zip"]}
        if len(members) < min_cluster or len(zips) < 2:
            continue
        clusters.append(_cluster_summary(
            f"EIN:{ein}", members, "shared_ein",
            {"strength": "medium"}))

    # --- Data-Axle structural passes (DA-EIN / DA-MAIL / DA-OFFICER / DA-PARENT) ---
    # Run over ALL watched practices (every entity_type) — the 2026-06-07 backfill
    # attached each da_* signal to every co-located NPI, so a friendly-PC office
    # with no organization NPI is still reachable through its provider NPIs.
    da_count = 0
    if have_da:
        conn2 = sqlite3.connect(DB)
        conn2.row_factory = sqlite3.Row
        da_rows = [dict(r) for r in conn2.execute(f"""
            SELECT p.npi, p.practice_name, p.doing_business_as, p.entity_type,
                   p.zip, p.city, p.state, p.entity_classification, p.address,
                   p.ein, p.parent_company, p.da_ein2, p.da_ein3,
                   p.da_mailing_address, p.da_mailing_zip, p.da_legal_name,
                   p.da_officers, p.da_corporate_employees, p.da_corporate_sales
            FROM practices p
            JOIN watched_zips w ON p.zip = w.zip_code
            WHERE p.practice_name IS NOT NULL
              {where_state}
        """).fetchall()]
        conn2.close()
        da = da_clusters(da_rows, min_distinct=3)
        clusters.extend(da)
        da_count = len(da)

    # Per-NPI exec-title flags (independent of clustering — a single org NPI whose
    # AO is a non-clinical executive is itself a corporate tell).
    exec_title_npis = []
    if have_ao:
        for r in rows:
            if is_exec_title(r.get("authorized_official_title"),
                             r.get("authorized_official_credential")):
                exec_title_npis.append({
                    "npi": r["npi"], "name": r["practice_name"], "zip": r["zip"],
                    "title": r.get("authorized_official_title"),
                    "credential": r.get("authorized_official_credential"),
                    "class": r["entity_classification"]})

    # Rank: clusters with the most still-independent members first (the opportunity).
    clusters.sort(key=lambda c: (c["still_independent"], c["npi_count"]), reverse=True)

    total_indep = sum(c["still_independent"] for c in clusters)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({
            "generated_by": "detect_corporate_clusters.py (Phase B2)",
            "state": state, "min_cluster": min_cluster,
            "backfilled": backfilled,
            "data_axle_passes_active": have_da,
            "da_cluster_count": da_count,
            "columns_available": {"parent_org_tin": have_tin, "authorized_official": have_ao,
                                  "mailing_address": have_mail, "credential": have_cred,
                                  "data_axle_signals": have_da},
            "cluster_count": len(clusters),
            "total_still_independent_in_clusters": total_indep,
            "exec_title_npi_count": len(exec_title_npis),
            "clusters": clusters,
            "exec_title_npis": exec_title_npis[:200],
        }, f, indent=2)

    mode = "FULL (Phase A backfilled)" if backfilled else "PRE-BACKFILL (EIN pass only — run after gate + backfill for TIN/AO/MAIL)"
    print(f"B2 corporate-cluster detector [{mode}]")
    print(f"  Data-Axle passes: {'ACTIVE' if have_da else 'inactive (da_* cols absent)'}"
          f"  ({da_count} DA clusters)")
    print(f"  state={state}  clusters={len(clusters)}  "
          f"still-independent-in-clusters={total_indep}  exec-title NPIs={len(exec_title_npis)}")
    print(f"  written -> {OUT}\n")
    print(f"  {'KIND':<20} {'KEY':<30} {'NPIs':>4} {'ZIPs':>4} {'indep':>5} {'corp':>4}")
    for c in clusters[:30]:
        print(f"  {c['cluster_kind']:<20} {c['cluster_key'][:30]:<30} "
              f"{c['npi_count']:>4} {c['zip_count']:>4} {c['still_independent']:>5} "
              f"{c['already_corporate']:>4}")
    if not backfilled:
        print("\n  NOTE: parent_org_tin / authorized_official / mailing_address not yet "
              "present.\n  Run after the sync gate opens:\n"
              "    python3 -m scrapers.migrate_ownership_cols\n"
              "    python3 scrapers/nppes_downloader.py --backfill-ownership-cols\n"
              "  then re-run this detector for the full TIN/AO/MAIL clustering.")
    return clusters


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="all", choices=["all", "IL", "MA"])
    ap.add_argument("--min-cluster", type=int, default=2)
    a = ap.parse_args()
    main(state=a.state, min_cluster=a.min_cluster)
