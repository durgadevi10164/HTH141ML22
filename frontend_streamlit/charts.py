"""
charts.py
---------
Plotly figure builders. Each function takes plain DataFrames / lists
(produced by data_utils) and returns a `plotly.graph_objects.Figure`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go

from data_utils import RISK_COLORS, RISK_LEVELS

FONT = "Inter, Segoe UI, system-ui, sans-serif"
INK = "#10231E"
MUTED = "#5B6F68"
GRID = "#E6EEEA"
BRAND = "#0E7C4A"
NAVY = "#1B4D6B"
AMBER = "#E8742A"


def _finish(fig: go.Figure, height: int = 360, **layout) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=36, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family=FONT, size=12, color=INK),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        **layout,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickcolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


# ------------------------------------------------------------------ branch demand
def branch_demand_chart(demand_rows: List[Dict[str, Any]],
                        risk_by_branch: Dict[str, str],
                        stock_by_branch: Dict[str, float],
                        highlight_branch_id: Optional[str] = None) -> go.Figure:
    """Bars = predicted demand per branch, coloured by stockout risk.
    Diamonds = current stock, so the gap (= the problem) is visible at a glance."""
    df = pd.DataFrame(demand_rows).sort_values("branch_id").reset_index(drop=True)
    df["risk"] = df["branch_id"].map(risk_by_branch).fillna("LOW")
    df["stock"] = df["branch_id"].map(stock_by_branch)
    order = df["branch_name"].tolist()

    fig = go.Figure()
    for level in RISK_LEVELS:
        sub = df[df["risk"] == level]
        if sub.empty:
            continue
        line_w = [3 if b == highlight_branch_id else 0 for b in sub["branch_id"]]
        fig.add_trace(go.Bar(
            x=sub["branch_name"], y=sub["predicted_demand"], name=f"{level.title()} risk",
            marker=dict(color=RISK_COLORS[level], line=dict(color=INK, width=line_w)),
            text=[f"{v:,.0f}" for v in sub["predicted_demand"]],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>Predicted demand: %{y:,.0f} units<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=df["branch_name"], y=df["stock"], mode="markers", name="Current stock",
        marker=dict(symbol="diamond", size=12, color=INK, line=dict(color="#FFFFFF", width=1.5)),
        hovertemplate="<b>%{x}</b><br>Current stock: %{y:,.0f} units<extra></extra>",
    ))
    _finish(fig, height=380, barmode="overlay",
            xaxis=dict(categoryorder="array", categoryarray=order),
            yaxis=dict(title="Units"), bargap=0.35)
    return fig


# ------------------------------------------------------------------ demand trend
def trend_chart(hist_df: pd.DataFrame, fc_df: pd.DataFrame) -> go.Figure:
    """Historical (solid navy) vs forecast (dashed orange, shaded forecast window)."""
    fig = go.Figure()
    has_hist = not hist_df.empty
    has_fc = not fc_df.empty

    if has_hist:
        fig.add_trace(go.Scatter(
            x=hist_df["date"], y=hist_df["units_sold"], mode="lines", name="Historical (actual units sold)",
            line=dict(color=NAVY, width=2.5),
            hovertemplate="%{x|%d %b %Y}<br>Actual: %{y:,.0f} units<extra></extra>",
        ))
    if has_fc:
        if has_hist:  # thin dotted bridge so the two series read as one timeline
            fig.add_trace(go.Scatter(
                x=[hist_df["date"].iloc[-1], fc_df["date"].iloc[0]],
                y=[hist_df["units_sold"].iloc[-1], fc_df["predicted_units"].iloc[0]],
                mode="lines", line=dict(color=AMBER, width=1.5, dash="dot"),
                hoverinfo="skip", showlegend=False,
            ))
        fig.add_trace(go.Scatter(
            x=fc_df["date"], y=fc_df["predicted_units"], mode="lines+markers", name="Forecast (ML prediction)",
            line=dict(color=AMBER, width=2.5, dash="dash"),
            marker=dict(size=7, color=AMBER, line=dict(color="#FFFFFF", width=1)),
            hovertemplate="%{x|%d %b %Y}<br>Forecast: %{y:,.1f} units<extra></extra>",
        ))
        fig.add_shape(type="rect", x0=fc_df["date"].iloc[0], x1=fc_df["date"].iloc[-1],
                      xref="x", y0=0, y1=1, yref="paper",
                      fillcolor="rgba(232,116,42,0.08)", line=dict(width=0), layer="below")
        fig.add_annotation(x=fc_df["date"].iloc[0], y=1, xref="x", yref="paper",
                           text="Forecast window", showarrow=False, xanchor="left", yanchor="bottom",
                           font=dict(size=11, color=AMBER))
    _finish(fig, height=380, hovermode="x unified",
            xaxis=dict(type="date", tickformat="%d %b"),
            yaxis=dict(title="Units per day", rangemode="tozero"))
    return fig


# ------------------------------------------------------------------ what-if
def whatif_chart(cmp_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    names = cmp_df["branch_name"]
    fig.add_trace(go.Bar(x=names, y=cmp_df["baseline_alloc"], name="Baseline allocation",
                         marker_color="#B9CFC5",
                         hovertemplate="<b>%{x}</b><br>Baseline: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(x=names, y=cmp_df["sim_alloc"], name="Simulated allocation",
                         marker_color=BRAND,
                         hovertemplate="<b>%{x}</b><br>Simulated: %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=names, y=cmp_df["shortage"], mode="markers", name="Branch shortage (requirement)",
                             marker=dict(symbol="diamond", size=12, color=RISK_COLORS["CRITICAL"],
                                         line=dict(color="#FFFFFF", width=1.5)),
                             hovertemplate="<b>%{x}</b><br>Shortage: %{y:,.0f}<extra></extra>"))
    _finish(fig, height=340, barmode="group", bargap=0.3, yaxis=dict(title="Units"))
    return fig


# ------------------------------------------------------------------ festivals
def festival_chart(festivals_sorted_desc: List[Dict[str, Any]]) -> go.Figure:
    names = [f["festival"] for f in festivals_sorted_desc]
    vals = [f["expected_demand_increase_pct"] for f in festivals_sorted_desc]
    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker=dict(color=vals, colorscale=[[0, "#B9CFC5"], [1, "#0A5C38"]], cmin=0),
        text=[f"{v:+.1f}%" for v in vals], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Expected demand vs normal day: %{x:+.1f}%<extra></extra>",
    ))
    _finish(fig, height=max(280, 44 * len(names) + 60), showlegend=False,
            xaxis=dict(title="Expected demand increase vs. a normal day (%)", zeroline=True),
            yaxis=dict(autorange="reversed"))
    fig.update_layout(margin=dict(l=10, r=50, t=10, b=10))
    return fig
