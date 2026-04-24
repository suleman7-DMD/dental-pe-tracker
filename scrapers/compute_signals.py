"""
Materialize Warroom-derived practice and ZIP signals.

This script builds two derived tables from existing pipeline tables:
practice_signals and zip_signals. It does not mutate source tables.

Usage:
    python3 scrapers/compute_signals.py --dry-run
    python3 scrapers/compute_signals.py
"""

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.database import DB_PATH
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import (
    log_scrape_complete,
    log_scrape_error,
    log_scrape_start,
)

log = get_logger("compute_signals")


INDEPENDENT_CLASSIFICATIONS = {
    "solo_established",
    "solo_new",
    "solo_inactive",
    "solo_high_volume",
    "family_practice",
    "small_group",
    "large_group",
}
STEALTH_CLASSIFICATIONS = INDEPENDENT_CLASSIFICATIONS
CORPORATE_CLASSIFICATIONS = {"dso_regional", "dso_national"}
RETIREMENT_CLASSIFICATIONS = {"solo_established", "solo_inactive"}

MICRO_CLUSTER_RADIUS_MI = 0.25
DEAL_CATCHMENT_RADIUS_MI = 2.0
WHITE_SPACE_POPULATION_THRESHOLD = 15000
RETIREMENT_HIGH_THRESHOLD = 70

GENERIC_NAMES = {
    "DENTAL",
    "DENTIST",
    "DENTISTS",
    "DENTAL CENTER",
    "DENTAL OFFICE",
    "DENTAL OFFICES",
    "DENTAL CARE",
    "FAMILY DENTAL",
    "GENERAL DENTISTRY",
}

NEW_BUILD_TERMS = (
    "new",
    "growth",
    "growing",
    "development",
    "developments",
    "construction",
    "subdivision",
    "subdivisions",
    "homes",
    "housing",
    "apartment",
    "apartments",
    "multifamily",
    "mixed-use",
)


PRACTICE_SIGNAL_COLUMNS = [
    "npi",
    "practice_id",
    "zip_code",
    "practice_name",
    "city",
    "state",
    "entity_classification",
    "ownership_status",
    "buyability_score",
    "stealth_dso_flag",
    "stealth_dso_cluster_id",
    "stealth_dso_cluster_size",
    "stealth_dso_zip_count",
    "stealth_dso_basis",
    "stealth_dso_reasoning",
    "phantom_inventory_flag",
    "phantom_inventory_reasoning",
    "revenue_default_flag",
    "revenue_default_reasoning",
    "family_dynasty_flag",
    "family_dynasty_reasoning",
    "micro_cluster_flag",
    "micro_cluster_id",
    "micro_cluster_size",
    "micro_cluster_reasoning",
    "intel_quant_disagreement_flag",
    "intel_quant_disagreement_type",
    "intel_quant_disagreement_reasoning",
    "retirement_combo_score",
    "retirement_combo_flag",
    "retirement_combo_reasoning",
    "deal_catchment_24mo",
    "deal_catchment_reasoning",
    "last_change_90d_flag",
    "last_change_date",
    "last_change_type",
    "last_change_reasoning",
    "buyability_pctile_zip_class",
    "buyability_pctile_class",
    "retirement_pctile_zip_class",
    "retirement_pctile_class",
    "high_peer_buyability_flag",
    "high_peer_retirement_flag",
    "peer_percentile_reasoning",
    "zip_white_space_flag",
    "zip_compound_demand_flag",
    "zip_contested_zone_flag",
    "zip_ada_benchmark_gap_flag",
    "data_limitations",
    "created_at",
]


ZIP_SIGNAL_COLUMNS = [
    "zip_code",
    "city",
    "state",
    "metro_area",
    "population",
    "total_practices",
    "total_gp_locations",
    "total_specialist_locations",
    "dld_gp_per_10k",
    "people_per_gp_door",
    "corporate_share_pct",
    "buyable_practice_ratio",
    "stealth_dso_practice_count",
    "stealth_dso_cluster_count",
    "phantom_inventory_count",
    "phantom_inventory_pct",
    "revenue_default_count",
    "family_dynasty_count",
    "micro_cluster_count",
    "micro_cluster_practice_count",
    "intel_quant_disagreement_count",
    "retirement_combo_high_count",
    "last_change_90d_count",
    "deal_count_all_time",
    "deal_count_24mo",
    "deal_catchment_sum_24mo",
    "deal_catchment_max_24mo",
    "compound_demand_flag",
    "compound_demand_score",
    "compound_demand_reasoning",
    "mirror_pair_flag",
    "mirror_pair_count",
    "top_mirror_zip",
    "top_mirror_similarity",
    "top_mirror_corporate_gap_pp",
    "mirror_zips_json",
    "mirror_reasoning",
    "white_space_flag",
    "white_space_score",
    "white_space_reasoning",
    "contested_zone_flag",
    "contested_platform_count",
    "contested_platforms_json",
    "contested_zone_reasoning",
    "ada_benchmark_pct",
    "ada_benchmark_gap_pp",
    "ada_benchmark_gap_flag",
    "ada_benchmark_reasoning",
    "high_peer_buyability_count",
    "high_peer_retirement_count",
    "data_limitations",
    "created_at",
]


