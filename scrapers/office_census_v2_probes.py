#!/usr/bin/env python3
"""Office census v2 evidence probes (local batch jobs; plan: data/office_census/V2_PLAN_2026-09-27.md).

  python3 scrapers/office_census_v2_probes.py iema-profiles [--limit N]

Each probe reads public or already-staged inputs and appends to a resumable JSONL cache under
data/office_census/staging/v2_probes/ (gitignored). Nothing here writes the rapid store,
Supabase, SQLite or the ledger. Reruns skip records already fetched.

iema-profiles: fetch the IEMA Radiation Health facility profile page for every dental facility
(Category 'Dental Clinic' or 'Dentist') in a watched Illinois ZIP. The export lacks the fields
v2 needs: status, administrator (usually the dentist), full physical address with suite and
ZIP+4, and active/inactive X-ray equipment (a 'Mobile' location marks a portable unit).
Polite: one request per second, a descriptive User-Agent, stops after 20 consecutive errors.
"""
import argparse
import datetime
import html
import http.client
import json
import os
import pathlib
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OC = ROOT / "data" / "office_census"
REG = OC / "staging" / "public_registries_20260927"
OUT = OC / "staging" / "v2_probes"
TRACKER_DB = pathlib.Path.home() / "dental-pe-tracker" / "data" / "dental_pe_tracker.db"
IEMA_PROFILE = "https://public.iema.state.il.us/RadHealthFacilitySearch/Facility?facilityId={}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
DENTAL_CATEGORIES = ("Dental Clinic", "Dentist")


def read_jsonl(p):
    return [json.loads(l) for l in p.open()] if p.exists() else []


def watched_il_zips():
    db = sqlite3.connect(f"file:{TRACKER_DB}?mode=ro", uri=True)
    return {r[0] for r in db.execute("SELECT zip_code FROM watched_zips WHERE state='IL'")}


def iema_dental_rows():
    import openpyxl
    rows = list(openpyxl.load_workbook(REG / "iema_radhealth_facilities_20260927.xlsx",
                                       read_only=True).active.iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:] if r[rows[0].index("Category")] in DENTAL_CATEGORIES]


