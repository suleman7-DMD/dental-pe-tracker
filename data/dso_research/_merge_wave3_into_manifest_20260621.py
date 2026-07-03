#!/usr/bin/env python3
"""
WAVE 3 MERGE (separate pass, AFTER the QA MUST-FIX demotion).
Inputs (all overlap existing buckets -> dedupe by location_id across ready/needs_more/rejected/conflicts):
  - ao_network_evidence_reach3_ranked_20260621.json (+ _qa companion)  (51 networks / 138 rows)
  - ownership_evidence_queue_fleet_b_local_clusters_20260621.json      (637 rows; 19 classified)
  - ownership_evidence_queue_fleet_b_website_clusters_20260621.json    (79 rows; 5 classified)
  - ownership_evidence_queue_fleet_b_structural_residue_20260621.json  (4 rows; 2 classified)
Rules: boring & strict per-ROW gate; honor reach3 QA regate/candidates/specialist; never promote on
AO-reach / brand-substring / weak-name-chain alone (require a durable artifact); honor every fleet_b
qa_flag; preserve ALL network/future-app intelligence as sidecars (nothing flattened). NO DB writes.
"""
import json, os
from collections import Counter
R="data/dso_research"
def L(p):
    with open(os.path.join(R,p)) as f: return json.load(f)
def dump(p,obj):
    with open(os.path.join(R,p),"w") as f: json.dump(obj,f,indent=1)

man=L("consolidation_candidate_manifest_20260621.json"); B=man["buckets"]
ready_ids={r["location_id"] for r in B["ready_to_validate"]}
nme_ids ={r["location_id"] for r in B["needs_more_evidence"]}
rej_ids ={r["location_id"] for r in B["rejected"]}
conf_ids={r["location_id"] for r in B["conflicts"]}
bq=man["evidence_gap_backfill_queue"]; bq_ids={r["location_id"] for r in bq}
seen_new_ready=set()

CANON=["location_id","assigned_tier","pe_backed","evidence_basis","evidence_urls",
       "evidence_artifacts","confidence","status","network_id","reasoning"]
BASIS={"stealth_dso":"structural","branded_dso":"name_chain","dentist_multi":"name_chain",
       "single_loc_group":"name_chain","true_independent":"web_verified","institutional":"web_verified"}

def in_core(lid):  # already dispositioned anywhere we must dedupe against
    return lid in ready_ids or lid in nme_ids or lid in rej_ids or lid in conf_ids or lid in seen_new_ready

# ====================== reach3 ======================
r3=L("ao_network_evidence_reach3_ranked_20260621.json")
r3q=L("ao_network_evidence_reach3_ranked_qa.json")
r3nets={n["network_id"]:n for n in r3["networks"]}
regate={r["location_id"]:r for r in r3q["regate_audit"]}                 # gate_status+candidate_tier = final
cand_unres={r["location_id"] for r in r3q["candidates_unresolved"]}
spec_undet={r["location_id"] for r in r3q["specialist_or_undetermined_flags"]}

def r3_eff(row):
    lid=row["location_id"]
    if lid in regate: return regate[lid].get("gate_status"), regate[lid].get("candidate_tier")
    if lid in spec_undet: return "undetermined","undetermined"
    if lid in cand_unres: return "candidate", row.get("candidate_tier")
    return row.get("gate_status"), row.get("candidate_tier")

