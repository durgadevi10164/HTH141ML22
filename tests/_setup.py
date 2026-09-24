"""
tests/_setup.py
-----------------
Shared setup for the test suite. Uses only Python's built-in `unittest`
module (no pytest / third-party test framework required), so the tests
run out of the box on a fresh Windows install with just requirements.txt.
"""
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def ensure_project_ready():
    """Generates data / trains model / initializes DB if they don't exist yet."""
    data_csv = os.path.join(BASE_DIR, "data", "dmart_synthetic_sales.csv")
    model_pkl = os.path.join(BASE_DIR, "models", "demand_model.pkl")
    db_path = os.path.join(BASE_DIR, "data", "dmart_smartstock.db")

    if not os.path.exists(data_csv):
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "scripts", "generate_data.py")], check=True)
    if not os.path.exists(model_pkl):
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "scripts", "train_model.py")], check=True)
    if not os.path.exists(db_path):
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "scripts", "initialize_db.py")], check=True)


def get_test_client(role=None, employee_id=None):
    """Flask test client. By default it is logged in as the Regional Supply Chain Manager (RSM001),
    who has the full chain-wide access the original dashboard had, so the existing tests keep
    exercising the unchanged forecasting / allocation behaviour. Pass role=None-like values
    explicitly via `anonymous_client()` for unauthenticated requests."""
    client = anonymous_client()
    login(client, role or "regional_manager", employee_id or "RSM001")
    return client


def anonymous_client():
    ensure_project_ready()
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def login(client, role, employee_id):
    """Logs `client` in (all its later requests carry the bearer token). Returns the login response."""
    resp = client.post("/api/auth/login", json={"role": role, "employee_id": employee_id})
    if resp.status_code == 200:
        client.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + resp.get_json()["token"]
    return resp