def _text(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_iema_profile(page):
    """Profile HTML -> dict. Labels are 'Name:', 'Status:', ... in page order; equipment tables
    follow 'Active X-Ray Equipment' / 'Inactive X-Ray Equipment' headings."""
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", page)
    flat = _text(body)
    out = {}
    labels = ["Name", "Status", "Category", "Administrator", "Physical Address", "Facility Contact",
              "County", "Phone", "Facility ID"]
    for i, lab in enumerate(labels):
        nxt = "|".join(re.escape(l) + ":" for l in labels[i + 1:]) or "$"
        m = re.search(re.escape(lab) + r":\s*(.*?)\s*(?=" + nxt + r"|Active X-Ray Equipment|Inactive X-Ray Equipment|Copyright)", flat)
        out[lab.lower().replace(" ", "_")] = m.group(1).strip() if m and m.group(1).strip() else None
    equipment = []
    for m in re.finditer(r"(?is)(Active|Inactive) X-Ray Equipment(.*?)(?=Active X-Ray Equipment|Inactive X-Ray Equipment|Copyright|$)", body):
        state = m.group(1).lower()
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", m.group(2)):
            cells = [_text(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)]
            if len(cells) >= 8 and re.match(r"^\d{3,5}$", cells[0] or ""):
                equipment.append({"state": state, "equip_id": cells[0], "class": cells[1], "manufacturer": cells[2],
                                  "model": cells[3], "location": cells[4], "serial": cells[5],
                                  "acquired": cells[6] or None, "registered": cells[7] or None})
    out["equipment"] = equipment
    out["active_units"] = sum(1 for e in equipment if e["state"] == "active")
    out["mobile_only"] = bool(equipment) and all(
        "mobile" in (e["location"] or "").lower() or "portable" in (e["model"] or "").lower()
        for e in equipment if e["state"] == "active") and out["active_units"] > 0
    return out


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def cmd_iema_profiles(args):
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "iema_profiles.jsonl"
    done = {r["facility_id"] for r in read_jsonl(dest) if r.get("ok")}
    zips = watched_il_zips()
    todo = [r for r in iema_dental_rows() if str(r["Zip"])[:5] in zips and str(r["Facility ID"]) not in done]
    # Facilities at a target row's site or on a target row's phone first, so a partial crawl
    # still covers the rows being resolved.
    tkeys, tphones = set(), set()
    for t in read_jsonl(OUT / "targets.jsonl"):
        tkeys.add(_addr_key(t.get("address"), t.get("zip")))
        tphones.add(digits10(t.get("phone")))
    todo.sort(key=lambda r: not (_addr_key(r["Physical Address"], r["Zip"]) in tkeys
                                 or digits10(r["Phone Number"]) in tphones))
    if args.limit:
        todo = todo[:args.limit]
    print(f"iema-profiles: {len(done)} cached, {len(todo)} to fetch", flush=True)
    errors = 0
    t0 = time.monotonic()
    with dest.open("a") as fh:
        for n, r in enumerate(todo, 1):
            if args.max_seconds and time.monotonic() - t0 > args.max_seconds:
                print(f"iema-profiles: paused after {n - 1} (--max-seconds); rerun to resume", flush=True)
                return 0
            started = time.monotonic()
            fid = str(r["Facility ID"])
            rec = {"facility_id": fid, "url": IEMA_PROFILE.format(fid),
                   "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                   "export": {k: r[k] for k in ("Facility Name", "Physical Address", "City", "Zip", "Phone Number", "Category")}}
            try:
                rec.update(parse_iema_profile(fetch(rec["url"])), ok=True)
                errors = 0
            except Exception as e:  # noqa: BLE001 - record and continue; rerun retries failures
                rec.update(ok=False, error=str(e)[:200])
                errors += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
            if errors >= 20:
                print("stopping: 20 consecutive errors", file=sys.stderr)
                return 1
            time.sleep(max(0.0, 1.0 - (time.monotonic() - started)))  # at most 1 request per second
    print("iema-profiles: done", flush=True)
    return 0


# ---- target rows ---------------------------------------------------------------------------
UNRESOLVED = {"IDENTITY_ONLY", "ESCALATE", "IDENTITY_PROBLEM", "NO_WEB_EVIDENCE"}


def latest_checks():
    out = {}
    for e in read_jsonl(OC / "rapid" / "checks.jsonl"):
        if e.get("type") == "rapid_check" and (e["candidate_id"] not in out or
                                                e["recorded_at"] >= out[e["candidate_id"]]["recorded_at"]):
            out[e["candidate_id"]] = e
    return out


def cmd_targets(args):
    """Freeze the probe target set: every checked-unresolved row, plus calibration controls
    (known not-open: NOT_CURRENT_GP closed/moved/home_or_registration; known open: a seeded
    sample of VALID and VALID_CORRECTED rows)."""
    import collections
    import random
    queue = {c["cid"]: c for c in read_jsonl(OC / "rapid" / "queue.jsonl")}
    checks = latest_checks()
    rng = random.Random(20260927)
    roles = {}
    for cid, e in sorted(checks.items()):
        if cid not in queue:
            continue
        if e["decision"] in UNRESOLVED:
            roles[cid] = "unresolved"
        elif e["decision"] == "NOT_CURRENT_GP" and e.get("reason") in ("closed", "moved", "home_or_registration"):
            roles[cid] = "control_not_open:" + e["reason"]
    for dec, n in (("VALID", args.valid), ("VALID_CORRECTED", args.valid_corrected)):
        pool = sorted(c for c, e in checks.items() if c in queue and e["decision"] == dec)
        for cid in rng.sample(pool, min(n, len(pool))):
            roles[cid] = "control_open:" + dec
    if args.unchecked:
        for cid in queue:
            if cid not in checks:
                roles[cid] = "unchecked"
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "targets.jsonl"
    with dest.open("w") as fh:
        for cid, role in roles.items():
            c = queue[cid]
            fh.write(json.dumps({"cid": cid, "role": role, "base_entry_id": (checks.get(cid) or {}).get("entry_id"),
                                 **{k: c.get(k) for k in ("zip", "city", "name", "public_name", "address", "suite",
                                                          "phone", "website", "providers")}}) + "\n")
    print(f"targets: {len(roles)} rows -> {dest}")
    for role, n in collections.Counter(r.split(":")[0] for r in roles.values()).most_common():
        print(f"  {role}: {n}")
    return 0


# ---- Google Places (New) -------------------------------------------------------------------
# Google terms: only place IDs may be stored indefinitely. This cache is working data for the
# v2 packets: gitignored, never committed or published, purged after 30 days (`places-purge`).
# A v2 check records only the place ID/Maps link and our own conclusion in our own words.
PLACES_SEARCH = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS = "https://places.googleapis.com/v1/places/{}"
# Google bills a request at the highest tier any requested field belongs to, and bills Text
# Search per REQUEST, not per result. So the phone search asks for phone/website/reviews in the
# search itself (the Enterprise search SKUs, each with its own free cap) and needs no Details
# call; the address and name searches stay on Pro.
_PRO = ("id,displayName,formattedAddress,addressComponents,businessStatus,types,primaryType,googleMapsUri")
_ENT = _PRO + ",nationalPhoneNumber,websiteUri,userRatingCount"
_ATMOS = _ENT + ",reviews"
SEARCH_MASKS = {"search_pro": ",".join("places." + f for f in _PRO.split(",")),
                "search_ent": ",".join("places." + f for f in _ENT.split(",")),
                "search_ent_atmos": ",".join("places." + f for f in _ATMOS.split(","))}
SEARCH_MASK = SEARCH_MASKS["search_pro"]
DETAILS_MASKS = {"details_ent": "id,nationalPhoneNumber,websiteUri,userRatingCount",
                 "details_ent_atmos": "id,nationalPhoneNumber,websiteUri,userRatingCount,reviews"}
# List price (USD per request, first paid tier) and free requests per calendar month. The free
# cap is separate for EACH SKU and counted per billing account
# (developers.google.com/maps/billing-and-pricing/pricing, re-read 2026-09-27: Text Search Pro
# 5,000 free then $32/1k; Text Search Enterprise 1,000 then $35/1k; Text Search Enterprise +
# Atmosphere 1,000 then $40/1k; Place Details Enterprise 1,000 then $20/1k; Place Details
# Enterprise + Atmosphere 1,000 then $25/1k).
PRICE = {"search_pro": (0.032, 5000), "search_ent": (0.035, 1000), "search_ent_atmos": (0.040, 1000),
         "details_ent": (0.020, 1000), "details_ent_atmos": (0.025, 1000)}
PLACES_CACHE_DAYS = 30
PLACES_SCHEME = 2
REVIEW_FLAG_RE = re.compile(r"retir|closed|new (?:owner|dentist|doctor)|took over|sold|passed away|moved|relocat", re.I)


def slim_reviews(place):
    """Keep only what the rules read from reviews: date, rating, and our own flag for
    retirement/closure/successor language. Review text and author are dropped before caching."""
    if place.get("reviews") is not None:
        place["reviews"] = [{"publishTime": r.get("publishTime"), "rating": r.get("rating"),
                             "status_words": bool(REVIEW_FLAG_RE.search(str((r.get("text") or {}).get("text") or "")))}
                            for r in place["reviews"]]
    return place


def places_key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if key:
        return key
    for env in (ROOT / ".env", pathlib.Path.home() / "dental-pe-tracker" / ".env"):
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.strip().startswith("GOOGLE_PLACES_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GOOGLE_PLACES_API_KEY not set (environment or ~/dental-pe-tracker/.env)")


class Spend:
    """Local call ledger. Each call is reserved BEFORE it is sent (a timeout still counts), and
    the estimated bill = calls beyond the monthly free allotment x list price. Refuses to send
    once the estimate would pass the cap."""

    def __init__(self, cap_usd):
        self.path = OUT / "places_ledger.jsonl"
        self.cap = cap_usd
        self.month = datetime.date.today().strftime("%Y-%m")
        self.calls = {sku: 0 for sku in PRICE}
        for r in read_jsonl(self.path):
            if r["month"] == self.month:
                self.calls[r["sku"]] = self.calls.get(r["sku"], 0) + 1

    def estimate(self, calls=None):
        calls = calls or self.calls
        return sum(max(0, calls[s] - PRICE[s][1]) * PRICE[s][0] for s in PRICE)

    def free_left(self, sku):
        return max(0, PRICE[sku][1] - self.calls[sku])

    def allowed(self, sku):
        after = dict(self.calls)
        after[sku] += 1
        return self.estimate(after) <= self.cap

    def report(self):
        lines = [f"  {sku:18} {self.calls[sku]:5} used of {free:5} free this month "
                 f"(then ${price * 1000:.0f} per 1,000)" for sku, (price, free) in PRICE.items()]
        return "\n".join(lines) + f"\n  estimated bill so far ${self.estimate():.2f} (cap ${self.cap:.2f})"

    def reserve(self, sku, cid):
        if not self.allowed(sku):
            raise SystemExit(f"SPEND CAP: estimated ${self.estimate():.2f} of ${self.cap:.2f}; not sending more")
        self.calls[sku] += 1
        with self.path.open("a") as fh:
            fh.write(json.dumps({"month": self.month, "sku": sku, "cid": cid,
                                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}) + "\n")


def places_call(url, key, mask, body=None):
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": mask, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    # Refused and failed requests are not billed; retry briefly (a new key or billing change can
    # flap between 403 and 200 for a few minutes) before giving up.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403, 429) or e.code >= 500:
                if attempt < 3:
                    time.sleep(20 * (attempt + 1))
                    continue
                if e.code in (401, 403):
                    raise SystemExit(f"Places API refused the key ({e.code}): {detail}")
            return {"error": {"code": e.code, "detail": detail}}
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            # URLError, timeouts, RemoteDisconnected/ConnectionReset (OSError), IncompleteRead
            if attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            return {"error": {"code": None, "detail": str(e)[:300]}}


def digits10(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else None


def _comp(place, kind):
    for c in place.get("addressComponents") or []:
        if kind in (c.get("types") or []):
            return c.get("shortText") or c.get("longText")
    return None


def _row_house(address):
    s = _parse_site(address)
    if s:
        return s[0]
    m = re.match(r"\s*(\d+)", str(address or ""))  # "15419-127th St" -> "15419"
    return m.group(1) if m else None


def place_matches_site(place, row):
    """House number + ZIP agreement, and the street name when Google gives one (a same-number
    address on another street in the ZIP is not the site). Street spellings vary, so any shared
    street word is enough."""
    house = _row_house(row.get("address"))
    if not house or (_comp(place, "street_number") or "").upper() != house or \
            (_comp(place, "postal_code") or "")[:5] != str(row.get("zip"))[:5]:
        return False
    route = _comp(place, "route")
    if not route:
        return True
    mine = _parse_site(row.get("address"))
    theirs = _parse_site(f"{house} {route}")
    if not mine or not theirs:
        return True
    return bool(set(mine[2].split()) & set(theirs[2].split()))


def place_site(place):
    """(street line, suite, ZIP5) of a Google listing, from its address components."""
    num, route = _comp(place, "street_number"), _comp(place, "route")
    sub = _comp(place, "subpremise")
    return ((f"{num} {route}" if num and route else None), sub, (_comp(place, "postal_code") or "")[:5] or None)


def iema_phone_sites():
    """Site key -> phones of IEMA dental facilities there (full registry export). A row whose
    phone is already on an X-ray registration at its site can be settled by PL-IEMA with the
    phone tie alone, so its phone search does not need the reviews (Atmosphere) SKU."""
    out = {}
    for r in iema_dental_rows():
        k, ph = _addr_key(r.get("Physical Address"), r.get("Zip")), digits10(r.get("Phone Number"))
        if k and ph:
            out.setdefault(k, set()).add(ph)
    return out


def _dental(p, rules):
    return bool(set(p.get("types") or []) & rules.DENTAL_TYPES) or p.get("primaryType") in rules.DENTAL_TYPES


def _name_tie(p, t, rules):
    dn = str((p.get("displayName") or {}).get("text") or "")
    row = rules.name_tokens(t.get("public_name")) | rules.name_tokens(t.get("name"))
    return bool(row & rules.name_tokens(dn)) or any(
        re.search(r"\b" + re.escape(ln) + r"\b", dn.lower()) for ln in rules.provider_lastnames(t.get("providers")))


def enrichment_plan(t, found, rules, needs_reviews):
    """At most ONE Details request per row, on the cheapest SKU that can settle a rule, for a
    listing the searches found without its phone (Pro fields only). Returns (place_id, sku, why)."""
    phone = digits10(t.get("phone"))
    at_site = [p for p in found.values() if place_matches_site(p, t) and _dental(p, rules)]
    tied_here = [p for p in at_site if phone and digits10(p.get("nationalPhoneNumber")) == phone]
    operating = [p for p in at_site if p.get("businessStatus") == "OPERATIONAL"]
    if any(p.get("businessStatus") == "OPERATIONAL" and ("reviews" in p or not needs_reviews) for p in tied_here):
        return None, None, "phone_search_settles"
    bare = [p for p in operating if "nationalPhoneNumber" not in p]
    if bare:
        pick = next((p for p in bare if _name_tie(p, t, rules)), bare[0])
        return pick["id"], ("details_ent_atmos" if needs_reviews else "details_ent"), "operating_at_site_needs_phone"
    tied_no_reviews = [p for p in tied_here if p.get("businessStatus") == "OPERATIONAL" and "reviews" not in p]
    if tied_no_reviews and needs_reviews:
        return tied_no_reviews[0]["id"], "details_ent_atmos", "operating_tied_needs_reviews"
    closed = [p for p in at_site if p.get("businessStatus") == "CLOSED_PERMANENTLY"
              and "nationalPhoneNumber" not in p and not _name_tie(p, t, rules)]
    if closed:
        return closed[0]["id"], "details_ent", "closed_needs_phone_tie"
    return None, None, "nothing_to_look_up"


def cmd_places(args):
    """Scheme 2, per row, stopping at every SKU's free cap (--cap 0):
      1. phone search (row phone, E.164) on Text Search Enterprise + Atmosphere when the row has no
         IEMA same-site phone registration (it may need a review date), else Text Search Enterprise;
         falls back to the other Enterprise SKU, then Pro, as free caps run out;
      2. address search "dentist <address>" on Pro (10 results): who operates at the site now,
         skipped when the phone search already found the row's operating listing at the site;
      3. name search "<name> <city> IL" on Pro, only when neither found a listing tied to the row;
      4. at most one Details lookup (enrichment_plan) for a site listing found without its phone."""
    import collections
    sys.path.insert(0, str(ROOT / "scrapers"))
    import office_census_v2_rules as rules
    key = places_key()
    spend = Spend(args.cap)
    dest = OUT / "places.jsonl"
    latest = {}
    for r in read_jsonl(dest):
        if r.get("ok") and r.get("scheme") == PLACES_SCHEME:
            latest[r["cid"]] = r
    done = {cid for cid, r in latest.items() if not r.get("pending_details")}
    roles = args.roles.split(",") if args.roles else None
    targets = [t for t in read_jsonl(OUT / "targets.jsonl") if t["cid"] not in done
               and (not roles or t["role"].split(":")[0] in roles)]
    order = {"control_not_open": 0, "control_open": 1, "unresolved": 2, "unchecked": 3}
    targets.sort(key=lambda t: order.get(t["role"].split(":")[0], 9))
    if args.limit:
        targets = targets[:args.limit]
    free_resolved = set()
    if args.skip_free_resolved:
        # unresolved rows the free rules already settle get the searches (a conflict check) only
        for pk in read_jsonl(OUT / "packets.jsonl"):
            prop = pk["eval"]["proposal"]
            if pk["role"] in ("unresolved", "unchecked") and prop and prop["rule_id"] in rules.FREE_RULES \
                    and not pk["eval"].get("conflicts"):
                free_resolved.add(pk["cid"])
    iema_sites = iema_phone_sites()
    print(f"places: {len(done)} cached, {len(targets)} to probe, {len(free_resolved)} settled by free evidence "
          f"(no Details lookup)\n{spend.report()}", flush=True)
    stats = collections.Counter()
    now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")  # noqa: E731
    stopped = None

    def search(kind, text, skus, cid, page_size):
        nonlocal stopped
        sku = next((k for k in skus if spend.free_left(k) > 0 or spend.allowed(k)), None)
        if not sku:
            stopped = "search free allotments used up"
            return None, None
        spend.reserve(sku, cid)
        res = places_call(PLACES_SEARCH, key, SEARCH_MASKS[sku],
                          {"textQuery": text, "regionCode": "US", "languageCode": "en", "pageSize": page_size})
        stats[sku] += 1
        return sku, res

    t0 = time.monotonic()
    with dest.open("a") as fh:
        for n, t in enumerate(targets, 1):
            if args.max_seconds and time.monotonic() - t0 > args.max_seconds:
                stopped = f"paused after {n - 1} rows (--max-seconds); rerun to resume"
                break
            prior = latest.get(t["cid"])
            key_site = _addr_key(t.get("address"), t.get("zip"))
            phone = digits10(t.get("phone"))
            on_iema = bool(key_site) and phone in iema_sites.get(key_site, set())
            needs_reviews = not on_iema
            if prior and prior.get("pending_details"):
                rec = {k: v for k, v in prior.items() if k != "pending_details"}
                pid, sku, why = (prior["pending_details"][k] for k in ("place_id", "sku", "why"))
            else:
                rec = {"cid": t["cid"], "role": t["role"], "ok": True, "scheme": PLACES_SCHEME, "queries": [],
                       "details": {}, "fetched_at": now()}
                found = {}

                def run(kind, text, skus, page_size):
                    sku, res = search(kind, text, skus, t["cid"], page_size)
                    if res is None:
                        return False
                    if "error" in res:
                        rec["ok"], rec["error"] = False, res["error"]
                        return False
                    ids = []
                    for p in res.get("places") or []:
                        # Google omits empty fields: mark what this SKU asked for, so a listing with
                        # no phone or no reviews is not looked up again for them.
                        if sku in ("search_ent", "search_ent_atmos"):
                            p.setdefault("nationalPhoneNumber", None)
                        if sku == "search_ent_atmos":
                            p.setdefault("reviews", [])
                        p = slim_reviews(p)
                        if p["id"] in found:
                            found[p["id"]].update({k: v for k, v in p.items() if k not in found[p["id"]]})
                        else:
                            found[p["id"]] = p
                        ids.append(p["id"])
                    rec["queries"].append({"kind": kind, "sku": sku, "text": text, "place_ids": ids})
                    return True

                city = t.get("city") or ""
                ok = True
                if phone:
                    skus = (["search_ent_atmos", "search_ent"] if needs_reviews else ["search_ent", "search_ent_atmos"]) \
                        + ["search_pro"]
                    ok = run("phone", f"+1 {phone[:3]}-{phone[3:6]}-{phone[6:]}", skus, 5)
                tied = lambda p: phone and digits10(p.get("nationalPhoneNumber")) == phone  # noqa: E731
                if ok and not any(place_matches_site(p, t) and _dental(p, rules) and tied(p)
                                  and p.get("businessStatus") == "OPERATIONAL" for p in found.values()):
                    ok = run("address", f"dentist {t.get('address') or ''} {city} IL {t.get('zip') or ''}".strip(),
                             ["search_pro"], 10)
                label = t.get("public_name") or t.get("name")
                if ok and label and not any(tied(p) or _name_tie(p, t, rules) for p in found.values()):
                    ok = run("name", f"{label} {city} IL", ["search_pro"], 5)
                if stopped:
                    break
                rec["search_places"] = found
                pid, sku, why = enrichment_plan(t, found, rules, needs_reviews) if t["cid"] not in free_resolved \
                    else (None, None, "free_evidence_resolves")
            rec["lookup"] = {"place_id": pid, "sku": sku, "why": why}
            stats["why:" + why] += 1
            if pid and rec["ok"]:
                pick = sku if spend.free_left(sku) > 0 else next(
                    (k for k in ("details_ent_atmos", "details_ent") if spend.free_left(k) > 0
                     and (k == "details_ent_atmos" or sku == "details_ent")), None)
                if pick and spend.allowed(pick):
                    spend.reserve(pick, t["cid"])
                    det = places_call(PLACES_DETAILS.format(pid), key, DETAILS_MASKS[pick])
                    if "error" not in det:
                        det.setdefault("nationalPhoneNumber", None)
                        if pick == "details_ent_atmos":
                            det.setdefault("reviews", [])
                    rec["details"][pid] = {"error": det["error"]} if "error" in det else slim_reviews(det)
                    rec["details_fetched_at"] = now()
                    stats[pick] += 1
                else:  # past the free allotment: hold the lookup for next month instead of paying
                    rec["pending_details"] = {"place_id": pid, "sku": sku, "why": why}
                    stats["held:" + sku] += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(targets)} · " + " · ".join(f"{k} {v}" for k, v in sorted(stats.items())
                                                             if not k.startswith("why:")) +
                      f" · est ${spend.estimate():.2f}", flush=True)
    if stopped:
        print(f"places: stopped early ({stopped})", flush=True)
    print("places: done\n  " + "\n  ".join(f"{k:40} {v}" for k, v in sorted(stats.items())) + f"\n{spend.report()}",
          flush=True)
    return 0


