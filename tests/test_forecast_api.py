import unittest
from _setup import get_test_client


class TestForecastAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()

    def test_forecast_valid_request(self):
        resp = self.client.get("/api/forecast?branch_id=B01&sku_id=SKU001&horizon_days=7")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreaterEqual(data["total_predicted_demand"], 0)
        self.assertEqual(len(data["daily_predictions"]), 7)
        self.assertIn("additional_requirement", data)

    def test_forecast_invalid_branch(self):
        resp = self.client.get("/api/forecast?branch_id=ZZZ&sku_id=SKU001&horizon_days=7")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_forecast_invalid_sku(self):
        resp = self.client.get("/api/forecast?branch_id=B01&sku_id=NOPE&horizon_days=7")
        self.assertEqual(resp.status_code, 400)

    def test_forecast_invalid_horizon(self):
        resp = self.client.get("/api/forecast?branch_id=B01&sku_id=SKU001&horizon_days=3")
        self.assertEqual(resp.status_code, 400)

    def test_forecast_post_matches_get(self):
        resp = self.client.post("/api/forecast", json={"branch_id": "B02", "sku_id": "SKU005", "horizon_days": 14})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["horizon_days"], 14)
        self.assertEqual(len(data["daily_predictions"]), 14)

    def test_metrics_endpoint(self):
        resp = self.client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        metrics = resp.get_json()["model_metrics"]
        self.assertGreaterEqual(metrics["mae"], 0)
        self.assertGreaterEqual(metrics["rmse"], 0)


if __name__ == "__main__":
    unittest.main()
