#!/usr/bin/env python3
"""Office-census rapid validation (Track A): a durable work queue for checking
existing directory rows against the live web, one row at a time.

  python3 scrapers/office_census_rapid.py init                  # build the queue once
  python3 scrapers/office_census_rapid.py next --n 10 --session S
  python3 scrapers/office_census_rapid.py record --session S <<'EOF'
  {"candidate_id": "loc:...", "decision": "VALID", ...}
  EOF
  python3 scrapers/office_census_rapid.py lookup --address "135 N Arlington Heights Rd" --zip 60089
  python3 scrapers/office_census_rapid.py status
  python3 scrapers/office_census_rapid.py list --decision ESCALATE [--sample 20]
  python3 scrapers/office_census_rapid.py check

Protocol: data/office_census/RAPID_VALIDATION_RUNBOOK.md.

Rapid checks are NOT census adjudications. They are appended to
data/office_census/rapid/checks.jsonl, separate from research_ledger.jsonl,
so a rapid run and a ZIP reconciliation session never write the same file.
Nothing here writes SQLite, Supabase, practice_locations or the ledger.

Lanes: rows in downtown ZIPs or with building-merge flags go to the building
lane (suite-level reconciliation, the 60602 protocol), never to rapid review.
Rows with a ledger decision, or in a ZIP whose current rows were swept, are
already adjudicated and are skipped.
"""
import argparse
import collections
import concurrent.futures
import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import random
import re
import socket
import sqlite3
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census as oc  # noqa: E402  (no project imports; AST normalizer only)

RULES = "rapid-2026-09-25.1"
SEED = 20260925
CALIBRATION_N = 100
CLAIM_HOURS = 4
RAPID_DIR = oc.OUT_DIR / "rapid"

# Dense downtown ZIPs: 60602 showed building rows hiding 32 offices and 0 of 10
# ordinary rows confirmable as listed. Whole ZIP goes to the building lane.
DOWNTOWN_ZIPS = {"60601", "60602", "60603", "60604", "60605", "60606", "60607",
                 "60610", "60611", "60654", "60661"}

DECISIONS = ("VALID", "VALID_CORRECTED", "IDENTITY_ONLY", "NOT_CURRENT_GP",
             "IDENTITY_PROBLEM", "NO_WEB_EVIDENCE", "ESCALATE")
NOT_CURRENT_REASONS = {"closed", "moved", "home_or_registration", "specialist_only",
                       "nonclinical", "duplicate"}
ESCALATE_REASONS = {"conflict", "gp_scope", "operating_status", "other"}
EVIDENCE_KINDS = {"first_party_site", "dso_locator", "maps_panel", "iema_registry", "listing",
                  "registry", "real_estate", "news_or_obituary", "other"}
CURRENT_KINDS = {"first_party_site", "dso_locator", "maps_panel"}
SIGNALS = {"practice_sold", "owner_deceased", "owner_retired", "successor_practice", "rebranded",
           "dso_or_group_branded", "multi_location_practice", "other_offices_in_building",
           "website_dead", "website_wrong_business", "phone_belongs_elsewhere",
           "real_estate_listing", "home_address", "hiring_seen"}
GP_SCOPES = {"gp", "mixed", "specialist_only", "unknown"}
OBSERVED_FIELDS = {"name", "address", "suite", "phone", "website", "zip"}

IL_AREA_CODES = {"217", "224", "309", "312", "331", "447", "464", "618", "630", "708",
                 "730", "773", "779", "815", "847", "872"}
SPECIALTY_TAX = {"1223E0200X": "endo", "1223P0221X": "pediatric", "1223P0300X": "perio",
                 "1223P0700X": "prosth", "1223S0112X": "oral surgery", "1223X0400X": "ortho",
                 "1223D0001X": "public health", "1223P0106X": "oral path", "1223X0008X": "radiology"}
STREET_SUFFIXES = {"st", "ave", "rd", "blvd", "dr", "ln", "ct", "pl", "pkwy", "hwy", "way", "cir",
                   "ter", "trl", "sq", "plz", "pike", "cv", "row", "aly", "xing", "pass", "path"}
RESIDENTIAL_SUFFIXES = {"ln", "ct", "cir", "pass", "trl", "way", "ter", "cv", "path"}
DENTAL_WORD_RE = re.compile(
    r"dental|dentist|dentistry|smile|teeth|tooth|ortho|oral|family|clinic|care|center|centre|"
    r"studio|group|associates|assoc|implant|health|kids|perio|endo", re.I)
LEGAL_TOKENS = {"dds", "dmd", "pc", "ltd", "llc", "inc", "pllc", "sc", "ms", "md", "fagd", "magd",
                "facd", "and", "dr"}
STATUS_RE = re.compile(
    oc.CLOSURE_RE.pattern + "|" + oc.MOVE_RE.pattern + "|" + oc.SUCCESSOR_RE.pattern +
    r"|deceased|passed away|\bdied\b|retir\w*|\bsold\b|for sale|for lease|\bCLOSED\b|new owner",
    re.I)