PRACTICE_SIGNALS_DDL = """
CREATE TABLE practice_signals (
    npi TEXT PRIMARY KEY,
    practice_id INTEGER,
    zip_code TEXT NOT NULL,
    practice_name TEXT,
    city TEXT,
    state TEXT,
    entity_classification TEXT,
    ownership_status TEXT,
    buyability_score REAL,
    stealth_dso_flag BOOLEAN DEFAULT 0,
    stealth_dso_cluster_id TEXT,
    stealth_dso_cluster_size INTEGER,
    stealth_dso_zip_count INTEGER,
    stealth_dso_basis TEXT,
    stealth_dso_reasoning TEXT,
    phantom_inventory_flag BOOLEAN DEFAULT 0,
    phantom_inventory_reasoning TEXT,
    revenue_default_flag BOOLEAN DEFAULT 0,
    revenue_default_reasoning TEXT,
    family_dynasty_flag BOOLEAN DEFAULT 0,
    family_dynasty_reasoning TEXT,
    micro_cluster_flag BOOLEAN DEFAULT 0,
    micro_cluster_id TEXT,
    micro_cluster_size INTEGER,
    micro_cluster_reasoning TEXT,
    intel_quant_disagreement_flag BOOLEAN DEFAULT 0,
    intel_quant_disagreement_type TEXT,
    intel_quant_disagreement_reasoning TEXT,
    retirement_combo_score INTEGER DEFAULT 0,
    retirement_combo_flag BOOLEAN DEFAULT 0,
    retirement_combo_reasoning TEXT,
    deal_catchment_24mo INTEGER DEFAULT 0,
    deal_catchment_reasoning TEXT,
    last_change_90d_flag BOOLEAN DEFAULT 0,
    last_change_date TEXT,
    last_change_type TEXT,
    last_change_reasoning TEXT,
    buyability_pctile_zip_class REAL,
    buyability_pctile_class REAL,
    retirement_pctile_zip_class REAL,
    retirement_pctile_class REAL,
    high_peer_buyability_flag BOOLEAN DEFAULT 0,
    high_peer_retirement_flag BOOLEAN DEFAULT 0,
    peer_percentile_reasoning TEXT,
    zip_white_space_flag BOOLEAN DEFAULT 0,
    zip_compound_demand_flag BOOLEAN DEFAULT 0,
    zip_contested_zone_flag BOOLEAN DEFAULT 0,
    zip_ada_benchmark_gap_flag BOOLEAN DEFAULT 0,
    data_limitations TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(npi) REFERENCES practices(npi)
)
"""


ZIP_SIGNALS_DDL = """
CREATE TABLE zip_signals (
    zip_code TEXT PRIMARY KEY,
    city TEXT,
    state TEXT,
    metro_area TEXT,
    population INTEGER,
    total_practices INTEGER,
    total_gp_locations INTEGER,
    total_specialist_locations INTEGER,
    dld_gp_per_10k REAL,
    people_per_gp_door INTEGER,
    corporate_share_pct REAL,
    buyable_practice_ratio REAL,
    stealth_dso_practice_count INTEGER DEFAULT 0,
    stealth_dso_cluster_count INTEGER DEFAULT 0,
    phantom_inventory_count INTEGER DEFAULT 0,
    phantom_inventory_pct REAL,
    revenue_default_count INTEGER DEFAULT 0,
    family_dynasty_count INTEGER DEFAULT 0,
    micro_cluster_count INTEGER DEFAULT 0,
    micro_cluster_practice_count INTEGER DEFAULT 0,
    intel_quant_disagreement_count INTEGER DEFAULT 0,
    retirement_combo_high_count INTEGER DEFAULT 0,
    last_change_90d_count INTEGER DEFAULT 0,
    deal_count_all_time INTEGER DEFAULT 0,
    deal_count_24mo INTEGER DEFAULT 0,
    deal_catchment_sum_24mo INTEGER DEFAULT 0,
    deal_catchment_max_24mo INTEGER DEFAULT 0,
    compound_demand_flag BOOLEAN DEFAULT 0,
    compound_demand_score INTEGER DEFAULT 0,
    compound_demand_reasoning TEXT,
    mirror_pair_flag BOOLEAN DEFAULT 0,
    mirror_pair_count INTEGER DEFAULT 0,
    top_mirror_zip TEXT,
    top_mirror_similarity REAL,
    top_mirror_corporate_gap_pp REAL,
    mirror_zips_json TEXT,
    mirror_reasoning TEXT,
    white_space_flag BOOLEAN DEFAULT 0,
    white_space_score INTEGER DEFAULT 0,
    white_space_reasoning TEXT,
    contested_zone_flag BOOLEAN DEFAULT 0,
    contested_platform_count INTEGER DEFAULT 0,
    contested_platforms_json TEXT,
    contested_zone_reasoning TEXT,
    ada_benchmark_pct REAL,
    ada_benchmark_gap_pp REAL,
    ada_benchmark_gap_flag BOOLEAN DEFAULT 0,
    ada_benchmark_reasoning TEXT,
    high_peer_buyability_count INTEGER DEFAULT 0,
    high_peer_retirement_count INTEGER DEFAULT 0,
    data_limitations TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(zip_code) REFERENCES watched_zips(zip_code)
)
"""


INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_zip ON practice_signals(zip_code)",
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_stealth ON practice_signals(stealth_dso_flag)",
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_phantom ON practice_signals(phantom_inventory_flag)",
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_micro ON practice_signals(micro_cluster_id)",
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_retirement ON practice_signals(retirement_combo_score)",
    "CREATE INDEX IF NOT EXISTS ix_practice_signals_disagreement ON practice_signals(intel_quant_disagreement_flag)",
    "CREATE INDEX IF NOT EXISTS ix_zip_signals_white_space ON zip_signals(white_space_flag)",
    "CREATE INDEX IF NOT EXISTS ix_zip_signals_compound ON zip_signals(compound_demand_flag)",
    "CREATE INDEX IF NOT EXISTS ix_zip_signals_mirror ON zip_signals(mirror_pair_flag)",
    "CREATE INDEX IF NOT EXISTS ix_zip_signals_contested ON zip_signals(contested_zone_flag)",
]


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, params=None):
    return [dict(row) for row in conn.execute(sql, params or {})]


def _one(conn, sql, params=None):
    row = conn.execute(sql, params or {}).fetchone()
    return dict(row) if row else None


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truth(value):
    return 1 if value else 0


def _norm_zip(value):
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[:5] if len(digits) >= 5 else None


def _parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _normalize_name(value):
    text = _clean_text(value).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\b(LLC|LTD|INC|PC|P C|DDS|DMD|SC|S C|PLLC|CORP|CO)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cluster_slug(value):
    text = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return text[:80] or "UNKNOWN"


