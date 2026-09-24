"""
data_utils.py
-------------
Pure pandas / Python helpers that turn the backend's JSON into display-ready
DataFrames and numbers. No Streamlit or Plotly imports here, so this module
is fully unit-testable.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# --------------------------------------------------------------------- constants
RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]           # worst -> best
RISK_COLORS = {"LOW": "#2E9E5B", "MEDIUM": "#E3A72F", "HIGH": "#E8742A", "CRITICAL": "#C62F3B"}
RISK_TINTS = {"LOW": "#E8F6EE", "MEDIUM": "#FDF3DC", "HIGH": "#FDEBDD", "CRITICAL": "#FBE6E8"}
RISK_TEXT = {"LOW": "#1E7A43", "MEDIUM": "#7A5600", "HIGH": "#A8480C", "CRITICAL": "#A32530"}   # readable on tints
RISK_FILL_TEXT = {"LOW": "#FFFFFF", "MEDIUM": "#3D2B00", "HIGH": "#FFFFFF", "CRITICAL": "#FFFFFF"}  # readable on solid fills
RISK_MEANING = {
    "LOW": "Stock covers the forecast",
    "MEDIUM": "60-99% of demand covered",
    "HIGH": "30-59% of demand covered",
    "CRITICAL": "Under 30% of demand covered",
}

# (api/enriched column, display name) - the exact columns requested for the table
TABLE_COLUMNS: List[Tuple[str, str]] = [
    ("branch_label", "Branch"),
    ("sku_label", "SKU"),
    ("forecast_demand", "Forecast Demand"),
    ("current_stock", "Current Stock"),
    ("safety_stock", "Safety Stock"),
    ("shortage", "Shortage"),
    ("stockout_risk", "Stockout Risk"),
    ("recommended_allocation", "Recommended Allocation"),
]
NUMERIC_COLS = ["forecast_demand", "current_stock", "safety_stock", "shortage",
                "recommended_allocation", "priority_score"]


# --------------------------------------------------------------------- formatting
def fmt_int(value: Any) -> str:
    """12345.6 -> '12,346'; None/NaN -> '-'."""
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "-"
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "-"


def fmt_pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def safe_pct(numerator: float, denominator: float) -> float:
    """Percentage that never divides by zero."""
    return (float(numerator) / float(denominator) * 100.0) if denominator else 0.0


# --------------------------------------------------------------------- allocation
def allocations_to_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """API allocation rows -> DataFrame with friendly label columns (order preserved:
    the backend returns rows already sorted by priority)."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["branch_label"] = df["branch_name"].astype(str) + " (" + df["branch_id"].astype(str) + ")"
    df["sku_label"] = df["product_name"].astype(str) + " (" + df["sku_id"].astype(str) + ")"
    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in ("forecast_demand", "current_stock", "safety_stock", "shortage", "recommended_allocation"):
        if c in df.columns:   # role-scoped payloads may omit some columns (e.g. allocation for Inventory Manager)
            df[c] = df[c].round().astype(int)
    df.insert(0, "priority_rank", range(1, len(df) + 1))
    return df


def build_display_table(df: pd.DataFrame, branch_id: Optional[str] = None) -> pd.DataFrame:
    """Selects + renames the 8 requested columns; optionally filters to one branch."""
    if df.empty:
        return pd.DataFrame(columns=[name for _, name in TABLE_COLUMNS])
    view = df if not branch_id else df[df["branch_id"] == branch_id]
    out = view[[src for src, _ in TABLE_COLUMNS]].copy()
    out.columns = [name for _, name in TABLE_COLUMNS]
    return out.reset_index(drop=True)


def _risk_cell_style(value: str) -> str:
    color = RISK_COLORS.get(str(value), "#888888")
    text = RISK_FILL_TEXT.get(str(value), "#FFFFFF")
    return f"background-color: {color}; color: {text}; font-weight: 700; text-align: center;"


def style_display_table(table: pd.DataFrame):
    """Pandas Styler: coloured risk pills + emphasised allocation column + thousands separators."""
    styler = table.style
    mapper = getattr(styler, "map", None) or getattr(styler, "applymap")  # pandas >=2.1 / older
    styler = mapper(_risk_cell_style, subset=["Stockout Risk"])
    num_cols = ["Forecast Demand", "Current Stock", "Safety Stock", "Shortage", "Recommended Allocation"]
    styler = styler.format({c: "{:,.0f}" for c in num_cols})
    styler = styler.set_properties(subset=["Recommended Allocation"],
                                   **{"font-weight": "700", "color": "#0A5C38"})
    return styler


def allocation_csv(table: pd.DataFrame) -> bytes:
    return table.to_csv(index=False).encode("utf-8")


def risk_counts_ordered(counts: Dict[str, int]) -> List[Tuple[str, int]]:
    return [(lvl, int(counts.get(lvl, 0))) for lvl in RISK_LEVELS]