# ---- paths -------------------------------------------------------------------
class P:
    """Rapid-run files; --rapid-dir moves all of them (tests, smoke runs)."""
    dir = RAPID_DIR

    @classmethod
    def set(cls, d):
        cls.dir = pathlib.Path(d)


def path(name):
    return P.dir / name


@contextlib.contextmanager
def locked():
    P.dir.mkdir(parents=True, exist_ok=True)
    with open(path(".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def read_jsonl(p):
    out = []
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass  # a concurrent writer's partial line; never fatal for readers
    return out


# ---- text helpers ------------------------------------------------------------
def title_token(t):
    if t in oc.DIRECTIONALS and len(t) <= 2:
        return t.upper()
    if re.match(r"^\d+[nsew]\d+$", t):          # DuPage grid address, e.g. 2s676
        return t.upper()
    if t[:1].isdigit():
        return t                                  # 75th, 183rd
    return t[:1].upper() + t[1:]


def split_run_together(address):
    # '4209stcharles rd' -> '4209 stcharles rd' (grid addresses like 2s676 stay intact)
    a = re.sub(r"^(\d+)([a-z]{3,})", r"\1 \2", (address or "").strip().lower())
    return re.sub(r"^(\d+) st(?=[a-z]{4,}\b)", r"\1 st ", a)


def address_phrases(address):
    """Quoted street phrases for search: house number + directional + street name, no suffix."""
    toks = re.findall(r"[a-z0-9]+", split_run_together(address))
    if not toks or not toks[0][:1].isdigit():
        return []
    body = toks[1:]
    if len(body) > 1 and body[-1] in STREET_SUFFIXES:
        body = body[:-1]
    if not body:
        return []
    phrase = " ".join(title_token(t) for t in [toks[0]] + body)
    out = [phrase]
    street = body[1:] if body[0] in oc.DIRECTIONALS and len(body) > 1 else body
    if street and street[0] == "st" and len(street) > 1:
        out.append(phrase.replace(" St ", " Saint ", 1))
    return out


def display_address(address):
    toks = split_run_together(address).split()
    return " ".join(title_token(t) for t in toks)


def city_title(city):
    return " ".join(w.capitalize() for w in str(city or "").split())


def fmt_phone(d):
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if d else None


def normalize_url(u):
    u = (u or "").strip()
    if not oc.present(u):
        return None
    u = u.split()[0]
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u


def host_of(u):
    try:
        h = urllib.parse.urlparse(u).hostname or ""
    except ValueError:
        return ""
    return h.lower()


def google(q):
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)


def maps(q):
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(q)


def name_tokens(name):
    # dots join initialisms (D.D.S. -> dds); commas separate ('DDS,PC' -> dds, pc)
    return re.findall(r"[a-z]+", str(name or "").lower().replace(".", ""))


def person_core(name):
    """'TIMOTHY L. STRAKA D.D.S., L.L.C.' -> 'Timothy L Straka' (legal suffixes dropped)."""
    toks = [t for t in name_tokens(name) if t not in LEGAL_TOKENS]
    return " ".join(t.capitalize() for t in toks)


def name_is_trusted(name, flags, provider_names=()):
    """A stored name worth searching as a practice name. Generated names and
    person/registry names ('Nisbeth Basit G DDS', 'Francis Carla') are not."""
    if not oc.present(name) or "name_possibly_generated" in flags:
        return False
    if DENTAL_WORD_RE.search(str(name)):
        return True
    toks = name_tokens(name)
    if any(t in LEGAL_TOKENS - {"and", "dr"} for t in toks):
        return False
    core = {t for t in toks if len(t) > 1}
    return not any(core and core <= set(name_tokens(p)) for p in provider_names)


# ---- queue build -------------------------------------------------------------
def load_ledger_state():
    decided, swept = set(), set()
    for _, e in oc.read_ledger():
        if e.get("type") == "decision" and e.get("candidate_id"):
            decided.add(e["candidate_id"])
        if e.get("type") == "zip_sweep" and e.get("pass_type", e.get("stage")) == "current_rows":
            swept.add(str(e.get("zip")))
    return decided, swept


def db_path():
    for p in (os.environ.get("OFFICE_CENSUS_DB"), oc.DB_PATH,
              pathlib.Path.home() / "dental-pe-tracker" / "data" / "dental_pe_tracker.db"):
        if p and pathlib.Path(p).exists():
            return pathlib.Path(p)
    return None


def load_providers(npis):
    """npi -> (display name, specialty tag); empty when no DB is available."""
    p = db_path()
    if not p or not npis:
        return {}
    db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    out = {}
    npis = sorted(npis)
    for i in range(0, len(npis), 900):
        chunk = npis[i:i + 900]
        q = ("SELECT npi, practice_name, entity_type, taxonomy_code FROM practices WHERE npi IN (%s)"
             % ",".join("?" * len(chunk)))
        for npi, name, etype, tax in db.execute(q, chunk):
            if (etype or "").lower() == "individual" and oc.present(name):
                out[str(npi)] = (" ".join(w.capitalize() for w in str(name).split()),
                                 SPECIALTY_TAX.get(tax or ""))
    db.close()
    return out


def status_snippets(c):
    texts = []
    pe = c.get("prior_evidence") or {}
    texts.append((pe.get("job_hunt_check") or {}).get("note") or "")
    for m in pe.get("manual_corrections") or []:
        texts.append(m.get("note") or "")
    for h in pe.get("historical_observations") or []:
        for v in (h.get("evidence") or {}).values():
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    texts.extend(x for x in parsed if isinstance(x, str)) if isinstance(parsed, list) \
                        else texts.append(v)
                except ValueError:
                    texts.append(v)
    out, seen = [], set()
    for t in texts:
        for s in re.split(r"(?<=[.!?])\s+|\n", t):
            s = s.strip()
            if s and STATUS_RE.search(s) and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s[:240])
    return out[:3]


