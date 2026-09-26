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
  python3 scrapers/office_census_rapid.py release --session S    # hand back unrecorded claims
  python3 scrapers/office_census_rapid.py tag                     # a fresh session tag
  python3 scrapers/office_census_rapid.py pull                    # mirror the shared log locally

Protocol: data/office_census/RAPID_VALIDATION_RUNBOOK.md.

Store. With the shared store configured (RAPID_TOKEN + Supabase URL/anon key, see
rapid_store.py) `next` claims rows and `record` logs each check in Supabase and applies it
to directory_web_checks at once, the overlay the live Directory page reads. Several sessions,
local or Claude Code cloud, can work the queue together. data/office_census/rapid/checks.jsonl
is the local mirror (`pull`). `--store local` (and any --rapid-dir) keeps everything in local
files, with claims.json and the batch publisher scrapers/directory_web_checks_publish.py.

Rapid checks are NOT census adjudications: they never touch research_ledger.jsonl, SQLite,
practice_locations or ownership tiers. The only Supabase writes are the rapid_* functions.

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
import hashlib
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
import rapid_store as store  # noqa: E402

RULES = "rapid-2026-09-25.2"
# .2 added ties_by on NOT_CURRENT_GP; checks recorded under these rules stay valid without it.
LEGACY_RULES = {"rapid-2026-09-25.1"}
PUBLISH_EVERY = 50
# A Claude Code session gets ~200 web searches; stop claiming new rows before that so a
# session ends cleanly (claimed rows recorded, published, committed) instead of mid-batch.
SEARCH_BUDGET = int(os.environ.get("RAPID_SEARCH_BUDGET", "170"))
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
# How NOT_CURRENT_GP evidence is tied to THIS row. A CLOSED listing for a different business
# at the same address says nothing about the row, so closed/moved/duplicate need a non-address tie.
TIES = {"name", "phone", "dentist", "website", "address"}
IDENTITY_TIE_REASONS = {"closed", "moved", "duplicate"}

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
    """Rapid-run files; --rapid-dir moves all of them (tests, smoke runs). `store` is
    "supabase" (shared queue, live on record) or "local" (files + batch publisher)."""
    dir = RAPID_DIR
    store = "local"

    @classmethod
    def set(cls, d):
        cls.dir = pathlib.Path(d)


def path(name):
    return P.dir / name


def remote():
    return P.store == "supabase"


# ---- live-page rows ------------------------------------------------------------
# Each row's latest check becomes one directory_web_checks row; the page applies `effect`.
EFFECT = {"VALID": "open_verified", "VALID_CORRECTED": "open_corrected", "IDENTITY_ONLY": "listed_only",
          "NOT_CURRENT_GP": "removed", "IDENTITY_PROBLEM": "needs_review", "ESCALATE": "needs_review",
          "NO_WEB_EVIDENCE": "no_web_evidence"}


def strip_loc(cid):
    return cid.split(":", 1)[1] if isinstance(cid, str) and cid.startswith("loc:") else cid


def web_check_row(cid, e, publish_id):
    return {"location_id": strip_loc(cid), "candidate_id": cid, "zip": e["zip"],
            "effect": EFFECT[e["decision"]], "decision": e["decision"], "reason": e.get("reason"),
            "duplicate_of": strip_loc(e.get("duplicate_of")), "gp_scope": e.get("gp_scope"),
            "observed": e.get("observed") or {}, "as_seen": e.get("as_seen") or {},
            "signals": e.get("signals") or [], "ties_by": e.get("ties_by") or [],
            "evidence": e.get("evidence") or [], "leads": e.get("leads") or [], "note": e.get("note"),
            "checked_at": e["checked_at"], "recorded_at": e["recorded_at"], "session": e.get("session"),
            "researcher": e.get("researcher"), "rules": e.get("rules"), "publish_id": publish_id}


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


