---
name: dashboard-dev
description: Develop, fix, or modify the Streamlit dashboard (dashboard/app.py). Use when changing any dashboard page, adding charts, fixing display issues, modifying KPI calculations, or adding new pages. Trigger phrases include "dashboard", "streamlit", "app.py", "Market Intel", "Deal Flow", "Buyability", "Research", "System Health", "KPI", "chart", "plotly", "map", "consolidation", "opportunity score".
---

# Dashboard Development Guide

## Architecture

Single file: `dashboard/app.py` (1,277 lines). Five pages routed via sidebar radio buttons.

```python
PAGES = {
    "Deal Flow": page_deal_flow,
    "Market Intel": page_market_intel,
    "Buyability": page_buyability,
    "Research": page_research,
    "System Health": page_system_health,
}
```

## Page Map

| Page | Function | Lines (approx) | Key Features |
|------|----------|----------------|-------------|
| Deal Flow | `page_deal_flow()` | 80-320 | Deal charts by year/state/type, recent deals feed, filters |
| Market Intel | `page_market_intel()` | 509-750 | ZIP consolidation KPIs, ADA HPI benchmarks, interactive map, city/ZIP tree |
| Buyability | `page_buyability()` | 750-900 | Practice scoring table, filters by ZIP/status/score |
| Research | `page_research()` | 900-1050 | PE sponsor profiles, platform profiles, state deep dives, SQL explorer |
| System Health | `page_system_health()` | 1050-1277 | Data freshness, pipeline activity log, raw logs, manual data entry |

## Key Helpers

```python
section_header(title, help_text)  # Consistent section headers with tooltips
make_kpi_card(icon, label, value) # HTML KPI card
help_tip(text)                    # Inline help tooltip
load_watched_zips()               # Cached DataFrame of watched ZIPs
load_zip_scores()                 # Cached DataFrame of ZIP consolidation scores
load_ada_hpi()                    # Cached ADA benchmark data
```

## Critical Rules

### Consolidation math — NEVER inflate numbers
```python
# CORRECT: conservative denominator (total practices)
consol = (pe + dso) / total * 100

# WRONG: only classified denominator (hides unknowns)
consol = (pe + dso) / classified * 100   # DO NOT USE for headline KPIs
```

Always show unknown count when >30% unknown. Labels must say "Known Consolidated".

### Streamlit Cloud constraints
- DB is gzipped in git; `database.py` auto-decompresses on first import
- Keep heavy imports inside page functions (not top-level) for cold start speed
- `@st.cache_data` for DB queries that don't change during a session
- Test locally with `streamlit run dashboard/app.py` before pushing

### Plotly dark theme
All charts use `dental_dark_template` (custom Plotly template defined near top of file).
Background: `#0B0E11`, text: white, grid: `#1a1d23`.

### Pipeline Activity Log (System Health page)
```python
from scrapers.pipeline_logger import get_recent_events, get_last_run_summary
events = get_recent_events(limit=30)    # List of dicts
last_runs = get_last_run_summary()       # Dict keyed by source name
```

## Adding a New Dashboard Page

1. Define `def page_new_name():` function
2. Add to `PAGES` dict at top
3. Use `section_header()` and `make_kpi_card()` for consistency
4. Use `dental_dark_template` for all Plotly charts
5. Test locally: `cd ~/dental-pe-tracker && streamlit run dashboard/app.py`

## Adding a New Chart

```python
import plotly.express as px
fig = px.bar(df, x="col", y="val", template=dental_dark_template, title="Title")
fig.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0),
                  paper_bgcolor="#0B0E11")
st.plotly_chart(fig, width="stretch")
```

## Testing

```bash
# Parse check
python3 -c "import ast; ast.parse(open('dashboard/app.py').read()); print('OK')"

# Local run
cd ~/dental-pe-tracker && streamlit run dashboard/app.py

# Deploy
python3 -c "import gzip,shutil; shutil.copyfileobj(open('data/dental_pe_tracker.db','rb'), gzip.open('data/dental_pe_tracker.db.gz','wb',6))"
git add data/dental_pe_tracker.db.gz && git commit -m "Update DB" && git push
```
