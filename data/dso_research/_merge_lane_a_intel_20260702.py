"""Opportunistic intel harvest: Lane A census result files -> practice_intel (2026-07-02).

Wave 3+ Lane A research agents optionally attach an "intel" object per practice
row (facts they already saw during ownership research: website, services,
tech, providers, Google rating, hiring, insurance, distinguishing notes —
each block backed by real source URLs). This converter validates those blocks
and lands the survivors in `practice_intel` keyed by the location's
primary_npi, unlocking Launchpad SIGNALS_REQUIRING_INTEL coverage and the
dossier tabs for practices that had no intel row at all.

Gate (mirrors the anti-hallucination gate's spirit — this path is explicitly
LOWER-grade than the 4-layer dossier pipeline and is marked as such):
  - intel block must carry >=1 valid http(s) URL in "sources"
  - google metrics dropped unless google_source_url is a valid URL
  - hiring dropped unless hiring_source_url is a valid URL
  - website_url must itself be a valid URL or it is dropped
  - row skipped if nothing substantive survives the gate
  - NEVER overwrites an existing practice_intel row (existing dossiers came
    through the full 4-layer gate and outrank opportunistic capture)
  - primary_npi must be a real federal NPI present in `practices` (FK)
  - verification_quality is stored as "partial", research_method post-tagged
    to "lane_a_census_opportunistic" so surfaces can distinguish provenance

Idempotent: re-runs skip NPIs that already have a row. Run after each wave's
result files land; safe to run while other waves are still writing (unfinished
units simply aren't on disk yet).

Usage: python3 data/dso_research/_merge_lane_a_intel_20260702.py [--dry-run]
"""
import glob
import json
import os
import re
import sqlite3
import sys
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
LANE = os.path.join(HERE, "_lane_a_20260702")
METHOD = "lane_a_census_opportunistic"

from scrapers.intel_database import store_practice_intel  # noqa: E402


def is_http_url(v):
    if not isinstance(v, str):
        return False
    v = v.strip()
    if not v or re.search(r"\s", v):
        return False
    try:
        parts = urlsplit(v)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and "." in (parts.netloc or "")


def _clean_list(v):
    if isinstance(v, list):
        out = [str(x).strip() for x in v if str(x).strip()]
        return out or None
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return None


def _clean_str(v, maxlen=600):
    if isinstance(v, str) and v.strip():
        return v.strip()[:maxlen]
    return None


def build_research_data(intel, searched, sources):
    """Map the agent's flat intel block onto store_practice_intel's nested schema.
    Returns (research_data, n_substantive_fields)."""
    n = 0
    rd = {
        "_meta": {"model": "claude-sonnet-5", "cost_usd": 0},
        "confidence": "medium",
        "sources": sources,
        "verification": {
            "searches_executed": len(searched or []),
            "evidence_quality": "partial",
            "primary_sources": sources,
        },
    }

    website_url = intel.get("website_url")
    if is_http_url(website_url):
        rd["website"] = {
            "url": website_url.strip(),
            "analysis": _clean_str(intel.get("website_note")),
            "_source_url": website_url.strip(),
        }
        n += 1

    services = _clean_list(intel.get("services"))
    if services:
        rd["services"] = {"listed": services}
        n += 1

    tech = _clean_list(intel.get("technology"))
    if tech:
        rd["technology"] = {"listed": tech}
        n += 1

    prov = {}
    if isinstance(intel.get("provider_count_web"), int) and intel["provider_count_web"] > 0:
        prov["web_count"] = intel["provider_count_web"]
    stage = intel.get("owner_career_stage")
    if stage in ("early_career", "mid_career", "late_career"):
        prov["owner_stage"] = stage
    notes = _clean_str(intel.get("provider_notes"))
    if notes:
        prov["notes"] = notes
    if prov:
        rd["providers"] = prov
        n += 1

    gsrc = intel.get("google_source_url")
    if is_http_url(gsrc) and (intel.get("google_rating") is not None
                              or intel.get("google_review_count") is not None):
        rd["google"] = {
            "rating": intel.get("google_rating"),
            "reviews": intel.get("google_review_count"),
            "_source_url": gsrc.strip(),
        }
        n += 1

    hsrc = intel.get("hiring_source_url")
    hiring = _clean_str(intel.get("hiring"))
    if hiring and is_http_url(hsrc):
        rd["hiring"] = {"active": True, "positions": [hiring], "source": hsrc.strip()}
        n += 1

    ins = {}
    if isinstance(intel.get("accepts_medicaid"), bool):
        ins["medicaid"] = intel["accepts_medicaid"]
    ins_note = _clean_str(intel.get("insurance_note"))
    if ins_note:
        ins["note"] = ins_note
    if ins:
        rd["insurance"] = ins
        n += 1

    distinguishing = _clean_str(intel.get("distinguishing_notes"))
    if distinguishing:
        rd["assessment"] = distinguishing
        n += 1

    return rd, n