def prior_lines(c):
    pe = c.get("prior_evidence") or {}
    out = []
    j = pe.get("job_hunt_check")
    if j:
        out.append(f"site check {j.get('checked_at')} {j.get('website_status')}/{j.get('verification_status')}"
                   f" name={j.get('public_name')!r} {j.get('website_url') or ''}".strip())
    d = pe.get("ai_dossier")
    if d:
        out.append(f"dossier {d.get('researched_at')} ({d.get('quality')}) site={d.get('website_url')} "
                   f"google_reviews={d.get('google_review_count')} recent={d.get('google_recent_review')}")
    o = pe.get("ownership_census")
    if o:
        out.append(f"ownership review {o.get('reviewed_at')}: " + " ".join((o.get("evidence_urls") or [])[:2]))
    return out


def lane_of(c, decided, swept):
    if c["candidate_id"] in decided or c["zip"] in swept:
        return "census_done", "ledger decision or ZIP current rows already reconciled"
    flags = set(c.get("flags") or [])
    if c["zip"] in DOWNTOWN_ZIPS:
        return "building", "downtown ZIP (building-first)"
    if "high_provider_count" in flags:
        return "building", "high provider count"
    if len(c.get("suites_seen") or []) >= 3:
        return "building", "3+ suites at street"
    if {"multi_org_multi_phone", "multi_suite_multi_phone"} <= flags:
        return "building", "several orgs, suites and phones at street"
    return "rapid", None


def make_card(c, providers):
    flags = list(c.get("flags") or [])
    pe = c.get("prior_evidence") or {}
    j, d = pe.get("job_hunt_check") or {}, pe.get("ai_dossier") or {}
    city = city_title(c.get("city"))
    phone = oc.digits(c.get("phone"))
    site = None
    if j.get("website_status") == "live" and oc.present(j.get("website_url")):
        site = normalize_url(j["website_url"])
    site = site or normalize_url(c.get("website")) or normalize_url(d.get("website_url"))
    provs, prov_names = [], []
    for n in (c.get("source_refs") or {}).get("npis") or []:
        if str(n) in providers:
            nm, tag = providers[str(n)]
            prov_names.append(nm)
            provs.append(f"{nm} ({tag})" if tag else nm)
    public = j.get("public_name") if oc.present(j.get("public_name")) else (
        c.get("name") if name_is_trusted(c.get("name"), flags, prov_names) else None)
    # person to search when the stored name is a person/legal name: first GP provider,
    # else the stored name stripped of legal suffixes (never a generated name)
    person = next((p for p, s in zip(prov_names, provs) if p == s), prov_names[0] if prov_names else None)
    if not person and not public and "name_possibly_generated" not in flags:
        core = person_core(c.get("name"))
        person = core if len(core.split()) >= 2 else None
    last = (re.findall(r"[a-z]+", (c.get("address") or "").lower()) or [""])[-1]
    home_like = (last in RESIDENTIAL_SUFFIXES and not c.get("suite") and not c.get("suites_seen")
                 and (c.get("provider_count") or 0) <= 1 and not site)
    non_il = bool(phone) and phone[:3] not in IL_AREA_CODES

    q = {}
    phrases = address_phrases(c.get("address"))
    if phrases:
        addr = " OR ".join(f'"{p}"' for p in phrases)
        q["ADDR"] = f"dentist {addr} {city} IL"
    elif oc.present(c.get("address")):
        q["ADDR"] = f'dentist "{display_address(c["address"])}" {city} IL'
    if public:
        q["NAME"] = f'"{public}" {city} IL' + ("" if DENTAL_WORD_RE.search(public) else " dentist")
    if phone:
        q["PHONE"] = f'"{fmt_phone(phone)}" OR "{phone[:3]}-{phone[3:6]}-{phone[6:]}"'
    if person:
        q["PROVIDER"] = f'"{person}" dentist {city} IL'

    fl = set(flags)
    if fl & {"prior_note_moved", "prior_note_successor"}:
        route, order = "moved_or_successor", ["NAME", "PHONE", "ADDR", "PROVIDER"]
    elif home_like or non_il:
        route, order = "home_like", ["ADDR", "PROVIDER", "PHONE"]
    elif fl & {"multi_suite_multi_phone", "multi_org_multi_phone", "phone_shared_with_other_address"}:
        route, order = "multi_tenant", ["ADDR", "PHONE", "NAME"]
    elif not public:
        route, order = "untrusted_name", ["ADDR", "PROVIDER", "PHONE"]
    else:
        route, order = "default", ["ADDR", "NAME", "PHONE"]
    queries = [{"kind": k, "q": q[k]} for k in order if k in q]
    full_addr = f"{display_address(c.get('address'))}, {city}, IL {c['zip']}"
    return {
        "cid": c["candidate_id"], "zip": c["zip"], "city": city,
        "name": c.get("name"), "public_name": public,
        "address": display_address(c.get("address")), "suite": c.get("suite"),
        "suites_seen": (c.get("suites_seen") or [])[:6], "phone": fmt_phone(phone),
        "website": site, "entity_classification": c.get("entity_classification"),
        "provider_count": c.get("provider_count"), "providers": provs[:3],
        "flags": flags, "queue_state": c.get("queue_state"),
        "prior": prior_lines(c), "status_notes": status_snippets(c),
        "home_like": home_like, "non_il_phone": non_il,
        "route": route, "queries": queries, "maps": maps(full_addr),
        "as_seen": {"name": c.get("name"), "address": c.get("address"), "suite": c.get("suite"),
                    "phone": fmt_phone(phone), "website": c.get("website")},
    }


