#!/usr/bin/env python3
"""Assemble AO Wave 3 (reach=3 ranked + strong reach=2) deliverable + QA from the workflow result.

EVIDENCE-ONLY. Reads (never writes) the SQLite DB for current entity_classification.
Writes ONLY two NEW files under data/dso_research/. No DB writes, no consolidation.

Usage:
    python3 scrapers/_assemble_ao_reach3.py /path/to/<taskid>.output
The .output file's top-level `result` key holds the workflow return
(network_summaries[] + classifications[], already defensively re-gated).
"""
import json, sqlite3, sys, os, re

ROOT = '/Users/suleman/dental-pe-tracker'
DSO = f'{ROOT}/data/dso_research'
RANKED_FILE = f'{DSO}/ao_network_evidence_reach3_ranked_targets_20260621.json'
TARGETS_FILE = f'{DSO}/ownership_evidence_targets_20260621.json'
DB = f'{ROOT}/data/dental_pe_tracker.db'
OUT = f'{DSO}/ao_network_evidence_reach3_ranked_20260621.json'
QA = f'{DSO}/ao_network_evidence_reach3_ranked_qa.json'

RAW_DIR = f'{DSO}/_reach3_raw_20260621'
DATE = '2026-06-21'
CORP = {'dso_regional', 'dso_national'}


def load_result(path):
    d = json.load(open(path))
    if isinstance(d, dict) and 'result' in d and isinstance(d['result'], dict):
        return d['result']
    return d


def covered_location_ids():
    """location_ids already emitted in completed waves (top-8, reach>=5, reach=4, backfill-71)."""
    covered = set()
    for fn in ('ao_network_evidence_20260621.json',
               'ao_network_evidence_reach5_20260621.json',
               'ao_network_evidence_reach4_20260621.json'):
        p = f'{DSO}/{fn}'
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        for key in ('classifications', 'rows'):
            for r in (d.get(key) or []):
                if isinstance(r, dict) and r.get('location_id'):
                    covered.add(r['location_id'])
    p = f'{DSO}/ao_backfill_evidence_71_20260621.json'
    if os.path.exists(p):
        b = json.load(open(p))
        for r in b.get('rows', []):
            if r.get('location_id'):
                covered.add(r['location_id'])
        for i in (b.get('individuals') or []):
            if isinstance(i, dict) and i.get('location_id'):
                covered.add(i['location_id'])
    return covered


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: _assemble_ao_reach3.py <result.output>')
    res = load_result(sys.argv[1])

    ranked = json.load(open(RANKED_FILE))
    by_ao = {t['authorized_official']: t for t in ranked['targets']}
    # location structural fields straight from the ranked targets (which embed the cluster locations)
    loc_struct = {}
    for t in ranked['targets']:
        for L in t['locations']:
            loc_struct[L['location_id']] = L

    # current DB entity_classification (READ-ONLY)
    db_ec = {}
    if os.path.exists(DB):
        con = sqlite3.connect(DB)
        ids = list(loc_struct)
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            q = f"SELECT location_id, entity_classification FROM practice_locations WHERE location_id IN ({','.join('?' * len(chunk))})"
            for lid, ec in con.execute(q, chunk).fetchall():
                db_ec[lid] = ec
        con.close()

    summaries = {s['network']: s for s in res.get('network_summaries', [])}
    classifications = res.get('classifications', [])

    # ── ROWS: join re-gated classification + structural + current DB + rank/reach ──
    rows = []
    seen_loc = {}
    collisions = []
    orphans = []
    for c in classifications:
        lid = c['location_id']
        net = c.get('_network')
        struct = loc_struct.get(lid)
        if struct is None:
            orphans.append({'location_id': lid, 'network': net})
        if lid in seen_loc and seen_loc[lid] != net:
            collisions.append({'location_id': lid, 'networks': [seen_loc[lid], net]})
        seen_loc[lid] = net
        tgt = by_ao.get(net, {})
        row = {
            'location_id': lid,
            'network': net,
            'network_id': c.get('network_id'),
            'ao_reach': c.get('_reach'),
            'rank': c.get('_rank'),
            # structural ground truth
            'name': (struct or {}).get('name'),
            'dba': (struct or {}).get('dba'),
            'address': (struct or {}).get('address'),
            'city': (struct or {}).get('city'),
            'zip': (struct or {}).get('zip'),
            'ein': (struct or {}).get('ein'),
            'primary_npi': (struct or {}).get('primary_npi'),
            'org_npi': (struct or {}).get('org_npi'),
            'provider_count': (struct or {}).get('provider_count'),
            'year_established': (struct or {}).get('year_established'),
            'db_affiliated_dso': (struct or {}).get('affiliated_dso'),
            'db_parent_company': (struct or {}).get('parent_company'),
            'current_db_entity_classification': db_ec.get(lid),
            # re-gated candidate output
            'candidate_tier': c.get('candidate_tier'),
            'pe_backed': c.get('pe_backed'),
            'owner_identity': c.get('owner_identity'),
            'gate_status': c.get('gate_status'),
            'confidence': c.get('confidence'),
            'signal_vs_evidence': c.get('signal_vs_evidence'),
            'evidence_urls': c.get('evidence_urls'),
            'stale_closed_note': c.get('stale_closed_note'),
            'reasoning': c.get('reasoning'),
            'regate_note': c.get('_regated'),
            'platform_evidence_detected': c.get('_platform_evidence'),
            'verdict': c.get('_verdict'),
        }
        rows.append(row)

    # ── NETWORKS: enrich summaries with rank/score/ranking_reasons + tier distribution ──
    networks = []
    for net, s in summaries.items():
        tgt = by_ao.get(net, {})
        net_rows = [r for r in rows if r['network'] == net]
        tier_dist = {}
        for r in net_rows:
            tier_dist[r['candidate_tier']] = tier_dist.get(r['candidate_tier'], 0) + 1
        modal = max(tier_dist, key=tier_dist.get) if tier_dist else None
        networks.append({
            'authorized_official': net,
            'network_id': s.get('network_id'),
            'reach': s.get('reach'),
            'rank': s.get('rank'),
            'ranking_score': tgt.get('score'),
            'ranking_reasons': tgt.get('ranking_reasons'),
            'linked_prior_work': s.get('linked_prior_work'),
            'owner_type_verdict': s.get('verdict'),
            'recommended_tier_modal': modal,
            'tier_distribution': tier_dist,
            'network_summary': s.get('summary'),
            'owner_operator_identity': s.get('owner_operator_identity'),
            'brand_trade_names': s.get('brand_trade_names'),
            'legal_entities': s.get('legal_entities'),
            'durable_artifacts': s.get('durable_artifacts'),
            'mso_platform_pe_evidence': s.get('mso_platform_pe_evidence'),
            'stale_closed_false_positive_notes': s.get('stale_closed_false_positive_notes'),
            'evidence_chain': s.get('evidence_chain'),
            'future_app_notes': s.get('future_app_notes'),
            'n_locations': s.get('n'),
        })
    networks.sort(key=lambda n: (n.get('rank') or 9999))

    deliverable = {
        '_meta': {
            'artifact': 'AO Wave 3 — Hidden Local Consolidator Discovery (ranked reach=3 + strong reach=2)',
            'wave': 'ao_network_reach3_ranked',
            'generated': DATE,
            'scope': 'Chicagoland watched-IL GP only (MA/Boston parked)',
            'standard': 'corrected_2026-06-21 (DSO tier = MSO/management/platform STRUCTURE, not PE; pe_backed separate)',
            'gate_ceiling': 'ready_for_validation (NEVER final)',
            'no_db_write': True,
            'source_signal': 'authorized-official cluster (shared AO across NPIs of 2+ watched-IL GP locations) = discovery signal, NOT ownership proof',
            'ranked_target_list': os.path.basename(RANKED_FILE),
            'raw_per_network_dir': RAW_DIR,
            'n_networks': len(networks),
            'n_locations': len(rows),
            'n_reach3': sum(1 for n in networks if n['reach'] == 3),
            'n_reach2_strong': sum(1 for n in networks if n['reach'] == 2),
            'tier_tally': res.get('tier_tally'),
            'gate_tally': res.get('gate_tally'),
            'verdict_tally': res.get('verdict_tally'),
            'n_ready_for_validation': res.get('n_ready_for_validation'),
        },
        'networks': networks,
        'rows': rows,
    }
    json.dump(deliverable, open(OUT, 'w'), indent=2)

    # ── QA ──
    covered = covered_location_ids()
    overlaps_prior = [{'location_id': r['location_id'], 'network': r['network']}
                      for r in rows if r['location_id'] in covered]
    rfv = [r for r in rows if r['gate_status'] == 'ready_for_validation']
    rfv_uncorroborated = [r for r in rfv if not (r.get('evidence_urls') and
                          (r.get('signal_vs_evidence') or {}).get('evidence'))]
    final_leak = [r for r in rows if r['gate_status'] not in ('ready_for_validation', 'candidate', 'undetermined')]

    # regate_review_needed: row downgraded *to* dentist_multi but its NETWORK carries mso/platform/pe evidence
    net_has_platform = {n['authorized_official']: bool(n.get('mso_platform_pe_evidence'))
                        for n in networks}
    regate_review_needed = []
    for r in rows:
        rn = r.get('regate_note') or ''
        if '->dentist_multi' in rn and net_has_platform.get(r['network']):
            regate_review_needed.append({
                'location_id': r['location_id'], 'network': r['network'],
                'name': r['name'], 'regate_note': rn,
                'network_mso_platform_pe_evidence': summaries.get(r['network'], {}).get('mso_platform_pe_evidence'),
                'flag': 'per-row re-gate may have missed network-level MSO/platform evidence — Gate Owner reconcile',
            })

    regate_audit = [{'location_id': r['location_id'], 'network': r['network'],
                     'candidate_tier': r['candidate_tier'], 'gate_status': r['gate_status'],
                     'regate_note': r['regate_note']} for r in rows if r.get('regate_note')]
    candidates_unresolved = [{'location_id': r['location_id'], 'network': r['network'], 'name': r['name'],
                              'candidate_tier': r['candidate_tier'], 'gate_status': r['gate_status'],
                              'reasoning': r['reasoning']}
                             for r in rows if r['gate_status'] in ('candidate', 'undetermined')]
    specialist_flags = [{'location_id': r['location_id'], 'network': r['network'], 'name': r['name'],
                         'reasoning': r['reasoning']}
                        for r in rows if r['candidate_tier'] == 'undetermined'
                        and re.search(r'specialist|ortho|endo|perio|oral surg|maxillofac|pediatric|pedodont|prosthodont|implant', (r['reasoning'] or ''), re.I)]
    already_corp = [{'location_id': r['location_id'], 'network': r['network'], 'name': r['name'],
                     'current_db_entity_classification': r['current_db_entity_classification'],
                     'candidate_tier': r['candidate_tier']}
                    for r in rows if r['current_db_entity_classification'] in CORP]
    # new intelligence: network whose evidence points to DSO/MSO but is NOT currently corporate in DB
    new_intel = []
    for n in networks:
        net_rows = [r for r in rows if r['network'] == n['authorized_official']]
        any_corp_db = any(r['current_db_entity_classification'] in CORP for r in net_rows)
        points_dso = (n['recommended_tier_modal'] in ('stealth_dso', 'branded_dso')) or bool(n.get('mso_platform_pe_evidence'))
        if points_dso and not any_corp_db:
            new_intel.append({
                'authorized_official': n['authorized_official'], 'rank': n['rank'],
                'recommended_tier_modal': n['recommended_tier_modal'],
                'mso_platform_pe_evidence': n.get('mso_platform_pe_evidence'),
                'brand_trade_names': n.get('brand_trade_names'),
                'note': 'evidence points to DSO/MSO structure but no location currently corporate in DB — candidate hidden consolidator',
            })

    per_network_oneliner = [
        f"#{n['rank']} r{n['reach']} {n['authorized_official']}: {n['owner_type_verdict']} / modal={n['recommended_tier_modal']}"
        + (f" / MSO+PE: {(n['mso_platform_pe_evidence'] or '')[:80]}" if n.get('mso_platform_pe_evidence') else '')
        for n in networks]

    qa = {
        '_meta': {'artifact': 'AO Wave 3 QA', 'generated': DATE, 'paired_deliverable': os.path.basename(OUT),
                  'no_db_write': True, 'gate_ceiling': 'ready_for_validation'},
        'validation_guards': {
            'networks_ok': res.get('networks_ok'), 'networks_total': res.get('networks_total'),
            'n_locations': len(rows),
            'orphan_location_ids_not_in_targets': orphans,
            'within_wave_network_collisions': collisions,
            'ready_for_validation_uncorroborated': rfv_uncorroborated,
            'gate_ceiling_violations_final_leak': final_leak,
            'overlaps_with_prior_waves': overlaps_prior,
            'PASS': (not orphans and not collisions and not rfv_uncorroborated and not final_leak),
        },
        'tallies': {
            'tier_tally': res.get('tier_tally'), 'gate_tally': res.get('gate_tally'),
            'verdict_tally': res.get('verdict_tally'),
            'n_ready_for_validation': len(rfv),
            'reach_split': {'reach3': deliverable['_meta']['n_reach3'], 'reach2_strong': deliverable['_meta']['n_reach2_strong']},
        },
        'regate_audit': regate_audit,
        'regate_review_needed': regate_review_needed,
        'candidates_unresolved': candidates_unresolved,
        'specialist_or_undetermined_flags': specialist_flags,
        'already_corporate_in_db': already_corp,
        'new_intelligence_summary': new_intel,
        'per_network_oneliner': per_network_oneliner,
    }
    json.dump(qa, open(QA, 'w'), indent=2)

    print(f"WROTE {OUT}")
    print(f"WROTE {QA}")
    print(f"networks={len(networks)} rows={len(rows)} rfv={len(rfv)} "
          f"candidates={len(candidates_unresolved)} regate_review_needed={len(regate_review_needed)} "
          f"already_corp_db={len(already_corp)} new_intel={len(new_intel)}")
    print("GUARDS PASS:", qa['validation_guards']['PASS'],
          "| orphans:", len(orphans), "collisions:", len(collisions),
          "rfv_uncorroborated:", len(rfv_uncorroborated), "final_leak:", len(final_leak),
          "prior_overlaps:", len(overlaps_prior))


if __name__ == '__main__':
    main()