def _normalize_address(value):
    text = _clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    replacements = {
        " STREET ": " ST ",
        " AVENUE ": " AVE ",
        " ROAD ": " RD ",
        " BOULEVARD ": " BLVD ",
        " DRIVE ": " DR ",
        " LANE ": " LN ",
        " COURT ": " CT ",
        " SUITE ": " STE ",
    }
    text = f" {text} "
    for src, dest in replacements.items():
        text = text.replace(src, dest)
    return re.sub(r"\s+", " ", text).strip()


def _platform_name(practice):
    for key in ("affiliated_dso", "parent_company", "franchise_name", "doing_business_as", "practice_name"):
        value = _clean_text(practice.get(key))
        if value:
            return value
    return None


def _pct_fraction(value):
    num = _as_float(value)
    if num is None:
        return None
    return num / 100.0 if num > 1.5 else num


def haversine_mi(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(math.sqrt(a))


class UnionFind:
    def __init__(self, size):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value):
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left, right):
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            self.parent[root_left] = root_right
        elif self.rank[root_left] > self.rank[root_right]:
            self.parent[root_right] = root_left
        else:
            self.parent[root_right] = root_left
            self.rank[root_left] += 1


def _load_inputs(conn):
    watched = {
        row["zip_code"]: row
        for row in _rows(conn, "SELECT * FROM watched_zips ORDER BY zip_code")
    }
    practices = _rows(
        conn,
        """
        SELECT *
        FROM practices
        WHERE zip IN (SELECT zip_code FROM watched_zips)
        ORDER BY zip, practice_name, npi
        """,
    )

    zip_scores = {}
    for row in _rows(conn, "SELECT * FROM zip_scores ORDER BY zip_code, score_date"):
        zip_scores[row["zip_code"]] = row

    practice_intel = {
        row["npi"]: row for row in _rows(conn, "SELECT * FROM practice_intel")
    }
    zip_intel = {
        row["zip_code"]: row for row in _rows(conn, "SELECT * FROM zip_qualitative_intel")
    }
    deals = _rows(conn, "SELECT * FROM deals")
    changes = _rows(conn, "SELECT * FROM practice_changes")
    ada = _rows(
        conn,
        """
        SELECT *
        FROM ada_hpi_benchmarks
        WHERE career_stage = 'all'
        ORDER BY state, data_year
        """,
    )

    return {
        "watched": watched,
        "practices": practices,
        "zip_scores": zip_scores,
        "practice_intel": practice_intel,
        "zip_intel": zip_intel,
        "deals": deals,
        "changes": changes,
        "ada": ada,
    }


def _build_stealth_clusters(practices):
    name_groups = defaultdict(list)
    ein_groups = defaultdict(list)

    for practice in practices:
        if practice.get("entity_classification") not in STEALTH_CLASSIFICATIONS:
            continue

        norm_name = _normalize_name(practice.get("practice_name"))
        if norm_name and len(norm_name) >= 6 and norm_name not in GENERIC_NAMES:
            name_groups[norm_name].append(practice)

        ein = _clean_text(practice.get("ein")).upper()
        if ein and ein not in {"0", "00-0000000", "000000000"}:
            ein_groups[ein].append(practice)

    clusters = []
    for norm_name, members in name_groups.items():
        zips = {m.get("zip") for m in members if m.get("zip")}
        if len(zips) >= 3:
            clusters.append({
                "id": f"name_{_cluster_slug(norm_name)}",
                "basis": "practice_name",
                "label": norm_name,
                "members": members,
                "zip_count": len(zips),
                "size": len(members),
            })

    for ein, members in ein_groups.items():
        zips = {m.get("zip") for m in members if m.get("zip")}
        if len(zips) >= 3:
            clusters.append({
                "id": f"ein_{_cluster_slug(ein)}",
                "basis": "ein",
                "label": ein,
                "members": members,
                "zip_count": len(zips),
                "size": len(members),
            })

    by_npi = {}
    cluster_meta = {}
    for cluster in sorted(clusters, key=lambda c: (-c["zip_count"], -c["size"], c["id"])):
        cluster_meta[cluster["id"]] = cluster
        for member in cluster["members"]:
            npi = member.get("npi")
            existing = by_npi.get(npi)
            if not existing:
                by_npi[npi] = cluster
                continue
            if (cluster["zip_count"], cluster["size"]) > (existing["zip_count"], existing["size"]):
                by_npi[npi] = cluster

    return by_npi, cluster_meta


def _valid_point(practice):
    lat = _as_float(practice.get("latitude"))
    lon = _as_float(practice.get("longitude"))
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _build_micro_clusters(practices):
    points = []
    for practice in practices:
        point = _valid_point(practice)
        if point:
            points.append((practice.get("npi"), point[0], point[1]))

    if not points:
        return {}, {}

    uf = UnionFind(len(points))
    buckets = defaultdict(list)
    cell_size = MICRO_CLUSTER_RADIUS_MI / 69.0

    for idx, (_, lat, lon) in enumerate(points):
        cell = (math.floor(lat / cell_size), math.floor(lon / cell_size))
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                for other in buckets.get((cell[0] + dlat, cell[1] + dlon), []):
                    _, other_lat, other_lon = points[other]
                    if haversine_mi(lat, lon, other_lat, other_lon) <= MICRO_CLUSTER_RADIUS_MI:
                        uf.union(idx, other)
        buckets[cell].append(idx)

    components = defaultdict(list)
    for idx, (npi, _, _) in enumerate(points):
        components[uf.find(idx)].append(npi)

    npi_to_cluster = {}
    cluster_meta = {}
    cluster_num = 1
    for members in sorted(components.values(), key=lambda vals: (-len(vals), vals[0] or "")):
        if len(members) < 3:
            continue
        cluster_id = f"mc_{cluster_num:04d}"
        cluster_num += 1
        cluster_meta[cluster_id] = {"id": cluster_id, "size": len(members), "members": members}
        for npi in members:
            npi_to_cluster[npi] = cluster_meta[cluster_id]

    return npi_to_cluster, cluster_meta