r3_ready=[]; r3_backfill=[]; r3_keepconf=[]; r3_dup=[]
for row in r3["rows"]:
    lid=row["location_id"]
    if lid in conf_ids: r3_keepconf.append(lid); continue
    if lid in ready_ids or lid in rej_ids or lid in nme_ids or lid in seen_new_ready:
        r3_dup.append(lid); continue
    gate,tier=r3_eff(row); cfd=row.get("confidence")
    nid=row.get("network_id") or ("ao:"+str(row.get("network","")).replace(" ","_").upper())
    net=r3nets.get(nid,{})
    arts=[a for a in [row.get("db_affiliated_dso"),row.get("db_parent_company")] if a] + list(net.get("durable_artifacts") or [])
    if gate!="ready_for_validation" or tier in (None,"undetermined") or cfd not in ("high","medium") or not arts:
        r3_backfill.append({"location_id":lid,"name":row.get("name"),"city":row.get("city"),"zip":row.get("zip"),
            "candidate_tier":tier,"gate_status":gate,"confidence":cfd,"network_id":nid,"source":"reach3",
            "reason":("reach3 candidate/undetermined/specialist or no durable artifact beyond AO reach"),
            "reasoning":str(row.get("reasoning") or "")[:400]}); continue
    nsum=str(net.get("network_summary") or "")[:300]; rrz=str(row.get("reasoning") or "")[:260]
    r3_ready.append({"location_id":lid,"assigned_tier":tier,
        "pe_backed":bool(row.get("pe_backed")) if row.get("pe_backed") is not None else False,
        "evidence_basis":BASIS.get(tier,"name_chain"),
        "evidence_urls":list(row.get("evidence_urls") or []),"evidence_artifacts":arts,
        "confidence":cfd,"status":"classified","network_id":nid,
        "reasoning":(f"[gate-owner wave3 reach3 | {nid} | verdict={net.get('owner_type_verdict')}] {nsum} || "
                     f"row: {rrz} || GATE: ready per reach3 QA (gate={gate}, tier={tier}); AO reach is signal "
                     f"only, tier rests on durable artifact (e.g. {str(arts[0])[:120]}).")})
    seen_new_ready.add(lid)

# ====================== fleet_b lanes ======================
def project(r):
    nid=r.get("network_id") or (r.get("network_ids") or [None])[0]
    if not nid and r.get("shared_domain"): nid="domain:"+str(r["shared_domain"])
    out={k:r.get(k) for k in CANON}; out["network_id"]=nid
    return out

def merge_fleet(fname, lane):
    d=L(fname); meta=d.get("_meta",{})
    qa_ids=set()
    qf=meta.get("_qa_flags")
    if isinstance(qf,list):
        for x in qf: qa_ids.add(x.get("location_id"))
    elif isinstance(qf,dict):
        for cat,rows in qf.items():
            for x in rows: qa_ids.add(x.get("location_id"))
    ready=[]; backfill=[]; dup=[]
    for r in d.get("classifications",[]):
        if r.get("status")!="classified": continue
        lid=r["location_id"]
        if lid in conf_ids: backfill.append((lid,"in_conflicts")); continue
        if in_core(lid): dup.append(lid); continue
        if lid in qa_ids:
            backfill.append({"location_id":lid,"name":r.get("practice_name"),"city":r.get("city"),"zip":r.get("zip"),
                "candidate_tier":r.get("assigned_tier"),"confidence":r.get("confidence"),"source":lane,
                "reason":"fleet_b qa_flag","reasoning":str(r.get("reasoning") or "")[:300]}); continue
        if r.get("confidence")=="low":
            backfill.append({"location_id":lid,"name":r.get("practice_name"),"source":lane,
                "reason":"low_confidence","candidate_tier":r.get("assigned_tier")}); continue
        ready.append(project(r)); seen_new_ready.add(lid)
    return d, ready, backfill, dup

lc_d, lc_ready, lc_bf, lc_dup = merge_fleet("ownership_evidence_queue_fleet_b_local_clusters_20260621.json","local_clusters")
wc_d, wc_ready, wc_bf, wc_dup = merge_fleet("ownership_evidence_queue_fleet_b_website_clusters_20260621.json","website_clusters")
sr_d, sr_ready, sr_bf, sr_dup = merge_fleet("ownership_evidence_queue_fleet_b_structural_residue_20260621.json","structural_residue")

