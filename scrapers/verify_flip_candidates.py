"""Phase C — web-verification gate for the DSO flip queue.

Consumes data/dso_research/flip_queue_b_union.json (the ranked, deduplicated
flip-candidate triage queue produced by build_flip_queue.py) and, for each
candidate, runs a forced-web-search Claude call that asks ONE question:

    "Is the dental office at <address>, <city>, IL — operating under the legal
     name <name> (and assumed name / DBA <dba>) — owned or operated by a Dental
     Support Organization (DSO) / corporate dental group? If so, which one?"

This is the verification step that stands BETWEEN the detectors (which only find
*candidates* from name/EIN/PSC/DBA signals) and any promotion of an independent
location to corporate. It exists because the binding rule of this project is:

    NEVER promote independent -> corporate on a single weak signal. Verify first.

The harness is READ-ONLY with respect to the database. It NEVER writes to
SQLite or Supabase. Its only side effects are two JSON files under
data/dso_research/ and entries in the research cost log. Promotion is a separate,
GATED step (reclassify_verified_corporate_il.py) run only after the live weekly
sync has completed and the user has explicitly confirmed it.

Evidence protocol (mirrors the anti-hallucination defense in weekly_research.py):
  1. Forced search   — force_search=True guarantees >=1 web_search per candidate.
  2. Per-claim URL   — the verdict schema requires source_urls for any corporate
                       finding; a confirmation with zero URLs is rejected.
  3. Self-assessment — the model returns evidence_quality (verified|partial|
                       insufficient) and searches_executed; it self-rates.
  4. Post-validation — verify_verdict() rejects: missing verdict, zero searches,
                       evidence_quality=insufficient, confirmed_corporate with no
                       source_urls. Rejected verdicts are recorded but NEVER
                       emitted to the promotion file.

Only verdict == "confirmed_corporate" with evidence_quality in (verified,partial)
and >=1 source URL becomes a promotion record. "likely_corporate" is recorded
for human review but is NOT auto-promoted. Low-tier candidates default to
independent unless the search returns strong, specific corporate evidence.

Outputs:
  data/dso_research/flip_verdicts_phasec.json   — full audit: every processed
        candidate, its verdict, evidence_quality, search queries, source URLs,
        model reasoning, cost. Idempotent/resumable (keyed by npi).
  data/dso_research/il_dso_phasec_verified.json — ONLY the confirmed-corporate
        records, in the exact il_dso_locations_merged.json schema, with the
        location's real practice_locations.normalized_address so the gated
        promotion script's xref_key match is guaranteed. Ready to union into
        il_dso_locations_merged.json (or be read directly) at promotion time.

Usage:
  # see what WOULD be verified + estimated cost, no API calls:
  python3 scrapers/verify_flip_candidates.py --tiers high,medium --dry-run

  # verify high + medium tiers, $5 budget cap (resumable — re-run to continue):
  python3 scrapers/verify_flip_candidates.py --tiers high,medium --budget 5

  # add the long low-tier tail later, separate budget:
  python3 scrapers/verify_flip_candidates.py --tiers low --budget 6 --limit 100

  # force re-verification of already-done NPIs:
  python3 scrapers/verify_flip_candidates.py --tiers high --refresh
"""
import argparse
import json
import os
import sqlite3
import sys

# Run as `python3 scrapers/verify_flip_candidates.py` from repo root.
# research_engine.py uses package imports (`from scrapers.X`), so the repo ROOT
# must be importable; the scrapers dir is added for the bare `research_engine`.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

# Load ANTHROPIC_API_KEY from repo .env (project convention; mirrors fast_sync_*).
_env_file = os.path.join(os.path.dirname(_HERE), ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_env_file)
except ImportError:
    if os.path.isfile(_env_file):
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

from research_engine import ResearchEngine, CircuitBreakerOpen  # noqa: E402

try:
    from pipeline_logger import log_scrape_start, log_scrape_complete  # noqa: E402
except Exception:  # pragma: no cover - logger optional in ad-hoc runs
    def log_scrape_start(source):
        return 0.0

    def log_scrape_complete(source, start_time, **k):
        return None

