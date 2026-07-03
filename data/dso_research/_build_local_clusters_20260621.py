"""
Fleet B — Local Brand / EIN / Intel Cluster discovery.  READ-ONLY on the DB.
Hunts HIDDEN LOCAL CONSOLIDATORS: dentist/family networks, friendly-PC shells,
MSO/platform operators, PE-backed DSOs, local brands that don't look corporate.

Builds TWO artifacts (NO DB writes, NO ledger/progress writes):
  1) local_consolidator_cluster_candidates_20260621.json   (network-level intelligence)
  2) ownership_evidence_queue_fleet_b_local_clusters_20260621.json (location-level,
     validator-native; ONLY artifact/URL-backed rows classified, rest needs_verification)

Cluster types:
  ein_cluster            same EIN across >=2 distinct ZIP5
  parent_company_chain   same parent_company across >=2 distinct ZIP5
  affiliated_dso_chain   same known DSO brand across >=2 distinct ZIP5 (context)
  brand_chain            same normalized practice/dba brand across >=3 distinct ZIP5
  phone_cluster          shared phone across >=2 distinct addresses spanning >=2 ZIP5
  ao_cluster             same authorized official across >=3 distinct ZIP5 (NOT Main-claimed)
  intel_keyword          practice_intel prose with acq/merger/MSO/platform/parent language
  dso_regional_review    dso_regional locations that may be dentist/family-owned
  lane1B_held_lead       the 22 unresolved stealth/branded leads from Lane 1B QA flags
"""
import json, glob, os, re, sqlite3, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
CAND = os.path.join(DR, "local_consolidator_cluster_candidates_20260621.json")

EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}
BADV = {"", "nan", "none", "null", "n/a", "na"}
BAD_EIN = {"000000000", "0", "00000000", "999999999", "111111111"}

# Known DSO/PE platform brands -> branded; helps tier EIN/parent chains.
KNOWN_DSO = {
    "heartland", "aspen", "admi", "pacific dental", "pds", "smile brands", "dental dreams",
    "dental experts", "western dental", "sonrava", "great lakes dental", "1st family",
    "first family", "midwest dental", "smile doctors", "myortho", "gentle dental",
    "dental 360", "all family dental", "united dental partners", "udp", "webster dental",
    "kos services", "choice dental", "orthodontic experts", "dentalworks", "dentalone",
    "decisionone", "decision one", "procare", "grand dental", "evenly", "sonrisa", "cdca",
    "north american dental", "nadg", "deca", "dececco", "dcA", "dca", "imagine dental",
    "advanced family dental", "elite dental", "bright", "brite",
}
# Known PE sponsor strings (parent_company / affiliated_pe_sponsor) -> pe_backed
KNOWN_PE = {
    "gryphon", "shore capital", "berkshire partners", "leonard green", "ares",
    "kkr", "thomas h lee", "thl", "jacobs holding", "morgan stanley", "warburg",
    "harvest partners", "new mountain", "incline", "jll partners", "jll",
    "blackstone", "audax", "bregal", "calera",
}

# Main-claimed AO networks (wave-1 + reach5) — leave to Main, only flag as already-claimed.
MAIN_AO = {
    ("sohail", "shafi"), ("vesna", "belkic"), ("rachel", "nittinger"), ("fadi", "aqel"),
    ("robert", "brunetti"), ("jubrail", "sweis"), ("boris", "labinov"), ("ahmed", "ramaha"),
    ("celia", "hayes"), ("alan", "acierno"), ("jay", "jorbin"), ("david", "rubis"),
    ("", "gonzalez"), ("", "nourahmadi"), ("", "tsaliagos"), ("", "korkus"),
    ("", "khurana"), ("", "palella"), ("", "chang"), ("sameera", "hussain"),
    ("rajan", "sharma"), ("milan", "roncevic"),
}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

def clean(v):
    s = str(v or "").strip()
    return "" if s.lower() in BADV else s

def is_da(v): return str(v or "").startswith("DA_")

