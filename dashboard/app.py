"""
Dental PE Consolidation Intelligence Dashboard
5-page consulting-grade analytics platform.
"""

import os
import sys
import glob as globmod
from datetime import date, datetime, timedelta

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Add project root to path (works locally and on Streamlit Cloud)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from sqlalchemy import func, text
from scrapers.database import (
    get_engine, get_session, table_exists,
    Deal, Practice, PracticeChange, PESponsor, Platform,
    WatchedZip, DSOLocation, ADAHPIBenchmark, ZipOverview,
    insert_deal, insert_or_update_practice, log_practice_change,
    DB_PATH,
)

LOGS_DIR = os.path.join(_project_root, "logs")

# ═══════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
    --bg-primary: #0B0E11; --bg-card: #141922; --bg-card-hover: #1A2332;
    --border: #1E2A3A; --border-hover: #2A3A4A;
    --accent-blue: #0066FF; --accent-green: #00C853; --accent-red: #FF3D00;
    --accent-amber: #FFB300; --accent-purple: #9C27B0; --accent-cyan: #00BCD4;
    --text-primary: #E8ECF1; --text-secondary: #8892A0; --text-muted: #566070;
}
body, .stApp { font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.88rem; }
.stApp [data-testid="stSidebar"] { font-size: 0.84rem; }
.kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1rem 1.2rem; box-shadow: 0 2px 4px rgba(0,0,0,0.3); transition: border-color 0.2s, transform 0.2s; }
.kpi-card:hover { border-color: var(--border-hover); transform: translateY(-1px); }
.kpi-number { font-family: 'JetBrains Mono', monospace; font-size: 1.7rem; font-weight: 600; color: var(--text-primary); }
.kpi-label { font-family: 'DM Sans', sans-serif; font-size: 0.78rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.03em; }
.kpi-delta-up { color: var(--accent-green); font-size: 0.8rem; }
.kpi-delta-down { color: var(--accent-red); font-size: 0.8rem; }
.section-header { font-family: 'DM Sans'; font-weight: 600; font-size: 0.95rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.05em; margin-top: 1.5rem; padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--border); }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.status-green { background: var(--accent-green); } .status-yellow { background: var(--accent-amber); }
.status-red { background: var(--accent-red); } .status-gray { background: var(--text-muted); }
#MainMenu {visibility: hidden;} footer {visibility: hidden;}
.sidebar-footer { font-size: 0.7rem; color: var(--text-muted); margin-top: 2rem; text-align: center; }
/* Tooltip system — CSS-only popover on hover */
.help-tip { display: inline-block; cursor: help; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 50%; width: 18px; height: 18px; text-align: center; font-size: 0.65rem; line-height: 18px;
  color: var(--text-secondary); margin-left: 6px; vertical-align: middle; position: relative; }
.help-tip:hover { border-color: var(--accent-blue); color: var(--accent-blue); }
.help-tip .tip-text { visibility: hidden; opacity: 0; position: absolute; z-index: 999;
  bottom: 130%; left: 50%; transform: translateX(-50%); width: 260px;
  background: #1A2332; border: 1px solid var(--border-hover); border-radius: 8px;
  padding: 0.6rem 0.8rem; font-size: 0.78rem; line-height: 1.4; color: var(--text-primary);
  box-shadow: 0 4px 12px rgba(0,0,0,0.5); transition: opacity 0.15s; pointer-events: none;
  font-family: 'DM Sans', sans-serif; text-transform: none; letter-spacing: normal; font-weight: 400; }