def cmd_places_reviews(args):
    """One Place Details (Enterprise + Atmosphere) lookup per row for the listing whose review dates
    would decide the row: an operating dental listing at the site (tied first, then untied), else
    the row phone's listing at another address. Only listings whose reviews were never fetched.
    Free allotment only (--cap 0); the record is re-appended with the details merged."""
    sys.path.insert(0, str(ROOT / "scrapers"))
    import office_census_v2_rules as rules
    key = places_key()
    spend = Spend(args.cap)
    latest = {r["cid"]: r for r in read_jsonl(OUT / "places.jsonl") if r.get("ok") and r.get("scheme") == PLACES_SCHEME}
    order = {"unresolved": 0, "control_not_open": 1, "control_open": 2, "unchecked": 3}
    plan = []
    for pk in read_jsonl(OUT / "packets.jsonl"):
        f = rules.facts(pk)
        site = [pl for pl, t in f["pl_site_ties"] if t] + [pl for pl, t in f["pl_site_ties"] if not t]
        cands = [pl for pl in site + f["pl_phone_elsewhere"] if pl.get("reviews") is None
                 and pl.get("id") not in (latest.get(pk["cid"], {}).get("details") or {})]
        if cands:
            plan.append((order.get(pk["role"].split(":")[0], 9), pk["cid"], cands[0]["id"]))
    plan.sort()
    if args.limit:
        plan = plan[:args.limit]
    print(f"places-reviews: {len(plan)} rows need a review-date lookup\n{spend.report()}", flush=True)
    n = 0
    with (OUT / "places.jsonl").open("a") as fh:
        for _, cid, pid in plan:
            if spend.free_left("details_ent_atmos") <= 0 or not spend.allowed("details_ent_atmos"):
                print("places-reviews: free allotment used up; the rest wait for the monthly reset", flush=True)
                break
            spend.reserve("details_ent_atmos", cid)
            det = places_call(PLACES_DETAILS.format(pid), key, DETAILS_MASKS["details_ent_atmos"])
            rec = dict(latest[cid])
            rec["details"] = dict(rec.get("details") or {})
            if "error" in det:
                rec["details"][pid] = {"error": det["error"]}
            else:
                det.setdefault("nationalPhoneNumber", None)
                det.setdefault("reviews", [])
                rec["details"][pid] = slim_reviews(det)
            rec["details_fetched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            latest[cid] = rec
            n += 1
    print(f"places-reviews: {n} lookups\n{spend.report()}", flush=True)
    return 0


def cmd_places_cost(args):
    print(Spend(args.cap).report())
    return 0


def cmd_places_purge(args):
    dest = OUT / "places.jsonl"
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=PLACES_CACHE_DAYS)
    keep = [r for r in read_jsonl(dest) if datetime.datetime.fromisoformat(r["fetched_at"]) >= cutoff]
    dest.write_text("".join(json.dumps(r) + "\n" for r in keep))
    print(f"places-purge: kept {len(keep)} records fetched within {PLACES_CACHE_DAYS} days")
    return 0


