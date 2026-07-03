#!/usr/bin/env python3
"""
WAVE 2 MERGE (Main AO reach=4 + Fleet B Lane1B) -> next manifest pass.
NO DB writes. Produces:
  - _ready_to_validate_wave2_20260621.json  (210 validator-native ready rows)
  - consolidation_candidate_manifest_20260621.json  (updated in place, living artifact)
Preserves ALL Wave 2 intelligence verbatim as sidecars (nothing flattened):
  - ao_network_intelligence.wave2_reach4  (14 networks + 56 rows, verbatim)
  - fleet_b_lane1B  (full 320 classifications + qa_flags, verbatim)
Gate rules: per-row, honor reach4 QA regate/candidates/specialist; Webster/Berwyn stay in
conflicts; never promote on AO-reach / brand-substring / weak-name-chain alone; honor every
Lane1B QA flag + held lead; drop cross-wave tier conflicts to backfill.
"""
import json, os
R="data/dso_research"
def L(p):
    with open(os.path.join(R,p)) as f: return json.load(f)
def dump(p,obj):
    with open(os.path.join(R,p),"w") as f: json.dump(obj,f,indent=1)

man=L("consolidation_candidate_manifest_20260621.json"); B=man["buckets"]
existing_ready=B["ready_to_validate"]                       # 123 validator-native rows
ready_ids={r["location_id"] for r in existing_ready}
nme=B["needs_more_evidence"]; rej=B["rejected"]; conf=B["conflicts"]
conf_ids={r["location_id"] for r in conf}; rej_ids={r["location_id"] for r in rej}
bq=man["evidence_gap_backfill_queue"]

# ===================== REACH4 =====================
r4=L("ao_network_evidence_reach4_20260621.json")
r4q=L("ao_network_evidence_reach4_20260621_qa.json")
r4nets={n["network_id"]:n for n in r4["networks"]}
# lid -> network_id via each network's locations list
lid2nid={}
for n in r4["networks"]:
    for loc in (n.get("locations") or []):
        lid = loc if isinstance(loc,str) else loc.get("location_id")
        if lid: lid2nid[lid]=n["network_id"]
regate={r["location_id"]:r for r in r4q["regate_audit"]}
cand_unres={r["location_id"] for r in r4q["candidates_unresolved"]}
spec_undet={r["location_id"] for r in r4q["specialist_or_undetermined_flags"]}

def r4_eff(row):
    lid=row["location_id"]
    if lid in regate: return regate[lid]["final_gate"], regate[lid]["final_tier"]
    if lid in spec_undet: return "undetermined","undetermined"
    if lid in cand_unres: return "candidate", row.get("candidate_tier")
    return row.get("gate_status"), row.get("candidate_tier")

BASIS={"stealth_dso":"structural","branded_dso":"name_chain","dentist_multi":"name_chain",
       "single_loc_group":"name_chain","true_independent":"web_verified","institutional":"web_verified"}

def build_r4_ready(row,tier):
    lid=row["location_id"]; nid=lid2nid.get(lid) or ("ao:"+str(row.get("network","")).replace(" ","_").upper())
    net=r4nets.get(nid,{})
    arts=[]
    if row.get("db_artifact"): arts.append(row["db_artifact"])
    arts += list(net.get("durable_artifacts") or [])
    urls=list(row.get("evidence_urls") or [])
    verdict=net.get("owner_type_verdict"); nsum=str(net.get("network_summary") or "")[:320]
    rrz=str(row.get("reasoning") or "")[:280]
    reasoning=(f"[gate-owner wave2 reach4 | {nid} | verdict={verdict}] {nsum} || row: {rrz} || "
               f"GATE: promoted to ready per reach4 QA (gate=ready_for_validation, tier={tier}). "
               f"AO reach is signal only; tier rests on durable artifacts (e.g. {str((arts or [''])[0])[:120]}).")
    pe=row.get("pe_backed")
    return {
        "location_id":lid, "assigned_tier":tier,
        "pe_backed":bool(pe) if pe is not None else False,
        "evidence_basis":BASIS.get(tier,"name_chain"),
        "evidence_urls":urls, "evidence_artifacts":arts,
        "confidence":row.get("confidence"), "status":"classified",
        "network_id":nid, "reasoning":reasoning,
    }

