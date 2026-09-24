import unittest
from _setup import get_test_client


class TestWarehouseConstraintAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()

    def test_allocation_api_respects_warehouse_constraint(self):
        resp = self.client.post("/api/allocation", json={"sku_id": "SKU005", "horizon_days": 14, "warehouse_stock": 300})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        total_allocated = sum(a["recommended_allocation"] for a in data["allocations"])
        self.assertLessEqual(total_allocated, data["warehouse_stock"])
        self.assertEqual(total_allocated, data["total_allocated"])

    def test_allocation_api_invalid_sku(self):
        resp = self.client.post("/api/allocation", json={"sku_id": "BAD", "horizon_days": 7, "warehouse_stock": 500})
        self.assertEqual(resp.status_code, 400)

    def test_allocation_api_negative_warehouse_rejected(self):
        resp = self.client.post("/api/allocation", json={"sku_id": "SKU001", "horizon_days": 7, "warehouse_stock": -10})
        self.assertEqual(resp.status_code, 400)

    def test_dashboard_endpoint_smoke(self):
        resp = self.client.get("/api/dashboard?sku_id=SKU001&horizon_days=7&warehouse_stock=1500")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        total_allocated = sum(a["recommended_allocation"] for a in data["allocation_table"])
        self.assertLessEqual(total_allocated, data["warehouse_panel"]["warehouse_available"])
        self.assertEqual(data["kpis"]["total_branches"], 5)
        self.assertEqual(data["kpis"]["total_skus"], 20)

    def test_dashboard_falls_back_gracefully_on_bad_sku(self):
        resp = self.client.get("/api/dashboard?sku_id=NOPE&horizon_days=7&warehouse_stock=1500")
        self.assertEqual(resp.status_code, 200)

    def test_inventory_endpoint(self):
        resp = self.client.get("/api/inventory?branch_id=B01")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreater(data["count"], 0)

    def test_festivals_endpoint(self):
        resp = self.client.get("/api/festivals")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreater(len(data["peak_demand_monitor"]), 0)


if __name__ == "__main__":
    unittest.main()
