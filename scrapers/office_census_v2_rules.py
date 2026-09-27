#!/usr/bin/env python3
"""Office census v2 rule engine: evidence packet -> proposed decision. Pure functions, no I/O.

Plan: data/office_census/V2_PLAN_2026-09-27.md (policies P1-P5). A packet (built by
`office_census_v2_probes.py packets`) holds one rapid row's card, its latest check, and what the
probes found: IEMA X-ray facilities at the site / on the row phone, IDFPR license status of each
row dentist, Google Places listings at the site / on the row phone, real-browser reads of candidate
office websites, and other directory rows at the same site / on the same phones.

Identity model (review 2026-09-27). Every piece of current evidence at the row's site is tied to
the row either by IDENTITY (the row's name or one of its dentists) or only by the PLACE (the row's
phone line or website on file). A phone line and a website domain stay with the office when a
practice is sold or a successor takes over the suite, so a place-only tie proves that *an* office
is open at the row's site, not that the row's business is. Under P1 (the row is the place) that
office becomes the row: VALID_CORRECTED with its name (signal successor_practice or rebranded),
or NOT_CURRENT_GP duplicate when that office already has its own directory row.

`evaluate(packet)` returns every rule's verdict (so each rule is calibrated on its own against
the control rows) plus one proposal chosen in priority order, a confidence tier ("auto": no
negative signal or conflict; "review": an agent must look) and the missing facts. Rule ids go
into the recorded check so a rule class can be audited or superseded later.

Open rules (a current GP office at the site):
  FP-SITE    the office's own website (read in a real browser) gives the row's street address with
             its city or ZIP, not as narrative ("moved from ..."), on a page without closure language
  PL-RECENT  Google listing at the site, OPERATIONAL, tied, a review dated within 365 days (P2b)
  PL-IEMA    Google listing at the site, OPERATIONAL, tied + an IEMA Open facility at the site with
             active fixed X-ray units, tied, and the same office as the listing (P2c)
  IEMA-LIC   IEMA Open facility at the site tied by phone AND by name/administrator + an active
             IDFPR license for a row dentist + no negative signal on the base check
  Each proposes VALID (identity tie, same phone), VALID_CORRECTED (identity tie with another phone,
  or a place-only tie: P1 successor/rebrand), or NOT_CURRENT_GP duplicate (P1 exception).
Not-current rules:
  PL-CLOSED  Google listing CLOSED_PERMANENTLY tied to the row (identity or phone), and nothing
             current at the site                                    -> closed
  MOVED-PH   the row phone's own Google listing is an operating dental office at another address
             with current evidence, and nothing at the row's site answers on the row's phone
             -> moved (other ZIP), duplicate (another row's office), or VALID_CORRECTED address
  LIC-CLOSED every row dentist's IDFPR license non-active + nothing dental at the site (no IEMA
             facility, no Google dental listing, no office website)   -> closed (P3)
  SUCCESSOR  nothing at the site tied to the row, and exactly one different GP office operates at
             the site with current evidence                -> VALID_CORRECTED / duplicate (P1)
  HOME-R     residential signal + nothing dental at the site + a row dentist practicing elsewhere
             -> home_or_registration (P3)
  SPEC-L     every row dentist holds an active IDFPR specialist license and the site listing is a
             specialist office                                -> specialist_only (P3)
"""
import datetime
import re

RULES_VERSION = "v2-rules-2026-09-27.3"
NONACTIVE = {"NOT RENEWED", "INACTIVE", "DECEASED", "EXPIRED", "CANCELLED", "REVOKED", "SUSPENDED", "RELINQUISH",
             "VOLUNTARY SURRENDER", "PERMANENT INACTIVE", "REFUSE TO RENEW", "INOPERATIVE", "TERMINATED"}
NEG_SIGNALS = {"real_estate_listing", "home_address", "website_dead", "owner_deceased", "owner_retired",
               "practice_sold", "successor_practice", "phone_belongs_elsewhere", "website_wrong_business"}
DENTAL_TYPES = {"dentist", "dental_clinic", "orthodontist", "oral_surgeon", "endodontist", "periodontist",
                "pediatric_dentist", "prosthodontist", "cosmetic_dentist", "dental_hygienist"}
SPECIALIST_TYPES = {"orthodontist", "oral_surgeon", "endodontist", "periodontist", "pediatric_dentist",
                    "prosthodontist"}
SPECIALIST_NAME_RE = re.compile(r"orthodont|periodont|endodont|oral (?:and maxillofacial )?surg|maxillofacial|"
                                r"pediatric dent|children'?s dent|pedodont|prosthodont|\bbraces\b|\bkids\b", re.I)
GENERIC_NAME_TOKENS = {"dental", "dentistry", "dentist", "dds", "dmd", "pc", "ltd", "llc", "inc", "sc", "the", "of",
                       "and", "family", "care", "center", "centre", "ctr", "group", "associates", "assoc", "office",
                       "clinic", "smile", "smiles", "dr", "drs", "ms", "general", "cosmetic", "implant", "implants",
                       "studio", "professional", "professionals", "practice", "services", "service", "health",
                       "oral", "arts", "art", "new", "modern", "advanced", "complete", "total", "comprehensive",
                       "gentle", "quality", "premier", "elite", "pllc", "llp", "corp", "company", "co"}
ABBREV = {"ctr": "center", "centre": "center", "assoc": "associates", "assocs": "associates", "dent": "dental",
          "grp": "group", "fam": "family", "svcs": "services"}
REVIEW_WINDOW_DAYS = 365
MOVED_STATUS_RE = re.compile(r"moved|relocat|formerly|previous(?:ly)? located|new (?:location|address)|"
                             r"permanently closed|has closed|closed (?:its|our) doors|retired", re.I)