def index_entry(c):
    return [c["candidate_id"], c.get("origin"), c.get("zip"), c.get("name"), c.get("address"),
            c.get("suite"), c.get("phone"), c.get("queue_state")]


def cmd_init(args):
    if path("queue.jsonl").exists() and not args.force:
        raise SystemExit(f"{path('queue.jsonl')} exists; pass --force to rebuild (checks.jsonl is kept).")
    cands = [json.loads(l) for l in oc.CANDIDATES_PATH.read_text().splitlines() if l.strip()]
    build_id = json.loads(oc.MANIFEST_PATH.read_text()).get("build_id")
    decided, swept = load_ledger_state()
    rank = {}
    if oc.COVERAGE_PATH.exists():
        import csv
        with oc.COVERAGE_PATH.open() as f:
            rank = {r["zip"]: int(r.get("batch_rank") or 9999) for r in csv.DictReader(f)}
    directory = [c for c in cands if c.get("origin") == "directory_row"]
    npis = {str(n) for c in directory for n in (c.get("source_refs") or {}).get("npis") or []}
    providers = load_providers(npis)

    rapid, building, done = [], [], []
    for c in directory:
        lane, why = lane_of(c, decided, swept)
        if lane == "rapid":
            rapid.append(c)
        elif lane == "building":
            building.append({"candidate_id": c["candidate_id"], "zip": c["zip"], "name": c.get("name"),
                             "address": c.get("address"), "reason": why, "flags": c.get("flags")})
        else:
            done.append(c["candidate_id"])
    rnd = random.Random(args.seed)
    calib = set(c["candidate_id"] for c in rnd.sample(rapid, min(args.calibration, len(rapid))))
    ordered = sorted((c for c in rapid if c["candidate_id"] in calib), key=lambda c: c["candidate_id"])
    rnd.shuffle(ordered)
    ordered += sorted((c for c in rapid if c["candidate_id"] not in calib),
                      key=lambda c: (rank.get(c["zip"], 9999), c["zip"], oc.street_key(c.get("address"), c["zip"])[0]))

    P.dir.mkdir(parents=True, exist_ok=True)
    with path("queue.jsonl").open("w") as f:
        for i, c in enumerate(ordered, 1):
            card = make_card(c, providers)
            card["position"] = i
            card["lane"] = "calibration" if c["candidate_id"] in calib else "zip_order"
            f.write(json.dumps(card, separators=(",", ":")) + "\n")
    with path("building_lane.jsonl").open("w") as f:
        for b in sorted(building, key=lambda b: (rank.get(b["zip"], 9999), b["zip"], b["address"] or "")):
            f.write(json.dumps(b) + "\n")
    by_street, by_phone, entries = collections.defaultdict(list), collections.defaultdict(list), {}
    for c in cands:
        e = index_entry(c)
        entries[c["candidate_id"]] = e
        if oc.present(c.get("address")):
            by_street["|".join(oc.street_key(c["address"], c.get("zip")))].append(c["candidate_id"])
        dg = oc.digits(c.get("phone"))
        if dg:
            by_phone[dg].append(c["candidate_id"])
    path("index.json").write_text(json.dumps({"by_street": by_street, "by_phone": by_phone,
                                              "entries": entries}, separators=(",", ":")))
    meta = {"rules": RULES, "build_id": build_id, "seed": args.seed, "created_at": now_utc().isoformat(),
            "directory_rows": len(directory), "rapid_rows": len(rapid), "calibration_rows": len(calib),
            "building_lane_rows": len(building), "census_done_rows": len(done),
            "providers_loaded": bool(providers), "downtown_zips": sorted(DOWNTOWN_ZIPS)}
    path("queue_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta, indent=1))
    return 0


# ---- queue state ---------------------------------------------------------------
def load_queue():
    if not path("queue.jsonl").exists():
        raise SystemExit("No rapid queue. Run: python3 scrapers/office_census_rapid.py init")
    return read_jsonl(path("queue.jsonl"))


def latest_checks():
    """candidate_id -> latest live check (later lines supersede earlier ones)."""
    out = {}
    for e in read_jsonl(path("checks.jsonl")):
        if e.get("candidate_id"):
            out[e["candidate_id"]] = e
    return out


def load_claims():
    p = path("claims.json")
    try:
        claims = json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        claims = {}
    cutoff = now_utc() - datetime.timedelta(hours=CLAIM_HOURS)
    return {k: v for k, v in claims.items()
            if datetime.datetime.fromisoformat(v["claimed_at"]) > cutoff}


def save_claims(claims):
    tmp = path("claims.json.tmp")
    tmp.write_text(json.dumps(claims))
    tmp.replace(path("claims.json"))


def dns_status(urls, timeout=4.0):
    hosts = {u: host_of(u) for u in urls if u}
    out = {}

    def resolve(h):
        socket.getaddrinfo(h, 443)
        return "ok"

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {u: ex.submit(resolve, h) for u, h in hosts.items() if h}
        for u, fut in futs.items():
            try:
                out[u] = fut.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                out[u] = "dns timeout"
            except OSError:
                out[u] = "DNS FAIL (domain does not resolve)"
    return out


def render(card, i, n, dns):
    L = [f"── [{i}/{n}] {card['cid']} · {card['zip']} {card['city']} · #{card['position']} "
         f"{card['lane']} · route={card['route']}"]
    site = card["website"]
    site_s = f"{site} [{dns.get(site, 'dns ?')}]" if site else "no website"
    addr = card["address"] + (f", Ste {card['suite']}" if card.get("suite") else "")
    L.append(f"app:   {card['name']} | {addr} | {card['phone'] or 'no phone'} | {site_s}")
    extra = f"class={card['entity_classification']} providers({card['provider_count'] or 0})"
    if card["providers"]:
        extra += ": " + ", ".join(card["providers"])
    if card["suites_seen"]:
        extra += f" · suites seen: {', '.join(card['suites_seen'])}"
    L.append(f"       {extra}")
    if card["public_name"] and card["public_name"] != card["name"]:
        L.append(f"       public name from prior site check: {card['public_name']}")
    if card["flags"]:
        L.append(f"flags: {', '.join(card['flags'])}")
    for k, p in enumerate(card["prior"]):
        L.append(("prior: " if k == 0 else "       ") + p[:220])
    warn = []
    if card["home_like"]:
        warn.append("address looks residential")
    if card["non_il_phone"]:
        warn.append("non-Illinois phone area code")
    if site and dns.get(site, "").startswith("DNS FAIL"):
        warn.append("website on file does not resolve")
    for s in card["status_notes"]:
        warn.append(f'prior note: "{s}"')
    for w in warn:
        L.append(f"⚠ {w}")
    for k, q in enumerate(card["queries"], 1):
        L.append(f"q{k} {q['kind']:<8} {q['q']}")
    return "\n".join(L)


def cmd_next(args):
    queue = load_queue()
    decided, swept = load_ledger_state()
    done = set(latest_checks())
    with locked():
        claims = load_claims()
        mine = [c for c in queue if claims.get(c["cid"], {}).get("session") == args.session
                and c["cid"] not in done]
        picked = mine[:args.n]
        for c in queue:
            if len(picked) >= args.n:
                break
            cid = c["cid"]
            if cid in done or cid in claims or cid in decided or c["zip"] in swept:
                continue
            picked.append(c)
        stamp = now_utc().isoformat()
        for c in picked:
            claims[c["cid"]] = {"session": args.session, "claimed_at": stamp}
        save_claims(claims)
    if not picked:
        print("Queue empty: every rapid row has a check or is claimed by another session.")
        return 0
    if args.json:
        print(json.dumps(picked, indent=1))
        return 0
    dns = dns_status([c["website"] for c in picked])
    remaining = sum(1 for c in queue if c["cid"] not in done)
    print(f"session {args.session}: {len(picked)} rows claimed · {remaining} rapid rows without a check\n")
    for i, c in enumerate(picked, 1):
        print(render(c, i, len(picked), dns))
        print()
    return 0


# ---- record ----------------------------------------------------------------------
def parse_objects(text):
    text = text.strip()
    if not text:
        return []
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else [v]
    except ValueError:
        pass
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text):
            break
        obj, i = dec.raw_decode(text, i)
        out.append(obj)
    return out


