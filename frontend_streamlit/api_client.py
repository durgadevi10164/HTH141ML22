"""
api_client.py
-------------
Thin, Streamlit-free client for the DMart SmartStock AI Flask backend.

This module ONLY consumes the REST API (via `requests`). It contains no
forecasting or allocation logic - that all lives in the backend.

Every failure mode (backend down, timeout, HTTP error, malformed JSON) is
converted into a single `APIError` with a human-readable message, so the UI
layer can show a friendly warning instead of crashing.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_BASE_URL = os.environ.get("DMART_API_URL", "http://127.0.0.1:5000")
CONNECT_TIMEOUT = 3.05   # seconds to establish a connection
READ_TIMEOUT = 90        # seconds to wait for a response (28-day forecasts can take a few seconds)


class APIError(Exception):
    """Raised for any problem talking to the backend.

    kind:
        "connection" - backend not reachable (probably not running)
        "timeout"    - backend reachable but too slow
        "http"       - backend answered with a 4xx/5xx status
        "unauthorized" - HTTP 401: not logged in / session expired / bad credentials
        "forbidden"  - HTTP 403: logged in, but the role may not access this resource
        "invalid"    - backend answered 2xx but the payload was not what we expect
        "config"     - the configured URL is malformed
    """

    def __init__(self, message: str, status: Optional[int] = None,
                 kind: str = "http", url: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.kind = kind
        self.url = url

    @property
    def backend_unreachable(self) -> bool:
        return self.kind in ("connection", "timeout", "config")


class DMartAPI:
    """Client for the Flask REST API."""

    def __init__(self, base_url: Optional[str] = None,
                 session: Optional[requests.Session] = None,
                 token: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.session = session or requests.Session()
        self.token = token   # bearer token from /api/auth/login (sent on every request)

    # ------------------------------------------------------------------ core
    def _request(self, method: str, path: str, *,
                 params: Optional[dict] = None,
                 json: Optional[dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        try:
            resp = self.session.request(
                method, url, params=params, json=json, headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.exceptions.ConnectionError as e:  # includes ConnectTimeout
            raise APIError(
                f"Cannot reach the backend at {self.base_url}. "
                "Is the Flask server running?",
                kind="connection", url=url,
            ) from e
        except requests.exceptions.Timeout as e:
            raise APIError(
                f"The backend at {self.base_url} took too long to respond "
                f"(> {READ_TIMEOUT}s) for {path}.",
                kind="timeout", url=url,
            ) from e
        except (requests.exceptions.MissingSchema,
                requests.exceptions.InvalidSchema,
                requests.exceptions.InvalidURL) as e:
            raise APIError(
                f"'{self.base_url}' is not a valid backend URL "
                "(expected something like http://127.0.0.1:5000).",
                kind="config", url=url,
            ) from e
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request to {path} failed: {e}", kind="connection", url=url) from e

        try:
            payload = resp.json()
        except ValueError:
            snippet = (resp.text or "").strip().replace("\n", " ")[:120]
            raise APIError(
                f"Backend returned a non-JSON response for {path} "
                f"(HTTP {resp.status_code}): {snippet!r}",
                status=resp.status_code, kind="invalid", url=url,
            )

        if not resp.ok:
            msg = payload.get("error") if isinstance(payload, dict) else None
            detail = payload.get("detail") if isinstance(payload, dict) else None
            text = msg or f"HTTP {resp.status_code}"
            if detail:
                text = f"{text} ({detail})"
            kind = {401: "unauthorized", 403: "forbidden"}.get(resp.status_code, "http")
            raise APIError(f"{text}", status=resp.status_code, kind=kind, url=url)

        if not isinstance(payload, dict):
            raise APIError(f"Unexpected response shape from {path}.",
                           status=resp.status_code, kind="invalid", url=url)
        # Some endpoints return HTTP 200 with an {"error": ...} body; treat as an error too.
        if "error" in payload and len(payload) == 1:
            raise APIError(str(payload["error"]), status=resp.status_code, kind="http", url=url)
        return payload

    @staticmethod
    def _need(payload: Dict[str, Any], *keys: str, where: str = "response") -> None:
        missing = [k for k in keys if k not in payload]
        if missing:
            raise APIError(
                f"Backend {where} is missing expected field(s): {', '.join(missing)}.",
                kind="invalid",
            )

    # -------------------------------------------------------------- endpoints
    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/health")

    # ---- authentication
    def roles(self) -> List[Dict[str, Any]]:
        p = self._request("GET", "/api/auth/roles")
        self._need(p, "roles", where="/api/auth/roles response")
        return p["roles"]

    def login(self, role: str, employee_id: str) -> Dict[str, Any]:
        """Logs in; on success the token is stored on this client and the session payload
        ({token, user, permissions}) is returned. Raises APIError(kind="unauthorized") if the
        Employee ID does not match the selected role."""
        p = self._request("POST", "/api/auth/login", json={"role": role, "employee_id": employee_id})
        self._need(p, "token", "user", "permissions", where="/api/auth/login response")
        self.token = p["token"]
        return p

    def me(self) -> Dict[str, Any]:
        p = self._request("GET", "/api/auth/me")
        self._need(p, "user", "permissions", where="/api/auth/me response")
        return p

    def logout(self) -> None:
        self._request("POST", "/api/auth/logout")
        self.token = None

    def branches(self) -> List[Dict[str, Any]]:
        p = self._request("GET", "/api/branches")
        self._need(p, "branches", where="/api/branches response")
        return p["branches"]

    def products(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        p = self._request("GET", "/api/products")
        self._need(p, "products", "categories", where="/api/products response")
        return p["products"], p["categories"]

    def dashboard(self, sku_id: str, horizon_days: int, warehouse_stock: float) -> Dict[str, Any]:
        p = self._request("GET", "/api/dashboard", params={
            "sku_id": sku_id, "horizon_days": horizon_days, "warehouse_stock": warehouse_stock,
        })
        self._need(p, "kpis", "branch_demand_chart", "demand_trend", "stockout_risk_counts",
                   "allocation_table", "warehouse_panel", "top_priority_branch",
                   where="/api/dashboard response")
        return p

    def allocation(self, sku_id: str, horizon_days: int, warehouse_stock: float) -> Dict[str, Any]:
        p = self._request("POST", "/api/allocation", json={
            "sku_id": sku_id, "horizon_days": horizon_days, "warehouse_stock": warehouse_stock,
        })
        self._need(p, "allocations", "total_required", "total_allocated", "unmet_requirement",
                   "allocation_utilization_pct", "warehouse_stock",
                   where="/api/allocation response")
        return p

    def forecast(self, branch_id: str, sku_id: str, horizon_days: int) -> Dict[str, Any]:
        p = self._request("GET", "/api/forecast", params={
            "branch_id": branch_id, "sku_id": sku_id, "horizon_days": horizon_days,
        })
        self._need(p, "daily_predictions", "total_predicted_demand",
                   where="/api/forecast response")
        return p

    def inventory(self, branch_id: Optional[str] = None,
                  sku_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {k: v for k, v in (("branch_id", branch_id), ("sku_id", sku_id)) if v}
        p = self._request("GET", "/api/inventory", params=params)
        self._need(p, "inventory", where="/api/inventory response")
        return p["inventory"]

    def metrics(self) -> Dict[str, Any]:
        p = self._request("GET", "/api/metrics")
        self._need(p, "model_metrics", where="/api/metrics response")
        return p["model_metrics"]

    def festivals(self, branch_id: Optional[str] = None,
                  sku_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Peak-demand results recalculated by the backend for the given branch / SKU
        (omit either one for "all")."""
        params = {k: v for k, v in (("branch_id", branch_id), ("sku_id", sku_id)) if v}
        p = self._request("GET", "/api/festivals", params=params)
        self._need(p, "peak_demand_monitor", where="/api/festivals response")
        return p["peak_demand_monitor"]