r4_ready_rows=[]; r4_backfill=[]; r4_keepconf=[]; r4_dup=[]
for row in r4["rows"]:
    lid=row["location_id"]; gate,tier=r4_eff(row); cfd=row.get("confidence")
    if lid in conf_ids: r4_keepconf.append(lid); continue
    if lid in ready_ids: r4_dup.append(lid); continue
    if gate!="ready_for_validation" or tier in (None,"undetermined") or cfd=="low":
        r4_backfill.append({"location_id":lid,"name":row.get("name"),"city":row.get("city"),
            "zip":row.get("zip"),"candidate_tier":tier,"gate_status":gate,"confidence":cfd,
            "network_id":lid2nid.get(lid),"source":"reach4",
            "reason":"reach4 gate=candidate/undetermined or specialist — needs documentary corroborator",
            "reasoning":str(row.get("reasoning") or "")[:400]}); continue
    r4_ready_rows.append(build_r4_ready(row,tier))

# ===================== LANE1B =====================
fb=L("ownership_evidence_queue_fleet_b_lane1B_20260621.json")
fbq=L("ownership_evidence_queue_fleet_b_lane1B_qa_flags_20260621.json")
flagged={}
for cat,rows in fbq["flags_by_category"].items():
    for r in rows: flagged[r["location_id"]]=cat
held={r["location_id"] for r in fbq["held_stealth_branded_leads"]}
XWAVE_HOLD={"1df260dc64a9a060"}      # Shafi Dental: wave1 released Shafi as dentist_multi; Lane1B says branded_dso
AO_REACH_ONLY={"18bb61421ac89614"}   # KALPANA SHAH ao_cluster: AO reach only, no website/BBB/intel corroborator
CANON=["location_id","assigned_tier","pe_backed","evidence_basis","evidence_urls",
       "evidence_artifacts","confidence","status","network_id","reasoning"]
r4_ready_ids={r["location_id"] for r in r4_ready_rows}

fb_ready_rows=[]; fb_backfill=[]; fb_keepconf=[]; fb_dup=[]
for r in fb["classifications"]:
    if r.get("status")!="classified": continue
    lid=r["location_id"]
    if lid in conf_ids: fb_keepconf.append(lid); continue
    if lid in ready_ids or lid in r4_ready_ids: fb_dup.append(lid); continue
    why=None
    if lid in flagged: why="qa_flag:"+flagged[lid]
    elif lid in held: why="held_stealth_branded_lead"
    elif r.get("confidence")=="low": why="low_confidence"
    elif lid in XWAVE_HOLD: why="xwave_tier_conflict_shafi"
    elif lid in AO_REACH_ONLY: why="ao_reach_only_no_corroborator"
    if why:
        fb_backfill.append({"location_id":lid,"name":r.get("practice_name"),"city":r.get("city"),
            "zip":r.get("zip"),"candidate_tier":r.get("assigned_tier"),"confidence":r.get("confidence"),
            "network_id":r.get("network_id"),"source":"lane1B","reason":why,
            "reasoning":str(r.get("reasoning") or "")[:400]}); continue
    fb_ready_rows.append({k:r.get(k) for k in CANON})

# ===================== ASSEMBLE =====================
new_ready=r4_ready_rows+fb_ready_rows
new_ready_ids={r["location_id"] for r in new_ready}
assert len(new_ready_ids)==len(new_ready), "dup location_id within new_ready"
assert not (new_ready_ids & ready_ids), "new_ready collides with existing ready"
assert not (new_ready_ids & conf_ids), "new_ready collides with conflicts"
assert not (new_ready_ids & rej_ids), "new_ready collides with rejected"

# ready
B["ready_to_validate"]=existing_ready+new_ready
# remove any promoted ids from needs_more + backfill
B["needs_more_evidence"]=[r for r in nme if r["location_id"] not in new_ready_ids]
bq=[r for r in bq if r["location_id"] not in new_ready_ids]
# append wave2 near-ready leads to backfill (dedup by location_id)
bq_ids={r["location_id"] for r in bq}
for r in (r4_backfill+fb_backfill):
    if r["location_id"] not in bq_ids and r["location_id"] not in new_ready_ids:
        bq.append(r); bq_ids.add(r["location_id"])