# ---- real-browser website probe -----------------------------------------------------------
# The rapid checker's fetch tool fails on bot-protected / JS-rendered sites. This probe opens
# every candidate office website in the locally installed Chrome (headless Playwright), follows
# one or two contact/location links, and keeps only what adjudication needs: status, final URL,
# a classification, address-like snippets, phone numbers and page titles. No full page text.
LISTING_HOSTS = (
    "yelp.", "healthgrades.", "webmd.", "zocdoc.", "google.", "facebook.", "vitals.", "npi", "yellowpages",
    "bbb.org", "carecredit", "mapquest", "linkedin", "instagram", "dentalplans", "doctor.", "sharecare",
    "loopnet", "zillow", "redfin", "homes.com", "compass.com", "crexi", "apartments.com", "opencorporates",
    "bizapedia", "manta.", "chamberofcommerce", "nextdoor", "caredash", "usnews", "findatopdoc", "dentistsok",
    "dr-leonardo", "hipaaspace", "doctorsnetwork", "patientconnect365", "dentistsranked", "localsearch",
    "buzzfile", "yahoo", "bing.", "legacy.com", "obituar", "idfpr", "iema", "illinois.gov", "ada.org",
    "deltadental", "cigna", "aetna", "metlife", "guardian", "humana", "uhc", "bcbs", "medicaid", "medicare",
    "wikipedia", "github", "cityfeet", "atproperties")
PARKED_HOSTS = ("forsale.godaddy", "sedo.com", "dan.com", "afternic", "hugedomains", "parkingcrew", "bodis",
                "above.com", "undeveloped.com", "domainmarket", "sav.com", "lander")
PARKED_RE = re.compile(r"domain (?:name )?(?:is|may be) for sale|buy this domain|this domain (?:is )?(?:parked|expired)|"
                       r"parked (?:free|domain)|get a price in 24 hours|domain has expired|renew (?:this|your) domain|"
                       r"website expired|site (?:has )?expired|account (?:has been )?suspended", re.I)
HIJACK_RE = re.compile(r"casino|slot|gambl|betting|ufabet|togel|poker|judi|bola|คาสิโน|แทงบอล|토토|카지노|바카라|viagra|cialis|loan", re.I)
CHALLENGE_RE = re.compile(r"just a moment|verify you are human|attention required|access denied|checking your browser|"
                          r"enable javascript and cookies", re.I)
DENTAL_RE = re.compile(r"dental|dentist|dentistry|teeth|tooth|orthodont|implant|smile|hygien|crown|filling|cleaning", re.I)
GP_RE = re.compile(r"general dentistry|family dentistry|cleanings?|fillings?|preventive|exams?|crowns?|root canal|"
                   r"dentures|periodontal maintenance|emergency dental", re.I)
CONTACT_LINK_RE = re.compile(r"contact|location|office|visit|direction|find[- ]us|about|our[- ]practice|hours", re.I)
ADDR_SNIPPET_RE = re.compile(r"\b\d{2,6}[A-Z]?\s+(?:[NSEW]\.?\s+)?[A-Za-z0-9.'\- ]{2,40}?\b(?:St|Street|Ave|Avenue|Rd|Road|Blvd|"
                             r"Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Pl|Place|Pkwy|Parkway|Hwy|Highway|Way|Cir|Circle|"
                             r"Ter|Terrace|Trl|Trail|Sq|Plz|Plaza|Pike|Center|Centre|Route|Rt)\b[^\n]{0,80}", re.I)
PHONE_RE = re.compile(r"\(?\b([2-9]\d{2})\)?[\s.\-]*([2-9]\d{2})[\s.\-]*(\d{4})\b")
BROWSER_VERSION = 2
# v2 also keeps: dentist names on the page, status language (closed / moved / retired / successor)
# with a little context, and the text just before each address snippet (narrative mentions such
# as "moved from 1642 W. Belmont Ave" are not the office's address).
DENTIST_RE = re.compile(r"\bDr\.?\s+([A-Z][a-z]+(?:[\s-][A-Z]\.?)?\s+[A-Z][A-Za-z'\-]+)|"
                        r"\b([A-Z][a-z]+(?:\s[A-Z]\.?)?\s+[A-Z][A-Za-z'\-]+),?\s+(?:D\.?D\.?S|D\.?M\.?D)\b")
STATUS_TEXT_RE = re.compile(r"permanently closed|(?:has|have|is now|are now) closed|closed (?:its|our) doors|"
                            r"(?:we|we've|we have|has|have|office has) (?:moved|relocated)|\bmoved (?:to|from|our)\b|relocat(?:ed|ing) to|"
                            r"new (?:location|address|office)|formerly (?:located|known)|retir(?:ed|ement|ing)|"
                            r"patients of dr|welcome (?:dr\.?|patients)|joined (?:our|the) (?:practice|team)|"
                            r"new owner|acquired|transition(?:ed|ing)? (?:of|to)|no longer (?:practicing|seeing)", re.I)


def host_of(u):
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/:?#\s]+)", str(u or "").strip().lower())
    return m.group(1) if m else None


def candidate_pages(target, row_checks):
    """Specific office-website pages on file (a DSO location page, a contact page), beyond the
    homepage: the row's website and first-party/locator evidence URLs that carry a path."""
    urls = set()
    for u in [target.get("website")] + [ev.get("url") for e in row_checks for ev in e.get("evidence") or []
                                        if ev.get("kind") in ("first_party_site", "dso_locator")]:
        h = host_of(u)
        if not h or any(b in h for b in LISTING_HOSTS):
            continue
        m = re.match(r"^(?:https?://)?[^/]+(/[^?#]*)", str(u).strip())
        path = (m.group(1) if m else "").rstrip("/")
        if path and path not in ("/index.html", "/index.php", "/home"):
            urls.add("https://" + str(u).strip().split("://", 1)[-1].split("#")[0])
    return sorted(urls)


def candidate_hosts(target, row_checks, places_rec=None):
    """Office-website hosts worth opening for this row: website on file, first-party/locator URLs
    and observed websites from every prior check, domains named in checker notes, and the
    websiteUri of any Places listing at the row's site (when the Places probe has run)."""
    cands = set()
    if target.get("website"):
        cands.add(target["website"])
    for e in row_checks:
        for ev in e.get("evidence") or []:
            if ev.get("kind") in ("first_party_site", "dso_locator") and ev.get("url"):
                cands.add(ev["url"])
        if (e.get("observed") or {}).get("website"):
            cands.add(e["observed"]["website"])
        cands.update(re.findall(r"\b([a-z0-9][a-z0-9-]+\.(?:com|net|org|dental|us|biz|info|co|care|health|clinic))\b",
                                (e.get("note") or "").lower()))
    for det in list(((places_rec or {}).get("details") or {}).values()) + \
            list(((places_rec or {}).get("search_places") or {}).values()):
        if det.get("websiteUri"):
            cands.add(det["websiteUri"])
    return sorted({h for h in (host_of(u) for u in cands) if h and "." in h and not any(b in h for b in LISTING_HOSTS)})


def classify_page(final_url, status, title, text):
    t = (title or "") + " " + (text or "")[:4000]
    if any(p in (final_url or "") for p in PARKED_HOSTS) or PARKED_RE.search(t):
        return "parked_or_for_sale"
    if CHALLENGE_RE.search(t[:3000]) and len(text or "") < 3000:
        return "bot_challenge"
    if status and status >= 500:
        return "server_error"
    if status and status >= 400:
        return "http_error"
    dental = len(DENTAL_RE.findall(t))
    if HIJACK_RE.search(t) and dental < 3:
        return "hijacked_spam"
    if len((text or "").strip()) < 80:
        return "empty"
    return "live_dental" if dental >= 2 else "live_not_dental"


def summarize_text(text):
    text = text or ""
    phones = sorted({"".join(m.groups()) for m in PHONE_RE.finditer(text)})[:25]
    addrs, context = [], []
    for m in ADDR_SNIPPET_RE.finditer(text):
        s = re.sub(r"\s+", " ", m.group(0)).strip()[:160]
        if s not in addrs:
            addrs.append(s)
            context.append({"text": s, "pre": re.sub(r"\s+", " ", text[max(0, m.start() - 60):m.start()]).strip()[-60:]})
        if len(addrs) >= 16:
            break
    dentists = []
    for m in DENTIST_RE.finditer(text):
        nm = re.sub(r"\s+", " ", (m.group(1) or m.group(2) or "")).strip().lower()
        if nm and nm not in dentists:
            dentists.append(nm)
        if len(dentists) >= 30:
            break
    status = []
    for m in STATUS_TEXT_RE.finditer(text):
        snip = re.sub(r"\s+", " ", text[max(0, m.start() - 90):m.end() + 90]).strip()
        if not any(snip[:40] in x for x in status):
            status.append(snip[:200])
        if len(status) >= 8:
            break
    return {"phones": phones, "address_snippets": addrs, "address_context": context, "dentists": dentists,
            "status_text": status, "gp_terms": sorted({g.lower() for g in GP_RE.findall(text)})[:12]}


