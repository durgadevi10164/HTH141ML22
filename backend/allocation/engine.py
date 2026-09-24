"""
allocation/engine.py
---------------------
Inventory-constrained smart allocation engine.

Given per-branch requirements (forecast demand, current stock, safety
stock) for a SKU and a LIMITED warehouse stock, this engine allocates
the available stock using a priority score rather than a naive equal
split, and guarantees:

    SUM(recommended_allocation) <= warehouse_stock

Priority score formula (0-100+ scale, higher = more urgent):

    shortage_ratio   = shortage / max(forecast_demand, 1)        [0..1+]
    stockout_urgency = shortage / max(current_stock + 1, 1)      [0..inf, capped]
    demand_weight    = forecast_demand / max(avg_forecast, 1)    [relative size]

    priority_score = (0.5 * shortage_ratio
                       + 0.3 * min(stockout_urgency, 3) / 3
                       + 0.2 * min(demand_weight, 3) / 3) * 100

Branches are ranked by priority_score (highest first). Warehouse stock
is allocated branch-by-branch in that order, each branch receiving the
lesser of (its shortage, remaining warehouse stock). This rewards the
branches with the most urgent, high-risk shortages first while never
exceeding the warehouse's available inventory.
"""

from typing import List, Dict


def compute_shortage(forecast_demand: float, current_stock: float, safety_stock: float) -> float:
    """Required additional stock = forecast demand - current usable stock + safety stock."""
    shortage = (forecast_demand - current_stock) + safety_stock
    return max(0.0, round(shortage))


def stockout_risk_level(forecast_demand: float, current_stock: float, shortage: float) -> str:
    """Classifies stockout risk into LOW / MEDIUM / HIGH / CRITICAL."""
    if forecast_demand <= 0:
        return "LOW"
    coverage_ratio = current_stock / forecast_demand  # how much of forecast demand is already covered

    if coverage_ratio >= 1.0:
        return "LOW"
    elif coverage_ratio >= 0.6:
        return "MEDIUM"
    elif coverage_ratio >= 0.3:
        return "HIGH"
    else:
        return "CRITICAL"


def _priority_score(forecast_demand, current_stock, shortage, avg_forecast):
    shortage_ratio = shortage / max(forecast_demand, 1)
    stockout_urgency = shortage / max(current_stock + 1, 1)
    demand_weight = forecast_demand / max(avg_forecast, 1)

    score = (
        0.5 * min(shortage_ratio, 1.0)
        + 0.3 * (min(stockout_urgency, 3) / 3)
        + 0.2 * (min(demand_weight, 3) / 3)
    ) * 100
    return round(score, 2)


def allocate_warehouse_stock(branch_requirements: List[Dict], warehouse_stock: float) -> Dict:
    """
    branch_requirements: list of dicts, each with:
        branch_id, branch_name, sku_id, product_name,
        forecast_demand, current_stock, safety_stock

    Returns a dict with the enriched per-branch allocation results plus a
    warehouse-level summary.
    """
    warehouse_stock = max(0, round(warehouse_stock))

    enriched = []
    forecasts = [b["forecast_demand"] for b in branch_requirements] or [0]
    avg_forecast = sum(forecasts) / len(forecasts)

    for b in branch_requirements:
        shortage = compute_shortage(b["forecast_demand"], b["current_stock"], b["safety_stock"])
        risk = stockout_risk_level(b["forecast_demand"], b["current_stock"], shortage)
        score = _priority_score(b["forecast_demand"], b["current_stock"], shortage, avg_forecast)
        enriched.append({
            **b,
            "shortage": shortage,
            "stockout_risk": risk,
            "priority_score": score,
            "recommended_allocation": 0,
        })

    # Highest priority first; ties broken by larger shortage
    enriched.sort(key=lambda x: (x["priority_score"], x["shortage"]), reverse=True)

    remaining = warehouse_stock
    for b in enriched:
        if remaining <= 0:
            b["recommended_allocation"] = 0
            continue
        alloc = min(b["shortage"], remaining)
        b["recommended_allocation"] = int(alloc)
        remaining -= alloc

    total_required = sum(b["shortage"] for b in enriched)
    total_allocated = sum(b["recommended_allocation"] for b in enriched)
    unmet = max(0, round(total_required - total_allocated))
    utilization = round((total_allocated / warehouse_stock) * 100, 1) if warehouse_stock > 0 else 0.0

    top_priority = enriched[0] if enriched else None

    # safety check invariant (also covered by automated tests)
    assert total_allocated <= warehouse_stock, "Allocation exceeded warehouse stock!"

    for b in enriched:
        b["allocation_reason"] = _explain(b)

    return {
        "warehouse_stock": warehouse_stock,
        "total_required": int(total_required),
        "total_allocated": int(total_allocated),
        "unmet_requirement": int(unmet),
        "allocation_utilization_pct": utilization,
        "top_priority_branch": {
            "branch_id": top_priority["branch_id"],
            "branch_name": top_priority["branch_name"],
            "reason": top_priority["allocation_reason"],
        } if top_priority else None,
        "allocations": enriched,
    }


def _explain(b):
    """Builds a short human-readable justification for this branch's priority/allocation."""
    parts = [
        f"forecast demand of {round(b['forecast_demand'])} units",
        f"only {round(b['current_stock'])} units currently in stock",
        f"a shortage of {b['shortage']} units",
        f"{b['stockout_risk'].lower()} stockout risk",
    ]
    reason = "High forecast demand and low current stock drive a " + parts[3] + \
             f" ({parts[0]}, {parts[1]}, {parts[2]})."
    return reason