# ---- exclusion / already-claimed lids from sibling Fleet B queues ----------
CLAIMED = {}  # lid -> source file
def harvest_lids(path, tag):
    if not os.path.exists(path): return
    try: d = json.load(open(path))
    except Exception: return
    def walk(o):
        if isinstance(o, dict):
            lid = o.get("location_id")
            if isinstance(lid, str): CLAIMED.setdefault(lid, tag)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(d)

for fn, tag in [
    ("ownership_evidence_queue_fleet_b_20260621.json", "wave1"),
    ("ownership_evidence_queue_fleet_b_lane3_20260621.json", "lane3"),
    ("ownership_evidence_queue_fleet_b_backfill_20260621.json", "backfill"),
    ("ownership_evidence_queue_fleet_b_lane1B_20260621.json", "lane1B"),
    ("ao_network_evidence_20260621.json", "main_ao"),
    ("ao_network_evidence_reach4_20260621.json", "main_reach4"),
    ("ao_network_evidence_reach5_20260621.json", "main_reach5"),
    ("_exclusion_set_fleet_b_20260621.json", "exclusion_set"),
]:
    harvest_lids(os.path.join(DR, fn), tag)
print(f"already-claimed lids harvested: {len(CLAIMED)}")

# ---- location universe (IL watched, GP, untiered) --------------------------
LOC = {}
for r in conn.execute("""
    SELECT pl.location_id, pl.practice_name, pl.doing_business_as, pl.city, pl.zip, pl.state,
           pl.normalized_address, pl.entity_classification, pl.ownership_tier,
           pl.primary_npi, pl.org_npi, pl.provider_npis,
           pl.ein, pl.parent_company, pl.affiliated_dso, pl.affiliated_pe_sponsor,
           pl.phone, pl.website
    FROM practice_locations pl
    JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5) AND wz.state='IL'
"""):
    LOC[r["location_id"]] = dict(r)
print(f"IL watched locations: {len(LOC)}")

def z5(z): return (z or "")[:5]
def gp_ok(l):
    return (l["entity_classification"] not in EXCLUDED_GP_CLASSES
            and not l["ownership_tier"]
            and not (is_da(l["primary_npi"]) and is_da(l["org_npi"])))

def npis_of(l):
    raw = set()
    for k in ("primary_npi", "org_npi", "provider_npis"):
        if l.get(k): raw |= set(re.findall(r"\d{10}", str(l[k])))
    return sorted(n for n in raw if not is_da(n))

# ---- brand normalization ----------------------------------------------------
DROP = {"LLC","LLP","LTD","PC","PLLC","INC","PA","SC","DDS","DMD","MD","DR","DRS","AND",
        "OF","THE","OFFICE","OFFICES","ASSOCIATES","ASSOC","ASSOCIATION","CO","CORP",
        "GROUP","FAMILY","GENERAL","COSMETIC","CENTER","CENTERS","CARE","PROF","PROFESSIONAL",
        "DENTAL","DENTISTRY","DENTIST","DENTISTS","DENTAL CARE"}
# placeholder/junk brand tokens that must never anchor a chain
PLACEHOLDER = {"UNAVAIL","UNAVAILABLE","UNKNOWN","NONE","NULL","NAME","NA","PRACTICE",
               "DENTAL","DENTISTRY","DENTIST","SMILE","SMILES","TOOTH","TEETH","HEALTH"}
def brand_key(name, dba=""):
    s = (dba or name or "").upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in DROP and len(t) > 1 and not t.isdigit()]
    bk = " ".join(toks)
    # reject placeholder-only or single generic token keys
    if not bk or all(t in PLACEHOLDER for t in toks): return ""
    if len(toks) == 1 and (toks[0] in PLACEHOLDER or len(toks[0]) < 5): return ""
    return bk

# ============================================================================
# Build clusters
# ============================================================================
clusters = []          # list of cluster dicts
member_to_clusters = collections.defaultdict(list)  # lid -> [cluster_id...]
cid = 0
def new_cid(kind):
    global cid; cid += 1
    return f"{kind}-{cid:03d}"

def has_known(s, table):
    s = (s or "").lower()
    return next((b for b in table if b and b in s), None)

