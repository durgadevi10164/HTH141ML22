"""
tests/test_streamlit_frontend.py
--------------------------------
Tests for the Streamlit frontend (frontend_streamlit/).

* API client + data layer: run against the REAL Flask app, served on a random
  local port and called over real HTTP (no mocks). Needs only requirements.txt.
* Chart builders: run only if plotly is installed.
* Full-app render: run only if streamlit is installed. Uses Streamlit's official
  headless `AppTest` runner against the live test server.

Run:  python tests/run_all.py     (or)     python -m unittest tests/test_streamlit_frontend.py -v
"""
import importlib.util
import os
import socket
import sys
import threading
import unittest

import _setup  # noqa: F401  (adds backend/ to sys.path, provides ensure_project_ready)

FRONTEND_DIR = os.path.join(_setup.BASE_DIR, "frontend_streamlit")
# Appended (not prepended) so the backend's `app` module is never shadowed by frontend_streamlit/app.py
if FRONTEND_DIR not in sys.path:
    sys.path.append(FRONTEND_DIR)

from api_client import APIError, DMartAPI  # noqa: E402
import data_utils as du  # noqa: E402


def _installed(name):
    return importlib.util.find_spec(name) is not None


class LiveBackendTestCase(unittest.TestCase):
    """Starts the real Flask app on 127.0.0.1:<random port> for the duration of the class."""

    @classmethod
    def setUpClass(cls):
        from werkzeug.serving import make_server
        _setup.ensure_project_ready()
        from app import create_app  # backend/app.py
        cls.server = make_server("127.0.0.1", 0, create_app(), threaded=True)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api = DMartAPI(cls.base_url)
        cls.session = cls.api.login("regional_manager", "RSM001")   # the API is role-protected

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)