async def _probe_host(ctx, hostname, sem, url=None):
    """Open a host's homepage (url None) or one specific page on file (url), plus up to two
    contact/location links on the same host."""
    rec = {"host": hostname, "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "version": BROWSER_VERSION, "pages": []}
    if url:
        rec["url"] = url
    async with sem:
        page = await ctx.new_page()
        try:
            try:
                resp = await page.goto(url or ("https://" + hostname), timeout=25000, wait_until="domcontentloaded")
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "ERR_NAME_NOT_RESOLVED" in msg:
                    rec["class"] = "dns_dead"
                    return rec
                resp = await page.goto((url or ("https://" + hostname)).replace("https://", "http://", 1),
                                       timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            text = await page.inner_text("body")
            title = await page.title()
            rec.update(status=resp.status if resp else None, final_url=page.url, title=(title or "")[:120])
            rec["class"] = classify_page(page.url, rec["status"], title, text)
            rec["pages"].append({"url": page.url, **summarize_text(text)})
            if rec["class"] == "live_dental":
                base = host_of(page.url)
                links = await page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, (e.innerText||'').trim()])")
                seen, hops = {page.url.rstrip("/")}, []
                for href, label in links:
                    if host_of(href) == base and CONTACT_LINK_RE.search(href + " " + label) and href.rstrip("/") not in seen:
                        seen.add(href.rstrip("/"))
                        hops.append(href)
                for href in hops[:2]:
                    try:
                        await page.goto(href, timeout=20000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(1500)
                        rec["pages"].append({"url": page.url, **summarize_text(await page.inner_text("body"))})
                    except Exception as e:  # noqa: BLE001
                        rec["pages"].append({"url": href, "error": str(e)[:120]})
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            rec["class"] = ("dns_dead" if "ERR_NAME_NOT_RESOLVED" in msg else
                            "timeout" if "Timeout" in msg else "connect_error")
            rec["error"] = msg[:160]
        finally:
            await page.close()
    return rec


def browser_key(rec):
    return rec.get("url") or rec["host"]


def load_browser():
    """Latest record per key (host homepage, or a specific page URL); a v2 re-probe appended after
    a v1 record supersedes it. The file is append-only: nothing is ever deleted."""
    out = {}
    for r in read_jsonl(OUT / "browser.jsonl"):
        k = browser_key(r)
        if k not in out or r.get("version", 1) >= out[k].get("version", 1):
            out[k] = r
    return out


def cmd_browser(args):
    import asyncio
    from playwright.async_api import async_playwright
    checks_by_row = {}
    for e in read_jsonl(OC / "rapid" / "checks.jsonl"):
        checks_by_row.setdefault(e["candidate_id"], []).append(e)
    places = {r["cid"]: r for r in read_jsonl(OUT / "places.jsonl") if r.get("ok")}
    keys, rank = set(), {}
    # rows still without a proposal first, then unresolved rows, then controls
    pending = {pk["cid"]: (0 if not pk["eval"]["proposal"] else 1 if pk["eval"]["proposal"].get("confidence") == "review"
                           else 2) for pk in read_jsonl(OUT / "packets.jsonl") if pk["role"] == "unresolved"}
    for t in read_jsonl(OUT / "targets.jsonl"):
        rc = checks_by_row.get(t["cid"], [])
        mine = {(h, None) for h in candidate_hosts(t, rc, places.get(t["cid"]))} | \
            {(host_of(u), u) for u in candidate_pages(t, rc)}
        keys |= mine
        for k in mine:
            rank[k] = min(rank.get(k, 9), pending.get(t["cid"], 3))
    dest = OUT / "browser.jsonl"
    have = load_browser()
    todo = sorted((k for k in keys if (k[1] or k[0]) not in have
                  or have[k[1] or k[0]].get("version", 1) < BROWSER_VERSION),
                  key=lambda k: (rank.get(k, 9), k[0], k[1] or ""))
    if args.limit:
        todo = todo[:args.limit]
    print(f"browser: {len(have)} keys cached, {len(todo)} to open (new or v1 re-probe)", flush=True)
    t0 = time.monotonic()

    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch(channel="chrome", headless=True,
                                        args=["--disable-blink-features=AutomationControlled"])
            ctx = await b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900})
            sem = asyncio.Semaphore(args.concurrency)
            with dest.open("a") as fh:
                step = args.concurrency * 4
                for i in range(0, len(todo), step):
                    if args.max_seconds and time.monotonic() - t0 > args.max_seconds:
                        print(f"browser: paused after {i} (--max-seconds); rerun to resume", flush=True)
                        break
                    for rec in await asyncio.gather(*[_probe_host(ctx, h, sem, u) for h, u in todo[i:i + step]]):
                        fh.write(json.dumps(rec) + "\n")
                    fh.flush()
            await b.close()
    asyncio.run(run())
    print("browser: done", flush=True)
    return 0


# ---- packets + calibration ---------------------------------------------------------------------
IDFPR_RECORD = "https://data.illinois.gov/resource/pzzh-kp68.json?license_number={}"


def _parse_site(addr):
    """(house, directional, street core) for site matching. The core drops the directional and
    the street suffix, because registries and directories disagree on both ("Wiesbrook Rd" vs
    "Wiesbrook Dr", "N Airlite St" vs "Airlite St"); a DuPage grid house split by a space
    ("40 W 320 Lafox Rd") is rejoined ("40W320")."""
    sys.path.insert(0, str(ROOT / "scrapers"))
    import office_census_address as oca
    try:
        parsed = oca.parse_physical_address(str(addr or ""))
    except Exception:  # noqa: BLE001
        return None
    if not parsed.get("house"):
        return None
    house, toks = parsed["house"], (parsed["street"] or "").split()
    if len(toks) >= 2 and toks[0] in ("n", "s", "e", "w") and re.fullmatch(r"\d+", toks[1]) and house.isdigit():
        house, toks = f"{house}{toks[0].upper()}{toks[1]}", toks[2:]
    direction = toks[0] if toks and toks[0] in oca.DIRECTIONALS else None
    core = [re.sub(r"^(\d+)(?:st|nd|rd|th)$", r"\1", t) for t in toks
            if t not in oca.DIRECTIONALS and t not in oca.SUFFIX_VALUES]  # "127th" == "127"
    return (house.upper(), direction, " ".join(core)) if core else None


def _addr_key(addr, zip_code):
    """Loose site key: (ZIP5, house, street core). Pair with _dir_ok() for the directional."""
    s = _parse_site(addr)
    return (str(zip_code or "")[:5], s[0], s[2]) if s else None


def _addr_dir(addr):
    s = _parse_site(addr)
    return s[1] if s else None


def _dir_ok(a, b):
    """Directionals agree, or one side omits it."""
    return not a or not b or a == b


def _name_key(first, last):
    f = str(first or "").lower().split()
    return (re.sub(r"[^a-z]", "", f[0]) if f else "", re.sub(r"[^a-z]", "", str(last or "").lower()))


def _provider_key(provider):
    parts = [t for t in re.findall(r"[A-Za-z]+", provider or "")
             if t.upper() not in {"DDS", "DMD", "JR", "SR", "II", "III", "MS", "PC", "DR"}]
    return (parts[0].lower(), parts[-1].lower()) if len(parts) >= 2 else None


def load_iema_profiles():
    """Dental IEMA facilities keyed by site and by phone. Profile fields when fetched, else the
    export row with status unknown (None)."""
    prof = {r["facility_id"]: r for r in read_jsonl(OUT / "iema_profiles.jsonl") if r.get("ok")}
    by_site, by_phone, facs = {}, {}, []
    for r in iema_dental_rows():
        fid = str(r["Facility ID"])
        pr = prof.get(fid) or {}
        fac = {"facility_id": fid, "url": IEMA_PROFILE.format(fid), "name": pr.get("name") or r["Facility Name"],
               "status": pr.get("status"), "administrator": pr.get("administrator"),
               "physical_address": pr.get("physical_address") or f"{r['Physical Address']}, {r['City']}, IL {r['Zip']}",
               "phone": pr.get("phone") or r["Phone Number"], "active_units": pr.get("active_units"),
               "mobile_only": pr.get("mobile_only"), "profiled": bool(pr), "category": r["Category"]}
        fac["site_key"] = _addr_key(r["Physical Address"], r["Zip"])
        fac["site_dir"] = _addr_dir(r["Physical Address"])
        facs.append(fac)
        if fac["site_key"]:
            by_site.setdefault(fac["site_key"], []).append(fac)
        if digits10(fac["phone"]):
            by_phone.setdefault(digits10(fac["phone"]), []).append(fac)
    return facs, by_site, by_phone


def load_licenses():
    lic = json.loads((REG / "idfpr_dental_licenses_20260927.json").read_text())
    by_name = {}
    for r in lic:
        by_name.setdefault(_name_key(r.get("first_name"), r.get("last_name")), []).append(r)
    return by_name