# ---- 1. EIN clusters (location-level, >=2 ZIP5) ----------------------------
ein_groups = collections.defaultdict(list)
for lid, l in LOC.items():
    e = clean(l["ein"])
    if e and e not in BAD_EIN and len(e) >= 9 and gp_ok(l):
        ein_groups[e].append(lid)
for ein, lids in ein_groups.items():
    zips = {z5(LOC[x]["zip"]) for x in lids}
    if len(zips) < 2: continue
    classes = collections.Counter(LOC[x]["entity_classification"] for x in lids)
    corp_members = sum(classes[k] for k in ("dso_national", "dso_regional"))
    dso_hit = next((has_known(LOC[x]["affiliated_dso"], KNOWN_DSO)
                    or has_known(LOC[x]["parent_company"], KNOWN_DSO) for x in lids
                    if has_known(LOC[x]["affiliated_dso"], KNOWN_DSO)
                    or has_known(LOC[x]["parent_company"], KNOWN_DSO)), None)
    cidv = new_cid("ein")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "ein_cluster",
        "key": ein, "n_locations": len(lids), "n_zips": len(zips),
        "linked_location_ids": lids, "corp_members": corp_members,
        "known_dso_hint": dso_hit, "class_mix": dict(classes),
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 2. parent_company chains (>=2 ZIP5) -----------------------------------
pc_groups = collections.defaultdict(list)
for lid, l in LOC.items():
    pc = clean(l["parent_company"])
    if pc and gp_ok(l): pc_groups[pc.upper()].append(lid)
for pc, lids in pc_groups.items():
    zips = {z5(LOC[x]["zip"]) for x in lids}
    if len(zips) < 2: continue
    cidv = new_cid("parent")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "parent_company_chain",
        "key": pc, "n_locations": len(lids), "n_zips": len(zips),
        "linked_location_ids": lids,
        "known_dso_hint": has_known(pc, KNOWN_DSO),
        "known_pe_hint": has_known(pc, KNOWN_PE),
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 3. affiliated_dso chains (>=2 ZIP5) -----------------------------------
ad_groups = collections.defaultdict(list)
for lid, l in LOC.items():
    ad = clean(l["affiliated_dso"])
    if ad and gp_ok(l): ad_groups[ad].append(lid)
for ad, lids in ad_groups.items():
    zips = {z5(LOC[x]["zip"]) for x in lids}
    if len(zips) < 2: continue
    cidv = new_cid("dso")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "affiliated_dso_chain",
        "key": ad, "n_locations": len(lids), "n_zips": len(zips),
        "linked_location_ids": lids,
        "known_dso_hint": has_known(ad, KNOWN_DSO) or ad,
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 4. brand chains (normalized name/dba, >=3 ZIP5) -----------------------
brand_groups = collections.defaultdict(list)
for lid, l in LOC.items():
    if not gp_ok(l): continue
    bk = brand_key(l["practice_name"], l["doing_business_as"])
    if len(bk.split()) >= 1 and "DENTAL" not in bk.split() and len(bk) >= 4:
        # keep distinctive multi-token OR single distinctive token
        pass
    if bk and len(bk) >= 4: brand_groups[bk].append(lid)
for bk, lids in brand_groups.items():
    zips = {z5(LOC[x]["zip"]) for x in lids}
    if len(zips) < 3: continue
    if len(set(bk.split())) == 1 and bk in {"SMILE","SMILES","TOOTH","TEETH"}: continue
    cidv = new_cid("brand")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "brand_chain",
        "key": bk, "n_locations": len(lids), "n_zips": len(zips),
        "linked_location_ids": lids,
        "known_dso_hint": has_known(bk, KNOWN_DSO),
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 5. phone clusters (shared phone, >=2 addresses, >=2 ZIP5) -------------
def norm_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""
ph_groups = collections.defaultdict(set)
for lid, l in LOC.items():
    if not gp_ok(l): continue
    ph = norm_phone(l["phone"])
    if ph: ph_groups[ph].add(lid)
