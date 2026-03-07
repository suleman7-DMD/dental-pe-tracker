"""
Merge and Score — final analytical layer for the dental PE tracker.

Runs AFTER all scrapers/importers. Deduplicates deals, enriches reference
tables, scores ZIP-level consolidation, and produces exports + summary.

Usage:
    python3 scrapers/merge_and_score.py
"""

import argparse
import csv
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import func, Column, Integer, Float, Text, Date, UniqueConstraint

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_engine, get_session, Base,
    Deal, Practice, PracticeChange, PESponsor, Platform,
    WatchedZip, DSOLocation, ADAHPIBenchmark,
    table_exists, backup_database, DB_PATH, BACKUP_DIR,
)

log = get_logger("merge_and_score")

COMBINED_DIR = os.path.expanduser("~/dental-pe-tracker/data/combined")


# ── ZipScore Model ──────────────────────────────────────────────────────────


class ZipScore(Base):
    __tablename__ = "zip_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zip_code = Column(Text, nullable=False)
    city = Column(Text)
    state = Column(Text)
    metro_area = Column(Text)
    total_practices = Column(Integer)
    pe_backed_count = Column(Integer)
    dso_affiliated_count = Column(Integer)
    independent_count = Column(Integer)
    unknown_count = Column(Integer)
    classified_count = Column(Integer)
    consolidation_pct = Column(Float)
    consolidation_pct_of_total = Column(Float)
    pe_penetration_pct = Column(Float)
    pct_unknown = Column(Float)
    recent_changes_90d = Column(Integer)
    state_deal_count_12m = Column(Integer)
    score_date = Column(Date)
    opportunity_score = Column(Float)
    data_confidence = Column(Text)

    __table_args__ = (
        UniqueConstraint("zip_code", "score_date", name="uq_zip_score_date"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PART 1 — DEAL DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════


def deduplicate_deals(session):
    all_deals = session.query(Deal).all()
    total_deals = len(all_deals)
    if total_deals == 0:
        return {"total_deals": 0, "duplicates_found": 0, "duplicates_merged": 0, "needs_review": 0}

    consumed = set()
    duplicates_found = 0
    duplicates_merged = 0
    needs_review = 0

    def _domain(url):
        if not url:
            return None
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return None

    def _non_null_count(d):
        cols = [d.deal_date, d.platform_company, d.pe_sponsor, d.target_name,
                d.target_city, d.target_state, d.target_zip, d.deal_type,
                d.deal_size_mm, d.ebitda_multiple, d.specialty, d.num_locations,
                d.source, d.source_url, d.notes, d.raw_text]
        return sum(1 for v in cols if v is not None)

    def _merge_sources(a, b):
        if not a:
            return b
        if not b:
            return a
        parts = sorted(set(a.lower().split("+")) | set(b.lower().split("+")))
        return "+".join(parts)

    mergeable = ["deal_date", "platform_company", "pe_sponsor", "target_name",
                 "target_city", "target_state", "target_zip", "deal_type",
                 "deal_size_mm", "ebitda_multiple", "specialty", "num_locations",
                 "source_url", "notes", "raw_text"]

    # Group deals by normalized platform prefix for faster dedup (avoid O(n²) full scan)
    from collections import defaultdict
    platform_groups = defaultdict(list)
    for d in all_deals:
        key = (d.platform_company or "").lower()[:4]  # first 4 chars as bucket key
        platform_groups[key].append(d)

    for key, group in platform_groups.items():
        for i in range(len(group)):
            a = group[i]
            if a.id in consumed:
                continue
            for j in range(i + 1, len(group)):
                b = group[j]
                if b.id in consumed:
                    continue

                # Primary match
                if not (a.platform_company and b.platform_company and a.target_name and b.target_name):
                    continue
                if fuzz.ratio(a.platform_company.lower(), b.platform_company.lower()) <= 85:
                    continue
                if fuzz.ratio(a.target_name.lower(), b.target_name.lower()) <= 80:
                    continue
                if not (a.deal_date and b.deal_date):
                    continue
                if abs((a.deal_date - b.deal_date).days) > 60:
                    continue

                duplicates_found += 1

                # Secondary confirmation
                confirmed = False
                if a.target_state and b.target_state and a.target_state.upper() == b.target_state.upper():
                    confirmed = True
                elif a.pe_sponsor and b.pe_sponsor and a.pe_sponsor.lower() == b.pe_sponsor.lower():
                    confirmed = True
                elif _domain(a.source_url) and _domain(b.source_url) and _domain(a.source_url) == _domain(b.source_url):
                    confirmed = True

                if not confirmed:
                    log.warning("Possible duplicate not merged — needs review: deal %s (%s/%s) <-> deal %s (%s/%s)",
                                a.id, a.platform_company, a.target_name, b.id, b.platform_company, b.target_name)
                    needs_review += 1
                    continue

                # Merge: keep most complete
                if _non_null_count(b) > _non_null_count(a):
                    keeper, donor = b, a
                else:
                    keeper, donor = a, b

                for attr in mergeable:
                    if getattr(keeper, attr) is None and getattr(donor, attr) is not None:
                        setattr(keeper, attr, getattr(donor, attr))

                keeper.source = _merge_sources(keeper.source, donor.source)
                log.info("Merged duplicate: keep deal %s, remove deal %s (%s / %s)",
                         keeper.id, donor.id, keeper.platform_company, keeper.target_name)
                session.delete(donor)
                consumed.add(donor.id)
                duplicates_merged += 1

    session.commit()
    log.info("Dedup: %d total, %d found, %d merged, %d need review",
             total_deals, duplicates_found, duplicates_merged, needs_review)
    return {"total_deals": total_deals, "duplicates_found": duplicates_found,
            "duplicates_merged": duplicates_merged, "needs_review": needs_review}


# ═══════════════════════════════════════════════════════════════════════════
# PART 2 — PLATFORM AND SPONSOR ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════


def enrich_platforms_and_sponsors(session):
    stats = {"platforms_updated": 0, "sponsors_updated": 0}

    # Pre-load all deals with platform_company in one query (avoid N+1)
    from collections import defaultdict
    all_deals = session.query(Deal).filter(Deal.platform_company.isnot(None)).all()
    deals_by_platform = defaultdict(list)
    for d in all_deals:
        deals_by_platform[d.platform_company].append(d)

    # Platforms
    for name, deals in deals_by_platform.items():
        states = sorted({d.target_state for d in deals if d.target_state})
        specialties = {}
        for d in deals:
            if d.specialty:
                specialties[d.specialty] = specialties.get(d.specialty, 0) + 1
        primary_spec = max(specialties, key=specialties.get) if specialties else None

        # Most recent PE sponsor
        sponsor = None
        for d in sorted(deals, key=lambda x: x.deal_date or date.min, reverse=True):
            if d.pe_sponsor:
                sponsor = d.pe_sponsor
                break

        existing = session.query(Platform).filter_by(name=name).first()
        if existing:
            existing.pe_sponsor_name = sponsor or existing.pe_sponsor_name
            existing.states_active = ", ".join(states) if states else existing.states_active
            existing.specialties = primary_spec or existing.specialties
            existing.estimated_locations = max(len(deals), existing.estimated_locations or 0)
        else:
            session.add(Platform(name=name, pe_sponsor_name=sponsor,
                                 states_active=", ".join(states) if states else None,
                                 specialties=primary_spec, estimated_locations=len(deals)))
        stats["platforms_updated"] += 1

    # Sponsors
    for (name,) in session.query(Deal.pe_sponsor).filter(Deal.pe_sponsor.isnot(None)).distinct():
        deal_count = session.query(func.count(Deal.id)).filter(Deal.pe_sponsor == name).scalar()
        plat_count = session.query(func.count(func.distinct(Deal.platform_company))).filter(Deal.pe_sponsor == name).scalar()

        existing = session.query(PESponsor).filter_by(name=name).first()
        if existing:
            existing.notes = f"{deal_count} deals across {plat_count} platforms"
            existing.healthcare_focus = True
        else:
            session.add(PESponsor(name=name, healthcare_focus=True,
                                   notes=f"{deal_count} deals across {plat_count} platforms"))
        stats["sponsors_updated"] += 1

    session.commit()
    log.info("Enrichment: %d platforms, %d sponsors", stats["platforms_updated"], stats["sponsors_updated"])
    return stats


# ═══════════════════════════════════════════════════════════════════════════
# PART 3 — CONSOLIDATION SCORING
# ═══════════════════════════════════════════════════════════════════════════


def score_watched_zips(session):
    Base.metadata.create_all(bind=session.get_bind())

    today = date.today()
    ninety_ago = today - timedelta(days=90)
    twelve_mo_ago = today - timedelta(days=365)

    watched = session.query(WatchedZip).all()
    has_dso_locs = table_exists("dso_locations")

    # Pre-load DSO locations by ZIP for efficiency
    dso_loc_by_zip = {}
    if has_dso_locs:
        for loc in session.query(DSOLocation).all():
            if loc.zip:
                dso_loc_by_zip.setdefault(loc.zip, []).append(loc)

    zips_scored = 0
    total_consol = 0.0
    total_opp = 0.0

    for wz in watched:
        zc = wz.zip_code

        # Cross-reference DSO locations — upgrade unknowns before counting
        if zc in dso_loc_by_zip:
            unknowns = session.query(Practice).filter(
                Practice.zip == zc, Practice.ownership_status == "unknown"
            ).all()
            for practice in unknowns:
                if not practice.address:
                    continue
                for dloc in dso_loc_by_zip[zc]:
                    if not dloc.address:
                        continue
                    if fuzz.token_sort_ratio(practice.address.lower(), dloc.address.lower()) >= 85:
                        practice.ownership_status = "dso_affiliated"
                        practice.affiliated_dso = dloc.dso_name
                        break
            session.flush()

        # Count practices
        practices = session.query(Practice).filter(Practice.zip == zc).all()
        total = len(practices)
        pe = sum(1 for p in practices if p.ownership_status == "pe_backed")
        dso = sum(1 for p in practices if p.ownership_status == "dso_affiliated")
        indep = sum(1 for p in practices if p.ownership_status == "independent")
        unk = sum(1 for p in practices if p.ownership_status in ("unknown", None))
        classified = total - unk

        consol_pct = ((pe + dso) / classified * 100) if classified > 0 else 0.0
        consol_total = ((pe + dso) / total * 100) if total > 0 else 0.0
        pe_pct = (pe / classified * 100) if classified > 0 else 0.0
        unk_pct = (unk / total * 100) if total > 0 else 0.0

        # Recent changes
        recent = session.query(func.count(PracticeChange.id)).join(
            Practice, PracticeChange.npi == Practice.npi
        ).filter(Practice.zip == zc, PracticeChange.change_date >= ninety_ago).scalar() or 0

        # State deals last 12 months
        st = wz.state
        state_deals = 0
        if st:
            state_deals = session.query(func.count(Deal.id)).filter(
                Deal.target_state == st, Deal.deal_date >= twelve_mo_ago
            ).scalar() or 0

        # Opportunity score
        opp = 100 - consol_pct
        if unk_pct < 10:
            opp += 5
        elif unk_pct < 20:
            opp += 3
        if state_deals > 20:
            opp += 5
        elif state_deals > 10:
            opp += 3
        if unk_pct > 60:
            opp -= 15
        opp = max(0.0, min(100.0, opp))

        confidence = "high" if unk_pct < 20 else ("medium" if unk_pct <= 50 else "low")

        # Upsert
        existing = session.query(ZipScore).filter_by(zip_code=zc, score_date=today).first()
        vals = dict(city=wz.city, state=st, metro_area=wz.metro_area,
                    total_practices=total, pe_backed_count=pe, dso_affiliated_count=dso,
                    independent_count=indep, unknown_count=unk, classified_count=classified,
                    consolidation_pct=round(consol_pct, 2), consolidation_pct_of_total=round(consol_total, 2),
                    pe_penetration_pct=round(pe_pct, 2), pct_unknown=round(unk_pct, 2),
                    recent_changes_90d=recent, state_deal_count_12m=state_deals,
                    opportunity_score=round(opp, 2), data_confidence=confidence)
        if existing:
            for k, v in vals.items():
                setattr(existing, k, v)
        else:
            session.add(ZipScore(zip_code=zc, score_date=today, **vals))

        zips_scored += 1
        total_consol += consol_pct
        total_opp += opp

    session.commit()
    avg_c = round(total_consol / zips_scored, 2) if zips_scored else 0.0
    avg_o = round(total_opp / zips_scored, 2) if zips_scored else 0.0
    log.info("Scored %d ZIPs (avg consolidation=%.1f%%, avg opportunity=%.1f)", zips_scored, avg_c, avg_o)
    return {"zips_scored": zips_scored, "avg_consolidation": avg_c, "avg_opportunity": avg_o}


# ═══════════════════════════════════════════════════════════════════════════
# PART 4 — METRO AREA ROLLUP
# ═══════════════════════════════════════════════════════════════════════════


def metro_rollup(session):
    today = date.today()
    metros = session.query(WatchedZip.metro_area).distinct().all()
    results = []

    for (metro,) in metros:
        if not metro:
            continue

        # Get all ZIP scores for this metro from today
        scores = session.query(ZipScore).filter(
            ZipScore.metro_area == metro, ZipScore.score_date == today
        ).all()

        if not scores:
            log.info("No scores for metro %s today, skipping.", metro)
            continue

        # Aggregate counts
        total = sum(s.total_practices or 0 for s in scores)
        pe = sum(s.pe_backed_count or 0 for s in scores)
        dso = sum(s.dso_affiliated_count or 0 for s in scores)
        indep = sum(s.independent_count or 0 for s in scores)
        unk = sum(s.unknown_count or 0 for s in scores)
        classified = total - unk

        consol = ((pe + dso) / classified * 100) if classified > 0 else 0.0
        consol_total = ((pe + dso) / total * 100) if total > 0 else 0.0
        unk_pct = (unk / total * 100) if total > 0 else 0.0
        confidence = "high" if unk_pct < 20 else ("medium" if unk_pct <= 50 else "low")
        avg_opp = sum(s.opportunity_score or 0 for s in scores) / len(scores) if scores else 0

        # Primary state
        state = scores[0].state if scores else None

        # QoQ change — look for previous score > 30 days ago
        qoq = None
        prev_scores = session.query(ZipScore).filter(
            ZipScore.metro_area == metro, ZipScore.score_date < today - timedelta(days=30)
        ).all()
        if prev_scores:
            prev_total = sum(s.total_practices or 0 for s in prev_scores)
            prev_pe = sum(s.pe_backed_count or 0 for s in prev_scores)
            prev_dso = sum(s.dso_affiliated_count or 0 for s in prev_scores)
            prev_classified = prev_total - sum(s.unknown_count or 0 for s in prev_scores)
            prev_consol = ((prev_pe + prev_dso) / prev_classified * 100) if prev_classified > 0 else 0.0
            qoq = round(consol - prev_consol, 1)
        else:
            log.info("First scoring run for %s — no QoQ comparison available", metro)

        # ADA HPI benchmark
        ada_benchmark = None
        if state and table_exists("ada_hpi_benchmarks"):
            row = session.query(ADAHPIBenchmark).filter(
                ADAHPIBenchmark.state == state,
                ADAHPIBenchmark.career_stage == "all"
            ).order_by(ADAHPIBenchmark.data_year.desc()).first()
            if row:
                ada_benchmark = row.pct_dso_affiliated

        # Top DSO in this metro
        zips_in_metro = [s.zip_code for s in scores]
        top_dso = None
        if zips_in_metro:
            dso_row = session.query(Practice.affiliated_dso, func.count(Practice.id).label("cnt")).filter(
                Practice.zip.in_(zips_in_metro),
                Practice.affiliated_dso.isnot(None)
            ).group_by(Practice.affiliated_dso).order_by(func.count(Practice.id).desc()).first()
            if dso_row:
                top_dso = dso_row[0]

        results.append({
            "metro_area": metro, "state": state, "zip_count": len(scores),
            "total_practices": total, "pe_backed": pe, "dso_affiliated": dso,
            "independent": indep, "unknown": unk,
            "consolidation_pct": round(consol, 1), "consolidation_pct_of_total": round(consol_total, 1),
            "data_confidence": confidence, "qoq_change": qoq,
            "ada_hpi_benchmark": ada_benchmark, "top_dso": top_dso,
            "opportunity_score": round(avg_opp, 1),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# PART 5 — EXPORTS AND BACKUP
# ═══════════════════════════════════════════════════════════════════════════


def export_and_backup(session):
    os.makedirs(COMBINED_DIR, exist_ok=True)

    deals_df = pd.read_sql(session.query(Deal).statement, session.bind)
    deals_path = os.path.join(COMBINED_DIR, "all_dental_pe_deals.csv")
    deals_df.to_csv(deals_path, index=False)

    practices_df = pd.read_sql(session.query(Practice).statement, session.bind)
    practices_path = os.path.join(COMBINED_DIR, "all_dental_practices.csv")
    practices_df.to_csv(practices_path, index=False)

    scores_exported = 0
    if table_exists("zip_scores"):
        scores_df = pd.read_sql("SELECT * FROM zip_scores", session.bind)
        scores_df.to_csv(os.path.join(COMBINED_DIR, "zip_consolidation_scores.csv"), index=False)
        scores_exported = len(scores_df)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"dental_pe_tracker_{date.today()}.db")
    shutil.copy2(DB_PATH, backup_path)

    log.info("Exported %d deals, %d practices, %d scores. Backup: %s",
             len(deals_df), len(practices_df), scores_exported, backup_path)
    return {"deals_exported": len(deals_df), "practices_exported": len(practices_df),
            "scores_exported": scores_exported, "backup_path": backup_path}


# ═══════════════════════════════════════════════════════════════════════════
# PART 6 — TERMINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


def print_summary(session, metro_results, dedup_stats, export_stats):
    total_deals = session.query(Deal).count()
    total_practices = session.query(Practice).count()

    print()
    print("=" * 55)
    print("  CONSOLIDATION INTELLIGENCE SUMMARY")
    print("=" * 55)
    print(f"  Total deals in database:    {total_deals:,}")
    print(f"  Total practices tracked:    {total_practices:,}")

    if total_practices > 0:
        for status in ("pe_backed", "dso_affiliated", "independent", "unknown"):
            cnt = session.query(Practice).filter(Practice.ownership_status == status).count()
            pct = cnt / total_practices * 100
            label = status.replace("_", "-").title()
            print(f"    {label:20} {cnt:>8,}  ({pct:5.1f}%)")
    else:
        print("  No practice data loaded. Run NPPES downloader first.")

    # Metro sections
    if metro_results:
        for m in metro_results:
            print()
            print(f"  {m['metro_area'].upper()} ({m['zip_count']} ZIPs tracked):")
            print(f"    Total practices:              {m['total_practices']:,}")
            print(f"    Consolidated:                 {m['consolidation_pct']:.1f}% (confidence: {m['data_confidence']})")
            print(f"    Conservative (incl unknown):   {m['consolidation_pct_of_total']:.1f}%")
            ada = f"{m['ada_hpi_benchmark']:.1f}%" if m.get("ada_hpi_benchmark") is not None else "not loaded"
            print(f"    ADA HPI {m['state'] or '??'} benchmark:       {ada}")
            qoq = f"{m['qoq_change']:+.1f}%" if m.get("qoq_change") is not None else "first run"
            print(f"    QoQ change:                   {qoq}")
            print(f"    Top DSO presence:             {m.get('top_dso') or 'none detected'}")
            print(f"    Opportunity score:            {m['opportunity_score']:.1f}")
    elif total_practices > 0:
        print("\n  No watched ZIPs scored (run NPPES + classifier first).")

    # Footer
    print()
    dd = dedup_stats
    print(f"  Deals: {dd['total_deals']:,} total, {dd['duplicates_merged']} merged, {dd['needs_review']} flagged for review")
    ex = export_stats
    print(f"  Exports: {ex['deals_exported']:,} deals, {ex['practices_exported']:,} practices, {ex['scores_exported']} scores → /data/combined/")
    print(f"  Backup: {ex['backup_path']}")
    print("=" * 55)
    print()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


def run():
    log.info("=" * 60)
    log.info("Merge and Score starting")
    log.info("=" * 60)

    init_db()
    session = get_session()

    # Part 1
    log.info("Part 1: Deduplicating deals...")
    dedup_stats = deduplicate_deals(session)

    # Part 2
    log.info("Part 2: Enriching platforms and sponsors...")
    enrich_platforms_and_sponsors(session)

    # Part 3 + 4 — only if practices exist
    metro_results = []
    practice_count = session.query(Practice).count()
    if practice_count > 0:
        log.info("Part 3: Scoring watched ZIPs...")
        score_watched_zips(session)

        log.info("Part 4: Metro area rollup...")
        metro_results = metro_rollup(session)
    else:
        log.info("No practices loaded — skipping Parts 3-4.")

    # Part 5
    log.info("Part 5: Exporting and backing up...")
    export_stats = export_and_backup(session)

    # Part 6
    print_summary(session, metro_results, dedup_stats, export_stats)

    session.close()
    log.info("Merge and Score complete.")


if __name__ == "__main__":
    run()