try:
    from logger_config import get_logger  # noqa: E402
    logger = get_logger("verify_flip_candidates")
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("verify_flip_candidates")

DB = "data/dental_pe_tracker.db"
QUEUE = "data/dso_research/flip_queue_b_union.json"
AUDIT = "data/dso_research/flip_verdicts_phasec.json"
VERIFIED = "data/dso_research/il_dso_phasec_verified.json"

# Per-tier search budget. Low tier gets the MOST scrutiny precisely because it is
# the weakest single-signal evidence and the most likely to be a false positive
# (a solo dentist with two offices, a common practice name) — we want the model
# to look hard before it dares call one corporate, and to default to independent.
TIER_MAX_SEARCHES = {"high": 2, "medium": 3, "low": 4}
# Rough planning cost per candidate (Haiku + ~2-4 web searches). Used only for
# the dry-run estimate and the budget guard's look-ahead.
EST_COST_PER_CANDIDATE = 0.02

VALID_VERDICTS = {"confirmed_corporate", "likely_corporate", "independent", "unverified"}
VALID_QUALITY = {"verified", "partial", "insufficient"}

NATIONAL = {
    "Heartland Dental", "Aspen Dental", "Affordable Care",
    "Affordable Dentures & Implants", "Western Dental", "Smile Doctors",
    "Dental Dreams", "Comfort Dental", "Access Dental",
}

VERIFY_SYSTEM = """You are a corporate-ownership verification analyst for US dental practices. \
You are given ONE dental office and a HYPOTHESIS that it is owned/operated by a specific Dental \
Support Organization (DSO) or corporate dental group. Your job is to CONFIRM or REFUTE that \
hypothesis using web search ONLY — never from prior knowledge.

CONTEXT — Illinois Corporate Practice of Dentistry (CPOD): Illinois law (225 ILCS 25) bars \
non-dentist corporations from owning dental practices, so DSOs operate through a "friendly PC": \
a dentist-owned professional corporation with a local name, bound to the DSO by a management \
services agreement. The office's storefront brand and DBA (assumed name) are often the DSO's \
public brand even though the legal owner is a local P.C. So a legal name like "DENTAL \
PROFESSIONALS OF ILLINOIS, P.C." operating offices branded "Aspen Dental" IS corporate.

EVIDENCE PROTOCOL — you MUST follow every rule:
1. Run at least one web_search. Good queries: the office name + city; the DBA/brand + city + \
   "dental"; the address; "<brand> dental support organization"; the brand + "DSO" or "private \
   equity".
2. A finding of corporate ownership REQUIRES at least one concrete source URL that names the \
   brand/DSO at (or operating) this office or this legal entity. No URL -> not confirmed.
3. Acceptable corporate evidence: the DSO's own locator/site listing this address; a news/deal \
   article naming the practice as a DSO location; the brand storefront at the address; a state \
   assumed-name (DBA) record tying the legal P.C. to the DSO brand; the DSO listing the P.C. as \
   a managed entity.
4. If search shows the office is an independent, locally-owned practice (owner-dentist named, no \
   DSO/brand affiliation, no management-company signal), return verdict "independent".
5. If search is inconclusive (can't find the office, conflicting signals), return "unverified". \
   Do NOT guess. Defaulting to "independent"/"unverified" is correct and expected for many \
   candidates — most independent practices are genuinely independent.
6. NEVER fabricate a URL, a brand, or a sponsor. If you did not see it in a search result, it \
   does not exist.

Return ONLY a JSON object, no prose, with EXACTLY these keys:
{
  "verdict": "confirmed_corporate" | "likely_corporate" | "independent" | "unverified",
  "confirmed_dso": "<canonical DSO/brand name, or null>",
  "pe_sponsor": "<private-equity sponsor if a source names one, else null>",
  "evidence_quality": "verified" | "partial" | "insufficient",
  "reasoning": "<2-3 sentences citing what the searches actually showed>",
  "source_urls": ["<url>", ...],
  "searches_executed": <integer>,
  "search_queries": ["<query>", ...]
}
- "confirmed_corporate": direct evidence (>=1 URL) the office is a DSO/corporate location.
- "likely_corporate": strong circumstantial evidence but no single decisive source.
- evidence_quality "verified" = decisive primary source; "partial" = suggestive; \
  "insufficient" = nothing usable found."""

