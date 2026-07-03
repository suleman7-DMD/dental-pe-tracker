"""
Consolidate ownership-census agent results into the durable record. Takes a JSON
file {"classifications": [ ...schema rows... ]} produced by the census workflow and:

  1. UPDATEs practice_locations.ownership_tier (+ pe_backed, evidence_basis,
     evidence_urls, confidence, network_id, updated_at) per location_id  (serialized).
  2. Propagates the same ownership fields to the underlying practices rows
     (primary_npi, org_npi of that location) + bumps updated_at  (audit trail).
  3. Appends one line per classification to RESEARCH_HOME/LEDGER.jsonl
     (append-only; skips a (location_id, reviewer_session) pair already present so
     re-runs are idempotent).
  4. Recomputes the census tier tally + coverage and updates RESEARCH_HOME/PROGRESS.json.

ZERO new flips to entity_classification. ZERO deletes. Writes ONLY the new
ownership-axis columns. Boston/MA rows are never touched (the census only feeds
IL location_ids).

Usage:
  python3 scrapers/consolidate_census.py <results.json> --session NAME --validate-only
  python3 scrapers/consolidate_census.py <results.json> --session NAME --allow-db-write

This script is intentionally fail-closed. Ownership-tier writes are DB mutations.
Do not run without an explicit session name and --allow-db-write after QA.
"""
import datetime
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from urllib.parse import urlsplit

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
HOME = os.path.join(ROOT, "data", "dso_research", "RESEARCH_HOME")
LEDGER = os.path.join(HOME, "LEDGER.jsonl")
PROGRESS = os.path.join(HOME, "PROGRESS.json")
# reviewed_at stamps ledger/progress writes with the ACTUAL consolidation date
# (was hardcoded "2026-06-21", which would have written stale audit dates on
# any later run — fixed 2026-07-02).
REVIEWED_AT = datetime.date.today().isoformat()

VALID_TIERS = {"true_independent", "single_loc_group", "dentist_multi",
               "stealth_dso", "branded_dso", "institutional", "undetermined"}
OWN_COLS = ("ownership_tier", "pe_backed", "ownership_evidence_basis",
            "ownership_evidence_urls", "ownership_confidence", "network_id")
VALID_BASES = {"locator", "web_verified", "ein_cluster", "ao_cluster",
               "name_chain", "intel_dossier", "structural", "none"}
VALID_STATUS = {"classified", "undetermined", "needs_verification"}
VALID_CONFIDENCE = {"high", "medium", "low"}
EXCLUDED_GP_CLASSES = {"specialist", "non_clinical", "da_unverified",
                       "org_only_npi", "duplicate_location"}
URL_BASES = {"locator", "web_verified", "intel_dossier"}
ARTIFACT_BASES = {"ein_cluster", "ao_cluster", "name_chain", "structural"}


def usage():
    print("usage: consolidate_census.py <results.json> --session NAME "
          "[--validate-only | --allow-db-write] [--allow-rereview]")
    sys.exit(2)


def parse_args(argv):
    if len(argv) < 2:
        usage()
    results_path = argv[1]
    if "--session" not in argv:
        print("ERROR: --session NAME is required; refusing stale default attribution.")
        usage()
    try:
        session = argv[argv.index("--session") + 1]
    except IndexError:
        usage()
    allow_write = "--allow-db-write" in argv
    validate_only = "--validate-only" in argv
    allow_rereview = "--allow-rereview" in argv
    if allow_write == validate_only:
        print("ERROR: pass exactly one of --validate-only or --allow-db-write.")
        usage()
    return results_path, session, allow_write, allow_rereview


def load_rows(results_path):
    data = json.load(open(results_path))
    if isinstance(data, dict):
        rows = data.get("classifications")
    elif isinstance(data, list):
        rows = data
    else:
        rows = None
    if not isinstance(rows, list):
        raise ValueError("Input must be a list or {'classifications': [...]}.")
    return rows


def listify(value):
    return value if isinstance(value, list) else []


