"""Fleet B — Local-clusters lane QA-flags / verification-wave handoff. READ-ONLY (JSON only).
Packages: demotion flags, landmine blocklist, and the highest-value HELD hidden-consolidator
leads (PE-parent, brand-uncorroborated DSO-parent, top-scoring novel clusters) for the next
verification wave. NO DB writes."""
import json, os, collections
DR="/Users/suleman/dental-pe-tracker/data/dso_research"
Q=json.load(open(f"{DR}/ownership_evidence_queue_fleet_b_local_clusters_20260621.json"))
C=json.load(open(f"{DR}/local_consolidator_cluster_candidates_20260621.json"))
rows=Q["classifications"]; meta=Q["_meta"]
cscore={c["cluster_id"]: c for c in C["clusters"]}

def best_cluster(r):
    cs=[cscore[n] for n in (r.get("network_ids") or []) if n in cscore]
    return max(cs, key=lambda c: c.get("score",0)) if cs else None

held=[r for r in rows if r["status"]=="needs_verification"]

# (a) held leads where a KNOWN DSO/PE parent is present but not classifiable yet
def arts_join(r): return " ".join(r.get("evidence_artifacts") or [])
pe_leads, dso_uncorrob_leads = [], []
for r in held:
    a=arts_join(r)
    if "(PE)" in a:
        pe_leads.append(r)
    elif "brand_uncorroborated" in a or "(name_uncorroborated)" in a:
        dso_uncorrob_leads.append(r)

def lead_row(r):
    bc=best_cluster(r)
    return {
        "location_id": r["location_id"], "practice_name": r["practice_name"],
        "zip": r["zip"], "city": r["city"],
        "current_entity_classification": r["current_entity_classification"],
        "candidate_types": r.get("candidate_types"),
        "owner_identity": r.get("owner_identity"), "family_surnames": r.get("family_surnames"),
        "brands": r.get("brands"), "legal_entities": r.get("legal_entities"),
        "evidence_artifacts": r.get("evidence_artifacts"),
        "cluster_score": round(bc.get("score",0),2) if bc else None,
        "novel_vs_known_dso": bc.get("novel_vs_known_dso") if bc else None,
        "n_zips": bc.get("n_zips") if bc else None, "n_locations": bc.get("n_locations") if bc else None,
        "why_it_matters": r["reasoning"], "missing_evidence": r.get("missing_evidence"),
        "suggested_next_step": "web/locator verify operator + brand; confirm DSO/MSO vs dentist-owned",
    }

# (b) top novel held leads by cluster score (exclude the parent leads already surfaced)
seen={r["location_id"] for r in pe_leads+dso_uncorrob_leads}
ranked=sorted((r for r in held if r["location_id"] not in seen),
              key=lambda r:-( (best_cluster(r) or {}).get("score",0) ))
top_novel=[lead_row(r) for r in ranked[:60]]

ctype_hist=collections.Counter(t for r in held for t in (r.get("candidate_types") or []))

out={
 "_meta":{
   "lane":"local_clusters","session":"fleet-b-local-clusters-2026-06-21","generated":"2026-06-21",
   "namespace":"fleet_b (NOT QA's ownership_evidence_QA_*)","db_writes":"NONE — validate-only handoff",
   "source_queue":"ownership_evidence_queue_fleet_b_local_clusters_20260621.json",
   "source_candidates":"local_consolidator_cluster_candidates_20260621.json",
   "queue_by_status":meta["by_status"],"queue_classified_by_tier":meta["classified_by_tier"],
   "landmine_blocklist":meta["landmine_blocklist"],
   "held_lead_counts":{"pe_parent":len(pe_leads),"dso_parent_brand_uncorroborated":len(dso_uncorrob_leads),
                       "top_novel_surfaced":len(top_novel),"total_held":len(held)},
   "held_candidate_type_histogram":dict(ctype_hist.most_common()),
   "note":"Highest-value HELD hidden-consolidator leads for the next verification wave. None are "
          "final. PE-parent and brand-uncorroborated DSO-parent rows were deliberately NOT classified "
          "(Data-Axle parent_company alone produced the 2026-06-12 Evenly false-positive); they are "
          "the strongest verify-next leads. Brand substring is a LEAD, never proof.",
 },
 "demotion_qa_flags":meta.get("_qa_flags",[]),
 "held_pe_parent_leads":[lead_row(r) for r in pe_leads],
 "held_dso_parent_brand_uncorroborated_leads":[lead_row(r) for r in dso_uncorrob_leads],
 "top_novel_held_leads":top_novel,
}
P=f"{DR}/ownership_evidence_queue_fleet_b_local_clusters_qa_flags_20260621.json"
json.dump(out,open(P,"w"),indent=1)
print("wrote",P)
print("demotion_qa_flags:",len(out["demotion_qa_flags"]),
      "| pe_parent_leads:",len(pe_leads),
      "| dso_brand_uncorrob_leads:",len(dso_uncorrob_leads),
      "| top_novel:",len(top_novel),"| total_held:",len(held))
print("held candidate-type histogram:",dict(ctype_hist.most_common(12)))