for ph, lidset in ph_groups.items():
    lids = sorted(lidset)
    addrs = {LOC[x]["normalized_address"] for x in lids}
    zips = {z5(LOC[x]["zip"]) for x in lids}
    if len(addrs) < 2 or len(zips) < 2: continue
    cidv = new_cid("phone")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "phone_cluster",
        "key": ph, "n_locations": len(lids), "n_zips": len(zips),
        "linked_location_ids": lids,
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 6. AO clusters (authorized official across >=3 ZIP5; map to locations) -
# Build AO -> watched-IL addresses from practices, then map addresses to LOC by normalized_address+zip5.
addr_index = collections.defaultdict(list)  # (norm_addr_core, z5) -> [lid]
def addr_core(a):
    a = (a or "").upper()
    a = re.sub(r"[^A-Z0-9 ]", " ", a)
    a = re.sub(r"\b(SUITE|STE|UNIT|APT|FL|FLOOR|#|NO|BLDG|DEPT)\b.*$", "", a)
    return " ".join(a.split())
for lid, l in LOC.items():
    addr_index[(addr_core(l["normalized_address"]), z5(l["zip"]))].append(lid)

ao_rows = conn.execute("""
    SELECT p.authorized_official_first_name fn, p.authorized_official_last_name ln,
           p.address, p.zip, p.practice_name
    FROM practices p JOIN watched_zips wz ON wz.zip_code = substr(p.zip,1,5) AND wz.state='IL'
    WHERE p.authorized_official_last_name IS NOT NULL AND TRIM(p.authorized_official_last_name)!=''
""").fetchall()
ao_addr = collections.defaultdict(set)
for r in ao_rows:
    fn = (r["fn"] or "").strip().lower(); ln = (r["ln"] or "").strip().lower()
    if not ln: continue
    ao_addr[(fn, ln)].add((addr_core(r["address"]), z5(r["zip"]), r["practice_name"]))
for (fn, ln), addrset in ao_addr.items():
    zips = {a[1] for a in addrset}
    if len(zips) < 3: continue
    if (fn, ln) in MAIN_AO or ("", ln) in MAIN_AO:
        main_claimed = True
    else:
        main_claimed = False
    # map to our locations
    lids = []
    for (ac, z, _nm) in addrset:
        lids.extend(member for member in addr_index.get((ac, z), []))
    lids = sorted(set(x for x in lids if gp_ok(LOC[x])))
    cidv = new_cid("ao")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "ao_cluster",
        "key": f"{fn} {ln}".strip(), "n_locations": len(lids),
        "n_zips": len(zips), "ao_addr_reach": len(addrset),
        "linked_location_ids": lids, "main_claimed": main_claimed,
        "addresses": sorted([{"addr": a[0], "zip": a[1], "name": a[2]} for a in addrset],
                            key=lambda d: d["zip"])[:12],
    })
    for x in lids: member_to_clusters[x].append(cidv)

# ---- 7. intel keyword hits (HIGH-SIGNAL ownership-transition language only) --
# Tightened to avoid generic "group practice"/"DSO industry" noise. We want
# documentary signals that THIS practice changed/holds corporate ownership.
KW = re.compile(
    r"(acquir(ed|es|ing|ition)\b|\bwas acquired\b|has acquired\b|\bmerg(ed|er)\b|"
    r"joined (the )?[A-Z][\w&' ]{2,40}(group|dental|partners|network|dso)|"
    r"management services organization|\bMSO\b|private equity|\bPE[- ]backed\b|"
    r"backed by [A-Z]|parent (company|organization)|portfolio company|"
    r"roll[- ]?up|consolidat(ed|ing|ion) (by|under)|"
    r"(owned|operated|managed) by [A-Z][\w&' ]{2,40}(LLC|LLP|Inc|Group|Partners|Management|Holdings|DSO)|"
    r"DSO[- ]affiliated|affiliated with [A-Z][\w&' ]{2,40}(Dental|DSO|Partners|Group|Management))",
    re.I)
STRONG = True  # require acquisition_found OR a tightened-regex match
TEXT_COLS = ("overall_assessment", "acquisition_details", "red_flags", "green_flags",
             "website_analysis", "provider_notes", "escalation_findings", "doctor_notes",
             "services_note", "insurance_note")
