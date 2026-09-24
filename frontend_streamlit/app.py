"""
DMart SmartStock AI - Streamlit dashboard
=========================================
A frontend for the existing Flask backend. It ONLY calls the REST API
(default http://127.0.0.1:5000) - no forecasting or allocation logic lives here.

Run (from the project root, with the Flask backend already running):
    streamlit run frontend_streamlit/app.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so sibling modules import from any cwd

import pandas as pd
import streamlit as st

import api_client
import charts
import data_utils as du
import styles
from api_client import APIError, DMartAPI

# ------------------------------------------------------------------ page setup
st.set_page_config(
    page_title="DMart SmartStock AI",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(styles.CSS, unsafe_allow_html=True)

DEFAULT_SKU = "SKU001"          # Rice 5kg - the backend's own demo default
DEFAULT_HORIZON = 7
DEFAULT_WAREHOUSE = 5000
ALL_BRANCHES = "__ALL__"
ALL_CATEGORIES = "All categories"

# Demo IDs listed on the login page (set DMART_SHOW_DEMO_IDS=0 to hide the list).
SHOW_DEMO_IDS = os.environ.get("DMART_SHOW_DEMO_IDS", "1") != "0"
DEMO_IDS_HELP = (
    "**Branch Manager:** BM001 Singanallur · BM002 Podanur · BM003 Mettupalayam Road · "
    "BM004 Chinniyampalayam · BM005 Sulur  \n"
    "**Inventory Manager:** IM001  \n"
    "**Warehouse / Distribution Manager:** WM001  \n"
    "**Regional Supply Chain Manager:** RSM001"
)
TAB_LABELS = {
    "overview": "Overview",
    "inventory": "Inventory",
    "allocation": "Allocation",
    "whatif": "What-If Simulator",
    "peak": "Peak Demand Monitor",
    "model": "Model Performance",
}


# ------------------------------------------------------------------ cached API calls
# (wrappers take base_url so the cache is keyed per backend; APIError is never cached)
# The login token is part of every cache key, so one user's role-scoped data is never served to another.
@st.cache_data(ttl=300, show_spinner=False)
def load_catalog(base_url: str, token: str):
    api = DMartAPI(base_url, token=token)
    products, categories = api.products()
    return api.branches(), products, categories


@st.cache_data(ttl=120, show_spinner=False)
def load_dashboard(base_url: str, token: str, sku_id: str, horizon: int, warehouse: int):
    return DMartAPI(base_url, token=token).dashboard(sku_id, horizon, warehouse)


@st.cache_data(ttl=120, show_spinner=False)
def load_allocation(base_url: str, token: str, sku_id: str, horizon: int, warehouse: int):
    return DMartAPI(base_url, token=token).allocation(sku_id, horizon, warehouse)


@st.cache_data(ttl=120, show_spinner=False)
def load_forecast(base_url: str, token: str, branch_id: str, sku_id: str, horizon: int):
    return DMartAPI(base_url, token=token).forecast(branch_id, sku_id, horizon)


@st.cache_data(ttl=120, show_spinner=False)
def load_inventory(base_url: str, token: str, sku_id: str = ""):
    return DMartAPI(base_url, token=token).inventory(sku_id=sku_id or None)


@st.cache_data(ttl=600, show_spinner=False)
def load_festivals(base_url: str, token: str, branch_id: str = "", sku_id: str = ""):
    # the selected branch / SKU are sent to the backend, which recalculates from the sales history
    return DMartAPI(base_url, token=token).festivals(branch_id=branch_id or None, sku_id=sku_id or None)


@st.cache_data(ttl=600, show_spinner=False)
def load_metrics(base_url: str, token: str):
    return DMartAPI(base_url, token=token).metrics()


# ------------------------------------------------------------------ small UI helpers
def show_chart(fig) -> None:
    st.plotly_chart(fig, use_container_width=True, theme=None)


def show_table(data, height=None) -> None:
    kwargs = {"hide_index": True, "use_container_width": True}
    if height:
        kwargs["height"] = height
    try:
        st.dataframe(data, **kwargs)
    except TypeError:  # newer Streamlit releases replaced use_container_width with width="stretch"
        kwargs.pop("use_container_width", None)
        st.dataframe(data, width="stretch", **kwargs)


def guarded(section_name: str, fn, *args) -> None:
    """Run one dashboard section; a failure shows a message but never takes down the page."""
    try:
        fn(*args)
    except APIError as e:
        if e.kind == "unauthorized":
            force_relogin("Your session has expired. Please log in again.")
        if e.kind == "forbidden":
            st.warning(f"**{section_name}** is not available for your role.")
            return
        st.warning(f"**{section_name}** could not be loaded: {e.message}")
    except Exception as e:  # noqa: BLE001 - last-resort net so one bad section can't crash the app
        st.error(f"Unexpected problem while rendering **{section_name}**: {e}")
        with st.expander("Technical details"):
            st.exception(e)


def render_backend_down(err: APIError, base_url: str) -> None:
    st.error(f"**Backend unavailable.** {err.message}")
    st.markdown(
        "This dashboard is only a frontend - it needs the Flask API to be running.\n\n"
        "1. Open a terminal in the project folder and start the backend:"
    )
    st.code("python backend/app.py", language="bash")
    st.markdown(
        f"2. Confirm it responds: open <{base_url}/api/health> in your browser (you should see `\"status\": \"ok\"`).\n"
        "3. Come back here and press **Retry connection** (or use *Backend API URL* in the sidebar if the server runs elsewhere).",
    )
    if st.button("Retry connection", type="primary"):
        st.cache_data.clear()
        st.rerun()


def force_relogin(message: str) -> None:
    """Drop the local session and show the login page (used when the backend says 401)."""
    st.session_state.pop("auth", None)
    st.session_state["login_notice"] = message
    st.rerun()


def render_login(base_url: str) -> None:
    """Role + Employee ID login. The backend validates that the ID belongs to the selected role."""
    api = DMartAPI(base_url)
    try:
        roles = api.roles()
    except APIError as err:
        st.error(f"Could not load the login form: {err.message}")
        st.stop()

    notice = st.session_state.pop("login_notice", None)
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        with st.container(border=True):
            st.markdown(styles.section("Sign in", "Select your role and enter your unique Employee ID to open your dashboard."),
                        unsafe_allow_html=True)
            if notice:
                st.info(notice)
            with st.form("login_form", clear_on_submit=False):
                role_labels = {r["key"]: r["label"] for r in roles}
                role_key = st.selectbox("Role", list(role_labels), format_func=lambda k: role_labels[k])
                employee_id = st.text_input("Employee ID", placeholder="e.g. BM002", max_chars=20)
                submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                try:
                    session = api.login(role_key, employee_id)
                except APIError as err:
                    st.error(err.message or "Login failed.")
                else:
                    st.session_state["auth"] = {
                        "token": session["token"], "user": session["user"],
                        "permissions": session["permissions"], "base_url": base_url,
                    }
                    st.rerun()
            if SHOW_DEMO_IDS:
                with st.expander("Demo Employee IDs"):
                    st.markdown(DEMO_IDS_HELP)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### DMart SmartStock AI")
    base_url = st.text_input(
        "Backend API URL", value=api_client.DEFAULT_BASE_URL,
        help="Where the Flask backend is listening. Override the default with the DMART_API_URL environment variable.",
    ).strip().rstrip("/") or api_client.DEFAULT_BASE_URL
    if st.button("Refresh data", help="Clear cached API responses and reload everything."):
        st.cache_data.clear()
    status_slot = st.empty()

# ------------------------------------------------------------------ header
st.markdown(styles.hero(), unsafe_allow_html=True)
st.markdown(styles.disclaimer(), unsafe_allow_html=True)

# ------------------------------------------------------------------ connect + catalog
try:
    DMartAPI(base_url).health()
except APIError as err:
    status_slot.markdown(styles.status_pill(False, "Backend offline"), unsafe_allow_html=True)
    render_backend_down(err, base_url)
    st.stop()

status_slot.markdown(styles.status_pill(True, "Backend connected"), unsafe_allow_html=True)

# ------------------------------------------------------------------ login gate
auth = st.session_state.get("auth")
if auth and auth.get("base_url") != base_url:   # the backend URL changed: the old token belongs to another server
    st.session_state.pop("auth", None)
    auth = None
if not auth:
    render_login(base_url)
    st.stop()

user = auth["user"]
perms = auth["permissions"]
token = auth["token"]
branch_locked = bool(perms["branch_locked"])   # Branch Managers: fixed to their own branch

try:
    branches, products, categories = load_catalog(base_url, token)
except APIError as err:
    if err.kind == "unauthorized":
        force_relogin("Your session has expired. Please log in again.")
    render_backend_down(err, base_url)
    st.stop()

with st.sidebar:
    st.caption(f"Connected to `{base_url}`")
    st.markdown("---")
    st.markdown(f"**{user['name']}**")
    who = f"{user['role_label']} · ID {user['employee_id']}"
    if user.get("branch_name"):
        who += f" · {user['branch_name']}"
    st.caption(who)
    if st.button("Log out", help="End this session and return to the login page."):
        try:
            DMartAPI(base_url, token=token).logout()
        except APIError:
            pass   # the local session is dropped either way
        st.session_state.pop("auth", None)
        st.rerun()
    st.markdown("---")
    st.caption(
        "All numbers are computed by the Flask backend (RandomForest forecast + priority-based "
        "allocation engine) from **synthetic** data. This UI only displays them."
    )

branch_name_by_id = {b["branch_id"]: b["branch_name"] for b in branches}
product_by_id = {p["sku_id"]: p for p in products}

# ------------------------------------------------------------------ filters
with st.container(border=True):
    st.markdown('<div class="filter-title">Filters</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = st.columns([1.35, 1.35, 1.7, 1.0, 1.3])

    if branch_locked:   # Branch Manager: the branch is fixed by the role (and enforced again by the backend)
        branch_choice = f1.selectbox(
            "Branch", [user["branch_id"]],
            format_func=lambda b: f"{branch_name_by_id.get(b, user['branch_name'])} ({b})",
            disabled=True, help="Your branch is fixed by your role.",
        )
    else:
        branch_choice = f1.selectbox(
            "Branch", [ALL_BRANCHES] + list(branch_name_by_id),
            format_func=lambda b: "All branches" if b == ALL_BRANCHES else f"{branch_name_by_id[b]} ({b})",
            help="Focuses the trend chart, bar highlight and allocation table on one branch. "
                 "Allocation itself is always computed across the whole chain.",
        )
    category = f2.selectbox("Category", [ALL_CATEGORIES] + list(categories))
    sku_options = [p["sku_id"] for p in products if category == ALL_CATEGORIES or p["category"] == category]
    sku_id = f3.selectbox(
        "SKU", sku_options,
        index=sku_options.index(DEFAULT_SKU) if DEFAULT_SKU in sku_options else 0,
        format_func=lambda s: f"{product_by_id[s]['product_name']} ({s})",
    )
    horizon = f4.selectbox("Forecast horizon", [7, 14, 28], index=[7, 14, 28].index(DEFAULT_HORIZON),
                           format_func=lambda d: f"{d} days")
    if perms["can_set_warehouse_stock"]:
        warehouse = int(f5.number_input("Warehouse stock (units)", min_value=0, value=DEFAULT_WAREHOUSE, step=100,
                                        help="Limited central stock available to distribute across branches."))
    else:   # Branch / Inventory managers do not control the warehouse figure
        warehouse = DEFAULT_WAREHOUSE

focus_branch = None if branch_choice == ALL_BRANCHES else branch_choice
product = product_by_id[sku_id]

# ------------------------------------------------------------------ load dashboard
try:
    with st.spinner("Running demand forecast and allocation..."):
        dash = load_dashboard(base_url, token, sku_id, horizon, warehouse)
except APIError as err:
    if err.kind == "unauthorized":
        force_relogin("Your session has expired. Please log in again.")
    st.error(f"Could not build the dashboard: {err.message}")
    if err.backend_unreachable:
        render_backend_down(err, base_url)
    st.stop()

kpis = dash["kpis"]
panel = dash.get("warehouse_panel")   # None for roles that do not see warehouse totals
alloc_df = du.allocations_to_df(dash["allocation_table"])
top = dash.get("top_priority_branch")
risk_by_branch = dict(zip(alloc_df["branch_id"], alloc_df["stockout_risk"])) if not alloc_df.empty else {}
stock_by_branch = dict(zip(alloc_df["branch_id"], alloc_df["current_stock"])) if not alloc_df.empty else {}

# ------------------------------------------------------------------ KPI cards
scope_text = f"{user['branch_name']} figures" if branch_locked else "chain-wide figures"
st.markdown(
    styles.section(f"{product['product_name']} - next {horizon} days",
                   f"{product['category']} / {product['subcategory']} · {scope_text} for the selected SKU"),
    unsafe_allow_html=True,
)
stockouts = int(kpis["potential_stockouts"])
if "warehouse_stock" in kpis:   # Regional Supply Chain Manager / Warehouse Manager: the full chain-wide cards
    util = float(kpis["allocation_utilization_pct"])
    k = st.columns(6)
    k[0].markdown(styles.kpi_card("Total Branches", du.fmt_int(kpis["total_branches"]), "Simulated stores", "info"), unsafe_allow_html=True)
    k[1].markdown(styles.kpi_card("Total SKUs", du.fmt_int(kpis["total_skus"]), f"{len(categories)} categories", "info"), unsafe_allow_html=True)
    k[2].markdown(styles.kpi_card("Warehouse Stock", du.fmt_int(kpis["warehouse_stock"]), "Units available to allocate"), unsafe_allow_html=True)
    k[3].markdown(styles.kpi_card("Predicted Demand", du.fmt_int(kpis["predicted_demand"]), f"Units across all branches, {horizon} days"), unsafe_allow_html=True)
    k[4].markdown(styles.kpi_card("Potential Stockouts", du.fmt_int(stockouts),
                                  "Branches at HIGH / CRITICAL risk" if stockouts else "No branch at HIGH / CRITICAL risk",
                                  "danger" if stockouts else "ok"), unsafe_allow_html=True)
    k[5].markdown(styles.kpi_card("Allocation Utilization", du.fmt_pct(util), "Warehouse stock allocated", "", bar_pct=util), unsafe_allow_html=True)
elif "current_stock" in kpis:   # Branch Manager: their own branch only
    risk = kpis["stockout_risk"]
    k = st.columns(6)
    k[0].markdown(styles.kpi_card("Current Stock", du.fmt_int(kpis["current_stock"]), "Units in your branch", "info"), unsafe_allow_html=True)
    k[1].markdown(styles.kpi_card("Safety Stock", du.fmt_int(kpis["safety_stock"]), "Buffer to keep on hand", "info"), unsafe_allow_html=True)
    k[2].markdown(styles.kpi_card("Predicted Demand", du.fmt_int(kpis["predicted_demand"]), f"Units at your branch, {horizon} days"), unsafe_allow_html=True)
    k[3].markdown(styles.kpi_card("Shortage", du.fmt_int(kpis["shortage"]), "Additional units required",
                                  "danger" if kpis["shortage"] else "ok"), unsafe_allow_html=True)
    k[4].markdown(styles.kpi_card("Stockout Risk", risk, du.RISK_MEANING.get(risk, ""),
                                  "danger" if risk in ("HIGH", "CRITICAL") else ("" if risk == "MEDIUM" else "ok")), unsafe_allow_html=True)
    k[5].markdown(styles.kpi_card("Recommended Allocation", du.fmt_int(kpis["recommended_allocation"]), "Units allocated to your branch"), unsafe_allow_html=True)
else:   # Inventory Manager: inventory / demand / risk across all branches (no warehouse allocation)
    k = st.columns(4)
    k[0].markdown(styles.kpi_card("Total Branches", du.fmt_int(kpis["total_branches"]), "Simulated stores", "info"), unsafe_allow_html=True)
    k[1].markdown(styles.kpi_card("Total SKUs", du.fmt_int(kpis["total_skus"]), f"{len(categories)} categories", "info"), unsafe_allow_html=True)
    k[2].markdown(styles.kpi_card("Predicted Demand", du.fmt_int(kpis["predicted_demand"]), f"Units across all branches, {horizon} days"), unsafe_allow_html=True)
    k[3].markdown(styles.kpi_card("Potential Stockouts", du.fmt_int(stockouts),
                                  "Branches at HIGH / CRITICAL risk" if stockouts else "No branch at HIGH / CRITICAL risk",
                                  "danger" if stockouts else "ok"), unsafe_allow_html=True)
st.write("")

# Only the tabs the backend granted to this role are shown (the backend also enforces this per endpoint).
tab_keys = [k for k in perms["tabs"] if k in TAB_LABELS]
tab_by_key = dict(zip(tab_keys, st.tabs([TAB_LABELS[k] for k in tab_keys])))


def show_tab(key: str, section_name: str, fn) -> None:
    tab = tab_by_key.get(key)
    if tab is None:
        return
    with tab:
        guarded(section_name, fn)


# ================================================================== OVERVIEW
def render_overview() -> None:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(styles.section("Predicted demand by branch",
                                   "Bars: forecast demand (coloured by stockout risk) · Diamonds: current stock"),
                    unsafe_allow_html=True)
        show_chart(charts.branch_demand_chart(dash["branch_demand_chart"], risk_by_branch,
                                              stock_by_branch, highlight_branch_id=focus_branch))
    with right:
        st.markdown(styles.section("Stockout risk summary", "Number of branches in each risk band"),
                    unsafe_allow_html=True)
        st.markdown(styles.risk_grid(du.risk_counts_ordered(dash["stockout_risk_counts"])), unsafe_allow_html=True)
        n_bad = sum(dash["stockout_risk_counts"].get(lv, 0) for lv in ("HIGH", "CRITICAL"))
        total = sum(dash["stockout_risk_counts"].values())
        st.write("")
        if branch_locked:
            if n_bad:
                st.warning(f"**Your branch** is at {kpis['stockout_risk']} risk of stocking out of "
                           f"{product['product_name']} within {horizon} days.")
            else:
                st.success(f"Your branch has adequate cover for {product['product_name']}.")
        elif n_bad:
            st.warning(f"**{n_bad} of {total} branches** are at HIGH or CRITICAL risk of stocking out of "
                       f"{product['product_name']} within {horizon} days.")
        else:
            st.success(f"All {total} branches have adequate cover for {product['product_name']}.")

    st.markdown("---")
    # ---- trend: historical vs forecast
    trend = dash["demand_trend"]
    trend_branch = trend["branch_id"]
    hist, fc_rows, shown_branch = trend["historical"], trend["forecast"], trend_branch
    note = None
    if focus_branch and focus_branch != trend_branch:
        top_name = branch_name_by_id.get(trend_branch, trend_branch)
        try:
            fc = load_forecast(base_url, token, focus_branch, sku_id, horizon)
            hist, fc_rows, shown_branch = None, fc["daily_predictions"], focus_branch
            note = (f"Historical sales are only exposed by the API for the highest-priority branch ({top_name}), "
                    f"so {branch_name_by_id[focus_branch]} shows the forecast only. Choose *All branches* or "
                    f"*{top_name}* to see the historical comparison.")
        except APIError as e:
            note = (f"Could not load the forecast for {branch_name_by_id[focus_branch]} ({e.message}). "
                    f"Showing the highest-priority branch ({top_name}) instead.")
    hist_df, fc_df = du.trend_frames(hist, fc_rows)
    summary = du.trend_summary(hist_df, fc_df)

    title = f"Demand trend - {branch_name_by_id.get(shown_branch, shown_branch)}"
    subtitle = ("Highest-priority branch · " if shown_branch == trend_branch and not focus_branch else "") + \
        "Last 30 days of actual sales vs the ML forecast"
    st.markdown(styles.section(title, subtitle), unsafe_allow_html=True)
    if note:
        st.info(note)
    show_chart(charts.trend_chart(hist_df, fc_df))

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Forecast total ({horizon} days)", du.fmt_int(summary["total_fc"]) + " units")
    m2.metric("Avg daily forecast", f"{summary['avg_fc']:.1f} units" if summary["avg_fc"] is not None else "-")
    if summary["avg_hist"] is not None:
        m3.metric("Avg daily (last 30 days)", f"{summary['avg_hist']:.1f} units",
                  delta=f"{summary['change_pct']:+.1f}% forecast vs actual" if summary["change_pct"] is not None else None,
                  delta_color="off")
    else:
        m3.metric("Avg daily (last 30 days)", "n/a")


show_tab("overview", "Overview", render_overview)


# ================================================================== INVENTORY (Inventory Manager)
def render_inventory() -> None:
    st.markdown(styles.section("Inventory across all branches and SKUs",
                               "Current stock, safety stock and reorder level per branch and SKU "
                               "(narrow it with the Branch and Category filters above)"),
                unsafe_allow_html=True)
    inv = pd.DataFrame(load_inventory(base_url, token))
    if inv.empty:
        st.info("No inventory rows returned.")
        return
    if focus_branch:
        inv = inv[inv["branch_id"] == focus_branch]
    if category != ALL_CATEGORIES:
        inv = inv[inv["category"] == category]
    c = st.columns(3)
    c[0].metric("Inventory lines", du.fmt_int(len(inv)))
    c[1].metric("Branches", du.fmt_int(inv["branch_id"].nunique()))
    c[2].metric("Total units in stock", du.fmt_int(inv["current_stock"].sum()))
    st.write("")
    inv = inv[["branch_name", "product_name", "category", "current_stock", "safety_stock", "reorder_level"]]
    inv.columns = ["Branch", "Product", "Category", "Current Stock", "Safety Stock", "Reorder Level"]
    show_table(inv, height=460)
    st.download_button("Download inventory as CSV", du.allocation_csv(inv), file_name="inventory.csv", mime="text/csv")


show_tab("inventory", "Inventory", render_inventory)


# ================================================================== ALLOCATION
def render_allocation() -> None:
    # ---- warehouse panel (Warehouse / Regional managers only - it holds chain-wide totals)
    if panel:
        st.markdown(styles.section("Warehouse panel", "How the limited warehouse stock meets branch requirements"),
                    unsafe_allow_html=True)
        w = st.columns(5)
        w[0].metric("Warehouse Available", du.fmt_int(panel["warehouse_available"]))
        w[1].metric("Total Required", du.fmt_int(panel["total_required"]))
        w[2].metric("Allocated", du.fmt_int(panel["allocated"]))
        w[3].metric("Unmet Requirement", du.fmt_int(panel["unmet_requirement"]))
        w[4].metric("Allocation Utilization", du.fmt_pct(panel["allocation_utilization_pct"]))
        st.progress(min(max(float(panel["allocation_utilization_pct"]) / 100.0, 0.0), 1.0),
                    text=f"{du.fmt_int(panel['allocated'])} of {du.fmt_int(panel['warehouse_available'])} warehouse units allocated")
        if panel["warehouse_available"] <= 0:
            st.error(f"Warehouse stock is 0 - nothing can be allocated, so the full requirement of "
                     f"{du.fmt_int(panel['total_required'])} units is unmet.")
        elif panel["unmet_requirement"] > 0:
            st.warning(f"The warehouse cannot cover every branch: **{du.fmt_int(panel['unmet_requirement'])} units** of "
                       "requirement remain unmet. Lower-priority branches receive nothing or a partial amount.")
        else:
            left_over = panel["warehouse_available"] - panel["allocated"]
            st.success(f"Every branch's requirement is fully covered, leaving **{du.fmt_int(left_over)} units** unallocated in the warehouse.")
        st.write("")

    # ---- highest priority branch (for a Branch Manager: their own branch)
    if top:
        row = du.top_branch_row(alloc_df, top["branch_id"]) or {}
        st.markdown(
            styles.priority_card(
                top["branch_name"], top["branch_id"], top["reason"], row.get("stockout_risk", "CRITICAL"),
                {
                    "Priority score": f"{row.get('priority_score', 0):.1f}",
                    "Forecast demand": du.fmt_int(row.get("forecast_demand")),
                    "Current stock": du.fmt_int(row.get("current_stock")),
                    "Shortage": du.fmt_int(row.get("shortage")),
                    "Recommended allocation": du.fmt_int(row.get("recommended_allocation")),
                },
                tag="Your branch" if branch_locked else "Highest priority branch",
            ),
            unsafe_allow_html=True,
        )
    st.write("")

    # ---- allocation table
    st.markdown(styles.section("Allocation table",
                               "Your branch's recommendation" if branch_locked else "Sorted by priority (most urgent first)"),
                unsafe_allow_html=True)
    table = du.build_display_table(alloc_df, focus_branch)
    if branch_locked:
        st.caption("The recommendation comes from the chain-wide allocation, which serves the most urgent branches first. "
                   "Other branches' figures are not shown to your role.")
    elif focus_branch:
        st.caption(f"Showing {branch_name_by_id[focus_branch]} only. The allocation is still computed across all "
                   f"{len(alloc_df)} branches - choose *All branches* to see them all.")
    show_table(du.style_display_table(table), height=min(38 * (len(table) + 1) + 3, 460))
    st.download_button("Download allocation as CSV", du.allocation_csv(du.build_display_table(alloc_df)),
                       file_name=f"allocation_{sku_id}_{horizon}d_{warehouse}units.csv", mime="text/csv")

    with st.expander("Why was your branch prioritised?" if branch_locked else "Why was each branch prioritised?"):
        for _, r in alloc_df.iterrows():
            rank = "" if branch_locked else f"#{r['priority_rank']} "   # a rank would only be the row's position (1) for one branch
            st.markdown(f"**{rank}{r['branch_name']}** - priority score {r['priority_score']:.1f}, "
                        f"allocated {du.fmt_int(r['recommended_allocation'])} of {du.fmt_int(r['shortage'])} needed. "
                        f"{r['allocation_reason']}")
    with st.expander("Current inventory for this SKU (from /api/inventory)"):
        inv = pd.DataFrame(load_inventory(base_url, token, sku_id))
        if inv.empty:
            st.info("No inventory rows returned.")
        else:
            inv = inv[["branch_name", "product_name", "current_stock", "safety_stock", "reorder_level"]]
            inv.columns = ["Branch", "Product", "Current Stock", "Safety Stock", "Reorder Level"]
            show_table(inv)


show_tab("allocation", "Allocation", render_allocation)


# ================================================================== WHAT-IF
def render_whatif() -> None:
    if not panel:   # only roles that see warehouse totals can run the simulator (the backend enforces this too)
        st.warning("**What-If Simulator** is not available for your role.")
        return
    st.markdown(styles.section("What-if warehouse stock simulator",
                               "Drag the slider to see how a different warehouse stock changes who gets what - "
                               "the backend re-runs the allocation each time."),
                unsafe_allow_html=True)
    cfg = du.whatif_slider_config(panel["total_required"], warehouse)
    sim_stock = st.slider("Simulated warehouse stock (units)", min_value=cfg["min"], max_value=cfg["max"],
                          value=cfg["value"], step=cfg["step"],
                          help=f"Range covers 0 to ~1.5x the total requirement ({du.fmt_int(panel['total_required'])} units).")
    if warehouse > cfg["max"]:
        st.caption(f"Your baseline warehouse stock ({du.fmt_int(warehouse)}) is above this slider's range because the "
                   f"total requirement is only {du.fmt_int(panel['total_required'])} units.")

    sim = load_allocation(base_url, token, sku_id, horizon, int(sim_stock))
    cmp_df = du.compare_allocations(dash["allocation_table"], sim["allocations"])
    base_alloc, base_unmet = int(panel["allocated"]), int(panel["unmet_requirement"])
    base_util = float(panel["allocation_utilization_pct"])
    served_now = du.branches_fully_served(cmp_df, "sim_alloc")
    served_base = du.branches_fully_served(cmp_df, "baseline_alloc")

    s = st.columns(4)
    s[0].metric("Allocated", du.fmt_int(sim["total_allocated"]),
                delta=f"{sim['total_allocated'] - base_alloc:+,} vs baseline", delta_color="off")
    s[1].metric("Unmet requirement", du.fmt_int(sim["unmet_requirement"]),
                delta=f"{sim['unmet_requirement'] - base_unmet:+,} vs baseline", delta_color="inverse")
    s[2].metric("Allocation utilization", du.fmt_pct(sim["allocation_utilization_pct"]),
                delta=f"{sim['allocation_utilization_pct'] - base_util:+.1f} pts vs baseline", delta_color="off")
    s[3].metric("Branches fully served", f"{served_now} of {len(cmp_df)}",
                delta=f"{served_now - served_base:+d} vs baseline", delta_color="normal")

    if sim["unmet_requirement"] > 0:
        st.warning(f"At {du.fmt_int(sim_stock)} units, **{du.fmt_int(sim['unmet_requirement'])} units** of requirement go unmet. "
                   f"Top priority branch: **{sim['top_priority_branch']['branch_name']}**.")
    else:
        st.success(f"At {du.fmt_int(sim_stock)} units every branch is fully covered.")

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown(styles.section("Simulated allocation table"), unsafe_allow_html=True)
        sim_df = du.allocations_to_df(sim["allocations"])
        show_table(du.style_display_table(du.build_display_table(sim_df, focus_branch)),
                   height=min(38 * (len(sim_df) + 1) + 3, 320))
    with right:
        st.markdown(styles.section("Baseline vs simulated, per branch"), unsafe_allow_html=True)
        show_chart(charts.whatif_chart(cmp_df))

    st.markdown(styles.section("Change vs baseline", f"Baseline = {du.fmt_int(warehouse)} units (from the filter above)"),
                unsafe_allow_html=True)
    show_table(du.style_whatif_table(du.whatif_display_table(cmp_df)))


show_tab("whatif", "What-If Simulator", render_whatif)


# ================================================================== PEAK DEMAND
def render_peak() -> None:
    st.markdown(styles.section("Peak demand monitor",
                               "How much demand rises on each simulated festival vs a normal day, "
                               "recalculated by the backend from the historical sales data for your selection."),
                unsafe_allow_html=True)
    # The Branch filter above and this SKU scope are sent to the backend, which recalculates
    # the baseline, festival uplift, top SKUs and buffer from ONLY the matching rows.
    sku_scope = st.radio(
        "SKU scope", ["selected", "all"], horizontal=True, key="peak_sku_scope",
        format_func=lambda v: f"Selected SKU only - {product['product_name']}" if v == "selected" else "All SKUs",
        help="Use the SKU chosen in the filters above, or analyse every SKU.",
    )
    peak_branch = focus_branch                       # None = all branches (always the own branch for a Branch Manager)
    peak_sku = sku_id if sku_scope == "selected" else None
    branch_text = branch_name_by_id[peak_branch] if peak_branch else "All branches"
    sku_text = product["product_name"] if peak_sku else "All SKUs"
    fests = du.festivals_sorted(load_festivals(base_url, token, peak_branch or "", peak_sku or ""))
    st.caption(f"Scope: **{branch_text}** · **{sku_text}**")
    if not fests:
        st.info("The backend returned no festival data for this selection.")
        return
    n_rec = fests[0].get("festival_records")
    if n_rec is not None and n_rec <= 5:
        st.caption(f"Narrow selections rest on few data points ({n_rec} record(s) per festival in the synthetic history), "
                   "so the percentages can swing a lot.")
    top_f = fests[0]
    c = st.columns(3)
    c[0].metric("Festivals monitored", len(fests))
    c[1].metric("Biggest demand spike", top_f["festival"], delta=f"{top_f['expected_demand_increase_pct']:+.1f}% vs normal day", delta_color="off")
    c[2].metric("Largest recommended buffer", f"{du.fmt_int(max(f['recommended_additional_inventory'] for f in fests))} units")
    st.write("")
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown(styles.section("Expected demand increase"), unsafe_allow_html=True)
        show_chart(charts.festival_chart(fests))
        st.caption("Impact bands (presentation only): Very high >= 40%, High >= 30%, Moderate >= 15%, Low < 15%.")
    with right:
        g1, g2 = st.columns(2)
        for i, f in enumerate(fests):
            (g1 if i % 2 == 0 else g2).markdown(styles.festival_card(f), unsafe_allow_html=True)


show_tab("peak", "Peak Demand Monitor", render_peak)


# ================================================================== MODEL METRICS
def render_model() -> None:
    m = load_metrics(base_url, token)
    st.markdown(styles.section("Forecasting model performance",
                               "Measured on a held-out test split of the synthetic dataset (not real-world accuracy)."),
                unsafe_allow_html=True)
    c = st.columns(4)
    c[0].metric("MAE", f"{m['mae']:.2f} units", help="Mean Absolute Error - the average size of a daily forecast miss.")
    c[1].metric("RMSE", f"{m['rmse']:.2f} units", help="Root Mean Squared Error - like MAE but penalises large misses more.")
    c[2].metric("MAPE", f"{m['mape']:.2f}%", help="Mean Absolute Percentage Error - the average miss relative to actual sales.")
    c[3].metric("Test rows", du.fmt_int(m.get("n_test_rows")), help="Number of branch/SKU/day records the metrics were computed on.")
    st.write("")
    st.info(
        f"On average the model's daily prediction is off by about **{m['mae']:.1f} units** "
        f"(roughly **{m['mape']:.1f}%** of actual sales). RMSE ({m['rmse']:.1f}) is higher than MAE because it "
        "penalises the larger misses more heavily."
    )


show_tab("model", "Model Performance", render_model)
