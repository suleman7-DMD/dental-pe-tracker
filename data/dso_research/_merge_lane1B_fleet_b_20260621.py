"""
Fleet B — Lane 1B Wave-2 merge + normalize to validator-native schema.
Reads the worker outputs (_out_lane1B_*.json), enforces EVERY consolidate_census
validator gate deterministically (agents judge; this script guarantees validity),
preserves future-app intelligence fields, and writes the final evidence queue.
READ-ONLY DB. No DB writes. No LEDGER/PROGRESS writes.
"""
import json, glob, os, sqlite3, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
WORK = os.path.join(DR, "_shards_fleet_b", "_lane1B_worker")
OUT = os.path.join(DR, "ownership_evidence_queue_fleet_b_lane1B_20260621.json")

VALID_TIERS = {"true_independent", "single_loc_group", "dentist_multi",
               "stealth_dso", "branded_dso", "institutional", "undetermined"}
VALID_BASES = {"locator", "web_verified", "ein_cluster", "ao_cluster",
               "name_chain", "intel_dossier", "structural", "none"}
VALID_STATUS = {"classified", "undetermined", "needs_verification"}
VALID_CONFIDENCE = {"high", "medium", "low"}
EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}
URL_BASES = {"locator", "web_verified", "intel_dossier"}
ARTIFACT_BASES = {"ein_cluster", "ao_cluster", "name_chain", "structural"}
DSO_TIERS = {"stealth_dso", "branded_dso"}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

def is_da(v): return str(v or "").startswith("DA_")
def listify(v): return v if isinstance(v, list) else ([] if v in (None, "") else [v])

