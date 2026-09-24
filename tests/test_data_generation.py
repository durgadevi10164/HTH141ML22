import os
import unittest
import pandas as pd

from _setup import ensure_project_ready, BASE_DIR

ensure_project_ready()
DATA_DIR = os.path.join(BASE_DIR, "data")


class TestDataGeneration(unittest.TestCase):

    def test_sales_csv_exists_and_has_expected_shape(self):
        path = os.path.join(DATA_DIR, "dmart_synthetic_sales.csv")
        self.assertTrue(os.path.exists(path))
        df = pd.read_csv(path)
        # 5 branches x 20 skus x 365 days = 36500 rows
        self.assertEqual(len(df), 5 * 20 * 365)

    def test_no_negative_sales_or_stock(self):
        df = pd.read_csv(os.path.join(DATA_DIR, "dmart_synthetic_sales.csv"))
        self.assertTrue((df["units_sold"] >= 0).all())
        self.assertTrue((df["opening_stock"] >= 0).all())
        self.assertTrue((df["closing_stock"] >= 0).all())

    def test_branches_and_products_reference_files(self):
        branches = pd.read_csv(os.path.join(DATA_DIR, "branches.csv"))
        products = pd.read_csv(os.path.join(DATA_DIR, "products.csv"))
        self.assertEqual(len(branches), 5)
        self.assertEqual(len(products), 20)

    def test_branches_have_different_demand_levels(self):
        df = pd.read_csv(os.path.join(DATA_DIR, "dmart_synthetic_sales.csv"))
        branch_totals = df.groupby("branch_id")["units_sold"].sum()
        self.assertEqual(branch_totals.nunique(), len(branch_totals))

    def test_festival_flag_boosts_demand(self):
        df = pd.read_csv(os.path.join(DATA_DIR, "dmart_synthetic_sales.csv"))
        fest_avg = df[df["festival_flag"] == 1]["units_sold"].mean()
        normal_avg = df[df["festival_flag"] == 0]["units_sold"].mean()
        self.assertGreater(fest_avg, normal_avg)


if __name__ == "__main__":
    unittest.main()