class TestApiClient(LiveBackendTestCase):
    def test_health(self):
        self.assertEqual(self.api.health()["status"], "ok")

    def test_login_logout_flow(self):
        roles = {r["key"] for r in DMartAPI(self.base_url).roles()}
        self.assertEqual(roles, {"branch_manager", "inventory_manager", "warehouse_manager", "regional_manager"})
        api = DMartAPI(self.base_url)
        with self.assertRaises(APIError) as ctx:                      # not logged in
            api.branches()
        self.assertEqual(ctx.exception.kind, "unauthorized")
        with self.assertRaises(APIError) as ctx:                      # ID belongs to a different role
            api.login("branch_manager", "WM001")
        self.assertEqual(ctx.exception.kind, "unauthorized")
        session = api.login("branch_manager", "BM002")
        self.assertEqual(session["user"]["branch_id"], "B02")
        self.assertEqual([b["branch_id"] for b in api.branches()], ["B02"])
        with self.assertRaises(APIError) as ctx:                      # another branch is forbidden
            api.forecast("B01", "SKU001", 7)
        self.assertEqual(ctx.exception.kind, "forbidden")
        api.logout()
        with self.assertRaises(APIError):
            DMartAPI(self.base_url, token=session["token"]).branches()   # the old token no longer works

    def test_catalog(self):
        branches = self.api.branches()
        products, categories = self.api.products()
        self.assertEqual(len(branches), 5)
        self.assertEqual(len(products), 20)
        self.assertEqual(len(categories), 5)
        self.assertTrue({"branch_id", "branch_name"} <= set(branches[0]))

    def test_dashboard_is_consistent(self):
        d = self.api.dashboard("SKU001", 7, 5000)
        rows = d["allocation_table"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(d["stockout_risk_counts"].values()), 5)
        self.assertEqual(d["kpis"]["predicted_demand"], int(round(sum(r["forecast_demand"] for r in rows))))
        self.assertLessEqual(d["warehouse_panel"]["allocated"], d["warehouse_panel"]["warehouse_available"])
        self.assertEqual(len(d["demand_trend"]["forecast"]), 7)
        self.assertEqual(len(d["demand_trend"]["historical"]), 30)
        self.assertEqual(d["top_priority_branch"]["branch_id"], rows[0]["branch_id"])

    def test_allocation_never_exceeds_warehouse(self):
        for stock in (0, 100, 1000, 5000):
            r = self.api.allocation("SKU001", 7, stock)
            self.assertLessEqual(r["total_allocated"], stock)
            self.assertEqual(r["total_allocated"], sum(a["recommended_allocation"] for a in r["allocations"]))

    def test_forecast_and_inventory(self):
        f = self.api.forecast("B02", "SKU001", 14)
        self.assertEqual(len(f["daily_predictions"]), 14)
        inv = self.api.inventory(sku_id="SKU001")
        self.assertEqual(len(inv), 5)

    def test_metrics_and_festivals(self):
        m = self.api.metrics()
        self.assertTrue({"mae", "rmse", "mape"} <= set(m))
        fests = self.api.festivals()
        self.assertGreater(len(fests), 0)
        self.assertTrue({"festival", "expected_demand_increase_pct", "high_risk_skus"} <= set(fests[0]))

    def test_festivals_client_sends_branch_and_sku(self):
        def diwali(**kw):
            return next(f for f in self.api.festivals(**kw) if f["festival"] == "Diwali")
        chain, podanur, podanur_rice = diwali(), diwali(branch_id="B02"), diwali(branch_id="B02", sku_id="SKU001")
        self.assertNotEqual(chain["expected_demand_increase_pct"], podanur["expected_demand_increase_pct"])
        self.assertNotEqual(podanur["expected_demand_increase_pct"], podanur_rice["expected_demand_increase_pct"])
        self.assertEqual([s["sku_id"] for s in podanur_rice["high_risk_skus"]], ["SKU001"])

    def test_http_errors_become_apierror(self):
        with self.assertRaises(APIError) as ctx:
            self.api.allocation("NOT_A_SKU", 7, 100)
        self.assertEqual(ctx.exception.kind, "http")
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("sku_id", ctx.exception.message)
        with self.assertRaises(APIError) as ctx:
            self.api.forecast("B01", "SKU001", 9)
        self.assertIn("horizon", ctx.exception.message.lower())

    def test_backend_down_becomes_apierror(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()  # nothing is listening on this port any more
        with self.assertRaises(APIError) as ctx:
            DMartAPI(f"http://127.0.0.1:{free_port}").branches()
        self.assertEqual(ctx.exception.kind, "connection")
        self.assertTrue(ctx.exception.backend_unreachable)

    def test_malformed_url_becomes_apierror(self):
        with self.assertRaises(APIError) as ctx:
            DMartAPI("not-a-url").health()
        self.assertEqual(ctx.exception.kind, "config")

    def test_non_json_response_becomes_apierror(self):
        # The backend serves HTML (not JSON) at "/" - the client must not crash on it.
        with self.assertRaises(APIError):
            DMartAPI(self.base_url)._request("GET", "/")


class TestDataUtils(LiveBackendTestCase):
    def setUp(self):
        self.dash = self.api.dashboard("SKU001", 7, 300)
        self.df = du.allocations_to_df(self.dash["allocation_table"])

    def test_display_table_has_exactly_the_requested_columns(self):
        t = du.build_display_table(self.df)
        self.assertEqual(list(t.columns), ["Branch", "SKU", "Forecast Demand", "Current Stock", "Safety Stock",
                                           "Shortage", "Stockout Risk", "Recommended Allocation"])
        self.assertEqual(len(t), 5)

    def test_display_table_branch_filter(self):
        t = du.build_display_table(self.df, "B03")
        self.assertEqual(len(t), 1)
        self.assertIn("(B03)", t.iloc[0]["Branch"])

    def test_styler_renders_risk_colours(self):
        html = du.style_display_table(du.build_display_table(self.df)).to_html()
        self.assertIn(du.RISK_COLORS["CRITICAL"], html)

    def test_slider_config_is_always_valid(self):
        for required in (0, 50, 1098, 4000, 25000):
            for current in (0, 137, 5000, 100000):
                c = du.whatif_slider_config(required, current)
                self.assertLessEqual(c["min"], c["value"])
                self.assertLessEqual(c["value"], c["max"])
                self.assertEqual(c["value"] % c["step"], 0)
                self.assertEqual(c["max"] % c["step"], 0)

    def test_compare_allocations(self):
        sim = self.api.allocation("SKU001", 7, 1000)
        cmp_df = du.compare_allocations(self.dash["allocation_table"], sim["allocations"])
        self.assertEqual(len(cmp_df), 5)
        self.assertTrue((cmp_df["delta"] == cmp_df["sim_alloc"] - cmp_df["baseline_alloc"]).all())
        self.assertTrue(cmp_df["fill_rate_pct"].between(0, 100).all())
        tbl = du.whatif_display_table(cmp_df)
        self.assertIn("Simulated Allocation", tbl.columns)
        self.assertIn("<td", du.style_whatif_table(tbl).to_html())

    def test_trend_summary(self):
        h, f = du.trend_frames(self.dash["demand_trend"]["historical"], self.dash["demand_trend"]["forecast"])
        s = du.trend_summary(h, f)
        self.assertGreater(s["avg_hist"], 0)
        self.assertAlmostEqual(s["total_fc"], f["predicted_units"].sum())
        s2 = du.trend_summary(*du.trend_frames(None, self.dash["demand_trend"]["forecast"]))
        self.assertIsNone(s2["avg_hist"])
        self.assertIsNone(s2["change_pct"])

    def test_formatters(self):
        self.assertEqual(du.fmt_int(12345.6), "12,346")
        self.assertEqual(du.fmt_int(None), "-")
        self.assertEqual(du.fmt_pct(22), "22.0%")
        self.assertEqual(du.safe_pct(5, 0), 0.0)

    def test_impact_bands(self):
        self.assertEqual(du.impact_band(44.3)[0], "Very high")
        self.assertEqual(du.impact_band(0.1)[0], "Low")


@unittest.skipUnless(_installed("plotly"), "plotly not installed")
class TestCharts(LiveBackendTestCase):
    def test_all_figures_build(self):
        import charts
        d = self.api.dashboard("SKU001", 7, 5000)
        df = du.allocations_to_df(d["allocation_table"])
        risk = dict(zip(df["branch_id"], df["stockout_risk"]))
        stock = dict(zip(df["branch_id"], df["current_stock"]))
        fig = charts.branch_demand_chart(d["branch_demand_chart"], risk, stock, highlight_branch_id="B01")
        self.assertGreaterEqual(len(fig.data), 2)

        h, f = du.trend_frames(d["demand_trend"]["historical"], d["demand_trend"]["forecast"])
        trend = charts.trend_chart(h, f)
        names = [t.name for t in trend.data if t.name]
        self.assertTrue(any("Historical" in n for n in names) and any("Forecast" in n for n in names))
        charts.trend_chart(du.trend_frames(None, d["demand_trend"]["forecast"])[0],
                           du.trend_frames(None, d["demand_trend"]["forecast"])[1])  # forecast-only

        sim = self.api.allocation("SKU001", 7, 500)
        charts.whatif_chart(du.compare_allocations(d["allocation_table"], sim["allocations"]))
        charts.festival_chart(du.festivals_sorted(self.api.festivals()))


@unittest.skipUnless(_installed("streamlit"), "streamlit not installed")
class TestStreamlitAppRenders(LiveBackendTestCase):
    def _run(self, url=None, login_as=("regional_manager", "RSM001")):
        import api_client
        from streamlit.testing.v1 import AppTest
        api_client.DEFAULT_BASE_URL = url or self.base_url
        at = AppTest.from_file(os.path.join(FRONTEND_DIR, "app.py"), default_timeout=180)
        if login_as:   # start already signed in, as the login form would have left the session
            s = DMartAPI(self.base_url).login(*login_as)
            at.session_state["auth"] = {"token": s["token"], "user": s["user"],
                                        "permissions": s["permissions"], "base_url": api_client.DEFAULT_BASE_URL}
        return at.run()

    def test_app_renders_with_real_data(self):
        at = self._run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        self.assertGreaterEqual(len(at.metric), 10)  # warehouse panel + simulator + festivals + model metrics

    def test_branch_filter_does_not_crash(self):
        at = self._run()
        at.selectbox[0].select_index(3).run()   # a non-top-priority branch -> forecast-only trend path
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])

    def test_login_page_is_shown_before_the_dashboard(self):
        at = self._run(login_as=None)
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        self.assertEqual(len(at.metric), 0)      # no dashboard content without a session
        self.assertTrue(any(sb.label == "Role" for sb in at.selectbox))

    def test_branch_manager_dashboard_renders(self):
        at = self._run(login_as=("branch_manager", "BM002"))
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        branch_box = next(sb for sb in at.selectbox if sb.label == "Branch")
        self.assertEqual(len(branch_box.options), 1)                      # only their own branch
        self.assertIn("Podanur", branch_box.options[0])

    def test_inventory_and_warehouse_roles_render(self):
        for who in (("inventory_manager", "IM001"), ("warehouse_manager", "WM001")):
            at = self._run(login_as=who)
            self.assertEqual(len(at.exception), 0, (who, [e.value for e in at.exception]))

    def test_backend_down_shows_message_not_traceback(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        at = self._run(url=f"http://127.0.0.1:{port}", login_as=None)
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Backend unavailable" in e.value for e in at.error))


if __name__ == "__main__":
    unittest.main(verbosity=2)
