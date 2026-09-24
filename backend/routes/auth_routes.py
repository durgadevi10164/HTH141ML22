"""routes/auth_routes.py - /api/auth/roles, /api/auth/login, /api/auth/me, /api/auth/logout"""
from flask import Blueprint, jsonify, request

from services import auth_service as auth

auth_bp = Blueprint("auth", __name__)


def _session_payload(user, token=None):
    body = {"user": user, "permissions": auth.permissions_for(user)}
    if token is not None:
        body["token"] = token
    return body


@auth_bp.route("/api/auth/roles", methods=["GET"])
def roles():
    """Public: the role list for the login form (labels only - no employee IDs)."""
    return jsonify({"roles": auth.list_roles()})


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    role = payload.get("role")
    employee_id = payload.get("employee_id")

    if not role or not str(employee_id or "").strip():
        return jsonify({"error": "Please select a role and enter your Employee ID."}), 400

    user = auth.authenticate(role, employee_id)
    if user is None:
        # Same message for "unknown ID" and "ID belongs to another role": no ID enumeration.
        return jsonify({"error": auth.INVALID_LOGIN_MESSAGE}), 401

    token = auth.create_session(user)
    return jsonify(_session_payload(user, token)), 200


@auth_bp.route("/api/auth/me", methods=["GET"])
@auth.login_required()
def me():
    return jsonify(_session_payload(auth.current_user()))


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    token = auth.bearer_token()
    if token:
        auth.destroy_session(token)
    return jsonify({"message": "Logged out."})
