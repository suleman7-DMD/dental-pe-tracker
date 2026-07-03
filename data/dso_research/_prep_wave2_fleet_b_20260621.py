"""
Fleet B WAVE-2 feed prep.  READ-ONLY on the DB.  Writes candidate feed batches only.
1. Refresh exclusion set: existing 498 + my wave-1 queue (361) + main reach5 networks (84).
2. Lane 3: gate-filter the 6 prepared dense-ZIP batches (drop excluded-GP-class / DA / already-tiered / non-IL / excluded-set).
3. Lane 1 Tier B: re-mine practice_intel prose for EXPLICIT ownership/structure phrases; keep only high-confidence rows, drop weak boilerplate.
No DB writes, no LEDGER/PROGRESS writes.
"""
import json, glob, os, re, sqlite3, collections

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DR = os.path.join(ROOT, "data", "dso_research")
SH = os.path.join(DR, "_shards_fleet_b")
EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# ---- 1. refreshed exclusion set --------------------------------------------
excl = json.load(open(os.path.join(DR, "_exclusion_set_fleet_b_20260621.json")))
ex = excl["excluded_location_ids"]                      # dict lid -> [sources]
def add(lid, src):
    if not lid: return
    ex.setdefault(lid, [])
    if src not in ex[lid]: ex[lid].append(src)

q = json.load(open(os.path.join(DR, "ownership_evidence_queue_fleet_b_20260621.json")))
for bucket in ("classifications", "held", "rejected"):
    for r in q.get(bucket, []):
        add(r.get("location_id"), "fleet_b_wave1_queue")
for c in q.get("conflicts", []):
    add(c.get("location_id"), "fleet_b_wave1_queue")