new_ready=r3_ready+lc_ready+wc_ready+sr_ready
new_ready_ids={r["location_id"] for r in new_ready}
assert len(new_ready_ids)==len(new_ready), "dup within new_ready"
assert not (new_ready_ids & ready_ids), "collide existing ready"
assert not (new_ready_ids & conf_ids), "collide conflicts"
assert not (new_ready_ids & rej_ids), "collide rejected"
assert not (new_ready_ids & nme_ids), "collide needs_more"

# ---- apply to buckets ----
B["ready_to_validate"]+=new_ready
# backfill overlay (dedupe; only structured dict items; only if not in a core bucket)
core_now=ready_ids|nme_ids|rej_ids|conf_ids|new_ready_ids
for r in (r3_backfill+[x for x in lc_bf if isinstance(x,dict)]+[x for x in wc_bf if isinstance(x,dict)]+[x for x in sr_bf if isinstance(x,dict)]):
    lid=r["location_id"]
    if lid in bq_ids or lid in core_now: continue
    bq.append(r); bq_ids.add(lid)
man["evidence_gap_backfill_queue"]=bq

# ====================== SIDECARS (verbatim) ======================
ao_intel=man.get("ao_network_intelligence",{})
ao_intel["wave3_reach3"]={
    "_provenance":"ao_network_evidence_reach3_ranked_20260621.json (+_qa). Ranked AO reach=3 / reach=2-strong "
                  "networks (Hidden Local Consolidator Discovery Wave 3). Strategic NETWORK evidence, verbatim. "
                  "AO reach = signal; tiers rest on durable_artifacts. Preserved: ao/owner/operator identity, "
                  "ranking_score+reasons, brand_trade_names, legal_entities, durable_artifacts, mso_platform_pe_"
                  "evidence, evidence_chain, future_app_notes, stale_closed_false_positive_notes.",
    "_meta":r3.get("_meta"),"networks":r3.get("networks"),"rows":r3.get("rows"),"qa":r3q,
}
man["ao_network_intelligence"]=ao_intel
man["fleet_b_wave3"]={
    "_provenance":"Fleet B Wave 3 deterministic sweeps (local_clusters / website_clusters / structural_residue). "
                  "Full candidate sets preserved verbatim — needs_verification rows are LEADS, NOT promotions. "
                  "landmine_blocklist + qa_flags retained for future-app review.",
    "local_clusters":{"_meta":lc_d.get("_meta"),"classifications":lc_d.get("classifications")},
    "website_clusters":{"_meta":wc_d.get("_meta"),"classifications":wc_d.get("classifications")},
    "structural_residue":{"_meta":sr_d.get("_meta"),"classifications":sr_d.get("classifications")},
}
man["reach3_network_release_decisions"]={
    "_policy":("Per-ROW gate honoring reach3 QA (regate_audit overrides gate/tier; candidates_unresolved + "
               "specialist/undetermined -> backfill). Promote ONLY with a durable artifact beyond AO reach; "
               "conf must be high/medium. Webster/contested + any row already in conflicts stay in conflicts. "
               "No PE inference; pe_backed from documented MSO/PE only."),
    "summary":{"reach3_rows":len(r3["rows"]),"released_ready":len(r3_ready),"backfill":len(r3_backfill),
               "held_in_conflicts":len(set(r3_keepconf)),"dup_already_dispositioned":len(r3_dup)},
    "per_network_oneliner":r3q.get("per_network_oneliner"),
}
man["fleet_b_wave3_dispositions"]={
    "local_clusters":{"classified":lc_d["_meta"].get("classified"),"released_ready":len(lc_ready),
                      "to_backfill":len([x for x in lc_bf if isinstance(x,dict)]),"in_conflicts":len([x for x in lc_bf if not isinstance(x,dict)]),
                      "dup":len(lc_dup),"needs_verification_in_sidecar":lc_d["_meta"].get("needs_verification")},
    "website_clusters":{"classified":wc_d["_meta"].get("by_status",{}).get("classified"),"released_ready":len(wc_ready),
                        "to_backfill":len([x for x in wc_bf if isinstance(x,dict)]),"dup":len(wc_dup),
                        "needs_verification_in_sidecar":wc_d["_meta"].get("by_status",{}).get("needs_verification")},
    "structural_residue":{"classified":sr_d["_meta"].get("classified"),"released_ready":len(sr_ready),
                          "to_backfill":len([x for x in sr_bf if isinstance(x,dict)]),"dup":len(sr_dup),
                          "needs_verification_in_sidecar":sr_d["_meta"].get("needs_verification")},
}