VERIFY_USER = """Office to verify (Illinois):
  Legal name : {name}
  Assumed name / DBA : {dba}
  Address    : {address}, {city}, IL {zip}

HYPOTHESIS to test: this office is owned/operated by **{proposed_dso}**{sponsor_clause}.

Detector signals that produced this hypothesis (for context only — verify independently, do NOT \
treat these as proof):
{signal_lines}

Search the web and decide: is this office a corporate/DSO location, or a genuinely independent \
practice? Return the JSON verdict object exactly as specified."""


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _signal_lines(cand):
    lines = []
    for s in cand.get("signals", []):
        lines.append(f"  - {s}")
    bk = cand.get("brand_keys") or []
    if bk:
        lines.append(f"  - detector brand key(s): {', '.join(bk)}")
    ev = cand.get("evidence", {})
    for b7 in ev.get("b7", []) or []:
        dbas = b7.get("psc_dbas")
        if dbas:
            lines.append(f"  - IDFPR PSC assumed-name(s): {', '.join(dbas)}")
    return "\n".join(lines) or "  (none)"


def verify_verdict(v):
    """Post-validation gate. Returns (ok_to_promote, normalized_verdict, reason).

    ok_to_promote is True ONLY for a decisively-confirmed corporate finding with
    at least one source URL. Everything else is recorded but not promoted.
    """
    if not isinstance(v, dict) or "error" in v and "verdict" not in v:
        return False, None, f"api_error:{v.get('error') if isinstance(v, dict) else 'non_dict'}"

    verdict = v.get("verdict")
    if verdict not in VALID_VERDICTS:
        return False, None, f"bad_verdict:{verdict!r}"

    quality = v.get("evidence_quality")
    if quality not in VALID_QUALITY:
        # tolerate a missing quality but treat as insufficient
        quality = "insufficient"
        v["evidence_quality"] = quality

    searches = v.get("searches_executed")
    try:
        searches = int(searches)
    except (TypeError, ValueError):
        searches = 0
    if searches < 1:
        return False, verdict, "no_searches_executed"

    urls = [u for u in (v.get("source_urls") or []) if isinstance(u, str) and u.strip()]

    if verdict == "confirmed_corporate":
        if quality == "insufficient":
            return False, verdict, "confirmed_but_insufficient_quality"
        if not urls:
            return False, verdict, "confirmed_without_source_url"
        return True, verdict, "ok"

    # likely_corporate / independent / unverified -> recorded, never auto-promoted
    return False, verdict, f"not_promoted:{verdict}"


