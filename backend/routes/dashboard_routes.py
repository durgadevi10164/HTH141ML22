"""routes/dashboard_routes.py - /api/dashboard (the main aggregated endpoint the UI uses)"""
from flask import Blueprint, jsonify, request
from services import data_service, allocation_service, forecast_service, access_service
from services import auth_service as auth
from config import VALID_HORIZONS, DEFAULT_WAREHOUSE_STOCK, DEFAULT_FORECAST_HORIZON

dashboard_bp = Blueprint("dashboard", __name__)

DEFAULT_SKU = "SKU001"  # Rice 5kg - used for Demo Mode


@dashboard_bp.route("/api/dashboard", methods=["GET"])
@auth.login_required("dashboard")
def dashboard():
    user = auth.current_user()
    sku_id = request.args.get("sku_id", DEFAULT_SKU)
    horizon_days = request.args.get("horizon_days", DEFAULT_FORECAST_HORIZON)
    warehouse_stock = request.args.get("warehouse_stock", DEFAULT_WAREHOUSE_STOCK)

    if not data_service.sku_exists(sku_id):
        sku_id = DEFAULT_SKU

    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        horizon_days = DEFAULT_FORECAST_HORIZON
    if horizon_days not in VALID_HORIZONS:
        horizon_days = DEFAULT_FORECAST_HORIZON

    try:
        warehouse_stock = float(warehouse_stock)
        if warehouse_stock < 0:
            warehouse_stock = DEFAULT_WAREHOUSE_STOCK
    except (TypeError, ValueError):
        warehouse_stock = DEFAULT_WAREHOUSE_STOCK

    if user["role"] == auth.ROLE_BRANCH_MANAGER:
        # Branch Managers cannot set the shared warehouse figure; their recommendation
        # is computed against the standard warehouse capacity.
        warehouse_stock = DEFAULT_WAREHOUSE_STOCK

    try:
        allocation_result = allocation_service.build_allocation_for_sku(sku_id, horizon_days, warehouse_stock)
    except Exception as e:
        return jsonify({"error": f"Dashboard build failed: {e}"}), 500

    branches = data_service.get_branches()
    products = data_service.get_products()

    allocations = allocation_result["allocations"]
    total_predicted_demand = sum(a["forecast_demand"] for a in allocations)
    stockout_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for a in allocations:
        stockout_counts[a["stockout_risk"]] += 1
    potential_stockouts = stockout_counts["HIGH"] + stockout_counts["CRITICAL"]

    # branch demand chart data (sorted by branch_id for a stable chart order)
    branch_demand_chart = sorted(
        [{"branch_id": a["branch_id"], "branch_name": a["branch_name"], "predicted_demand": a["forecast_demand"]}
         for a in allocations],
        key=lambda x: x["branch_id"],
    )

    # demand trend: historical (last 30 days) + forecast (horizon_days) for the highest-priority branch
    top_branch_id = allocation_result["top_priority_branch"]["branch_id"] if allocation_result["top_priority_branch"] else branches[0]["branch_id"]
    historical = data_service.get_historical_series(top_branch_id, sku_id, last_n_days=30)
    forecast_detail = forecast_service.forecast_for(top_branch_id, sku_id, horizon_days)

    demand_trend = {
        "branch_id": top_branch_id,
        "historical": historical,
        "forecast": forecast_detail["daily_predictions"],
    }

    kpis = {
        "total_branches": len(branches),
        "total_skus": len(products),
        "warehouse_stock": allocation_result["warehouse_stock"],
        "predicted_demand": int(round(total_predicted_demand)),
        "potential_stockouts": potential_stockouts,
        "allocation_utilization_pct": allocation_result["allocation_utilization_pct"],
    }

    full_payload = {
        "sku_id": sku_id,
        "horizon_days": horizon_days,
        "kpis": kpis,
        "branch_demand_chart": branch_demand_chart,
        "demand_trend": demand_trend,
        "stockout_risk_counts": stockout_counts,
        "allocation_table": allocations,
        "warehouse_panel": {
            "warehouse_available": allocation_result["warehouse_stock"],
            "total_required": allocation_result["total_required"],
            "allocated": allocation_result["total_allocated"],
            "unmet_requirement": allocation_result["unmet_requirement"],
            "allocation_utilization_pct": allocation_result["allocation_utilization_pct"],
        },
        "top_priority_branch": allocation_result["top_priority_branch"],
    }

    # Role-based scoping happens HERE, on the server, before anything is returned.
    try:
        return jsonify(access_service.scope_dashboard(user, full_payload))
    except Exception as e:
        return jsonify({"error": f"Dashboard build failed: {e}"}), 500