def license_summary(provider, by_name, row):
    k = _provider_key(provider)
    recs = by_name.get(k, []) if k else []
    if not recs:
        return {"provider": provider, "status": None}
    local = [r for r in recs if (r.get("zip") or "")[:5] == str(row.get("zip")) or
             (r.get("city") or "").lower() == str(row.get("city") or "").lower()]
    pool = local or recs
    gp = [r for r in pool if r["description"] == "LICENSED DENTIST"] or pool
    active = [r for r in gp if r["license_status"] == "ACTIVE"]
    pick = (active or sorted(gp, key=lambda r: r.get("expiration_date") or "", reverse=True))[0]
    spec_active = any(r["description"] == "LICENSED SPECIALIST IN DENTISTRY" and r["license_status"] == "ACTIVE"
                      for r in pool)
    status = "ACTIVE" if active else pick["license_status"]
    return {"provider": provider, "status": status, "name": pick.get("business_name"),
            "description": pick["description"], "expiration_date": pick.get("expiration_date"),
            "city": pick.get("city"), "zip": pick.get("zip"), "specialist_active": spec_active,
            "specialty": next((r.get("specialty_qualifier") for r in pool
                               if r["description"] == "LICENSED SPECIALIST IN DENTISTRY"), None),
            "matches": len(recs), "local_matches": len(local),
            "url": IDFPR_RECORD.format(pick.get("license_number")) if "*" not in str(pick.get("license_number")) else
            "https://data.illinois.gov/d/pzzh-kp68"}


