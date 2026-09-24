"""routes/catalog_routes.py - /api/branches, /api/products, /api/festivals"""
from flask import Blueprint, jsonify, request
from services import data_service, festival_service, access_service
from services import auth_service as auth

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.route("/api/branches", methods=["GET"])
@auth.login_required("branches")
def branches():
    user = auth.current_user()
    return jsonify({"branches": access_service.scope_branches(user, data_service.get_branches())})


@catalog_bp.route("/api/products", methods=["GET"])
@auth.login_required("products")
def products():
    return jsonify({
        "products": data_service.get_products(),
        "categories": data_service.get_categories(),
    })


@catalog_bp.route("/api/festivals", methods=["GET"])
@auth.login_required("festivals")
def festivals():
    """Peak Demand Monitor, recalculated from the sales data for the selected branch / SKU.

    Query params (both optional; omit = all):  branch_id, sku_id
    """
    user = auth.current_user()
    branch_id, denied = access_service.resolve_branch(user, request.args.get("branch_id"))
    if denied:
        return denied
    sku_id = (request.args.get("sku_id") or "").strip() or None

    if branch_id and not data_service.branch_exists(branch_id):
        return jsonify({"error": f"Unknown branch_id '{branch_id}'"}), 400
    if sku_id and not data_service.sku_exists(sku_id):
        return jsonify({"error": f"Unknown sku_id '{sku_id}'"}), 400

    try:
        result = festival_service.peak_demand_monitor(branch_id=branch_id, sku_id=sku_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    branch_name = next((b["branch_name"] for b in data_service.get_branches() if b["branch_id"] == branch_id), None)
    product_name = next((p["product_name"] for p in data_service.get_products() if p["sku_id"] == sku_id), None)
    return jsonify({
        "peak_demand_monitor": result,
        "filters": {"branch_id": branch_id, "branch_name": branch_name,
                    "sku_id": sku_id, "product_name": product_name},
    })
