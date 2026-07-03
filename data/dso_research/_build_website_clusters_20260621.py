"""
Fleet B — Website-domain consolidator discovery + evidence QUEUE (validator-native).
READ-ONLY DB. NO DB writes. NO ledger/progress writes.

Signal: untiered IL watched GP locations that share a website DOMAIN across >=2 ZIPs.
A shared custom domain across differently-named offices is strong common-operator evidence
AND carries a real URL (web_verified, the strongest evidence class). But a domain is only
PROOF of common ownership when the member's OWN practice_name coheres with the brand —
otherwise it can be a shared marketing-template / scheduling-software / payer host. So:

  CLASSIFY (status=classified, basis=web_verified, evidence_urls=[domain]):
    * domain in DOMAIN_BRAND  AND member name carries the brand token -> branded_dso (+pe)
    * domain in DOMAIN_INSTITUTIONAL AND member name carries the system token -> institutional
    * novel custom domain, >=2 cohering members spanning >=2 ZIP, this member coheres -> dentist_multi
  HOLD (needs_verification + undetermined, domain kept as a strong lead URL):
    * brand/institutional domain but member name does NOT cohere (friendly-PC vs listing error)
    * novel domain that does not reach the cohering-group bar
    * landmine domain (evenly.com)
  EXCLUDE entirely (not an ownership signal):
    * aggregator / scheduling-software / directory / payer hosts (NOISE_DOMAINS)

Already-claimed sibling-queue lids are skipped to avoid collision/double-count.
"""
import json, os, sqlite3, re, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
CAND = os.path.join(DR, "website_consolidator_candidates_20260621.json")
OUT = os.path.join(DR, "ownership_evidence_queue_fleet_b_website_clusters_20260621.json")

# ---- curated maps -----------------------------------------------------------
# domain -> (brand, tier, pe_backed, name_tokens that must appear in member's own name)
DOMAIN_BRAND = {
    "aspendental.com":      ("Aspen Dental", "branded_dso", True,  ("ASPEN",)),
    "dentalworks.com":      ("DentalWorks (Dental Care Partners)", "branded_dso", True,  ("DENTALWORKS", "DENTAL WORKS", "DCP", "DENTIST IN")),
    "orlandsquare.dentalworks.com": ("DentalWorks (Dental Care Partners)", "branded_dso", True, ("DENTALWORKS", "DENTAL WORKS", "DCP", "DENTIST IN")),
    "midwest-dental.com":   ("Midwest Dental (Smile Brands)", "branded_dso", True,  ("MIDWEST",)),
    "dentaldreams.com":     ("Dental Dreams", "branded_dso", False, ("DENTAL DREAMS", "DREAM DENTAL", "DENTAL EXPERTS")),
    "1stfamilydental.com":  ("1st Family Dental", "branded_dso", False, ("1ST FAMILY", "FIRST FAMILY", "1FD")),
    "1fdimplants.com":      ("1st Family Dental", "branded_dso", False, ("1ST FAMILY", "FIRST FAMILY")),
    "dentalandbraces.com":  ("All Family Dental & Braces (United Dental Partners)", "branded_dso", True, ("ALL FAMILY", "ALL KIDS")),
    "familydentalcare.com": ("Family Dental Care", "branded_dso", False, ("FAMILY DENTAL CARE", "FAMILY DENTAL CENTER")),
    "britedental.org":      ("Brite Dental", "branded_dso", False, ("BRITE",)),
    "familiadental.com":    ("Familia Dental", "branded_dso", True,  ("FAMILIA",)),
    "destinydentalcare.com":("Destiny Dental / ProSmile", "branded_dso", True, ("DESTINY", "PROSMILE", "DENTINY")),
    "metrosmilesdental.com":("MetroSmiles Dental", "branded_dso", False, ("METROSMILES", "METRO KIDZ")),
    "grovedental.com":      ("Grove Dental Associates", "branded_dso", False, ("GROVE",)),
    "webdentalchicago.com": ("Webster Dental Care", "branded_dso", False, ("WEBSTER",)),
    "lincolnsquarefamilydentist.com": ("Webster Dental Care", "branded_dso", False, ("WEBSTER",)),
}
# health-system domains -> classify institutional only if member name carries the system token
DOMAIN_INSTITUTIONAL = {
    "doctors.advocatehealth.com": ("Advocate Health", ("ADVOCATE",)),
    "care.advocatehealth.com":    ("Advocate Health", ("ADVOCATE",)),
    "uchicagomedicine.org":       ("University of Chicago Medicine", ("UCHICAGO", "UNIVERSITY OF CHICAGO", "U CHICAGO")),
    "loyolamedicine.org":         ("Loyola Medicine", ("LOYOLA",)),
}
# aggregator / scheduling-software / directory / payer / national-specialist hosts — NOT ownership
NOISE_DOMAINS = {
    "findadentist.ada.org", "opencare.com", "dentistoffices.com", "atooth.com",
    "auroradentrix.com", "patientconnect365.com", "dentalinsider.com",
    "deltadentalil.com", "clearchoice.com",
}
LANDMINE_DOMAINS = {"evenly.com"}
BLOCK_EIN = {"363676741", "432052561", "322684113"}
GENERIC_DOMAIN_TOKENS = {"dental", "dentistry", "dentist", "smile", "smiles", "family",
                         "care", "center", "group", "associates", "clinic", "chicago",
                         "illinois", "the", "of", "and", "pc", "llc", "ltd", "studio",
                         "office", "offices", "best", "new", "advanced", "complete"}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