def loc_facts(lid):
    return conn.execute("""
        SELECT pl.practice_name, pl.city, pl.zip, pl.state, pl.entity_classification,
               pl.primary_npi, pl.org_npi, pl.ownership_tier, wz.state AS ws
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()

# ---- load worker outputs ----------------------------------------------------
out_files = sorted(glob.glob(os.path.join(WORK, "_out_lane1B_*.json")))
raw = []
for f in out_files:
    try:
        d = json.load(open(f))
        rows = d if isinstance(d, list) else d.get("rows") or d.get("classifications") or []
        for r in rows: r["_src_shard"] = os.path.basename(f)
        raw.extend(rows)
    except Exception as e:
        print(f"  WARN: could not load {f}: {e}")
print(f"loaded {len(raw)} worker rows from {len(out_files)} shards")

# ---- normalize + enforce gates ---------------------------------------------
final, qa_flags, demotions = [], [], collections.Counter()
seen = set()
for r in raw:
    lid = r.get("location_id")
    if not lid or lid in seen:
        if lid in seen: qa_flags.append({"location_id": lid, "flag": "duplicate_lid_dropped"})
        continue
    seen.add(lid)
    loc = loc_facts(lid)
    if not loc:
        qa_flags.append({"location_id": lid, "flag": "lid_not_in_db_dropped"}); continue
    if loc["ws"] != "IL" or (loc["state"] or "").upper() != "IL":
        qa_flags.append({"location_id": lid, "flag": "not_IL_dropped"}); continue
    if loc["entity_classification"] in EXCLUDED_GP_CLASSES:
        qa_flags.append({"location_id": lid, "flag": f"excluded_class_{loc['entity_classification']}_dropped"}); continue
    if loc["ownership_tier"]:
        qa_flags.append({"location_id": lid, "flag": f"already_tiered_{loc['ownership_tier']}_dropped"}); continue

    tier = r.get("proposed_tier") or r.get("assigned_tier") or "undetermined"
    status = r.get("status") or "needs_verification"
    conf = r.get("confidence") or "low"
    basis = r.get("evidence_basis") or "none"
    urls = [u for u in listify(r.get("evidence_urls")) if u and isinstance(u, str)
            and ("http" in u or u == "no_results_found")]
    arts = [a for a in listify(r.get("evidence_artifacts")) if a and isinstance(a, str)]

    # vocab coercion
    if tier not in VALID_TIERS: tier = "undetermined"
    if basis not in VALID_BASES: basis = "none"
    if status not in VALID_STATUS: status = "needs_verification"
    if conf not in VALID_CONFIDENCE: conf = "low"

    da_loc = is_da(loc["primary_npi"]) or is_da(loc["org_npi"])
    demote_reason = None
    if status == "classified":
        if conf == "low": demote_reason = "low_confidence"
        elif basis == "none": demote_reason = "classified_basis_none"
        elif basis in URL_BASES and not urls: demote_reason = "url_basis_without_url"
        elif basis in ARTIFACT_BASES and not arts: demote_reason = "artifact_basis_without_artifact"
        elif tier in DSO_TIERS and not (urls or arts): demote_reason = "dso_tier_no_evidence"
        elif tier == "true_independent" and basis == "structural" and not arts: demote_reason = "true_indep_structural_no_artifact"
        elif da_loc: demote_reason = "da_synthetic_npi"
    if demote_reason:
        demotions[demote_reason] += 1
        qa_flags.append({"location_id": lid, "practice_name": loc["practice_name"],
                         "flag": f"classify_demoted:{demote_reason}",
                         "would_be_tier": tier})
        status = "needs_verification"; tier = "undetermined"
    # status hygiene
    if status in ("needs_verification", "undetermined"):
        tier = "undetermined"
    # carry agent qa_flag
    if r.get("qa_flag"):
        qa_flags.append({"location_id": lid, "practice_name": loc["practice_name"],
                         "flag": "agent:" + str(r["qa_flag"])})

    reasoning = (r.get("reasoning") or "").strip() or \
        f"No documentary ownership evidence isolated; held for verification ({basis})."

    row = {
        # validator-native (required)
        "location_id": lid,
        "assigned_tier": tier,
        "evidence_basis": basis,
        "confidence": conf,
        "status": status,
        "reasoning": reasoning,
        # validator-read evidence
        "evidence_urls": urls,
        "evidence_artifacts": arts,
        "pe_backed": bool(r.get("pe_backed")) if status == "classified" else bool(r.get("pe_backed", False)),
        # auto-fill context
        "practice_name": loc["practice_name"], "city": loc["city"], "zip": loc["zip"],
        "current_entity_classification": loc["entity_classification"],
        # ---- future-app intelligence (validator ignores unknown keys) ----
        "owner_identity": r.get("owner_identity"),
        "brands": listify(r.get("brands")),
        "legal_entities": listify(r.get("legal_entities")),
        "network_id": r.get("network_id"),
        "stale_or_closed": r.get("stale_or_closed"),
        "why_it_matters": r.get("why_it_matters"),
        "proposed_tier_raw": r.get("proposed_tier"),
        "agent_status_raw": r.get("status"),
        "source_shard": r.get("_src_shard"),
        "lane": "lane1B_wave2",
        "session": "fleet-b-lane1B-2026-06-21",
        "reviewed_at": "2026-06-21",
    }
    final.append(row)

# ---- coverage backstop: no survivor lid silently dropped --------------------
in_lids = {}
for f in sorted(glob.glob(os.path.join(WORK, "_w_lane1B_*.json"))):
    for r in json.load(open(f)):
        if r.get("location_id"):
            in_lids[r["location_id"]] = r
missing = [lid for lid in in_lids if lid not in seen]
for lid in missing:
    loc = loc_facts(lid)
    if not loc or loc["ws"] != "IL" or (loc["state"] or "").upper() != "IL":
        continue
    if loc["entity_classification"] in EXCLUDED_GP_CLASSES or loc["ownership_tier"]:
        continue
    seen.add(lid)
    qa_flags.append({"location_id": lid, "practice_name": loc["practice_name"],
                     "flag": "worker_did_not_emit:defaulted_needs_verification"})
    final.append({
        "location_id": lid, "assigned_tier": "undetermined", "evidence_basis": "none",
        "confidence": "low", "status": "needs_verification",
        "reasoning": "Worker shard did not emit a row for this location; defaulted to "
                     "needs_verification so no survivor is silently dropped.",
        "evidence_urls": [], "evidence_artifacts": [], "pe_backed": False,
        "practice_name": loc["practice_name"], "city": loc["city"], "zip": loc["zip"],
        "current_entity_classification": loc["entity_classification"],
        "owner_identity": None, "brands": [], "legal_entities": [], "network_id": None,
        "stale_or_closed": None, "why_it_matters": None, "proposed_tier_raw": None,
        "agent_status_raw": None, "source_shard": "BACKSTOP",
        "lane": "lane1B_wave2", "session": "fleet-b-lane1B-2026-06-21", "reviewed_at": "2026-06-21",
    })
print(f"coverage backstop: {len(in_lids)} survivor lids in, {len(missing)} not emitted by workers -> defaulted")

# ---- tallies ----------------------------------------------------------------
by_status = collections.Counter(x["status"] for x in final)
by_tier = collections.Counter(x["assigned_tier"] for x in final)
by_tier_classified = collections.Counter(x["assigned_tier"] for x in final if x["status"] == "classified")
meta = {
    "lane": "lane1B_wave2", "session": "fleet-b-lane1B-2026-06-21",
    "generated": "2026-06-21", "total_rows": len(final),
    "by_status": dict(by_status), "by_tier": dict(by_tier),
    "classified_by_tier": dict(by_tier_classified),
    "classified": by_status.get("classified", 0),
    "needs_verification": by_status.get("needs_verification", 0),
    "demotions": dict(demotions),
    "qa_flag_count": len(qa_flags),
    "_qa_flags": qa_flags,
    "note": "Evidence-only candidate rows; never final truth. No DB writes. "
            "Gate-enforced validator-native schema + future-app intelligence fields.",
}
json.dump({"classifications": final, "_meta": meta}, open(OUT, "w"), indent=1)
print(f"\nwrote {len(final)} rows -> {OUT}")
print("by_status:", dict(by_status))
print("by_tier:", dict(by_tier))
print("classified_by_tier:", dict(by_tier_classified))
print("demotions:", dict(demotions))
print("qa_flags:", len(qa_flags))