def digits10(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else None


def fmt_phone(d):
    d = digits10(d)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if d else None


def name_tokens(s):
    return {t for t in re.findall(r"[a-z]+", str(s or "").lower().replace(".", ""))
            if len(t) > 2 and t not in GENERIC_NAME_TOKENS}


def name_norm(s):
    toks = re.findall(r"[a-z0-9]+", str(s or "").lower().replace(".", ""))
    return " ".join(ABBREV.get(t, t) for t in toks
                    if t not in {"dds", "dmd", "pc", "ltd", "llc", "inc", "sc", "the", "pllc", "ms", "dr"})


def display_name(pl):
    dn = pl.get("displayName")
    return (dn.get("text") if isinstance(dn, dict) else dn) or ""


def clean_business_name(name):
    """A Google display name without the SEO tail: 'Todo Dental (General Dentistry, ...)' ->
    'Todo Dental'; 'Batavia Family Dental: Korpan Kenneth A DDS' -> 'Batavia Family Dental'."""
    s = str(name or "").strip()
    for sep in (" (", ": ", " | ", " - ", " – ", " — "):
        head = s.split(sep)[0].strip()
        if len(head) >= 4 and head != s:
            s = head
    return s


def row_dentists(providers):
    """[(first, last)] from card providers like 'Paul Engen' or 'Susan Torma (endo)'."""
    out = []
    for p in providers or []:
        p = re.sub(r"\(.*?\)", "", str(p))
        parts = [t for t in re.findall(r"[A-Za-z][A-Za-z'\-]*", p)
                 if t.upper() not in {"DDS", "DMD", "JR", "SR", "II", "III", "MS", "PC", "DR"}]
        if len(parts) >= 2:
            out.append((parts[0].lower(), parts[-1].lower()))
    return out


def provider_lastnames(providers):
    return {last for _, last in row_dentists(providers)}


def dentist_in(text, dentists):
    """A row dentist's last name (3+ letters, whole word) appears in `text`."""
    low = str(text or "").lower()
    return any(len(last) >= 3 and re.search(r"\b" + re.escape(last) + r"\b", low) for _, last in dentists)


def house_of(address):
    m = re.match(r"\s*(\d+[A-Za-z]?\d*)", str(address or ""))
    return m.group(1).upper() if m else None


STREET_STOP = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south", "east", "west", "st", "ave", "av", "rd",
               "dr", "ln", "ct", "blvd", "pl", "ste", "suite", "unit", "hwy", "pkwy", "way", "street", "avenue", "road",
               "drive", "lane", "court", "boulevard", "place", "parkway", "highway", "cir", "circle", "ter", "trl",
               "plz", "plaza", "sq", "fl", "floor", "apt", "rm", "room", "bldg", "il", "illinois", "usa", "us"}


def street_tokens(address):
    toks = re.findall(r"[a-z0-9]+", str(address or "").lower())[1:]
    return {t for t in toks if t not in STREET_STOP and not re.fullmatch(r"\d{5}", t)}


def snippet_matches_site(snippet, row, pre=""):
    """A page's address-like snippet IS the row's address: house number + a street word + the row's
    ZIP or city, no other Illinois ZIP in the snippet, and no move/closure words just before it
    ("moved from 1642 W. Belmont Ave", "formerly located at ...")."""
    house = house_of(row.get("address"))
    if not house or not re.search(r"(?<![0-9])" + re.escape(house) + r"(?![0-9])", snippet, re.I):
        return False
    words = street_tokens(row.get("address"))
    if not words or not any(re.search(r"\b" + re.escape(w) + r"\b", snippet, re.I) for w in words):
        return False
    zips = set(re.findall(r"(?<![0-9])(6\d{4})(?![0-9])", snippet))
    row_zip = str(row.get("zip") or "")[:5]
    if zips and row_zip not in zips:
        return False
    city = str(row.get("city") or "").strip()
    if not (row_zip in zips or (city and re.search(r"\b" + re.escape(city) + r"\b", snippet, re.I))):
        return False
    return not MOVED_STATUS_RE.search(pre or "")


def _days_since(iso, today):
    try:
        return (today - datetime.date.fromisoformat(str(iso)[:10])).days
    except (TypeError, ValueError):
        return None


def is_dental(pl):
    return bool(set(pl.get("types") or []) & DENTAL_TYPES) or pl.get("primaryType") in DENTAL_TYPES


PRACTITIONER_RE = re.compile(r"^\s*dr\.?\s|,?\s*(?:d\.?\s?d\.?\s?s|d\.?\s?m\.?\s?d)\.?\s*$", re.I)


def is_practitioner(pl, dentists=()):
    """Google's individual-dentist listing ('Dr. Jane Doe', 'Jane Doe, DDS', or just a row dentist's
    name). These outlive the office they were attached to."""
    n = display_name(pl)
    if PRACTITIONER_RE.search(n):
        return True
    words = re.findall(r"[a-z]+", n.lower())
    return any(first in words and last in words and len(words) <= 4 for first, last in dentists)


def is_specialist_place(pl):
    return pl.get("primaryType") in SPECIALIST_TYPES or bool(SPECIALIST_NAME_RE.search(display_name(pl)))


