"""
tests/test_auth_roles.py
--------------------------
Role-based login and BACKEND data scoping. Every check here talks to the Flask API
directly (no frontend), so it proves the filtering is enforced on the server.
"""
import unittest

from _setup import anonymous_client, login

BRANCHES = {"BM001": ("B01", "Singanallur"), "BM002": ("B02", "Podanur"), "BM003": ("B03", "Mettupalayam Road"),
            "BM004": ("B04", "Chinniyampalayam"), "BM005": ("B05", "Sulur")}


def client_for(role, emp):
    c = anonymous_client()
    resp = login(c, role, emp)
    assert resp.status_code == 200, resp.get_json()
    return c


class TestLogin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anon = anonymous_client()

    def test_roles_listed_without_login(self):
        roles = self.anon.get("/api/auth/roles").get_json()["roles"]
        self.assertEqual([r["label"] for r in roles],
                         ["Branch Manager", "Inventory Manager", "Warehouse / Distribution Manager",
                          "Regional Supply Chain Manager"])

    def test_every_demo_id_logs_in_with_its_own_role(self):
        cases = [("branch_manager", emp) for emp in BRANCHES] + [
            ("inventory_manager", "IM001"), ("warehouse_manager", "WM001"), ("regional_manager", "RSM001")]
        for role, emp in cases:
            with self.subTest(role=role, emp=emp):
                r = self.anon.post("/api/auth/login", json={"role": role, "employee_id": emp})
                self.assertEqual(r.status_code, 200)
                body = r.get_json()
                self.assertEqual(body["user"]["role"], role)
                self.assertTrue(body["token"])
        r = self.anon.post("/api/auth/login", json={"role": "branch_manager", "employee_id": "BM002"}).get_json()
        self.assertEqual((r["user"]["branch_id"], r["user"]["branch_name"]), BRANCHES["BM002"])

    def test_id_must_match_selected_role(self):
        wrong = [("branch_manager", "WM001"), ("branch_manager", "IM001"), ("branch_manager", "RSM001"),
                 ("inventory_manager", "BM001"), ("inventory_manager", "WM001"),
                 ("warehouse_manager", "IM001"), ("warehouse_manager", "BM002"),
                 ("regional_manager", "BM001"), ("regional_manager", "WM001"),
                 ("branch_manager", "BM999"), ("branch_manager", "nope"), ("no_such_role", "BM001")]
        for role, emp in wrong:
            with self.subTest(role=role, emp=emp):
                r = self.anon.post("/api/auth/login", json={"role": role, "employee_id": emp})
                self.assertEqual(r.status_code, 401)
                self.assertNotIn("token", r.get_json())

    def test_rejection_message_does_not_reveal_the_ids_real_role(self):
        a = self.anon.post("/api/auth/login", json={"role": "branch_manager", "employee_id": "WM001"}).get_json()
        b = self.anon.post("/api/auth/login", json={"role": "branch_manager", "employee_id": "BM999"}).get_json()
        self.assertEqual(a, b)

    def test_missing_fields_and_case_or_space_in_id(self):
        self.assertEqual(self.anon.post("/api/auth/login", json={"role": "branch_manager"}).status_code, 400)
        self.assertEqual(self.anon.post("/api/auth/login", json={"employee_id": "BM001"}).status_code, 400)
        self.assertEqual(self.anon.post("/api/auth/login", json={}).status_code, 400)
        r = self.anon.post("/api/auth/login", json={"role": "branch_manager", "employee_id": "  bm001 "})
        self.assertEqual(r.status_code, 200)

    def test_protected_endpoints_need_a_token(self):
        for url in ("/api/dashboard", "/api/branches", "/api/products", "/api/inventory", "/api/festivals",
                    "/api/forecast?branch_id=B01&sku_id=SKU001", "/api/metrics", "/api/auth/me"):
            with self.subTest(url=url):
                self.assertEqual(self.anon.get(url).status_code, 401)
        self.assertEqual(self.anon.post("/api/allocation", json={"sku_id": "SKU001"}).status_code, 401)
        bad = self.anon.get("/api/dashboard", headers={"Authorization": "Bearer not-a-real-token"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.anon.get("/api/health").status_code, 200)   # health stays public

    def test_logout_invalidates_the_token(self):
        c = client_for("inventory_manager", "IM001")
        self.assertEqual(c.get("/api/auth/me").status_code, 200)
        self.assertEqual(c.post("/api/auth/logout").status_code, 200)
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual(c.get("/api/dashboard").status_code, 401)


class TestBranchManagerScope(unittest.TestCase):
    """BM001..BM005: every response contains ONLY the manager's own branch."""

    def test_each_branch_manager_sees_only_their_branch(self):
        for emp, (bid, bname) in BRANCHES.items():
            with self.subTest(emp=emp):
                c = client_for("branch_manager", emp)
                d = c.get("/api/dashboard?sku_id=SKU001&horizon_days=7&warehouse_stock=9999").get_json()
                self.assertEqual([a["branch_id"] for a in d["allocation_table"]], [bid])
                self.assertEqual([b["branch_id"] for b in d["branch_demand_chart"]], [bid])
                self.assertEqual(d["demand_trend"]["branch_id"], bid)
                self.assertEqual(d["top_priority_branch"]["branch_id"], bid)
                self.assertEqual(sum(d["stockout_risk_counts"].values()), 1)
                self.assertEqual(d["kpis"]["total_branches"], 1)
                self.assertIsNone(d["warehouse_panel"])            # chain-wide warehouse totals are hidden
                self.assertNotIn("warehouse_stock", d["kpis"])
                row = d["allocation_table"][0]
                self.assertEqual(d["kpis"]["current_stock"], row["current_stock"])
                self.assertEqual(d["kpis"]["shortage"], row["shortage"])
                self.assertEqual([b["branch_id"] for b in c.get("/api/branches").get_json()["branches"]], [bid])
                inv = c.get("/api/inventory").get_json()["inventory"]
                self.assertEqual({r["branch_id"] for r in inv}, {bid})
                self.assertEqual(len(inv), 20)
                # the raw body must not mention any other branch at all
                raw = c.get("/api/dashboard?sku_id=SKU001").get_data(as_text=True)
                for other_id, other_name in BRANCHES.values():
                    if other_id != bid:
                        self.assertNotIn(other_name, raw)

    def test_podanur_manager_numbers_match_the_chain_wide_allocation(self):
        """The branch view is a filtered view of the unchanged allocation, not a re-computation."""
        bm = client_for("branch_manager", "BM002")
        rsm = client_for("regional_manager", "RSM001")
        mine = bm.get("/api/dashboard?sku_id=SKU001&horizon_days=7").get_json()["allocation_table"][0]
        full = rsm.get("/api/dashboard?sku_id=SKU001&horizon_days=7&warehouse_stock=5000").get_json()["allocation_table"]
        chain_row = next(r for r in full if r["branch_id"] == "B02")
        self.assertEqual(mine, chain_row)

    def test_cannot_switch_branch_on_any_endpoint(self):
        c = client_for("branch_manager", "BM002")
        for url in ("/api/forecast?branch_id=B01&sku_id=SKU001&horizon_days=7",
                    "/api/inventory?branch_id=B01",
                    "/api/festivals?branch_id=B01"):
            with self.subTest(url=url):
                self.assertEqual(c.get(url).status_code, 403)
        self.assertEqual(c.post("/api/forecast", json={"branch_id": "B01", "sku_id": "SKU001"}).status_code, 403)
        # their own branch is fine, explicitly or implicitly
        self.assertEqual(c.get("/api/forecast?branch_id=B02&sku_id=SKU001&horizon_days=7").status_code, 200)
        self.assertEqual(c.get("/api/forecast?sku_id=SKU001&horizon_days=7").status_code, 200)
        self.assertEqual(c.get("/api/inventory?branch_id=B02").status_code, 200)

    def test_branch_manager_cannot_use_warehouse_or_model_endpoints(self):
        c = client_for("branch_manager", "BM001")
        self.assertEqual(c.post("/api/allocation", json={"sku_id": "SKU001", "warehouse_stock": 100}).status_code, 403)
        self.assertEqual(c.get("/api/metrics").status_code, 403)

    def test_warehouse_stock_parameter_cannot_change_a_branch_managers_result(self):
        c = client_for("branch_manager", "BM003")
        a = c.get("/api/dashboard?sku_id=SKU001&warehouse_stock=0").get_json()
        b = c.get("/api/dashboard?sku_id=SKU001&warehouse_stock=1000000").get_json()
        self.assertEqual(a["allocation_table"], b["allocation_table"])


class TestOtherRoles(unittest.TestCase):
    def test_inventory_manager_sees_all_branches_without_warehouse_allocation(self):
        c = client_for("inventory_manager", "IM001")
        d = c.get("/api/dashboard?sku_id=SKU001").get_json()
        self.assertEqual({a["branch_id"] for a in d["allocation_table"]}, {"B01", "B02", "B03", "B04", "B05"})
        for a in d["allocation_table"]:
            for hidden in ("recommended_allocation", "priority_score", "allocation_reason"):
                self.assertNotIn(hidden, a)
            self.assertIn("current_stock", a)
            self.assertIn("shortage", a)
            self.assertIn("stockout_risk", a)
        self.assertIsNone(d["warehouse_panel"])
        self.assertIsNone(d["top_priority_branch"])
        self.assertNotIn("warehouse_stock", d["kpis"])
        inv = c.get("/api/inventory").get_json()
        self.assertEqual(inv["count"], 100)                       # 5 branches x 20 SKUs
        self.assertEqual(len(c.get("/api/branches").get_json()["branches"]), 5)
        self.assertEqual(c.get("/api/metrics").status_code, 200)
        self.assertEqual(c.post("/api/allocation", json={"sku_id": "SKU001"}).status_code, 403)

    def test_warehouse_manager_sees_warehouse_and_allocation_but_not_forecast_history(self):
        c = client_for("warehouse_manager", "WM001")
        d = c.get("/api/dashboard?sku_id=SKU001&warehouse_stock=1500").get_json()
        self.assertEqual(d["warehouse_panel"]["warehouse_available"], 1500)
        self.assertEqual(len(d["allocation_table"]), 5)
        self.assertLessEqual(sum(a["recommended_allocation"] for a in d["allocation_table"]), 1500)
        self.assertEqual(d["demand_trend"]["historical"], [])
        self.assertEqual(c.post("/api/allocation", json={"sku_id": "SKU001", "warehouse_stock": 500}).status_code, 200)
        self.assertEqual(c.get("/api/forecast?branch_id=B01&sku_id=SKU001").status_code, 403)
        self.assertEqual(c.get("/api/metrics").status_code, 403)

    def test_regional_manager_gets_the_full_original_dashboard(self):
        c = client_for("regional_manager", "RSM001")
        d = c.get("/api/dashboard?sku_id=SKU001&warehouse_stock=5000").get_json()
        self.assertEqual(len(d["allocation_table"]), 5)
        self.assertIsNotNone(d["warehouse_panel"])
        self.assertEqual(d["kpis"]["warehouse_stock"], 5000)
        self.assertEqual(len(d["demand_trend"]["historical"]), 30)
        for url in ("/api/metrics", "/api/festivals", "/api/inventory", "/api/forecast?branch_id=B04&sku_id=SKU001"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.post("/api/allocation", json={"sku_id": "SKU001"}).status_code, 200)

    def test_role_and_permissions_come_from_the_server_session(self):
        c = client_for("branch_manager", "BM005")
        me = c.get("/api/auth/me").get_json()
        self.assertEqual(me["user"]["branch_id"], "B05")
        self.assertTrue(me["permissions"]["branch_locked"])
        self.assertEqual(me["permissions"]["tabs"], ["overview", "allocation", "peak"])
        # role/branch hints sent by the client are ignored
        d = c.get("/api/dashboard?sku_id=SKU001&role=regional_manager&branch_id=B01").get_json()
        self.assertEqual([a["branch_id"] for a in d["allocation_table"]], ["B05"])


if __name__ == "__main__":
    unittest.main()