def top_branch_row(df: pd.DataFrame, branch_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if df.empty or not branch_id:
        return None
    match = df[df["branch_id"] == branch_id]
    return None if match.empty else match.iloc[0].to_dict()


# --------------------------------------------------------------------- what-if
def whatif_slider_config(total_required: float, current_warehouse: float) -> Dict[str, int]:
    """Slider range centred on the interesting region (0 .. ~1.5x the requirement).

    Returns dict(min, max, step, value). `value` starts at the current warehouse
    setting, capped to the slider's max so Streamlit never sees an out-of-range default.
    """
    upper = max(int(math.ceil(float(total_required) * 1.5 / 100.0) * 100), 500)
    step = 10 if upper <= 2000 else 50
    value = int(min(max(current_warehouse, 0), upper))
    value = int(round(value / step) * step)
    return {"min": 0, "max": upper, "step": step, "value": value}


def compare_allocations(baseline_rows: List[Dict[str, Any]],
                        sim_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Merge baseline and simulated allocation results per branch."""
    base = pd.DataFrame(baseline_rows)
    sim = pd.DataFrame(sim_rows)
    if base.empty or sim.empty:
        return pd.DataFrame()
    merged = base[["branch_id", "branch_name", "shortage", "recommended_allocation", "stockout_risk"]].rename(
        columns={"recommended_allocation": "baseline_alloc"}
    ).merge(
        sim[["branch_id", "recommended_allocation", "priority_score"]].rename(
            columns={"recommended_allocation": "sim_alloc"}),
        on="branch_id", how="inner",
    )
    merged["delta"] = merged["sim_alloc"] - merged["baseline_alloc"]
    merged["fill_rate_pct"] = [round(safe_pct(a, s), 1) if s > 0 else 100.0
                               for a, s in zip(merged["sim_alloc"], merged["shortage"])]
    merged = merged.sort_values("branch_id").reset_index(drop=True)
    return merged


def whatif_display_table(cmp_df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "Branch": cmp_df["branch_name"] + " (" + cmp_df["branch_id"] + ")",
        "Shortage": cmp_df["shortage"].astype(int),
        "Baseline Allocation": cmp_df["baseline_alloc"].astype(int),
        "Simulated Allocation": cmp_df["sim_alloc"].astype(int),
        "Change": cmp_df["delta"].astype(int),
        "Shortage Covered (%)": cmp_df["fill_rate_pct"].astype(float),
        "Stockout Risk": cmp_df["stockout_risk"],
    })
    return out


def style_whatif_table(table: pd.DataFrame):
    styler = table.style
    mapper = getattr(styler, "map", None) or getattr(styler, "applymap")

    def delta_style(v):
        if v > 0:
            return "color: #0A5C38; font-weight: 700;"
        if v < 0:
            return "color: #C62F3B; font-weight: 700;"
        return "color: #5B6F68;"

    styler = mapper(_risk_cell_style, subset=["Stockout Risk"])
    styler = mapper(delta_style, subset=["Change"])
    styler = styler.format({
        "Shortage": "{:,.0f}", "Baseline Allocation": "{:,.0f}",
        "Simulated Allocation": "{:,.0f}", "Change": "{:+,.0f}",
        "Shortage Covered (%)": "{:.1f}%",
    })
    styler = styler.set_properties(subset=["Simulated Allocation"], **{"font-weight": "700"})
    return styler


def branches_fully_served(cmp_df: pd.DataFrame, column: str) -> int:
    """Number of branches whose shortage is fully covered by the given allocation column."""
    if cmp_df.empty:
        return 0
    return int((cmp_df[column] >= cmp_df["shortage"]).sum())


# --------------------------------------------------------------------- trend
def trend_frames(hist: Optional[List[Dict[str, Any]]],
                 forecast: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    hist_df = pd.DataFrame(hist or [], columns=["date", "units_sold"])
    fc_df = pd.DataFrame(forecast or [], columns=["date", "predicted_units"])
    return hist_df, fc_df


def trend_summary(hist_df: pd.DataFrame, fc_df: pd.DataFrame) -> Dict[str, Optional[float]]:
    avg_hist = float(hist_df["units_sold"].mean()) if not hist_df.empty else None
    avg_fc = float(fc_df["predicted_units"].mean()) if not fc_df.empty else None
    change = None
    if avg_hist and avg_fc is not None:
        change = (avg_fc - avg_hist) / avg_hist * 100.0
    return {
        "avg_hist": avg_hist,
        "avg_fc": avg_fc,
        "total_fc": float(fc_df["predicted_units"].sum()) if not fc_df.empty else None,
        "change_pct": change,
    }


# --------------------------------------------------------------------- festivals
def impact_band(pct: float) -> Tuple[str, str]:
    """Presentation-only bucket for the festival demand uplift: (label, colour)."""
    if pct >= 40:
        return "Very high", RISK_COLORS["CRITICAL"]
    if pct >= 30:
        return "High", RISK_COLORS["HIGH"]
    if pct >= 15:
        return "Moderate", RISK_COLORS["MEDIUM"]
    return "Low", RISK_COLORS["LOW"]


def festivals_sorted(festivals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(festivals, key=lambda f: f.get("expected_demand_increase_pct", 0), reverse=True)