def latest_checks(include_held=True):
    """candidate_id -> latest check (later lines supersede earlier ones). A removal the store's
    brake held back (outcome "held") never reached the page; include_held=False skips it."""
    out = {}
    for e in read_jsonl(path("checks.jsonl")):
        if e.get("candidate_id") and (include_held or e.get("outcome") != "held"):
            out[e["candidate_id"]] = e
    return out


def pull():
    """Mirror the shared log into checks.jsonl: add entries other sessions recorded, keep every
    local line (verbatim where the log has it too), order by recorded_at so the latest wins."""
    got, off = [], 0
    while True:
        page = store.rpc("rapid_pull", p_offset=off, p_limit=500) or []
        got += page
        if len(page) < 500:
            break
        off += 500
    server = {}
    for e in got:
        if e.get("outcome") in ("live", "backfill"):
            e.pop("outcome")
        server[e["entry_id"]] = e
    with locked():
        local = read_jsonl(path("checks.jsonl"))
        have = {e.get("entry_id") for e in local}
        changed = False
        for e in local:
            s = server.get(e.get("entry_id"))
            if s is not None and s.get("outcome") != e.get("outcome"):
                changed = True
                e["outcome"] = s.get("outcome")
                if e["outcome"] is None:
                    e.pop("outcome")
        merged = local + [e for k, e in server.items() if k not in have]
        merged.sort(key=lambda e: e.get("recorded_at") or "")   # stable: same-second lines keep file order
        only_local = sum(1 for e in local if e.get("entry_id") not in server)
        if changed or len(merged) != len(local) or any(a is not b for a, b in zip(merged, local)):
            tmp = path("checks.jsonl.tmp")
            tmp.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in merged))
            tmp.replace(path("checks.jsonl"))
    return {"log": len(server), "added": len(merged) - len(local), "only_local": only_local}


def last_publish():
    """What the live Directory page last received (written by directory_web_checks_publish.py)."""
    try:
        return json.loads(path("last_publish.json").read_text())
    except (OSError, ValueError):
        return {}


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


def dns_works():
    # Behind a cloud sandbox proxy the VM may resolve nothing; then every site would look dead.
    try:
        socket.getaddrinfo("example.com", 443)
        return True
    except OSError:
        return False


def dns_status(urls, timeout=4.0):
    hosts = {u: host_of(u) for u in urls if u}
    out = {}
    if hosts and not dns_works():
        return {u: "dns not checked" for u in hosts}

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


def session_searches(session):
    return sum(e.get("searches", 0) for e in read_jsonl(path("checks.jsonl")) if e.get("session") == session)


def claim_local(queue, session, n, decided, swept):
    done = set(latest_checks())
    used = session_searches(session)
    with locked():
        claims = load_claims()
        picked = [c for c in queue if claims.get(c["cid"], {}).get("session") == session
                  and c["cid"] not in done][:n]
        for c in queue:
            if used >= SEARCH_BUDGET or len(picked) >= n:
                break
            cid = c["cid"]
            if cid in done or cid in claims or cid in decided or c["zip"] in swept:
                continue
            picked.append(c)
        stamp = now_utc().isoformat()
        for c in picked:
            claims[c["cid"]] = {"session": session, "claimed_at": stamp}
        save_claims(claims)
    return picked, used, 0, sum(1 for c in queue if c["cid"] not in done)


def claim_remote(queue, session, n, decided, swept):
    eligible = [c["cid"] for c in queue if c["cid"] not in decided and c["zip"] not in swept]
    res = store.rpc("rapid_next", p_session=session, p_ids=eligible, p_n=n, p_budget=SEARCH_BUDGET)
    by_cid = {c["cid"]: c for c in queue}
    return [by_cid[c] for c in res["picked"]], res["searches_used"], res["held"], res["remaining"]