def cmd_packets(args):
    import collections
    sys.path.insert(0, str(ROOT / "scrapers"))
    import office_census_v2_rules as rules
    queue = {c["cid"]: c for c in read_jsonl(OC / "rapid" / "queue.jsonl")}
    checks_by_row = {}
    for e in read_jsonl(OC / "rapid" / "checks.jsonl"):
        checks_by_row.setdefault(e["candidate_id"], []).append(e)
    latest = latest_checks()
    facs, iema_site, _ = load_iema_profiles()
    lic_by_name = load_licenses()
    places = {r["cid"]: r for r in read_jsonl(OUT / "places.jsonl") if r.get("ok")}
    browser = load_browser()
    adm_index = {}
    for fac in facs:
        for tok in set(re.findall(r"[a-z]+", str(fac.get("administrator") or "").lower())):
            adm_index.setdefault(tok, []).append(fac)
    # other directory rows by site and by phone (rapid index: every candidate row; loc: = directory rows)
    idx = json.loads((OC / "rapid" / "index.json").read_text())
    rows_site, rows_phone = {}, {}
    for cid, e in idx["entries"].items():
        if not cid.startswith("loc:"):
            continue
        lc = latest.get(cid) or {}
        r = {"cid": cid, "name": e[3], "address": e[4], "zip": e[2], "suite": e[5], "phone": e[6],
             "decision": lc.get("decision"), "reason": lc.get("reason"),
             "observed": {k: v for k, v in (lc.get("observed") or {}).items() if k in ("name", "phone", "address")}}
        k = _addr_key(e[4], e[2])
        if k:
            rows_site.setdefault(k, []).append(r)
        if digits10(e[6]):
            rows_phone.setdefault(digits10(e[6]), []).append(r)
    _, _, iema_by_phone = load_iema_profiles()
    targets = read_jsonl(OUT / "targets.jsonl")
    dest = OUT / "packets.jsonl"
    report = collections.defaultdict(collections.Counter)
    with dest.open("w") as fh:
        for t in targets:
            card = queue[t["cid"]]
            base = latest.get(t["cid"]) or {}
            key = _addr_key(card.get("address"), card.get("zip"))
            row_dir = _addr_dir(card.get("address"))
            site_facs = [f for f in iema_site.get(key, []) if _dir_ok(f["site_dir"], row_dir)] if key else []
            elsewhere = []
            for prov in card.get("providers") or []:
                pk = _provider_key(prov)
                if pk:
                    elsewhere += [f for f in adm_index.get(pk[1], []) if pk[0] in str(f.get("administrator") or "").lower()
                                  and f["site_key"] != key]
            pr = places.get(t["cid"]) or {}
            dets = pr.get("details") or {}
            at_site, phone_hit, phone_listings, elsewhere_listings = [], None, [], []
            row_phone = digits10(card.get("phone"))
            for pid, sp in (pr.get("search_places") or {}).items():
                full = {**sp, **({k: v for k, v in dets.get(pid, {}).items() if k != "error"})}
                full["_at_site"] = place_matches_site(full, card)
                street, suite, pzip = place_site(full)
                full.update(_street=street, _suite=suite, _zip=pzip, _site_key=_addr_key(street, pzip) if street else None)
                full["_rows_here"] = [r for r in rows_site.get(full["_site_key"], []) if r["cid"] != t["cid"]] \
                    if full["_site_key"] and not full["_at_site"] else []
                if full["_at_site"]:
                    at_site.append(full)
                elif full.get("businessStatus") == "OPERATIONAL":
                    elsewhere_listings.append(full)
                if row_phone and digits10(full.get("nationalPhoneNumber")) == row_phone:
                    phone_listings.append(full)
            if pr.get("queries") and pr["queries"][0]["kind"] == "phone" and pr["queries"][0]["place_ids"]:
                pid = pr["queries"][0]["place_ids"][0]
                phone_hit = next((x for x in at_site + phone_listings if x["id"] == pid), None) or \
                    {**(pr.get("search_places") or {}).get(pid, {}), "_at_site": False}
            other_rows_site = [r for r in rows_site.get(key, []) if r["cid"] != t["cid"]
                               and _dir_ok(_addr_dir(r["address"]), row_dir)] if key else []
            office_phones = {digits10(x.get("nationalPhoneNumber")) for x in at_site} - {None, row_phone}
            rows_on_office_phone = [r for ph in office_phones for r in rows_phone.get(ph, []) if r["cid"] != t["cid"]]
            iema_phone_elsewhere = [f for f in iema_by_phone.get(row_phone, []) if f["site_key"] != key] if row_phone else []
            hosts = candidate_hosts(card, checks_by_row.get(t["cid"], []), pr)
            row_hosts = sorted({host_of(u) for u in [card.get("website")] +
                                [(e.get("observed") or {}).get("website") for e in checks_by_row.get(t["cid"], [])] if u})
            packet = {"cid": t["cid"], "role": t["role"], "base_entry_id": base.get("entry_id"),
                      "card": {k: card.get(k) for k in ("cid", "zip", "city", "name", "public_name", "address", "suite",
                                                        "phone", "website", "providers", "home_like", "status_notes",
                                                        "entity_classification", "flags")},
                      "base": {k: base.get(k) for k in ("decision", "reason", "signals", "note", "evidence", "leads",
                                                        "observed", "searches", "fetches")},
                      "iema_site": site_facs, "iema_dentist_elsewhere": elsewhere[:3],
                      "licenses": [license_summary(p, lic_by_name, card) for p in card.get("providers") or []],
                      "places": {"probed": bool(pr), "at_site": at_site, "phone_hit": phone_hit,
                                 "phone_listings": phone_listings,
                                 "elsewhere_listings": [x for x in elsewhere_listings if x not in phone_listings][:12]},
                      "iema_phone_elsewhere": iema_phone_elsewhere[:3], "other_rows_site": other_rows_site[:8],
                      "rows_on_office_phone": rows_on_office_phone[:5],
                      "browser": [browser[h] for h in hosts if h in browser] +
                                 [browser[u] for u in candidate_pages(card, checks_by_row.get(t["cid"], []))
                                  if u in browser],
                      "row_hosts": row_hosts,
                      "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            packet["eval"] = rules.evaluate(packet)
            fh.write(json.dumps(packet) + "\n")
            role = t["role"]
            report[role]["n"] += 1
            report[role]["places_probed"] += bool(pr)
            for rid in packet["eval"]["fired"]:
                report[role]["fired:" + rid] += 1
            prop = packet["eval"]["proposal"]
            report[role]["proposal:" + (prop["rule_id"] if prop else "none")] += 1
            report[role]["dec:" + ((prop["decision"] + (":" + prop["reason"] if prop.get("reason") else "")
                                    + "/" + prop["confidence"]) if prop else "none")] += 1
    rule_ids = [r for r, _ in rules.RULES]
    roles = sorted(report)
    print(f"packets: {sum(report[r]['n'] for r in roles)} -> {dest}\n")
    print("rule fire counts by role (each rule evaluated independently; rows):")
    print(f"{'rule':12}" + "".join(f"{r[:28]:>30}" for r in roles))
    print(f"{'(rows)':12}" + "".join(f"{report[r]['n']:>30}" for r in roles))
    print(f"{'(places)':12}" + "".join(f"{report[r]['places_probed']:>30}" for r in roles))
    for rid in rule_ids:
        print(f"{rid:12}" + "".join(f"{report[r]['fired:' + rid]:>22} ({report[r]['fired:' + rid] / max(report[r]['n'], 1):5.1%})"
                                    for r in roles))
    print("\nproposals (priority order) for unresolved rows:")
    u = report.get("unresolved", {})
    for k, v in sorted(((k, v) for k, v in u.items() if k.startswith("proposal:")), key=lambda kv: -kv[1]):
        print(f"  {k[9:]:12} {v:5}  {v / max(u.get('n', 1), 1):5.1%}")
    print("\nproposal decision x confidence, by role (rows):")
    for r in roles:
        print(f"  {r:40} " + " · ".join(f"{k[4:]} {v}" for k, v in sorted(report[r].items()) if k.startswith("dec:")))
    return 0


REMOVE_ORDER = ["PL-CLOSED", "MOVED-PH", "LIC-CLOSED", "HOME-R"]


def cmd_publish_records(args):
    """Write `office_census_rapid.py record` input for the proposals v2_rules.publish_tier allows,
    for unresolved rows whose latest check is still the one the packet was built on. Opens go
    first; removals follow in evidence-strength order and are capped at the number of opens, so the
    session stays within the store's 50% session removal brake (never bypassed: the rest wait for a
    later session). VALID_CORRECTED waits too: its corrected values come from Places content."""
    import hashlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import office_census_v2_rules as rules
    latest = {}
    for e in read_jsonl(OC / "rapid" / "checks.jsonl"):
        if e.get("type") == "rapid_check" and e.get("outcome") != "held":
            latest[e["candidate_id"]] = e
    opens, removals, skipped = [], [], {}
    for pk in read_jsonl(OUT / "packets.jsonl"):
        if pk["role"] != "unresolved":
            continue
        ev = rules.evaluate(pk)
        ok, why = rules.publish_tier(pk, ev)
        pr = ev["proposal"]
        if ok and pr["decision"] == "VALID_CORRECTED":
            ok, why = False, "VALID_CORRECTED waits (values from Places content)"
        cur = latest.get(pk["cid"]) or {}
        if ok and cur.get("entry_id") != pk.get("base_entry_id"):
            ok, why = False, "the row was re-checked after the packet was built"
        if not ok:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        packet_id = "v2p-" + hashlib.sha256(json.dumps(pk, sort_keys=True).encode()).hexdigest()[:12]
        base = f"{cur.get('decision')}" + (f"/{cur['reason']}" if cur.get("reason") else "")
        note = (f"v2 {pr['rule_id']} ({ev['rules_version']}), packet {packet_id}; supersedes v1 {base}. "
                + (pr.get("note") or ""))[:400]
        rec = {"candidate_id": pk["cid"], "decision": pr["decision"], "gp_scope": pr.get("gp_scope", "gp"),
               "evidence": pr["evidence"][:4], "ties_by": pr.get("ties_by") or [], "note": note.strip(),
               "searches": 0, "fetches": 0, "supersede": True, "rule_id": pr["rule_id"], "packet_id": packet_id,
               "rules_version": ev["rules_version"]}
        if pr.get("reason"):
            rec["reason"] = pr["reason"]
        if pr.get("signals"):
            rec["signals"] = pr["signals"]
        if pr.get("duplicate_of"):
            rec["duplicate_of"] = pr["duplicate_of"]
        (opens if pr["decision"] in ("VALID", "VALID_CORRECTED") else removals).append(rec)
    removals.sort(key=lambda r: (REMOVE_ORDER.index(r["rule_id"]), r["candidate_id"]))
    cap = len(opens) if args.max_removals is None else min(len(opens), args.max_removals)
    held = removals[cap:]
    removals = removals[:cap]
    out = pathlib.Path(args.out)
    with out.open("w") as fh:
        for r in opens + removals:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    with (out.parent / (out.stem + "_waiting_for_brake.jsonl")).open("w") as fh:
        for r in held:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    by = {}
    for r in opens + removals:
        k = f"{r['rule_id']} {r['decision']}" + (f"/{r['reason']}" if r.get("reason") else "")
        by[k] = by.get(k, 0) + 1
    print(f"publish records: {len(opens)} open + {len(removals)} removals -> {out}")
    print(f"  waiting for the removal brake (next session with opens): {len(held)}")
    for k, v in sorted(by.items()):
        print(f"  {k}: {v}")
    print(f"  not published: {skipped}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("iema-profiles", help="fetch IEMA facility profiles for watched-IL dental facilities")
    p.add_argument("--limit", type=int)
    p.add_argument("--max-seconds", type=int, help="stop cleanly after this many seconds (rerun resumes)")
    p.set_defaults(fn=cmd_iema_profiles)
    p = sub.add_parser("targets", help="freeze the probe target set (unresolved rows + controls)")
    p.add_argument("--valid", type=int, default=150)
    p.add_argument("--valid-corrected", type=int, default=100)
    p.add_argument("--unchecked", action="store_true", help="also include rows not yet checked")
    p.set_defaults(fn=cmd_targets)
    p = sub.add_parser("places", help="Google Places probe for the frozen targets (spend-capped)")
    p.add_argument("--cap", type=float, default=0.0,
                   help="estimated USD allowed beyond Google's free monthly allotments (default 0 = free tier only)")
    p.add_argument("--roles", help="comma list: unresolved,control_open,control_not_open,unchecked")
    p.add_argument("--skip-free-resolved", action="store_true",
                   help="no Details lookup for unresolved rows packets.jsonl already settles from free evidence")
    p.add_argument("--limit", type=int)
    p.add_argument("--max-seconds", type=int, help="stop cleanly after this many seconds (rerun resumes)")
    p.set_defaults(fn=cmd_places)
    p = sub.add_parser("places-reviews", help="review dates for the listing that decides each row (free tier)")
    p.add_argument("--cap", type=float, default=0.0)
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_places_reviews)
    p = sub.add_parser("places-cost", help="Places calls this month by SKU vs the free allotments")
    p.add_argument("--cap", type=float, default=0.0)
    p.set_defaults(fn=cmd_places_cost)
    p = sub.add_parser("places-purge", help="drop cached Places records older than 30 days")
    p.set_defaults(fn=cmd_places_purge)
    p = sub.add_parser("packets", help="assemble evidence packets, run the rule engine, print calibration")
    p.set_defaults(fn=cmd_packets)
    p = sub.add_parser("publish-records", help="record input for the proposals publish_tier allows")
    p.add_argument("--out", default=str(OUT / "publish_records.jsonl"))
    p.add_argument("--max-removals", type=int)
    p.set_defaults(fn=cmd_publish_records)
    p = sub.add_parser("browser", help="open candidate office websites in headless Chrome")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--limit", type=int)
    p.add_argument("--max-seconds", type=int, help="stop cleanly after this many seconds (rerun resumes)")
    p.set_defaults(fn=cmd_browser)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
