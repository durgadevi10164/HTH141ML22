"""
config.py
---------
Central configuration for DMart SmartStock AI backend.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

DEFAULT_WAREHOUSE_STOCK = 5000
DEFAULT_FORECAST_HORIZON = 7
VALID_HORIZONS = [7, 14, 28]

HOST = "127.0.0.1"
PORT = 5000
DEBUG = True

# --- Authentication (demo-grade: role + employee ID, no passwords) ---
SESSION_TTL_SECONDS = int(os.environ.get("DMART_SESSION_TTL_SECONDS", 8 * 60 * 60))  # 8 hours
