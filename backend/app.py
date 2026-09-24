"""
app.py
------
DMart SmartStock AI - Flask backend entrypoint.

Serves the JSON API under /api/* and the static frontend (single-page
HTML/CSS/JS dashboard) from /frontend.

Run directly:
    python backend/app.py

Or via the provided run.bat on Windows, which also generates data,
trains the model and initializes the database on first run.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # make backend/ importable

from flask import Flask, send_from_directory, jsonify, request

from config import FRONTEND_DIR, HOST, PORT, DEBUG
from database import init_database, database_exists

from routes.auth_routes import auth_bp
from routes.catalog_routes import catalog_bp
from routes.inventory_routes import inventory_bp
from routes.forecast_routes import forecast_bp
from routes.allocation_routes import allocation_bp
from routes.dashboard_routes import dashboard_bp


def create_app():
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

    # --- Manual CORS (avoids needing the flask-cors package) ---
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.route("/api/<path:_any>", methods=["OPTIONS"])
    def cors_preflight(_any):
        return "", 204

    # --- Register API blueprints ---
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(allocation_bp)
    app.register_blueprint(dashboard_bp)

    # --- Health check ---
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "DMart SmartStock AI backend"})

    # --- Friendly error handlers so the app never hard-crashes on bad input ---
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

    # --- Serve the static frontend ---
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        if filename.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        full_path = os.path.join(FRONTEND_DIR, filename)
        if os.path.exists(full_path):
            return send_from_directory(FRONTEND_DIR, filename)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    if not database_exists():
        print("No database found - initializing from CSV files...")
        init_database()
    print(f"Starting DMart SmartStock AI backend on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
