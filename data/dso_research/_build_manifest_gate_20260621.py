#!/usr/bin/env python3
"""Gate-owner manifest builder (2026-06-21). READ-ONLY: loads the 6 signed inputs
+ the Phase-6 gate review, dedups by location_id, applies exclusions + gate
network dispositions, and buckets rows. NO DB writes.
Run: python3 data/dso_research/_build_manifest_gate_20260621.py
"""
import json, sqlite3, os, collections

RES = os.path.dirname(__file__)
DB  = os.path.join(RES, "..", "dental_pe_tracker.db")
def L(fn): return json.load(open(os.path.join(RES, fn)))

DSO={"branded_dso","stealth_dso"}; CND={"dentist_multi","single_loc_group"}
IND={"true_independent"}; INST={"institutional"}
def eqclass(t):
    if t in DSO: return "DSO"
    if t in CND: return "CND"
    if t in IND: return "IND"
    if t in INST: return "INST"
    return "NOOP"
EXCLUDED_GP={"specialist","non_clinical","da_unverified","org_only_npi","duplicate_location"}

# ---------- gate review: build network disposition + alias/stem maps ----------
gr = L("ownership_taxonomy_DSO_structure_gate_review_20260621.json")
NET={}        # net_name -> {disposition, tier, taxonomy_revised}
ALIAS={}      # alias label -> net_name
STEM=[]       # (stem, net_name)
def reg(net, dispo, tier=None, taxrev=False, aliases=None, stems=None):
    NET[net]={"disposition":dispo,"tier":tier,"taxonomy_revised":taxrev}
    for a in (aliases or []): ALIAS[a.strip().upper()]=net
    for s in (stems or []):   STEM.append((s.strip().upper(), net))

for n in gr["eight_network_audit"]:
    d=n["disposition"]
    tier=n.get("revised_tier") if d=="eligible_dso" else None
    reg(n["network"], d, tier, n.get("taxonomy_revised",False), n.get("aliases"), n.get("name_stems"))
for n in gr["additional_dso_networks_eligible"]["networks"]:
    reg(n["network"], "eligible_dso", n["tier"], False, n.get("aliases"), n.get("name_stems"))
for n in gr["dentist_multi_networks_eligible"]["networks"]:
    reg(n["network"], "eligible_dentist_multi", "dentist_multi", False, n.get("aliases"), n.get("name_stems"))
for n in gr["needs_more_evidence_networks"]["networks"]:
    reg(n["network"], "needs_more_evidence", None, False, n.get("aliases"), n.get("name_stems"))
SPECIAL={o["location_id"]:o for o in gr["special_location_overrides"]["true_independent_positively_earned"]}
# disposition -> conservative priority (lower = wins when a location matches >1 network)
PRIO={"conflict":0,"needs_more_evidence":1,"eligible_dso":2,"eligible_dentist_multi":3}

# ---------- accumulate per-location opinions ----------
rec=collections.defaultdict(lambda:{"op":[]})
def add(lid, src, tier, **kw):
    if not lid: return
    o={"src":src,"tier":tier}; o.update(kw); rec[lid]["op"].append(o)
    if kw.get("net"): rec[lid].setdefault("nets",set()).add(kw["net"])

d=L("ownership_evidence_QA_20260621.json")
NOTCONSOL={r["location_id"]:r.get("reason") for r in d.get("should_NOT_consolidate_despite_final_ready_label",[])}
for r in d["rows"]:
    add(r["location_id"],"ownership_QA", r.get("corrected_tier_if_obvious") or r.get("fleet_assigned_tier"),
        status=r.get("qa_status"), safe=r.get("safe_to_consolidate"),
        basis=str(r.get("fleet_evidence_basis") or "")+" "+str(r.get("qa_reasons") or ""))
d=L("ao_network_evidence_QA_20260621.json")
for r in d["rows"]:
    add(r["location_id"],"ao_QA", r.get("corrected_tier_if_obvious") or r.get("fleet_tier"),
        status=r.get("qa_status"), safe=r.get("safe_to_consolidate"), exact=r.get("main_session_addr_exact_confirmed"),
        nurls=r.get("n_evidence_urls"), net=r.get("network"))
