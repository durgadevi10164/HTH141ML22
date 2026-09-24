"""
services/auth_service.py
--------------------------
Demo-grade, role-based authentication for DMart SmartStock AI.

* A user logs in with a ROLE and a unique EMPLOYEE ID. The ID must belong to
  the selected role, otherwise the login is rejected.
* A successful login creates a server-side session and returns an opaque bearer
  token. The client sends it as ``Authorization: Bearer <token>`` on every call.
* The role (and, for Branch Managers, the branch) is ALWAYS taken from the
  server-side session - never from anything the client sends - so a Branch
  Manager cannot switch branch by editing a request.
* ``login_required(permission)`` protects an endpoint and makes the signed-in
  user available as ``flask.g.user``.

There are intentionally no passwords: this is a hackathon demo with fixed demo
IDs (see DEMO_USERS). Swap ``authenticate`` for a real identity provider before
using anything like this for real.
"""
import secrets
import threading
import time
from functools import wraps

from flask import g, jsonify, request

import config
from services import data_service

# --------------------------------------------------------------------- roles
ROLE_BRANCH_MANAGER = "branch_manager"
ROLE_INVENTORY_MANAGER = "inventory_manager"
ROLE_WAREHOUSE_MANAGER = "warehouse_manager"
ROLE_REGIONAL_MANAGER = "regional_manager"

# Dashboard tab keys (the Streamlit app maps them to labels / renderers)
TAB_OVERVIEW = "overview"
TAB_INVENTORY = "inventory"
TAB_ALLOCATION = "allocation"
TAB_WHATIF = "whatif"
TAB_PEAK = "peak"
TAB_MODEL = "model"

# Endpoint permissions. Every protected API endpoint names exactly one of these.
ALL_ACCESS = {"dashboard", "forecast", "allocation", "inventory", "metrics",
              "festivals", "branches", "products"}

ROLES = {
    ROLE_BRANCH_MANAGER: {
        "label": "Branch Manager",
        # own branch only: inventory, demand, shortage, risk, recommendation, peak demand
        "tabs": [TAB_OVERVIEW, TAB_ALLOCATION, TAB_PEAK],
        "access": {"dashboard", "forecast", "inventory", "festivals", "branches", "products"},
        "branch_locked": True,
        "can_set_warehouse_stock": False,
    },
    ROLE_INVENTORY_MANAGER: {
        "label": "Inventory Manager",
        # inventory across all branches / SKUs (no warehouse allocation)
        "tabs": [TAB_OVERVIEW, TAB_INVENTORY, TAB_PEAK, TAB_MODEL],
        "access": {"dashboard", "forecast", "inventory", "metrics", "festivals", "branches", "products"},
        "branch_locked": False,
        "can_set_warehouse_stock": False,
    },
    ROLE_WAREHOUSE_MANAGER: {
        "label": "Warehouse / Distribution Manager",
        # warehouse stock, shortages and allocation
        "tabs": [TAB_ALLOCATION, TAB_WHATIF, TAB_PEAK],
        "access": {"dashboard", "allocation", "inventory", "festivals", "branches", "products"},
        "branch_locked": False,
        "can_set_warehouse_stock": True,
    },
    ROLE_REGIONAL_MANAGER: {
        "label": "Regional Supply Chain Manager",
        # the full, chain-wide overview (the original dashboard)
        "tabs": [TAB_OVERVIEW, TAB_ALLOCATION, TAB_WHATIF, TAB_PEAK, TAB_MODEL],
        "access": set(ALL_ACCESS),
        "branch_locked": False,
        "can_set_warehouse_stock": True,
    },
}

