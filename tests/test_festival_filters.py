"""
tests/test_festival_filters.py
--------------------------------
The Peak Demand Monitor must be recalculated from the historical dataset for the selected
branch / SKU. The expected numbers below are recomputed independently with pandas straight
from data/dmart_synthetic_sales.csv, so nothing is compared against a hardcoded value.
"""
import os
import unittest

import pandas as pd

import _setup
from _setup import get_test_client, login, anonymous_client

CSV = os.path.join(_setup.BASE_DIR, "data", "dmart_synthetic_sales.csv")


def expected(df, festival, branch=None, sku=None):
    """Independent re-implementation of the definition: festival avg vs normal-day avg."""
    if branch:
        df = df[df["branch_id"] == branch]
    if sku:
        df = df[df["sku_id"] == sku]
    normal = df[df["festival_flag"] == 0]["units_sold"].mean()
    fest = df[df["festival"] == festival]["units_sold"].mean()
    return {"pct": round((fest - normal) / normal * 100, 1),
            "buffer": max(0, int(round(fest - normal)) * df["branch_id"].nunique())}


class TestFestivalFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup.ensure_project_ready()
        cls.client = get_test_client()          # Regional Supply Chain Manager: may pick any branch / SKU
        cls.df = pd.read_csv(CSV, keep_default_na=False, na_values=[""])

    def fest(self, festival="Diwali", **params):
        resp = self.client.get("/api/festivals", query_string=params)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        return next(f for f in body["peak_demand_monitor"] if f["festival"] == festival), body

    def test_all_branches_all_skus_uses_all_rows(self):
        f, body = self.fest()
        e = expected(self.df, "Diwali")
        self.assertEqual(f["expected_demand_increase_pct"], e["pct"])
        self.assertEqual(f["recommended_additional_inventory"], e["buffer"])
        self.assertEqual(body["filters"], {"branch_id": None, "branch_name": None, "sku_id": None, "product_name": None})

    def test_branch_filter_matches_independent_calculation_for_every_branch_and_festival(self):
        festivals = [x["festival"] for x in self.client.get("/api/festivals").get_json()["peak_demand_monitor"]]
        self.assertEqual(len(festivals), 8)
        for branch in ("B01", "B02", "B03", "B04", "B05"):
            for festival in festivals:
                with self.subTest(branch=branch, festival=festival):
                    f, _ = self.fest(festival, branch_id=branch)
                    e = expected(self.df, festival, branch=branch)
                    self.assertEqual(f["expected_demand_increase_pct"], e["pct"])
                    self.assertEqual(f["recommended_additional_inventory"], e["buffer"])

    def test_branch_and_sku_filter_matches_independent_calculation(self):
        for branch, sku in (("B02", "SKU001"), ("B01", "SKU001"), ("B05", "SKU005"), ("B03", "SKU010")):
            with self.subTest(branch=branch, sku=sku):
                f, body = self.fest(branch_id=branch, sku_id=sku)
                e = expected(self.df, "Diwali", branch=branch, sku=sku)
                self.assertEqual(f["expected_demand_increase_pct"], e["pct"])
                self.assertEqual(f["recommended_additional_inventory"], e["buffer"])
                self.assertEqual(body["filters"]["branch_id"], branch)
                self.assertEqual(body["filters"]["sku_id"], sku)

    def test_sku_only_filter_matches_independent_calculation(self):
        f, _ = self.fest(sku_id="SKU001")
        e = expected(self.df, "Diwali", sku="SKU001")
        self.assertEqual(f["expected_demand_increase_pct"], e["pct"])
        self.assertEqual(f["recommended_additional_inventory"], e["buffer"])

    def test_results_change_when_the_branch_changes(self):
        pcts = {b: self.fest(branch_id=b)[0]["expected_demand_increase_pct"] for b in ("B01", "B02", "B03", "B04", "B05")}
        pcts["ALL"] = self.fest()[0]["expected_demand_increase_pct"]
        self.assertGreater(len(set(pcts.values())), 3, pcts)             # the old bug returned one constant
        buffers = {b: self.fest(branch_id=b)[0]["recommended_additional_inventory"] for b in ("B01", "B02", "B03", "B04", "B05")}
        self.assertGreater(len(set(buffers.values())), 1, buffers)

    def test_results_change_when_the_sku_changes(self):
        pcts = {s: self.fest(branch_id="B02", sku_id=s)[0]["expected_demand_increase_pct"]
                for s in ("SKU001", "SKU002", "SKU005", "SKU010")}
        self.assertGreater(len(set(pcts.values())), 2, pcts)

    def test_top_skus_are_limited_to_the_selection(self):
        one, _ = self.fest(branch_id="B02", sku_id="SKU001")
        self.assertEqual([s["sku_id"] for s in one["high_risk_skus"]], ["SKU001"])
        branch_all, _ = self.fest(branch_id="B02")
        self.assertEqual(len(branch_all["high_risk_skus"]), 5)
        chain, _ = self.fest()
        self.assertNotEqual([(s["sku_id"], s["pct_increase"]) for s in branch_all["high_risk_skus"]],
                            [(s["sku_id"], s["pct_increase"]) for s in chain["high_risk_skus"]])

    def test_top_sku_jump_matches_independent_calculation(self):
        f, _ = self.fest(branch_id="B01")
        d = self.df[self.df["branch_id"] == "B01"]
        base = d[d["festival_flag"] == 0].groupby("sku_id")["units_sold"].mean()
        diw = d[d["festival"] == "Diwali"].groupby("sku_id")["units_sold"].mean()
        want = ((diw - base) / base * 100).sort_values(ascending=False).head(5)
        self.assertEqual([s["sku_id"] for s in f["high_risk_skus"]], list(want.index))
        for s in f["high_risk_skus"]:
            self.assertAlmostEqual(s["pct_increase"], want[s["sku_id"]], places=1)

    def test_buffer_is_data_driven_not_a_constant(self):
        # per-branch buffer covers one branch; the chain-wide buffer covers all five
        chain = self.fest()[0]
        self.assertEqual(chain["branches_in_scope"], 5)
        self.assertEqual(self.fest(branch_id="B04")[0]["branches_in_scope"], 1)

    def test_record_counts_show_how_much_data_backs_a_result(self):
        f, _ = self.fest(branch_id="B02", sku_id="SKU001")
        self.assertEqual(f["festival_records"], 1)                        # one festival day x one branch x one SKU
        self.assertGreater(f["baseline_records"], 300)
        chain, _ = self.fest()
        self.assertEqual(chain["festival_records"], 100)                  # 5 branches x 20 SKUs

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(self.client.get("/api/festivals?branch_id=ZZZ").status_code, 400)
        self.assertEqual(self.client.get("/api/festivals?sku_id=NOPE").status_code, 400)

    def test_identical_requests_give_identical_results(self):
        a = self.client.get("/api/festivals?branch_id=B03&sku_id=SKU002").get_json()
        b = self.client.get("/api/festivals?branch_id=B03&sku_id=SKU002").get_json()
        self.assertEqual(a, b)


class TestFestivalScopeByRole(unittest.TestCase):
    def test_branch_manager_festivals_are_forced_to_their_branch(self):
        _setup.ensure_project_ready()
        df = pd.read_csv(CSV, keep_default_na=False, na_values=[""])
        c = anonymous_client()
        login(c, "branch_manager", "BM002")
        body = c.get("/api/festivals").get_json()                          # no branch given -> their own
        self.assertEqual(body["filters"]["branch_id"], "B02")
        diwali = next(f for f in body["peak_demand_monitor"] if f["festival"] == "Diwali")
        self.assertEqual(diwali["expected_demand_increase_pct"], expected(df, "Diwali", branch="B02")["pct"])
        self.assertEqual(c.get("/api/festivals?branch_id=B01").status_code, 403)
        self.assertEqual(c.get("/api/festivals?branch_id=B02&sku_id=SKU001").status_code, 200)

    def test_other_roles_can_choose_any_branch(self):
        for role, emp in (("inventory_manager", "IM001"), ("warehouse_manager", "WM001")):
            c = anonymous_client()
            login(c, role, emp)
            self.assertEqual(c.get("/api/festivals?branch_id=B05").status_code, 200)


if __name__ == "__main__":
    unittest.main()