def norm_field(k, v):
    if not oc.present(v):
        return ""
    if k == "phone":
        return oc.digits(v) or str(v)
    if k == "address":
        return oc.NORM(str(v))
    if k == "website":
        return host_of(normalize_url(v)).removeprefix("www.")
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def http_url(u):
    return isinstance(u, str) and re.match(r"^https?://\S+$", u.strip()) is not None


def validate(obj, card, already_done):
    errs = []
    if not isinstance(obj, dict):
        return ["each record must be a JSON object"]
    dec = obj.get("decision")
    if dec not in DECISIONS:
        errs.append(f"decision must be one of {', '.join(DECISIONS)}")
    if card is None:
        errs.append(f"candidate_id {obj.get('candidate_id')!r} is not in the rapid queue")
    if already_done and not obj.get("supersede"):
        errs.append("this row already has a check; add \"supersede\": true to replace it")
    ev = obj.get("evidence") or []
    if not isinstance(ev, list) or len(ev) > 4:
        errs.append("evidence must be a list of at most 4 items")
        ev = []
    for k, e in enumerate(ev):
        if not isinstance(e, dict) or e.get("kind") not in EVIDENCE_KINDS:
            errs.append(f"evidence[{k}].kind must be one of {', '.join(sorted(EVIDENCE_KINDS))}")
        elif not http_url(e.get("url")):
            errs.append(f"evidence[{k}].url must be an http(s) URL")
        elif len(str(e.get("quote") or "")) > 240:
            errs.append(f"evidence[{k}].quote must be at most 240 characters")
    kinds = {e.get("kind") for e in ev if isinstance(e, dict)}
    observed = obj.get("observed") or {}
    if not isinstance(observed, dict) or set(observed) - OBSERVED_FIELDS:
        errs.append(f"observed keys must be within {sorted(OBSERVED_FIELDS)}")
        observed = {}
    changed = {k for k, v in observed.items()
               if k != "zip" and oc.present(v) and card is not None
               and norm_field(k, v) != norm_field(k, (card.get("as_seen") or {}).get(k))}
    if obj.get("gp_scope", "unknown") not in GP_SCOPES:
        errs.append(f"gp_scope must be one of {sorted(GP_SCOPES)}")
    sig = obj.get("signals") or []
    if not isinstance(sig, list) or set(sig) - SIGNALS:
        errs.append(f"signals must be within {sorted(SIGNALS)}")
    note = obj.get("note") or ""
    if len(str(note)) > 400:
        errs.append("note must be at most 400 characters")
    leads = obj.get("leads") or []
    if not isinstance(leads, list) or len(leads) > 8 or any(
            not isinstance(l, dict) or not oc.present(l.get("name")) for l in leads):
        errs.append("leads must be a list (max 8) of objects with at least a name")
    for f in ("searches", "fetches"):
        v = obj.get(f)
        if not isinstance(v, int) or not 0 <= v <= 12:
            errs.append(f"{f} must be an integer 0-12")
    if isinstance(obj.get("searches"), int) and obj["searches"] < 1:
        errs.append("searches must be at least 1: every row gets a fresh search")

    if dec in ("VALID", "VALID_CORRECTED"):
        if not kinds & CURRENT_KINDS:
            errs.append(f"{dec} needs current evidence: kind in {sorted(CURRENT_KINDS)}. "
                        "Listings alone -> IDENTITY_ONLY")
        if obj.get("gp_scope") not in ("gp", "mixed"):
            errs.append(f"{dec} needs gp_scope gp or mixed")
    if dec == "VALID" and changed:
        errs.append(f"observed differs from the app ({', '.join(sorted(changed))}) -> use VALID_CORRECTED")
    if dec == "VALID_CORRECTED" and not changed:
        errs.append("VALID_CORRECTED needs at least one observed field that differs from the app")
    if dec == "IDENTITY_ONLY" and not ev:
        errs.append("IDENTITY_ONLY needs at least one evidence item")
    if dec == "NOT_CURRENT_GP":
        if obj.get("reason") not in NOT_CURRENT_REASONS:
            errs.append(f"NOT_CURRENT_GP needs reason in {sorted(NOT_CURRENT_REASONS)}")
        if not any(isinstance(e, dict) and oc.present(e.get("quote")) for e in ev):
            errs.append("NOT_CURRENT_GP needs positive evidence: an evidence item with a quote "
                        "(absence of results is NO_WEB_EVIDENCE, not closure)")
        if obj.get("reason") == "duplicate" and not oc.present(obj.get("duplicate_of")):
            errs.append("reason duplicate needs duplicate_of (a candidate id from lookup)")
    if dec == "ESCALATE" and obj.get("reason") not in ESCALATE_REASONS:
        errs.append(f"ESCALATE needs reason in {sorted(ESCALATE_REASONS)}")
    if dec in ("ESCALATE", "IDENTITY_PROBLEM", "NO_WEB_EVIDENCE") and not oc.present(note):
        errs.append(f"{dec} needs a note (what conflicts / what was tried)")
    if dec == "NO_WEB_EVIDENCE" and isinstance(obj.get("searches"), int) and obj["searches"] < 2:
        errs.append("NO_WEB_EVIDENCE needs at least 2 searches")
    return errs