def cmd_next(args):
    queue = load_queue()
    decided, swept = load_ledger_state()
    try:
        picked, used, held, remaining = (claim_remote if remote() else claim_local)(
            queue, args.session, args.n, decided, swept)
    except store.StoreError as exc:
        print(f"STORE ERROR: {exc}\nNothing was claimed. Retry once; if it fails again, end the session "
              "(runbook section 7) and report this line.")
        return 1
    if held and not picked:
        print(f"REMOVAL BRAKE: {held} of session {args.session}'s NOT_CURRENT_GP checks were held back from the "
              "live page (too many removals). Claim nothing more: end the session now (runbook section 7).")
        return 0
    if used >= SEARCH_BUDGET and not picked:
        print(f"SEARCH BUDGET REACHED: session {args.session} has used {used} web searches "
              f"(budget {SEARCH_BUDGET}). Claim nothing more: end the session now (runbook section 7).")
        return 0
    if not picked:
        print("Queue empty: every rapid row has a check or is claimed by another session.")
        return 0
    if args.json:
        print(json.dumps(picked, indent=1))
        return 0
    dns = dns_status([c["website"] for c in picked])
    print(f"session {args.session}: {len(picked)} rows claimed · {remaining} rapid rows without a check"
          f" · web searches used this session {used}/{SEARCH_BUDGET}"
          + (" · store: shared, each record goes live" if remote() else " · store: local files"))
    if not remote():
        unpublished = len(latest_checks()) - last_publish().get("rows", 0)
        if unpublished >= PUBLISH_EVERY:
            print(f"PUBLISH DUE ({unpublished} checks not on the live page yet): "
                  "python3 scrapers/directory_web_checks_publish.py --allow-db-write --verify")
    print()
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


def validate(obj, card, already_done, rules=RULES):
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
        ties = obj.get("ties_by")
        if rules not in LEGACY_RULES:
            if not isinstance(ties, list) or not ties or set(ties) - TIES:
                errs.append(f"NOT_CURRENT_GP needs ties_by: which facts tie the evidence to THIS row, "
                            f"a list within {sorted(TIES)} (e.g. [\"dentist\", \"phone\"])")
            elif obj.get("reason") in IDENTITY_TIE_REASONS and not set(ties) - {"address"}:
                errs.append(f"reason {obj.get('reason')} needs a tie beyond the address (name, phone, dentist "
                            "or website): a closed/moved business at the same address may be a "
                            "different office -> IDENTITY_PROBLEM or ESCALATE")
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
    # local store: one lock for the whole batch; shared store: lock only the mirror append,
    # never across a network call
    with contextlib.nullcontext() if remote() else locked():
        done = {} if remote() else latest_checks()
        claims = {} if remote() else load_claims()
        for obj in objs:
            cid = obj.get("candidate_id") if isinstance(obj, dict) else None
            card = cards.get(cid)
            # the shared store decides "already checked" itself, across every session
            errs = validate(obj, card, cid in done and not remote())
            if errs:
                bad += 1
                print(f"REJECTED {cid}:")
                for e in errs:
                    print(f"  - {e}")
                continue
            entry = make_entry(obj, card, args)
            col = collisions(obj, card, idx)
            if col:
                entry["collisions"] = col
            note = ""
            if remote():
                try:
                    res = store.rpc("rapid_record", p_entry=entry,
                                    p_row=web_check_row(cid, entry, entry["entry_id"]))
                except store.StoreError as exc:
                    bad += 1
                    print(f"NOT SAVED {cid}: {exc}\n  Resend the same record command once; the store "
                          "ignores a record it already has.")
                    continue
                outcome = res.get("outcome")
                if outcome == "rejected":
                    bad += 1
                    print(f"REJECTED {cid}:\n  - {res.get('error')}")
                    continue
                if outcome in ("held", "stale"):
                    entry["outcome"] = outcome
                note = {"live": " · live on the Directory page",
                        "held": " · HELD by the removal brake: logged, not on the page. Finish this card, "
                                "then end the session (runbook section 7)",
                        "stale": " · logged; a newer check of this row is already live"}.get(outcome, "")
                if res.get("duplicate"):
                    note += " (already recorded earlier)"
            with locked() if remote() else contextlib.nullcontext():
                if not any(e.get("entry_id") == entry["entry_id"] for e in read_jsonl(path("checks.jsonl"))):
                    with path("checks.jsonl").open("a") as out:
                        out.write(json.dumps(entry, separators=(",", ":")) + "\n")
            done[cid] = entry
            claims.pop(cid, None)
            msg = f"OK {cid} {obj['decision']}{note}"
            if col:
                msg += " · COLLISION: " + "; ".join(
                    f"{c['via']} matches {c['candidate_id']} {c['name']!r} ste={c['suite']}" for c in col)
            print(msg)
        if not remote():
            save_claims(claims)
    return 1 if bad else 0


def make_entry(obj, card, args):
    ts = now_utc()
    cid = obj["candidate_id"]
    if remote():
        # content-derived id: resending the same record (a lost reply) is a no-op in the store
        digest = hashlib.sha256(json.dumps([args.session, obj], sort_keys=True).encode()).hexdigest()[:8]
        entry_id = f"rc-{ts.strftime('%Y%m%d')}-{cid.split(':')[-1][:10]}-{digest}"
    else:
        entry_id = (f"rc-{ts.strftime('%Y%m%dT%H%M%S')}-{cid.split(':')[-1][:10]}"
                    f"-{random.randrange(16**4):04x}")
    entry = {"entry_id": entry_id, "type": "rapid_check", "rules": RULES, "candidate_id": cid,
             "zip": card["zip"], "session": args.session, "researcher": args.researcher,
             "recorded_at": ts.isoformat(), "checked_at": ts.date().isoformat(), "as_seen": card["as_seen"]}
    for k in ("decision", "reason", "gp_scope", "evidence", "observed", "signals", "note",
              "leads", "searches", "fetches", "duplicate_of", "ties_by", "supersede"):
        if k in obj and obj[k] not in (None, "", [], {}):
            entry[k] = obj[k]
    return entry


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


def cmd_release(args):
    if remote():
        n = store.rpc("rapid_release", p_session=args.session)
        print(f"released {n} unrecorded claimed rows of session {args.session}")
        return 0
    with locked():
        claims = load_claims()
        mine = [k for k, v in claims.items() if v["session"] == args.session]
        for k in mine:
            claims.pop(k)
        save_claims(claims)
    print(f"released {len(mine)} unrecorded claimed rows of session {args.session}")
    return 0


def cmd_status(args):
    meta = json.loads(path("queue_meta.json").read_text()) if path("queue_meta.json").exists() else {}
    queue = load_queue()
    qids = {c["cid"] for c in queue}
    calib = {c["cid"] for c in queue if c["lane"] == "calibration"}
    server = None
    if remote():
        pulled = pull()
        server = store.rpc("rapid_status")
        claims = {f"{s}#{i}": {"session": s} for s, k in server["claims"].items() for i in range(k)}
    else:
        claims = load_claims()
    checks = latest_checks()
    done = {k: v for k, v in checks.items() if k in qids}
    decided, swept = load_ledger_state()
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
        sessions[v.get("session")].append((v["recorded_at"], v.get("searches", 0)))
    if sessions:
        print("\nsessions:")
        for s, rows in sorted(sessions.items(), key=lambda kv: min(kv[1])):
            ts = [t for t, _ in rows]
            t0, t1 = min(ts), max(ts)
            hrs = (datetime.datetime.fromisoformat(t1) - datetime.datetime.fromisoformat(t0)).total_seconds() / 3600
            rate = f"{len(ts) / hrs:.0f}/h" if hrs > 0.05 else "-"
            print(f"  {s}: {len(ts)} rows · {sum(n for _, n in rows)} searches · "
                  f"{t0[:16]} → {t1[11:16]} UTC ({rate})")
    if server is not None:
        live = server["live"]
        print(f"\nshared store: {server['log_rows']} checks logged (mirror: {pulled['added']} new pulled"
              + (f", {pulled['only_local']} local-only NOT in the store" if pulled["only_local"] else "")
              + f") · live Directory page: {sum(live.values())} rows ("
              + ", ".join(f"{k} {v}" for k, v in sorted(live.items())) + ")")
        if server["held"]:
            print(f"REMOVAL BRAKE: {server['held']} NOT_CURRENT_GP checks were held back from the page; "
                  "they need a human review (runbook section 7)")
    else:
        pub = last_publish()
        print(f"\nlive Directory page: {pub.get('rows', 0)} checks published "
              f"({pub.get('published_at', 'never')[:16]}) · unpublished: {len(checks) - pub.get('rows', 0)}")
    later = [c for c in queue if c["cid"] not in checks]
    if later:
        print(f"\nnext up: #{later[0]['position']} {later[0]['lane']} ZIP {later[0]['zip']} {later[0]['city']}")
    if decided or swept:
        stale = sum(1 for c in queue if c["cid"] in decided or c["zip"] in swept)
        if stale:
            print(f"note: {stale} queued rows were adjudicated in the census ledger after init; next skips them")
    return 0


def cmd_list(args):
    if remote():
        pull()
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


def check_errors():
    """Re-validate every stored check under the rules it was recorded with."""
    cards = {c["cid"]: c for c in load_queue()}
    out, seen = [], set()
    for n, e in enumerate(read_jsonl(path("checks.jsonl")), 1):
        for x in validate(e, cards.get(e.get("candidate_id")), e.get("candidate_id") in seen,
                          e.get("rules", RULES)):
            out.append(f"line {n} {e.get('candidate_id')}: {x}")
        seen.add(e.get("candidate_id"))
    return out, len(seen)


def cmd_check(args):
    if remote():
        pull()
    errs, rows = check_errors()
    for x in errs:
        print(x)
    print(f"{'OK' if not errs else 'FAIL'}: {len(errs)} error(s) across {rows} rows")
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rapid-dir", help="alternate directory for all rapid files (tests / smoke runs)")
    ap.add_argument("--store", choices=("auto", "supabase", "local"), default=os.environ.get("RAPID_STORE", "auto"),
                    help="auto (default): the shared Supabase store, or local files with --rapid-dir")
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
    s = sub.add_parser("release")
    s.add_argument("--session", required=True)
    sub.add_parser("pull", help="mirror the shared log into checks.jsonl")
    sub.add_parser("tag", help="print a fresh session tag")
    args = ap.parse_args(argv)
    if args.rapid_dir:
        P.set(args.rapid_dir)
    P.store = resolve_store(args)
    if P.store is None:
        print(f"STORE NOT CONFIGURED: missing {', '.join(store.missing())}. Sessions work the shared queue, so "
              "set these (runbook section 0), or pass --store local for an offline run that no other "
              "session sees.")
        return 2
    return {"init": cmd_init, "next": cmd_next, "record": cmd_record, "lookup": cmd_lookup,
            "status": cmd_status, "list": cmd_list, "check": cmd_check, "release": cmd_release,
            "pull": cmd_pull, "tag": cmd_tag}[args.cmd](args)


def resolve_store(args):
    """The real queue works the shared store; a --rapid-dir run (tests, smoke runs) stays local.
    None: the shared store is required here but not configured (fail closed: a session must never
    silently work into files that die with its VM)."""
    if args.cmd in ("init", "lookup", "tag"):
        return "local"
    if args.store == "local" or (args.store == "auto" and args.rapid_dir):
        return "local"
    return "supabase" if store.configured() else None


def cmd_tag(args):
    # unique even when parallel sessions start in the same minute; the search budget is per tag
    print(now_utc().strftime("rv-%m%d-%H%M-") + f"{random.SystemRandom().randrange(16**4):04x}")
    return 0


def cmd_pull(args):
    if not remote():
        raise SystemExit("pull needs the shared store")
    r = pull()
    print(f"shared log: {r['log']} checks · {r['added']} added to checks.jsonl"
          + (f" · {r['only_local']} local-only checks are NOT in the store" if r["only_local"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