def _build_centroids(practices):
    by_zip = defaultdict(list)
    by_city_state = defaultdict(list)
    for practice in practices:
        point = _valid_point(practice)
        if not point:
            continue
        zc = _norm_zip(practice.get("zip"))
        city = _normalize_name(practice.get("city"))
        state = _clean_text(practice.get("state")).upper()
        if zc:
            by_zip[zc].append(point)
        if city and state:
            by_city_state[(city, state)].append(point)

    def avg(points):
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )

    return (
        {zc: avg(points) for zc, points in by_zip.items()},
        {key: avg(points) for key, points in by_city_state.items()},
    )


def _build_deal_metrics(deals, zip_centroids, city_centroids, run_date):
    cutoff_24mo = run_date - timedelta(days=730)
    deal_count_all = defaultdict(int)
    deal_count_24mo = defaultdict(int)
    recent_deal_points = []

    for deal in deals:
        deal_date = _parse_date(deal.get("deal_date"))
        target_zip = _norm_zip(deal.get("target_zip"))
        if target_zip:
            deal_count_all[target_zip] += 1
            if deal_date and deal_date >= cutoff_24mo:
                deal_count_24mo[target_zip] += 1

        if not deal_date or deal_date < cutoff_24mo:
            continue

        point = None
        source = None
        if target_zip and target_zip in zip_centroids:
            point = zip_centroids[target_zip]
            source = "target_zip centroid"
        else:
            city = _normalize_name(deal.get("target_city"))
            state = _clean_text(deal.get("target_state")).upper()
            if (city, state) in city_centroids:
                point = city_centroids[(city, state)]
                source = "target_city centroid"

        if point:
            recent_deal_points.append({
                "id": deal.get("id"),
                "state": _clean_text(deal.get("target_state")).upper(),
                "point": point,
                "source": source,
            })

    return deal_count_all, deal_count_24mo, recent_deal_points


def _deal_catchment_for_practices(practices, recent_deal_points):
    by_npi = {}
    for practice in practices:
        npi = practice.get("npi")
        point = _valid_point(practice)
        if not point:
            by_npi[npi] = (0, "Practice coordinates unavailable; catchment count set to 0.")
            continue
        state = _clean_text(practice.get("state")).upper()
        count = 0
        for deal in recent_deal_points:
            if state and deal["state"] and state != deal["state"]:
                continue
            if haversine_mi(point[0], point[1], deal["point"][0], deal["point"][1]) <= DEAL_CATCHMENT_RADIUS_MI:
                count += 1
        by_npi[npi] = (
            count,
            f"{count} PE deals within {DEAL_CATCHMENT_RADIUS_MI:g} mi in last 24 months using deal ZIP/city centroids.",
        )
    return by_npi


def _latest_changes(changes, run_date):
    cutoff = run_date - timedelta(days=90)
    latest = {}
    for change in changes:
        npi = change.get("npi")
        change_date = _parse_date(change.get("change_date")) or _parse_date(change.get("created_at"))
        if not npi or not change_date:
            continue
        existing = latest.get(npi)
        if not existing or change_date > existing["date"]:
            latest[npi] = {
                "date": change_date,
                "type": change.get("change_type") or change.get("field_changed"),
                "within_90d": change_date >= cutoff,
            }
    return latest


def _retirement_combo(practice, run_year):
    score = 0
    reasons = []
    classification = practice.get("entity_classification")
    if classification in RETIREMENT_CLASSIFICATIONS:
        score += 40
        reasons.append(f"classification={classification}")

    established = _as_int(practice.get("year_established"))
    if established and (run_year - established) >= 30:
        score += 30
        reasons.append(f"established {established} ({run_year - established} years)")

    if not _clean_text(practice.get("website")):
        score += 15
        reasons.append("no website")

    if not _clean_text(practice.get("phone")):
        score += 10
        reasons.append("no phone")

    if _as_int(practice.get("num_providers")) == 1:
        score += 5
        reasons.append("single provider")

    score = min(score, 100)
    if reasons:
        return score, "; ".join(reasons)
    return score, "No retirement-combo inputs matched."


def _rank_percentiles(items):
    values = [(key, _as_float(value)) for key, value in items if _as_float(value) is not None]
    if len(values) < 2:
        return {key: None for key, _ in values}

    values.sort(key=lambda item: item[1])
    result = {}
    first_rank_for_value = {}
    for idx, (_, value) in enumerate(values):
        first_rank_for_value.setdefault(value, idx + 1)
    denom = len(values) - 1
    for key, value in values:
        rank = first_rank_for_value[value]
        result[key] = round(((rank - 1) / denom) * 100, 1)
    return result


def _build_percentiles(practices, retirement_scores):
    buy_zip_class = defaultdict(list)
    buy_class = defaultdict(list)
    ret_zip_class = defaultdict(list)
    ret_class = defaultdict(list)

    for practice in practices:
        npi = practice.get("npi")
        classification = practice.get("entity_classification") or "unknown"
        zip_code = practice.get("zip")
        buyability = _as_float(practice.get("buyability_score"))
        if buyability is not None:
            buy_zip_class[(zip_code, classification)].append((npi, buyability))
            buy_class[classification].append((npi, buyability))
        ret_score = retirement_scores.get(npi, 0)
        ret_zip_class[(zip_code, classification)].append((npi, ret_score))
        ret_class[classification].append((npi, ret_score))

    def flatten(groups):
        result = {}
        for group_items in groups.values():
            result.update(_rank_percentiles(group_items))
        return result

    return {
        "buy_zip_class": flatten(buy_zip_class),
        "buy_class": flatten(buy_class),
        "ret_zip_class": flatten(ret_zip_class),
        "ret_class": flatten(ret_class),
    }


def _intel_quant_disagreement(practice, intel):
    if not intel:
        return 0, None, None

    readiness = _clean_text(intel.get("acquisition_readiness")).lower()
    buyability = _as_float(practice.get("buyability_score"))
    if buyability is None or not readiness:
        return 0, None, None

    if readiness == "high" and buyability < 40:
        return (
            1,
            "intel_high_quant_low",
            f"Practice intel readiness is high but buyability_score is {buyability:g}.",
        )

    if readiness in {"unlikely", "low"} and buyability >= 70:
        return (
            1,
            "quant_high_intel_low",
            f"buyability_score is {buyability:g} but practice intel readiness is {readiness}.",
        )

    return 0, None, None


