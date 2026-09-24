#!/usr/bin/env python3
"""Chicagoland office-census queue: builder, ledger checker, batch planner.

Goal: a defensible census of CURRENTLY OPERATING general dental offices in the
269 watched IL ZIPs. This module does NOT decide that any office exists. It
turns every existing data source into a stateful research queue and replays
the append-only research ledger on top of it.

  python3 scrapers/office_census.py build          # regenerate data/office_census/*
  python3 scrapers/office_census.py check-ledger   # validate the ledger only
  python3 scrapers/office_census.py next-batch     # write the next ZIP worklist
  python3 scrapers/office_census.py status [--zip 60602]

Safety: SQLite is opened mode=ro + query_only. No project modules are
imported (database.py decompresses/initializes on import); the address
normalizer is extracted from dedup_practice_locations.py by AST, exactly as
scripts/audit_directory_foundation.py does. The only files written are the
generated artifacts under data/office_census/ (never the ledger) and, for
next-batch, one worklist file.

Units: a candidate is a RESEARCH ITEM, not an office. Only a ledger decision
(see data/office_census/README.md) makes a candidate CONFIRMED_OPERATING_GP.
Prior evidence (job-hunt website checks, AI dossiers, ownership-census review,
Data Axle listing dates) is carried as provenance and never upgraded into a
confirmation by the builder.
"""

import argparse
import ast
import collections
import csv
import datetime
import hashlib
import json
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "dental_pe_tracker.db"
OUT_DIR = ROOT / "data" / "office_census"
LEDGER_PATH = OUT_DIR / "research_ledger.jsonl"
CANDIDATES_PATH = OUT_DIR / "candidates.jsonl"
COVERAGE_PATH = OUT_DIR / "zip_coverage.csv"
MANIFEST_PATH = OUT_DIR / "manifest.json"
WORKLIST_DIR = OUT_DIR / "worklists"
JHV_SEED = ROOT / "data" / "job_hunt_verification_seed.json"
OWNERSHIP_LEDGER = ROOT / "data" / "dso_research" / "RESEARCH_HOME" / "LEDGER.jsonl"
DA_DIR = ROOT / "data" / "data-axle"

RULES_VERSION = "2026-09-24.1"
CONFIRMATION_VALID_DAYS = 365

GP_CLASSES = (
    "solo_established", "solo_new", "solo_inactive", "solo_high_volume",
    "family_practice", "small_group", "large_group", "dso_regional", "dso_national",
)
GP_TAXONOMY = {"122300000X", "1223G0001X"}
SPECIALIST_TAXONOMY_PREFIXES = ("1223D", "1223E", "1223P", "1223S", "1223X")
SPECIALIST_NAME_RE = re.compile(
    r"ORTHODONT|PERIODON|ENDODONT|ORAL SURG|MAXILLOFACIAL|PEDIATRIC DENT|PEDODONT|"
    r"PROSTHODONT|IMPLANT CENT|\bBRACES\b|\bKIDS\b|CHILDREN", re.I)
CLOSURE_RE = re.compile(
    r"permanently closed|has closed|closed its doors|closed permanently|practice (?:is |has )?closed|"
    r"no longer (?:in practice|operating|practicing|at this)|retired and closed|out of business", re.I)
MOVE_RE = re.compile(r"\brelocat\w*|\bmoved (?:to|away)|new (?:address|location) (?:is|at)", re.I)
SUCCESSOR_RE = re.compile(r"\bsuccessor\b|now (?:belongs|operat\w*) (?:to|as)|acquired by|took over", re.I)
PO_BOX_RE = re.compile(r"\bP\.?\s*O\.?\s*BOX\b|\bPOB\b", re.I)
SUITE_RE = re.compile(
    r"(?:\b(STE|SUITE|UNIT|APT|RM|ROOM|BLDG|BUILDING|FL|FLOOR)\b\.?|#)\s*([A-Z0-9][A-Z0-9-]*)", re.I)
NON_DENTAL_SIC = {
    "Attorneys", "Associations", "Laboratories-Dental", "Facial Cosmetology",
    "Physicians & Surgeons", "Ambulatory Surgical Centers", "Denturists",
}
PILOT_ZIPS = ("60602", "60614", "60622", "60623", "60068", "60201", "60126",
              "60540", "60517", "60440", "60491", "60426")

# Queue states. Order = display order; the builder picks the FIRST blocking
# state that applies (identity before status: a building-merge row's dead
# website may belong to another tenant).
STATES = {
    "CONFIRMED_OPERATING_GP": "Ledger decision: operating GP (or mixed GP) office confirmed at this address within the validity window.",
    "NEEDS_CURRENT_VERIFICATION": "Likely an office; no contradiction in existing data, but no current confirmation.",
    "IDENTITY_REVIEW": "Row may merge several offices (multi-tenant building) or duplicate another row; settle identity first.",
    "OPERATING_STATUS_UNRESOLVED": "Existing data contradicts current operation (closure/move note, dead site, no contact channel).",
    "GP_SCOPE_UNRESOLVED": "Unclear whether general dentistry is offered here (specialist signals on a directory row, or GP signals on an excluded specialist row).",
    "LOCATION_INCOMPLETE": "Address unusable for a physical office (PO box, no street number, state mismatch).",
    "PROBABLE_NON_OFFICE": "Excluded row or raw record that is probably not a patient-facing GP office; confirm exclusion.",
    "LIKELY_SPECIALIST_ONLY": "Excluded specialist row with no GP signal; low-priority exclusion check.",
    "SOURCE_CANDIDATE_UNREPRESENTED": "Raw source record (Data Axle / NPPES / DSO locator) at a street address the office table does not have.",
    "EXTERNAL_DISCOVERY": "Office added from outside the repo's data by a research session; awaiting a decision.",
    "RESEARCHED_UNRESOLVED": "Researched; evidence insufficient either way. Needs a call or manual review.",
    "RESOLVED_EXCLUDED": "Ledger decision: not a current GP office (closed, moved, duplicate, specialist-only, non-clinical).",
    "RESOLVED_SPLIT": "Ledger decision: record merged several offices; child candidates carry them.",
}
OPEN_STATES = {
    "NEEDS_CURRENT_VERIFICATION", "IDENTITY_REVIEW", "OPERATING_STATUS_UNRESOLVED",
    "GP_SCOPE_UNRESOLVED", "LOCATION_INCOMPLETE", "SOURCE_CANDIDATE_UNREPRESENTED",
    "EXTERNAL_DISCOVERY", "PROBABLE_NON_OFFICE", "LIKELY_SPECIALIST_ONLY",
}