# ------------------------------------------------------------- demo employees
# Branch Managers are tied to a branch NAME; the branch_id is looked up in the
# database at login time so this stays correct if the dataset is regenerated.
DEMO_USERS = {
    "BM001": {"role": ROLE_BRANCH_MANAGER, "name": "Branch Manager - Singanallur", "branch_name": "Singanallur"},
    "BM002": {"role": ROLE_BRANCH_MANAGER, "name": "Branch Manager - Podanur", "branch_name": "Podanur"},
    "BM003": {"role": ROLE_BRANCH_MANAGER, "name": "Branch Manager - Mettupalayam Road", "branch_name": "Mettupalayam Road"},
    "BM004": {"role": ROLE_BRANCH_MANAGER, "name": "Branch Manager - Chinniyampalayam", "branch_name": "Chinniyampalayam"},
    "BM005": {"role": ROLE_BRANCH_MANAGER, "name": "Branch Manager - Sulur", "branch_name": "Sulur"},
    "IM001": {"role": ROLE_INVENTORY_MANAGER, "name": "Inventory Manager"},
    "WM001": {"role": ROLE_WAREHOUSE_MANAGER, "name": "Warehouse / Distribution Manager"},
    "RSM001": {"role": ROLE_REGIONAL_MANAGER, "name": "Regional Supply Chain Manager"},
}

INVALID_LOGIN_MESSAGE = "Invalid Employee ID for the selected role."

# ------------------------------------------------------------------ sessions
_SESSIONS = {}          # token -> {"user": {...}, "expires_at": float}
_LOCK = threading.Lock()


def list_roles():
    return [{"key": key, "label": cfg["label"]} for key, cfg in ROLES.items()]


def normalize_role(value):
    """Accepts a role key ('branch_manager') or its label ('Branch Manager')."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in ROLES:
        return v
    for key, cfg in ROLES.items():
        if cfg["label"].lower() == v:
            return key
    return None


def authenticate(role, employee_id):
    """Returns the user dict if `employee_id` exists AND belongs to `role`, else None."""
    role_key = normalize_role(role)
    if role_key is None or not isinstance(employee_id, str):
        return None
    emp = employee_id.strip().upper()
    record = DEMO_USERS.get(emp)
    if record is None or record["role"] != role_key:
        return None

    user = {
        "employee_id": emp,
        "name": record["name"],
        "role": role_key,
        "role_label": ROLES[role_key]["label"],
        "branch_id": None,
        "branch_name": None,
    }
    if ROLES[role_key]["branch_locked"]:
        branch = next((b for b in data_service.get_branches()
                       if b["branch_name"] == record["branch_name"]), None)
        if branch is None:  # dataset does not contain this branch -> refuse rather than widen access
            return None
        user["branch_id"] = branch["branch_id"]
        user["branch_name"] = branch["branch_name"]
    return user


def permissions_for(user):
    cfg = ROLES[user["role"]]
    return {
        "tabs": list(cfg["tabs"]),
        "branch_locked": cfg["branch_locked"],
        "can_set_warehouse_stock": cfg["can_set_warehouse_stock"],
        "access": sorted(cfg["access"]),
    }


def create_session(user):
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _purge_expired()
        _SESSIONS[token] = {"user": user, "expires_at": time.time() + config.SESSION_TTL_SECONDS}
    return token


def destroy_session(token):
    with _LOCK:
        return _SESSIONS.pop(token, None) is not None


def _purge_expired():
    now = time.time()
    for t in [t for t, s in _SESSIONS.items() if s["expires_at"] <= now]:
        del _SESSIONS[t]


def bearer_token():
    header = request.headers.get("Authorization", "")
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def user_for_token(token):
    if not token:
        return None
    with _LOCK:
        session = _SESSIONS.get(token)
        if session is None:
            return None
        if session["expires_at"] <= time.time():
            del _SESSIONS[token]
            return None
        return dict(session["user"])


def current_user():
    """The signed-in user for this request (set by @login_required)."""
    return g.user


def login_required(permission=None):
    """Decorator: 401 without a valid session, 403 if the role lacks `permission`."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = user_for_token(bearer_token())
            if user is None:
                return jsonify({"error": "Authentication required. Please log in."}), 401
            if permission is not None and permission not in ROLES[user["role"]]["access"]:
                return jsonify({"error": f"Your role ({user['role_label']}) does not have access to this resource."}), 403
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator
