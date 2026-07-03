#!/usr/bin/env python3
"""
Ownership-Census Engine  (2026-06-20)
=====================================
Phase-1 foundation for the "god view" mandate: classify every real GP practice
in the watched Chicagoland (IL) ZIPs by COMMON OWNERSHIP, deterministically and
for free, BEFORE any web verification.

User's taxonomy (binding):
  - Independent           = one dentist owns exactly ONE practice (a singleton).
  - Corporate/consolidated = the owner operates MORE THAN ONE practice (a DSO),
                             whether or not PE-backed.
      * branded / PE-backed DSO  (Heartland=KKR, Aspen, Western=New Mountain, ...)
      * dentist-owned DSO        (multi-location, no PE evidence)
  - Undetermined          = single location, multiple dentists, ownership unclear
                            -> DENOTED honestly, never force-classified.

Method: union-find over locations that share an OWNER-IDENTITY key. Six keys,
each independent, so corroboration = confidence (this is what separates a real
chain like ASHTON DENTAL PC from a common-surname coincidence like PATEL DENTAL):
  1. real EIN              (placeholders 000000000 / 125555555 dropped)
  2. service phone         (same number at 2+ distinct addresses)
  3. authorized official   (org NPI's owner name across 2+ locations)
  4. mailing HQ            (org mailing addr that DIFFERS from service addr = MSO)
  5. legal / brand name    (non-generic normalized practice name; WEAK alone)
  6. self-reported DSO     (affiliated_dso + affiliated_pe_sponsor in our own data)

Cluster confidence:
  HIGH    -> >=2 distinct STRONG keys (EIN/phone/official/mailing) link it,
             OR a known GP-DSO brand on the cluster,
             OR >=1 already-corporate member + >=1 strong key.
  MEDIUM  -> exactly 1 strong key links >=2 locations.
  LOW     -> name-only link (the Patel trap). Candidate, never auto-anything.

OUTPUT: data/dso_research/ownership_census_YYYYMMDD.json  (candidate map only).
NO entity_classification is written. NO denominators change. Read-only on the DB.
"""
import sqlite3, re, json, sys
from collections import defaultdict

DB = "data/dental_pe_tracker.db"
OUT = "data/dso_research/ownership_census_20260620.json"

# GP-eligible location classes (exclude specialist/non-clinical/synthetic/dupes)
EXCLUDE_CLASSES = ('specialist','non_clinical','da_unverified','duplicate_location','org_only_npi')
INDEP_CLASSES = ('solo_established','solo_new','solo_high_volume','solo_inactive',
                 'family_practice','small_group','large_group')
CORP_CLASSES = ('dso_regional','dso_national')

EIN_PLACEHOLDERS = {'000000000','125555555','0','','111111111','999999999'}

# Known GP DSO brands -> (pe_sponsor or None, is_gp). Ortho/denture-only brands are
# is_gp=False: their tag on a GP NPI is an address-share leak (see 2026-06-20 audit),
# so they NEVER mark a GP location corporate here.
DSO_BRANDS = {
    'heartland dental':            ('KKR', True),
    'great lakes dental partners': ('Shore Capital', True),
    'western dental':              ('New Mountain Capital', True),
    'aspen dental':                ('ADMI / Leonard Green / American Securities', True),
    'dental dreams':               (None, True),
    '1st family dental':           (None, True),
    'all family dental & braces':  ('United Dental Partners', True),
    'all family dental':           ('United Dental Partners', True),
    'dental 360':                  (None, True),
    'webster dental management':   (None, True),
    'webster dental care':         (None, True),
    'comfort dental':              (None, True),
    'familia dental':              (None, True),
    'midwest dental':              ('Gryphon Investors', True),
    'choice dental group':         (None, True),
    'dentologie':                  (None, True),
    'affordable care':             ('Berkshire Partners', True),  # denture/implant; verify
    'affordable dentures & implants':('Berkshire Partners', True),
    'dental salon':                (None, True),
    # ORTHO / specialist DSOs -> not GP; tag on a GP NPI = leak
    'orthodontic experts':         ('PE ortho', False),
    'smile doctors':               ('Thomas H. Lee', False),
}

GENERIC_NAME = {
 '','DENTAL','FAMILY DENTAL','DENTAL CARE','DENTAL GROUP','SMILE','SMILES','DENTISTRY',
 'FAMILY DENTISTRY','DENTAL CENTER','FAMILY DENTAL CARE','GENERAL DENTISTRY',
 'PEDIATRIC DENTISTRY','DENTAL ARTS','DENTAL OFFICE','DENTAL ASSOCIATES','SMILE DENTAL',
 'FAMILY DENTAL GROUP','GENTLE DENTAL','DENTAL STUDIO','MODERN DENTAL','DENTAL CLINIC',
}
GENERIC_OFFICIAL_LAST = {'','NONE','N/A','NA','NULL','OWNER','PRESIDENT','DENTIST'}

def norm_name(s):
    if not s: return ''
    s = s.upper()
    s = re.sub(r'[^A-Z0-9 ]',' ',s)
    s = re.sub(r'\b(PC|LLC|LTD|DDS|DMD|INC|SC|PLLC|MS|MD|THE|OF|AND|LLP|PA|CO|CORP|PROF|SVC)\b',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def norm_addr(s):
    if not s: return ''
    s = s.upper()
    s = re.sub(r'[^A-Z0-9 ]',' ',s)
    s = re.sub(r'\b(SUITE|STE|UNIT|APT|FL|FLOOR|RM|ROOM|BLDG|#|NO)\b',' ',s)
    s = re.sub(r'\b(STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|LANE|LN|COURT|CT|PLACE|PL|HIGHWAY|HWY|PARKWAY|PKWY|NORTH|SOUTH|EAST|WEST|N|S|E|W)\b',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def digits(s):
    return re.sub(r'\D','',s or '')

def brand_lookup(name):
    if not name: return None
    n = name.strip().lower()
    for b,(pe,gp) in DSO_BRANDS.items():
        if b in n:
            return (b, pe, gp)
    return None

def main():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row

    # --- pull owner-identity columns for every practice (NPI) once ---
    prac = {}
    for r in c.execute("""SELECT npi, ein, da_ein2, da_ein3, parent_org_tin,
                 authorized_official_last_name aol, authorized_official_first_name aof,
                 mailing_address ma, mailing_zip mz, parent_company pcomp,
                 affiliated_dso adso, affiliated_pe_sponsor ape, da_legal_name dlegal
                 FROM practices"""):
        prac[r['npi']] = r

    # --- pull watched-IL GP locations ---
    locs = c.execute(f"""
       SELECT pl.location_id lid, pl.practice_name nm, pl.normalized_address na,
              substr(pl.zip,1,5) z, pl.city, pl.phone, pl.ein lein,
              pl.entity_classification ec, pl.provider_count pcount,
              pl.affiliated_dso ladso, pl.affiliated_pe_sponsor lape,
              pl.primary_npi pn, pl.org_npi onpi, pl.buyability_score bs
       FROM practice_locations pl
       JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code AND w.state='IL'
       WHERE pl.entity_classification NOT IN {EXCLUDE_CLASSES}
    """).fetchall()

    n = len(locs)
    # per-location key sets
    L = []  # list of dicts
    for r in locs:
        eins=set(); officials=set(); mailings=set(); brands=set(); pes=set()
        svc = norm_addr(r['na'])
        # location-level keys
        if r['lein'] and digits(r['lein']) not in EIN_PLACEHOLDERS and len(digits(r['lein']))>=9:
            eins.add(digits(r['lein']))
        bl = brand_lookup(r['ladso'])
        # gather owner-entity NPI keys (primary + org only -- NOT associates)
        for npi in (r['pn'], r['onpi']):
            p = prac.get(npi)
            if not p: continue
            for ek in (p['ein'], p['da_ein2'], p['da_ein3'], p['parent_org_tin']):
                d = digits(ek)
                if d and d not in EIN_PLACEHOLDERS and len(d)>=9: eins.add(d)
            last = (p['aol'] or '').strip().upper()
            first = (p['aof'] or '').strip().upper()
            if last and last not in GENERIC_OFFICIAL_LAST and len(last)>=2:
                officials.add(f"{last}|{first[:1]}")
            m = norm_addr(p['ma'])
            mz = digits(p['mz'])[:5]
            if m and len(m)>=6 and m != svc:           # mailing HQ that differs from service
                mailings.add(f"{m}|{mz}")
            if not bl: bl = brand_lookup(p['adso'])
            if p['ape'] and str(p['ape']).strip().lower() not in ('','nan','none'):
                pes.add(str(p['ape']).strip())
        if not bl:
            pp = prac.get(r['pn'])
            bl = brand_lookup(r['nm']) or (brand_lookup(pp['dlegal']) if pp else None)
        nm = norm_name(r['nm'])
        L.append(dict(lid=r['lid'], nm=r['nm'], nkey=(nm if nm not in GENERIC_NAME and len(nm)>=4 else None),
                      z=r['z'], city=r['city'], ec=r['ec'], pcount=r['pcount'] or 0,
                      svc=svc, phone=digits(r['phone']) if len(digits(r['phone']))==10 else None,
                      eins=eins, officials=officials, mailings=mailings,
                      brand=bl, pes=pes, bs=r['bs']))

    # --- build union-find over STRONG keys (+name as weak) ---
    parent=list(range(n))
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[ra]=rb

    # index locations by each key; union members sharing a key; record link types
    link_types=defaultdict(set)  # root -> set of strong key types present
    def index_and_link(getter, kind, strong):
        idx=defaultdict(list)
        for i,l in enumerate(L):
            for k in getter(l): idx[k].append(i)
        for k,members in idx.items():
            if len(members)<2: continue
            # for phone: require distinct service addresses (else same office dup)
            if kind=='phone':
                addrs={L[m]['svc'] for m in members}
                if len(addrs)<2:
                    continue
            base=members[0]
            for m in members[1:]: union(base,m)
            for m in members:
                link_types[m].add(kind)  # provisional; recombined after find()

    index_and_link(lambda l: l['eins'],     'ein',      True)
    index_and_link(lambda l: [l['phone']] if l['phone'] else [], 'phone', True)
    index_and_link(lambda l: l['officials'],'official', True)
    index_and_link(lambda l: l['mailings'], 'mailing',  True)
    index_and_link(lambda l: [l['nkey']] if l['nkey'] else [], 'name', False)

    # collect clusters
    clusters=defaultdict(list)
    for i in range(n): clusters[find(i)].append(i)

    # recompute, per cluster, which strong key types actually corroborate (>=2 members share)
    def cluster_keytypes(members):
        kt=set()
        for kind,getter in (('ein',lambda l:l['eins']),('phone',lambda l:[l['phone']] if l['phone'] else []),
                            ('official',lambda l:l['officials']),('mailing',lambda l:l['mailings']),
                            ('name',lambda l:[l['nkey']] if l['nkey'] else [])):
            cnt=defaultdict(int)
            for m in members:
                for k in getter(L[m]): cnt[k]+=1
            if kind=='phone':
                # need same key across >=2 distinct addresses
                for k in list(cnt):
                    addrs={L[m]['svc'] for m in members if (L[m]['phone']==k)}
                    if len(addrs)<2: cnt[k]=0
            if any(v>=2 for v in cnt.values()): kt.add(kind)
        return kt

    multi=[]; singletons=[]
    for root,members in clusters.items():
        addr_set={L[m]['svc'] for m in members}
        if len(members)>=2 and len(addr_set)>=2:
            multi.append((root,members))
        else:
            singletons.append((root,members))

    out_clusters=[]
    for root,members in multi:
        kt=cluster_keytypes(members)
        strong = kt - {'name'}
        brands={L[m]['brand'][0] for m in members if L[m]['brand']}
        gp_brands={L[m]['brand'][0] for m in members if L[m]['brand'] and L[m]['brand'][2]}
        pes=set()
        for m in members:
            pes|=L[m]['pes']
            if L[m]['brand'] and L[m]['brand'][1]: pes.add(L[m]['brand'][1])
        already_corp=sum(1 for m in members if L[m]['ec'] in CORP_CLASSES)
        indep=[m for m in members if L[m]['ec'] in INDEP_CLASSES]
        # confidence
        if len(strong)>=2 or gp_brands or (already_corp>=1 and len(strong)>=1):
            tier='HIGH'
        elif len(strong)>=1:
            tier='MEDIUM'
        else:
            tier='LOW'   # name-only
        # suggested bucket
        if gp_brands:
            pe_backed = any(L[m]['brand'] and L[m]['brand'][1] for m in members if L[m]['brand'] and L[m]['brand'][2])
            bucket = 'pe_dso' if (pes and pe_backed) else 'branded_dso'
        else:
            bucket = 'dso_candidate'
        out_clusters.append(dict(
            cluster_id=f"c{root}", tier=tier, bucket=bucket,
            n_locations=len(members), n_zips=len({L[m]['z'] for m in members}),
            already_corporate=already_corp, net_new_candidates=len(indep),
            link_keys=sorted(kt), strong_keys=sorted(strong),
            gp_brands=sorted(gp_brands), all_brands=sorted(brands), pe_sponsors=sorted(pes),
            members=[dict(lid=L[m]['lid'], name=L[m]['nm'], zip=L[m]['z'], city=L[m]['city'],
                          ec=L[m]['ec'], providers=L[m]['pcount'], buyability=L[m]['bs']) for m in members],
        ))
    # sort: HIGH first, then by net-new candidates desc
    rank={'HIGH':0,'MEDIUM':1,'LOW':2}
    out_clusters.sort(key=lambda x:(rank[x['tier']], -x['net_new_candidates'], -x['n_locations']))

    # undetermined singletons: single location, multi-dentist, ambiguous ownership
    undet=[]
    for root,members in singletons:
        m=members[0]; l=L[m]
        if l['ec'] in ('small_group','large_group') and l['pcount']>=3:
            undet.append(dict(lid=l['lid'], name=l['nm'], zip=l['z'], city=l['city'],
                              ec=l['ec'], providers=l['pcount'], buyability=l['bs'],
                              reason='single-location group, ownership may be split across dentists; cannot confirm multi-practice ownership'))

    # ---- summary ----
    tot=n
    in_multi=sum(c['n_locations'] for c in out_clusters)
    netnew={t:0 for t in ('HIGH','MEDIUM','LOW')}
    clcount={t:0 for t in ('HIGH','MEDIUM','LOW')}
    for c0 in out_clusters:
        netnew[c0['tier']]+=c0['net_new_candidates']; clcount[c0['tier']]+=1
    already_corp_total=sum(1 for l in L if l['ec'] in CORP_CLASSES)

    summary=dict(
        generated='2026-06-20', scope='watched IL GP locations',
        total_gp_locations=tot,
        already_corporate=already_corp_total,
        multi_unit_clusters=len(out_clusters),
        locations_in_multi_unit_clusters=in_multi,
        clusters_by_tier=clcount,
        net_new_corporate_candidates_by_tier=netnew,
        undetermined_single_location_groups=len(undet),
        note=("net_new = currently-independent locations sitting in a multi-location common-ownership "
              "cluster. HIGH = multi-key corroborated or known GP-DSO brand (promote after light web check). "
              "MEDIUM = single strong key (verify). LOW = name-only (Patel trap; never auto-flip). "
              "NOTHING here is classified yet -- this is a candidate map."),
    )

    json.dump(dict(summary=summary, clusters=out_clusters, undetermined=undet),
              open(OUT,'w'), indent=1)

    # ---- console report ----
    print("="*72)
    print("OWNERSHIP-CENSUS ENGINE  --  watched IL GP locations")
    print("="*72)
    for k,v in summary.items():
        if k=='note': continue
        print(f"  {k:42} {v}")
    print(f"\n  -> floor today: {already_corp_total} corporate")
    print(f"  -> if ALL high-tier net-new verify: {already_corp_total}+{netnew['HIGH']} = {already_corp_total+netnew['HIGH']} corporate")
    print(f"  -> +medium: +{netnew['MEDIUM']} more candidates to verify")
    print(f"  -> LOW (name-only, NOT auto): +{netnew['LOW']}")
    print(f"\nTOP 30 CLUSTERS (tier | bucket | locs | net-new indep | keys | brands):")
    for c0 in out_clusters[:30]:
        nm=c0['members'][0]['name'][:26]
        print(f"  [{c0['tier']:6}] {c0['bucket']:13} locs={c0['n_locations']:2} new={c0['net_new_candidates']:2} "
              f"corp={c0['already_corporate']:2} keys={','.join(c0['strong_keys']) or 'name':22} "
              f"{','.join(c0['gp_brands'])[:22]:22} :: {nm}")
    print(f"\nUndetermined single-location groups (provider_count>=3, denoted not classified): {len(undet)}")
    print(f"\nWrote {OUT}")

if __name__=='__main__':
    main()