# ---- ledger vocabulary ------------------------------------------------------
ENTRY_TYPES = {"observation", "decision", "add_candidate", "zip_sweep", "retract"}
SOURCE_FAMILIES = {
    "office_website", "phone_call", "dso_locator", "google_business_profile",
    "insurer_directory", "hrsa_fqhc", "idfpr_license", "nppes", "data_axle",
    "street_view", "healthgrades_zocdoc_yelp", "other_web",
}
# A live website is NOT proof of an office at the address (dead practices keep
# sites up; sites list sister locations). Only a phone call answered at the
# office or the operator's own current locator suffices alone; anything else
# needs operating_at_address from two independent source families.
SINGLE_SOURCE_SUFFICIENT = {"phone_call", "dso_locator"}
CLAIMS = {
    "operating_at_address", "closed", "moved", "not_found", "name", "phone",
    "suite", "gp_services", "specialist_only", "nonclinical", "duplicate_of",
    "hours", "other",
}
TERMINAL = {
    "OPERATING_GP_CONFIRMED": "CONFIRMED_OPERATING_GP",
    "OPERATING_MIXED_GP_CONFIRMED": "CONFIRMED_OPERATING_GP",
    "OPERATING_SPECIALIST_ONLY": "RESOLVED_EXCLUDED",
    "CLOSED": "RESOLVED_EXCLUDED",
    "MOVED": "RESOLVED_EXCLUDED",
    "DUPLICATE": "RESOLVED_EXCLUDED",
    "NONCLINICAL_OR_ADMINISTRATIVE": "RESOLVED_EXCLUDED",
    "MERGED_RECORD_NEEDS_SPLIT": "RESOLVED_SPLIT",
    "UNRESOLVED": "RESEARCHED_UNRESOLVED",
}
CONFIDENCE = {"high", "medium", "low"}
SWEEP_STAGES = ("current_rows", "discovery", "recall_audit")
EXT_ID_RE = re.compile(r"^ext:\d{5}:[a-z0-9][a-z0-9-]{2,60}$")


# ---- helpers ----------------------------------------------------------------
def load_normalizer():
    tree = ast.parse((ROOT / "scrapers/dedup_practice_locations.py").read_text())
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name == "normalize_address") or
             (isinstance(n, ast.Assign) and any(
                 isinstance(t, ast.Name) and t.id == "_STREET_ABBREV" for t in n.targets))]
    scope = {"re": re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "normalizer", "exec"), scope)
    return scope["normalize_address"]


NORM = load_normalizer()


def present(value):
    return value is not None and str(value).strip().lower() not in ("", "nan", "none", "null")


def clean(value):
    return str(value).strip() if present(value) else None


def digits(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-10:] if len(d) >= 10 else None


def suite_of(address):
    if not present(address):
        return None
    matches = SUITE_RE.findall(str(address).upper())
    if not matches:
        return None
    kind, value = matches[-1]
    value = value.strip("-")
    if kind in ("FL", "FLOOR"):
        return "FL" + value
    return value.lstrip("0") or "0"


def street_key(address, zip_code):
    return (NORM(str(address or "")), str(zip_code or "")[:5])


DIRECTIONALS = {"n", "s", "e", "w", "north", "south", "east", "west", "ne", "nw", "se", "sw"}


def loose_key(address, zip_code):
    """ZIP + house number + first 4 letters of the street name: catches spelling
    variants ('w n ave' vs 'w north ave', 'uppr' suffixes) that the strict key misses."""
    toks = re.findall(r"[a-z0-9]+", NORM(str(address or "")))
    if not toks or not re.match(r"^\d", toks[0]):
        return None
    name = next((t for t in toks[1:] if t not in DIRECTIONALS and not t.isdigit()), "")
    return (str(zip_code or "")[:5], toks[0], name[:4])


def key_hash(key):
    return hashlib.sha1("|".join(key).encode()).hexdigest()[:12]


def float_or_none(v):
    try:
        f = float(v)
        return f if f != 0 else None
    except (TypeError, ValueError):
        return None


def json_list(v):
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v) if present(v) else []
        return out if isinstance(out, list) else []
    except (TypeError, ValueError):
        return []


def parse_date(s):
    if not present(s):
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# ---- input loading ----------------------------------------------------------
def load_db():
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    zips = {r["zip_code"]: r["city"] for r in db.execute(
        "SELECT zip_code, city FROM watched_zips WHERE state='IL'")}
    in_zips = "(SELECT zip_code FROM watched_zips WHERE state='IL')"
    locations = [dict(r) for r in db.execute(f"SELECT * FROM practice_locations WHERE zip IN {in_zips}")]
    providers = [dict(r) for r in db.execute(
        f"SELECT npi, practice_name, doing_business_as, entity_type, address, city, state, zip, phone, "
        f"taxonomy_code, last_updated, data_source, data_axle_raw_name, website FROM practices WHERE zip IN {in_zips}")]
    intel = {}
    for r in db.execute(
            "SELECT npi, research_date, website_url, google_review_count, google_recent_date, "
            "verification_quality, red_flags, overall_assessment, provider_notes FROM practice_intel"):
        intel[str(r["npi"])] = dict(r)
    corrections = collections.defaultdict(list)
    for r in db.execute("SELECT location_id, field_key, suggested_value, notes, status, created_at "
                        "FROM practice_manual_corrections"):
        corrections[r["location_id"]].append(dict(r))
    dso = [dict(r) for r in db.execute(
        f"SELECT dso_name, location_name, address, city, state, zip, phone, source_url, scraped_at "
        f"FROM dso_locations WHERE substr(zip,1,5) IN {in_zips}")]
    db.close()
    return zips, locations, providers, intel, corrections, dso


def load_data_axle(zips):
    """Unique raw Data Axle records (IUSA or fallback identity), IL watched ZIPs only."""
    raw = {}
    files = sorted(DA_DIR.rglob("*.csv"))
    for path in files:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                z = (row.get("ZIP Code") or "")[:5]
                if (row.get("State") or "").strip().upper() != "IL" or z not in zips:
                    continue
                ident = row.get("IUSA Number") or json.dumps([
                    row.get(k) for k in ("Company Name", "Address", "ZIP Code", "Phone Number Combined")])
                prev = raw.get(ident)
                # keep the most recently updated copy of each source record
                if prev is None or (row.get("Last Updated On") or "") > (prev.get("Last Updated On") or ""):
                    raw[ident] = {**row, "_ident": ident, "_file": str(path.relative_to(ROOT))}
    return list(raw.values()), len(files)


def load_jhv():
    if not JHV_SEED.exists():
        return {}
    return {r["location_id"]: r for r in json.loads(JHV_SEED.read_text())}


def load_ownership_ledger():
    out = {}
    if not OWNERSHIP_LEDGER.exists():
        return out
    for line in OWNERSHIP_LEDGER.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        loc = r.get("location_id")
        if loc and (loc not in out or str(r.get("reviewed_at", "")) >= str(out[loc].get("reviewed_at", ""))):
            out[loc] = r
    return out