# ---- facts --------------------------------------------------------------------------------------
def facts(p, today=None):
    """Derived facts from a packet; every rule reads only these."""
    today = today or datetime.date.today()
    card, base = p["card"], p.get("base") or {}
    row_phone = digits10(card.get("phone"))
    row_names = name_tokens(card.get("public_name")) | name_tokens(card.get("name"))
    row_norms = {n for n in (name_norm(card.get("public_name")), name_norm(card.get("name"))) if n}
    dentists = row_dentists(card.get("providers"))
    f = {"row_phone": row_phone, "row_names": row_names, "dentists": dentists, "today": today}
    base_signals = set(base.get("signals") or [])
    f["neg_signals"] = sorted(base_signals & NEG_SIGNALS)
    f["neg"] = bool(f["neg_signals"]) or bool(card.get("status_notes"))

    def ties(phone=None, name=None, people=()):
        t = []
        if row_phone and digits10(phone) == row_phone:
            t.append("phone")
        if name and ((row_names & name_tokens(name)) or (row_norms and name_norm(name) in row_norms)):
            t.append("name")
        if dentists and any(dentist_in(x, dentists) for x in [name, *people] if x):
            t.append("dentist")
        return t
    f["ties"] = ties

    # IEMA
    site_all = p.get("iema_site") or []
    f["iema_site_any"] = bool(site_all)
    f["iema_site_open"] = [x for x in site_all if x.get("status") in (None, "Open")]
    f["iema_site_active"] = [x for x in f["iema_site_open"]
                             if (x.get("active_units") or 0) > 0 and not x.get("mobile_only")]
    tied = [(x, ties(x.get("phone"), x.get("name"), [x.get("administrator")])) for x in f["iema_site_active"]]
    f["iema_tied"] = [(x, t) for x, t in tied if t]
    f["iema_mobile_only_site"] = bool(site_all) and all(x.get("mobile_only") for x in site_all)
    f["iema_dentist_elsewhere"] = [x for x in p.get("iema_dentist_elsewhere") or [] if x.get("status") in (None, "Open")]
    f["iema_phone_elsewhere"] = [x for x in p.get("iema_phone_elsewhere") or [] if x.get("status") in (None, "Open")
                                 and (x.get("active_units") or 0) > 0]

    # IDFPR
    lic = p.get("licenses") or []
    f["lic_matched"] = [l for l in lic if l.get("status")]
    f["lic_any_active"] = any(l.get("status") == "ACTIVE" for l in lic)
    f["lic_all_nonactive"] = bool(lic) and all(l.get("status") and l["status"] in NONACTIVE for l in lic)
    f["lic_all_specialist"] = bool(lic) and all(l.get("specialist_active") for l in lic)

    # Places
    places = p.get("places") or {}
    site = [pl for pl in places.get("at_site") or [] if is_dental(pl)]

    def review_days(pl):
        ds = [_days_since(r.get("publishTime"), today) for r in pl.get("reviews") or []]
        ds = [d for d in ds if d is not None]
        return min(ds) if ds else None

    def recent_status_words(pl):
        return any(r.get("status_words") and (_days_since(r.get("publishTime"), today) or 9999) <= REVIEW_WINDOW_DAYS
                   for r in pl.get("reviews") or [])
    f["review_days"] = review_days
    f["pl_site_dental"] = site
    f["pl_site_operating"] = [pl for pl in site if pl.get("businessStatus") == "OPERATIONAL"]
    def pl_ties(pl):
        t = ties(pl.get("nationalPhoneNumber"), display_name(pl))
        if is_practitioner(pl, dentists) and "phone" not in t:
            return []  # a dentist's personal listing with another phone: not evidence the row's office is here
        return t
    f["pl_site_ties"] = [(pl, pl_ties(pl)) for pl in f["pl_site_operating"]]
    f["pl_site_closed"] = [pl for pl in site if pl.get("businessStatus") == "CLOSED_PERMANENTLY"]
    f["pl_review_status_words"] = any(recent_status_words(pl) for pl in f["pl_site_operating"])
    phone_listings = [pl for pl in places.get("phone_listings") or [] if is_dental(pl)]
    f["pl_phone_elsewhere"] = [pl for pl in phone_listings if not pl.get("_at_site")
                               and pl.get("businessStatus") == "OPERATIONAL"]
    closed = f["pl_site_closed"] + [pl for pl in phone_listings if pl.get("businessStatus") == "CLOSED_PERMANENTLY"
                                    and pl.get("id") not in {c.get("id") for c in f["pl_site_closed"]}]
    f["pl_closed_tied"] = [(pl, t) for pl in closed for t in [ties(pl.get("nationalPhoneNumber"), display_name(pl))]
                           if t]
    # a row dentist's current listing at another address: first AND last name in the listing name
    # (a practitioner or practice listing), operating, with a review within the window
    f["pl_dentist_elsewhere"] = [pl for pl in places.get("elsewhere_listings") or [] if is_dental(pl)
                                 and any(first in display_name(pl).lower() and re.search(r"\b" + re.escape(last) + r"\b",
                                                                                          display_name(pl).lower())
                                         for first, last in dentists if len(first) >= 3 and len(last) >= 3)
                                 and (review_days(pl) or 9999) <= REVIEW_WINDOW_DAYS]

    # Browser: first-party pages naming the row's address
    fp, fp_neg = [], []
    for b in p.get("browser") or []:
        if b.get("class") != "live_dental":
            continue
        for page in b.get("pages") or []:
            ctx = page.get("address_context") or [{"text": s, "pre": ""} for s in page.get("address_snippets") or []]
            hits = [c["text"] for c in ctx if snippet_matches_site(c["text"], card, c.get("pre"))]
            if not hits:
                continue
            item = {"host": b["host"], "url": page["url"], "quote": hits[0][:240], "phones": page.get("phones") or [],
                    "dentists": page.get("dentists") or [], "title": b.get("title"),
                    "gp_terms": page.get("gp_terms") or [], "status_text": page.get("status_text") or [],
                    "place_ties": [], "identity_ties": []}
            if row_phone and row_phone in item["phones"]:
                item["place_ties"].append("phone")
            if b.get("host") in (p.get("row_hosts") or []):
                item["place_ties"].append("website")
            item["identity_ties"] = [t for t in ties(None, b.get("title"), item["dentists"]) if t != "phone"]
            (fp_neg if any(MOVED_STATUS_RE.search(s) for s in item["status_text"]) else fp).append(item)
    f["fp_site"] = fp
    f["fp_site_neg"] = fp_neg
    f["dead_sites"] = [b["host"] for b in p.get("browser") or [] if b.get("class") in
                       ("dns_dead", "parked_or_for_sale", "hijacked_spam")]
    f["residential"] = bool(card.get("home_like")) or "home_address" in base_signals
    f["other_rows_site"] = p.get("other_rows_site") or []
    f["other_offices_signal"] = "other_offices_in_building" in base_signals
    return f


