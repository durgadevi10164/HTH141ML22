"""
initialize_db.py
-----------------
Standalone script to (re)create the SQLite database from the CSV files
in /data. Safe to run multiple times.

Run:
    python scripts/initialize_db.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from database import init_database  # noqa: E402

if __name__ == "__main__":
    init_database()
    print("Database ready.")
