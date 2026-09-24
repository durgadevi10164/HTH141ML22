"""routes/allocation_routes.py - /api/allocation"""
from flask import Blueprint, jsonify, request
from services import data_service, allocation_service
from services import auth_service as auth
from config import VALID_HORIZONS, DEFAULT_WAREHOUSE_STOCK

allocation_bp = Blueprint("allocation", __name__)


@allocation_bp.route("/api/allocation", methods=["POST"])
@auth.login_required("allocation")
def run_allocation():
    payload = request.get_json(silent=True) or {}
    sku_id = payload.get("sku_id")
    horizon_days = payload.get("horizon_days", 7)
    warehouse_stock = payload.get("warehouse_stock", DEFAULT_WAREHOUSE_STOCK)

    if not sku_id or not data_service.sku_exists(sku_id):
        return jsonify({"error": f"Invalid or missing sku_id '{sku_id}'"}), 400
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return jsonify({"error": "Forecast horizon must be an integer"}), 400
    if horizon_days not in VALID_HORIZONS:
        return jsonify({"error": f"Forecast horizon must be one of {VALID_HORIZONS}"}), 400
    try:
        warehouse_stock = float(warehouse_stock)
    except (TypeError, ValueError):
        return jsonify({"error": "warehouse_stock must be numeric"}), 400
    if warehouse_stock < 0:
        return jsonify({"error": "warehouse_stock cannot be negative"}), 400

    try:
        result = allocation_service.build_allocation_for_sku(sku_id, horizon_days, warehouse_stock)
    except Exception as e:
        return jsonify({"error": f"Allocation failed: {e}"}), 500

    return jsonify(result), 200