man["evidence_gap_backfill_queue"]=bq

# ---- Webster/Berwyn conflict enrichment (reach4 strengthened the MSO evidence) ----
rempas=r4nets.get("ao:REMPAS_STEVEN",{})
for c in conf:
    if c["location_id"] in set(r4_keepconf):
        c.setdefault("wave2_reach4_note",
            "reach4 corroborates: AO STEVEN REMPAS reach=4; parent_company/affiliated_dso='WEBSTER DENTAL "
            "MANAGEMENT' (documented MSO at websterdentalmanagement.com). STRENGTHENS the contested-Webster "
            "case but stays in conflicts pending whole-Webster adjudication. NOT auto-promoted.")

# ===================== SIDECARS (verbatim, nothing flattened) =====================
ao_intel=man.get("ao_network_intelligence",{})
ao_intel["wave2_reach4"]={
    "_provenance":"ao_network_evidence_reach4_20260621.json (Main AO reach=4, Hidden Local Consolidator "
                  "Discovery Wave 2). Strategic NETWORK evidence. Preserved verbatim. AO reach=4 = signal, "
                  "not proof; tiers rest on durable_artifacts (shared EIN/legal-entity, MSO website "
                  "disclosure, public DSO locator, court/BBB records, NexHealth MSO booking slug).",
    "_meta":r4.get("_meta"),
    "networks":r4.get("networks"),   # ao/owner/operator identity, brands, legal_entities, durable_artifacts,
                                     # evidence_chain, future_app_notes, stale_closed_false_positive_notes
    "rows":r4.get("rows"),
    "qa":r4q,
}
man["ao_network_intelligence"]=ao_intel

man["fleet_b_lane1B"]={
    "_provenance":"ownership_evidence_queue_fleet_b_lane1B_20260621.json + _qa_flags companion. Full "
                  "candidate set preserved verbatim (61 classified + 258 needs_verification + 1 "
                  "undetermined) — future-app intelligence; needs_verification rows are leads, NOT promotions.",
    "_meta":fb.get("_meta"),
    "classifications":fb.get("classifications"),
    "qa_flags":fbq,
}

# ---- reach4 per-network gate decisions ----
def net_decision(nid):
    n=r4nets[nid]; locs=[l if isinstance(l,str) else l.get("location_id") for l in (n.get("locations") or [])]
    rdy=[lid for lid in locs if lid in r4_ready_ids]
    return {"network_id":nid,"recommended_tier":n.get("recommended_tier"),
            "owner_type_verdict":n.get("owner_type_verdict"),
            "recommended_confidence":n.get("recommended_confidence"),
            "mso_platform_pe":bool(n.get("mso_platform_pe_evidence")),
            "n_locations":len(locs),"n_released_ready":len(rdy),
            "n_held":len(locs)-len(rdy)-len([x for x in locs if x in conf_ids]),
            "n_in_conflicts":len([x for x in locs if x in conf_ids])}
man["reach4_network_release_decisions"]={
    "_policy":("Per-ROW gate honoring reach4 QA (regate_audit overrides candidate_tier; candidates_unresolved "
               "and specialist/undetermined -> backfill). branded/stealth/dentist_multi promoted ONLY with a "
               "durable artifact beyond AO reach. Webster/Berwyn (ao:REMPAS_STEVEN + Berwyn) HELD in conflicts "
               "(contested-Webster set). No PE inference: pe_backed set ONLY from documented MSO/PE evidence; "
               "pe_backed=false never downgrades a DSO tier."),
    "decisions":[net_decision(nid) for nid in r4nets],
    "summary":{"reach4_rows":len(r4["rows"]),"released_ready":len(r4_ready_rows),
               "backfill":len(r4_backfill),"held_in_conflicts":len(set(r4_keepconf)),
               "dup_already_ready":len(r4_dup)},
}
man["fleet_b_lane1B_dispositions"]={
    "source":"ownership_evidence_queue_fleet_b_lane1B_20260621.json",
    "classified_total":61,"released_ready":len(fb_ready_rows),
    "to_backfill":len(fb_backfill),"dup":len(fb_dup),"kept_in_conflicts":len(fb_keepconf),
    "needs_verification_preserved_in_sidecar":sum(1 for r in fb["classifications"] if r.get("status")=="needs_verification"),
    "qa_flag_actions":{
        "all 16 QA-flag categories honored":"any classified row in maybe_specialist/identity_mismatch/"
            "address_or_stale/ein_cluster/other_agent_flag/closed/held_stealth_branded_leads -> backfill, NOT ready",
        "1df260dc64a9a060":"Shafi Dental -> backfill (Lane1B branded_dso conflicts with wave1 Shafi dentist_multi release)",
        "18bb61421ac89614":"Kalpana Shah -> backfill (ao_cluster AO-reach-only, no website/BBB/intel corroborator)",
        "c7e3a014ba70dd36":"H&U West Loop -> dedup (also promoted via reach4 Hoffman network, same tier dentist_multi)",
    },
}

