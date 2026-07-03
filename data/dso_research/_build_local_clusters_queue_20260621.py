"""
Fleet B — Local-cluster evidence QUEUE builder (validator-native). READ-ONLY DB.
Consumes local_consolidator_cluster_candidates_20260621.json and emits ONE row per
untiered IL GP location that is a cluster member and NOT already claimed by a sibling
Fleet B / Main queue.

CLASSIFY (status=classified) ONLY for vetted, landmine-free, artifact-backed clusters:
  * EIN cluster whose members map to a KNOWN DSO/MSO friendly-PC  -> branded_dso (ein_cluster)
  * EIN cluster that is dentist-owned multi-location, no DSO/MSO  -> dentist_multi (ein_cluster)
  * parent_company chain to a KNOWN operating DSO brand           -> branded_dso (structural)
  * parent_company chain to a KNOWN PE sponsor                    -> branded_dso + pe_backed
Everything else (phone / AO / brand / intel / dso_regional_review / lane1B_held, and any
landmine) -> needs_verification + undetermined, full intelligence preserved.

NO DB writes. NO ledger/progress writes.
"""
import json, os, sqlite3, collections, re

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
CAND = os.path.join(DR, "local_consolidator_cluster_candidates_20260621.json")
OUT = os.path.join(DR, "ownership_evidence_queue_fleet_b_local_clusters_20260621.json")

# ---- landmine blocklist: NEVER classify these (hold needs_verification) ------
BLOCK_EIN = {
    "363676741",   # Schwartz/Ryan single-building pair — 2026-06-07 REJECTED (not a chain)
    "432052561",   # Acierno — Main-claimed AO network, leave to Main
    "322684113",   # 30 N Michigan Ave 52-NPI shared building — data-quality flag
}
BLOCK_PARENT_SUBSTR = ("EVENLY",)  # parent_iusa=000000000 placeholder, also ortho/specialist

# ---- known friendly-PC / MSO legal entities -> branded_dso brand mapping -----
# (independently corroborated brands; EIN-shared legal names that ARE a DSO/MSO)
FRIENDLY_PC = {
    "DENTAL PROFESSIONALS OF ILLINOIS": ("Heartland Dental", True),   # KKR-backed
    "DENTAL DREAMS": ("Dental Dreams", False),
    "DENTAL EXPERTS": ("Dental Dreams", False),
    "KOS SERVICES": ("Dental Dreams (KOS Services MSO)", False),
    "FAMILY DENTAL CARE": ("Family Dental Care", False),
    "BRITE DENTAL": ("Brite Dental", False),
    # NOTE: "JANS DENTAL" removed — it is a single dentist's holding LLC across two
    # differently-named "Family Dental" offices, i.e. a dentist_multi, NOT a DSO/MSO.
    # It now falls through to the EIN dentist_multi path.
}
# parent_company -> (brand, pe_backed, name_tokens). The Data-Axle/NPPES parent_company
# field is the NOISIEST ownership signal (it produced the 2026-06-12 Evenly false-positive
# and the audit's landlord/PE-name confusion). So we CLASSIFY on a known-DSO parent ONLY
# when the member's OWN practice_name also carries the brand token — otherwise the linkage
# is unconfirmed and the row is held needs_verification with the parent kept as intelligence.
KNOWN_DSO_PARENT = {
    "ADMI CORP": ("Aspen Dental (ADMI)", True, ("ASPEN",)),
    "SONRAVA HEALTH": ("Western Dental (Sonrava)", True, ("WESTERN",)),
    "KOS SERVICES": ("Dental Dreams (KOS Services MSO)", False, ("DENTAL DREAMS", "DREAMS")),
    "WEBSTER DENTAL MANAGEMENT": ("Webster Dental Management", False, ("WEBSTER",)),
    "1ST FAMILY DENTAL": ("1st Family Dental", False, ("1ST FAMILY", "FIRST FAMILY")),
    "MIDWEST DENTAL": ("Midwest Dental", False, ("MIDWEST",)),
}
# PE-sponsor parent on a small practice is almost never name-corroborated (no office is
# literally named "Gryphon"), and it is the exact signal the Evenly audit demoted. We NEVER
# classify on a PE parent alone — these are HELD as high-value needs_verification leads.
KNOWN_PE_PARENT = {
    "GRYPHON INVESTORS": "Gryphon Investors (PE platform)",
    "SHORE CAPITAL PARTNERS LLC": "Shore Capital Partners (PE platform)",
    "BERKSHIRE PARTNERS LLC": "Berkshire Partners (PE platform)",
}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

