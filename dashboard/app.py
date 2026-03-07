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

# ZIP centroids for watched ZIPs (used for map plotting)
ZIP_CENTROIDS = {
    # Chicagoland
    "60491": (41.60, -87.94), "60439": (41.67, -87.98), "60441": (41.58, -88.06),
    "60540": (41.77, -88.15), "60564": (41.72, -88.20), "60565": (41.73, -88.17),
    "60563": (41.76, -88.19), "60527": (41.76, -87.94), "60515": (41.80, -88.02),
    "60516": (41.78, -88.03), "60532": (41.80, -88.08), "60559": (41.79, -87.97),
    "60514": (41.80, -87.95), "60521": (41.80, -87.93), "60523": (41.83, -87.95),
    "60148": (41.87, -88.01), "60440": (41.70, -88.07), "60490": (41.65, -88.12),
    "60504": (41.74, -88.26), "60502": (41.77, -88.28), "60431": (41.52, -88.09),
    "60435": (41.55, -88.08), "60586": (41.62, -88.22), "60585": (41.63, -88.20),
    "60503": (41.73, -88.26), "60554": (41.76, -88.44), "60543": (41.68, -88.35),
    "60560": (41.64, -88.44),
    # Boston Metro
    "02116": (42.35, -71.07), "02115": (42.34, -71.10), "02118": (42.34, -71.07),
    "02119": (42.32, -71.08), "02120": (42.33, -71.10), "02215": (42.35, -71.10),
    "02134": (42.35, -71.13), "02135": (42.35, -71.16), "02446": (42.34, -71.12),
    "02445": (42.33, -71.13), "02467": (42.32, -71.16), "02459": (42.31, -71.19),
    "02458": (42.35, -71.19), "02453": (42.38, -71.24), "02451": (42.39, -71.24),
    "02138": (42.38, -71.13), "02139": (42.37, -71.10), "02140": (42.39, -71.13),
    "02141": (42.37, -71.09), "02142": (42.36, -71.08), "02144": (42.40, -71.12),
}
METRO_CENTERS = {
    "Chicagoland": {"lat": 41.72, "lon": -88.10, "zoom": 10},
    "Boston Metro": {"lat": 42.35, "lon": -71.13, "zoom": 11},
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
        return pd.read_sql(text("SELECT * FROM zip_scores"), s.bind)
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
        classified = int(zs["classified_count"].sum())
        consol = ((pe_cnt + dso_cnt) / classified * 100) if classified > 0 else 0
        pe_pct = (pe_cnt / classified * 100) if classified > 0 else 0
        unk_pct = float(zs["pct_unknown"].mean()) if not zs.empty else 100
        conf = "🟢 High" if unk_pct < 20 else ("🟡 Medium" if unk_pct <= 50 else "🔴 Low")

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(make_kpi_card("🏥", "Total Practices", total_p), unsafe_allow_html=True)
        c2.markdown(make_kpi_card("📊", f"Consolidated {conf}", f"{consol:.1f}%"), unsafe_allow_html=True)
        c3.markdown(make_kpi_card("💰", "PE-Backed", f"{pe_pct:.1f}%"), unsafe_allow_html=True)
        c4.markdown(make_kpi_card("📈", "Opportunity Score", f"{zs['opportunity_score'].mean():.0f}"), unsafe_allow_html=True)

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
            "Interactive map of your watched ZIP codes. Circle size = number of practices. "
            "Color = consolidation percentage (red = highly consolidated, green = mostly independent). "
            "Hover over any circle to see full details. Scroll to zoom, drag to pan."), unsafe_allow_html=True)

        map_data = zs.copy()
        map_data["lat"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[0])
        map_data["lon"] = map_data["zip_code"].map(lambda z: ZIP_CENTROIDS.get(z, (None, None))[1])
        map_data = map_data.dropna(subset=["lat", "lon"])

        if not map_data.empty:
            map_data["label"] = map_data.apply(
                lambda r: f"{r['zip_code']} — {r['city']}<br>"
                          f"Practices: {int(r['total_practices'])}<br>"
                          f"Consolidation: {r['consolidation_pct']:.1f}%<br>"
                          f"Independent: {int(r['independent_count'])} | DSO: {int(r['dso_affiliated_count'])} | PE: {int(r['pe_backed_count'])}<br>"
                          f"Opportunity Score: {r['opportunity_score']:.0f}",
                axis=1)

            # Determine map center
            metro_key = selected if selected in METRO_CENTERS else None
            if metro_key:
                center = METRO_CENTERS[metro_key]
            else:
                center = {"lat": map_data["lat"].mean(), "lon": map_data["lon"].mean(), "zoom": 9}

            fig_map = px.scatter_mapbox(
                map_data, lat="lat", lon="lon",
                size="total_practices", color="consolidation_pct",
                color_continuous_scale=["#00C853", "#FFB300", "#FF3D00"],
                range_color=[0, 60],
                size_max=28, zoom=center["zoom"],
                center={"lat": center["lat"], "lon": center["lon"]},
                hover_name="label",
                mapbox_style="carto-darkmatter",
            )
            fig_map.update_layout(
                height=500, margin=dict(l=0, r=0, t=0, b=0),
                coloraxis_colorbar=dict(title="Consol %", ticksuffix="%"),
                paper_bgcolor="#0B0E11",
            )
            fig_map.update_traces(hovertemplate="%{hovertext}<extra></extra>")
            st.plotly_chart(fig_map, width="stretch")
        else:
            st.info("No ZIP coordinates available for map display.")

    # ── ZIP Score Table ───────────────────────────────────────────────
    if not zs.empty:
        st.markdown(section_header("ZIP Code Consolidation Detail",
            "Each row = one ZIP code. Columns show how many practices are independent vs DSO vs PE-backed. "
            "Consolidation % = (DSO + PE) / total classified. Opportunity Score = higher means more independent "
            "practices available for acquisition. Data Confidence = how many practices we could classify."), unsafe_allow_html=True)
        show_cols = ["zip_code", "city", "total_practices", "independent_count", "dso_affiliated_count",
                     "pe_backed_count", "unknown_count", "consolidation_pct", "data_confidence", "opportunity_score"]
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
                        classified = city_indep + city_dso + city_pe
                        consol = ((city_dso + city_pe) / classified * 100) if classified > 0 else 0
                        kc1, kc2, kc3, kc4 = st.columns(4)
                        kc1.metric("Total", city_total)
                        kc2.metric("Independent", city_indep)
                        kc3.metric("DSO + PE", city_dso + city_pe)
                        kc4.metric("Consolidated", f"{consol:.0f}%")

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
            "affiliated_dso, buyability_score, year_established, employee_count "
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

        display = filtered[["practice_name", "address", "city", "zip", "ownership_status",
                            "buyability_score", "verdict"]].copy()
        display["ownership_status"] = display["ownership_status"].apply(format_status)
        display = clean_dataframe(display)
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
        sources.append({"Source": "ADA HPI", "Records": ada_cnt, "Date Range": "—",
                         "Last Updated": "—", "Status": status_dot(None) if ada_cnt == 0 else '<span class="status-dot status-green"></span>Loaded'})

    src_df = pd.DataFrame(sources)
    st.markdown(src_df.to_html(escape=False, index=False), unsafe_allow_html=True)

    # DB size
    if os.path.exists(DB_PATH):
        db_mb = os.path.getsize(DB_PATH) / 1024 / 1024
        st.caption(f"Database size: {db_mb:.1f} MB")

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

    # Log viewer
    st.markdown(section_header("Recent Logs",
        "Last 100 lines from the most recent log file. Warnings (yellow) and errors (red) are highlighted. "
        "Logs are generated each time a scraper or data pipeline runs."
    ), unsafe_allow_html=True)
    log_files = sorted(globmod.glob(os.path.join(LOGS_DIR, "*.log")))
    if log_files:
        with open(log_files[-1], "r") as f:
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
        st.info("No logs found.")

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
    "🔬 Research": page_research,
    "⚙️ System": page_system_health,
}

selected_page = st.sidebar.radio("Navigation", list(pages.keys()), label_visibility="collapsed")
pages[selected_page]()
