"""
services/festival_service.py
-------------------------------
Computes "Peak Demand Monitor" insights directly from the historical
synthetic dataset: for each simulated festival, how much demand rose
vs a normal day, which SKUs jump the most, and a recommended extra
inventory buffer.

Everything is recalculated on every request from the sales data, and it is
scoped by the optional `branch_id` / `sku_id` filters:

    branch=None,    sku=None   -> all branches, all SKUs
    branch="B02",   sku=None   -> only Podanur rows
    branch="B02",   sku="SKU001" -> only Podanur + that SKU's rows

The "normal day" baseline, the festival averages, the top-SKU ranking and the
buffer are ALL computed from the same filtered rows, so nothing is shared
between different branch / SKU selections. No percentage or buffer is hardcoded.
"""
from services.data_service import get_sales_dataframe


def peak_demand_monitor(branch_id=None, sku_id=None):
    df = get_sales_dataframe()
    if branch_id:
        df = df[df["branch_id"] == branch_id]
    if sku_id:
        df = df[df["sku_id"] == sku_id]
    if df.empty:
        return []

    normal = df[df["festival_flag"] == 0]
    if normal.empty:
        return []
    baseline = normal.groupby("sku_id")["units_sold"].mean()
    baseline_overall = normal["units_sold"].mean()
    n_branches = int(df["branch_id"].nunique())   # branches inside the selected scope

    festivals = sorted([f for f in df["festival"].dropna().unique() if f])

    output = []
    for festival in festivals:
        fest_df = df[df["festival"] == festival]
        if fest_df.empty:
            continue

        fest_avg = fest_df["units_sold"].mean()
        pct_increase = round(((fest_avg - baseline_overall) / max(baseline_overall, 0.01)) * 100, 1)

        # per-SKU comparison (within the selected scope) to find the biggest % jumps
        sku_avgs = fest_df.groupby(["sku_id", "product_name"])["units_sold"].mean().reset_index()
        sku_avgs["baseline"] = sku_avgs["sku_id"].map(baseline)
        sku_avgs["pct_increase"] = ((sku_avgs["units_sold"] - sku_avgs["baseline"])
                                     / sku_avgs["baseline"].clip(lower=0.01)) * 100
        top_skus = sku_avgs.sort_values("pct_increase", ascending=False).head(5)

        high_risk_skus = [
            {
                "sku_id": r["sku_id"],
                "product_name": r["product_name"],
                "pct_increase": round(r["pct_increase"], 1),
            }
            for _, r in top_skus.iterrows()
        ]

        # extra units per festival day: the average daily uplift of one branch/SKU line,
        # summed across the branches that are in scope (1 for a single branch)
        recommended_buffer_units = int(round(fest_avg - baseline_overall)) * n_branches
        recommended_buffer_units = max(0, recommended_buffer_units)

        output.append({
            "festival": festival,
            "avg_units_on_festival": round(float(fest_avg), 1),
            "avg_units_baseline": round(float(baseline_overall), 1),
            "expected_demand_increase_pct": pct_increase,
            "high_risk_skus": high_risk_skus,
            "recommended_additional_inventory": recommended_buffer_units,
            "festival_records": int(len(fest_df)),     # data points behind this festival's figures
            "baseline_records": int(len(normal)),      # normal-day data points used as the baseline
            "branches_in_scope": n_branches,
        })

    return output