# npi -> lid via address index of practices
npi_to_lid = {}
for lid, l in LOC.items():
    for n in npis_of(l): npi_to_lid[n] = lid
intel_hits = []
for r in conn.execute(f"SELECT npi, acquisition_found, {','.join(TEXT_COLS)} FROM practice_intel"):
    d = dict(r); npi = d["npi"]
    lid = npi_to_lid.get(npi)
    if not lid or not gp_ok(LOC[lid]): continue
    blob = " || ".join(str(d[c]) for c in TEXT_COLS if d.get(c))
    matches = [m.group(0).strip() for m in KW.finditer(blob)]
    if d.get("acquisition_found") or matches:
        snip = ""
        for c in TEXT_COLS:
            if d.get(c) and KW.search(str(d[c])):
                m = KW.search(str(d[c])); s = max(0, m.start()-60)
                snip = str(d[c])[s:m.end()+90]; break
        intel_hits.append({"location_id": lid, "npi": npi,
                           "acquisition_found": bool(d.get("acquisition_found")),
                           "keywords": sorted(set(x.lower() for x in matches))[:8],
                           "snippet": snip[:240]})
# group intel hits as one cluster type entry per location
seen_intel = set()
for h in intel_hits:
    if h["location_id"] in seen_intel: continue
    seen_intel.add(h["location_id"])
    cidv = new_cid("intel")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "intel_keyword",
        "key": LOC[h["location_id"]]["practice_name"], "n_locations": 1,
        "n_zips": 1, "linked_location_ids": [h["location_id"]],
        "intel": [x for x in intel_hits if x["location_id"] == h["location_id"]],
    })
    member_to_clusters[h["location_id"]].append(cidv)

# ---- 8. dso_regional review (maybe dentist/family-owned) -------------------
for lid, l in LOC.items():
    if l["entity_classification"] != "dso_regional" or not gp_ok(l): continue
    # only flag those NOT obviously a known national brand
    known = has_known(l["affiliated_dso"], KNOWN_DSO) or has_known(l["parent_company"], KNOWN_DSO)
    cidv = new_cid("dsoreg")
    clusters.append({
        "cluster_id": cidv, "candidate_type": "dso_regional_review",
        "key": l["practice_name"], "n_locations": 1, "n_zips": 1,
        "linked_location_ids": [lid], "known_dso_hint": known,
        "affiliated_dso": clean(l["affiliated_dso"]),
        "parent_company": clean(l["parent_company"]),
    })
    member_to_clusters[lid].append(cidv)

# ---- 9. Lane1B held stealth/branded leads ----------------------------------
qaf = os.path.join(DR, "ownership_evidence_queue_fleet_b_lane1B_qa_flags_20260621.json")
if os.path.exists(qaf):
    for lead in json.load(open(qaf)).get("held_stealth_branded_leads", []):
        lid = lead.get("location_id")
        if lid not in LOC: continue
        cidv = new_cid("l1bhold")
        clusters.append({
            "cluster_id": cidv, "candidate_type": "lane1B_held_lead",
            "key": lead.get("practice_name"), "n_locations": 1, "n_zips": 1,
            "linked_location_ids": [lid],
            "proposed_tier_raw": lead.get("proposed_tier_raw"),
            "lane1B_reasoning": lead.get("reasoning"),
        })
        member_to_clusters[lid].append(cidv)

print(f"raw clusters built: {len(clusters)}")
by_type = collections.Counter(c["candidate_type"] for c in clusters)
print("by type:", dict(by_type))

# ============================================================================
# Enrich each cluster with member detail + owner/operator + suspected tier
# ============================================================================
def member_detail(lid):
    l = LOC[lid]
    npis = npis_of(l)
    own = []
    if npis:
        qm = ",".join("?" * len(npis))
        for p in conn.execute(f"""SELECT npi, da_legal_name, parent_org_lbn, franchise_name,
              authorized_official_first_name fn, authorized_official_last_name ln,
              authorized_official_title title FROM practices WHERE npi IN ({qm})""", npis):
            d = {k: clean(p[k]) for k in p.keys()}
            if any(d.values()): own.append(d)
    return {
        "location_id": lid, "practice_name": l["practice_name"],
        "dba": clean(l["doing_business_as"]), "city": l["city"], "zip": l["zip"],
        "address": l["normalized_address"], "entity_classification": l["entity_classification"],
        "ein": clean(l["ein"]), "parent_company": clean(l["parent_company"]),
        "affiliated_dso": clean(l["affiliated_dso"]), "phone": clean(l["phone"]),
        "website": clean(l["website"]),
        "already_claimed_by": CLAIMED.get(lid),
        "officials": own,
    }

