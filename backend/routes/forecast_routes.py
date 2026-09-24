"""routes/forecast_routes.py - /api/forecast (GET + POST), /api/metrics"""
from flask import Blueprint, jsonify, request
from services import data_service, forecast_service, access_service
from services import auth_service as auth
from config import VALID_HORIZONS

forecast_bp = Blueprint("forecast", __name__)


def _validate(branch_id, sku_id, horizon_days):
    if not branch_id or not data_service.branch_exists(branch_id):
        return f"Invalid or missing branch_id '{branch_id}'"
    if not sku_id or not data_service.sku_exists(sku_id):
        return f"Invalid or missing sku_id '{sku_id}'"
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return "Forecast horizon must be an integer"
    if horizon_days not in VALID_HORIZONS:
        return f"Forecast horizon must be one of {VALID_HORIZONS}"
    return None


def _run_forecast(branch_id, sku_id, horizon_days):
    horizon_days = int(horizon_days)
    error = _validate(branch_id, sku_id, horizon_days)
    if error:
        return {"error": error}, 400

    try:
        result = forecast_service.forecast_for(branch_id, sku_id, horizon_days)
    except FileNotFoundError as e:
        return {"error": f"Model not available: {e}"}, 503
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        return {"error": f"Forecast failed: {e}"}, 500

    inv = data_service.get_inventory_for(branch_id, sku_id) or {"current_stock": 0, "safety_stock": 0}
    current_stock = inv["current_stock"]
    safety_stock = inv["safety_stock"]
    shortage = max(0, round((result["total_predicted_demand"] - current_stock) + safety_stock))

    result["current_stock"] = current_stock
    result["safety_stock"] = safety_stock
    result["additional_requirement"] = shortage
    return result, 200


def _guarded_forecast(branch_id, sku_id, horizon_days):
    """Branch Managers may only forecast their own branch (server-side check)."""
    user = auth.current_user()
    if user["role"] == auth.ROLE_BRANCH_MANAGER:
        _, denied = access_service.resolve_branch(user, branch_id or user["branch_id"])
        if denied:
            return denied
        branch_id = branch_id or user["branch_id"]
    body, status = _run_forecast(branch_id, sku_id, horizon_days)
    return jsonify(body), status


@forecast_bp.route("/api/forecast", methods=["GET"])
@auth.login_required("forecast")
def forecast_get():
    branch_id = request.args.get("branch_id")
    sku_id = request.args.get("sku_id")
    horizon_days = request.args.get("horizon_days", 7)
    return _guarded_forecast(branch_id, sku_id, horizon_days)


@forecast_bp.route("/api/forecast", methods=["POST"])
@auth.login_required("forecast")
def forecast_post():
    payload = request.get_json(silent=True) or {}
    branch_id = payload.get("branch_id")
    sku_id = payload.get("sku_id")
    horizon_days = payload.get("horizon_days", 7)
    return _guarded_forecast(branch_id, sku_id, horizon_days)


@forecast_bp.route("/api/metrics", methods=["GET"])
@auth.login_required("metrics")
def metrics():
    try:
        return jsonify({"model_metrics": forecast_service.model_metrics()})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
