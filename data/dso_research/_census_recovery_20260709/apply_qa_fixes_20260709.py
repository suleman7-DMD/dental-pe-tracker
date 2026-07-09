#!/usr/bin/env python3
"""Apply the Fable QA-pass fixes (census-qa-fable, 2026-07-09) to merged_1259_rows.json.

Idempotent via the QA marker in reasoning. Covers:
  - ratified-ruling contradiction (Two Rivers -> SHAFI T3)
  - refuted network linkages stripped from writable fields (net/pe) on undetermined rows
  - missing pe_backed=true (Quad-C, Sonrava)
  - pre-classified rows folded into the R4 network rulings (Grand Dental, Smile Obsession)
  - R5 closure adjudication: closed sites revert to undetermined (fail-closed)
  - same-practice network split unified (DecisionOne)
  - Dentologie pe_backed=true applied uniformly (PM decision: institutional growth capital)
  - owner boilerplate nulled; wrong artifacts scrubbed
  - network_id nulled on true_independent/single_loc_group rows (merge keys, not networks)
  - file-wide network_id slug normalization
"""
import json, sys

MERGED = "/private/tmp/claude-501/-Users-suleman/04294c63-97de-4d3e-b0fe-0aa37fbabc3f/scratchpad/census_results/merged_1259_rows.json"
QMARK = "[QA fix 2026-07-09 (census-qa-fable)"

NORM_MAP = {
    "aspen_dental": "brand:aspen_dental",
    "1st_family_dental": "brand:1st_family_dental",
    "first_family_dental": "brand:1st_family_dental",
    "great_lakes_dental_partners": "brand:great_lakes_dental_partners",
    "chicagoland_smile_group": "brand:great_lakes_dental_partners",
    "brand:chicagoland_smile_group": "brand:great_lakes_dental_partners",
    "smile_obsession": "brand:smile_obsession",
    "dentologie": "brand:dentologie",
    "two_rivers_dental": "ao:SHAFI_SOHAIL",
    "ao:SHAFI_REEM": "ao:SHAFI_SOHAIL",
    "sonrisa_group": "brand:sonrisa_family_dental",
    "partners_in_care_dental": "brand:partners_in_care_il",
    "dentalworks": "ao:NITTINGER_RACHEL",
    "brand:dentalworks_sonrava": "ao:NITTINGER_RACHEL",
    "dent_sure_dental_services": "dent_sure_dental",
}

FIX = {
    "9279cc777453fb1d": dict(tier="dentist_multi", net="ao:SHAFI_SOHAIL", pe=False, conf="medium",
        note="ratified SHAFI ruling: Two Rivers/Reem Shafi network is T3 dentist_multi, not stealth_dso"),
    "d4d827860b4132cb": dict(net=None, pe=False,
        note="Heartland linkage refuted (Elmhurst Dental Group dba Bloomingdale Dental, non-PE Partners in Care); net/pe stripped"),
    "b721ad68889ce64d": dict(net=None, pe=False,
        note="Heartland job posting belongs to a different tenant (Suite 241); census practice has no Heartland link; net/pe stripped"),
    "ccd94a511fe6d32a": dict(net=None, pe=False, conf="medium",
        note="Aspen linkage refuted (real address is Dr. Neil Blumenthal, periodontist); net/pe stripped, conf capped medium"),
    "38d3d0a02dff7b6f": dict(net=None, pe=False,
        note="Aspen linkage refuted (Dr. Raino ties to Dental Experts LLC); net/pe stripped"),
    "9ff39651d697af30": dict(net=None, pe=False,
        note="GLDP linkage refuted (census practice is Comfort Family Dental at 2036 W 95th, not Beverly Smiles); net/pe stripped"),
    "29ded9c384c4e2e3": dict(pe=True,
        note="Specialized Dental Partners is Quad-C-backed per own verify note; pe_backed corrected to true"),
    "7542f13e98b7bd0d": dict(pe=True, net="ao:NITTINGER_RACHEL",
        note="DentalOne/Sonrava network is New Mountain Capital-backed per 11 ratified siblings; pe=true, slug aligned"),
    "c2ddefdc5cef6aa2": dict(tier="dentist_multi", net="brand:grand_dental_group", pe=False,
        note="folded into R4 PM ruling: Grand Dental Group is T3 dentist_multi (doctor-owned), not branded_dso"),
    "3f92a54ef4d70d13": dict(tier="branded_dso", net="brand:smile_obsession",
        note="folded into R4 PM ruling: Smile Obsession brand is patient-facing => T5 branded_dso"),
    "925b33f318557fe7": dict(tier="undetermined", status="undetermined",
        note="R5 closure adjudication: Streamwood office closed Jul 2025 (merged into Sutton Lake Dental); fail-closed, ownership-at-closure kept in reasoning"),
    "bca301b92b2ede41": dict(tier="undetermined", status="undetermined",
        note="R5 closure adjudication: MINT Northlake closed Oct 2025; fail-closed"),
    "2990d3b52d394795": dict(tier="undetermined", status="undetermined",
        note="R5 closure adjudication: Aspen Lockport consolidated into Joliet Apr 2026; fail-closed"),
    "fe4e8aece6d7fd2e": dict(net="decisionone_dental_partners",
        note="same practice as d3a0e2085a1e3776; DecisionOne membership confirmed, Smile Brands is upstream investor; unified"),
    "3ec3e5c611e518e7": dict(conf="medium",
        note="classic-PE sub-claim refuted; conf capped medium (Beringea VC backing stands)"),
    "9fe62bf8816a28c1": dict(owner=None,
        note="owner_identity was Aspen sitewide boilerplate (ADMI Chief Clinical Officer), nulled"),
}

