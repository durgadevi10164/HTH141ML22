"""
services/allocation_service.py
---------------------------------
Ties together: forecast demand -> current inventory -> allocation engine,
for a single SKU across all branches (the core "inventory-constrained
allocation" workflow of the product).
"""
from services import data_service, forecast_service
from allocation.engine import allocate_warehouse_stock


def build_allocation_for_sku(sku_id, horizon_days, warehouse_stock):
    branches = data_service.get_branches()
    branch_ids = [b["branch_id"] for b in branches]
    branch_name_lookup = {b["branch_id"]: b["branch_name"] for b in branches}

    products = {p["sku_id"]: p for p in data_service.get_products()}
    product = products.get(sku_id)
    product_name = product["product_name"] if product else sku_id

    forecasts = forecast_service.forecast_all_branches(branch_ids, sku_id, horizon_days)

    branch_requirements = []
    for f in forecasts:
        branch_id = f["branch_id"]
        inv = data_service.get_inventory_for(branch_id, sku_id) or {
            "current_stock": 0, "safety_stock": 0,
        }
        branch_requirements.append({
            "branch_id": branch_id,
            "branch_name": branch_name_lookup.get(branch_id, branch_id),
            "sku_id": sku_id,
            "product_name": product_name,
            "forecast_demand": f["total_predicted_demand"],
            "current_stock": inv["current_stock"],
            "safety_stock": inv["safety_stock"],
        })

    result = allocate_warehouse_stock(branch_requirements, warehouse_stock)
    result["sku_id"] = sku_id
    result["product_name"] = product_name
    result["horizon_days"] = horizon_days
    return result


def build_allocation_for_all_skus(horizon_days, warehouse_stock_per_sku):
    """
    Builds allocation results for every SKU (used by the main dashboard table).
    warehouse_stock_per_sku: the warehouse stock figure applied to EACH sku's
    allocation run (in this simplified demo, one shared warehouse capacity
    number is used per SKU allocation, as configured on the dashboard).
    """
    products = data_service.get_products()
    all_results = []
    for p in products:
        res = build_allocation_for_sku(p["sku_id"], horizon_days, warehouse_stock_per_sku)
        all_results.append(res)
    return all_results