# ---- helpers ------------------------------------------------------------------------------------
def _ev(kind, url, quote):
    return {"kind": kind, "url": url or "https://www.google.com/maps", "quote": str(quote or "")[:240]}


def _today(f):
    return f["today"].isoformat()


def _pl_ev(pl, conclusion):
    return _ev("places_listing", pl.get("googleMapsUri"), conclusion)


def _iema_ev(fac):
    return _ev("iema_registry", fac.get("url"),
               f"IEMA X-ray registration: {fac.get('name')} · Status: {fac.get('status') or 'Open'} · "
               f"{fac.get('active_units')} active unit(s) · {fac.get('physical_address')} · {fac.get('phone')} · "
               f"administrator {fac.get('administrator')}")


def _pl_current(f, pl):
    d = f["review_days"](pl)
    return d is not None and d <= REVIEW_WINDOW_DAYS, d


def _duplicate_row(f, p, office):
    """Another directory row at this site that is this office: same phone or a shared name word,
    by its app data or by its latest check's corrected values. Rows elsewhere with the same phone
    are not duplicates (an older office of the same practice is its own row's question)."""
    ph = digits10(office.get("phone"))
    words = name_tokens(office.get("name"))
    for r in f["other_rows_site"]:
        obs = r.get("observed") or {}
        phones = {digits10(r.get("phone")), digits10(obs.get("phone"))} - {None}
        names = name_tokens(r.get("name")) | name_tokens(obs.get("name"))
        if (ph and ph in phones) or (words & names):
            return r
    return None


def _open_row_at_site(f):
    return [r for r in f["other_rows_site"] if r.get("decision") in ("VALID", "VALID_CORRECTED")]


def _open_proposal(f, p, identity, place, office, evidence):
    """Shape an open-rule result. identity: ties to the row's own business (name/dentist);
    place: ties to the row's phone/website only. office: {name, phone, website, dentists, types}."""
    card = p["card"]
    if SPECIALIST_NAME_RE.search(str(office.get("name") or "")) or set(office.get("types") or []) & SPECIALIST_TYPES:
        return None  # a specialist-only occupant is not a VALID GP office; SPEC-L or an agent decides
    out = {"ties_by": sorted(set(identity) | set(place)), "evidence": evidence[:4], "gp_scope": "gp", "office": office}
    if identity:
        observed = {}
        if office.get("phone") and f["row_phone"] and digits10(office["phone"]) != f["row_phone"] \
                and "phone" not in place:
            observed["phone"] = fmt_phone(office["phone"])
        name = clean_business_name(office.get("name"))
        if "name" not in identity and name and not name_tokens(name) & f["row_names"] and \
                name_norm(name) != name_norm(card.get("name")) and not PRACTITIONER_RE.search(name) and \
                not is_practitioner({"displayName": {"text": name}}, f["dentists"]):
            observed["name"] = name  # tied by a row dentist only: the office now goes by another name
        out.update(decision="VALID_CORRECTED" if observed else "VALID", observed=observed)
        return out
    if not office.get("current_for_successor"):
        return None  # a place-only tie needs a recent review or the office's own website (stale listings)
    # place-only tie (P1): the office at the site becomes the row, unless it already has a row
    dup = _duplicate_row(f, p, office)
    if dup:
        out.update(decision="NOT_CURRENT_GP", reason="duplicate", duplicate_of=dup["cid"],
                   ties_by=sorted(set(place) | {"address"}), signals=["successor_practice"],
                   note=f"P1: {clean_business_name(office.get('name'))} occupies this site and already has its "
                        f"own row {dup['cid']}.")
        return out
    ours = [x for x in office.get("dentists") or [] if x]
    signal = "rebranded" if any(dentist_in(x, f["dentists"]) for x in ours) else (
        "successor_practice" if (ours or f["lic_all_nonactive"]) else "rebranded")
    name = clean_business_name(office.get("name"))
    observed = {}
    if name and name_norm(name) != name_norm(card.get("name")):
        observed["name"] = name
    if office.get("phone") and f["row_phone"] and digits10(office["phone"]) != f["row_phone"]:
        observed["phone"] = fmt_phone(office["phone"])
    if office.get("website") and not any(h and h in str(office["website"]).lower() for h in p.get("row_hosts") or []):
        observed["website"] = office["website"]
    if not observed:
        return None
    out.update(decision="VALID_CORRECTED", observed=observed, signals=[signal],
               note=f"P1: the office now at this site is {name}; the row's name is not tied to it.")
    if _open_row_at_site(f):
        out["review_reason"] = "another row at this site is already open: it may be this office"
    elif _multi_tenant(f, office):
        out["review_reason"] = "several dental offices at this address: an agent confirms which suite is the row's"
    return out