d=L("ownership_evidence_QA_fleet_b_20260621.json")
for r in d["rows"]:
    add(r["location_id"],"fleet_b", r.get("corrected_tier") or r.get("fleet_tier"),
        status=r.get("qa_status"), safe=r.get("safe_to_consolidate_post_freeze"), exact=r.get("exact_address_match"),
        basis=str(r.get("fleet_basis") or ""))
d=L("ao_network_evidence_reach5_20260621.json")
for r in d["classifications"]:
    add(r["location_id"],"reach5", r.get("candidate_tier"),
        status=r.get("gate_status"), safe=(r.get("gate_status")=="ready_for_validation"),
        urls=r.get("evidence_urls"), net=r.get("_network") or r.get("network_id"))
d=L("ownership_taxonomy_DSO_structure_addendum_20260621.json")
for r in d["rows"]:
    add(r["location_id"],"addendum", r.get("revised_tier"),
        safe=(r.get("action")=="restore_DSO_tier"), basis=str(r.get("evidence_basis") or ""),
        net=r.get("network"))

# ---------- denominator review: 8 HIGH duplicate-door pairs (the named block) ----------
d=L("evidence_denominator_review_20260621.json")
DUP=set()
for row in d["tier_contradictions_at_dup_addresses"]["rows"]:
    for lid in row.get("location_ids",[]): DUP.add(lid)
COLLAPSE_NOTE=d["summary"]  # reported as denominator caveat only, not a row block

# ---------- DB enrichment ----------
con=sqlite3.connect(DB); ids=list(rec.keys()); q=",".join("?"*len(ids))
DBR={}
for r in con.execute(f"SELECT location_id,entity_classification,state,zip,city,is_specialist_only,practice_name,primary_npi FROM practice_locations WHERE location_id IN ({q})", ids):
    DBR[r[0]]={"ec":r[1],"state":r[2],"zip":r[3],"city":r[4],"spec":r[5],"name":r[6],"npi":r[7]}

def resolve_net(lid, name):
    """Return the conservative-priority network disposition matching this location, or None."""
    cands=set()
    for n in rec[lid].get("nets",set()):
        if n and n.strip().upper() in ALIAS: cands.add(ALIAS[n.strip().upper()])
    nm=(name or "").upper()
    for stem,net in STEM:
        if stem and stem in nm: cands.add(net)
    if not cands: return None
    return min(cands, key=lambda c: PRIO.get(NET[c]["disposition"],9))

LOCATOR_KW=("locator","/locations/","own site","webdentalchicago","group site")
MSO_KW=("mso","management","parent","platform","pe-backed","pe backed","kkr","gryphon","dental partners","services llc","kos","united dental","smile brands","heartland","aspen")