def _new_build_signal(zip_intel):
    if not zip_intel:
        return False
    fields = [
        "housing_status",
        "housing_developments",
        "housing_summary",
        "commercial_projects",
        "commercial_note",
        "pop_growth_signals",
        "pop_note",
        "investment_thesis",
    ]
    text = " ".join(_clean_text(zip_intel.get(field)).lower() for field in fields)
    return any(term in text for term in NEW_BUILD_TERMS)


def _compound_demand(zip_score, zip_intel):
    dld = _as_float(zip_score.get("dld_gp_per_10k")) if zip_score else None
    people = _as_int(zip_score.get("people_per_gp_door")) if zip_score else None
    has_new_build = _new_build_signal(zip_intel)

    score = 0
    parts = []
    if dld is not None and dld > 7:
        score += 35
        parts.append(f"dld_gp_per_10k={dld:g} > 7")
    if people is not None and people > 1600:
        score += 35
        parts.append(f"people_per_gp_door={people} > 1600")
    if has_new_build:
        score += 30
        parts.append("ZIP intel contains new-build or growth language")

    flag = score == 100
    if parts:
        return flag, score, "; ".join(parts)
    return False, 0, "No compound demand inputs matched."


def _build_mirror_pairs(zip_scores):
    rows = []
    for zip_code, score in zip_scores.items():
        gp = _as_float(score.get("total_gp_locations")) or 0.0
        spec = _as_float(score.get("total_specialist_locations")) or 0.0
        total = gp + spec
        rows.append({
            "zip_code": zip_code,
            "corp": _pct_fraction(score.get("corporate_share_pct")),
            "values": [
                _as_float(score.get("dld_gp_per_10k")),
                _pct_fraction(score.get("buyable_practice_ratio")),
                _pct_fraction(score.get("corporate_share_pct")),
                _as_float(score.get("people_per_gp_door")),
                (spec / total) if total > 0 else 0.0,
            ],
        })

    complete = [row for row in rows if row["corp"] is not None and all(v is not None for v in row["values"])]
    if len(complete) < 2:
        return {}

    dims = len(complete[0]["values"])
    means = []
    stdevs = []
    for dim in range(dims):
        vals = [row["values"][dim] for row in complete]
        mean = sum(vals) / len(vals)
        variance = sum((value - mean) ** 2 for value in vals) / len(vals)
        means.append(mean)
        stdevs.append(math.sqrt(variance) or 1.0)

    vectors = {}
    for row in complete:
        vectors[row["zip_code"]] = [
            (row["values"][dim] - means[dim]) / stdevs[dim]
            for dim in range(dims)
        ]

    def cosine(left, right):
        dot = sum(a * b for a, b in zip(left, right))
        left_mag = math.sqrt(sum(a * a for a in left))
        right_mag = math.sqrt(sum(b * b for b in right))
        if left_mag == 0 or right_mag == 0:
            return 0.0
        return dot / (left_mag * right_mag)

    by_zip = {}
    for left in complete:
        candidates = []
        for right in complete:
            if left["zip_code"] == right["zip_code"]:
                continue
            gap = abs(left["corp"] - right["corp"])
            if gap < 0.15:
                continue
            sim = cosine(vectors[left["zip_code"]], vectors[right["zip_code"]])
            candidates.append({
                "zip_code": right["zip_code"],
                "similarity": round(sim, 4),
                "corporate_gap_pp": round(gap * 100, 1),
                "corporate_share_pct": round(right["corp"] * 100, 1),
            })
        candidates.sort(key=lambda item: (-item["similarity"], -item["corporate_gap_pp"], item["zip_code"]))
        by_zip[left["zip_code"]] = candidates[:5]

    return by_zip


def _build_contested_zones(practices, zip_scores):
    platform_addresses = defaultdict(lambda: defaultdict(set))
    all_addresses = defaultdict(set)

    for practice in practices:
        zip_code = practice.get("zip")
        if not zip_code:
            continue
        address_key = (_normalize_address(practice.get("address")), _normalize_name(practice.get("city")))
        if address_key[0]:
            all_addresses[zip_code].add(address_key)

        is_corporate = (
            practice.get("entity_classification") in CORPORATE_CLASSIFICATIONS
            or practice.get("ownership_status") in {"dso_affiliated", "pe_backed"}
        )
        if not is_corporate:
            continue
        platform = _platform_name(practice)
        norm_platform = _normalize_name(platform)
        if not norm_platform or norm_platform in GENERIC_NAMES:
            continue
        platform_addresses[zip_code][platform].add(address_key)

    contested = {}
    for zip_code, platforms in platform_addresses.items():
        score = zip_scores.get(zip_code, {})
        denominator = _as_int(score.get("total_gp_locations")) or len(all_addresses.get(zip_code, [])) or 0
        platform_rows = []
        if denominator <= 0:
            contested[zip_code] = []
            continue
        for platform, addresses in platforms.items():
            count = len(addresses)
            share = count / denominator
            if share >= 0.20:
                platform_rows.append({
                    "platform": platform,
                    "locations": count,
                    "share_pct": round(share * 100, 1),
                })
        platform_rows.sort(key=lambda item: (-item["share_pct"], item["platform"]))
        contested[zip_code] = platform_rows
    return contested


def _latest_ada_by_state(ada_rows):
    latest = {}
    for row in ada_rows:
        state = _clean_text(row.get("state")).upper()
        if not state:
            continue
        existing = latest.get(state)
        year = _as_int(row.get("data_year")) or 0
        if not existing or year >= (_as_int(existing.get("data_year")) or 0):
            latest[state] = row
    return latest


