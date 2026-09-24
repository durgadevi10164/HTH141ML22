"""
services/access_service.py
----------------------------
Server-side data scoping per role. The routes always compute results with the
original (unchanged) forecasting / allocation code and then pass them through
here BEFORE they are returned, so a role can never receive data outside its
scope no matter what the client asks for or hides.

Scope summary
    Branch Manager      -> only their own branch (forced; other branches -> 403)
    Inventory Manager   -> all branches / SKUs, inventory + demand + risk, no warehouse allocation
    Warehouse Manager   -> warehouse stock, shortages and allocation (no demand-trend history)
    Regional Manager    -> everything (the original chain-wide dashboard)
"""
import copy

from flask import jsonify

from services import auth_service as auth
from services import data_service, forecast_service

_ALLOCATION_ONLY_FIELDS = ("recommended_allocation", "priority_score", "allocation_reason")


def _forbidden(message):
    return jsonify({"error": message}), 403


# ------------------------------------------------------------ branch filtering
def resolve_branch(user, requested_branch_id):
    """
    Returns (branch_id_or_None, error_response_or_None).

    Branch Managers are pinned to their own branch: no branch given -> their branch;
    a different branch -> 403. Other roles get whatever they asked for (None = all).
    """
    requested = (requested_branch_id or "").strip() or None
    if user["role"] == auth.ROLE_BRANCH_MANAGER:
        own = user["branch_id"]
        if requested is not None and requested != own:
            return None, _forbidden("Branch Managers can only access their own branch's data.")
        return own, None
    return requested, None


def scope_branches(user, branches):
    if user["role"] == auth.ROLE_BRANCH_MANAGER:
        return [b for b in branches if b["branch_id"] == user["branch_id"]]
    return branches


# ------------------------------------------------------------------- dashboard
def scope_dashboard(user, payload):
    """Reduces the full chain-wide /api/dashboard payload to what `user` may see."""
    role = user["role"]
    if role == auth.ROLE_REGIONAL_MANAGER:
        return payload
    payload = copy.deepcopy(payload)

    if role == auth.ROLE_WAREHOUSE_MANAGER:
        # warehouse view: allocation + shortages; no branch demand-trend history
        payload["demand_trend"] = {"branch_id": None, "historical": [], "forecast": []}
        return payload

    if role == auth.ROLE_INVENTORY_MANAGER:
        rows = sorted(payload["allocation_table"], key=lambda r: r["branch_id"])  # no priority ordering
        for r in rows:
            for f in _ALLOCATION_ONLY_FIELDS:
                r.pop(f, None)
        payload["allocation_table"] = rows
        payload["warehouse_panel"] = None
        payload["top_priority_branch"] = None
        for k in ("warehouse_stock", "allocation_utilization_pct"):
            payload["kpis"].pop(k, None)
        return payload

    if role == auth.ROLE_BRANCH_MANAGER:
        return _branch_only_dashboard(user, payload)

    raise ValueError(f"Unknown role {role!r}")


def _branch_only_dashboard(user, full):
    own = user["branch_id"]
    row = next((dict(r) for r in full["allocation_table"] if r["branch_id"] == own), None)
    if row is None:
        raise ValueError(f"No data for branch {own}")

    sku_id, horizon = full["sku_id"], full["horizon_days"]
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    counts[row["stockout_risk"]] += 1

    forecast = forecast_service.forecast_for(own, sku_id, horizon)
    return {
        "sku_id": sku_id,
        "horizon_days": horizon,
        "kpis": {
            "total_branches": 1,
            "total_skus": full["kpis"]["total_skus"],
            "current_stock": row["current_stock"],
            "safety_stock": row["safety_stock"],
            "predicted_demand": int(round(row["forecast_demand"])),
            "shortage": row["shortage"],
            "stockout_risk": row["stockout_risk"],
            "recommended_allocation": row["recommended_allocation"],
            "potential_stockouts": counts["HIGH"] + counts["CRITICAL"],
        },
        "branch_demand_chart": [{"branch_id": own, "branch_name": row["branch_name"],
                                 "predicted_demand": row["forecast_demand"]}],
        "demand_trend": {
            "branch_id": own,
            "historical": data_service.get_historical_series(own, sku_id, last_n_days=30),
            "forecast": forecast["daily_predictions"],
        },
        "stockout_risk_counts": counts,
        "allocation_table": [row],
        "warehouse_panel": None,   # chain-wide warehouse totals include other branches
        "top_priority_branch": {"branch_id": own, "branch_name": row["branch_name"],
                                "reason": row["allocation_reason"]},
    }