# ---------- bucket ----------
B=collections.defaultdict(list); taxrev_index=[]
for lid,info in rec.items():
    db=DBR.get(lid,{}); name=info.get("name") or db.get("name"); state=db.get("ec");
    ec=db.get("ec"); st=db.get("state")
    ops=info["op"]
    classes={eqclass(o["tier"]) for o in ops}; nonnoop=classes-{"NOOP"}
    base={"location_id":lid,"name":name,"zip":db.get("zip"),"city":db.get("city"),"state":st,
          "entity_classification":ec,"nets":sorted(n for n in info.get("nets",set()) if n),
          "sources":{o["src"]:o["tier"] for o in ops}}
    # priority safe opinion (for deferred tier)
    order=["ownership_QA","ao_QA","fleet_b","reach5","addendum"]
    bysrc={o["src"]:o for o in ops}
    safe_op=None
    for s in order:
        if s in bysrc and bysrc[s].get("safe") and eqclass(bysrc[s]["tier"])!="NOOP":
            safe_op=bysrc[s]; break

    # (1) exclusions
    if st and st!="IL":
        base["reason"]=f"state={st} (not IL; MA parked / out of scope)"; B["rejected"].append(base); continue
    if ec in EXCLUDED_GP or db.get("spec"):
        base["reason"]=f"excluded GP class entity_classification={ec} spec_only={db.get('spec')}"; B["rejected"].append(base); continue
    if lid in NOTCONSOL:
        base["reason"]="QA should_NOT_consolidate: "+str(NOTCONSOL[lid]); B["rejected"].append(base); continue
    # (2) named duplicate-door HIGH tier-contradiction
    if lid in DUP:
        base["reason"]="duplicate-door HIGH tier-contradiction (evidence_denominator_review): one physical door, conflicting tiers across dup rows"
        B["duplicate_denominator_blocked"].append(base); continue
    # (3) gate special override (positively-earned true_independent)
    if lid in SPECIAL:
        base["final_tier"]="true_independent"; base["reason"]=SPECIAL[lid]["reason"]
        B["ready_to_validate"].append(base); continue
    # (4) gate network disposition
    net=resolve_net(lid,name)
    if net:
        nd=NET[net]; base["gate_network"]=net; base["gate_disposition"]=nd["disposition"]
        if nd["disposition"]=="conflict":
            base["reason"]=f"gate review: network '{net}' is CONTESTED across signed passes (DSO vs dentist_multi); resolve before validating"
            B["conflicts"].append(base); continue
        if nd["disposition"]=="needs_more_evidence":
            base["reason"]=f"gate review: network '{net}' does not meet the DSO bar (locator-only / weak signal / specialist)"
            B["needs_more_evidence"].append(base); continue
        if nd["disposition"] in ("eligible_dso","eligible_dentist_multi"):
            base["final_tier"]=nd["tier"]; base["reason"]=f"gate review: network '{net}' {nd['disposition']}"
            if nd["taxonomy_revised"]:
                base["taxonomy_revised"]=True
                taxrev_index.append({"location_id":lid,"name":name,"network":net,"to":nd["tier"]})
            B["ready_to_validate"].append(base); continue
    # (5) per-location cross-source class disagreement
    if len({c for c in nonnoop if c in ("DSO","CND","IND","INST")})>1:
        base["reason"]="cross-source equivalence-class disagreement at this location_id"
        base["conflict_classes"]=sorted(nonnoop); B["conflicts"].append(base); continue
    # (6) defer to QA safe disposition
    if safe_op is None:
        base["reason"]="no signed pass marked this row safe_to_consolidate (undetermined / needs_more_evidence)"
        B["needs_more_evidence"].append(base); continue
    ft=safe_op["tier"]; base["final_tier"]=ft
    # (6a) locator-only DSO demotion
    if eqclass(ft)=="DSO":
        allbasis=" ".join(str(o.get("basis","")) for o in ops).lower()
        has_loc=any(k in allbasis for k in LOCATOR_KW); has_mso=any(k in allbasis for k in MSO_KW)
        exact=any(o.get("exact") for o in ops); has_url=any(o.get("urls") for o in ops) or any((o.get("nurls") or 0)>0 for o in ops)
        if has_loc and not has_mso:
            base["reason"]="DSO tier rests on a locator/own-site with no MSO/PE/established-brand evidence (canonical rule: locator != MSO)"
            B["needs_more_evidence"].append(base); continue
        if not (exact or has_url):
            base["reason"]="DSO tier without exact-address confirmation or documentary URL"
            B["needs_more_evidence"].append(base); continue
    # (6b) true_independent already earned (safe_op present); ship
    base["reason"]=f"deferred to {safe_op['src']} safe_to_consolidate disposition"
    B["ready_to_validate"].append(base)

# ---------- report + stash ----------
print("INPUT location_ids:",len(rec)," DB-resolved:",len(DBR))
print("named duplicate-door ids:",len(DUP))
for b in ["ready_to_validate","needs_more_evidence","rejected","duplicate_denominator_blocked","conflicts"]:
    print(f"  {b:30s}: {len(B[b])}")
print("  taxonomy_revised (index)       :",len(taxrev_index))
print("ready_to_validate by final_tier:",dict(collections.Counter(r.get("final_tier") for r in B["ready_to_validate"])))
print("conflicts by gate_network:",dict(collections.Counter(r.get("gate_network","(per-location)") for r in B["conflicts"])))
print("needs_more_evidence by gate_network:",dict(collections.Counter(r.get("gate_network","(deferred/per-row)") for r in B["needs_more_evidence"])))

json.dump({"buckets":dict(B),"taxonomy_revised_index":taxrev_index,
           "counts":{k:len(v) for k,v in B.items()},"collapse_note":COLLAPSE_NOTE},
          open(os.path.join(RES,"_manifest_draft_20260621.json"),"w"),indent=1)
print("wrote _manifest_draft_20260621.json")