def _multi_tenant(f, office):
    """More than one dental business at the site besides the office itself (IEMA facilities, Google
    listings not tied to the row, other directory rows), or the base check saw other offices."""
    ph, words = digits10(office.get("phone")), name_tokens(office.get("name"))

    def same(phone, name):
        return (ph and digits10(phone) == ph) or bool(words & name_tokens(name))
    others = [x for x in f["iema_site_open"] if not same(x.get("phone"), x.get("name"))
              and not f["ties"](x.get("phone"), x.get("name"), [x.get("administrator")])]
    others += [pl for pl in f["pl_site_dental"] if not same(pl.get("nationalPhoneNumber"), display_name(pl))
               and not f["ties"](pl.get("nationalPhoneNumber"), display_name(pl))
               and not is_practitioner(pl, f["dentists"])]
    return bool(others) or bool(f["other_rows_site"]) or f["other_offices_signal"]


def _place_office(pl, fac=None, page=None, current=False):
    return {"name": display_name(pl) or (fac or {}).get("name"), "phone": pl.get("nationalPhoneNumber"),
            "current_for_successor": current,
            "website": pl.get("websiteUri"), "place_id": pl.get("id"), "maps": pl.get("googleMapsUri"),
            "types": [pl.get("primaryType")] if pl.get("primaryType") else [],
            "dentists": [x for x in [(fac or {}).get("administrator")] if x] + ((page or {}).get("dentists") or [])}


def _site_identity(f):
    """Current evidence at the site tied to the row's own name or dentist."""
    return bool([1 for _, t in f["pl_site_ties"] if {"name", "dentist"} & set(t)] or
                [1 for _, t in f["iema_tied"] if {"name", "dentist"} & set(t)] or
                [1 for x in f["fp_site"] if x["identity_ties"]])


def _site_phone(f):
    return bool([1 for _, t in f["pl_site_ties"] if "phone" in t] or [1 for _, t in f["iema_tied"] if "phone" in t]
                or [1 for x in f["fp_site"] if "phone" in x["place_ties"]])


def _conflicted(f):
    """The row phone's own Google listing operates at another address while nothing at the site
    carries the row's name or dentist: a move the registries have not caught up with, or a stale
    listing. With the row's identity current at the site, the phone elsewhere is a sister office
    or a stale number, and the open rules still decide (at review confidence)."""
    return bool(f["pl_phone_elsewhere"]) and not _site_identity(f)


# ---- open rules ---------------------------------------------------------------------------------
def rule_fp_site(f, p):
    items = [x for x in f["fp_site"] if x["identity_ties"] or x["place_ties"]]
    if not items or _conflicted(f):
        return None
    best = sorted(items, key=lambda x: (-len(x["identity_ties"]), -len(x["place_ties"])))[0]
    site_pl = next((pl for pl, _ in f["pl_site_ties"] if digits10(pl.get("nationalPhoneNumber")) in best["phones"]), None)
    title = str(best.get("title") or "")
    title_name = re.split(r"\s[|\-–—]\s", title)[-1].strip() if title else None
    office = {"name": display_name(site_pl) if site_pl else title_name,
              "phone": fmt_phone(f["row_phone"]) if "phone" in best["place_ties"] else
              (site_pl or {}).get("nationalPhoneNumber"),
              "website": "https://" + best["host"] + "/", "dentists": best["dentists"], "types": [],
              "current_for_successor": True}
    if not best["identity_ties"] and not (site_pl or best["dentists"]):
        return None  # place-only tie and no idea who the office is: an agent decides
    return _open_proposal(f, p, best["identity_ties"], best["place_ties"], office,
                          [_ev("first_party_site", best["url"], best["quote"])])


def rule_pl_recent(f, p):
    if _conflicted(f):
        return None
    for pl, t in f["pl_site_ties"]:
        current, days = _pl_current(f, pl)
        if not current or not t:
            continue
        ev = [_pl_ev(pl, f"Google business listing at this address ({'/'.join(t)} match) is shown as operating; "
                         f"a patient review is dated within {days} days (checked {_today(f)}).")]
        return _open_proposal(f, p, [x for x in t if x != "phone"], ["phone"] if "phone" in t else [],
                              _place_office(pl, current=True), ev)
    return None


def rule_pl_iema(f, p):
    if _conflicted(f):
        return None
    for pl, t in f["pl_site_ties"]:
        if not t:
            continue
        for fac, ft in f["iema_tied"]:
            same_office = digits10(fac.get("phone")) == digits10(pl.get("nationalPhoneNumber")) or \
                bool(name_tokens(fac.get("name")) & name_tokens(display_name(pl)))
            if not same_office:
                continue
            allt = set(t) | set(ft)
            ev = [_pl_ev(pl, f"Google business listing at this address ({'/'.join(t)} match) is shown as operating "
                             f"(checked {_today(f)})."), _iema_ev(fac)]
            return _open_proposal(f, p, sorted(allt - {"phone"}), ["phone"] if "phone" in allt else [],
                                  _place_office(pl, fac, current=_pl_current(f, pl)[0]), ev)
    return None


def rule_iema_lic(f, p):
    if f["neg"] or _conflicted(f) or not f["lic_any_active"]:
        return None
    for fac, t in f["iema_tied"]:
        if "phone" in t and ({"name", "dentist"} & set(t)):
            lic = next(l for l in f["lic_matched"] if l["status"] == "ACTIVE")
            ev = [_iema_ev(fac), _ev("license_registry", lic.get("url"),
                                     f"IDFPR: {lic.get('name')} · {lic.get('description')} · {lic['status']} · "
                                     f"expires {lic.get('expiration_date')}")]
            office = {"name": fac.get("name"), "phone": fac.get("phone"), "dentists": [fac.get("administrator")],
                      "types": []}
            return _open_proposal(f, p, sorted(set(t) - {"phone"}), ["phone"], office, ev)
    return None