def load_index():
    return json.loads(path("index.json").read_text())


def collisions(obj, card, idx):
    observed = obj.get("observed") or {}
    zip_code = observed.get("zip") or card["zip"]
    hits = []
    if oc.present(observed.get("address")):
        key = "|".join(oc.street_key(observed["address"], zip_code))
        hits += [("address", c) for c in idx["by_street"].get(key, [])]
    dg = oc.digits(observed.get("phone"))
    if dg:
        hits += [("phone", c) for c in idx["by_phone"].get(dg, [])]
    out, seen = [], set()
    for via, cid in hits:
        if cid == card["cid"] or (via, cid) in seen:
            continue
        seen.add((via, cid))
        e = idx["entries"].get(cid) or [cid]
        out.append({"via": via, "candidate_id": cid, "origin": e[1] if len(e) > 1 else None,
                    "name": e[3] if len(e) > 3 else None, "suite": e[5] if len(e) > 5 else None,
                    "phone": e[6] if len(e) > 6 else None})
    return out[:10]


def cmd_record(args):
    text = pathlib.Path(args.file).read_text() if args.file else sys.stdin.read()
    try:
        objs = parse_objects(text)
    except ValueError as exc:
        print(f"REJECTED: input is not valid JSON ({exc})")
        return 1
    if not objs:
        print("REJECTED: no JSON objects on input")
        return 1
    cards = {c["cid"]: c for c in load_queue()}
    idx = load_index()
    bad = 0
    with locked():
        done = latest_checks()
        claims = load_claims()
        with path("checks.jsonl").open("a") as out:
            for obj in objs:
                cid = obj.get("candidate_id") if isinstance(obj, dict) else None
                card = cards.get(cid)
                errs = validate(obj, card, cid in done)
                if errs:
                    bad += 1
                    print(f"REJECTED {cid}:")
                    for e in errs:
                        print(f"  - {e}")
                    continue
                ts = now_utc()
                entry = {"entry_id": f"rc-{ts.strftime('%Y%m%dT%H%M%S')}-{cid.split(':')[-1][:10]}"
                                     f"-{random.randrange(16**4):04x}",
                         "type": "rapid_check", "rules": RULES, "candidate_id": cid, "zip": card["zip"],
                         "session": args.session, "researcher": args.researcher,
                         "recorded_at": ts.isoformat(), "checked_at": ts.date().isoformat(),
                         "as_seen": card["as_seen"]}
                for k in ("decision", "reason", "gp_scope", "evidence", "observed", "signals", "note",
                          "leads", "searches", "fetches", "duplicate_of", "supersede"):
                    if k in obj and obj[k] not in (None, "", [], {}):
                        entry[k] = obj[k]
                col = collisions(obj, card, idx)
                if col:
                    entry["collisions"] = col
                out.write(json.dumps(entry, separators=(",", ":")) + "\n")
                out.flush()
                done[cid] = entry
                claims.pop(cid, None)
                msg = f"OK {cid} {entry['decision']}"
                if col:
                    msg += " · COLLISION: " + "; ".join(
                        f"{c['via']} matches {c['candidate_id']} {c['name']!r} ste={c['suite']}" for c in col)
                print(msg)
        save_claims(claims)
    return 1 if bad else 0


