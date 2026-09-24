import unittest
from _setup import ensure_project_ready  # noqa: F401  (ensures backend path is on sys.path)

from allocation.engine import allocate_warehouse_stock, compute_shortage, stockout_risk_level


SAMPLE_REQUIREMENTS = [
    {"branch_id": "B01", "branch_name": "Singanallur", "sku_id": "SKU001", "product_name": "Rice 5kg",
     "forecast_demand": 700, "current_stock": 100, "safety_stock": 50},
    {"branch_id": "B02", "branch_name": "Podanur", "sku_id": "SKU001", "product_name": "Rice 5kg",
     "forecast_demand": 550, "current_stock": 80, "safety_stock": 50},
    {"branch_id": "B03", "branch_name": "Mettupalayam Road", "sku_id": "SKU001", "product_name": "Rice 5kg",
     "forecast_demand": 400, "current_stock": 150, "safety_stock": 50},
    {"branch_id": "B04", "branch_name": "Chinniyampalayam", "sku_id": "SKU001", "product_name": "Rice 5kg",
     "forecast_demand": 300, "current_stock": 200, "safety_stock": 50},
]


class TestAllocationEngine(unittest.TestCase):

    def test_shortage_never_negative(self):
        s = compute_shortage(forecast_demand=100, current_stock=500, safety_stock=20)
        self.assertEqual(s, 0)

    def test_shortage_basic_math(self):
        s = compute_shortage(forecast_demand=735, current_stock=420, safety_stock=100)
        self.assertEqual(s, 415)

    def test_stockout_risk_levels(self):
        self.assertEqual(stockout_risk_level(100, 150, 0), "LOW")
        self.assertEqual(stockout_risk_level(100, 20, 80), "CRITICAL")

    def test_allocation_never_exceeds_warehouse_stock_when_scarce(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=1500)
        total_allocated = sum(a["recommended_allocation"] for a in result["allocations"])
        self.assertLessEqual(total_allocated, 1500)
        self.assertEqual(result["total_allocated"], total_allocated)

    def test_allocation_never_exceeds_warehouse_stock_when_zero(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=0)
        total_allocated = sum(a["recommended_allocation"] for a in result["allocations"])
        self.assertEqual(total_allocated, 0)

    def test_allocation_fully_covers_when_warehouse_is_abundant(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=100000)
        total_required = sum(
            compute_shortage(r["forecast_demand"], r["current_stock"], r["safety_stock"])
            for r in SAMPLE_REQUIREMENTS
        )
        self.assertEqual(result["total_allocated"], total_required)
        self.assertEqual(result["unmet_requirement"], 0)

    def test_allocation_prioritizes_higher_shortage_first(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=650)
        top = max(result["allocations"], key=lambda a: a["priority_score"])
        self.assertEqual(top["branch_id"], "B01")

    def test_allocation_utilization_between_0_and_100(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=1500)
        self.assertGreaterEqual(result["allocation_utilization_pct"], 0)
        self.assertLessEqual(result["allocation_utilization_pct"], 100)

    def test_top_priority_branch_present(self):
        result = allocate_warehouse_stock(SAMPLE_REQUIREMENTS, warehouse_stock=1500)
        self.assertIsNotNone(result["top_priority_branch"])
        self.assertIn("reason", result["top_priority_branch"])


if __name__ == "__main__":
    unittest.main()