.help-tip:hover .tip-text { visibility: visible; opacity: 1; }
/* Reduce Streamlit default padding/spacing */
.stApp [data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
h1 { font-size: 1.6rem !important; margin-bottom: 0.5rem !important; }
h2 { font-size: 1.2rem !important; }
h3 { font-size: 1rem !important; }
</style>
"""

dental_dark_template = dict(layout=dict(
    paper_bgcolor="#0B0E11", plot_bgcolor="#141922",
    font=dict(color="#E8ECF1", family="DM Sans"),
    colorway=["#0066FF","#00C853","#FFB300","#9C27B0","#00BCD4","#FF3D00","#7C4DFF","#FF6D00","#00E5FF","#EEFF41"],
    xaxis=dict(gridcolor="#1E2A3A", linecolor="#1E2A3A", zerolinecolor="#1E2A3A"),
    yaxis=dict(gridcolor="#1E2A3A", linecolor="#1E2A3A", zerolinecolor="#1E2A3A"),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#8892A0")),
    hoverlabel=dict(bgcolor="#1A2332", bordercolor="#2A3A4A", font=dict(color="white")),
))

DEAL_TYPE_COLORS = {"buyout": "#0066FF", "add-on": "#00C853", "recapitalization": "#FFB300",
                    "growth": "#9C27B0", "de_novo": "#00BCD4", "partnership": "#7C4DFF", "other": "#566070"}

US_STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA",
             "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM",
             "NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]

# ZIP centroids for watched ZIPs (used for map plotting) — 289 entries via pgeocode
ZIP_CENTROIDS = {
    # ── CHICAGOLAND_ZIPS (original 28 - Naperville/DuPage/Will corridor) ──
    "60491": (41.6, -87.96), "60439": (41.71, -87.98), "60441": (41.59, -88.05),
    "60540": (41.77, -88.14), "60564": (41.7, -88.2), "60565": (41.73, -88.13),
    "60563": (41.79, -88.17), "60527": (41.74, -87.93), "60515": (41.8, -88.01),
    "60516": (41.76, -88.02), "60532": (41.79, -88.09), "60559": (41.77, -87.98),
    "60514": (41.8, -87.96), "60521": (41.8, -87.93), "60523": (41.84, -87.96),
    "60148": (41.87, -88.02), "60440": (41.7, -88.09), "60490": (41.68, -88.14),
    "60504": (41.75, -88.25), "60502": (41.78, -88.26), "60431": (41.47, -87.94),
    "60435": (41.55, -88.13), "60586": (41.56, -88.22), "60585": (41.66, -88.22),
    "60503": (41.72, -88.25), "60554": (41.77, -88.44), "60543": (41.68, -88.35),
    "60560": (41.64, -88.44),
    # ── CHI_NORTH_ZIPS (North Shore + North suburbs) ──
    "60004": (42.11, -87.98), "60005": (42.06, -87.99), "60007": (42.01, -87.99),
    "60008": (42.07, -88.02), "60010": (42.16, -88.14), "60015": (42.17, -87.86),
    "60016": (42.05, -87.89), "60017": (42.03, -87.89), "60018": (42.02, -87.87),
    "60022": (42.13, -87.76), "60025": (42.08, -87.82), "60026": (42.07, -87.79),
    "60035": (42.18, -87.81), "60037": (42.21, -87.81), "60038": (42.1, -88.01),
    "60040": (42.2, -87.81), "60045": (42.24, -87.85), "60053": (42.04, -87.79),
    "60056": (42.06, -87.94), "60061": (42.23, -87.97), "60062": (42.13, -87.85),
    "60067": (42.11, -88.04), "60068": (42.01, -87.84), "60069": (42.2, -87.93),
    "60070": (42.11, -87.94), "60074": (42.15, -88.02), "60076": (42.04, -87.73),
    "60077": (42.03, -87.75), "60089": (42.16, -87.96), "60090": (42.13, -87.93),
    "60091": (42.08, -87.72), "60093": (42.11, -87.75), "60201": (42.05, -87.69),
    "60202": (42.03, -87.69), "60203": (42.05, -87.72), "60712": (42.01, -87.74),
    "60714": (42.03, -87.81),
    # ── CHI_CITY_ZIPS (Chicago city proper) ──
    "60601": (41.89, -87.62), "60602": (41.88, -87.63), "60603": (41.88, -87.63),
    "60604": (41.88, -87.63), "60605": (41.87, -87.63), "60606": (41.89, -87.64),
    "60607": (41.87, -87.66), "60608": (41.85, -87.67), "60609": (41.81, -87.65),
    "60610": (41.9, -87.63), "60611": (41.9, -87.62), "60612": (41.88, -87.69),
    "60613": (41.95, -87.66), "60614": (41.92, -87.65), "60615": (41.8, -87.6),
    "60616": (41.84, -87.63), "60617": (41.73, -87.56), "60618": (41.95, -87.7),
    "60619": (41.75, -87.61), "60620": (41.74, -87.65), "60621": (41.78, -87.64),
    "60622": (41.9, -87.68), "60623": (41.85, -87.72), "60624": (41.88, -87.72),
    "60625": (41.97, -87.7), "60626": (42.01, -87.67), "60628": (41.69, -87.62),
    "60629": (41.78, -87.71), "60630": (41.97, -87.76), "60631": (42.0, -87.81),
    "60632": (41.81, -87.71), "60633": (41.66, -87.56), "60634": (41.95, -87.81),
    "60636": (41.78, -87.67), "60637": (41.78, -87.61), "60638": (41.78, -87.77),
    "60639": (41.92, -87.75), "60640": (41.97, -87.66), "60641": (41.95, -87.75),
    "60642": (41.9, -87.65), "60643": (41.7, -87.66), "60644": (41.88, -87.76),
    "60645": (42.01, -87.69), "60646": (41.99, -87.76), "60647": (41.92, -87.7),
    "60649": (41.76, -87.57), "60651": (41.9, -87.74), "60652": (41.75, -87.71),
    "60653": (41.82, -87.61), "60654": (41.89, -87.64), "60655": (41.69, -87.7),
    "60656": (41.97, -87.87), "60657": (41.94, -87.65), "60659": (42.0, -87.72),
    "60660": (41.99, -87.66), "60661": (41.88, -87.64),
    # ── CHI_SOUTH_ZIPS (South suburbs) ──
    "60406": (41.66, -87.68), "60409": (41.62, -87.55), "60411": (41.51, -87.59),
    "60412": (41.51, -87.64), "60415": (41.7, -87.78), "60418": (41.64, -87.74),
    "60419": (41.63, -87.6), "60422": (41.54, -87.68), "60423": (41.51, -87.82),
    "60425": (41.55, -87.61), "60426": (41.61, -87.65), "60428": (41.6, -87.69),
    "60429": (41.57, -87.68), "60430": (41.56, -87.66), "60438": (41.57, -87.54),
    "60442": (41.43, -87.98), "60443": (41.51, -87.74), "60445": (41.64, -87.74),
    "60449": (41.42, -87.77), "60452": (41.61, -87.75), "60453": (41.71, -87.75),
    "60454": (41.81, -87.69), "60455": (41.74, -87.81), "60456": (41.73, -87.73),
    "60457": (41.73, -87.83), "60458": (41.74, -87.83), "60459": (41.74, -87.77),
    "60461": (41.51, -87.67), "60462": (41.62, -87.84), "60463": (41.66, -87.79),
    "60464": (41.66, -87.85), "60465": (41.7, -87.83), "60466": (41.48, -87.68),
    "60467": (41.6, -87.89), "60468": (41.34, -87.79), "60469": (41.63, -87.69),
    "60471": (41.48, -87.72), "60472": (41.64, -87.71), "60473": (41.6, -87.59),
    "60475": (41.47, -87.64), "60476": (41.57, -87.61), "60477": (41.58, -87.8),
    "60478": (41.56, -87.72), "60480": (41.74, -87.88), "60481": (41.31, -88.15),
    "60482": (41.69, -87.79), "60484": (41.44, -87.71), "60487": (41.56, -87.83),
    "60501": (41.78, -87.82), "60803": (41.67, -87.74), "60804": (41.84, -87.76),
    "60805": (41.72, -87.7), "60827": (41.65, -87.63),
    # ── CHI_WEST_ZIPS (Inner west suburbs) ──
    "60101": (41.93, -88.01), "60103": (41.98, -88.21), "60104": (41.88, -87.88),
    "60106": (41.95, -87.94), "60107": (42.02, -88.17), "60108": (41.95, -88.08),
    "60126": (41.89, -87.94), "60130": (41.87, -87.81), "60131": (41.93, -87.87),
    "60133": (42.0, -88.15), "60137": (41.87, -88.06), "60138": (41.88, -88.07),
    "60139": (41.92, -88.08), "60143": (41.97, -88.02), "60153": (41.88, -87.84),
    "60154": (41.85, -87.88), "60155": (41.86, -87.86), "60160": (41.9, -87.86),
    "60161": (41.9, -87.86), "60162": (41.87, -87.9), "60163": (41.89, -87.91),
    "60164": (41.92, -87.89), "60165": (41.9, -87.88), "60171": (41.93, -87.84),
    "60176": (41.96, -87.87), "60181": (41.88, -87.98), "60187": (41.87, -88.11),
    "60188": (41.92, -88.14), "60189": (41.84, -88.09), "60190": (41.87, -88.15),
    "60191": (41.96, -87.98), "60193": (42.01, -88.09), "60194": (42.03, -88.12),
    "60195": (42.08, -88.11), "60301": (41.89, -87.8), "60302": (41.89, -87.79),
    "60304": (41.87, -87.79), "60305": (41.9, -87.82), "60402": (41.83, -87.79),
    "60513": (41.82, -87.85), "60525": (41.78, -87.87), "60526": (41.83, -87.87),
    "60534": (41.81, -87.82), "60546": (41.84, -87.82), "60555": (41.83, -88.19),
    "60558": (41.8, -87.9), "60706": (41.96, -87.82), "60707": (41.92, -87.82),
    # ── CHI_FAR_WEST_ZIPS (Aurora, Elgin, Batavia, Geneva) ──
    "60110": (42.12, -88.26), "60118": (42.1, -88.29), "60119": (41.88, -88.46),
    "60120": (42.04, -88.26), "60121": (42.04, -88.28), "60122": (42.07, -88.3),
    "60123": (42.04, -88.32), "60124": (42.03, -88.37), "60134": (41.89, -88.31),
    "60144": (41.84, -88.52), "60151": (41.92, -88.6), "60172": (41.98, -88.09),
    "60173": (42.06, -88.05), "60174": (41.92, -88.31), "60175": (41.95, -88.39),
    "60185": (41.89, -88.2), "60186": (41.88, -88.2), "60505": (41.76, -88.3),
    "60506": (41.77, -88.34), "60510": (41.85, -88.31), "60511": (41.76, -88.54),
    "60512": (41.7, -88.44), "60519": (41.78, -88.24), "60536": (41.6, -88.55),
    "60537": (41.56, -88.6), "60538": (41.72, -88.33), "60539": (41.82, -88.33),
    "60541": (41.53, -88.53), "60542": (41.81, -88.33), "60544": (41.6, -88.2),
    "60545": (41.67, -88.54), "60548": (41.64, -88.64),
    # ── CHI_FAR_SOUTH_ZIPS (Joliet extended, Frankfort) ──
    "60403": (41.55, -88.1), "60404": (41.51, -88.22), "60410": (41.43, -88.21),
    "60416": (41.29, -88.28), "60421": (41.43, -88.09), "60432": (41.54, -88.06),
    "60433": (41.51, -88.06), "60434": (41.53, -88.08), "60436": (41.49, -88.16),
    "60446": (41.64, -88.07), "60447": (41.46, -88.28), "60448": (41.53, -87.89),
    "60450": (41.37, -88.42), "60451": (41.51, -87.96),
    # ── BOSTON_ZIPS ──
    "02116": (42.35, -71.08), "02115": (42.34, -71.09), "02118": (42.34, -71.07),
    "02119": (42.33, -71.1), "02120": (42.33, -71.09), "02215": (42.35, -71.1),
    "02134": (42.35, -71.13), "02135": (42.35, -71.16), "02446": (42.34, -71.12),
    "02445": (42.33, -71.13), "02467": (42.32, -71.16), "02459": (42.33, -71.18),
    "02458": (42.35, -71.19), "02453": (42.37, -71.23), "02451": (42.4, -71.25),
    "02138": (42.38, -71.13), "02139": (42.36, -71.1), "02140": (42.39, -71.13),
    "02141": (42.37, -71.08), "02142": (42.36, -71.08), "02144": (42.4, -71.12),
}
METRO_CENTERS = {
    "Chicagoland": {"lat": 41.72, "lon": -88.10, "zoom": 10},
    "Boston Metro": {"lat": 42.35, "lon": -71.13, "zoom": 11},
}

# ── Living Locations for Job Market page ──────────────────────────────────
# ZIP lists from scrapers/data_axle_exporter.py zones, deduplicated via Python
LIVING_LOCATIONS = {
    "West Loop / South Loop": {
        "center_zip": "60607", "center_lat": 41.88, "center_lon": -87.64,
        "commutable_zips": [  # 142 ZIPs: CHI_CITY + CHI_NORTH + CHI_WEST
            "60004", "60005", "60007", "60008", "60010", "60015", "60016", "60017",
            "60018", "60022", "60025", "60026", "60035", "60037", "60038", "60040",
            "60045", "60053", "60056", "60061", "60062", "60067", "60068", "60069",
            "60070", "60074", "60076", "60077", "60089", "60090", "60091", "60093",
            "60101", "60103", "60104", "60106", "60107", "60108", "60126", "60130",
            "60131", "60133", "60137", "60138", "60139", "60143", "60153", "60154",
            "60155", "60160", "60161", "60162", "60163", "60164", "60165", "60171",
            "60176", "60181", "60187", "60188", "60189", "60190", "60191", "60193",
            "60194", "60195", "60201", "60202", "60203", "60301", "60302", "60304",
            "60305", "60402", "60501", "60513", "60525", "60526", "60534", "60546",
            "60555", "60558", "60601", "60602", "60603", "60604", "60605", "60606",
            "60607", "60608", "60609", "60610", "60611", "60612", "60613", "60614",
            "60615", "60616", "60617", "60618", "60619", "60620", "60621", "60622",
            "60623", "60624", "60625", "60626", "60628", "60629", "60630", "60631",
            "60632", "60633", "60634", "60636", "60637", "60638", "60639", "60640",
            "60641", "60642", "60643", "60644", "60645", "60646", "60647", "60649",
            "60651", "60652", "60653", "60654", "60655", "60656", "60657", "60659",
            "60660", "60661", "60706", "60707", "60712", "60714",
        ],
    },
    "Woodridge": {
        "center_zip": "60517", "center_lat": 41.75, "center_lon": -88.05,
        "commutable_zips": [  # 129 ZIPs: CHICAGOLAND_28 + CHI_SOUTH + CHI_WEST
            "60101", "60103", "60104", "60106", "60107", "60108", "60126", "60130",
            "60131", "60133", "60137", "60138", "60139", "60143", "60148", "60153",
            "60154", "60155", "60160", "60161", "60162", "60163", "60164", "60165",
            "60171", "60176", "60181", "60187", "60188", "60189", "60190", "60191",
            "60193", "60194", "60195", "60301", "60302", "60304", "60305", "60402",
            "60406", "60409", "60411", "60412", "60415", "60418", "60419", "60422",
            "60423", "60425", "60426", "60428", "60429", "60430", "60431", "60435",
            "60438", "60439", "60440", "60441", "60442", "60443", "60445", "60449",
            "60452", "60453", "60454", "60455", "60456", "60457", "60458", "60459",
            "60461", "60462", "60463", "60464", "60465", "60466", "60467", "60468",
            "60469", "60471", "60472", "60473", "60475", "60476", "60477", "60478",
            "60480", "60481", "60482", "60484", "60487", "60490", "60491", "60501",
            "60502", "60503", "60504", "60513", "60514", "60515", "60516", "60521",
            "60523", "60525", "60526", "60527", "60532", "60534", "60540", "60543",
            "60546", "60554", "60555", "60558", "60559", "60560", "60563", "60564",
            "60565", "60585", "60586", "60706", "60707", "60803", "60804", "60805",
            "60827",
        ],
    },
    "Bolingbrook": {
        "center_zip": "60440", "center_lat": 41.70, "center_lon": -88.07,
        "commutable_zips": [  # 127 ZIPs: CHICAGOLAND_28 + CHI_SOUTH + CHI_FAR_SOUTH + CHI_FAR_WEST
            "60110", "60118", "60119", "60120", "60121", "60122", "60123", "60124",
            "60134", "60144", "60148", "60151", "60172", "60173", "60174", "60175",
            "60185", "60186", "60403", "60404", "60406", "60409", "60410", "60411",
            "60412", "60415", "60416", "60418", "60419", "60421", "60422", "60423",
            "60425", "60426", "60428", "60429", "60430", "60431", "60432", "60433",
            "60434", "60435", "60436", "60438", "60439", "60440", "60441", "60442",
            "60443", "60445", "60446", "60447", "60448", "60449", "60450", "60451",
            "60452", "60453", "60454", "60455", "60456", "60457", "60458", "60459",
            "60461", "60462", "60463", "60464", "60465", "60466", "60467", "60468",
            "60469", "60471", "60472", "60473", "60475", "60476", "60477", "60478",
            "60480", "60481", "60482", "60484", "60487", "60490", "60491", "60501",
            "60502", "60503", "60504", "60505", "60506", "60510", "60511", "60512",
            "60514", "60515", "60516", "60519", "60521", "60523", "60527", "60532",
            "60536", "60537", "60538", "60539", "60540", "60541", "60542", "60543",
            "60544", "60545", "60548", "60554", "60559", "60560", "60563", "60564",
            "60565", "60585", "60586", "60803", "60804", "60805", "60827",
        ],
    },
}


def help_tip(text):
    """Inline ? icon with a CSS popover tooltip on hover."""
    safe = text.replace('"', '&quot;').replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<span class="help-tip">?<span class="tip-text">{safe}</span></span>'


def section_header(title, help_text=None):
    """Section header with optional ? tooltip."""
    tip = help_tip(help_text) if help_text else ""
    return f'<div class="section-header">{title}{tip}</div>'


def format_status(val):
    """Format ownership status with color icon."""
    icons = {
        "independent": ("🟢", "Independent"),
        "likely_independent": ("🟢", "Likely Independent"),
        "dso_affiliated": ("🟡", "DSO Affiliated"),
        "pe_backed": ("🔴", "PE-Backed"),
        "unknown": ("⚪", "Unknown"),
    }
    icon, label = icons.get(val, ("⚪", str(val) if val else "Unknown"))
    return f"{icon} {label}"


def clean_dataframe(df):
    """Clean a DataFrame for display: fill NaN, rename columns."""
    df = df.fillna("—")
    renames = {
        "practice_name": "Practice Name", "npi": "NPI", "entity_type": "Entity Type",
        "ownership_status": "Status", "affiliated_dso": "Affiliated DSO",
        "affiliated_pe_sponsor": "PE Sponsor", "deal_date": "Date",
        "platform_company": "Platform", "pe_sponsor": "PE Sponsor",
        "target_name": "Target", "target_state": "State", "deal_type": "Type",
        "specialty": "Specialty", "deal_size_mm": "Deal Size ($M)",
        "source": "Source", "source_url": "Source URL", "num_locations": "Locations",
        "change_date": "Date", "field_changed": "Field", "old_value": "Old",
        "new_value": "New", "change_type": "Change Type", "city": "City",
        "zip": "ZIP", "notes": "Notes",
    }
    df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})
    return df


def make_kpi_card(icon, label, value, delta=None, delta_pct=None):
    if isinstance(value, (int, float)):
        fv = f"{value:,}" if isinstance(value, int) else f"{value:,.1f}"
    else:
        fv = str(value)
    dh = ""
    if delta is not None:
        arrow = "▲" if delta >= 0 else "▼"
        cls = "kpi-delta-up" if delta >= 0 else "kpi-delta-down"
        dt = f"{arrow} {abs(delta):,.0f}" if isinstance(delta, (int, float)) else f"{arrow} {delta}"
        if delta_pct is not None:
            dt += f" ({delta_pct:+.1f}%)"
        dh = f'<div class="{cls}">{dt}</div>'
    return f'<div class="kpi-card"><div style="font-size:1.5rem;margin-bottom:0.3rem">{icon}</div><div class="kpi-number">{fv}</div><div class="kpi-label">{label}</div>{dh}</div>'


def compute_job_opportunity_score(df):
    """Add 'job_opp_score' column (0-100) based on job opportunity signals."""
    df = df.copy()
    scores = pd.Series(0, index=df.index, dtype=int)
    status = df["ownership_status"].fillna("unknown").str.strip().str.lower()
    scores += status.eq("independent").astype(int) * 30
    scores += status.isin(["unknown", ""]).astype(int) * 10
    buy = pd.to_numeric(df.get("buyability_score"), errors="coerce")
    scores += (buy >= 70).astype(int) * 25 + ((buy >= 50) & (buy < 70)).astype(int) * 15
    emp = pd.to_numeric(df.get("employee_count"), errors="coerce")
    scores += (emp >= 10).astype(int) * 20 + ((emp >= 5) & (emp < 10)).astype(int) * 10
    yr = pd.to_numeric(df.get("year_established"), errors="coerce")
    scores += (yr >= 2021).astype(int) * 15 + ((yr >= 2016) & (yr < 2021)).astype(int) * 8
    df["job_opp_score"] = scores
    return df


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING (cached)
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800)
def load_deals():
    s = get_session()
    try:
        df = pd.read_sql(s.query(Deal).statement, s.bind)
        if "deal_date" in df.columns:
            df["deal_date"] = pd.to_datetime(df["deal_date"], errors="coerce")
        return df
    finally:
        s.close()

@st.cache_data(ttl=3600)
def load_watched_zips():
    s = get_session()
    try:
        return pd.read_sql(s.query(WatchedZip).statement, s.bind)
    finally:
        s.close()

@st.cache_data(ttl=3600)
def load_zip_scores():
    if not table_exists("zip_scores"):
        return pd.DataFrame()
    s = get_session()
    try:
        df = pd.read_sql(text("SELECT * FROM zip_scores"), s.bind)
        return df.drop_duplicates(subset=["zip_code"], keep="last") if not df.empty else df
    finally:
        s.close()

@st.cache_data(ttl=1800)
def load_practices_for_zone(zip_tuple):
    """Load all practices for a set of ZIP codes (cached, uses tuple for hashability)."""
    s = get_session()
    try:
        zip_list = list(zip_tuple)
        placeholders = ", ".join([f":z{i}" for i in range(len(zip_list))])
        params = {f"z{i}": z for i, z in enumerate(zip_list)}
        return pd.read_sql(text(
            f"SELECT * FROM practices WHERE zip IN ({placeholders})"
        ), s.bind, params=params)
    finally:
        s.close()

def get_data_freshness():
    """Get last import date and practice counts for the 'last updated' banner."""
    s = get_session()
    try:
        total = s.execute(text("SELECT COUNT(*) FROM practices")).scalar()
        da_count = s.execute(text("SELECT COUNT(DISTINCT import_batch_id) FROM practices WHERE import_batch_id LIKE 'DA_%'")).scalar()
        da_practices = s.execute(text("SELECT COUNT(*) FROM practices WHERE import_batch_id LIKE 'DA_%'")).scalar()
        # Get most recent update timestamp from the DB file itself
        db_mtime = datetime.fromtimestamp(os.path.getmtime(DB_PATH))
        # Get latest pipeline log timestamp
        latest_log = None
        log_path = os.path.join(LOGS_DIR, "pipeline_events.jsonl")
        if os.path.exists(log_path):
            import json
            with open(log_path) as f:
                lines = f.readlines()
            for line in reversed(lines):
                try:
                    evt = json.loads(line.strip())
                    if "timestamp" in evt:
                        latest_log = evt["timestamp"][:16].replace("T", " ")
                        break
                except Exception:
                    continue
        return {
            "total_practices": total,
            "da_enriched": da_practices,
            "da_batches": da_count,
            "db_updated": db_mtime.strftime("%b %d, %Y at %I:%M %p"),
            "last_pipeline": latest_log,
        }
    finally:
        s.close()

@st.cache_data(ttl=3600)
def load_ada_hpi():
    if not table_exists("ada_hpi_benchmarks"):
        return pd.DataFrame()
    s = get_session()
    try:
        return pd.read_sql(s.query(ADAHPIBenchmark).statement, s.bind)
    finally:
        s.close()

def get_filtered_deals(df):
    """Apply sidebar filters to deals DataFrame."""
    if df.empty:
        return df
    f = df.copy()
    if "deal_date" in f.columns:
        f["deal_date"] = pd.to_datetime(f["deal_date"], errors="coerce")
        start = st.session_state.get("filter_date_start", date(2020, 1, 1))
        end = st.session_state.get("filter_date_end", date.today())
        f = f[(f["deal_date"] >= pd.Timestamp(start)) & (f["deal_date"] <= pd.Timestamp(end))]
    for key, col in [("filter_deal_types", "deal_type"), ("filter_sponsors", "pe_sponsor"),
                     ("filter_platforms", "platform_company"), ("filter_states", "target_state"),
                     ("filter_specialties", "specialty"), ("filter_sources", "source")]:
        vals = st.session_state.get(key, [])
        if vals and col in f.columns:
            f = f[f[col].isin(vals)]
    return f


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════

def render_sidebar():
    with st.sidebar:
        # Status badge
        log_files = sorted(globmod.glob(os.path.join(LOGS_DIR, "*.log")))
        if log_files:
            mtime = datetime.fromtimestamp(os.path.getmtime(log_files[-1]))
            st.markdown(f"<span class='status-dot status-green'></span> **System Online** — last refresh {mtime.strftime('%b %d %H:%M')}", unsafe_allow_html=True)
        else:
            st.markdown("<span class='status-dot status-gray'></span> No data loaded yet", unsafe_allow_html=True)

        st.divider()
        deals_df = load_deals()

        # Date range
        st.markdown(f'**Date Range** {help_tip("Only show deals that happened within this date window. Affects all pages.")}', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.date_input("Start", value=date(2020, 1, 1), key="filter_date_start")
        with c2:
            st.date_input("End", value=date.today(), key="filter_date_end")

        # Deal type
        st.markdown(f'**Deal Type** {help_tip("Buyout = PE firm buys a dental company outright. Add-on = PE-owned platform acquires another practice. Recap = refinancing/dividend. Growth = expansion capital. De Novo = brand new office opened.")}', unsafe_allow_html=True)
        all_types = ["buyout", "add-on", "recapitalization", "growth", "de_novo", "partnership", "other"]
        st.multiselect("Deal Type", all_types, default=all_types, key="filter_deal_types", label_visibility="collapsed")

        # PE Sponsor
        st.markdown(f'**PE Sponsor** {help_tip("The private equity firm funding the deal. Examples: KKR (owns Heartland Dental), Charlesbank (owns MB2). Filter to one firm to see all their dental activity.")}', unsafe_allow_html=True)
        sponsors = sorted(deals_df["pe_sponsor"].dropna().unique().tolist()) if not deals_df.empty else []
        st.multiselect("PE Sponsor", sponsors, key="filter_sponsors", label_visibility="collapsed")

        # Platform
        st.markdown(f'**Platform** {help_tip("The dental company (DSO) making acquisitions. Examples: Heartland Dental, Aspen Dental, MB2. A platform is backed by a PE sponsor and buys individual practices.")}', unsafe_allow_html=True)
        platforms = sorted(deals_df["platform_company"].dropna().unique().tolist()) if not deals_df.empty else []
        st.multiselect("Platform", platforms, key="filter_platforms", label_visibility="collapsed")

        # State
        st.markdown(f'**State** {help_tip("Filter deals by the state where the target practice is located. Select IL for Illinois or MA for Massachusetts to see activity in your markets.")}', unsafe_allow_html=True)
        states = sorted(deals_df["target_state"].dropna().unique().tolist()) if not deals_df.empty else []
        st.multiselect("State", states, key="filter_states", label_visibility="collapsed")

        # Specialty
        st.markdown(f'**Specialty** {help_tip("The dental specialty of the target practice. General = family dentistry (most common). Oral surgery and orthodontics are the most PE-active specialties.")}', unsafe_allow_html=True)
        specs = ["general", "orthodontics", "oral_surgery", "endodontics", "periodontics", "pediatric", "prosthodontics", "multi_specialty", "other"]
        st.multiselect("Specialty", specs, key="filter_specialties", label_visibility="collapsed")

        # Source
        st.markdown(f'**Data Source** {help_tip("Where the deal data came from. PitchBook = financial database with deal sizes. PESP = PE deal announcements. GDN = DSO deal roundups. Multiple sources improve coverage.")}', unsafe_allow_html=True)
        st.multiselect("Data Source", ["pitchbook", "pesp", "gdn"], key="filter_sources", label_visibility="collapsed")

        def _reset_filters():
            for k in ["filter_deal_types", "filter_sponsors", "filter_platforms", "filter_states", "filter_specialties", "filter_sources"]:
                st.session_state[k] = []
            st.session_state["filter_date_start"] = date(2020, 1, 1)
            st.session_state["filter_date_end"] = date.today()
        st.button("🔄 Reset All Filters", on_click=_reset_filters)

        st.markdown("---")
        with st.expander("❓ How to use this dashboard"):
            st.markdown("""
**This dashboard tracks private equity consolidation in U.S. dentistry.**

**Sidebar filters** narrow down the data shown on every page:
- **Date Range**: Only show deals within these dates
- **Deal Type**: Buyout = full purchase, Add-on = bolt-on acquisition to existing platform
- **PE Sponsor**: The private equity firm funding the deal
- **Platform**: The dental company making the acquisition (DSO)
- **State/Specialty/Source**: Further filtering

**Pages:**
- **Deal Flow**: Overview of all PE deals — charts, maps, recent activity
- **Market Intelligence**: Your watched ZIP codes — who owns what in your neighborhoods
- **Buyability Scanner**: Score practices by acquisition likelihood (needs Data Axle data)
- **Job Market**: Job opportunity signals near your planned living locations — practice scoring, ownership maps, DSO landscape
- **Research Tools**: Deep-dive into specific sponsors, platforms, states + SQL explorer
- **System Health**: Data freshness, completeness, manual entry forms
            """)
        st.markdown('<div class="sidebar-footer">Built by Sully | BU GSDM \'27</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 1: DEAL FLOW
# ═══════════════════════════════════════════════════════════════════════════

def page_deal_flow():
    deals_raw = load_deals()
    df = get_filtered_deals(deals_raw)

    # Header
    total = len(df)
    sources = df["source"].nunique() if not df.empty else 0
    st.markdown(f"""
    <div style="margin-bottom:1.5rem">
        <h1 style="font-family:'DM Sans';font-weight:700;margin-bottom:0">Dental PE Consolidation Intelligence</h1>
        <p style="color:var(--text-secondary);margin-top:0.2rem">Real-time tracking of private equity activity in U.S. dentistry</p>
        <p style="color:var(--text-muted);font-size:0.8rem">{total:,} deals | {sources} sources | Filtered view</p>
    </div>""", unsafe_allow_html=True)

    if df.empty:
        st.info("No deals match current filters. Adjust the sidebar filters or run the scrapers.")
        return

    # KPIs — safe date filtering (handle NaT)
    now = date.today()
    has_dates = "deal_date" in df.columns and df["deal_date"].notna().any()
    this_year = df[df["deal_date"].dt.year == now.year] if has_dates else pd.DataFrame()
    last_year = df[df["deal_date"].dt.year == now.year - 1] if has_dates else pd.DataFrame()
    ytd_last = last_year[last_year["deal_date"].dt.dayofyear <= now.timetuple().tm_yday] if not last_year.empty else pd.DataFrame()

    sponsors_now = this_year["pe_sponsor"].nunique() if not this_year.empty else 0
    sponsors_prev = last_year["pe_sponsor"].nunique() if not last_year.empty else 0
    plats_now = this_year["platform_company"].nunique() if not this_year.empty else 0
    plats_prev = last_year["platform_company"].nunique() if not last_year.empty else 0

    st.markdown(section_header("Key Metrics",
        "Top-line numbers for the filtered deal set. Green/red arrows show year-over-year change. "
        "Total Deals = all acquisitions matching your filters. "
        "PE Sponsors = distinct private equity firms. "
        "Platforms = DSO companies doing the buying. "
        "YTD = deals so far this calendar year vs same point last year."), unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(make_kpi_card("📈", "Total Deals", total, delta=len(this_year) - len(last_year) if not last_year.empty else None), unsafe_allow_html=True)
    c2.markdown(make_kpi_card("🏢", "Active PE Sponsors", df["pe_sponsor"].nunique(), delta=sponsors_now - sponsors_prev if sponsors_prev else None), unsafe_allow_html=True)
    c3.markdown(make_kpi_card("🔗", "Active Platforms", df["platform_company"].nunique(), delta=plats_now - plats_prev if plats_prev else None), unsafe_allow_html=True)
    c4.markdown(make_kpi_card("📅", "Deals YTD", len(this_year), delta=len(this_year) - len(ytd_last) if not ytd_last.empty else None), unsafe_allow_html=True)

    st.markdown("")

    # Deal Volume Timeline
    st.markdown(section_header("Deal Volume Over Time",
        "Monthly count of dental PE deals, stacked by type. "
        "Buyout = full acquisition of a practice/group. Add-on = bolt-on to existing platform. "
        "The white dashed line shows the 6-month rolling average trend. "
        "A rising trend means PE firms are accelerating acquisitions."), unsafe_allow_html=True)
    monthly = df[df["deal_date"].notna()].copy()
    monthly["deal_type"] = monthly["deal_type"].fillna("other")
    monthly["month"] = monthly["deal_date"].dt.to_period("M").astype(str)
    vol = monthly.groupby(["month", "deal_type"]).size().reset_index(name="count")
    fig = px.bar(vol, x="month", y="count", color="deal_type", color_discrete_map=DEAL_TYPE_COLORS,
                 template=dental_dark_template, height=450)
    # Rolling avg
    total_monthly = monthly.groupby("month").size().reset_index(name="total")
    total_monthly["rolling"] = total_monthly["total"].rolling(6, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=total_monthly["month"], y=total_monthly["rolling"], mode="lines",
                             line=dict(color="white", width=2, dash="dash"), opacity=0.6, name="6-mo avg", showlegend=True))
    fig.update_layout(barmode="stack", xaxis_title="", yaxis_title="Deals", legend_title="Deal Type",
                      margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")

    # Top Sponsors & Platforms
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(section_header("Top 15 PE Sponsors",
            "Private equity firms ranked by deal count. These are the financial backers funding dental acquisitions. "
            "Higher bars = more aggressive acquirers in dentistry."), unsafe_allow_html=True)
        sp = df[df["pe_sponsor"].notna()].groupby("pe_sponsor").size().nlargest(15).reset_index(name="deals")
        if not sp.empty:
            fig_sp = px.bar(sp, x="deals", y="pe_sponsor", orientation="h", template=dental_dark_template,
                            color_discrete_sequence=["#0066FF"], text="deals")
            fig_sp.update_layout(yaxis=dict(autorange="reversed", title=""), xaxis_title="Deals",
                                 height=450, margin=dict(l=0, r=0, t=10, b=0))
            fig_sp.update_traces(textposition="outside")
            st.plotly_chart(fig_sp, width="stretch")
        else:
            st.info("No PE sponsor data available.")

    with col_r:
        st.markdown(section_header("Top 15 Platforms",
            "Platform companies (DSOs) ranked by deal count. These are the dental companies doing the buying. "
            "Examples: Heartland Dental, Aspen Dental. They buy individual practices and bolt them on."), unsafe_allow_html=True)
        pl = df[df["platform_company"].notna()].groupby("platform_company").size().nlargest(15).reset_index(name="deals")
        if not pl.empty:
            fig_pl = px.bar(pl, x="deals", y="platform_company", orientation="h", template=dental_dark_template,
                            color_discrete_sequence=["#00C853"], text="deals")
            fig_pl.update_layout(yaxis=dict(autorange="reversed", title=""), xaxis_title="Deals",
                                 height=450, margin=dict(l=0, r=0, t=10, b=0))
            fig_pl.update_traces(textposition="outside")
            st.plotly_chart(fig_pl, width="stretch")
        else:
            st.info("No platform data available.")

    # Geographic
    col_map, col_tbl = st.columns([2, 1])
    with col_map:
        st.markdown(section_header("Deal Activity by State",
            "Geographic heatmap of PE deal activity. Darker blue = more deals. "
            "States with heavy activity (FL, TX, CA) are consolidation hotspots."), unsafe_allow_html=True)
        state_deals = df[df["target_state"].notna()].groupby("target_state").size().reset_index(name="deals")
        if not state_deals.empty:
            fig_map = px.choropleth(state_deals, locations="target_state", locationmode="USA-states",
                                    color="deals", scope="usa", color_continuous_scale="Blues",
                                    template=dental_dark_template)
            fig_map.update_layout(geo=dict(bgcolor="#0B0E11", lakecolor="#141922", landcolor="#141922"),
                                  margin=dict(l=0, r=0, t=10, b=0), height=400, coloraxis_colorbar_title="Deals")
            st.plotly_chart(fig_map, width="stretch")

    with col_tbl:
        st.markdown(section_header("Top States",
            "States ranked by total PE deal count. These are the most active acquisition markets."), unsafe_allow_html=True)
        if not state_deals.empty:
            top_states = state_deals.nlargest(15, "deals")
            st.dataframe(top_states.rename(columns={"target_state": "State", "deals": "Deals"}),
                         hide_index=True, width="stretch")

    # Specialty
    col_don, col_trend = st.columns(2)
    with col_don:
        st.markdown(section_header("Deals by Specialty",
            "Breakdown of deals by dental specialty. General dentistry dominates, "
            "but orthodontics, oral surgery, and pediatric are also PE targets."), unsafe_allow_html=True)
        spec_data = df[df["specialty"].notna()].groupby("specialty").size().reset_index(name="count")
        if not spec_data.empty:
            fig_don = px.pie(spec_data, values="count", names="specialty", hole=0.5,
                             template=dental_dark_template)
            fig_don.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
            fig_don.update_traces(textinfo="label+percent")
            st.plotly_chart(fig_don, width="stretch")

    with col_trend:
        st.markdown(section_header("Specialty Trends",
            "How each specialty's deal volume is changing over time (by quarter). "
            "Rising areas show where PE firms are expanding focus."), unsafe_allow_html=True)
        spec_q = df[df["deal_date"].notna()].copy()
        spec_q["quarter"] = spec_q["deal_date"].dt.to_period("Q").astype(str)
        top_specs = spec_q["specialty"].value_counts().head(6).index.tolist()
        spec_q = spec_q[spec_q["specialty"].isin(top_specs)]
        if not spec_q.empty:
            sq = spec_q.groupby(["quarter", "specialty"]).size().reset_index(name="count")
            fig_sq = px.area(sq, x="quarter", y="count", color="specialty", facet_col="specialty",
                             facet_col_wrap=3, template=dental_dark_template, height=350)
            fig_sq.update_layout(showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
            fig_sq.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
            st.plotly_chart(fig_sq, width="stretch")

    # Recent Deals
    st.markdown(section_header("Recent Deal Activity",
        "The 100 most recent deals matching your filters. Use the search box to find specific companies. "
        "Click column headers to sort. Download button exports to CSV for Excel."), unsafe_allow_html=True)
    search = st.text_input("🔍 Search deals (type any company name, state, or keyword)...", key="deal_search")
    recent = df.sort_values("deal_date", ascending=False).head(100)
    if search:
        mask = recent.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
        recent = recent[mask]
    display_cols = ["deal_date", "platform_company", "pe_sponsor", "target_name", "target_state",
                    "deal_type", "specialty", "deal_size_mm", "source"]
    show = clean_dataframe(recent[[c for c in display_cols if c in recent.columns]])
    st.dataframe(show, hide_index=True, width="stretch")
    st.download_button("📥 Download filtered deals", show.to_csv(index=False), "deals_export.csv", "text/csv")


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 2: MARKET INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════

def page_market_intel():
    st.markdown('<h1 style="font-family:\'DM Sans\';font-weight:700">Market Intelligence</h1>', unsafe_allow_html=True)
    st.markdown(f"""<p style="color:var(--text-secondary);margin-top:-0.5rem;margin-bottom:1rem">
    Drill into your watched neighborhoods to see who owns what, which practices are independent,
    and where consolidation is happening.{help_tip(
    "This page shows data for ZIP codes you're watching. Each ZIP has practices from NPPES (national provider registry) "
    "classified by ownership status. Green = independent, Yellow = DSO-affiliated, Red = PE-backed. "
    "Use the metro dropdown to filter by region. Expand any ZIP to see every practice."
    )}</p>""", unsafe_allow_html=True)

    # Data freshness banner
    freshness = get_data_freshness()
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#0a1628 0%,#0d2137 100%);border:1px solid #1a3a5c;'
        f'border-radius:8px;padding:0.75rem 1.25rem;margin-bottom:1.25rem;display:flex;align-items:center;'
        f'justify-content:space-between;flex-wrap:wrap;gap:0.5rem">'
        f'<span style="color:#7eb8e0;font-size:0.82rem;font-weight:500">'
        f'📡 <strong style="color:#e8ecf1">{freshness["total_practices"]:,}</strong> practices tracked'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<strong style="color:#e8ecf1">{freshness["da_enriched"]:,}</strong> Data Axle enriched'
        f'</span>'
        f'<span style="color:#5a7a96;font-size:0.78rem">'
        f'Last updated {freshness["db_updated"]}'
        f'</span></div>',
        unsafe_allow_html=True
    )

    wz = load_watched_zips()
    if wz.empty:
        st.info("No watched ZIP codes configured. Go to System Health > Add ZIP to Watch to add some.")
        return

    metros = sorted(wz["metro_area"].dropna().unique().tolist())
    metros = ["All Watched ZIPs"] + metros
    # Find best default — try Chicagoland, then Chicago, then first
    default_idx = 0
    for name in ["Chicagoland", "Chicago"]:
        if name in metros:
            default_idx = metros.index(name)
            break
    selected = st.selectbox("Metro Area", metros, index=default_idx)

    zs = load_zip_scores()
    if selected != "All Watched ZIPs" and not zs.empty:
        zs = zs[zs["metro_area"] == selected]
    wz_filtered = wz if selected == "All Watched ZIPs" else wz[wz["metro_area"] == selected]
    zip_list = wz_filtered["zip_code"].tolist()

    # KPI cards
    if zs.empty:
        st.info("No consolidation scores calculated yet. Run `python3 scrapers/merge_and_score.py` to calculate ZIP-level scores.")
    else:
        total_p = int(zs["total_practices"].sum())
        pe_cnt = int(zs["pe_backed_count"].sum())
        dso_cnt = int(zs["dso_affiliated_count"].sum())
        indep_cnt = int(zs["independent_count"].sum())
        unk_cnt = int(zs["unknown_count"].sum())
        classified = int(zs["classified_count"].sum())
        # Conservative: use total as denominator (unknown = independent until proven otherwise)
        consol_total = ((pe_cnt + dso_cnt) / total_p * 100) if total_p > 0 else 0
        pe_pct_total = (pe_cnt / total_p * 100) if total_p > 0 else 0
        unk_pct = (unk_cnt / total_p * 100) if total_p > 0 else 100
        conf = "🟢 High" if unk_pct < 20 else ("🟡 Medium" if unk_pct <= 50 else "🔴 Low")

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(make_kpi_card("🏥", "Total Practices", f"{total_p:,}"), unsafe_allow_html=True)
        c2.markdown(make_kpi_card("📊", f"Known Consolidated {conf}", f"{consol_total:.1f}%"), unsafe_allow_html=True)
        c3.markdown(make_kpi_card("💰", "Known PE-Backed", f"{pe_pct_total:.1f}%"), unsafe_allow_html=True)
        c4.markdown(make_kpi_card("📈", "Opportunity Score", f"{zs['opportunity_score'].mean():.0f}"), unsafe_allow_html=True)

        # Transparency bar: show data classification breakdown
        if unk_pct > 30:
            st.caption(f"⚠️ {unk_pct:.0f}% of practices have unknown ownership ({unk_cnt:,} / {total_p:,}). "
                       f"Classified: {classified:,} — Independent: {indep_cnt:,}, DSO: {dso_cnt:,}, PE: {pe_cnt:,}. "
                       f"Real consolidation is likely higher. Add Data Axle exports to improve classification.")

    # ADA HPI Benchmarks
    ada = load_ada_hpi()
    if not ada.empty:
        st.markdown(section_header("ADA HPI State-Level DSO Affiliation Benchmarks",
            "Official ADA Health Policy Institute data showing what percentage of dentists in each state are DSO-affiliated, "
            "broken down by career stage. Early-career dentists are much more likely to join DSOs. "
            "This gives you the national context for how fast consolidation is happening."), unsafe_allow_html=True)
        ada_il = ada[ada["state"] == "IL"]
        ada_ma = ada[ada["state"] == "MA"]
        col_il, col_ma = st.columns(2)
        for col, state_df, state_name in [(col_il, ada_il, "Illinois"), (col_ma, ada_ma, "Massachusetts")]:
            with col:
                if not state_df.empty:
                    fig_ada = px.bar(state_df, x="career_stage", y="pct_dso_affiliated", color="data_year",
                                     barmode="group", template=dental_dark_template, title=state_name,
                                     labels={"pct_dso_affiliated": "DSO %", "career_stage": "Career Stage"})
                    fig_ada.update_layout(height=350, margin=dict(l=0, r=0, t=40, b=0))
                    st.plotly_chart(fig_ada, width="stretch")
                else:
                    st.info(f"No ADA HPI data for {state_name}")

    # ── Interactive Map ──────────────────────────────────────────────────
    if not zs.empty:
        st.markdown(section_header("Consolidation Map",
            "Each marker = one ZIP code. Size reflects practice count. Color shows consolidation level: "
            "blue = low consolidation (opportunity), warm = higher consolidation. Hover for details."), unsafe_allow_html=True)

        map_data = zs.copy()
        map_data["lat"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[0])
        map_data["lon"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[1])
        map_data = map_data.dropna(subset=["lat", "lon"])

        if not map_data.empty:
            # Rich hover text — PE-firm quality at-a-glance
            map_data["hover"] = map_data.apply(
                lambda r: (
                    f"<b style='font-size:14px'>{r['city']}</b>"
                    f"<span style='color:#90a4ae'> · {r['zip_code']}</span><br>"
                    f"<span style='font-size:13px;color:#e0e0e0'>"
                    f"{'●' * min(int(r['total_practices'] // 10), 8)} "
                    f"<b>{int(r['total_practices'])}</b> practices</span><br>"
                    f"<span style='font-size:12px;color:#4fc3f7'>"
                    f"▸ {int(r['independent_count'])} independent</span><br>"
                    f"<span style='font-size:12px;color:#ffb74d'>"
                    f"▸ {int(r['dso_affiliated_count'])} DSO  ·  {int(r['pe_backed_count'])} PE-backed</span><br>"
                    f"<span style='font-size:11px;color:#{'ef5350' if r['consolidation_pct'] > 35 else '66bb6a'}'>"
                    f"{'▲' if r['consolidation_pct'] > 35 else '◆'} "
                    f"{r['consolidation_pct']:.1f}% consolidated</span>"
                ), axis=1)

            # Determine map center
            metro_key = selected if selected in METRO_CENTERS else None
            if metro_key:
                center = METRO_CENTERS[metro_key]
            else:
                center = {"lat": map_data["lat"].mean(), "lon": map_data["lon"].mean(), "zoom": 9}

            # Marker sizing: power-scaled with tighter range for cleaner look
            sizes = map_data["total_practices"].apply(
                lambda x: max(7, min(24, 5 + (x ** 0.5) * 1.3)))

            fig_map = go.Figure()

            # Layer 0: Area of Interest boundary polygon (Chicagoland commute zone)
            # Covers DeKalb → Evanston/Chicago → Hammond → Kankakee → Morris → back
            AOI_POLYGONS = {
                "Chicagoland": {
                    "lats": [42.08, 42.08, 42.08, 41.88, 41.55, 41.10, 41.18, 41.35, 42.08],
                    "lons": [-88.95, -88.20, -87.60, -87.52, -87.48, -87.80, -88.60, -88.95, -88.95],
                },
            }
            aoi_key = selected if selected in AOI_POLYGONS else None
            if aoi_key:
                aoi = AOI_POLYGONS[aoi_key]
                # Filled polygon — light wash for "unmapped" zone
                fig_map.add_trace(go.Scattermapbox(
                    lat=aoi["lats"], lon=aoi["lons"],
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(100,150,200,0.12)",
                    line=dict(width=2.5, color="rgba(70,130,180,0.6)"),
                    hoverinfo="skip", showlegend=False,
                ))

            # Layer 1: Density heatmap background — smooth radius-based saturation field
            # Seed grid inside AOI so unmapped areas show a faint base wash
            import numpy as np
            grid_lats, grid_lons, grid_z = [], [], []
            if aoi_key:
                aoi = AOI_POLYGONS[aoi_key]
                lat_min, lat_max = min(aoi["lats"]), max(aoi["lats"])
                lon_min, lon_max = min(aoi["lons"]), max(aoi["lons"])
                for glat in np.arange(lat_min + 0.05, lat_max, 0.08):
                    for glon in np.arange(lon_min + 0.05, lon_max, 0.08):
                        grid_lats.append(glat)
                        grid_lons.append(glon)
                        grid_z.append(20.0)  # Base signal — registers as faint blue wash for unmapped areas
            # Combine real data with grid
            heat_z = map_data["consolidation_pct"] * map_data["total_practices"].apply(lambda x: max(1, x ** 0.7))
            all_lats = list(map_data["lat"]) + grid_lats
            all_lons = list(map_data["lon"]) + grid_lons
            all_z = list(heat_z) + grid_z
            fig_map.add_trace(go.Densitymapbox(
                lat=all_lats, lon=all_lons,
                z=all_z,
                radius=50,  # ~8-10 mile smooth radius
                opacity=0.75,
                zmin=0, zmax=max(all_z) * 0.35 if all_z else 100,  # Compress range so grid seeds register as faint wash
                colorscale=[
                    [0.00, "rgba(200,220,240,0.0)"],   # Transparent — no data
                    [0.06, "rgba(100,181,246,0.3)"],   # Light blue glow
                    [0.15, "rgba(41,182,246,0.5)"],    # Bright blue
                    [0.28, "rgba(38,198,218,0.6)"],    # Cyan
                    [0.40, "rgba(102,187,106,0.65)"],  # Green — opportunity
                    [0.52, "rgba(255,235,59,0.7)"],    # Yellow — transitional
                    [0.65, "rgba(255,152,0,0.75)"],    # Orange — elevated
                    [0.80, "rgba(244,67,54,0.8)"],     # Red — high
                    [1.00, "rgba(183,28,28,0.85)"],    # Deep red — saturated
                ],
                showscale=False,
                hoverinfo="skip",
            ))

            # Layer 2: Main data markers on top of heatmap
            fig_map.add_trace(go.Scattermapbox(
                lat=map_data["lat"], lon=map_data["lon"],
                mode="markers",
                marker=dict(
                    size=sizes,
                    color=map_data["consolidation_pct"],
                    colorscale=[
                        [0.00, "#4FC3F7"],   # Light blue — minimal consolidation
                        [0.15, "#26C6DA"],   # Cyan
                        [0.30, "#66BB6A"],   # Green — opportunity
                        [0.50, "#FDD835"],   # Yellow — transitional
                        [0.65, "#FFB74D"],   # Amber — elevated
                        [0.80, "#EF5350"],   # Red — high
                        [1.00, "#AD1457"],   # Deep magenta — heavily consolidated
                    ],
                    cmin=0, cmax=65,
                    opacity=0.95,
                    colorbar=dict(
                        title=dict(text="Consolidation %", font=dict(size=11, color="#b0bec5")),
                        ticksuffix="%", tickfont=dict(size=10, color="#90a4ae"),
                        tickvals=[0, 10, 20, 30, 40, 50, 60],
                        thickness=12, len=0.45, y=0.5, x=1.01,
                        bgcolor="rgba(10,22,40,0.85)", borderwidth=0,
                        outlinewidth=0,
                    ),
                ),
                text=map_data["hover"],
                hovertemplate="%{text}<extra></extra>",
                hoverinfo="text",
            ))

            # Layer 3: City labels for notable ZIPs (dark text for light map)
            label_threshold = 25 if len(map_data) > 50 else 15
            label_data = map_data[map_data["total_practices"] >= label_threshold].copy()
            if not label_data.empty:
                label_data["short_label"] = label_data.apply(
                    lambda r: f"{r['city']} ({int(r['total_practices'])})", axis=1)
                fig_map.add_trace(go.Scattermapbox(
                    lat=label_data["lat"] + 0.015,
                    lon=label_data["lon"],
                    mode="text",
                    text=label_data["short_label"],
                    textfont=dict(size=9.5, color="#1a237e", family="DM Sans"),
                    textposition="top center",
                    hoverinfo="skip", showlegend=False,
                ))

            fig_map.update_layout(
                mapbox=dict(
                    style="carto-positron",
                    center=dict(lat=center["lat"], lon=center["lon"]),
                    zoom=center["zoom"],
                ),
                height=620,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                hoverlabel=dict(
                    bgcolor="rgba(13,27,42,0.95)", bordercolor="#1a3a5c",
                    font=dict(color="white", size=12, family="DM Sans"),
                ),
                showlegend=False,
            )

            st.plotly_chart(fig_map, use_container_width=True)

            # Map legend callouts
            leg_cols = st.columns(4)
            with leg_cols[0]:
                st.markdown('<span style="color:#4FC3F7;font-size:13px">● Low consolidation</span>', unsafe_allow_html=True)
            with leg_cols[1]:
                st.markdown('<span style="color:#66BB6A;font-size:13px">● Opportunity zone</span>', unsafe_allow_html=True)
            with leg_cols[2]:
                st.markdown('<span style="color:#FFB74D;font-size:13px">● Elevated</span>', unsafe_allow_html=True)
            with leg_cols[3]:
                st.markdown('<span style="color:#EF5350;font-size:13px">● High consolidation</span>', unsafe_allow_html=True)
        else:
            st.info("No ZIP coordinates available for map display.")

    # ── ZIP Score Table ───────────────────────────────────────────────
    if not zs.empty:
        st.markdown(section_header("ZIP Code Consolidation Detail",
            "Each row = one ZIP code. Columns show how many practices are independent vs DSO vs PE-backed. "
            "Consolidation % = (DSO + PE) / total practices (conservative — treats unknowns as not consolidated). "
            "Opportunity Score = higher means more independent practices. Data Confidence = how well we can classify."), unsafe_allow_html=True)
        show_cols = ["zip_code", "city", "total_practices", "independent_count", "dso_affiliated_count",
                     "pe_backed_count", "unknown_count", "consolidation_pct_of_total", "pct_unknown", "data_confidence", "opportunity_score"]
        avail_cols = [c for c in show_cols if c in zs.columns]
        zt = zs[avail_cols]
        sort_col = "opportunity_score" if "opportunity_score" in zt.columns else avail_cols[0]
        zt = zt.sort_values(sort_col, ascending=False)
        st.dataframe(zt, hide_index=True, width="stretch")
        st.download_button("📥 Download ZIP scores", zt.to_csv(index=False), "zip_scores.csv", "text/csv")

    # ── Practice Detail: City → ZIP Tree ──────────────────────────────
    if zip_list:
        st.markdown(section_header("Practice Detail by City",
            "Practices grouped by city, then by ZIP code. Expand a city to see its ZIP codes, "
            "then expand a ZIP to see every practice. Green = independent (potential acquisition target), "
            "Yellow = DSO-affiliated, Red = PE-backed."), unsafe_allow_html=True)

        display_zips = sorted(zip_list)
        placeholders = ", ".join([f":z{i}" for i in range(len(display_zips))])
        params = {f"z{i}": z for i, z in enumerate(display_zips)}
        sess = get_session()
        try:
            all_practices = pd.read_sql(
                text(f"SELECT practice_name, npi, entity_type, ownership_status, "
                     f"affiliated_dso, affiliated_pe_sponsor, notes, zip "
                     f"FROM practices WHERE zip IN ({placeholders})"),
                sess.bind, params=params)

            zip_overviews = {}
            if table_exists("zip_overviews"):
                for ov in sess.query(ZipOverview).filter(ZipOverview.zip_code.in_(display_zips)).all():
                    zip_overviews[ov.zip_code] = ov.overview_html

            # Build city → ZIP mapping from watched_zips
            city_zips = {}
            for _, row in wz_filtered.iterrows():
                city = row.get("city", "Unknown") or "Unknown"
                zc = row["zip_code"]
                if city not in city_zips:
                    city_zips[city] = []
                city_zips[city].append(zc)

            for city_name in sorted(city_zips.keys()):
                zips_in_city = sorted(city_zips[city_name])
                city_practices = all_practices[all_practices["zip"].isin(zips_in_city)]
                city_total = len(city_practices)

                # City-level ownership counts
                city_indep = len(city_practices[city_practices["ownership_status"] == "independent"])
                city_dso = len(city_practices[city_practices["ownership_status"] == "dso_affiliated"])
                city_pe = len(city_practices[city_practices["ownership_status"] == "pe_backed"])

                city_label = (f"🏙️ {city_name} — {city_total} practices across {len(zips_in_city)} ZIP"
                              f"{'s' if len(zips_in_city) > 1 else ''}"
                              f"  (🟢 {city_indep} | 🟡 {city_dso} | 🔴 {city_pe})")

                with st.expander(city_label):
                    # City-level mini KPIs
                    if city_total > 0:
                        city_unk = city_total - city_indep - city_dso - city_pe
                        consol = ((city_dso + city_pe) / city_total * 100)
                        kc1, kc2, kc3, kc4 = st.columns(4)
                        kc1.metric("Total", city_total)
                        kc2.metric("Independent", city_indep)
                        kc3.metric("DSO + PE", city_dso + city_pe)
                        kc4.metric("Known Consolidated", f"{consol:.0f}%",
                                   delta=f"{city_unk} unknown" if city_unk > 0 else None,
                                   delta_color="off")

                    # ZIP sub-expanders within each city
                    for zc in zips_in_city:
                        zip_practices = all_practices[all_practices["zip"] == zc].drop(columns=["zip"])
                        analyzed = zip_practices["notes"].notna().sum() if "notes" in zip_practices.columns else 0

                        # Get ZIP score if available
                        zip_score_row = zs[zs["zip_code"] == zc] if not zs.empty else pd.DataFrame()
                        score_tag = ""
                        if not zip_score_row.empty:
                            opp = zip_score_row.iloc[0].get("opportunity_score", 0)
                            score_tag = f" | Score: {opp:.0f}"

                        zip_label = f"📍 {zc} — {len(zip_practices)} practices{score_tag}"
                        if analyzed > 0:
                            zip_label += f" | {analyzed} analyzed"

                        with st.expander(zip_label):
                            if zc in zip_overviews:
                                st.markdown(
                                    f'<div style="background: linear-gradient(135deg, #1a2332 0%, #0d1b2a 100%); '
                                    f'border: 1px solid #1e3a5f; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; '
                                    f'font-size: 0.85rem; color: #c8d6e5;">{zip_overviews[zc]}</div>',
                                    unsafe_allow_html=True,
                                )

                            if zip_practices.empty:
                                st.info("No practices in this ZIP.")
                            else:
                                display_cols = ["practice_name", "ownership_status",
                                                "affiliated_dso", "affiliated_pe_sponsor", "entity_type"]
                                display_df = zip_practices[[c for c in display_cols if c in zip_practices.columns]].copy()
                                display_df["ownership_status"] = display_df["ownership_status"].apply(format_status)
                                display_df = clean_dataframe(display_df)
                                st.dataframe(display_df, hide_index=True, width="stretch")
        finally:
            sess.close()

    # Recent changes
    st.markdown(section_header("Recent Practice Changes",
        "Detected ownership changes in your watched ZIPs — when a practice switches from independent to DSO, "
        "gets a new name, or changes status. These are automatically detected by comparing NPPES data snapshots."), unsafe_allow_html=True)
    if zip_list:
        sess = get_session()
        try:
            # Build parameterized IN clause (SQLite doesn't support tuple binding in text())
            placeholders = ", ".join([f":z{i}" for i in range(len(zip_list))])
            params = {f"z{i}": z for i, z in enumerate(zip_list)}
            changes = pd.read_sql(text(
                f"SELECT pc.change_date, p.practice_name, p.city, p.zip, pc.field_changed, "
                f"pc.old_value, pc.new_value, pc.change_type FROM practice_changes pc "
                f"JOIN practices p ON pc.npi = p.npi WHERE p.zip IN ({placeholders}) "
                f"ORDER BY pc.change_date DESC LIMIT 50"
            ), sess.bind, params=params)
            if changes.empty:
                st.info("No practice changes detected yet in these ZIPs. Changes appear when NPPES data is refreshed monthly.")
            else:
                st.dataframe(clean_dataframe(changes), hide_index=True, width="stretch")
        except Exception:
            st.info("No practice changes detected yet.")
        finally:
            sess.close()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 3: BUYABILITY SCANNER
# ═══════════════════════════════════════════════════════════════════════════

def page_buyability():
    st.markdown('<h1 style="font-family:\'DM Sans\';font-weight:700">Buyability Scanner</h1>', unsafe_allow_html=True)
    st.markdown(f"""<p style="color:var(--text-secondary);margin-top:-0.5rem;margin-bottom:1rem">
    Practices scored by acquisition likelihood based on hand research and directory analysis.
    {help_tip("This page shows practices that have been analyzed with verdict classifications. "
    "Acquisition Targets are practices likely buyable — solo practitioners, retirement plays, succession opportunities. "
    "Dead Ends are locked (dynasty, corporate, ghost). Job Targets are places to work, not buy.")}</p>""", unsafe_allow_html=True)

    sess = get_session()
    try:
        # Load practices with EITHER a VERDICT in notes OR a buyability_score
        analyzed = pd.read_sql(text(
            "SELECT practice_name, address, city, zip, ownership_status, notes, "
            "affiliated_dso, buyability_score, buyability_confidence, "
            "year_established, employee_count, estimated_revenue "
            "FROM practices "
            "WHERE notes LIKE '%VERDICT%' OR buyability_score IS NOT NULL "
            "ORDER BY buyability_score DESC NULLS LAST, zip, practice_name"
        ), sess.bind)

        if analyzed.empty:
            st.info("**No analyzed practices yet.**\n\n"
                    "Run the directory importer to load practice analysis data, or "
                    "import Data Axle records for automated scoring.\n\n"
                    "```\npython3 -m scrapers.directory_importer\n```")
            return

        # Extract verdicts from notes
        import re
        def _extract(pattern, notes):
            if not notes:
                return "—"
            m = re.search(pattern, notes)
            return m.group(1).strip() if m else "—"

        analyzed["verdict"] = analyzed["notes"].apply(lambda n: _extract(r'VERDICT:\s*(.+?)(?:\n|$)', n))
        analyzed["buyability_tag"] = analyzed["notes"].apply(lambda n: _extract(r'Buyability:\s*(.+?)(?:\n|$)', n))

        # KPIs
        acq_targets = analyzed[analyzed["buyability_tag"] == "acquisition_target"]
        dead_ends = analyzed[analyzed["buyability_tag"] == "dead_end"]
        job_targets = analyzed[analyzed["buyability_tag"] == "job_target"]
        specialists = analyzed[analyzed["buyability_tag"] == "specialist"]

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(make_kpi_card("🎯", "Acquisition Targets", len(acq_targets)), unsafe_allow_html=True)
        c2.markdown(make_kpi_card("🚫", "Dead Ends", len(dead_ends)), unsafe_allow_html=True)
        c3.markdown(make_kpi_card("💼", "Job Targets", len(job_targets)), unsafe_allow_html=True)
        c4.markdown(make_kpi_card("🔬", "Specialists", len(specialists)), unsafe_allow_html=True)

        # Filters
        st.markdown(section_header("Analyzed Practices",
            "Practices with hand-researched verdicts and/or buyability scores. "
            "Filter by category and ZIP code to find acquisition targets. "
            "Sort by score descending to see the most buyable practices first."
        ), unsafe_allow_html=True)

        f1, f2 = st.columns(2)
        category = f1.selectbox("Filter by category", ["All", "Acquisition Targets", "Dead Ends", "Job Targets", "Specialists"])
        zip_options = ["All ZIPs"] + sorted(analyzed["zip"].dropna().unique().tolist())
        zip_filter = f2.selectbox("Filter by ZIP", zip_options, key="buyability_zip")

        cat_map = {"Acquisition Targets": "acquisition_target", "Dead Ends": "dead_end",
                   "Job Targets": "job_target", "Specialists": "specialist"}
        filtered = analyzed.copy()
        if category != "All":
            filtered = filtered[filtered["buyability_tag"] == cat_map[category]]
        if zip_filter != "All ZIPs":
            filtered = filtered[filtered["zip"] == zip_filter]

        show_cols = ["practice_name", "address", "city", "zip", "ownership_status",
                     "buyability_score", "confidence", "year_established", "employee_count", "verdict"]
        display = filtered.copy()
        display["ownership_status"] = display["ownership_status"].apply(format_status)
        # Confidence stars (1-5 data points)
        display["confidence"] = display["buyability_confidence"].apply(
            lambda c: ("*" * int(c)) if pd.notna(c) and c else "?")
        avail_cols = [c for c in show_cols if c in display.columns]
        display = clean_dataframe(display[avail_cols])
        st.dataframe(display, hide_index=True, width="stretch")
        st.download_button("📥 Download analyzed practices", display.to_csv(index=False), "buyability_analysis.csv", "text/csv")

    finally:
        sess.close()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 4: RESEARCH TOOLS
# ═══════════════════════════════════════════════════════════════════════════

def page_research():
    st.markdown('<h1 style="font-family:\'DM Sans\';font-weight:700">Research Tools</h1>', unsafe_allow_html=True)
    st.markdown(f"""<p style="color:var(--text-secondary);margin-top:-0.5rem;margin-bottom:1rem">
    Deep-dive into specific PE sponsors, platforms, states, or write custom SQL queries.
    {help_tip("Use these tools to research specific companies or markets. "
    "PE Sponsor Profile = look up a specific PE firm and see all their deals. "
    "Platform Profile = look up a specific DSO. State Deep Dive = see all activity in a state. "
    "SQL Explorer = query the raw database directly with SQL.")}</p>""", unsafe_allow_html=True)

    tab_sp, tab_pl, tab_st, tab_sql = st.tabs(["PE Sponsor Profile", "Platform Profile", "State Deep Dive", "SQL Explorer"])

    deals_df = load_deals()

    with tab_sp:
        sponsors = sorted(deals_df["pe_sponsor"].dropna().unique().tolist()) if not deals_df.empty else []
        if not sponsors:
            st.info("No PE sponsor data available.")
        else:
            sel = st.selectbox("Select PE Sponsor", sponsors, key="research_sponsor")
            sp_deals = deals_df[deals_df["pe_sponsor"] == sel]
            st.markdown(make_kpi_card("🏢", sel, len(sp_deals), delta=None), unsafe_allow_html=True)
            if not sp_deals.empty:
                # Timeline
                fig = px.scatter(sp_deals, x="deal_date", y="platform_company", color="deal_type",
                                 color_discrete_map=DEAL_TYPE_COLORS, template=dental_dark_template,
                                 hover_data=["target_name", "target_state"])
                fig.update_layout(height=350, yaxis_title="", margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, width="stretch")
                # Platforms
                plats = sp_deals.groupby("platform_company").size().reset_index(name="deals").sort_values("deals", ascending=False)
                st.dataframe(plats.rename(columns={"platform_company": "Platform", "deals": "Deals"}), hide_index=True)
                # Recent
                st.markdown("**Recent Activity**")
                recent = sp_deals.sort_values("deal_date", ascending=False).head(10)
                st.dataframe(recent[["deal_date", "platform_company", "target_name", "target_state", "deal_type"]],
                             hide_index=True, width="stretch")

    with tab_pl:
        platforms = sorted(deals_df["platform_company"].dropna().unique().tolist()) if not deals_df.empty else []
        if not platforms:
            st.info("No platform data available.")
        else:
            sel = st.selectbox("Select Platform", platforms, key="research_platform")
            pl_deals = deals_df[deals_df["platform_company"] == sel]
            sponsor = pl_deals["pe_sponsor"].dropna().iloc[0] if not pl_deals["pe_sponsor"].dropna().empty else "Unknown"
            st.markdown(make_kpi_card("🔗", f"{sel} ({sponsor})", len(pl_deals)), unsafe_allow_html=True)
            if not pl_deals.empty:
                fig = px.scatter(pl_deals, x="deal_date", y="target_state", color="target_state",
                                 template=dental_dark_template, hover_data=["target_name", "deal_type"])
                fig.update_layout(height=350, yaxis_title="State", margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, width="stretch")
                st.dataframe(pl_deals[["deal_date", "target_name", "target_state", "deal_type", "specialty"]].sort_values("deal_date", ascending=False),
                             hide_index=True, width="stretch")

    with tab_st:
        states = sorted(deals_df["target_state"].dropna().unique().tolist()) if not deals_df.empty else []
        if not states:
            st.info("No state data available.")
        else:
            sel = st.selectbox("Select State", states, key="research_state")
            st_deals = deals_df[deals_df["target_state"] == sel]
            st.markdown(make_kpi_card("🗺️", f"{sel} Deals", len(st_deals)), unsafe_allow_html=True)
            if not st_deals.empty:
                st_deals_q = st_deals[st_deals["deal_date"].notna()].copy()
                st_deals_q["quarter"] = st_deals_q["deal_date"].dt.to_period("Q").astype(str)
                q_data = st_deals_q.groupby("quarter").size().reset_index(name="deals")
                fig = px.bar(q_data, x="quarter", y="deals", template=dental_dark_template,
                             color_discrete_sequence=["#0066FF"])
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, width="stretch")
                # Top platforms
                top = st_deals.groupby("platform_company").size().nlargest(10).reset_index(name="deals")
                fig2 = px.bar(top, x="deals", y="platform_company", orientation="h", template=dental_dark_template,
                              color_discrete_sequence=["#00C853"], text="deals")
                fig2.update_layout(yaxis=dict(autorange="reversed", title=""), height=350, margin=dict(l=0, r=0, t=10, b=0))
                fig2.update_traces(textposition="outside")
                st.plotly_chart(fig2, width="stretch")

    with tab_sql:
        st.markdown(f"""**SQL Explorer** — query the database directly {help_tip(
            "Write SQL SELECT queries to explore the raw data. Tables available: "
            "deals (PE transactions), practices (dental providers), watched_zips (your target ZIPs), "
            "practice_changes (ownership changes), pe_sponsors, platforms, dso_locations, zip_overviews. "
            "Click the preset buttons below for example queries. Only SELECT queries are allowed."
        )}""", unsafe_allow_html=True)

        # Pre-built queries
        queries = {
            "Deals by sponsor": "SELECT deal_date, platform_company, pe_sponsor, target_name, target_state, deal_type, deal_size_mm\nFROM deals WHERE pe_sponsor = '[EDIT: sponsor name]'\nORDER BY deal_date DESC",
            "ZIP ownership": "SELECT zip, city, state,\n  SUM(CASE WHEN ownership_status='independent' THEN 1 ELSE 0 END) as independent,\n  SUM(CASE WHEN ownership_status='dso_affiliated' THEN 1 ELSE 0 END) as dso,\n  SUM(CASE WHEN ownership_status='pe_backed' THEN 1 ELSE 0 END) as pe,\n  COUNT(*) as total\nFROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)\nGROUP BY zip, city, state ORDER BY total DESC",
            "Monthly volume": "SELECT strftime('%Y-%m', deal_date) as month, deal_type, COUNT(*) as deals\nFROM deals GROUP BY month, deal_type ORDER BY month DESC",
            "New in state": "SELECT DISTINCT platform_company, pe_sponsor, MIN(deal_date) as first_deal, COUNT(*) as total\nFROM deals WHERE target_state='[EDIT: ST]' AND deal_date > date('now','-12 months')\nGROUP BY platform_company, pe_sponsor ORDER BY first_deal DESC",
            "Practice changes": "SELECT pc.change_date, p.practice_name, p.city, p.zip, pc.field_changed,\n  pc.old_value, pc.new_value, pc.change_type\nFROM practice_changes pc JOIN practices p ON pc.npi=p.npi\nWHERE p.zip IN (SELECT zip_code FROM watched_zips)\nORDER BY pc.change_date DESC LIMIT 50",
        }
        btn_cols = st.columns(len(queries))
        for i, (name, q) in enumerate(queries.items()):
            if btn_cols[i].button(name, key=f"sql_btn_{i}"):
                st.session_state["sql_query"] = q

        query = st.text_area("SQL Query", value=st.session_state.get("sql_query", ""), height=150, key="sql_input")

        if st.button("▶️ Execute", key="sql_exec"):
            q = query.strip()
            if not q:
                st.warning("Enter a query first.")
            elif not q.upper().startswith("SELECT"):
                st.error("⛔ Only SELECT queries are allowed for safety.")
            elif any(kw in q.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "EXEC"]):
                st.error("⛔ Query contains forbidden keywords. Only SELECT queries are allowed.")
            else:
                s = get_session()
                try:
                    result = pd.read_sql(text(q), s.bind)
                    st.success(f"✅ {len(result)} rows returned")
                    st.dataframe(result, hide_index=True, width="stretch")
                    st.download_button("📥 Download results", result.to_csv(index=False), "query_results.csv", "text/csv")
                except Exception as e:
                    st.error(f"Query error: {e}")
                finally:
                    s.close()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 5: SYSTEM HEALTH
# ═══════════════════════════════════════════════════════════════════════════

def page_system_health():
    st.markdown('<h1 style="font-family:\'DM Sans\';font-weight:700">System Health</h1>', unsafe_allow_html=True)
    st.markdown(f"""<p style="color:var(--text-secondary);margin-top:-0.5rem;margin-bottom:1rem">
    Monitor data freshness, run diagnostics, and manually add data.
    {help_tip("This page shows the health of your data pipeline. Green = data is fresh (updated within 7 days). "
    "Yellow = stale (7-30 days). Red = outdated (30+ days). "
    "Use the manual entry forms at the bottom to add deals, update practices, or add new ZIP codes to watch.")}</p>""", unsafe_allow_html=True)

    s = get_session()
    try:
        _render_system_health(s)
    finally:
        s.close()


def _render_system_health(s):

    # Source Coverage
    st.markdown(section_header("Data Source Coverage",
        "Each row shows a data source and its freshness. PESP = PE research firm scraper. "
        "GDN = dental news scraper. PitchBook = PE deal database. NPPES = CMS national provider registry. "
        "ADSO = American Dental Support Organizations member scraper. ADA HPI = official benchmark data."
    ), unsafe_allow_html=True)
    now = datetime.now()

    def status_dot(last_dt):
        if last_dt is None:
            return '<span class="status-dot status-gray"></span>No data'
        days = (now - last_dt).days
        if days <= 7:
            return '<span class="status-dot status-green"></span>Current'
        elif days <= 30:
            return '<span class="status-dot status-yellow"></span>Stale'
        else:
            return '<span class="status-dot status-red"></span>Outdated'

    sources = []
    for src_name, src_filter in [("PESP", "pesp"), ("GDN", "gdn"), ("PitchBook", "pitchbook")]:
        cnt = s.query(func.count(Deal.id)).filter(Deal.source.contains(src_filter)).scalar() or 0
        min_d = s.query(func.min(Deal.deal_date)).filter(Deal.source.contains(src_filter)).scalar()
        max_d = s.query(func.max(Deal.deal_date)).filter(Deal.source.contains(src_filter)).scalar()
        last = s.query(func.max(Deal.created_at)).filter(Deal.source.contains(src_filter)).scalar()
        sources.append({"Source": src_name, "Records": cnt,
                         "Date Range": f"{min_d} → {max_d}" if min_d else "—",
                         "Last Updated": str(last)[:10] if last else "—",
                         "Status": status_dot(last)})

    # NPPES
    nppes_cnt = s.query(func.count(Practice.id)).filter(Practice.data_source == "nppes").scalar() or 0
    nppes_last = s.query(func.max(Practice.created_at)).filter(Practice.data_source == "nppes").scalar()
    sources.append({"Source": "NPPES", "Records": nppes_cnt, "Date Range": "—",
                     "Last Updated": str(nppes_last)[:10] if nppes_last else "—",
                     "Status": status_dot(nppes_last)})

    if table_exists("dso_locations"):
        dso_cnt = s.query(func.count(DSOLocation.id)).scalar() or 0
        dso_last = s.query(func.max(DSOLocation.scraped_at)).scalar()
        sources.append({"Source": "ADSO Scraper", "Records": dso_cnt, "Date Range": "—",
                         "Last Updated": str(dso_last)[:10] if dso_last else "—",
                         "Status": status_dot(dso_last)})

    if table_exists("ada_hpi_benchmarks"):
        ada_cnt = s.query(func.count(ADAHPIBenchmark.id)).scalar() or 0
        ada_last = s.query(func.max(ADAHPIBenchmark.created_at)).scalar()
        ada_years = s.query(func.min(ADAHPIBenchmark.data_year), func.max(ADAHPIBenchmark.data_year)).first()
        ada_range = f"{ada_years[0]}–{ada_years[1]}" if ada_years[0] else "—"
        sources.append({"Source": "ADA HPI", "Records": ada_cnt, "Date Range": ada_range,
                         "Last Updated": str(ada_last)[:10] if ada_last else "—",
                         "Status": status_dot(ada_last)})

    src_df = pd.DataFrame(sources)
    st.markdown(src_df.to_html(escape=False, index=False), unsafe_allow_html=True)

    # DB size
    if os.path.exists(DB_PATH):
        db_mb = os.path.getsize(DB_PATH) / 1024 / 1024
        gz_path = DB_PATH + ".gz"
        gz_mb = os.path.getsize(gz_path) / 1024 / 1024 if os.path.exists(gz_path) else 0
        size_warning = ""
        if db_mb > 400:
            size_warning = " -- APPROACHING LIMIT: GitHub max is 100MB for .gz, consider pruning practice_changes"
        elif db_mb > 200:
            size_warning = " -- growing, monitor quarterly"
        st.caption(f"Database: {db_mb:.1f} MB (compressed: {gz_mb:.1f} MB for git){size_warning}")

    # Data Completeness
    st.markdown(section_header("Data Completeness",
        "How complete your data is across key fields. Green = 80%+ filled. Yellow = 50-80%. Red = under 50%. "
        "Deals with PE sponsor = % of deals where we know the PE firm. Practices classified = % where ownership is known."
    ), unsafe_allow_html=True)
    total_deals = s.query(func.count(Deal.id)).scalar() or 1
    total_practices = s.query(func.count(Practice.id)).scalar() or 1

    metrics = [
        ("Deals with PE sponsor", s.query(func.count(Deal.id)).filter(Deal.pe_sponsor.isnot(None)).scalar() or 0, total_deals),
        ("Deals with state", s.query(func.count(Deal.id)).filter(Deal.target_state.isnot(None)).scalar() or 0, total_deals),
        ("Deals with specialty", s.query(func.count(Deal.id)).filter(Deal.specialty.isnot(None)).scalar() or 0, total_deals),
        ("Deals with deal size", s.query(func.count(Deal.id)).filter(Deal.deal_size_mm.isnot(None)).scalar() or 0, total_deals),
        ("Practices classified", s.query(func.count(Practice.id)).filter(Practice.ownership_status != "unknown").scalar() or 0, total_practices),
    ]
    for label, count, total in metrics:
        pct = count / total * 100 if total > 0 else 0
        color = "#00C853" if pct >= 80 else ("#FFB300" if pct >= 50 else "#FF3D00")
        st.markdown(f'<span style="color:{color};font-weight:600">{label}: {pct:.0f}%</span> ({count:,} / {total:,})', unsafe_allow_html=True)
        st.progress(min(pct / 100, 1.0))

    # Pipeline Activity Log (structured events)
    st.markdown(section_header("Pipeline Activity Log",
        "Timestamped record of every automated scraper and pipeline run. Shows what ran, what changed, and whether it succeeded. "
        "Events are logged by each scraper in the refresh pipeline. Green = success, red = error."
    ), unsafe_allow_html=True)

    try:
        from scrapers.pipeline_logger import get_recent_events, get_last_run_summary
        events = get_recent_events(limit=30)
    except ImportError:
        events = []

    if events:
        # Last-run summary cards
        try:
            last_runs = get_last_run_summary()
        except Exception:
            last_runs = {}
        if last_runs:
            cols = st.columns(min(len(last_runs), 4))
            for i, (src, ev) in enumerate(sorted(last_runs.items())):
                with cols[i % len(cols)]:
                    ts = ev.get("timestamp", "")[:16].replace("T", " ")
                    status = ev.get("status", "")
                    emoji = "✅" if status == "success" else "❌"
                    label = src.replace("_", " ").title()
                    new_r = ev.get("details", {}).get("new_records", 0)
                    dur = ev.get("details", {}).get("duration_seconds", 0)
                    st.metric(f"{emoji} {label}", f"{new_r} new" if new_r else "No changes",
                              f"{dur}s • {ts}")

        # Event table
        rows = []
        for ev in reversed(events):
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            src = ev.get("source", "")
            status = ev.get("status", "")
            summary = ev.get("summary", "")
            det = ev.get("details", {})
            dur = det.get("duration_seconds", "")
            new_r = det.get("new_records", "")
            status_icon = {"success": "🟢", "error": "🔴", "info": "🔵"}.get(status, "⚪")
            rows.append({
                "Time": ts,
                "Source": src,
                "Status": status_icon,
                "Summary": summary[:80],
                "New": new_r,
                "Duration": f"{dur}s" if dur else "",
            })
        if rows:
            ev_df = pd.DataFrame(rows)
            st.dataframe(ev_df, use_container_width=True, hide_index=True)
    else:
        st.info("No pipeline events yet. Events will appear after the first automated refresh runs.")

    # Raw log viewer (expandable)
    with st.expander("Raw Log Files (debug)", expanded=False):
        log_files = sorted(globmod.glob(os.path.join(LOGS_DIR, "*.log")))
        if log_files:
            selected_log = st.selectbox("Log file", [os.path.basename(f) for f in reversed(log_files[-10:])])
            log_path = os.path.join(LOGS_DIR, selected_log)
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()[-100:]
                display = []
                for line in lines:
                    if "WARNING" in line:
                        display.append("⚠️ " + line.rstrip())
                    elif "ERROR" in line:
                        display.append("❌ " + line.rstrip())
                    else:
                        display.append(line.rstrip())
                st.code("\n".join(display), language="log")
        else:
            st.info("No log files found.")

    # Manual Entry Forms
    st.markdown(section_header("Manual Data Entry",
        "Manually add deals from press releases, update practice ownership when you learn new info, "
        "or add new ZIP codes to monitor. All manual entries are tracked with source='manual'."
    ), unsafe_allow_html=True)
    tab_deal, tab_practice, tab_zip = st.tabs(["Add Deal", "Update Practice", "Add ZIP to Watch"])

    with tab_deal:
        with st.form("add_deal_form"):
            d1, d2 = st.columns(2)
            deal_date = d1.date_input("Deal Date", value=date.today())
            platform = d2.text_input("Platform Company *")
            d3, d4 = st.columns(2)
            sponsor = d3.text_input("PE Sponsor")
            target = d4.text_input("Target Name")
            d5, d6 = st.columns(2)
            state = d5.selectbox("State", [""] + US_STATES)
            deal_type = d6.selectbox("Deal Type", ["buyout", "add-on", "recapitalization", "growth", "de_novo", "partnership", "other"])
            d7, d8 = st.columns(2)
            specialty = d7.selectbox("Specialty", ["general", "orthodontics", "oral_surgery", "endodontics", "periodontics", "pediatric", "prosthodontics", "multi_specialty", "other"])
            deal_size = d8.number_input("Deal Size ($M)", min_value=0.0, step=0.1, value=0.0)
            source = st.selectbox("Source", ["manual", "press_release", "linkedin", "conference", "other"])
            notes = st.text_area("Notes")
            if st.form_submit_button("Add Deal"):
                if not platform:
                    st.error("Platform company is required.")
                else:
                    try:
                        insert_deal(s, deal_date=deal_date, platform_company=platform,
                                    pe_sponsor=sponsor or None, target_name=target or None,
                                    target_state=state or None, deal_type=deal_type, specialty=specialty,
                                    deal_size_mm=deal_size if deal_size > 0 else None,
                                    source=source, notes=notes or None)
                        st.success(f"✅ Deal added: {platform}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab_practice:
        npi_lookup = st.text_input("Look up NPI", max_chars=10, key="npi_lookup")
        if npi_lookup and len(npi_lookup) == 10:
            p = s.query(Practice).filter_by(npi=npi_lookup).first()
            if p:
                st.info(f"**{p.practice_name or '—'}** | {p.city or '—'}, {p.state or '—'} {p.zip or '—'} | Status: {format_status(p.ownership_status)} | DSO: {p.affiliated_dso or '—'}")
            else:
                st.warning("NPI not found.")

        with st.form("update_practice_form"):
            npi = st.text_input("NPI Number", max_chars=10)
            new_status = st.selectbox("New Status", ["independent", "dso_affiliated", "pe_backed", "unknown"])
            dso = st.text_input("Affiliated DSO")
            pe = st.text_input("Affiliated PE Sponsor")
            notes = st.text_area("Notes")
            if st.form_submit_button("Update Practice"):
                p = s.query(Practice).filter_by(npi=npi).first()
                if not p:
                    st.error("NPI not found.")
                else:
                    try:
                        old = p.ownership_status
                        p.ownership_status = new_status
                        if dso:
                            p.affiliated_dso = dso
                        if pe:
                            p.affiliated_pe_sponsor = pe
                        log_practice_change(s, npi=npi, change_date=date.today(),
                                            field_changed="ownership_status", old_value=old,
                                            new_value=new_status, change_type="acquisition",
                                            notes=notes or "Manual update")
                        st.success(f"✅ Updated NPI {npi}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab_zip:
        with st.form("add_zip_form"):
            z1, z2 = st.columns(2)
            zc = z1.text_input("ZIP Code", max_chars=5)
            city = z2.text_input("City")
            z3, z4 = st.columns(2)
            state = z3.selectbox("State", US_STATES, key="zip_state")
            metro = z4.text_input("Metro Area", placeholder="e.g., Chicagoland")
            if st.form_submit_button("Add ZIP"):
                if not zc or len(zc) != 5:
                    st.error("Enter a valid 5-digit ZIP code.")
                else:
                    try:
                        s.add(WatchedZip(zip_code=zc, city=city, state=state, metro_area=metro))
                        s.commit()
                        st.success(f"✅ Added ZIP {zc} to watch list. Run merge_and_score.py to calculate scores.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # Session is closed by caller (page_system_health try/finally)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 6: JOB MARKET INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════

def page_job_market():
    st.markdown('<h1 style="font-family:\'DM Sans\';font-weight:700">Job Market Intelligence</h1>', unsafe_allow_html=True)
    st.markdown(f"""<p style="color:var(--text-secondary);margin-top:-0.5rem;margin-bottom:1rem">
    Evaluate dental practice landscapes near your planned living locations —
    where are independent practices, and where is consolidation squeezing out opportunity?{help_tip(
    "This page filters consolidation data to ZIP codes commutable from your planned living location. "
    "Green zones = high opportunity (many independent practices, low PE/DSO penetration). "
    "Red zones = saturated markets."
    )}</p>""", unsafe_allow_html=True)

    # Data freshness banner
    freshness = get_data_freshness()
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#0a1628 0%,#0d2137 100%);border:1px solid #1a3a5c;'
        f'border-radius:8px;padding:0.75rem 1.25rem;margin-bottom:1.25rem;display:flex;align-items:center;'
        f'justify-content:space-between;flex-wrap:wrap;gap:0.5rem">'
        f'<span style="color:#7eb8e0;font-size:0.82rem;font-weight:500">'
        f'📡 <strong style="color:#e8ecf1">{freshness["total_practices"]:,}</strong> practices tracked'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<strong style="color:#e8ecf1">{freshness["da_enriched"]:,}</strong> Data Axle enriched'
        f'</span>'
        f'<span style="color:#5a7a96;font-size:0.78rem">'
        f'Last updated {freshness["db_updated"]}'
        f'</span></div>',
        unsafe_allow_html=True
    )

    # Living location selector
    selected = st.selectbox("Planned Living Area", list(LIVING_LOCATIONS.keys()))
    loc = LIVING_LOCATIONS[selected]
    zip_list = loc["commutable_zips"]

    # Load and filter zip scores to commutable ZIPs
    zs = load_zip_scores()
    if zs.empty:
        st.info("No consolidation scores calculated yet. Run `python3 scrapers/merge_and_score.py` to calculate ZIP-level scores.")
        return
    zs = zs[zs["zip_code"].isin(zip_list)]

    # ── KPI Cards ────────────────────────────────────────────────────────
    if zs.empty:
        st.warning(f"No scored ZIPs found for **{selected}**. Run Data Axle exports and merge_and_score.py for these ZIPs.")
    else:
        total_p = int(zs["total_practices"].sum())
        indep_cnt = int(zs["independent_count"].sum())
        unk_cnt = int(zs["unknown_count"].sum())
        unk_pct = (unk_cnt / total_p * 100) if total_p > 0 else 100
        avg_opp = zs["opportunity_score"].mean()
        recent_chg = int(zs["recent_changes_90d"].sum()) if "recent_changes_90d" in zs.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(make_kpi_card("🏥", "Total Practices", f"{total_p:,}"), unsafe_allow_html=True)
        c2.markdown(make_kpi_card("🟢", "Known Independent", f"{indep_cnt:,}"), unsafe_allow_html=True)
        c3.markdown(make_kpi_card("📈", "Avg Opportunity Score", f"{avg_opp:.0f}"), unsafe_allow_html=True)
        c4.markdown(make_kpi_card("🔄", "Recent Changes (90d)", f"{recent_chg:,}"), unsafe_allow_html=True)

        if unk_pct > 30:
            st.caption(f"⚠️ {unk_pct:.0f}% of practices have unknown ownership ({unk_cnt:,} / {total_p:,}). "
                       f"Known independent: {indep_cnt:,}. Real independent count is likely higher. "
                       f"Add Data Axle exports to improve classification.")

    # ── Commutable Zone Map ──────────────────────────────────────────────
    if not zs.empty:
        st.markdown(section_header("Commutable Zone Map",
            "Each marker = one ZIP code. Green = high opportunity (many independent practices). "
            "Red = saturated (heavy PE/DSO presence). Size reflects practice count."), unsafe_allow_html=True)

        map_data = zs.copy()
        map_data["lat"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[0])
        map_data["lon"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[1])
        map_data = map_data.dropna(subset=["lat", "lon"])

        if not map_data.empty:
            # Rich hover text — opportunity-focused
            map_data["hover"] = map_data.apply(
                lambda r: (
                    f"<b style='font-size:14px'>{r['city']}</b>"
                    f"<span style='color:#90a4ae'> · {r['zip_code']}</span><br>"
                    f"<span style='font-size:13px;color:#e0e0e0'>"
                    f"{'●' * min(int(r['total_practices'] // 10), 8)} "
                    f"<b>{int(r['total_practices'])}</b> practices</span><br>"
                    f"<span style='font-size:12px;color:#66bb6a'>"
                    f"▸ {int(r['independent_count'])} independent</span><br>"
                    f"<span style='font-size:12px;color:#ffb74d'>"
                    f"▸ {int(r['dso_affiliated_count'])} DSO  ·  {int(r['pe_backed_count'])} PE-backed</span><br>"
                    f"<span style='font-size:12px;color:#4fc3f7'>"
                    f"◆ Opportunity: <b>{r['opportunity_score']:.0f}</b></span>"
                ), axis=1)

            sizes = map_data["total_practices"].apply(
                lambda x: max(7, min(24, 5 + (x ** 0.5) * 1.3)))

            fig_map = go.Figure()

            # Layer 1: Density heatmap — opportunity-focused (green = high)
            import numpy as np
            heat_z = map_data["opportunity_score"] * map_data["total_practices"].apply(lambda x: max(1, x ** 0.7))
            fig_map.add_trace(go.Densitymapbox(
                lat=list(map_data["lat"]), lon=list(map_data["lon"]),
                z=list(heat_z),
                radius=50, opacity=0.75,
                zmin=0, zmax=max(list(heat_z)) * 0.35 if len(heat_z) > 0 else 100,
                colorscale=[
                    [0.00, "rgba(200,220,240,0.0)"],
                    [0.06, "rgba(183,28,28,0.3)"],
                    [0.15, "rgba(244,67,54,0.5)"],
                    [0.28, "rgba(255,152,0,0.6)"],
                    [0.40, "rgba(255,235,59,0.65)"],
                    [0.52, "rgba(102,187,106,0.7)"],
                    [0.65, "rgba(38,198,218,0.7)"],
                    [0.80, "rgba(41,182,246,0.75)"],
                    [1.00, "rgba(46,125,50,0.85)"],
                ],
                showscale=False, hoverinfo="skip",
            ))

            # Layer 2: Scatter markers — opportunity coloring
            fig_map.add_trace(go.Scattermapbox(
                lat=map_data["lat"], lon=map_data["lon"],
                mode="markers",
                marker=dict(
                    size=sizes,
                    color=map_data["opportunity_score"],
                    colorscale=[
                        [0.00, "#AD1457"],
                        [0.15, "#EF5350"],
                        [0.30, "#FFB74D"],
                        [0.50, "#FDD835"],
                        [0.70, "#66BB6A"],
                        [0.85, "#26C6DA"],
                        [1.00, "#2E7D32"],
                    ],
                    cmin=0, cmax=100, opacity=0.95,
                    colorbar=dict(
                        title=dict(text="Opportunity Score", font=dict(size=11, color="#b0bec5")),
                        tickfont=dict(size=10, color="#90a4ae"),
                        tickvals=[0, 20, 40, 60, 80, 100],
                        thickness=12, len=0.45, y=0.5, x=1.01,
                        bgcolor="rgba(10,22,40,0.85)", borderwidth=0, outlinewidth=0,
                    ),
                ),
                text=map_data["hover"],
                hovertemplate="%{text}<extra></extra>",
                hoverinfo="text",
            ))

            # Layer 3: City labels for notable ZIPs
            label_threshold = 25 if len(map_data) > 50 else 15
            label_data = map_data[map_data["total_practices"] >= label_threshold].copy()
            if not label_data.empty:
                label_data["short_label"] = label_data.apply(
                    lambda r: f"{r['city']} ({int(r['total_practices'])})", axis=1)
                fig_map.add_trace(go.Scattermapbox(
                    lat=label_data["lat"] + 0.015, lon=label_data["lon"],
                    mode="text", text=label_data["short_label"],
                    textfont=dict(size=9.5, color="#1a237e", family="DM Sans"),
                    textposition="top center", hoverinfo="skip", showlegend=False,
                ))

            # Auto-fit zoom to data bounds
            lat_range = map_data["lat"].max() - map_data["lat"].min()
            lon_range = map_data["lon"].max() - map_data["lon"].min()
            span = max(lat_range, lon_range)
            if span > 1.0: auto_zoom = 7.5
            elif span > 0.5: auto_zoom = 8.8
            elif span > 0.3: auto_zoom = 9.5
            else: auto_zoom = 10.5
            fit_center = {
                "lat": (map_data["lat"].max() + map_data["lat"].min()) / 2,
                "lon": (map_data["lon"].max() + map_data["lon"].min()) / 2,
            }

            fig_map.update_layout(
                mapbox=dict(style="carto-positron", center=fit_center, zoom=auto_zoom),
                height=620, margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                hoverlabel=dict(
                    bgcolor="rgba(13,27,42,0.95)", bordercolor="#1a3a5c",
                    font=dict(color="white", size=12, family="DM Sans"),
                ),
                showlegend=False,
            )

            st.plotly_chart(fig_map, use_container_width=True)

            st.caption(f"Showing {len(map_data)} of {len(zip_list)} commutable ZIPs with consolidation data")

            leg_cols = st.columns(4)
            with leg_cols[0]:
                st.markdown('<span style="color:#2E7D32;font-size:13px">● High opportunity</span>', unsafe_allow_html=True)
            with leg_cols[1]:
                st.markdown('<span style="color:#26C6DA;font-size:13px">● Moderate</span>', unsafe_allow_html=True)
            with leg_cols[2]:
                st.markdown('<span style="color:#FFB74D;font-size:13px">● Lower opportunity</span>', unsafe_allow_html=True)
            with leg_cols[3]:
                st.markdown('<span style="color:#EF5350;font-size:13px">● Saturated</span>', unsafe_allow_html=True)
        else:
            st.info("No ZIP coordinates available for map display.")

    # ── Opportunity Signals Table ────────────────────────────────────────
    st.markdown(section_header("Opportunity Signals",
        "Each practice scored 0-100: independent ownership (30), buyability (25), "
        "size (20), young practice (15), unknown status (10)."), unsafe_allow_html=True)

    practices_df = load_practices_for_zone(tuple(zip_list))
    if not practices_df.empty:
        practices_df = compute_job_opportunity_score(practices_df)

        da_mask = practices_df["import_batch_id"].fillna("").str.startswith("DA_")
        enriched_df = practices_df[da_mask].copy()
        other_df = practices_df[~da_mask].copy()

        show_cols = ["practice_name", "city", "zip", "ownership_status", "employee_count",
                     "year_established", "buyability_score", "job_opp_score"]
        col_renames = {
            "practice_name": "Practice Name", "city": "City", "zip": "ZIP",
            "ownership_status": "Status", "employee_count": "Employees",
            "year_established": "Year Est.", "buyability_score": "Buyability",
            "job_opp_score": "Job Opp Score",
        }
        avail_cols = [c for c in show_cols if c in practices_df.columns]

        # Tier 1: Enriched
        st.subheader("Enriched Practices (Data Axle)")
        if enriched_df.empty:
            st.info("No Data Axle-enriched practices in these ZIPs yet.")
        else:
            t1 = enriched_df[avail_cols].sort_values("job_opp_score", ascending=False).copy()
            t1["ownership_status"] = t1["ownership_status"].apply(format_status)
            st.dataframe(t1.rename(columns=col_renames).fillna("—"), hide_index=True, use_container_width=True)

        # Tier 2: All other
        st.subheader("All Other Practices")
        if other_df.empty:
            st.info("No other practices in these ZIPs.")
        else:
            t2 = other_df[avail_cols].sort_values("job_opp_score", ascending=False).head(200).copy()
            t2["ownership_status"] = t2["ownership_status"].apply(format_status)
            st.dataframe(t2.rename(columns=col_renames).fillna("—"), hide_index=True, use_container_width=True)

        # Download
        combined = practices_df[avail_cols].sort_values("job_opp_score", ascending=False).copy()
        st.download_button("📥 Download all practices with scores",
                           combined.rename(columns=col_renames).fillna("—").to_csv(index=False),
                           "opportunity_scores.csv", "text/csv")

        enriched_count = len(enriched_df)
        total = len(practices_df)
        if total > 0:
            st.caption(f"{enriched_count} of {total} practices have Data Axle enrichment "
                       f"({enriched_count / total * 100:.0f}% coverage).")

        # ── Market Stats ─────────────────────────────────────────────────
        st.markdown(section_header("Ownership Landscape",
            "Breakdown of practices by ownership status and size."), unsafe_allow_html=True)

        # Ownership bar chart
        ownership_counts = practices_df["ownership_status"].fillna("unknown").value_counts().reset_index()
        ownership_counts.columns = ["status", "count"]
        status_labels = {"independent": "Independent", "dso_affiliated": "DSO Affiliated",
                         "pe_backed": "PE-Backed", "unknown": "Unknown",
                         "likely_independent": "Likely Independent"}
        status_colors = {"Independent": "#66BB6A", "DSO Affiliated": "#FFB74D",
                         "PE-Backed": "#EF5350", "Unknown": "#78909C",
                         "Likely Independent": "#81C784"}
        ownership_counts["label"] = ownership_counts["status"].map(
            lambda s: status_labels.get(s, s.replace("_", " ").title()))

        fig_own = px.bar(ownership_counts, x="count", y="label", orientation="h",
                         color="label", color_discrete_map=status_colors,
                         template=dental_dark_template,
                         labels={"count": "Practices", "label": ""})
        fig_own.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig_own, use_container_width=True)

        # Practice size distribution
        enriched_with_emp = practices_df[practices_df["employee_count"].notna()].copy()
        if not enriched_with_emp.empty:
            def _size_bucket(emp):
                if emp <= 4: return "Solo (1-4)"
                elif emp <= 9: return "Small Group (5-9)"
                return "Large Group (10+)"
            enriched_with_emp["size"] = enriched_with_emp["employee_count"].apply(_size_bucket)
            size_order = ["Solo (1-4)", "Small Group (5-9)", "Large Group (10+)"]
            sc = enriched_with_emp["size"].value_counts().reindex(size_order, fill_value=0).reset_index()
            sc.columns = ["size", "count"]
            fig_sz = px.bar(sc, x="size", y="count", template=dental_dark_template,
                            labels={"size": "Practice Size", "count": "Practices"})
            fig_sz.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_sz, use_container_width=True)
            st.caption(f"Size data available for {len(enriched_with_emp)} of {total} practices.")

        # Top DSOs
        dso_df = practices_df[practices_df["affiliated_dso"].notna() & (practices_df["affiliated_dso"] != "")]
        if not dso_df.empty:
            st.markdown("**Top DSOs in Zone**")
            top_dsos = (dso_df.groupby("affiliated_dso").size().reset_index(name="Practices")
                        .sort_values("Practices", ascending=False).head(10))
            st.dataframe(clean_dataframe(top_dsos), hide_index=True, use_container_width=True)

        # DSO Penetration by ZIP
        if not zs.empty and "consolidation_pct_of_total" in zs.columns:
            st.markdown("**DSO Penetration by ZIP**")
            pen_cols = ["zip_code", "city", "total_practices", "consolidation_pct_of_total", "opportunity_score"]
            pen = zs[[c for c in pen_cols if c in zs.columns]].copy()
            pen = pen.sort_values("consolidation_pct_of_total", ascending=True)
            pen = pen.rename(columns={"zip_code": "ZIP", "city": "City", "total_practices": "Practices",
                                       "consolidation_pct_of_total": "Consolidation %", "opportunity_score": "Opportunity"})
            st.dataframe(pen, hide_index=True, use_container_width=True)
    else:
        st.info("No practices found in the selected ZIPs.")

    # ── Growth Signals Placeholder ───────────────────────────────────────
    st.markdown(section_header("Growth Signals", "Future demographic data"), unsafe_allow_html=True)
    st.info("This section will track new housing developments, population growth trends, "
            "and commercial expansion to predict where patient demand is increasing. "
            "Data sources being evaluated include Census ACS, county building permits, "
            "and CMAP regional planning data.")

    # ── Recent Ownership Changes ─────────────────────────────────────────
    st.markdown(section_header("Recent Ownership Changes",
        "Detected ownership changes in your commutable ZIPs — when a practice switches from "
        "independent to DSO, gets a new name, or changes status."), unsafe_allow_html=True)
    if zip_list:
        sess = get_session()
        try:
            placeholders = ", ".join([f":z{i}" for i in range(len(zip_list))])
            params = {f"z{i}": z for i, z in enumerate(zip_list)}
            changes = pd.read_sql(text(
                f"SELECT pc.change_date, p.practice_name, p.city, p.zip, pc.field_changed, "
                f"pc.old_value, pc.new_value, pc.change_type FROM practice_changes pc "
                f"JOIN practices p ON pc.npi = p.npi WHERE p.zip IN ({placeholders}) "
                f"ORDER BY pc.change_date DESC LIMIT 50"
            ), sess.bind, params=params)
            if changes.empty:
                st.info("No practice changes detected yet in these ZIPs.")
            else:
                st.dataframe(clean_dataframe(changes), hide_index=True, use_container_width=True)
        except Exception:
            st.info("No practice changes detected yet.")
        finally:
            sess.close()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Dental PE Intelligence",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
render_sidebar()

pages = {
    "📊 Deal Flow": page_deal_flow,
    "🗺️ Market Intel": page_market_intel,
    "🎯 Buyability": page_buyability,
    "💼 Job Market": page_job_market,
    "🔬 Research": page_research,
    "⚙️ System": page_system_health,
}

selected_page = st.sidebar.radio("Navigation", list(pages.keys()), label_visibility="collapsed")
pages[selected_page]()