# ---- research ledger --------------------------------------------------------
def read_ledger():
    entries = []
    if not LEDGER_PATH.exists():
        return entries
    for n, line in enumerate(LEDGER_PATH.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append((n, json.loads(line)))
        except ValueError as exc:
            entries.append((n, {"_parse_error": str(exc)}))
    return entries


def check_ledger(entries, known_ids, today):
    """Return (errors, applied) where applied = replayable ledger state."""
    errors = []
    by_id = {}
    retracted = set()
    for n, e in entries:
        if "_parse_error" in e:
            errors.append(f"line {n}: invalid JSON ({e['_parse_error']})")
            continue
        if e.get("type") == "meta":
            continue
        eid = e.get("entry_id")
        if not eid:
            errors.append(f"line {n}: missing entry_id")
            continue
        if eid in by_id:
            errors.append(f"line {n}: duplicate entry_id {eid}")
            continue
        by_id[eid] = (n, e)
        if e.get("type") not in ENTRY_TYPES:
            errors.append(f"{eid}: unknown type {e.get('type')!r}")
        for f in ("researcher", "recorded_at"):
            if not present(e.get(f)):
                errors.append(f"{eid}: missing {f}")
        if e.get("type") == "retract":
            retracted.add(e.get("target_entry_id"))
            if not present(e.get("reason")):
                errors.append(f"{eid}: retract needs reason")
    live = {eid: v for eid, v in by_id.items() if eid not in retracted}

    ext = {}
    for eid, (n, e) in live.items():
        if e.get("type") != "add_candidate":
            continue
        cid = e.get("candidate_id", "")
        if not EXT_ID_RE.match(cid):
            errors.append(f"{eid}: add_candidate id must match ext:<zip>:<slug>, got {cid!r}")
            continue
        if cid in known_ids or cid in ext:
            errors.append(f"{eid}: candidate {cid} already exists")
            continue
        for f in ("zip", "name", "address", "discovered_via"):
            if not present(e.get(f)):
                errors.append(f"{eid}: add_candidate missing {f}")
        if not str(e.get("source_url", "")).startswith(("http://", "https://")):
            errors.append(f"{eid}: add_candidate needs an http(s) source_url")
        if e.get("split_from") and e["split_from"] not in known_ids:
            errors.append(f"{eid}: split_from {e['split_from']} unknown")
        ext[cid] = e
    all_ids = set(known_ids) | set(ext)

    # A loc:/src: id can vanish when the weekly refresh changes the underlying
    # rows (address re-normalized, a source candidate becomes represented).
    # Those entries are ORPHANS: reported in the manifest for a researcher to
    # re-point with a new entry, never silently applied and never build-blocking.
    orphans = []
    observations = collections.defaultdict(list)
    for eid, (n, e) in live.items():
        if e.get("type") != "observation":
            continue
        cid = e.get("candidate_id")
        if cid not in all_ids:
            if str(cid).startswith(("loc:", "src:")):
                orphans.append({"entry_id": eid, "candidate_id": cid, "type": "observation"})
            else:
                errors.append(f"{eid}: observation for unknown candidate {cid}")
            continue
        if e.get("source_family") not in SOURCE_FAMILIES:
            errors.append(f"{eid}: bad source_family {e.get('source_family')!r}")
        if e.get("claim") not in CLAIMS:
            errors.append(f"{eid}: bad claim {e.get('claim')!r}")
        if e.get("confidence") not in CONFIDENCE:
            errors.append(f"{eid}: bad confidence {e.get('confidence')!r}")
        if not parse_date(e.get("observed_at")):
            errors.append(f"{eid}: observed_at must be YYYY-MM-DD")
        url = str(e.get("source_url") or "")
        if not present(e.get("evidence")):
            errors.append(f"{eid}: observation needs evidence (quote or what was seen/said)")
        if e.get("source_family") == "phone_call":
            pass  # no URL for a call; evidence carries who answered and what was said
        elif not url.startswith(("http://", "https://")):
            errors.append(f"{eid}: observation needs an http(s) source_url")
        observations[cid].append(e)

    decisions = {}
    for eid, (n, e) in sorted(live.items(), key=lambda kv: kv[1][0]):
        if e.get("type") != "decision":
            continue
        cid = e.get("candidate_id")
        status = e.get("terminal_status")
        if cid not in all_ids:
            if str(cid).startswith(("loc:", "src:")):
                orphans.append({"entry_id": eid, "candidate_id": cid, "type": "decision"})
            else:
                errors.append(f"{eid}: decision for unknown candidate {cid}")
            continue
        if status not in TERMINAL:
            errors.append(f"{eid}: bad terminal_status {status!r}")
            continue
        if e.get("confidence") not in CONFIDENCE:
            errors.append(f"{eid}: bad confidence {e.get('confidence')!r}")
        if not parse_date(e.get("decided_at")):
            errors.append(f"{eid}: decided_at must be YYYY-MM-DD")
        basis = [live.get(b) for b in e.get("basis_entry_ids", [])]
        if any(b is None for b in basis):
            errors.append(f"{eid}: basis_entry_ids reference missing/retracted entries")
            continue
        basis = [b[1] for b in basis]
        if any(b.get("type") != "observation" or b.get("candidate_id") != cid for b in basis):
            errors.append(f"{eid}: every basis entry must be an observation of the same candidate")
            continue
        claims = {b["claim"] for b in basis}
        fams = {b["source_family"] for b in basis if b["claim"] == "operating_at_address"}
        if status in ("OPERATING_GP_CONFIRMED", "OPERATING_MIXED_GP_CONFIRMED"):
            if not (fams & SINGLE_SOURCE_SUFFICIENT or len(fams) >= 2):
                errors.append(f"{eid}: confirmation needs operating_at_address from "
                              f"{'/'.join(sorted(SINGLE_SOURCE_SUFFICIENT))} or from 2 independent source families")
            decided = parse_date(e.get("decided_at"))
            stale = [b["entry_id"] for b in basis if b["claim"] == "operating_at_address" and decided
                     and parse_date(b.get("observed_at"))
                     and (decided - parse_date(b["observed_at"])).days > CONFIRMATION_VALID_DAYS]
            if stale:
                errors.append(f"{eid}: basis observations older than {CONFIRMATION_VALID_DAYS}d: {stale}")
            if "gp_services" not in claims and status == "OPERATING_MIXED_GP_CONFIRMED":
                errors.append(f"{eid}: mixed confirmation needs a gp_services observation")
            if not present((e.get("fields") or {}).get("office_name")):
                errors.append(f"{eid}: confirmation needs fields.office_name")
        if status in ("CLOSED", "MOVED") and not claims & {"closed", "moved"}:
            errors.append(f"{eid}: {status} needs a positive closed/moved observation (absence is not closure)")
        if status == "MOVED" and not present(e.get("moved_to")):
            errors.append(f"{eid}: MOVED needs moved_to (candidate id or address)")
        if status == "DUPLICATE" and e.get("duplicate_of") not in all_ids:
            errors.append(f"{eid}: DUPLICATE needs duplicate_of = an existing candidate id")
        if status == "OPERATING_SPECIALIST_ONLY" and "specialist_only" not in claims:
            errors.append(f"{eid}: OPERATING_SPECIALIST_ONLY needs a specialist_only observation")
        if status == "NONCLINICAL_OR_ADMINISTRATIVE" and "nonclinical" not in claims:
            errors.append(f"{eid}: NONCLINICAL_OR_ADMINISTRATIVE needs a nonclinical observation")
        if status == "UNRESOLVED" and not present(e.get("notes")):
            errors.append(f"{eid}: UNRESOLVED needs notes on what was tried")
        decisions[cid] = e  # later lines supersede earlier ones

    sweeps = collections.defaultdict(list)
    for eid, (n, e) in live.items():
        if e.get("type") != "zip_sweep":
            continue
        if e.get("stage") not in SWEEP_STAGES:
            errors.append(f"{eid}: bad sweep stage {e.get('stage')!r}")
        if not isinstance(e.get("sources_searched"), list) or not e.get("sources_searched"):
            errors.append(f"{eid}: zip_sweep needs sources_searched list")
        elif any(s not in SOURCE_FAMILIES for s in e["sources_searched"]):
            errors.append(f"{eid}: unknown source family in sources_searched")
        if not parse_date(e.get("completed_at")):
            errors.append(f"{eid}: completed_at must be YYYY-MM-DD")
        sweeps[str(e.get("zip"))].append(e)
    return errors, {"ext": ext, "observations": observations, "decisions": decisions, "sweeps": sweeps,
                    "orphans": orphans}


# ---- signal computation -----------------------------------------------------
def taxonomy_scope(codes):
    codes = {c for c in codes if present(c)}
    gp = bool(codes & GP_TAXONOMY)
    spec = any(c.startswith(SPECIALIST_TAXONOMY_PREFIXES) for c in codes)
    if gp and spec:
        return "mixed_gp_specialist"
    if gp:
        return "gp"
    if spec:
        return "specialist_only"
    return "unknown"


def prior_evidence(loc_id, npis, jhv, intel, own_ledger, corrections):
    ev = {}
    j = jhv.get(loc_id)
    if j:
        ev["job_hunt_check"] = {
            "website_status": j.get("website_status"), "verification_status": j.get("verification_status"),
            "website_url": j.get("website_url"), "public_name": j.get("public_practice_name"),
            "checked_at": str(j.get("last_checked_at") or "")[:10],
            "evidence_urls": (j.get("evidence_urls") or [])[:5],
            "note": (j.get("notes") or "")[:400] or None,
        }
    best = None
    for npi in npis:
        r = intel.get(str(npi))
        if not r:
            continue
        rank = ({"verified": 2, "partial": 1}.get(r.get("verification_quality"), 0), str(r.get("research_date") or ""))
        if best is None or rank > best[0]:
            best = (rank, npi, r)
    if best:
        _, npi, r = best
        urls = json_list(r.get("verification_urls"))
        ev["ai_dossier"] = {
            "npi": str(npi), "quality": r.get("verification_quality"),
            "researched_at": str(r.get("research_date") or "")[:10],
            "website_url": r.get("website_url"), "google_review_count": r.get("google_review_count"),
            "google_recent_review": clean(r.get("google_recent_date")), "urls": urls[:5],
        }
    o = own_ledger.get(loc_id)
    if o:
        ev["ownership_census"] = {
            "reviewed_at": str(o.get("reviewed_at") or "")[:10], "status": o.get("status"),
            "evidence_urls": (o.get("evidence_urls") or [])[:5],
        }
    if corrections.get(loc_id):
        ev["manual_corrections"] = [
            {"field": c["field_key"], "suggested": c["suggested_value"], "note": (c["notes"] or "")[:300],
             "status": c["status"]} for c in corrections[loc_id]]
    j_live = j and j.get("website_status") == "live" and j.get("verification_status") in (
        "roster_verified", "hiring_page_found")
    if j_live:
        level = "site_checked_live"          # own website read, roster/hiring page found
    elif j or "ai_dossier" in ev:
        level = "researched"                 # web research exists, not a current confirmation
    elif ev:
        level = "ownership_review_only"      # ownership-census / manual-correction evidence only
    else:
        level = "none"
    return level, ev


def evidence_text(ev):
    parts = [ev.get("job_hunt_check", {}).get("note") or ""]
    parts += [c.get("note") or "" for c in ev.get("manual_corrections", [])]
    return " ".join(parts)


def build(today=None):
    today = today or datetime.date.today()
    zips, locations, providers, intel, corrections, dso = load_db()
    da_rows, da_files = load_data_axle(zips)
    jhv = load_jhv()
    own_ledger = load_ownership_ledger()
    for r in intel.values():
        text = " ".join(str(r.get(k) or "") for k in ("red_flags", "overall_assessment", "provider_notes"))
        r["_closure"] = bool(CLOSURE_RE.search(text))

    by_key = collections.defaultdict(list)
    for p in providers:
        by_key[street_key(p["address"], p["zip"])].append(p)
    prov_by_npi = {str(p["npi"]): p for p in providers}
    da_by_key = collections.defaultdict(list)
    for r in da_rows:
        da_by_key[street_key(r["Address"], r["ZIP Code"])].append(r)
    loc_keys = collections.defaultdict(list)
    for loc in locations:
        loc_keys[street_key(loc["normalized_address"], loc["zip"])].append(loc["location_id"])

    def is_directory(loc):
        return (loc["state"] == "IL" and loc["entity_classification"] in GP_CLASSES
                and not loc["is_likely_residential"])

    directory_phones = collections.defaultdict(set)
    coord_groups = collections.Counter()
    loc_by_phone = collections.defaultdict(set)
    loc_by_loose = collections.defaultdict(set)
    for loc in locations:
        if digits(loc["phone"]):
            loc_by_phone[digits(loc["phone"])].add(loc["location_id"])
        lk = loose_key(loc["normalized_address"], loc["zip"])
        if lk:
            loc_by_loose[lk].add(loc["location_id"])
        if is_directory(loc):
            ph = digits(loc["phone"])
            if ph:
                directory_phones[ph].add(street_key(loc["normalized_address"], loc["zip"]))
            lat, lon = float_or_none(loc["latitude"]), float_or_none(loc["longitude"])
            if lat and lon:
                coord_groups[(loc["zip"], round(lat, 5), round(lon, 5))] += 1

    candidates = []
    for loc in locations:
        key = street_key(loc["normalized_address"], loc["zip"])
        members = by_key[key]
        member_npis = [str(n) for n in json_list(loc["provider_npis"])]
        member_rows = [prov_by_npi[n] for n in member_npis if n in prov_by_npi]
        taxa = set(json_list(loc["taxonomy_codes"])) | {m["taxonomy_code"] for m in member_rows}
        scope = taxonomy_scope(taxa)
        da_here = da_by_key[key]
        orgs = [m for m in members if m["entity_type"] == "organization" and str(m["npi"]).isdigit()]
        phones_at_key = {digits(m["phone"]) for m in members} | {
            digits(r["Phone Number Combined"]) for r in da_here if r.get("Firm or Individual") == "2"}
        phones_at_key.discard(None)
        suites = sorted({s for s in (suite_of(m["address"]) for m in members) if s} |
                        {s for s in (suite_of(r["Address"]) for r in da_here) if s})
        firm_phones = {digits(r["Phone Number Combined"]) for r in da_here if r.get("Firm or Individual") == "2"}
        firm_phones.discard(None)
        names = {str(m.get(k) or "").strip().casefold() for m in members
                 for k in ("practice_name", "doing_business_as", "data_axle_raw_name")}
        in_dir = is_directory(loc)
        level, ev = prior_evidence(loc["location_id"], member_npis, jhv, intel, own_ledger, corrections)
        flags = set()

        # identity axis
        if len(orgs) >= 2 and len(phones_at_key) >= 2:
            flags.add("multi_org_multi_phone")
        if len(suites) >= 2 and len(phones_at_key) >= 2:
            flags.add("multi_suite_multi_phone")
        if (loc["provider_count"] or 0) >= 12:
            flags.add("high_provider_count")
        if len(loc_keys[key]) > 1:
            flags.add("street_key_shared_with_other_row")
        ph = digits(loc["phone"])
        if in_dir and ph and len(directory_phones[ph]) > 1:
            flags.add("phone_shared_with_other_address")
        if (loc["practice_name"] or "").endswith(" Dental") and (loc["practice_name"] or "").strip().casefold() not in names:
            flags.add("name_possibly_generated")
        if str(loc["primary_npi"] or "").startswith(("DA_", "DIR_")):
            flags.add("no_federal_npi")
        jnote = evidence_text(ev)
        j = ev.get("job_hunt_check") or {}
        if SUCCESSOR_RE.search(jnote):
            flags.add("prior_note_successor")
        # operating axis
        if CLOSURE_RE.search(jnote) or any(intel.get(n, {}).get("_closure") for n in member_npis):
            flags.add("prior_note_closure")
        if MOVE_RE.search(jnote):
            flags.add("prior_note_moved")
        if j.get("website_status") in ("dead", "parked"):
            flags.add("prior_site_dead_or_parked")
        if not present(loc["phone"]) and not present(loc["website"]) and j.get("website_status") != "live":
            flags.add("no_contact_channel")
        da_latest = max((r.get("Last Updated On") or "" for r in da_here), default="")
        if da_latest >= "202501":
            flags.add("da_listing_2025_plus")
        fed_updates = [str(m.get("last_updated") or "") for m in member_rows if str(m["npi"]).isdigit()]
        if fed_updates and max(fed_updates) < "2018-01-01" and not da_here and level == "none":
            flags.add("stale_registry_only")
        # gp-scope axis
        if in_dir and scope == "specialist_only":
            flags.add("no_gp_taxonomy")
        if in_dir and SPECIALIST_NAME_RE.search(loc["practice_name"] or ""):
            flags.add("name_suggests_specialty")
        if scope == "mixed_gp_specialist":
            flags.add("mixed_gp_specialist_taxonomy")
        # location axis
        lat, lon = float_or_none(loc["latitude"]), float_or_none(loc["longitude"])
        da_coords = [r for r in da_here if float_or_none(r.get("Latitude")) and float_or_none(r.get("Longitude"))
                     and r.get("Location Centerpoint") in ("Parcel", "Site Level")]
        if lat and lon:
            coord_status = "stored_unverified"
            if coord_groups[(loc["zip"], round(lat, 5), round(lon, 5))] >= 4:
                coord_status = "stored_suspect_shared_point"
                flags.add("coords_shared_by_4plus_rows")
        elif da_coords:
            coord_status = "recoverable_da_" + ("parcel" if any(
                r["Location Centerpoint"] == "Parcel" for r in da_coords) else "site")
        else:
            coord_status = "none"
        if PO_BOX_RE.search(loc["normalized_address"] or "") or not re.match(r"^\d", loc["normalized_address"] or ""):
            flags.add("address_not_a_street_location")
        if loc["state"] != "IL":
            flags.add("state_mismatch")

        if in_dir:
            if flags & {"address_not_a_street_location", "state_mismatch"}:
                state = "LOCATION_INCOMPLETE"
            elif flags & {"multi_org_multi_phone", "multi_suite_multi_phone", "prior_note_successor"}:
                state = "IDENTITY_REVIEW"
            elif flags & {"prior_note_closure", "prior_note_moved", "prior_site_dead_or_parked",
                          "no_contact_channel", "stale_registry_only"}:
                state = "OPERATING_STATUS_UNRESOLVED"
            elif flags & {"no_gp_taxonomy", "name_suggests_specialty"}:
                state = "GP_SCOPE_UNRESOLVED"
            else:
                state = "NEEDS_CURRENT_VERIFICATION"
            origin = "directory_row"
        else:
            origin = "excluded_row"
            ec = loc["entity_classification"]
            if ec == "specialist":
                state = "GP_SCOPE_UNRESOLVED" if scope in ("gp", "mixed_gp_specialist") else "LIKELY_SPECIALIST_ONLY"
            elif loc["state"] != "IL":
                state = "LOCATION_INCOMPLETE"
            else:
                state = "PROBABLE_NON_OFFICE"
            flags.add("excluded_as_" + ("residential" if loc["is_likely_residential"] else ec))

        candidates.append({
            "candidate_id": "loc:" + loc["location_id"], "origin": origin, "in_directory": in_dir,
            "location_id": loc["location_id"], "zip": loc["zip"], "city": clean(loc["city"]) or zips.get(loc["zip"]),
            "name": clean(loc["practice_name"]), "address": clean(loc["normalized_address"]),
            "suite": suites[0] if len(suites) == 1 else None, "suites_seen": suites,
            "phone": clean(loc["phone"]), "website": clean(loc["website"]) or j.get("website_url"),
            "entity_classification": loc["entity_classification"], "queue_state": state,
            "flags": sorted(flags), "gp_scope_taxonomy": scope,
            "provider_count": loc["provider_count"], "org_npis_at_street": len(orgs),
            "phones_at_street": len(phones_at_key), "da_records_at_street": len(da_here),
            "da_latest_update": da_latest or None, "prior_evidence_level": level, "prior_evidence": ev,
            "source_refs": {"npis": member_npis[:60], "iusa": sorted(r["_ident"] for r in da_here)[:40],
                            "data_sources": clean(loc["data_sources"])},
            "latitude": lat, "longitude": lon, "coord_status": coord_status,
        })

    # raw-source candidates at street keys the office table does not contain
    unrep = collections.defaultdict(lambda: {"da": [], "nppes": [], "dso": []})
    for key, rows in da_by_key.items():
        if key not in loc_keys:
            unrep[key]["da"] = rows
    for key, rows in by_key.items():
        fed = [r for r in rows if re.fullmatch(r"\d{10}", str(r["npi"]))]
        if key not in loc_keys and fed:
            unrep[key]["nppes"] = fed
    for d in dso:
        key = street_key(d["address"], d["zip"])
        if key not in loc_keys:
            unrep[key]["dso"].append(d)
    for key, src in unrep.items():
        da, fed, dl = src["da"], src["nppes"], src["dso"]
        firms = [r for r in da if r.get("Firm or Individual") == "2"] or da
        name = (dl[0]["location_name"] if dl else None) or (firms[0]["Company Name"] if firms else None) or (
            fed[0]["practice_name"] if fed else None)
        flags = set()
        sics = {r.get("Primary SIC Description") for r in da}
        if da and sics <= NON_DENTAL_SIC:
            flags.add("da_non_dental_sic")
        if any(r.get("Location Centerpoint") == "Zip Centroid" for r in da) and not any(
                r.get("Location Centerpoint") in ("Parcel", "Site Level") for r in da):
            flags.add("da_zip_centroid_only")
        da_latest = max((r.get("Last Updated On") or "" for r in da), default="")
        if da and da_latest < "202401":
            flags.add("da_record_pre_2024")
        if da and all(r.get("Firm or Individual") == "1" for r in da):
            flags.add("da_individual_listings_only")
        if SPECIALIST_NAME_RE.search(" ".join(filter(None, [name] + [r["Company Name"] for r in da]))):
            flags.add("name_suggests_specialty")
        phones_here = {p for p in [digits(r["Phone Number Combined"]) for r in da] +
                       [digits(r["phone"]) for r in fed] + [digits(d["phone"]) for d in dl] if p}
        same_phone = sorted({l for p in phones_here for l in loc_by_phone.get(p, ())})
        variant_of = sorted(loc_by_loose.get(loose_key(key[0], key[1]), ()))
        if same_phone:
            flags.add("phone_matches_existing_row")
        if variant_of:
            flags.add("possible_address_variant_of_row")
        fed_scope = taxonomy_scope({r["taxonomy_code"] for r in fed}) if fed else "unknown"
        if fed_scope == "specialist_only":
            flags.add("no_gp_taxonomy")
        addr_sample = next((a for a in [d["address"] for d in dl] + [r["Address"] for r in da] +
                            [r["address"] for r in fed] if present(a)), "")
        if PO_BOX_RE.search(addr_sample or "") or not re.match(r"^\d", NORM(addr_sample or "")):
            flags.add("address_not_a_street_location")
        state = "SOURCE_CANDIDATE_UNREPRESENTED"
        if "address_not_a_street_location" in flags:
            state = "LOCATION_INCOMPLETE"
        elif "da_non_dental_sic" in flags and not dl and not fed:
            state = "PROBABLE_NON_OFFICE"
        coords = [(float_or_none(r.get("Latitude")), float_or_none(r.get("Longitude")), r.get("Location Centerpoint"))
                  for r in da if r.get("Location Centerpoint") in ("Parcel", "Site Level")]
        coords = [c for c in coords if c[0] and c[1]]
        origin = ("dso_locator_unrepresented" if dl else
                  "data_axle_unrepresented" if da else "nppes_unrepresented")
        suites = sorted({s for s in (suite_of(x) for x in [r["Address"] for r in da] +
                                     [r["address"] for r in fed] + [d["address"] for d in dl]) if s})
        phones = sorted({p for p in [digits(r["Phone Number Combined"]) for r in da] +
                         [digits(r["phone"]) for r in fed] + [digits(d["phone"]) for d in dl] if p})
        candidates.append({
            "candidate_id": f"src:{key[1]}:{key_hash(key)}", "origin": origin, "in_directory": False,
            "location_id": None, "zip": key[1], "city": zips.get(key[1]), "name": clean(name),
            "address": key[0], "suite": suites[0] if len(suites) == 1 else None, "suites_seen": suites,
            "phone": phones[0] if len(phones) == 1 else (", ".join(phones[:3]) or None),
            "website": next((clean(r.get("Website")) for r in da if present(r.get("Website"))), None),
            "entity_classification": None, "queue_state": state, "flags": sorted(flags),
            "gp_scope_taxonomy": fed_scope, "provider_count": None, "org_npis_at_street": sum(
                r["entity_type"] == "organization" for r in fed),
            "phones_at_street": len(phones), "da_records_at_street": len(da), "da_latest_update": da_latest or None,
            "prior_evidence_level": "none", "prior_evidence": {},
            "source_refs": {
                "npis": sorted(str(r["npi"]) for r in fed), "iusa": sorted(r["_ident"] for r in da)[:40],
                "da_names": sorted({r["Company Name"] for r in da})[:10],
                "dso": [{"dso": d["dso_name"], "name": d["location_name"], "source": d["source_url"]} for d in dl],
                "same_phone_rows": ["loc:" + l for l in same_phone][:5],
                "address_variant_rows": ["loc:" + l for l in variant_of][:5]},
            "latitude": coords[0][0] if coords else None, "longitude": coords[0][1] if coords else None,
            "coord_status": ("recoverable_da_" + ("parcel" if coords[0][2] == "Parcel" else "site")) if coords else "none",
        })

    known = {c["candidate_id"] for c in candidates}
    errors, led = check_ledger(read_ledger(), known, today)
    if errors:
        return None, errors
    for cid, e in sorted(led["ext"].items()):
        z = str(e["zip"])
        candidates.append({
            "candidate_id": cid, "origin": "external_discovery", "in_directory": False, "location_id": None,
            "zip": z, "city": zips.get(z), "name": e["name"], "address": NORM(e["address"]),
            "suite": e.get("suite"), "suites_seen": [e["suite"]] if e.get("suite") else [],
            "phone": e.get("phone"), "website": e.get("website"), "entity_classification": None,
            "queue_state": "EXTERNAL_DISCOVERY", "flags": ["split_child"] if e.get("split_from") else [],
            "gp_scope_taxonomy": "unknown", "provider_count": None, "org_npis_at_street": 0,
            "phones_at_street": 0, "da_records_at_street": 0, "da_latest_update": None,
            "prior_evidence_level": "none", "prior_evidence": {},
            "source_refs": {"discovered_via": e["discovered_via"], "source_url": e["source_url"],
                            "split_from": e.get("split_from")},
            "latitude": None, "longitude": None, "coord_status": "none",
        })

    split_parents = {e.get("split_from") for e in led["ext"].values() if e.get("split_from")}
    for c in candidates:
        obs = led["observations"].get(c["candidate_id"], [])
        c["observations"] = len(obs)
        c["sources_checked"] = sorted({o["source_family"] for o in obs})
        d = led["decisions"].get(c["candidate_id"])
        c["decision"] = None
        if d:
            c["decision"] = {k: d.get(k) for k in (
                "entry_id", "terminal_status", "decided_at", "confidence", "researcher", "fields",
                "duplicate_of", "moved_to", "notes", "basis_entry_ids")}
            state = TERMINAL[d["terminal_status"]]
            if state == "CONFIRMED_OPERATING_GP":
                age = (today - parse_date(d["decided_at"])).days
                if age > CONFIRMATION_VALID_DAYS:
                    state = "NEEDS_CURRENT_VERIFICATION"
                    c["flags"] = sorted(set(c["flags"]) | {"confirmation_expired"})
                fields = d.get("fields") or {}
                if fields.get("latitude") and fields.get("longitude"):
                    c["latitude"], c["longitude"] = fields["latitude"], fields["longitude"]
                    c["coord_status"] = "verified_" + str(fields.get("geocode_precision") or "rooftop")
            if state == "RESOLVED_SPLIT" and c["candidate_id"] not in split_parents:
                state = "IDENTITY_REVIEW"
                c["flags"] = sorted(set(c["flags"]) | {"split_pending_children"})
            c["queue_state"] = state
        c["priority"] = (1 if c["queue_state"] in ("IDENTITY_REVIEW", "OPERATING_STATUS_UNRESOLVED",
                                                    "SOURCE_CANDIDATE_UNREPRESENTED", "EXTERNAL_DISCOVERY")
                         else 3 if c["queue_state"] in ("PROBABLE_NON_OFFICE", "LIKELY_SPECIALIST_ONLY")
                         else 2)
        c["effort"] = ("done" if c["queue_state"] in ("CONFIRMED_OPERATING_GP", "RESOLVED_EXCLUDED", "RESOLVED_SPLIT")
                       else "quick_confirm" if c["queue_state"] == "NEEDS_CURRENT_VERIFICATION"
                       and c["prior_evidence_level"] == "site_checked_live" and c["phone"]
                       else "deep" if c["priority"] == 1 else "standard")

    coverage = zip_coverage(zips, candidates, led["sweeps"])
    rank = {r["zip"]: r["batch_rank"] for r in coverage}
    for c in candidates:
        c["batch_rank"] = rank.get(c["zip"])
    candidates.sort(key=lambda c: (c["zip"], c["priority"], c["candidate_id"]))
    return {"candidates": candidates, "coverage": coverage, "da_files": da_files,
            "da_records": len(da_rows), "ledger": led, "zips": zips}, []


def zip_coverage(zips, candidates, sweeps):
    by_zip = collections.defaultdict(list)
    for c in candidates:
        by_zip[c["zip"]].append(c)
    rows = []
    for z, city in zips.items():
        cs = by_zip.get(z, [])
        st = collections.Counter(c["queue_state"] for c in cs)
        d = [c for c in cs if c["in_directory"]]
        stages = {s["stage"] for s in sweeps.get(z, [])}
        stage = ("recall_audited" if "recall_audit" in stages else
                 "discovery_done" if "discovery" in stages else
                 "rows_validated" if "current_rows" in stages else
                 "in_progress" if any(c["observations"] or c["decision"] for c in cs) else "not_started")
        open_rows = sum(c["queue_state"] in OPEN_STATES - {"PROBABLE_NON_OFFICE", "LIKELY_SPECIALIST_ONLY"}
                        for c in cs)
        sweep_dates = [s.get("completed_at") for s in sweeps.get(z, [])]
        obs_dates = [c["decision"]["decided_at"] for c in cs if c["decision"]]
        rows.append({
            "zip": z, "city": city, "pilot": z in PILOT_ZIPS, "stage": stage,
            "directory_rows": len(d),
            "excluded_rows": sum(c["origin"] == "excluded_row" for c in cs),
            "source_candidates": sum(c["origin"] in ("data_axle_unrepresented", "nppes_unrepresented",
                                                     "dso_locator_unrepresented") for c in cs),
            "external_discoveries": sum(c["origin"] == "external_discovery" for c in cs),
            "confirmed": st["CONFIRMED_OPERATING_GP"],
            "needs_verification": st["NEEDS_CURRENT_VERIFICATION"],
            "identity_review": st["IDENTITY_REVIEW"],
            "status_unresolved": st["OPERATING_STATUS_UNRESOLVED"],
            "gp_scope_unresolved": st["GP_SCOPE_UNRESOLVED"],
            "location_incomplete": st["LOCATION_INCOMPLETE"],
            "probable_non_office": st["PROBABLE_NON_OFFICE"],
            "likely_specialist_only": st["LIKELY_SPECIALIST_ONLY"],
            "source_unrepresented": st["SOURCE_CANDIDATE_UNREPRESENTED"],
            "external_pending": st["EXTERNAL_DISCOVERY"],
            "researched_unresolved": st["RESEARCHED_UNRESOLVED"],
            "resolved_excluded": st["RESOLVED_EXCLUDED"] + st["RESOLVED_SPLIT"],
            "dir_with_coords": sum(c["coord_status"].startswith(("stored", "verified")) for c in d),
            "dir_missing_coords": sum(not c["coord_status"].startswith(("stored", "verified")) for c in d),
            "dir_coords_recoverable": sum(c["coord_status"].startswith("recoverable") for c in d),
            "dir_coords_suspect": sum(c["coord_status"] == "stored_suspect_shared_point" for c in d),
            "dir_site_checked_live": sum(c["prior_evidence_level"] == "site_checked_live" for c in d),
            "dir_prior_web_research": sum(c["prior_evidence_level"] == "researched" for c in d),
            "dir_ownership_review_only": sum(c["prior_evidence_level"] == "ownership_review_only" for c in d),
            "dir_no_prior_research": sum(c["prior_evidence_level"] == "none" for c in d),
            "dir_identity_flagged": sum(bool(set(c["flags"]) & {"multi_org_multi_phone", "multi_suite_multi_phone",
                                                                "high_provider_count", "phone_shared_with_other_address"})
                                        for c in d),
            "open_items": open_rows,
            "review_items": st["IDENTITY_REVIEW"] + st["OPERATING_STATUS_UNRESOLVED"] + st["GP_SCOPE_UNRESOLVED"]
                            + st["SOURCE_CANDIDATE_UNREPRESENTED"] + st["EXTERNAL_DISCOVERY"],
            "sources_searched": sorted({s for sw in sweeps.get(z, []) for s in sw.get("sources_searched", [])}),
            "last_activity": max(sweep_dates + obs_dates, default=None),
        })
    pilot_order = {z: i for i, z in enumerate(PILOT_ZIPS)}
    rows.sort(key=lambda r: (r["zip"] not in pilot_order, pilot_order.get(r["zip"], 0),
                             -r["review_items"], -r["open_items"], r["zip"]))
    for i, r in enumerate(rows, 1):
        r["batch_rank"] = i
    return rows


# ---- outputs ----------------------------------------------------------------
def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_outputs(res):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_PATH.open("w") as f:
        for c in res["candidates"]:
            f.write(json.dumps(c, sort_keys=True, separators=(",", ":")) + "\n")
    cov = res["coverage"]
    with COVERAGE_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cov[0].keys()))
        w.writeheader()
        for r in sorted(cov, key=lambda r: r["batch_rank"]):
            w.writerow({**r, "sources_searched": ";".join(r["sources_searched"])})
    cands = res["candidates"]
    d = [c for c in cands if c["in_directory"]]
    inputs = {
        "sqlite_sha256": file_sha(DB_PATH), "candidates_sha256": file_sha(CANDIDATES_PATH),
        "ledger_sha256": file_sha(LEDGER_PATH) if LEDGER_PATH.exists() else None,
        "job_hunt_seed_rows": len(load_jhv()), "data_axle_files": res["da_files"],
        "data_axle_unique_records": res["da_records"],
    }
    build_id = hashlib.sha256(json.dumps([RULES_VERSION, inputs["sqlite_sha256"],
                                          inputs["candidates_sha256"], inputs["ledger_sha256"]]).encode()).hexdigest()[:12]
    manifest = {
        "build_id": build_id, "rules_version": RULES_VERSION,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "scope": "IL watched ZIPs only (Boston/MA parked)", "watched_zips": len(res["zips"]),
        "inputs": inputs,
        "totals": {
            "candidates": len(cands), "directory_rows": len(d),
            "by_origin": dict(sorted(collections.Counter(c["origin"] for c in cands).items())),
            "by_state": {s: sum(c["queue_state"] == s for c in cands) for s in STATES},
            "directory_by_state": {s: sum(c["queue_state"] == s for c in d) for s in STATES},
            "directory_by_prior_evidence": dict(sorted(collections.Counter(c["prior_evidence_level"] for c in d).items())),
            "directory_coord_status": dict(sorted(collections.Counter(c["coord_status"] for c in d).items())),
            "directory_flags": dict(sorted(collections.Counter(f for c in d for f in c["flags"]).items())),
            "zips_by_stage": dict(sorted(collections.Counter(r["stage"] for r in cov).items())),
            "ledger_decisions": len(res["ledger"]["decisions"]),
            "ledger_observations": sum(len(v) for v in res["ledger"]["observations"].values()),
        },
        "ledger_orphans": res["ledger"]["orphans"],
        "state_definitions": STATES,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    return manifest


def cmd_build(args):
    res, errors = build()
    if errors:
        print("LEDGER INVALID -- nothing written:")
        for e in errors:
            print("  " + e)
        return 1
    m = write_outputs(res)
    t = m["totals"]
    print(f"build {m['build_id']}  candidates={t['candidates']}  directory_rows={t['directory_rows']}")
    print("by origin:", json.dumps(t["by_origin"]))
    print("directory by state:", json.dumps({k: v for k, v in t["directory_by_state"].items() if v}))
    print("all by state:", json.dumps({k: v for k, v in t["by_state"].items() if v}))
    print("directory prior evidence:", json.dumps(t["directory_by_prior_evidence"]))
    print("directory coords:", json.dumps(t["directory_coord_status"]))
    print(f"wrote {CANDIDATES_PATH.relative_to(ROOT)}, {COVERAGE_PATH.relative_to(ROOT)}, {MANIFEST_PATH.relative_to(ROOT)}")
    return 0


def cmd_check_ledger(args):
    # ext: candidates are created BY the ledger, so only builder ids count as known.
    known = {cid for cid in (json.loads(l)["candidate_id"] for l in CANDIDATES_PATH.read_text().splitlines())
             if not cid.startswith("ext:")} if CANDIDATES_PATH.exists() else set()
    errors, led = check_ledger(read_ledger(), known, datetime.date.today())
    for e in errors:
        print("  " + e)
    print(("FAIL" if errors else "OK") + f": {len(errors)} error(s); decisions={len(led['decisions'])} "
          f"observations={sum(len(v) for v in led['observations'].values())} "
          f"external={len(led['ext'])} sweeps={sum(len(v) for v in led['sweeps'].values())} "
          f"orphans={len(led['orphans'])}")
    for o in led["orphans"]:
        print(f"  ORPHAN {o['entry_id']} -> {o['candidate_id']} (candidate no longer generated; re-point it)")
    return 1 if errors else 0


def load_generated():
    if not CANDIDATES_PATH.exists():
        raise SystemExit("Run `python3 scrapers/office_census.py build` first.")
    cands = [json.loads(l) for l in CANDIDATES_PATH.read_text().splitlines()]
    with COVERAGE_PATH.open() as f:
        cov = list(csv.DictReader(f))
    return cands, cov


def cmd_next_batch(args):
    cands, cov = load_generated()
    cov.sort(key=lambda r: int(r["batch_rank"]))
    todo = [r for r in cov if r["stage"] in ("not_started", "in_progress")] if not args.zip else \
        [r for r in cov if r["zip"] in args.zip]
    picked, total = [], 0
    for r in todo:
        n = int(r["open_items"])
        if picked and (total + n > args.target_items or len(picked) >= args.max_zips):
            break
        picked.append(r)
        total += n
    if not picked:
        print("No unswept ZIPs remain.")
        return 0
    zset = {r["zip"] for r in picked}
    items = [c for c in cands if c["zip"] in zset and c["queue_state"] in OPEN_STATES]
    items.sort(key=lambda c: (c["zip"], c["priority"], c["candidate_id"]))
    WORKLIST_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKLIST_DIR / f"batch_{'_'.join(sorted(zset))}.json"
    worklist = {
        "zips": sorted(zset), "generated_from_build": json.loads(MANIFEST_PATH.read_text())["build_id"],
        "stage": "current_rows", "items": len(items),
        "by_state": dict(collections.Counter(c["queue_state"] for c in items)),
        "instructions": "Follow data/office_census/README.md §Batch protocol. Append ledger entries only.",
        "candidates": items,
    }
    path.write_text(json.dumps(worklist, indent=1) + "\n")
    print(f"next batch: {', '.join(r['zip'] + ' ' + (r['city'] or '') for r in picked)}")
    print(f"items={len(items)}  by_state={json.dumps(worklist['by_state'])}")
    print(f"worklist -> {path.relative_to(ROOT)}")
    return 0


def cmd_status(args):
    cands, cov = load_generated()
    m = json.loads(MANIFEST_PATH.read_text())
    print(f"build {m['build_id']} ({m['built_at']})")
    if args.zip:
        for r in cov:
            if r["zip"] in args.zip:
                print(json.dumps(r, indent=1))
        return 0
    print(json.dumps(m["totals"]["zips_by_stage"]))
    print(json.dumps({k: v for k, v in m["totals"]["directory_by_state"].items() if v}))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("check-ledger")
    nb = sub.add_parser("next-batch")
    nb.add_argument("--zip", nargs="*", help="force specific ZIPs instead of the next unswept ones")
    nb.add_argument("--target-items", type=int, default=40)
    nb.add_argument("--max-zips", type=int, default=3)
    s = sub.add_parser("status")
    s.add_argument("--zip", nargs="*")
    args = ap.parse_args()
    return {"build": cmd_build, "check-ledger": cmd_check_ledger,
            "next-batch": cmd_next_batch, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