r5 = json.load(open(os.path.join(DR, "ao_network_evidence_reach5_20260621.json")))
def find_lids(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "location_id" and isinstance(v, str): acc.add(v)
            else: find_lids(v, acc)
    elif isinstance(o, list):
        for x in o: find_lids(x, acc)
r5l = set(); find_lids(r5, r5l)
for lid in r5l: add(lid, "main_reach5_ao")

excl["_meta"]["updated_20260621_wave2"] = {
    "added_wave1_queue": True, "added_main_reach5": len(r5l), "total_excluded": len(ex)}
json.dump(excl, open(os.path.join(DR, "_exclusion_set_fleet_b_20260621.json"), "w"), indent=1)
EXSET = set(ex.keys())
print(f"exclusion set now {len(EXSET)} location_ids (+wave1 queue, +{len(r5l)} reach5)")

# ---- gate helper (mirror validate_rows location checks) --------------------
def gate(lid):
    loc = conn.execute("""
        SELECT pl.state, pl.zip, pl.primary_npi, pl.org_npi,
               pl.entity_classification AS ec, pl.ownership_tier, wz.state AS ws
        FROM practice_locations pl
        LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
        WHERE pl.location_id=?""", (lid,)).fetchone()
    if not loc: return "no_loc"
    if loc["ws"] != "IL" or (loc["state"] or "").upper() != "IL": return "not_IL"
    if loc["ec"] in EXCLUDED_GP_CLASSES: return f"excluded:{loc['ec']}"
    if loc["ownership_tier"]: return "already_tiered"
    da = str(loc["primary_npi"] or "").startswith("DA_") and str(loc["org_npi"] or "").startswith("DA_")
    if da: return "da_only"
    return "ok"

def load_batch(f):
    d = json.load(open(f))
    return d if isinstance(d, list) else d.get("rows", d.get("locations", d.get("classifications", [])))

# ---- 2. Lane 3: gate-filter the 6 dense-ZIP batches ------------------------
lane3_rows, drop3 = [], collections.Counter()
for f in sorted(glob.glob(os.path.join(SH, "_batch_lane3_*.json"))):
    for r in load_batch(f):
        lid = r.get("location_id")
        if lid in EXSET: drop3["in_exclusion_set"] += 1; continue
        g = gate(lid)
        if g != "ok": drop3[g] += 1; continue
        lane3_rows.append(r)
print(f"\nLane 3: {len(lane3_rows)} GP-eligible rows kept; dropped {dict(drop3)}")

# rebuild balanced Lane 3 batches grouped by ZIP (keep ZIP cohesion for agents)
byzip = collections.defaultdict(list)
for r in lane3_rows: byzip[str(r.get("zip"))[:5]].append(r)
l3batches = []
for z in sorted(byzip):
    l3batches.append((z, byzip[z]))
for i, (z, rows) in enumerate(l3batches, 1):
    json.dump(rows, open(os.path.join(SH, f"_feed_w2_lane3_{i:02d}.json"), "w"), indent=1)
print("Lane 3 feeds:", [(z, len(rows)) for z, rows in l3batches])

# ---- 3. Lane 1 Tier B: mine prose for EXPLICIT ownership/structure ---------
pool = json.load(open(os.path.join(DR, "_lane1_intel_signal_pool_fleet_b.json")))
pool = pool if isinstance(pool, list) else pool.get("rows", [])
tierB = [r for r in pool if not ((r.get("acq") in (1, "1", True)) or r.get("brands"))]

# STRONG = explicit DSO/MSO/platform/PE structure OR a real acquisition/merger event
# OR an explicit MULTI-location ownership statement. Excludes generic "owner-operated",
# "solo owner", "privately owned" boilerplate that every independent dossier contains.
STRONG = re.compile(
    r"\b("
    r"DSO|MSO|management services|management compan|management organization|"
    r"support organization|dental support|private equity|portfolio compan|parent compan|"
    r"backed by [A-Z]|acquired by|acquisition by|bought by|merged with|merger with|"
    r"joined (?:the |a )?[A-Z][\w&. ]+ (?:group|network|dental|partners)|"
    r"part of (?:the |a )?[A-Z][\w&. ]+ (?:group|network|chain|platform)|"
    r"owns? (?:two|three|four|five|six|\d+|multiple|several) (?:locations|offices|practices)|"
    r"operates (?:two|three|four|\d+|multiple|several) (?:locations|offices|practices)|"
    r"(?:second|third|other|sister) (?:location|office|practice)|"
    r"multi[- ]location (?:group|practice|dental) (?:owned|operated|run) by|"
    r"locations in [A-Z][\w ]+ and [A-Z]"
    r")\b", re.I)
# NAMED owner tied to a multi-location pool flag = strong dentist_multi lead
NAMED_OWNER = re.compile(r"\bowned by (?:Dr\.?\s*)?[A-Z][a-z]+|"
                         r"\b(?:Dr\.?\s*)?[A-Z][a-z]+ (?:owns|founded|established) (?:the|this|two|three|multiple|her|his)", re.I)
PROSE_COLS = ("overall_assessment", "acquisition_details", "red_flags", "green_flags",
              "provider_notes", "doctor_notes", "escalation_findings")

tierB_hi, tierB_drop = [], 0
for r in tierB:
    lid = r.get("location_id")
    if lid in EXSET: tierB_drop += 1; continue
    if gate(lid) != "ok": tierB_drop += 1; continue
    npis = [str(n) for n in (r.get("npis") or []) if n and not str(n).startswith("DA_")]
    if not npis: continue
    qmarks = ",".join("?" * len(npis))
    rows = conn.execute(
        f"SELECT * FROM practice_intel WHERE npi IN ({qmarks})", npis).fetchall()
    snippets, urls, kinds = [], [], set()
    multi = bool(r.get("multi"))
    for pr in rows:
        d = dict(pr)
        for col in PROSE_COLS:
            txt = d.get(col)
            if not txt: continue
            s = str(txt)
            m = STRONG.search(s)
            if m:
                kinds.add("structure_or_event")
                i = max(0, m.start() - 60); j = min(len(s), m.end() + 90)
                snippets.append(f"[{col}|STRONG] …{s[i:j].strip()}…")
            mo = NAMED_OWNER.search(s)
            if mo and multi:                 # named owner + multi-loc flag = dentist_multi lead
                kinds.add("named_multi_owner")
                i = max(0, mo.start() - 40); j = min(len(s), mo.end() + 110)
                snippets.append(f"[{col}|NAMED+MULTI] …{s[i:j].strip()}…")
        if d.get("verification_urls"):
            urls += [u for u in re.split(r"[\s,]+", str(d["verification_urls"])) if u.startswith("http")]
    if snippets:
        out = dict(r); out["_explicit_ownership_snippets"] = snippets[:4]
        out["_signal_kinds"] = sorted(kinds)
        out["_intel_urls"] = list(dict.fromkeys(urls))[:5]
        tierB_hi.append(out)

print(f"\nTier B: {len(tierB)} raw -> {len(tierB_hi)} high-confidence explicit-ownership rows "
      f"(dropped {tierB_drop} excluded/gated; rest had no explicit phrase = boilerplate, skipped)")

# split Tier B hi into batches of ~25
B = 25
tb_batches = [tierB_hi[i:i+B] for i in range(0, len(tierB_hi), B)]
for i, batch in enumerate(tb_batches, 1):
    json.dump(batch, open(os.path.join(SH, f"_feed_w2_lane1B_{i:02d}.json"), "w"), indent=1)
print("Tier B feeds:", [len(b) for b in tb_batches])

# show a few sample snippets so I can sanity-check signal quality
print("\nSample Tier B explicit-ownership snippets:")
for r in tierB_hi[:6]:
    print(f"  {r.get('name')} ({r.get('zip')}): {r['_explicit_ownership_snippets'][0][:130]}")

print("\nWAVE-2 FEED SUMMARY:")
print(f"  Lane 3 (zero-corp sweep): {len(l3batches)} feeds, {sum(len(x) for _,x in l3batches)} rows")
print(f"  Lane 1B (explicit ownership): {len(tb_batches)} feeds, {len(tierB_hi)} rows")
print(f"  total agents needed: {len(l3batches)+len(tb_batches)}")