def is_http_url(value):
    """True only for a real http(s) URL string: scheme http/https, dotted host,
    no whitespace. Prose sentences, bare domains ('example.com'), dicts, and
    'see locator page' notes all fail — they belong in evidence_artifacts."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or re.search(r"\s", v):
        return False
    try:
        parts = urlsplit(v)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and "." in (parts.netloc or "")


def is_da(value):
    return str(value or "").startswith("DA_")


def validate_rows(conn, rows, allow_rereview=False):
    errors = []
    seen = set()
    for idx, r in enumerate(rows, 1):
        prefix = f"row {idx} location_id={r.get('location_id')}"
        lid = r.get("location_id")
        tier = r.get("assigned_tier")
        basis = r.get("evidence_basis")
        status = r.get("status")
        confidence = r.get("confidence")
        raw_urls = r.get("evidence_urls")
        raw_artifacts = r.get("evidence_artifacts")
        if raw_urls is not None and not isinstance(raw_urls, list):
            errors.append(f"{prefix}: evidence_urls must be a list, got "
                          f"{type(raw_urls).__name__}")
        if raw_artifacts is not None and not isinstance(raw_artifacts, list):
            errors.append(f"{prefix}: evidence_artifacts must be a list, got "
                          f"{type(raw_artifacts).__name__}")
        urls = listify(raw_urls)
        artifacts = listify(raw_artifacts)

        # Source hygiene (2026-07-02 hardening): every evidence_urls entry must
        # be a real http(s) URL. The 2026-06-21 ready file carried 24 dicts and
        # ~50 prose/bare-domain strings here that the old truthiness check let
        # through — the validator was proving schema shape, not source hygiene.
        for i, u in enumerate(urls):
            if not isinstance(u, str):
                errors.append(f"{prefix}: evidence_urls[{i}] must be a string "
                              f"URL, got {type(u).__name__} (structured evidence "
                              "belongs in evidence_artifacts)")
            elif not is_http_url(u):
                errors.append(f"{prefix}: evidence_urls[{i}] is not a valid "
                              f"http(s) URL: {u.strip()[:80]!r}")
        for i, a in enumerate(artifacts):
            if isinstance(a, str):
                if not a.strip():
                    errors.append(f"{prefix}: evidence_artifacts[{i}] is empty")
            elif isinstance(a, dict):
                if not a:
                    errors.append(f"{prefix}: evidence_artifacts[{i}] is an empty dict")
            else:
                errors.append(f"{prefix}: evidence_artifacts[{i}] must be a "
                              f"string or dict, got {type(a).__name__}")
        valid_urls = [u for u in urls if is_http_url(u)]

        for field in ("location_id", "assigned_tier", "evidence_basis",
                      "confidence", "status", "reasoning"):
            if field not in r:
                errors.append(f"{prefix}: missing {field}")
        if not lid:
            errors.append(f"{prefix}: blank location_id")
            continue
        if lid in seen:
            errors.append(f"{prefix}: duplicate location_id in input")
        seen.add(lid)
        if tier not in VALID_TIERS:
            errors.append(f"{prefix}: invalid assigned_tier {tier!r}")
        if basis not in VALID_BASES:
            errors.append(f"{prefix}: invalid evidence_basis {basis!r}")
        if status not in VALID_STATUS:
            errors.append(f"{prefix}: invalid status {status!r}")
        if confidence not in VALID_CONFIDENCE:
            errors.append(f"{prefix}: invalid confidence {confidence!r}")
        if status == "classified" and confidence == "low":
            errors.append(f"{prefix}: classified rows cannot have low confidence")
        if status == "needs_verification" and tier != "undetermined":
            errors.append(f"{prefix}: needs_verification rows must use assigned_tier=undetermined")
        if status == "classified":
            if basis in URL_BASES and not valid_urls:
                errors.append(f"{prefix}: {basis} classification requires at "
                              "least one VALID http(s) evidence URL")
            if basis in ARTIFACT_BASES and not artifacts:
                errors.append(f"{prefix}: {basis} classification requires evidence_artifacts")
            if tier in {"stealth_dso", "branded_dso"} and not (valid_urls or artifacts):
                errors.append(f"{prefix}: DSO tier requires documentary URL or durable artifact")
            if tier == "true_independent" and basis == "structural" and not artifacts:
                errors.append(f"{prefix}: structural true_independent requires query artifact")

        loc = conn.execute("""
            SELECT pl.location_id, pl.practice_name, pl.city, pl.state, pl.zip,
                   pl.primary_npi, pl.org_npi, pl.provider_npis,
                   pl.entity_classification, pl.ownership_tier,
                   wz.state AS watched_state
            FROM practice_locations pl
            LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
            WHERE pl.location_id=?
        """, (lid,)).fetchone()
        if not loc:
            errors.append(f"{prefix}: location_id not found")
            continue
        if loc["watched_state"] != "IL" or (loc["state"] or "").upper() != "IL":
            errors.append(f"{prefix}: not an IL watched location "
                          f"(state={loc['state']} watched={loc['watched_state']})")
        if loc["entity_classification"] in EXCLUDED_GP_CLASSES:
            errors.append(f"{prefix}: excluded GP class {loc['entity_classification']}")
        if is_da(loc["primary_npi"]) or is_da(loc["org_npi"]):
            if status == "classified":
                errors.append(f"{prefix}: DA_ synthetic NPI cannot be classified final")
        if loc["ownership_tier"] and not allow_rereview:
            errors.append(f"{prefix}: existing ownership_tier={loc['ownership_tier']} "
                          "(use --allow-rereview with superseding evidence)")
        for field, source in (("practice_name", loc["practice_name"]),
                              ("city", loc["city"]),
                              ("zip", loc["zip"]),
                              ("current_entity_classification",
                               loc["entity_classification"])):
            if not r.get(field):
                r[field] = source
        r["provider_npis"] = r.get("provider_npis") or loc["provider_npis"]
    return errors


def main():
    results_path, session, allow_write, allow_rereview = parse_args(sys.argv)
    rows = load_rows(results_path)
    print(f"Loaded {len(rows)} classification rows from {results_path}")

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    errors = validate_rows(c, rows, allow_rereview=allow_rereview)
    if errors:
        print(f"VALIDATION FAILED: {len(errors)} error(s). No DB/ledger/progress writes.")
        for err in errors[:80]:
            print("  -", err)
        if len(errors) > 80:
            print(f"  ... {len(errors) - 80} more")
        sys.exit(1)
    print("Validation OK")
    if not allow_write:
        print("validate-only complete; no DB/ledger/progress writes.")
        return

    # existing (location_id, session) ledger keys for idempotency
    seen = set()
    if os.path.exists(LEDGER):
        for ln in open(LEDGER):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if isinstance(rec, dict) and rec.get("location_id"):
                seen.add((rec["location_id"], rec.get("reviewer_session")))

    written, skipped_bad, appended, tally = 0, 0, 0, defaultdict(int)
    ledger_lines = []

    for r in rows:
        lid = r.get("location_id")
        tier = r.get("assigned_tier")
        if not lid or tier not in VALID_TIERS:
            skipped_bad += 1
            continue
        loc = c.execute(
            "SELECT location_id, primary_npi, org_npi, provider_npis, state "
            "FROM practice_locations WHERE location_id=?",
            (lid,)).fetchone()
        if not loc:
            skipped_bad += 1
            continue
        if (loc["state"] or "").upper() == "MA":   # Boston parked — never touch
            skipped_bad += 1
            continue

        pe = r.get("pe_backed")
        basis = r.get("evidence_basis")
        urls = json.dumps(r.get("evidence_urls") or [])
        conf = r.get("confidence")
        net = r.get("network_id")

        c.execute(f"""UPDATE practice_locations SET
            ownership_tier=?, pe_backed=?, ownership_evidence_basis=?,
            ownership_evidence_urls=?, ownership_confidence=?, network_id=?,
            updated_at=CURRENT_TIMESTAMP WHERE location_id=?""",
            (tier, pe, basis, urls, conf, net, lid))

        # Mirror the location's tier onto EVERY federal NPI practicing at it:
        # primary + org + the provider_npis roster (JSON list column). Before
        # 2026-07-02 only primary/org were updated, which would have left
        # ~644 provider NPIs across ~200 multi-provider locations blank in
        # `practices`. DA_ synthetic NPIs are skipped (da_unverified scope —
        # never census-classified).
        npi_set = {str(x) for x in (loc["primary_npi"], loc["org_npi"]) if x}
        try:
            roster = json.loads(loc["provider_npis"] or "[]")
        except (ValueError, TypeError):
            roster = []
        npi_set.update(str(x) for x in roster if x)
        npis = sorted(n for n in npi_set if not is_da(n))
        if npis:
            qm = ",".join("?" * len(npis))
            c.execute(f"""UPDATE practices SET
                ownership_tier=?, pe_backed=?, ownership_evidence_basis=?,
                ownership_evidence_urls=?, ownership_confidence=?, network_id=?,
                updated_at=CURRENT_TIMESTAMP WHERE npi IN ({qm})""",
                (tier, pe, basis, urls, conf, net, *npis))

        written += 1
        tally[tier] += 1

        if (lid, session) not in seen:
            ledger_lines.append(json.dumps({
                "location_id": lid,
                "primary_npi": loc["primary_npi"], "org_npi": loc["org_npi"],
                "practice_name": r.get("practice_name"),
                "city": r.get("city"),
                "zip": r.get("zip"),
                "current_entity_classification": r.get("current_entity_classification"),
                "provider_npis": r.get("provider_npis"),
                "assigned_tier": tier, "pe_backed": pe,
                "owner_identity": r.get("owner_identity"),
                "network_id": net,
                "evidence_basis": basis,
                "evidence_urls": r.get("evidence_urls") or [],
                "evidence_artifacts": r.get("evidence_artifacts") or [],
                "confidence": conf,
                "status": r.get("status"),
                "reasoning": r.get("reasoning"),
                "reviewer_session": session,
                "reviewed_at": REVIEWED_AT,
            }))
            seen.add((lid, session))
            appended += 1

    c.commit()

    if ledger_lines:
        with open(LEDGER, "a") as f:
            for ln in ledger_lines:
                f.write(ln + "\n")

    # ── refresh PROGRESS.json from the LEDGER (source of truth for coverage) ──
    ledger_by_loc = {}
    if os.path.exists(LEDGER):
        for ln in open(LEDGER):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if isinstance(rec, dict) and rec.get("location_id") and rec.get("assigned_tier"):
                ledger_by_loc[rec["location_id"]] = rec["assigned_tier"]   # latest wins

    full_tally = defaultdict(int)
    for t in ledger_by_loc.values():
        full_tally[t] += 1
    reviewed = len(ledger_by_loc)

    if os.path.exists(PROGRESS):
        prog = json.load(open(PROGRESS))
        universe = (prog.get("universe", {}) or {}).get("il_gp_locations_official", 4439)
        remaining = max(0, universe - reviewed)
        # Canonical census_status schema (matches the scaffold key names — no stale
        # duplicates). reviewed_via_protocol = locations that EARNED a tier through the
        # hand-verified census; coverage_pct = reviewed / universe * 100.
        prog["census_status"] = {
            "reviewed_via_protocol": reviewed,
            "remaining": remaining,
            "coverage_pct": round(reviewed / universe * 100, 2) if universe else 0.0,
            "universe_il_gp_locations": universe,
            "note": (f"{reviewed} of {universe} IL GP locations have EARNED an ownership_tier "
                     f"through the hand-verified census ({round(reviewed/universe*100,2)}%). "
                     f"The remaining {remaining} stay undetermined until earned through evidence. "
                     f"Legacy detector 'corporate' counts are NOT assumed — re-confirmed via this protocol."),
        }
        prog["tier_tally"] = {t: full_tally.get(t, 0) for t in sorted(VALID_TIERS)}
        prog["tier_tally"]["undetermined_unreviewed"] = remaining
        prog["last_consolidated"] = {"session": session, "at": REVIEWED_AT,
                                     "this_run_written": written, "this_run_appended": appended}
        json.dump(prog, open(PROGRESS, "w"), indent=2)

    print(f"DB writes: {written} locations updated | skipped_bad={skipped_bad}")
    print(f"LEDGER: +{appended} new lines (idempotent skip of pre-existing pairs)")
    print(f"This-run tier tally: {dict(sorted(tally.items(), key=lambda kv:-kv[1]))}")
    print(f"CENSUS coverage: {reviewed}/{universe} = "
          f"{round(reviewed/universe*100,2) if universe else 0}%")
    print(f"Full LEDGER tier tally: {dict(sorted(full_tally.items(), key=lambda kv:-kv[1]))}")


if __name__ == "__main__":
    main()
