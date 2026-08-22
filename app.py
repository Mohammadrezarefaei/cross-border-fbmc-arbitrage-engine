import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.optimize import linprog
import streamlit as st

# ==========================================
# 1. PAGE SETUP & HIGH-END THEME STYLING
# ==========================================
st.set_page_config(
    page_title="Cross-Border FBMC Arbitrage Engine",
    page_icon="🌐",
    layout="wide",
)

st.markdown(
    """
<style>
    div[data-testid="stMetric"] {
        background-color: #050b1f;
        border: 2px solid #0055ff;
        padding: 16px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 14px rgba(0, 85, 255, 0.25);
    }
    div[data-testid="stMetricLabel"] {
        color: #ffffff;
        font-size: 0.9rem;
        font-weight: 600;
    }
    div[data-testid="stMetricValue"] {
        color: #ffffff;
        font-size: 1.6rem;
        font-weight: 700;
    }
    hr {
        border-top: 1px solid #0044ff;
        margin: 25px 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🌐 Cross-Border FBMC & Arbitrage Convergence Engine")
st.markdown(
    "<p style='color: #cbd5e1; font-size: 1.05rem; margin-top: -10px;'>"
    "Multi-zone European market coupling optimization across the <b>Core FBMC"
    " Region (DE, FR, AT, NL)</b>.</p>",
    unsafe_allow_html=True,
)

# ==========================================
# 2. CORE FBMC MATHEMATICAL ENGINE
# ==========================================
def get_core_fbmc_parameters():
  """Returns Core FBMC market coupling parameters:

  PTDF matrix, RAM capacities, and commercial Net Position bounds.
  """
  ram_mw = np.array([2500.0, 1800.0, 3000.0])  # CNEC1: DE->FR, CNEC2: DE->NL, CNEC3: DE->AT

  ptdf_matrix = np.array([
      [0.0, -0.72, 0.08, -0.22],
      [0.0, -0.15, 0.05, -0.68],
      [0.0, 0.12, -0.81, 0.05],
  ])

  max_export_mw = np.array([6000.0, 5000.0, 3500.0, 4000.0])
  max_import_mw = np.array([-6000.0, -5000.0, -3500.0, -4000.0])

  return ptdf_matrix, ram_mw, max_export_mw, max_import_mw


def clear_fbmc_market(unconstrained_prices, timestamps, ram_scale_factor=1.0):
  """Linear Programming (HiGHS) multi-period social welfare market coupling."""
  ptdf, base_ram, max_exp, max_imp = get_core_fbmc_parameters()
  ram = base_ram * ram_scale_factor
  n_zones = 4
  n_hours = len(timestamps)

  cleared_net_positions = []
  cnec_loadings_pct = []
  cleared_prices = []
  congestion_rents = []

  for h in range(n_hours):
    c_obj = unconstrained_prices[h]

    # Global balance: Sum(Net Positions) == 0
    A_eq = np.ones((1, n_zones))
    b_eq = np.zeros(1)

    # RAM limits in forward & reverse directions: |PTDF @ NP| <= RAM
    A_ub = np.vstack([ptdf, -ptdf])
    b_ub = np.concatenate([ram, ram])

    bounds = [(max_imp[z], max_exp[z]) for z in range(n_zones)]

    res = linprog(
        c_obj,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res.success:
      raise RuntimeError(f"Clearing error at index {h}: {res.message}")

    net_pos = res.x
    cleared_net_positions.append(net_pos)

    flows = ptdf @ net_pos
    loading_pct = (np.abs(flows) / ram) * 100.0
    cnec_loadings_pct.append(loading_pct)

    is_congested = (loading_pct >= 99.0).any()
    if is_congested:
      hour_p = unconstrained_prices[h] + (net_pos / 150.0)
    else:
      hour_p = np.full(n_zones, np.mean(unconstrained_prices[h]))

    cleared_prices.append(hour_p)
    c_rent = np.sum(
        np.abs(flows) * np.abs(hour_p[1:] - hour_p[0]) / 3.0
    )
    congestion_rents.append(c_rent)

  net_pos_arr = np.array(cleared_net_positions)
  prices_arr = np.array(cleared_prices)
  loadings_arr = np.array(cnec_loadings_pct)

  return pd.DataFrame({
      "timestamp": timestamps,
      "de_net_export_mw": np.round(net_pos_arr[:, 0], 1),
      "fr_net_export_mw": np.round(net_pos_arr[:, 1], 1),
      "at_net_export_mw": np.round(net_pos_arr[:, 2], 1),
      "nl_net_export_mw": np.round(net_pos_arr[:, 3], 1),
      "de_price_eur": np.round(prices_arr[:, 0], 2),
      "fr_price_eur": np.round(prices_arr[:, 1], 2),
      "at_price_eur": np.round(prices_arr[:, 2], 2),
      "nl_price_eur": np.round(prices_arr[:, 3], 2),
      "de_fr_spread_eur": np.round(
          prices_arr[:, 1] - prices_arr[:, 0], 2
      ),
      "cnec1_de_fr_loading_pct": np.round(loadings_arr[:, 0], 1),
      "cnec2_de_nl_loading_pct": np.round(loadings_arr[:, 1], 1),
      "cnec3_de_at_loading_pct": np.round(loadings_arr[:, 2], 1),
      "congestion_rent_eur": np.round(congestion_rents, 2),
  })


# ==========================================
# 3. SIDEBAR CONTROLS & DATA GENERATION
# ==========================================
st.sidebar.markdown("### ⚙️ Grid & Market Parameters")
horizon_days = st.sidebar.slider(
    "Simulation Horizon (Days)", min_value=3, max_value=14, value=7, step=1
)
ram_scale = st.sidebar.slider(
    "Interconnector Capacity Factor (RAM)",
    min_value=0.5,
    max_value=1.5,
    value=1.0,
    step=0.1,
)
renewable_spread_boost = st.sidebar.slider(
    "Renewable Merit-Order Spread Boost",
    min_value=0.8,
    max_value=2.0,
    value=1.2,
    step=0.1,
)

n_hours = horizon_days * 24
dates = pd.date_range("2026-08-01 00:00:00", periods=n_hours, freq="h")
hours = dates.hour.to_numpy()

de_base = (
    65.0
    - np.maximum(0, np.sin((hours - 6) * np.pi / 12))
    * 45.0
    * renewable_spread_boost
) + np.random.normal(0, 4, n_hours)
fr_base = (
    82.0 + np.maximum(0, np.sin((hours - 17) * np.pi / 4)) * 35.0
) + np.random.normal(0, 5, n_hours)
at_base = (
    72.0 + np.sin((hours - 8) * np.pi / 10) * 15.0 + np.random.normal(0, 3, n_hours)
)
nl_base = (
    76.0 + np.sin((hours - 7) * np.pi / 11) * 20.0 + np.random.normal(0, 4, n_hours)
)

unconstrained_prices = np.column_stack([de_base, fr_base, at_base, nl_base])
df = clear_fbmc_market(unconstrained_prices, dates, ram_scale_factor=ram_scale)

# ==========================================
# 4. KPI METRICS & PLOTLY DASHBOARD
# ==========================================
total_congestion_rent = df["congestion_rent_eur"].sum()
total_de_export = df["de_net_export_mw"][df["de_net_export_mw"] > 0].sum()
avg_spread = df["de_fr_spread_eur"].mean()
peak_loading = (
    df[[
        "cnec1_de_fr_loading_pct",
        "cnec2_de_nl_loading_pct",
        "cnec3_de_at_loading_pct",
    ]]
    .max()
    .max()
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total German Cross-Border Export", f"{total_de_export:,.1f} MWh")
k2.metric("Congestion Rent Captured", f"€{total_congestion_rent:,.2f}")
k3.metric("Avg DE-FR Price Spread", f"€{avg_spread:.2f}/MWh")
k4.metric("Peak Interconnector Utilization", f"{peak_loading:.1f}%")

st.markdown("<hr>", unsafe_allow_html=True)

pure_blue_legend = dict(
    orientation="h",
    yanchor="bottom",
    y=1.05,
    xanchor="right",
    x=1.0,
    bgcolor="#003cd2",
    bordercolor="#ffffff",
    borderwidth=2,
    font=dict(color="#ffffff", size=12, family="Arial, sans-serif"),
)

pure_blue_hover = dict(
    bgcolor="#002db3",
    bordercolor="#ffffff",
    font=dict(color="#ffffff", size=13, family="Arial, sans-serif"),
)

st.markdown("#### 1. Core Region Zonal Price Formation & Convergence (€/MWh)")
fig1 = go.Figure()
fig1.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["de_price_eur"],
        name="Germany (DE)",
        line=dict(color="#0284c7", width=2.2),
    )
)
fig1.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["fr_price_eur"],
        name="France (FR)",
        line=dict(color="#ef4444", width=2.0),
    )
)
fig1.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["nl_price_eur"],
        name="Netherlands (NL)",
        line=dict(color="#10b981", width=1.6, dash="dot"),
    )
)
fig1.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["at_price_eur"],
        name="Austria (AT)",
        line=dict(color="#f59e0b", width=1.6, dash="dash"),
    )
)

fig1.update_layout(
    template="plotly_dark",
    plot_bgcolor="#060913",
    paper_bgcolor="#060913",
    height=420,
    margin=dict(l=20, r=20, t=55, b=20),
    legend=pure_blue_legend,
    hoverlabel=pure_blue_hover,
    xaxis=dict(gridcolor="#1e293b", title="Timeline"),
    yaxis=dict(gridcolor="#1e293b", title="Cleared Price [€/MWh]"),
    hovermode="x unified",
)
st.plotly_chart(fig1, use_container_width=True)

st.markdown(
    "#### 2. Cross-Border Net Commercial Positions (MW) & CNEC Saturation"
)
fig2 = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.10,
    subplot_titles=(
        "Zonal Commercial Net Position (Export > 0, Import < 0)",
        "DE-FR Interconnector Physical Loading (%)",
    ),
)

fig2.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["de_net_export_mw"],
        name="DE Net Position",
        line=dict(color="#0284c7", width=2.0),
    ),
    row=1,
    col=1,
)
fig2.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["fr_net_export_mw"],
        name="FR Net Position",
        line=dict(color="#ef4444", width=2.0),
    ),
    row=1,
    col=1,
)

fig2.add_trace(
    go.Scatter(
        x=df["timestamp"],
        y=df["cnec1_de_fr_loading_pct"],
        name="DE-FR Loading (%)",
        line=dict(color="#f59e0b", width=2.2),
    ),
    row=2,
    col=1,
)
fig2.add_hline(y=100.0, line_dash="dash", line_color="#ef4444", row=2, col=1)

fig2.update_layout(
    template="plotly_dark",
    plot_bgcolor="#060913",
    paper_bgcolor="#060913",
    height=500,
    margin=dict(l=20, r=20, t=55, b=20),
    legend=pure_blue_legend,
    hoverlabel=pure_blue_hover,
    hovermode="x unified",
)
fig2.update_xaxes(gridcolor="#1e293b")
fig2.update_yaxes(gridcolor="#1e293b")

st.plotly_chart(fig2, use_container_width=True)