data = json.load(open(MERGED))
rows = data["classifications"] if isinstance(data, dict) else data
by = {r["location_id"]: r for r in rows}

missing = [l for l in FIX if l not in by]
if missing:
    sys.exit(f"FATAL: not in file: {missing}")

def mark(r, note):
    if QMARK not in (r.get("reasoning") or ""):
        r["reasoning"] = (r.get("reasoning") or "").rstrip() + f" {QMARK}: {note}]"

fixed = 0
for lid, f in FIX.items():
    r = by[lid]
    if QMARK in (r.get("reasoning") or ""):
        continue
    if "tier" in f: r["assigned_tier"] = f["tier"]
    if "status" in f: r["status"] = f["status"]
    if "net" in f: r["network_id"] = f["net"]
    if "pe" in f: r["pe_backed"] = f["pe"]
    if "conf" in f: r["confidence"] = f["conf"]
    if "owner" in f: r["owner_identity"] = f["owner"]
    mark(r, f["note"])
    fixed += 1

# e45faab59b6a118f: scrub factually-wrong artifacts (ADA EIN, Roncevic), rest on locator match
r = by.get("e45faab59b6a118f")
if r and QMARK not in (r.get("reasoning") or ""):
    arts = r.get("evidence_artifacts") or []
    kept = [a for a in arts if "EIN" not in str(a) and "Roncevic" not in str(a).lower() and "roncevic" not in str(a)]
    dropped = len(arts) - len(kept)
    urls = [u for u in (r.get("evidence_urls") or []) if u]
    if dropped and not urls and not kept:
        print("WARN e45faab59b6a118f: would strand row without evidence; left untouched for manual review")
    elif dropped:
        r["evidence_artifacts"] = kept
        if r.get("evidence_basis") in {"ein_cluster", "ao_cluster", "name_chain", "structural"} and not kept:
            r["evidence_basis"] = "locator"
        mark(r, f"scrubbed {dropped} factually-wrong artifacts (ADA EIN / unconfirmed Roncevic tie); locator match carries the tier")
        fixed += 1

# Dentologie: pe_backed=true uniformly (PM decision: Beringea institutional growth capital counts)
dent_pe = 0
for r in rows:
    if (r.get("network_id") or "").replace("brand:", "") == "dentologie" and r.get("pe_backed") is not True:
        r["pe_backed"] = True
        mark(r, "PM decision: Beringea institutional backing => pe_backed=true uniformly across Dentologie")
        dent_pe += 1

# network_id on T1/T2 rows is a same-practice merge key, not a network -> null
t12 = 0
for r in rows:
    if r["assigned_tier"] in ("true_independent", "single_loc_group") and r.get("network_id"):
        old = r["network_id"]
        r["network_id"] = None
        mark(r, f"network_id '{old}' was a same-practice merge key, nulled (T1/T2 rows are not network members)")
        t12 += 1

# file-wide slug normalization
norm = 0
for r in rows:
    nid = r.get("network_id")
    if nid in NORM_MAP:
        r["network_id"] = NORM_MAP[nid]
        norm += 1

json.dump(data, open(MERGED, "w"), indent=1)
from collections import Counter
print(f"row_fixes={fixed} dentologie_pe={dent_pe} t12_net_nulled={t12} slugs_normalized={norm}")
print("tiers:", dict(Counter(r["assigned_tier"] for r in rows).most_common()))
print("status:", dict(Counter(r["status"] for r in rows).most_common()))
pe_true = [r["location_id"] for r in rows if r.get("pe_backed") is True]
print(f"pe_backed_true={len(pe_true)}")
nets = Counter(r["network_id"] for r in rows if r.get("network_id"))
print("network slugs:", dict(sorted(nets.items())))