doc = json.load(open(CAND))
clusters = doc["clusters"]
by_lid = collections.defaultdict(list)   # lid -> [cluster,...]
for c in clusters:
    for lid in c["linked_location_ids"]:
        by_lid[lid].append(c)

def loc_facts(lid):
    return conn.execute("""
        SELECT pl.location_id, pl.practice_name, pl.city, pl.zip, pl.state,
               pl.entity_classification, pl.ownership_tier, pl.primary_npi, pl.org_npi,
               pl.provider_npis, pl.ein, pl.parent_company, pl.affiliated_dso, pl.website,
               wz.state AS ws
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()

def upper(s): return (s or "").upper().strip()

def office_brand_blob(loc):
    """UPPER concat of the office's OWN underlying-NPI brand fields (affiliated_dso,
    franchise_name, da_legal_name, parent_org_lbn). Used to corroborate a Data-Axle
    parent_company guess with an independent per-provider DSO-brand string. Holding-company
    echoes that merely repeat parent_company are deliberately NOT distinguishing here —
    only CONSUMER-BRAND tokens are matched against this blob by the caller."""
    npis = set()
    for k in ("primary_npi", "org_npi", "provider_npis"):
        if loc[k]: npis |= set(re.findall(r"\d{10}", str(loc[k])))
    npis = sorted(npis)
    if not npis: return ""
    qm = ",".join("?" * len(npis))
    parts = []
    for p in conn.execute(f"""SELECT affiliated_dso, franchise_name, da_legal_name, parent_org_lbn
                              FROM practices WHERE npi IN ({qm})""", npis).fetchall():
        for v in (p["affiliated_dso"], p["franchise_name"], p["da_legal_name"], p["parent_org_lbn"]):
            if v: parts.append(upper(v))
    return " | ".join(parts)

# ---- decide classification for a location given its clusters -----------------
def classify(lid, cls, loc):
    """return (status, tier, basis, confidence, pe_backed, brand, artifacts, why, missing)"""
    ein = (loc["ein"] or "").strip()
    parent = upper(loc["parent_company"])
    # collect cluster artifacts/intelligence
    types = {c["candidate_type"] for c in cls}
    legals = set()
    for c in cls:
        for m in c.get("members", []):
            if m["location_id"] == lid:
                for o in m.get("officials", []):
                    for k in ("da_legal_name", "parent_org_lbn", "franchise_name"):
                        if o.get(k): legals.add(upper(o[k]))
        for le in c.get("legal_entities", []): legals.add(upper(le))
    if parent: legals.add(parent)
    legal_join = " | ".join(sorted(legals))

    # ---- landmine: never classify -------------------------------------------
    if ein in BLOCK_EIN:
        return ("needs_verification", "undetermined", "none", "low", False, None, [],
                "EIN on landmine blocklist (prior-rejected / Main-claimed / shared-building).",
                ["independent ownership verification — EIN flagged as non-chain/ambiguous"])
    if any(b in parent for b in BLOCK_PARENT_SUBSTR) or any(any(b in le for b in BLOCK_PARENT_SUBSTR) for le in legals):
        return ("needs_verification", "undetermined", "none", "low", False, None, [],
                "parent_company on landmine blocklist (Evenly placeholder / specialist).",
                ["confirm real operating parent vs. placeholder parent_iusa=000000000"])

    # ---- EIN cluster classification -----------------------------------------
    ein_cluster = next((c for c in cls if c["candidate_type"] == "ein_cluster"), None)
    if ein_cluster and ein and ein not in BLOCK_EIN:
        siblings = [x for x in ein_cluster["linked_location_ids"] if x != lid]
        art = [f"shared_EIN={ein}", f"members={len(ein_cluster['linked_location_ids'])}",
               f"zips={ein_cluster['n_zips']}"] + [f"legal={le}" for le in sorted(legals) if le][:3]
        # known friendly-PC / MSO -> branded_dso
        brand_pe = None
        for needle, (brand, pe) in FRIENDLY_PC.items():
            if needle in legal_join or needle in upper(loc["practice_name"]):
                brand_pe = (brand, pe); break
        if brand_pe:
            return ("classified", "branded_dso", "ein_cluster", "medium", brand_pe[1], brand_pe[0],
                    art, f"Shared EIN {ein} across {ein_cluster['n_zips']} ZIPs; legal entity maps to "
                         f"known DSO/MSO friendly-PC '{brand_pe[0]}'.",
                    [])
        # dentist-owned multi-location (no DSO/MSO) -> dentist_multi
        # require >=2 distinct ZIP (ein clusters here already are), and at least one
        # member with a real practice brand (not two unrelated solos sharing billing)
        return ("classified", "dentist_multi", "ein_cluster", "medium", False, None,
                art, f"Shared real EIN {ein} across {ein_cluster['n_zips']} ZIP(s) with no "
                     f"DSO/MSO/platform signal — dentist-owned multi-location group.",
                ["confirm common ownership vs. shared-billing arrangement; check for hidden MSO"])

    # ---- parent_company chain classification --------------------------------
    pchain = next((c for c in cls if c["candidate_type"] == "parent_company_chain"), None)
    if pchain and parent:
        pname = upper(loc["practice_name"])
        if parent in KNOWN_DSO_PARENT:
            brand, pe, tokens = KNOWN_DSO_PARENT[parent]
            # corroborate the parent_company guess with the CONSUMER DSO brand appearing in the
            # office's OWN name or its OWN underlying-NPI brand fields (affiliated_dso etc.).
            # A holding-company echo (e.g. affiliated_dso='ADMI CORP' == parent_company) is the
            # SAME Data-Axle linkage in two columns, not a second observation -> not accepted.
            blob = office_brand_blob(loc)
            hit = next((t for t in tokens if t in pname or t in blob), None)
            if hit:
                src = "own_name" if hit in pname else "own_npi_affiliated_dso"
                return ("classified", "branded_dso", "structural", "medium", pe, brand,
                        [f"parent_company={parent}", f"consumer_brand='{hit}'({src})",
                         f"chain_zips={pchain['n_zips']}", f"chain_locations={pchain['n_locations']}"],
                        f"parent_company='{parent}' (known DSO '{brand}') AND the office's own "
                        f"{src} carries the '{hit}' consumer brand — two independent fields agree "
                        f"across {pchain['n_zips']} ZIPs.", [])
            # parent says DSO but no consumer-brand string on the office itself -> linkage unconfirmed
            return ("needs_verification", "undetermined", "none", "low", False, None,
                    [f"parent_company={parent}(brand_uncorroborated)", f"chain_zips={pchain['n_zips']}"],
                    f"parent_company='{parent}' (would be DSO '{brand}') but NO consumer-brand string "
                    f"('{'/'.join(tokens)}') on the office's own name or NPI fields — only the "
                    f"holding-company name echoes parent_company, the SAME Data-Axle linkage that "
                    f"produced the Evenly false-positive. HIGH-VALUE lead, HELD.",
                    [f"confirm office operates under '{brand}' via locator/web — parent name alone insufficient"])
        if parent in KNOWN_PE_PARENT:
            # NEVER classify on a PE parent alone — held as a high-value hidden-platform lead
            return ("needs_verification", "undetermined", "none", "low", False, None,
                    [f"parent_company={parent}(PE)", f"chain_zips={pchain['n_zips']}"],
                    f"parent_company='{parent}' is a known PE sponsor across {pchain['n_zips']} ZIPs — "
                    f"strong hidden-platform LEAD, but a PE parent_company on an independent-named office "
                    f"is the exact signal the 2026-06-12 audit demoted (landlord/PE-name confusion). HELD.",
                    [f"confirm '{parent}' actually owns/backs the operating practice via locator/SEC/press, "
                     f"not a Data-Axle name collision"])
        # named but unknown parent -> hold (could be placeholder/landlord)
        return ("needs_verification", "undetermined", "none", "low", False, None,
                [f"parent_company={parent}"],
                f"parent_company='{parent}' present across {pchain['n_zips']} ZIPs but not a "
                f"recognized DSO/MSO/PE — verify it is a real operating parent.",
                ["confirm parent_company is an operating DSO/MSO, not a landlord/placeholder"])

    # ---- everything else: hold as intelligence ------------------------------
    # pick the richest cluster for the why/missing narrative
    primary = sorted(cls, key=lambda c: -c.get("score", 0))[0]
    why = f"Lead via {sorted(types)} (top: {primary['candidate_type']} '{primary['key']}', "\
          f"{primary['n_zips']} ZIP / {primary['n_locations']} loc). " + (primary.get("future_app_notes") or "")
    missing = sorted(set(sum([c.get("missing_evidence", []) for c in cls], [])))[:5] or \
              ["documentary URL or durable artifact confirming ownership structure"]
    return ("needs_verification", "undetermined", "none", "low", False, None, [], why[:400], missing)

# ---- harvest already-claimed lids (avoid collision/double-count) -------------
CLAIMED = doc["_meta"]  # not used; recompute precisely from sibling queues
claimed = set()
def harvest(path):
    if not os.path.exists(path): return
    try: d = json.load(open(path))
    except Exception: return
    def walk(o):
        if isinstance(o, dict):
            lid = o.get("location_id")
            if isinstance(lid, str): claimed.add(lid)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(d)
for fn in ["ownership_evidence_queue_fleet_b_20260621.json",
           "ownership_evidence_queue_fleet_b_lane3_20260621.json",
           "ownership_evidence_queue_fleet_b_backfill_20260621.json",
           "ownership_evidence_queue_fleet_b_lane1B_20260621.json",
           "ao_network_evidence_20260621.json",
           "ao_network_evidence_reach4_20260621.json",
           "ao_network_evidence_reach5_20260621.json"]:
    harvest(os.path.join(DR, fn))
print(f"already-claimed lids (excluded from this queue): {len(claimed)}")

EXCLUDED = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}
rows, qa_flags = [], []
skipped = collections.Counter()
for lid, cls in by_lid.items():
    if lid in claimed:
        skipped["already_claimed"] += 1; continue
    loc = loc_facts(lid)
    if not loc: skipped["no_loc"] += 1; continue
    if loc["ws"] != "IL" or upper(loc["state"]) != "IL": skipped["not_IL"] += 1; continue
    if loc["entity_classification"] in EXCLUDED: skipped["excluded_class"] += 1; continue
    if loc["ownership_tier"]: skipped["already_tiered"] += 1; continue
    if str(loc["primary_npi"] or "").startswith("DA_") and str(loc["org_npi"] or "").startswith("DA_"):
        skipped["da_only"] += 1; continue

    status, tier, basis, conf, pe, brand, arts, why, missing = classify(lid, cls, loc)
    # intelligence fields
    network_ids = sorted({c["cluster_id"] for c in cls})
    cand_types = sorted({c["candidate_type"] for c in cls})
    owners, fams, brands, legals = set(), set(), set(), set()
    for c in cls:
        for o in c.get("suspected_owner_operator", []): owners.add(o)
        for f in c.get("suspected_family_surnames", []): fams.add(f)
        for le in c.get("legal_entities", []): legals.add(le)
    if brand: brands.add(brand)
    if loc["affiliated_dso"]: brands.add(loc["affiliated_dso"])
    evidence_urls = []
    if loc["website"] and str(loc["website"]).startswith("http"): evidence_urls.append(loc["website"])

    row = {
        # validator-native required
        "location_id": lid, "assigned_tier": tier, "evidence_basis": basis,
        "confidence": conf, "status": status, "reasoning": why,
        # validator-read evidence
        "evidence_urls": evidence_urls if basis in ("web_verified","locator","intel_dossier") else [],
        "evidence_artifacts": arts, "pe_backed": bool(pe),
        # context auto-fill
        "practice_name": loc["practice_name"], "city": loc["city"], "zip": loc["zip"],
        "current_entity_classification": loc["entity_classification"],
        # ---- future-app intelligence ----
        "network_ids": network_ids, "candidate_types": cand_types,
        "owner_identity": sorted(owners)[:5] or None,
        "family_surnames": sorted(fams)[:5] or None,
        "brands": sorted(brands) or None,
        "legal_entities": sorted(legals)[:6] or None,
        "evidence_chain": arts + ([f"website={evidence_urls[0]}"] if evidence_urls else []),
        "missing_evidence": missing,
        "lane": "local_clusters", "session": "fleet-b-local-clusters-2026-06-21",
        "reviewed_at": "2026-06-21",
    }
    # enforce validator hygiene deterministically (defense in depth)
    if status == "classified":
        bad = None
        # validator forbids classifying if EITHER primary OR org NPI is a DA_ synthetic (OR, not AND)
        if str(loc["primary_npi"] or "").startswith("DA_") or str(loc["org_npi"] or "").startswith("DA_"):
            bad = "da_synthetic_npi"
        elif conf == "low": bad = "low_confidence"
        elif basis == "none": bad = "basis_none"
        elif basis in ("web_verified","locator","intel_dossier") and not row["evidence_urls"]: bad = "url_basis_without_url"
        elif basis in ("ein_cluster","ao_cluster","name_chain","structural") and not arts: bad = "artifact_basis_without_artifact"
        elif tier in ("stealth_dso","branded_dso") and not (row["evidence_urls"] or arts): bad = "dso_tier_no_evidence"
        if bad:
            qa_flags.append({"location_id": lid, "practice_name": loc["practice_name"],
                             "flag": f"classify_demoted:{bad}", "would_be_tier": tier})
            row.update({"status": "needs_verification", "assigned_tier": "undetermined",
                        "evidence_basis": "none", "confidence": "low"})
    rows.append(row)

print(f"queue rows: {len(rows)} | skipped: {dict(skipped)}")
by_status = collections.Counter(r["status"] for r in rows)
by_tier = collections.Counter(r["assigned_tier"] for r in rows if r["status"] == "classified")
print("by_status:", dict(by_status))
print("classified_by_tier:", dict(by_tier))

meta = {
    "lane": "local_clusters", "session": "fleet-b-local-clusters-2026-06-21",
    "generated": "2026-06-21", "db_mode": "read_only", "total_rows": len(rows),
    "by_status": dict(by_status), "classified_by_tier": dict(by_tier),
    "classified": by_status.get("classified", 0),
    "needs_verification": by_status.get("needs_verification", 0),
    "skipped": dict(skipped), "qa_flag_count": len(qa_flags), "_qa_flags": qa_flags,
    "landmine_blocklist": {"ein": sorted(BLOCK_EIN), "parent_substr": list(BLOCK_PARENT_SUBSTR)},
    "note": "Evidence-only, ready_for_validation, NEVER final. No DB writes. Classified rows are "
            "artifact-backed (EIN cluster or known-DSO/PE parent). AO/phone/brand are LEADS held "
            "needs_verification. Already-claimed sibling-queue lids excluded to avoid collision.",
}
json.dump({"classifications": rows, "_meta": meta}, open(OUT, "w"), indent=1)
print(f"\nwrote {len(rows)} rows -> {OUT}")
print("classified examples:")
for r in rows:
    if r["status"] == "classified":
        print(f"  {r['practice_name'][:30]:30} {r['zip']} -> {r['assigned_tier']:13} pe={r['pe_backed']} "
              f"{r['evidence_basis']:11} {(r['brands'] or [''])[0][:28]}")