# ---- not-current rules --------------------------------------------------------------------------
def rule_pl_closed(f, p):
    if not f["pl_closed_tied"] or f["pl_site_operating"] or f["fp_site"] or f["iema_tied"]:
        return None
    pl, t = f["pl_closed_tied"][0]
    return {"decision": "NOT_CURRENT_GP", "reason": "closed", "ties_by": t, "gp_scope": "gp",
            "evidence": [_pl_ev(pl, f"A Google business listing matching this row ({'/'.join(t)}) is marked "
                                    f"permanently closed; no operating dental listing at this address "
                                    f"(checked {_today(f)}).")]}


def rule_moved(f, p):
    if not f["pl_phone_elsewhere"] or not house_of(p["card"].get("address")):
        return None
    if _site_phone(f) or _site_identity(f):
        return None  # the row's phone or identity is still at its site: open rules or an agent decide
    for pl in f["pl_phone_elsewhere"]:
        if is_specialist_place(pl):
            continue
        current, days = _pl_current(f, pl)
        iema_there = [x for x in f["iema_phone_elsewhere"] if x.get("site_key") and x["site_key"] == pl.get("_site_key")]
        if not (current or iema_there):
            continue
        where = pl.get("formattedAddress")
        # the listing's own name also tied to the row (name/dentist): the practice itself moved; a
        # phone-only tie can be a number handed to a buyer or merger partner (publish_tier: review)
        ties = ["phone"] + [t for t in f["ties"](None, display_name(pl)) if t != "phone"]
        ev = [_pl_ev(pl, f"The row's phone belongs to an operating dental office ({'/'.join(ties)} match) listed "
                         f"at another address (Maps link), not this one"
                         + (f"; a review is dated within {days} days" if current else "")
                         + f" (checked {_today(f)}).")]
        if iema_there:
            ev.append(_iema_ev(iema_there[0]))
        other = [r for r in pl.get("_rows_here") or [] if r.get("cid") != p["cid"]]
        if other:  # runbook: "moved" covers a move into another row's office
            return {"decision": "NOT_CURRENT_GP", "reason": "moved", "ties_by": ties, "gp_scope": "gp",
                    "evidence": ev, "moved_to": where, "moved_into_row": other[0]["cid"],
                    "note": f"The practice now operates at the office of directory row {other[0]['cid']}."}
        if not pl.get("_zip") or pl["_zip"] == str(p["card"].get("zip"))[:5]:
            return None  # a move within the ZIP is VALID_CORRECTED with the office's own address: an agent
        return {"decision": "NOT_CURRENT_GP", "reason": "moved", "ties_by": ties, "gp_scope": "gp",
                "evidence": ev, "moved_to": where,
                "note": "The practice now operates at another address outside this ZIP (see the Maps link)."}
    return None


def _nothing_dental_at_site(f):
    return not f["iema_site_open"] and not f["pl_site_dental"] and not f["fp_site"] and not f["fp_site_neg"]


def rule_lic_closed(f, p):
    if not f["lic_all_nonactive"] or not _nothing_dental_at_site(f) or not (p.get("places") or {}).get("probed"):
        return None
    if f["pl_phone_elsewhere"] or f["iema_phone_elsewhere"]:
        return None  # the practice may have moved: MOVED-PH or an agent decides
    ev = [_ev("license_registry", l.get("url"),
              f"IDFPR: {l.get('name')} · {l.get('description')} · {l['status']} · expired {l.get('expiration_date')}")
          for l in f["lic_matched"][:2]]
    return {"decision": "NOT_CURRENT_GP", "reason": "closed", "ties_by": ["dentist"], "gp_scope": "gp", "evidence": ev,
            "note": "Every row dentist's Illinois license is non-active; no X-ray registration, Google dental listing "
                    "or office website at this address."}


def rule_successor(f, p):
    if [1 for _, t in f["pl_site_ties"] if t] or f["iema_tied"] or \
            [1 for x in f["fp_site"] if x["identity_ties"] or x["place_ties"]] or _conflicted(f):
        return None  # something at the site ties to the row (the open rules decide), or a move conflict
    current = []
    for pl in f["pl_site_operating"]:
        if is_specialist_place(pl) or is_practitioner(pl):
            continue
        ok, days = _pl_current(f, pl)
        fac = next((x for x in f["iema_site_active"] if digits10(x.get("phone")) == digits10(pl.get("nationalPhoneNumber"))
                    or name_tokens(x.get("name")) & name_tokens(display_name(pl))), None)
        if ok:
            current.append((pl, days, fac))
    if len(current) != 1:
        return None  # none, or several tenants and no tie to pick one (P4: an agent decides)
    pl, days, fac = current[0]
    ev = [_pl_ev(pl, "A different dental office's Google listing at this address is shown as operating"
                     + (f"; a review is dated within {days} days" if days is not None and days <= REVIEW_WINDOW_DAYS
                        else "") + f" (checked {_today(f)}).")]
    if fac:
        ev.append(_iema_ev(fac))
    res = _open_proposal(f, p, [], [], _place_office(pl, fac, current=True), ev)
    if res:
        res["ties_by"] = sorted(set(res["ties_by"]) | {"address"})
    return res