def suspect_tier(c, members):
    kd = c.get("known_dso_hint")
    pe = c.get("known_pe_hint") or any(has_known(m.get("parent_company"), KNOWN_PE) for m in members)
    t = c["candidate_type"]
    if t == "affiliated_dso_chain" and kd:
        return ("branded_dso", "medium")
    if t == "parent_company_chain":
        if kd: return ("branded_dso", "medium")
        if pe: return ("branded_dso", "medium")
        return ("stealth_dso", "low")        # named parent co but unknown brand
    if t == "ein_cluster":
        if kd: return ("branded_dso", "medium")
        if c["n_zips"] >= 3 or c.get("corp_members"): return ("stealth_dso", "low")
        return ("dentist_multi", "low")
    if t == "brand_chain":
        if kd: return ("branded_dso", "low")
        return ("dentist_multi", "low")
    if t == "phone_cluster":
        return ("dentist_multi", "low")
    if t == "ao_cluster":
        return ("dentist_multi", "low")
    if t == "intel_keyword":
        return ("undetermined", "low")
    if t == "dso_regional_review":
        return ("undetermined", "low")
    if t == "lane1B_held_lead":
        return (c.get("proposed_tier_raw") or "undetermined", "low")
    return ("undetermined", "low")

ranked = []
for c in clusters:
    members = [member_detail(x) for x in c["linked_location_ids"]]
    tier, conf = suspect_tier(c, members)
    # owner/operator/family inference
    fams = collections.Counter()
    ops = collections.Counter()
    legals = set()
    for m in members:
        for o in m["officials"]:
            if o.get("ln"): fams[o["ln"].title()] += 1
            nm = f"{o.get('fn','').title()} {o.get('ln','').title()}".strip()
            if nm: ops[nm] += 1
            for k in ("da_legal_name", "parent_org_lbn", "franchise_name"):
                if o.get(k): legals.add(o[k])
        if m.get("parent_company"): legals.add(m["parent_company"])
    claimed_n = sum(1 for m in members if m["already_claimed_by"])
    artifacts = []
    if c["candidate_type"] == "ein_cluster": artifacts.append(f"shared_EIN={c['key']}")
    if c["candidate_type"] == "parent_company_chain": artifacts.append(f"parent_company={c['key']}")
    if c["candidate_type"] == "affiliated_dso_chain": artifacts.append(f"affiliated_dso={c['key']}")
    if c["candidate_type"] == "phone_cluster": artifacts.append(f"shared_phone={c['key']}")
    if c["candidate_type"] == "brand_chain": artifacts.append(f"shared_brand_key={c['key']}")
    if c["candidate_type"] == "ao_cluster": artifacts.append(f"authorized_official={c['key']} reach={c.get('ao_addr_reach')}")
    # score: prioritize multi-zip non-already-known hidden consolidators.
    # Hard-artifact types (ein/parent/phone) outrank weak-lead types (brand/ao surname coincidence).
    novelty = 1.0 if not c.get("known_dso_hint") else 0.4
    TYPE_W = {"ein_cluster": 3.0, "parent_company_chain": 2.5, "phone_cluster": 2.0,
              "affiliated_dso_chain": 1.5, "ao_cluster": 1.0, "intel_keyword": 1.2,
              "dso_regional_review": 1.0, "lane1B_held_lead": 1.3, "brand_chain": 0.5}
    base = c["n_zips"] * 2 + c["n_locations"] + (3 if c.get("known_pe_hint") else 0)
    score = base * novelty * TYPE_W.get(c["candidate_type"], 1.0)
    if c.get("main_claimed"): score *= 0.1   # Main owns these AO networks
    if claimed_n and claimed_n == len(members): score *= 0.3  # fully already-covered
    score = round(score, 2)
    missing = []
    if tier in ("stealth_dso", "branded_dso") and c["candidate_type"] not in ("ein_cluster","parent_company_chain","affiliated_dso_chain"):
        missing.append("documentary locator/web URL confirming DSO/MSO structure")
    if c["candidate_type"] == "ao_cluster":
        missing.append("confirm single owner vs. coincidental same-name; corporate-structure doc")
    if c["candidate_type"] == "brand_chain":
        missing.append("confirm same ownership vs. coincidental same brand words; website/locator")
    if not legals and tier != "true_independent":
        missing.append("legal entity / parent confirmation")
    ranked.append({
        "cluster_id": c["cluster_id"], "candidate_type": c["candidate_type"],
        "key": c["key"], "n_locations": c["n_locations"], "n_zips": c["n_zips"],
        "score": score, "novel_vs_known_dso": not bool(c.get("known_dso_hint")),
        "known_dso_hint": c.get("known_dso_hint"), "known_pe_hint": c.get("known_pe_hint"),
        "main_claimed": c.get("main_claimed", False),
        "already_claimed_member_count": claimed_n,
        "suspected_tier": tier, "confidence": conf,
        "suspected_owner_operator": [n for n, _ in ops.most_common(5)],
        "suspected_family_surnames": [f for f, n in fams.most_common(5) if n >= 2] or [f for f, _ in fams.most_common(3)],
        "legal_entities": sorted(legals)[:8],
        "evidence_artifacts": artifacts,
        "linked_location_ids": c["linked_location_ids"],
        "members": members,
        "intel": c.get("intel"),
        "addresses": c.get("addresses"),
        "class_mix": c.get("class_mix"),
        "lane1B_reasoning": c.get("lane1B_reasoning"),
        "missing_evidence": missing,
        "future_app_notes": (
            f"{c['candidate_type']} spanning {c['n_zips']} ZIP(s), {c['n_locations']} location(s). "
            f"Suspected {tier} (conf {conf}). "
            + (f"Known brand hint: {c.get('known_dso_hint')}. " if c.get('known_dso_hint') else "No known-DSO brand match — potential HIDDEN local consolidator. ")
            + (f"{claimed_n} member(s) already in {set(CLAIMED[m['location_id']] for m in members if m['already_claimed_by'])}. " if claimed_n else "")
            + ("Main-claimed AO network — left to Main. " if c.get("main_claimed") else "")
        ),
    })