def upper(s): return (s or "").upper().strip()

def dom(u):
    if not u: return None
    u = str(u).lower().strip()
    m = re.search(r"https?://([^/]+)", u) or re.search(r"^([a-z0-9.-]+\.[a-z]{2,})", u)
    if not m: return None
    d = m.group(1)
    if d.startswith("www."): d = d[4:]
    if any(g in d for g in ("facebook", "google", "yelp", "healthgrades", "zocdoc",
                            "instagram", "linkedin", ".gov", "twitter", "youtube")):
        return None
    return d

def dom_tokens(d):
    """significant tokens of the registrable label (drop TLD + generic dental words)."""
    label = d.split(".")[0] if "." in d else d
    # split the second-level label into words by known dental tokens / camel-ish boundaries
    words = re.findall(r"[a-z]+", label)
    # also try to break long concatenations on generic anchors
    out = set()
    for w in words:
        if len(w) >= 4 and w not in GENERIC_DOMAIN_TOKENS:
            out.add(w)
    # whole label minus generic suffix words (e.g. "procaredentalgroup" -> "procare")
    lab = label
    for g in ("dentalgroup", "familydental", "dentalcare", "dentalclinic", "dentalstudio",
              "dentalcenter", "dental", "dentistry", "dentist", "smiles", "smile", "group",
              "care", "clinic", "studio", "chicago", "center", "associates"):
        if lab.endswith(g) and len(lab) > len(g) + 2:
            lab = lab[: -len(g)]; break
    if len(lab) >= 4 and lab not in GENERIC_DOMAIN_TOKENS:
        out.add(lab)
    return {t.upper() for t in out}

# ---- universe: untiered IL watched GP locations + website -------------------
EXCL = ("specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location")
rows = conn.execute(f"""
    SELECT pl.location_id, pl.practice_name, pl.city, pl.zip, pl.website, pl.ein,
           pl.parent_company, pl.entity_classification, pl.primary_npi, pl.org_npi
    FROM practice_locations pl
    JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5) AND wz.state='IL'
    WHERE pl.ownership_tier IS NULL
      AND pl.entity_classification NOT IN ({",".join("?"*len(EXCL))})""", EXCL).fetchall()

bydom = collections.defaultdict(list)
for r in rows:
    d = dom(r["website"])
    if d: bydom[d].append(r)
shared = {d: v for d, v in bydom.items() if len({x["zip"][:5] for x in v}) >= 2}

# ---- harvest claimed lids (all sibling queues incl. local_clusters + AO) ------
claimed = set()
def walk(o):
    if isinstance(o, dict):
        v = o.get("location_id")
        if isinstance(v, str): claimed.add(v)
        for x in o.values(): walk(x)
    elif isinstance(o, list):
        for x in o: walk(x)
for fn in ["ownership_evidence_queue_fleet_b_20260621.json",
           "ownership_evidence_queue_fleet_b_lane3_20260621.json",
           "ownership_evidence_queue_fleet_b_backfill_20260621.json",
           "ownership_evidence_queue_fleet_b_lane1B_20260621.json",
           "ownership_evidence_queue_fleet_b_local_clusters_20260621.json",
           "ao_network_evidence_20260621.json",
           "ao_network_evidence_reach4_20260621.json",
           "ao_network_evidence_reach5_20260621.json"]:
    p = os.path.join(DR, fn)
    if os.path.exists(p):
        try: walk(json.load(open(p)))
        except Exception as e: print("warn", fn, e)
print(f"claimed lids across sibling queues: {len(claimed)}")

def is_da(r): return str(r["primary_npi"] or "").startswith("DA_") or str(r["org_npi"] or "").startswith("DA_")

# ---- pre-compute novel-domain cohesion --------------------------------------
def cohering_token(name, tokens):
    nm = upper(name)
    return next((t for t in tokens if t in nm), None)