def rule_home(f, p):
    """Residential address form (a residential street type, no suite, one provider, no website: the
    card's home_like) or a mobile-only X-ray registration, and nothing dental at the site: no X-ray
    facility, no Google dental listing (open or closed), no office website, and the row phone is not a
    dental listing here. A row dentist practicing elsewhere is quoted when known."""
    residential = f["residential"] or f["iema_mobile_only_site"]
    if not residential or f["iema_site_active"] or f["pl_site_dental"] or f["fp_site"] or f["fp_site_neg"]:
        return None
    if [1 for pl in (p.get("places") or {}).get("phone_listings") or [] if pl.get("_at_site")]:
        return None
    ev = [_ev("iema_registry", "https://public.iema.state.il.us/RadHealthFacilitySearch/",
              f"No dental X-ray facility is registered with IEMA at {p['card'].get('address')}, "
              f"{p['card'].get('city')} (statewide registry, checked {_today(f)}); residential address form.")]
    elsewhere = f["iema_dentist_elsewhere"] or f["pl_dentist_elsewhere"] or f["pl_phone_elsewhere"]
    where = None
    if elsewhere:
        x = elsewhere[0]
        where = x.get("physical_address") or x.get("formattedAddress")
        ev.insert(0, _iema_ev(x) if x.get("physical_address") else
                  _pl_ev(x, f"A row dentist / the row's phone is listed at a dental office at another address "
                            f"(Maps link; checked {_today(f)})."))
    return {"decision": "NOT_CURRENT_GP", "reason": "home_or_registration",
            "ties_by": ["dentist", "address"] if elsewhere else ["address"], "gp_scope": "unknown", "evidence": ev,
            "practices_at": where}


def rule_moved_dentist(f, p):
    """Nothing dental at the site, and a row dentist currently practices at another address: the
    IEMA administrator of an Open facility elsewhere, or a current Google listing in the dentist's
    name elsewhere. Only when that address is another directory row's office or outside the ZIP
    (a move within the ZIP to an unlisted address is VALID_CORRECTED: an agent)."""
    if f["iema_site_any"] or f["pl_site_dental"] or f["fp_site"] or f["fp_site_neg"] or f["pl_phone_elsewhere"]:
        return None
    if f["residential"] or not f["dentists"] or len(f["dentists"]) > 2:
        return None  # home rows are HOME-R's; large groups move dentists around without moving offices
    row_zip = str(p["card"].get("zip") or "")[:5]
    for pl in f["pl_dentist_elsewhere"]:
        other = [r for r in pl.get("_rows_here") or [] if r.get("cid") != p["cid"]]
        if other or (pl.get("_zip") and pl["_zip"] != row_zip):
            where = pl.get("formattedAddress")
            return {"decision": "NOT_CURRENT_GP", "reason": "moved", "ties_by": ["dentist"], "gp_scope": "gp",
                    "evidence": [_pl_ev(pl, f"The row's dentist is listed at an operating dental office at another "
                                            f"address (Maps link); "
                                            f"a review is dated within {f['review_days'](pl)} days. No X-ray "
                                            f"registration or Google dental listing at this address (checked "
                                            f"{_today(f)}).")],
                    "moved_to": where, **({"moved_into_row": other[0]["cid"]} if other else {})}
    for x in f["iema_dentist_elsewhere"]:
        if (x.get("active_units") or 0) <= 0 or x.get("mobile_only"):
            continue
        z = str(x.get("site_key") or ("", ))[0] if isinstance(x.get("site_key"), (list, tuple)) else ""
        if z and z != row_zip:
            return {"decision": "NOT_CURRENT_GP", "reason": "moved", "ties_by": ["dentist"], "gp_scope": "gp",
                    "evidence": [_iema_ev(x)], "moved_to": x.get("physical_address"),
                    "note": "The row's dentist is the registered X-ray administrator at another office outside this "
                            "ZIP; no X-ray registration or Google dental listing at this address."}
    return None


def rule_spec(f, p):
    spec = [pl for pl in f["pl_site_operating"] if pl.get("primaryType") in SPECIALIST_TYPES]
    if f["lic_all_specialist"] and spec and len(spec) == len(f["pl_site_operating"]):
        pl = spec[0]
        return {"decision": "NOT_CURRENT_GP", "reason": "specialist_only", "ties_by": ["dentist"],
                "gp_scope": "specialist_only",
                "evidence": [_pl_ev(pl, f"The Google listing at this address is a specialist office "
                                        f"({pl.get('primaryType')}); every row dentist holds a specialist license.")]}
    return None


RULES = [("FP-SITE", rule_fp_site), ("PL-RECENT", rule_pl_recent), ("PL-IEMA", rule_pl_iema),
         ("IEMA-LIC", rule_iema_lic), ("PL-CLOSED", rule_pl_closed), ("LIC-CLOSED", rule_lic_closed),
         ("SUCCESSOR", rule_successor), ("MOVED-PH", rule_moved), ("MOVED-D", rule_moved_dentist),
         ("HOME-R", rule_home), ("SPEC-L", rule_spec)]
OPEN_RULES = {"FP-SITE", "PL-RECENT", "PL-IEMA", "IEMA-LIC", "SUCCESSOR"}
# Rules that settle a row from free evidence (no Places data needed).
FREE_RULES = {"FP-SITE", "IEMA-LIC"}
# spot check 2026-09-27: 2 of 4 MOVED-D samples matched a different dentist of the same name
REVIEW_ONLY_RULES = {"MOVED-D"}
PRIORITY = ["FP-SITE", "PL-RECENT", "PL-IEMA", "IEMA-LIC", "PL-CLOSED", "SPEC-L", "MOVED-PH", "HOME-R",
            "MOVED-D", "SUCCESSOR", "LIC-CLOSED"]