# ===================== COUNTS + RECON =====================
ready=B["ready_to_validate"]; nme2=B["needs_more_evidence"]
core_ids={}
dups=[]
for bk,rows in [("ready",ready),("needs_more",nme2),("conflicts",conf),("rejected",rej)]:
    for r in rows:
        lid=r["location_id"]
        if lid in core_ids: dups.append((lid,core_ids[lid],bk))
        core_ids[lid]=bk
assert not dups, f"core-bucket location_id collisions: {dups[:10]}"

from collections import Counter
man["counts"]={
    "ready_to_validate":len(ready),
    "ready_tier_mix":dict(Counter(r["assigned_tier"] for r in ready)),
    "ready_basis_mix":dict(Counter(r["evidence_basis"] for r in ready)),
    "needs_more_evidence":len(nme2),
    "evidence_gap_backfill_queue":len(bq),
    "conflicts":len(conf),"rejected":len(rej),
    "taxonomy_revised":len(B.get("taxonomy_revised",[])),
    "core_universe_distinct_locations":len(core_ids),
    "sidecar_ao_wave1_networks":len((man["ao_network_intelligence"].get("networks") or {})),
    "sidecar_ao_wave2_reach4_networks":len(r4["networks"]),
    "sidecar_lane1B_total_rows":len(fb["classifications"]),
}
man.setdefault("_meta",{})["wave2_merge"]={
    "at":"2026-06-21","by":"opus-4.8 reset-consolidation-gate (4th session, autonomous)",
    "inputs":["ao_network_evidence_reach4_20260621.json (+_qa)",
              "ownership_evidence_queue_fleet_b_lane1B_20260621.json (+_qa_flags)"],
    "result":(f"ready {len(existing_ready)} -> {len(ready)} (+{len(r4_ready_rows)} reach4, +{len(fb_ready_rows)} "
              f"lane1B); reach4 backfill {len(r4_backfill)}, lane1B backfill {len(fb_backfill)}; "
              f"Webster/Berwyn {len(set(r4_keepconf))} held in conflicts. All reach4 networks + full Lane1B "
              f"set preserved verbatim as sidecars. Sweis/Ramaha (wave1) remain protected/held."),
    "validate_only":"python3 scrapers/consolidate_census.py "
        "data/dso_research/_ready_to_validate_wave2_20260621.json --session gate_owner_wave2_20260621 --validate-only",
    "db_writes":"NONE. consolidation still FROZEN; no --allow-db-write.",
}

dump("_ready_to_validate_wave2_20260621.json", {"classifications":ready})
dump("consolidation_candidate_manifest_20260621.json", man)

print("WAVE 2 MERGE complete (no DB writes).")
print(" reach4: ready+%d backfill %d held_conflicts %d dup %d" %
      (len(r4_ready_rows),len(r4_backfill),len(set(r4_keepconf)),len(r4_dup)))
print(" lane1B: ready+%d backfill %d dup %d (needs_verification %d preserved in sidecar)" %
      (len(fb_ready_rows),len(fb_backfill),len(fb_dup),
       man["fleet_b_lane1B_dispositions"]["needs_verification_preserved_in_sidecar"]))
print(json.dumps(man["counts"],indent=1))