novel_group = {}   # domain -> {"tokens":set, "cohere_zips":set, "n_cohere":int}
for d, members in shared.items():
    if d in DOMAIN_BRAND or d in DOMAIN_INSTITUTIONAL or d in NOISE_DOMAINS or d in LANDMINE_DOMAINS:
        continue
    toks = dom_tokens(d)
    if not toks: continue
    czips, ncoh = set(), 0
    for r in members:
        if cohering_token(r["practice_name"], toks):
            ncoh += 1; czips.add(r["zip"][:5])
    novel_group[d] = {"tokens": toks, "cohere_zips": czips, "n_cohere": ncoh}

# ---- classify ---------------------------------------------------------------
def classify(r, d):
    name = r["practice_name"]; ein = (r["ein"] or "").strip()
    if d in LANDMINE_DOMAINS:
        return ("needs_verification", "undetermined", "none", "low", False, None,
                f"Shares landmine domain {d} (Evenly placeholder) — HELD.",
                ["confirm real operating ownership; Evenly domain is a placeholder signal"])
    if ein in BLOCK_EIN:
        return ("needs_verification", "undetermined", "none", "low", False, None,
                f"EIN {ein} on landmine blocklist; domain {d} held as lead.",
                ["independent ownership verification — EIN flagged non-chain"])
    if d in DOMAIN_BRAND:
        brand, tier, pe, tokens = DOMAIN_BRAND[d]
        hit = cohering_token(name, tokens)
        if hit:
            return ("classified", tier, "web_verified", "medium", pe, brand,
                    f"Office's own website domain '{d}' is the {brand} brand site AND the office's "
                    f"own name carries the '{hit}' brand token — documentary brand site + name agree.",
                    [])
        return ("needs_verification", "undetermined", "none", "low", False, brand,
                f"Office lists brand website '{d}' ({brand}) but its OWN name ('{name}') does not "
                f"carry the brand token — likely friendly-PC or a listing artifact. HIGH-VALUE lead.",
                [f"confirm office operates under {brand} (friendly-PC) vs. website-listing error"])
    if d in DOMAIN_INSTITUTIONAL:
        system, tokens = DOMAIN_INSTITUTIONAL[d]
        hit = cohering_token(name, tokens)
        if hit:
            return ("classified", "institutional", "web_verified", "medium", False, system,
                    f"Office's own website is the {system} health-system domain '{d}' AND its name "
                    f"carries the '{hit}' system token — hospital/health-system owned.", [])
        return ("needs_verification", "undetermined", "none", "low", False, system,
                f"Office lists health-system domain '{d}' ({system}) but its OWN name ('{name}') does "
                f"not carry the system token — likely a referral listing, not ownership. Lead.",
                [f"confirm {system} ownership vs. referral-directory listing"])
    # novel custom domain
    ng = novel_group.get(d)
    if ng:
        hit = cohering_token(name, ng["tokens"])
        if hit and ng["n_cohere"] >= 2 and len(ng["cohere_zips"]) >= 2:
            return ("classified", "dentist_multi", "web_verified", "medium", False, None,
                    f"Shares custom website domain '{d}' across {len(ng['cohere_zips'])} ZIPs with "
                    f"{ng['n_cohere']} same-brand offices (name token '{hit}'), no DSO/MSO/PE signal — "
                    f"dentist-owned multi-location group.",
                    ["confirm no hidden MSO/platform; confirm dentist ownership"])
        # on the domain but not a cohering multi-brand group member
        return ("needs_verification", "undetermined", "none", "low", False, None,
                f"Shares website domain '{d}' (group has {ng['n_cohere']} cohering offices over "
                f"{len(ng['cohere_zips'])} ZIPs) but this office's name does not cohere — verify "
                f"common ownership vs. shared marketing/host. Lead.",
                ["confirm common ownership vs. shared marketing-template / hosting domain"])
    return ("needs_verification", "undetermined", "none", "low", False, None,
            f"Shares website domain '{d}' across >=2 ZIPs — verify common ownership.",
            ["confirm common ownership vs. shared marketing/host domain"])