def evaluate(packet, today=None):
    f = facts(packet, today)
    fired = {}
    for rid, fn in RULES:
        r = fn(f, packet)
        if r:
            fired[rid] = r
    proposal = next(({"rule_id": rid, **fired[rid]} for rid in PRIORITY if rid in fired), None)
    conflicts = []
    kinds = {("open" if r["decision"] in ("VALID", "VALID_CORRECTED") else "not_current") for r in fired.values()}
    if len(kinds) > 1:
        conflicts.append("open and not-current rules both fired: " + ", ".join(sorted(fired)))
    if f["fp_site_neg"]:
        conflicts.append("an office website naming this address carries closure/move language")
    if f["pl_review_status_words"] and proposal and proposal["decision"] in ("VALID", "VALID_CORRECTED"):
        conflicts.append("a recent Google review mentions retirement/closure/new owner")
    if proposal and proposal.get("review_reason"):
        conflicts.append(proposal["review_reason"])
    if proposal and proposal["decision"] in ("VALID", "VALID_CORRECTED") and f["pl_phone_elsewhere"]:
        conflicts.append("the row's phone is also listed for an office at another address")
    if proposal and proposal["rule_id"] in REVIEW_ONLY_RULES:
        conflicts.append(f"{proposal['rule_id']} matches a dentist by name only (common names collide)")
    if proposal:
        review = bool(conflicts) or (f["neg"] and proposal["decision"] in ("VALID", "VALID_CORRECTED"))
        proposal["confidence"] = "review" if review else "auto"
    missing = []
    if not proposal:
        places = packet.get("places") or {}
        if not places.get("at_site") and not places.get("phone_listings"):
            missing.append("no Google listing found at the site or on the phone")
        if not f["fp_site"]:
            missing.append("no readable office website names this address")
        if not f["iema_site_any"]:
            missing.append("no IEMA X-ray facility at this address")
        if not f["lic_matched"]:
            missing.append("row dentist not matched in IDFPR")
    return {"rules_version": RULES_VERSION, "fired": sorted(fired), "proposal": proposal, "conflicts": conflicts,
            "missing": missing,
            "summary": {"fp_site": len(f["fp_site"]), "pl_site_operating": len(f["pl_site_operating"]),
                        "pl_site_tied": sum(1 for _, t in f["pl_site_ties"] if t),
                        "iema_site_active": len(f["iema_site_active"]), "iema_tied": len(f["iema_tied"]),
                        "lic_any_active": f["lic_any_active"], "lic_all_nonactive": f["lic_all_nonactive"],
                        "pl_phone_elsewhere": len(f["pl_phone_elsewhere"]), "dead_sites": f["dead_sites"],
                        "neg": f["neg_signals"]}}


# ---- publish tier -------------------------------------------------------------------------------
# Which auto proposals may be written to the live Directory without an agent (decision record:
# data/office_census/handoffs/20260927_v2_builder/CHECKPOINT.md, "Publish policy"). Everything else
# goes to the v2 agent lane with its packet. Deliberately narrower than "auto":
#   - no Google display name ever overwrites the row's name (P1 successor and rebrand name
#     corrections, duplicates) until an agent or first-party page confirms it;
#   - VALID needs the row's own NAME tied (or a row whose name is its dentist's name), so a
#     dentist-only tie cannot confirm a wrong practice name;
#   - rows v1 flagged IDENTITY_PROBLEM or ESCALATE/gp_scope keep that question for an agent;
#   - MOVED-PH needs the phone listing's own name tied to the row (a phone-only tie can be a number
#     handed to a buyer), and MOVED-D, SUCCESSOR and SPEC-L never publish.
PUBLISH_OPEN_RULES = {"FP-SITE", "PL-RECENT", "PL-IEMA", "IEMA-LIC"}
PUBLISH_REMOVE_RULES = {"PL-CLOSED", "LIC-CLOSED", "HOME-R", "MOVED-PH"}


def publish_tier(packet, result):
    """(True, why) when the proposal may go live unreviewed; (False, why) otherwise."""
    pr = result.get("proposal")
    if not pr:
        return False, "no proposal"
    if pr.get("confidence") != "auto":
        return False, "review confidence"
    base = packet.get("base") or {}
    card = packet["card"]
    rid, dec, ties = pr["rule_id"], pr["decision"], set(pr.get("ties_by") or [])
    if dec in ("VALID", "VALID_CORRECTED"):
        if rid not in PUBLISH_OPEN_RULES:
            return False, f"{rid} does not publish"
        if base.get("decision") == "IDENTITY_PROBLEM" or base.get("reason") == "gp_scope":
            return False, f"v1 {base.get('decision')}/{base.get('reason')}: an agent settles it"
        name_is_dentist = dentist_in(card.get("name"), row_dentists(card.get("providers"))) or \
            dentist_in(card.get("public_name"), row_dentists(card.get("providers")))
        if "name" not in ties and not ("dentist" in ties and name_is_dentist):
            return False, "the row's name is not tied"
        if dec == "VALID_CORRECTED" and set(pr.get("observed") or {}) - {"phone"}:
            return False, "name/website correction: an agent or first-party page confirms it"
        return True, f"{rid} {dec}"
    if rid not in PUBLISH_REMOVE_RULES or pr.get("reason") == "duplicate":
        return False, f"{rid} {pr.get('reason')} does not publish"
    if rid == "MOVED-PH" and not ties & {"name", "dentist"}:
        return False, "phone-only move: the number may have gone to a buyer"
    return True, f"{rid} {pr.get('reason')}"
