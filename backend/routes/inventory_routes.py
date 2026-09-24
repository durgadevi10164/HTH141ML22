"""routes/inventory_routes.py - /api/inventory"""
from flask import Blueprint, jsonify, request
from services import data_service, access_service
from services import auth_service as auth

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/api/inventory", methods=["GET"])
@auth.login_required("inventory")
def inventory():
    user = auth.current_user()
    branch_id, denied = access_service.resolve_branch(user, request.args.get("branch_id"))
    if denied:
        return denied
    sku_id = request.args.get("sku_id")

    if branch_id and not data_service.branch_exists(branch_id):
        return jsonify({"error": f"Unknown branch_id '{branch_id}'"}), 400
    if sku_id and not data_service.sku_exists(sku_id):
        return jsonify({"error": f"Unknown sku_id '{sku_id}'"}), 400

    rows = data_service.get_inventory(branch_id, sku_id)
    return jsonify({"inventory": rows, "count": len(rows)})