# ---- build candidate file + queue -------------------------------------------
candidates, queue, qa_flags = [], [], []
skip = collections.Counter()
for d in sorted(shared, key=lambda d: -len(shared[d])):
    members = shared[d]
    nz = len({x["zip"][:5] for x in members})
    if d in NOISE_DOMAINS:
        skip["noise_domain_excluded"] += len(members);
        candidates.append({"domain": d, "disposition": "EXCLUDED_noise_host", "n_locations": len(members),
                           "n_zips": nz, "members": [{"location_id": r["location_id"],
                           "practice_name": r["practice_name"], "zip": r["zip"]} for r in members]})
        continue
    kind = ("landmine" if d in LANDMINE_DOMAINS else "known_dso" if d in DOMAIN_BRAND
            else "institutional" if d in DOMAIN_INSTITUTIONAL else "novel_custom")
    cand_members = []
    for r in members:
        new = not (r["location_id"] in claimed or is_da(r))
        cand_members.append({"location_id": r["location_id"], "practice_name": r["practice_name"],
                             "zip": r["zip"], "city": r["city"], "new_unclaimed": new,
                             "entity_classification": r["entity_classification"],
                             "parent_company": r["parent_company"], "ein": r["ein"]})
    ng_c = novel_group.get(d)
    ng_ser = ({"tokens": sorted(ng_c["tokens"]), "cohere_zips": sorted(ng_c["cohere_zips"]),
               "n_cohere": ng_c["n_cohere"]} if ng_c else None)
    candidates.append({"domain": d, "disposition": kind, "n_locations": len(members), "n_zips": nz,
                       "brand": (DOMAIN_BRAND.get(d) or DOMAIN_INSTITUTIONAL.get(d) or [None])[0],
                       "novel_cohesion": ng_ser, "members": cand_members})
    for r in members:
        if is_da(r): skip["da_synthetic"] += 1; continue
        if r["location_id"] in claimed: skip["already_claimed"] += 1; continue
        status, tier, basis, conf, pe, brand, why, missing = classify(r, d)
        url = [f"https://{d}"]
        row = {
            "location_id": r["location_id"], "assigned_tier": tier, "evidence_basis": basis,
            "confidence": conf, "status": status, "reasoning": why,
            "evidence_urls": url if basis == "web_verified" else url,  # domain kept as lead either way
            "evidence_artifacts": [f"shared_website_domain={d}", f"domain_zips={nz}",
                                   f"domain_locations={len(members)}"],
            "pe_backed": bool(pe),
            "practice_name": r["practice_name"], "city": r["city"], "zip": r["zip"],
            "current_entity_classification": r["entity_classification"],
            "shared_domain": d, "brands": [brand] if brand else None,
            "missing_evidence": missing,
            "lane": "website_clusters", "session": "fleet-b-website-clusters-2026-06-21",
            "reviewed_at": "2026-06-21",
        }
        # defense-in-depth validator hygiene
        if status == "classified":
            bad = None
            if is_da(r): bad = "da_synthetic_npi"
            elif conf == "low": bad = "low_confidence"
            elif basis == "none": bad = "basis_none"
            elif basis == "web_verified" and not row["evidence_urls"]: bad = "url_basis_without_url"
            elif tier in ("stealth_dso", "branded_dso") and not (row["evidence_urls"] or row["evidence_artifacts"]):
                bad = "dso_tier_no_evidence"
            if bad:
                qa_flags.append({"location_id": r["location_id"], "practice_name": r["practice_name"],
                                 "flag": f"classify_demoted:{bad}", "would_be_tier": tier})
                row.update({"status": "needs_verification", "assigned_tier": "undetermined",
                            "evidence_basis": "none", "confidence": "low"})
        queue.append(row)

by_status = collections.Counter(r["status"] for r in queue)
by_tier = collections.Counter(r["assigned_tier"] for r in queue if r["status"] == "classified")
meta = {
    "lane": "website_clusters", "session": "fleet-b-website-clusters-2026-06-21",
    "generated": "2026-06-21", "db_mode": "read_only", "total_rows": len(queue),
    "by_status": dict(by_status), "classified_by_tier": dict(by_tier),
    "skipped": dict(skip), "qa_flag_count": len(qa_flags), "_qa_flags": qa_flags,
    "shared_domains_seen": len(shared), "noise_domains_excluded": sorted(NOISE_DOMAINS),
    "landmine_domains": sorted(LANDMINE_DOMAINS),
    "note": "Evidence-only, ready_for_validation, NEVER final. No DB writes. Classified rows are "
            "web_verified by the office's OWN website domain + name cohesion (brand site, health-system "
            "site, or custom multi-ZIP group). Brand/host domain without name cohesion is a LEAD held "
            "needs_verification. Aggregator/software/payer hosts excluded; evenly.com landmine held.",
}
json.dump({"_meta": {"generated": "2026-06-21", "lane": "website_clusters",
                     "shared_domains": len(shared)}, "candidates": candidates},
          open(CAND, "w"), indent=1)
json.dump({"classifications": queue, "_meta": meta}, open(OUT, "w"), indent=1)
print(f"shared domains (>=2 ZIP): {len(shared)} | queue rows: {len(queue)} | skipped: {dict(skip)}")
print("by_status:", dict(by_status), "| classified_by_tier:", dict(by_tier))
print(f"wrote {CAND}\nwrote {OUT}")
print("\nclassified examples:")
for r in queue:
    if r["status"] == "classified":
        print(f"  {r['practice_name'][:28]:28} {r['zip']} -> {r['assigned_tier']:13} pe={r['pe_backed']} "
              f"{r['shared_domain'][:26]:26} {(r['brands'] or [''])[0][:24]}")