ranked.sort(key=lambda r: (-r["score"], -r["n_zips"], r["candidate_type"]))

cand_doc = {
    "_meta": {
        "lane": "local_clusters", "session": "fleet-b-local-clusters-2026-06-21",
        "generated": "2026-06-21", "db_mode": "read_only",
        "total_clusters": len(ranked),
        "by_type": dict(collections.Counter(r["candidate_type"] for r in ranked)),
        "novel_hidden_consolidator_clusters": sum(1 for r in ranked if r["novel_vs_known_dso"]),
        "note": "Discovery candidates ONLY — never final truth. No DB writes. Brand/AO/phone "
                "are LEADS, not proof. Documentary URL or durable artifact required before any "
                "stealth_dso/branded_dso classification.",
    },
    "clusters": ranked,
}
json.dump(cand_doc, open(CAND, "w"), indent=1)
print(f"\nwrote {len(ranked)} clusters -> {CAND}")
print("by type:", cand_doc["_meta"]["by_type"])
print("novel hidden-consolidator clusters:", cand_doc["_meta"]["novel_hidden_consolidator_clusters"])
print("\nTop 20 by score:")
for r in ranked[:20]:
    print(f"  [{r['score']:>5}] {r['candidate_type']:21} z={r['n_zips']:>2} n={r['n_locations']:>2} "
          f"{str(r['key'])[:34]:34} -> {r['suspected_tier']:14} {'NOVEL' if r['novel_vs_known_dso'] else 'known'}")