# ====================== COUNTS + RECON ======================
ready=B["ready_to_validate"]
core={}; dups=[]
for bk in ("ready_to_validate","needs_more_evidence","conflicts","rejected"):
    for r in B[bk]:
        lid=r["location_id"]
        if lid in core: dups.append((lid,core[lid],bk))
        core[lid]=bk
assert not dups, f"core-bucket collisions: {dups[:10]}"
man["counts"].update({
    "ready_to_validate":len(ready),
    "ready_tier_mix":dict(Counter(r["assigned_tier"] for r in ready)),
    "ready_basis_mix":dict(Counter(r["evidence_basis"] for r in ready)),
    "needs_more_evidence":len(B["needs_more_evidence"]),
    "evidence_gap_backfill_queue":len(bq),
    "conflicts":len(B["conflicts"]),"rejected":len(B["rejected"]),
    "core_universe_distinct_locations":len(core),
    "sidecar_ao_wave3_reach3_networks":len(r3["networks"]),
    "sidecar_fleet_b_wave3_total_rows":len(lc_d["classifications"])+len(wc_d["classifications"])+len(sr_d["classifications"]),
})
man.setdefault("_meta",{})["wave3_merge"]={
    "at":"2026-06-21","by":"opus-4.8 reset-consolidation-gate (4th session, autonomous)",
    "inputs":["ao_network_evidence_reach3_ranked_20260621.json (+_qa)",
              "ownership_evidence_queue_fleet_b_local_clusters_20260621.json",
              "ownership_evidence_queue_fleet_b_website_clusters_20260621.json",
              "ownership_evidence_queue_fleet_b_structural_residue_20260621.json"],
    "ran_after":"QA MUST-FIX demotion of 4 operating-status-unverified rows (ready 210->206)",
    "result":(f"ready 206 -> {len(ready)} (+{len(r3_ready)} reach3, +{len(lc_ready)} local, "
              f"+{len(wc_ready)} website, +{len(sr_ready)} structural). All sources deduped by "
              f"location_id across ready/needs_more/rejected/conflicts + within-wave. Sidecars preserved."),
    "validate_only":"python3 scrapers/consolidate_census.py "
        "data/dso_research/_ready_to_validate_wave2_20260621.json --session gate_owner_wave3_20260621 --validate-only",
    "db_writes":"NONE.",
}
dump("_ready_to_validate_wave2_20260621.json", {"classifications":ready})
dump("consolidation_candidate_manifest_20260621.json", man)

print("WAVE 3 MERGE complete (no DB writes).")
print(" reach3:   ready+%d backfill %d held_conflicts %d dup %d"%(len(r3_ready),len(r3_backfill),len(set(r3_keepconf)),len(r3_dup)))
print(" local:    ready+%d backfill %d dup %d"%(len(lc_ready),len([x for x in lc_bf if isinstance(x,dict)]),len(lc_dup)))
print(" website:  ready+%d backfill %d dup %d"%(len(wc_ready),len([x for x in wc_bf if isinstance(x,dict)]),len(wc_dup)))
print(" struct:   ready+%d backfill %d dup %d"%(len(sr_ready),len([x for x in sr_bf if isinstance(x,dict)]),len(sr_dup)))
print(" TOTAL new ready:",len(new_ready)," -> ready_to_validate",len(ready))
print(json.dumps(man["counts"],indent=1))