def _materialize(conn, practice_rows, zip_rows):
    placeholders = ", ".join(f":{col}" for col in PRACTICE_SIGNAL_COLUMNS)
    practice_insert = (
        f"INSERT INTO practice_signals ({', '.join(PRACTICE_SIGNAL_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )

    zip_placeholders = ", ".join(f":{col}" for col in ZIP_SIGNAL_COLUMNS)
    zip_insert = (
        f"INSERT INTO zip_signals ({', '.join(ZIP_SIGNAL_COLUMNS)}) "
        f"VALUES ({zip_placeholders})"
    )

    with conn:
        conn.execute("DROP TABLE IF EXISTS practice_signals")
        conn.execute("DROP TABLE IF EXISTS zip_signals")
        conn.execute(PRACTICE_SIGNALS_DDL)
        conn.execute(ZIP_SIGNALS_DDL)
        conn.executemany(practice_insert, practice_rows)
        conn.executemany(zip_insert, zip_rows)
        for stmt in INDEX_DDL:
            conn.execute(stmt)


def compute_signal_rows(conn, run_date=None):
    run_date = run_date or date.today()
    created_at = datetime.now().isoformat(timespec="seconds")
    inputs = _load_inputs(conn)

    watched = inputs["watched"]
    practices = inputs["practices"]
    zip_scores = inputs["zip_scores"]
    practice_intel = inputs["practice_intel"]
    zip_intel = inputs["zip_intel"]
    deals = inputs["deals"]
    changes = inputs["changes"]

    stealth_by_npi, stealth_clusters = _build_stealth_clusters(practices)
    micro_by_npi, micro_clusters = _build_micro_clusters(practices)
    zip_centroids, city_centroids = _build_centroids(practices)
    deal_count_all, deal_count_24mo, recent_deal_points = _build_deal_metrics(
        deals, zip_centroids, city_centroids, run_date
    )
    deal_catchments = _deal_catchment_for_practices(practices, recent_deal_points)
    latest_changes = _latest_changes(changes, run_date)

    retirement_scores = {}
    retirement_reasons = {}
    for practice in practices:
        score, reason = _retirement_combo(practice, run_date.year)
        retirement_scores[practice.get("npi")] = score
        retirement_reasons[practice.get("npi")] = reason
    percentiles = _build_percentiles(practices, retirement_scores)

    mirror_pairs = _build_mirror_pairs(zip_scores)
    contested_zones = _build_contested_zones(practices, zip_scores)
    latest_ada = _latest_ada_by_state(inputs["ada"])

    practice_rows = []
    signals_by_zip = defaultdict(list)

    for practice in practices:
        npi = practice.get("npi")
        zip_code = practice.get("zip")
        buyability = _as_float(practice.get("buyability_score"))
        stealth = stealth_by_npi.get(npi)
        micro = micro_by_npi.get(npi)
        latest_change = latest_changes.get(npi)
        intel_flag, intel_type, intel_reason = _intel_quant_disagreement(
            practice, practice_intel.get(npi)
        )
        retirement_score = retirement_scores.get(npi, 0)
        catchment_count, catchment_reason = deal_catchments.get(
            npi, (0, "Practice not evaluated for deal catchment.")
        )

        phantom = not _clean_text(practice.get("phone")) and not _clean_text(practice.get("website"))
        revenue_default = _as_float(practice.get("estimated_revenue")) == 250000
        family = practice.get("entity_classification") == "family_practice"
        buy_zip_pct = percentiles["buy_zip_class"].get(npi)
        buy_class_pct = percentiles["buy_class"].get(npi)
        ret_zip_pct = percentiles["ret_zip_class"].get(npi)
        ret_class_pct = percentiles["ret_class"].get(npi)

        row = {
            "npi": npi,
            "practice_id": practice.get("id"),
            "zip_code": zip_code,
            "practice_name": practice.get("practice_name"),
            "city": practice.get("city"),
            "state": practice.get("state"),
            "entity_classification": practice.get("entity_classification"),
            "ownership_status": practice.get("ownership_status"),
            "buyability_score": buyability,
            "stealth_dso_flag": _truth(stealth),
            "stealth_dso_cluster_id": stealth["id"] if stealth else None,
            "stealth_dso_cluster_size": stealth["size"] if stealth else None,
            "stealth_dso_zip_count": stealth["zip_count"] if stealth else None,
            "stealth_dso_basis": stealth["basis"] if stealth else None,
            "stealth_dso_reasoning": (
                f"{stealth['basis']} '{stealth['label']}' appears across "
                f"{stealth['zip_count']} watched ZIPs ({stealth['size']} NPIs)."
                if stealth else None
            ),
            "phantom_inventory_flag": _truth(phantom),
            "phantom_inventory_reasoning": (
                "Valid watched-ZIP NPI has no phone and no website; hours are unavailable in source schema."
                if phantom else None
            ),
            "revenue_default_flag": _truth(revenue_default),
            "revenue_default_reasoning": (
                "estimated_revenue equals 250000, treated as Data Axle presence/default flag, not true revenue."
                if revenue_default else None
            ),
            "family_dynasty_flag": _truth(family),
            "family_dynasty_reasoning": (
                "entity_classification is family_practice, indicating shared-last-name/internal succession signal."
                if family else None
            ),
            "micro_cluster_flag": _truth(micro),
            "micro_cluster_id": micro["id"] if micro else None,
            "micro_cluster_size": micro["size"] if micro else None,
            "micro_cluster_reasoning": (
                f"{micro['size']} coordinate-enriched practices connected by <= {MICRO_CLUSTER_RADIUS_MI:g} mi neighbor links."
                if micro else None
            ),
            "intel_quant_disagreement_flag": intel_flag,
            "intel_quant_disagreement_type": intel_type,
            "intel_quant_disagreement_reasoning": intel_reason,
            "retirement_combo_score": retirement_score,
            "retirement_combo_flag": _truth(retirement_score >= RETIREMENT_HIGH_THRESHOLD),
            "retirement_combo_reasoning": retirement_reasons.get(npi),
            "deal_catchment_24mo": catchment_count,
            "deal_catchment_reasoning": catchment_reason,
            "last_change_90d_flag": _truth(latest_change and latest_change["within_90d"]),
            "last_change_date": latest_change["date"].isoformat() if latest_change else None,
            "last_change_type": latest_change["type"] if latest_change else None,
            "last_change_reasoning": (
                f"Latest practice_changes event is {latest_change['type']} on {latest_change['date'].isoformat()}."
                if latest_change else None
            ),
            "buyability_pctile_zip_class": buy_zip_pct,
            "buyability_pctile_class": buy_class_pct,
            "retirement_pctile_zip_class": ret_zip_pct,
            "retirement_pctile_class": ret_class_pct,
            "high_peer_buyability_flag": _truth(buy_zip_pct is not None and buy_zip_pct >= 90),
            "high_peer_retirement_flag": _truth(ret_zip_pct is not None and ret_zip_pct >= 90),
            "peer_percentile_reasoning": (
                "Percentiles compare within ZIP + entity_classification and within entity_classification. "
                "Null means insufficient scored peers."
            ),
            "zip_white_space_flag": 0,
            "zip_compound_demand_flag": 0,
            "zip_contested_zone_flag": 0,
            "zip_ada_benchmark_gap_flag": 0,
            "data_limitations": (
                "Derived from watched-ZIP SQLite records. Hours are not present; "
                "deal catchment uses target ZIP/city centroids when exact deal coordinates are absent."
            ),
            "created_at": created_at,
        }
        practice_rows.append(row)
        signals_by_zip[zip_code].append(row)

    zip_rows = []
    for zip_code in sorted(watched):
        wz = watched[zip_code]
        score = zip_scores.get(zip_code, {})
        intel = zip_intel.get(zip_code)
        practice_signals = signals_by_zip.get(zip_code, [])
        population = _as_int(wz.get("population"))

        compound_flag, compound_score, compound_reason = _compound_demand(score, intel)
        mirrors = mirror_pairs.get(zip_code, [])
        top_mirror = mirrors[0] if mirrors else None

        all_deals = deal_count_all.get(zip_code, 0)
        deals_24mo = deal_count_24mo.get(zip_code, 0)
        white_space = all_deals == 0 and (population or 0) >= WHITE_SPACE_POPULATION_THRESHOLD
        white_space_score = 0
        white_parts = []
        if all_deals == 0:
            white_space_score += 50
            white_parts.append("0 exact target_zip deals")
        if (population or 0) >= WHITE_SPACE_POPULATION_THRESHOLD:
            white_space_score += 30
            white_parts.append(f"population {population} >= {WHITE_SPACE_POPULATION_THRESHOLD}")
        corp_frac = _pct_fraction(score.get("corporate_share_pct"))
        if corp_frac is not None and corp_frac < 0.10:
            white_space_score += 20
            white_parts.append(f"corporate_share_pct {corp_frac * 100:.1f}% < 10%")

        contested_platforms = contested_zones.get(zip_code, [])
        contested_flag = len(contested_platforms) >= 2

        state = _clean_text(wz.get("state")).upper()
        ada_row = latest_ada.get(state)
        ada_pct = _as_float(ada_row.get("pct_dso_affiliated")) if ada_row else None
        local_corp_pct = (corp_frac * 100.0) if corp_frac is not None else None
        ada_gap = (ada_pct - local_corp_pct) if ada_pct is not None and local_corp_pct is not None else None
        ada_gap_flag = ada_gap is not None and ada_gap >= 10

        zip_practice_count = len(practice_signals)
        phantom_count = sum(p["phantom_inventory_flag"] for p in practice_signals)
        micro_cluster_ids = {p["micro_cluster_id"] for p in practice_signals if p["micro_cluster_id"]}
        stealth_cluster_ids = {p["stealth_dso_cluster_id"] for p in practice_signals if p["stealth_dso_cluster_id"]}
        catchment_values = [p["deal_catchment_24mo"] or 0 for p in practice_signals]

        row = {
            "zip_code": zip_code,
            "city": wz.get("city") or score.get("city"),
            "state": wz.get("state") or score.get("state"),
            "metro_area": wz.get("metro_area") or score.get("metro_area"),
            "population": population,
            "total_practices": _as_int(score.get("total_practices")) or zip_practice_count,
            "total_gp_locations": _as_int(score.get("total_gp_locations")),
            "total_specialist_locations": _as_int(score.get("total_specialist_locations")),
            "dld_gp_per_10k": _as_float(score.get("dld_gp_per_10k")),
            "people_per_gp_door": _as_int(score.get("people_per_gp_door")),
            "corporate_share_pct": _as_float(score.get("corporate_share_pct")),
            "buyable_practice_ratio": _as_float(score.get("buyable_practice_ratio")),
            "stealth_dso_practice_count": sum(p["stealth_dso_flag"] for p in practice_signals),
            "stealth_dso_cluster_count": len(stealth_cluster_ids),
            "phantom_inventory_count": phantom_count,
            "phantom_inventory_pct": round((phantom_count / zip_practice_count) * 100, 2) if zip_practice_count else 0.0,
            "revenue_default_count": sum(p["revenue_default_flag"] for p in practice_signals),
            "family_dynasty_count": sum(p["family_dynasty_flag"] for p in practice_signals),
            "micro_cluster_count": len(micro_cluster_ids),
            "micro_cluster_practice_count": sum(p["micro_cluster_flag"] for p in practice_signals),
            "intel_quant_disagreement_count": sum(p["intel_quant_disagreement_flag"] for p in practice_signals),
            "retirement_combo_high_count": sum(p["retirement_combo_flag"] for p in practice_signals),
            "last_change_90d_count": sum(p["last_change_90d_flag"] for p in practice_signals),
            "deal_count_all_time": all_deals,
            "deal_count_24mo": deals_24mo,
            "deal_catchment_sum_24mo": sum(catchment_values),
            "deal_catchment_max_24mo": max(catchment_values) if catchment_values else 0,
            "compound_demand_flag": _truth(compound_flag),
            "compound_demand_score": compound_score,
            "compound_demand_reasoning": compound_reason,
            "mirror_pair_flag": _truth(bool(mirrors)),
            "mirror_pair_count": len(mirrors),
            "top_mirror_zip": top_mirror["zip_code"] if top_mirror else None,
            "top_mirror_similarity": top_mirror["similarity"] if top_mirror else None,
            "top_mirror_corporate_gap_pp": top_mirror["corporate_gap_pp"] if top_mirror else None,
            "mirror_zips_json": json.dumps(mirrors) if mirrors else None,
            "mirror_reasoning": (
                f"Top mirror {top_mirror['zip_code']} similarity {top_mirror['similarity']:.2f} "
                f"with {top_mirror['corporate_gap_pp']:.1f} pp corporate-share gap."
                if top_mirror else None
            ),
            "white_space_flag": _truth(white_space),
            "white_space_score": min(100, white_space_score),
            "white_space_reasoning": "; ".join(white_parts) if white_parts else "White-space inputs did not match.",
            "contested_zone_flag": _truth(contested_flag),
            "contested_platform_count": len(contested_platforms),
            "contested_platforms_json": json.dumps(contested_platforms) if contested_platforms else None,
            "contested_zone_reasoning": (
                f"{len(contested_platforms)} corporate platforms each have >=20% estimated GP-location share."
                if contested_flag else "Fewer than two platforms reached 20% estimated GP-location share."
            ),
            "ada_benchmark_pct": ada_pct,
            "ada_benchmark_gap_pp": round(ada_gap, 1) if ada_gap is not None else None,
            "ada_benchmark_gap_flag": _truth(ada_gap_flag),
            "ada_benchmark_reasoning": (
                f"{state} ADA HPI DSO affiliation {ada_pct:.1f}% minus local corporate share {local_corp_pct:.1f}%."
                if ada_gap is not None else "ADA benchmark or local corporate share unavailable."
            ),
            "high_peer_buyability_count": sum(p["high_peer_buyability_flag"] for p in practice_signals),
            "high_peer_retirement_count": sum(p["high_peer_retirement_flag"] for p in practice_signals),
            "data_limitations": (
                "Deal activity uses exact target_zip for white-space counts; city-only deals are excluded from that flag. "
                "Contested zones use available affiliated_dso/parent/franchise labels and address-level counts."
            ),
            "created_at": created_at,
        }
        zip_rows.append(row)

    zip_flags = {row["zip_code"]: row for row in zip_rows}
    for row in practice_rows:
        z = zip_flags.get(row["zip_code"], {})
        row["zip_white_space_flag"] = z.get("white_space_flag", 0)
        row["zip_compound_demand_flag"] = z.get("compound_demand_flag", 0)
        row["zip_contested_zone_flag"] = z.get("contested_zone_flag", 0)
        row["zip_ada_benchmark_gap_flag"] = z.get("ada_benchmark_gap_flag", 0)

    counts = {
        "practice_rows": len(practice_rows),
        "zip_rows": len(zip_rows),
        "stealth_dso_practices": sum(p["stealth_dso_flag"] for p in practice_rows),
        "stealth_dso_clusters": len(stealth_clusters),
        "phantom_inventory_practices": sum(p["phantom_inventory_flag"] for p in practice_rows),
        "retirement_combo_high_practices": sum(p["retirement_combo_flag"] for p in practice_rows),
        "high_disagreement_practices": sum(p["intel_quant_disagreement_flag"] for p in practice_rows),
        "micro_cluster_practices": sum(p["micro_cluster_flag"] for p in practice_rows),
        "micro_clusters": len(micro_clusters),
        "white_space_zips": sum(z["white_space_flag"] for z in zip_rows),
        "compound_demand_zips": sum(z["compound_demand_flag"] for z in zip_rows),
        "mirror_pair_zips": sum(z["mirror_pair_flag"] for z in zip_rows),
        "contested_zips": sum(z["contested_zone_flag"] for z in zip_rows),
        "ada_gap_zips": sum(z["ada_benchmark_gap_flag"] for z in zip_rows),
    }

    return practice_rows, zip_rows, counts


def print_summary(counts, dry_run):
    prefix = "DRY RUN - no writes" if dry_run else "MATERIALIZED"
    print(prefix)
    print(f"practice_signals rows: {counts['practice_rows']:,}")
    print(f"zip_signals rows:      {counts['zip_rows']:,}")
    print()
    print("Signal counts:")
    for key in [
        "stealth_dso_practices",
        "stealth_dso_clusters",
        "phantom_inventory_practices",
        "retirement_combo_high_practices",
        "high_disagreement_practices",
        "micro_cluster_practices",
        "micro_clusters",
        "white_space_zips",
        "compound_demand_zips",
        "mirror_pair_zips",
        "contested_zips",
        "ada_gap_zips",
    ]:
        print(f"  {key}: {counts[key]:,}")


def run(db_path=DB_PATH, dry_run=False):
    start_time = log_scrape_start("compute_signals")
    try:
        conn = _connect(db_path)
        try:
            practice_rows, zip_rows, counts = compute_signal_rows(conn)
            if not dry_run:
                _materialize(conn, practice_rows, zip_rows)
                log.info(
                    "Materialized %d practice_signals and %d zip_signals rows",
                    len(practice_rows),
                    len(zip_rows),
                )
            else:
                log.info(
                    "Dry run computed %d practice_signals and %d zip_signals rows",
                    len(practice_rows),
                    len(zip_rows),
                )
            print_summary(counts, dry_run=dry_run)
        finally:
            conn.close()

        log_scrape_complete(
            "compute_signals",
            start_time,
            new_records=0 if dry_run else counts["practice_rows"] + counts["zip_rows"],
            summary=(
                "compute_signals dry run complete"
                if dry_run
                else "compute_signals materialization complete"
            ),
            extra=counts,
        )
        return counts
    except Exception as exc:
        log.exception("compute_signals failed")
        log_scrape_error("compute_signals", str(exc), start_time)
        raise


def main():
    parser = argparse.ArgumentParser(description="Materialize Warroom derived signal tables.")
    parser.add_argument("--db-path", default=DB_PATH, help="Path to SQLite database.")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print counts without writes.")
    args = parser.parse_args()
    run(db_path=args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