def load_location_addresses(location_ids):
    """READ-ONLY lookup: location_id -> (normalized_address, zip, city, practice_name).

    Using the location's real normalized_address guarantees the gated promotion
    script's xref_key(address, zip) match succeeds.
    """
    out = {}
    if not location_ids:
        return out
    uri = f"file:{DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    qmarks = ",".join("?" * len(location_ids))
    for r in conn.execute(
        f"""SELECT location_id, normalized_address, zip, city, practice_name
            FROM practice_locations WHERE location_id IN ({qmarks})""",
        list(location_ids),
    ):
        out[r["location_id"]] = (
            r["normalized_address"], r["zip"], r["city"], r["practice_name"])
    conn.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiers", default="high,medium",
                    help="comma list of tiers to verify (high,medium,low)")
    ap.add_argument("--budget", type=float, default=5.0,
                    help="hard USD cap; stop before exceeding it")
    ap.add_argument("--limit", type=int, default=0,
                    help="max candidates to verify this run (0 = no limit)")
    ap.add_argument("--model", default=None,
                    help="override model (default = ResearchEngine default, Haiku)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-verify NPIs already in the audit file")
    ap.add_argument("--dry-run", action="store_true",
                    help="list candidates + cost estimate, make NO API calls")
    args = ap.parse_args()

    tiers = {t.strip() for t in args.tiers.split(",") if t.strip()}
    queue = load_json(QUEUE, {})
    cands = queue.get("candidates", [])
    if not cands:
        print(f"no candidates in {QUEUE} — run build_flip_queue.py first")
        return

    # tier order: high first (cheapest, strongest), then medium, then low.
    order = {"high": 0, "medium": 1, "low": 2}
    selected = [c for c in cands if c.get("tier") in tiers]
    selected.sort(key=lambda c: order.get(c.get("tier"), 9))

    audit = load_json(AUDIT, {})            # npi -> verdict record
    done = set(audit.keys())
    pending = [c for c in selected
               if args.refresh or str(c.get("npi")) not in done]

    print(f"flip queue : {len(cands)} candidates")
    print(f"tiers      : {sorted(tiers, key=lambda t: order.get(t, 9))}")
    print(f"selected   : {len(selected)}  already-verified: {len(selected) - len(pending)}")
    print(f"to verify  : {len(pending)}"
          + (f"  (capped at {args.limit})" if args.limit else ""))
    if args.limit:
        pending = pending[:args.limit]
    est = len(pending) * EST_COST_PER_CANDIDATE
    print(f"est. cost  : ~${est:.2f}   budget cap: ${args.budget:.2f}")

    if args.dry_run:
        print("\nDRY RUN — candidates that would be verified:")
        for c in pending[:60]:
            print(f"  [{c['tier']:6}] {c['npi']}  {c.get('proposed_dso') or '?':22} "
                  f"{(c.get('name') or '')[:34]:34} {c.get('city','')[:16]:16} {c.get('zip','')}")
        if len(pending) > 60:
            print(f"  ... and {len(pending) - 60} more")
        return

    eng = ResearchEngine(model=args.model) if args.model else ResearchEngine()
    if not eng.api_key:
        print("ERROR: ANTHROPIC_API_KEY not set — cannot verify. Aborting.")
        sys.exit(1)

    _t0 = log_scrape_start("verify_flip_candidates")

    spent = 0.0
    promoted, processed = 0, 0
    confirmed_records = {c["npi"]: c for c in cands}  # for re-deriving on rebuild
    try:
        for c in pending:
            if spent + EST_COST_PER_CANDIDATE > args.budget:
                print(f"\nbudget cap reached (${spent:.2f} spent, "
                      f"next ~${EST_COST_PER_CANDIDATE:.2f} would exceed ${args.budget:.2f}) — stopping")
                break
            npi = str(c.get("npi"))
            tier = c.get("tier")
            sponsor = c.get("pe_sponsor")
            sponsor_clause = f" (PE sponsor reportedly: {sponsor})" if sponsor else ""
            user = VERIFY_USER.format(
                name=c.get("name") or "Unknown",
                dba=c.get("dba") or "(none on file)",
                address=c.get("address") or "Unknown",
                city=c.get("city") or "Unknown",
                zip=c.get("zip") or "",
                proposed_dso=c.get("proposed_dso") or "an unidentified DSO/corporate group",
                sponsor_clause=sponsor_clause,
                signal_lines=_signal_lines(c),
            )
            try:
                r = eng._call_api(
                    VERIFY_SYSTEM, user, model=args.model,
                    max_tokens=1200,
                    max_searches=TIER_MAX_SEARCHES.get(tier, 3),
                    force_search=True)
            except CircuitBreakerOpen as e:
                print(f"\nCircuit breaker open — aborting: {e}")
                break

            cost = (r.get("_meta", {}) or {}).get("cost_usd", 0.0) if isinstance(r, dict) else 0.0
            spent += cost or 0.0
            processed += 1

            ok, verdict, reason = verify_verdict(r)
            rec = {
                "npi": npi,
                "tier": tier,
                "location_id": c.get("location_id"),
                "address": c.get("address"),
                "city": c.get("city"),
                "zip": c.get("zip"),
                "name": c.get("name"),
                "proposed_dso": c.get("proposed_dso"),
                "detector_signals": c.get("signals"),
                "verdict": verdict,
                "confirmed_dso": (r.get("confirmed_dso") if isinstance(r, dict) else None),
                "pe_sponsor": (r.get("pe_sponsor") if isinstance(r, dict) else None) or sponsor,
                "evidence_quality": (r.get("evidence_quality") if isinstance(r, dict) else None),
                "reasoning": (r.get("reasoning") if isinstance(r, dict) else None),
                "source_urls": (r.get("source_urls") if isinstance(r, dict) else None),
                "searches_executed": (r.get("searches_executed") if isinstance(r, dict) else None),
                "search_queries": (r.get("search_queries") if isinstance(r, dict) else None),
                "promoted": ok,
                "gate_reason": reason,
                "cost_usd": cost,
            }
            audit[npi] = rec
            if ok:
                promoted += 1

            flag = "✓PROMOTE" if ok else f"·{verdict or 'err'}"
            print(f"  [{tier:6}] {npi}  {flag:18} {reason:28} "
                  f"${spent:5.2f}  {(c.get('proposed_dso') or '?')[:20]}")

            # checkpoint audit every 10 to survive interruption
            if processed % 10 == 0:
                with open(AUDIT, "w") as f:
                    json.dump(audit, f, indent=2)
    finally:
        with open(AUDIT, "w") as f:
            json.dump(audit, f, indent=2)

    # ---- build the promotion-ready merged-schema file from CONFIRMED verdicts ----
    promoted_recs = [v for v in audit.values() if v.get("promoted")]
    loc_ids = {v["location_id"] for v in promoted_recs if v.get("location_id")}
    loc_addr = load_location_addresses(loc_ids)

    verified_out = []
    seen_loc = set()
    for v in promoted_recs:
        lid = v.get("location_id")
        if lid and lid in seen_loc:
            continue          # one record per location
        seen_loc.add(lid)
        # prefer the location's real normalized_address so xref_key match is exact
        addr, zip_, city, pname = loc_addr.get(
            lid, (v.get("address"), v.get("zip"), v.get("city"), v.get("name")))
        brand = v.get("confirmed_dso") or v.get("proposed_dso")
        verified_out.append({
            "address": addr,
            "zip": (zip_ or v.get("zip") or "")[:5],
            "city": city or v.get("city"),
            "dso_name": brand,
            "pe_sponsor": v.get("pe_sponsor"),
            "in_watched": True,
            "_sources": ["phasec_web_verified"],
            "confidence": v.get("evidence_quality") or "verified",
            "location_name": pname or v.get("name"),
            "phone": None,
            "source": "phasec_web_verified",
            "_npi": v.get("npi"),
            "_tier": v.get("tier"),
            "_source_urls": v.get("source_urls"),
        })
    with open(VERIFIED, "w") as f:
        json.dump(verified_out, f, indent=2)

    # ---- summary ----
    by_verdict = {}
    for v in audit.values():
        by_verdict[v.get("verdict")] = by_verdict.get(v.get("verdict"), 0) + 1
    print("\n" + "=" * 64)
    print(f"processed this run : {processed}   spent: ${spent:.2f}")
    print(f"audit total        : {len(audit)}   {AUDIT}")
    print(f"verdict mix        : {by_verdict}")
    print(f"CONFIRMED corporate: {len([v for v in audit.values() if v.get('promoted')])} "
          f"-> {len(verified_out)} unique locations  {VERIFIED}")
    likely = [v for v in audit.values() if v.get("verdict") == "likely_corporate"]
    if likely:
        print(f"likely_corporate (human review, NOT promoted): {len(likely)}")
    print("\nNEXT (GATED — only after weekly sync confirmed):")
    print("  1. review", VERIFIED, "+ likely_corporate rows in", AUDIT)
    print("  2. union the verified file into il_dso_locations_merged.json (or extend")
    print("     reclassify_verified_corporate_il.py to read it), then run that")
    print("     promotion script + sync zip_scores/practice_locations/practices.")

    log_scrape_complete("verify_flip_candidates", _t0,
                        new_records=promoted, updated_records=processed,
                        summary=f"verified {processed}, confirmed {promoted}, ${spent:.2f}")


if __name__ == "__main__":
    main()