# ---- lookup / status / list / check ----------------------------------------------
def cmd_lookup(args):
    idx = load_index()
    hits = []
    if args.address:
        if not args.zip:
            raise SystemExit("--address needs --zip")
        hits += idx["by_street"].get("|".join(oc.street_key(args.address, args.zip)), [])
        lk = oc.loose_key(args.address, args.zip)
        if lk:
            for cid, e in idx["entries"].items():
                if e[4] and oc.loose_key(e[4], e[2]) == lk:
                    hits.append(cid)
    if args.phone:
        hits += idx["by_phone"].get(oc.digits(args.phone) or "", [])
    if args.name:
        needle = re.sub(r"[^a-z0-9]", "", args.name.lower())
        hits += [cid for cid, e in idx["entries"].items()
                 if needle and needle in re.sub(r"[^a-z0-9]", "", str(e[3] or "").lower())
                 and (not args.zip or e[2] == args.zip)]
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    if not seen:
        print("no matching rows")
    for cid in seen[:25]:
        e = idx["entries"][cid]
        print(f"{cid} | {e[1]} | {e[2]} | {e[3]} | {e[4]} ste={e[5]} | {e[6]} | {e[7]}")
    return 0


def cmd_status(args):
    meta = json.loads(path("queue_meta.json").read_text()) if path("queue_meta.json").exists() else {}
    queue = load_queue()
    qids = {c["cid"] for c in queue}
    calib = {c["cid"] for c in queue if c["lane"] == "calibration"}
    checks = latest_checks()
    done = {k: v for k, v in checks.items() if k in qids}
    decided, swept = load_ledger_state()
    claims = load_claims()
    n = len(done)
    print(f"rapid queue (build {meta.get('build_id')}, {meta.get('created_at', '')[:10]}): "
          f"{len(queue)} rows · checked {n} ({n / max(len(queue), 1):.1%}) · remaining {len(queue) - n}")
    print(f"calibration sample: {len(calib & set(done))}/{len(calib)} · building lane: "
          f"{meta.get('building_lane_rows')} rows · already reconciled by census: {meta.get('census_done_rows')}")
    if claims:
        print(f"open claims: " + ", ".join(f"{s}={c}" for s, c in
                                           collections.Counter(v["session"] for v in claims.values()).items()))
    dec = collections.Counter(v["decision"] for v in done.values())
    print("\ndecisions:")
    for d in DECISIONS:
        if dec[d]:
            print(f"  {d:<17} {dec[d]:>5}  {dec[d] / max(n, 1):.0%}")
    reasons = collections.Counter(f"{v['decision']}:{v['reason']}" for v in done.values() if v.get("reason"))
    if reasons:
        print("reasons: " + ", ".join(f"{k}={c}" for k, c in reasons.most_common()))
    sig = collections.Counter(s for v in done.values() for s in v.get("signals") or [])
    if sig:
        print("signals: " + ", ".join(f"{k}={c}" for k, c in sig.most_common()))
    corr = collections.Counter(k for v in done.values() if v["decision"] == "VALID_CORRECTED"
                               for k in (v.get("observed") or {}))
    if corr:
        print("corrected fields: " + ", ".join(f"{k}={c}" for k, c in corr.most_common()))
    leads = sum(len(v.get("leads") or []) for v in done.values())
    col = sum(1 for v in done.values() if v.get("collisions"))
    print(f"leads logged: {leads} · rows with collisions: {col} · "
          f"searches/row: {sum(v.get('searches', 0) for v in done.values()) / max(n, 1):.1f} · "
          f"fetches/row: {sum(v.get('fetches', 0) for v in done.values()) / max(n, 1):.1f}")
    sessions = collections.defaultdict(list)
    for v in read_jsonl(path("checks.jsonl")):
        sessions[v.get("session")].append(v["recorded_at"])
    if sessions:
        print("\nsessions:")
        for s, ts in sorted(sessions.items(), key=lambda kv: min(kv[1])):
            t0, t1 = min(ts), max(ts)
            hrs = (datetime.datetime.fromisoformat(t1) - datetime.datetime.fromisoformat(t0)).total_seconds() / 3600
            rate = f"{len(ts) / hrs:.0f}/h" if hrs > 0.05 else "-"
            print(f"  {s}: {len(ts)} rows {t0[:16]} → {t1[11:16]} UTC ({rate})")
    later = [c for c in queue if c["cid"] not in checks]
    if later:
        print(f"\nnext up: #{later[0]['position']} {later[0]['lane']} ZIP {later[0]['zip']} {later[0]['city']}")
    if decided or swept:
        stale = sum(1 for c in queue if c["cid"] in decided or c["zip"] in swept)
        if stale:
            print(f"note: {stale} queued rows were adjudicated in the census ledger after init; next skips them")
    return 0