def main():
    dry = "--dry-run" in sys.argv
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    stats = {"rows_seen": 0, "intel_blocks": 0, "stored": 0, "skip_no_sources": 0,
             "skip_empty_after_gate": 0, "skip_existing_intel": 0, "skip_no_npi": 0,
             "skip_synthetic_npi": 0, "skip_npi_not_in_practices": 0,
             "skip_location_not_found": 0, "skip_dup_npi_in_run": 0}
    stored_npis = []
    seen_npis = set()

    for path in sorted(glob.glob(os.path.join(LANE, "result_unit_*.json"))):
        try:
            data = json.load(open(path))
        except Exception as e:
            print(f"UNREADABLE {path}: {e}")
            continue
        for r in data.get("classifications", []):
            stats["rows_seen"] += 1
            intel = r.get("intel")
            if not isinstance(intel, dict) or not intel:
                continue
            stats["intel_blocks"] += 1

            sources = [u.strip() for u in (intel.get("sources") or []) if is_http_url(u)]
            if not sources:
                stats["skip_no_sources"] += 1
                continue

            lid = r.get("location_id")
            loc = c.execute(
                "SELECT primary_npi, org_npi FROM practice_locations WHERE location_id=?",
                (lid,)).fetchone() if lid else None
            if not loc:
                stats["skip_location_not_found"] += 1
                continue
            npi = str(loc["primary_npi"] or "").strip() or str(loc["org_npi"] or "").strip()
            if not npi:
                stats["skip_no_npi"] += 1
                continue
            if npi.startswith(("DA_", "DIR_")):
                stats["skip_synthetic_npi"] += 1
                continue
            if npi in seen_npis:
                stats["skip_dup_npi_in_run"] += 1
                continue
            if not c.execute("SELECT 1 FROM practices WHERE npi=?", (npi,)).fetchone():
                stats["skip_npi_not_in_practices"] += 1
                continue
            if c.execute("SELECT 1 FROM practice_intel WHERE npi=?", (npi,)).fetchone():
                stats["skip_existing_intel"] += 1
                continue

            rd, n_fields = build_research_data(intel, r.get("searched"), sources)
            if n_fields == 0:
                stats["skip_empty_after_gate"] += 1
                continue

            seen_npis.add(npi)
            if dry:
                stats["stored"] += 1
                stored_npis.append(npi)
                continue
            store_practice_intel(npi, rd)
            stats["stored"] += 1
            stored_npis.append(npi)

    if stored_npis and not dry:
        # store_practice_intel derives research_method from _meta.model; post-tag
        # these rows so every surface can tell opportunistic capture from the
        # full 4-layer dossier pipeline.
        w = sqlite3.connect(DB)
        w.executemany("UPDATE practice_intel SET research_method=? WHERE npi=?",
                      [(METHOD, n) for n in stored_npis])
        w.commit()
        w.close()

    print(("DRY RUN — " if dry else "") + "intel harvest stats:", json.dumps(stats, indent=1))
    if stored_npis:
        print(f"{'would store' if dry else 'stored'} {len(stored_npis)} practice_intel rows "
              f"(research_method={METHOD}, verification_quality=partial)")
        print("sample NPIs:", stored_npis[:10])
    print("NOTE: Supabase leg — use scrapers/dossier_batch/upsert_practice_intel.py "
          "(surgical UPSERT; avoids the full_replace TRUNCATE) after local write.")


if __name__ == "__main__":
    main()