def cmd_list(args):
    rows = list(latest_checks().values())
    if args.decision:
        rows = [r for r in rows if r["decision"] == args.decision]
    if args.signal:
        rows = [r for r in rows if args.signal in (r.get("signals") or [])]
    if args.reason:
        rows = [r for r in rows if r.get("reason") == args.reason]
    if args.session:
        rows = [r for r in rows if r.get("session") == args.session]
    if args.sample and len(rows) > args.sample:
        rows = random.Random(args.seed).sample(rows, args.sample)
    for r in rows:
        url = next((e["url"] for e in r.get("evidence") or []), "")
        obs = " ".join(f"{k}={v}" for k, v in (r.get("observed") or {}).items())
        print(f"{r['candidate_id']} | {r['zip']} | {r['decision']}{':' + r['reason'] if r.get('reason') else ''}"
              f" | {r['as_seen'].get('name')} | {obs} | {r.get('note', '')} | {url}")
    print(f"({len(rows)} rows)")
    return 0


def cmd_check(args):
    cards = {c["cid"]: c for c in load_queue()}
    errors, seen = 0, set()
    for n, e in enumerate(read_jsonl(path("checks.jsonl")), 1):
        errs = validate(e, cards.get(e.get("candidate_id")), e.get("candidate_id") in seen)
        seen.add(e.get("candidate_id"))
        for x in errs:
            errors += 1
            print(f"line {n} {e.get('candidate_id')}: {x}")
    print(f"{'OK' if not errors else 'FAIL'}: {errors} error(s) across {len(seen)} rows")
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rapid-dir", help="alternate directory for all rapid files (tests / smoke runs)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("--force", action="store_true")
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--calibration", type=int, default=CALIBRATION_N)
    s = sub.add_parser("next")
    s.add_argument("--n", type=int, default=10)
    s.add_argument("--session", default="solo")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("record")
    s.add_argument("--session", default="solo")
    s.add_argument("--researcher", default=os.environ.get("RAPID_RESEARCHER", "claude"))
    s.add_argument("--file")
    s = sub.add_parser("lookup")
    s.add_argument("--address")
    s.add_argument("--zip")
    s.add_argument("--phone")
    s.add_argument("--name")
    sub.add_parser("status")
    s = sub.add_parser("list")
    s.add_argument("--decision", choices=DECISIONS)
    s.add_argument("--signal", choices=sorted(SIGNALS))
    s.add_argument("--reason")
    s.add_argument("--session")
    s.add_argument("--sample", type=int)
    s.add_argument("--seed", type=int, default=1)
    sub.add_parser("check")
    args = ap.parse_args(argv)
    if args.rapid_dir:
        P.set(args.rapid_dir)
    return {"init": cmd_init, "next": cmd_next, "record": cmd_record, "lookup": cmd_lookup,
            "status": cmd_status, "list": cmd_list, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
