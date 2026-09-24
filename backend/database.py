"""
database.py
-----------
SQLite database helpers for DMart SmartStock AI.
Creates the schema (branches, products, sales, inventory, forecasts)
and loads it from the CSV files in /data on first run.
"""

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "data", "dmart_smartstock.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    branch_name TEXT NOT NULL,
    demand_weight REAL,
    city TEXT
);

CREATE TABLE IF NOT EXISTS products (
    sku_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT,
    subcategory TEXT,
    base_price REAL,
    unit TEXT,
    base_demand REAL
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    branch_id TEXT,
    branch_name TEXT,
    sku_id TEXT,
    product_name TEXT,
    category TEXT,
    units_sold INTEGER,
    selling_price REAL,
    promotion INTEGER,
    festival TEXT,
    festival_flag INTEGER,
    weekend_flag INTEGER,
    month INTEGER,
    day_of_week INTEGER,
    opening_stock INTEGER,
    closing_stock INTEGER,
    warehouse_stock INTEGER
);

CREATE TABLE IF NOT EXISTS inventory (
    branch_id TEXT,
    branch_name TEXT,
    sku_id TEXT,
    product_name TEXT,
    category TEXT,
    current_stock INTEGER,
    safety_stock INTEGER,
    reorder_level INTEGER,
    PRIMARY KEY (branch_id, sku_id)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id TEXT,
    sku_id TEXT,
    horizon_days INTEGER,
    predicted_demand REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sales_branch_sku ON sales(branch_id, sku_id);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def database_exists():
    return os.path.exists(DB_PATH)


def init_database(force=False):
    """Creates schema and loads CSV data into SQLite. Safe to call multiple times."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    fresh = not os.path.exists(DB_PATH)

    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()

    # Only (re)load data if tables are empty (avoids duplicating rows on every app start)
    cur.execute("SELECT COUNT(*) FROM branches")
    branch_count = cur.fetchone()[0]

    if branch_count == 0:
        _load_csv_into_table(conn, "branches.csv", "branches")
        _load_csv_into_table(conn, "products.csv", "products")
        _load_csv_into_table(conn, "dmart_synthetic_sales.csv", "sales")
        _load_csv_into_table(conn, "inventory.csv", "inventory")
        print("Database initialized and populated from CSV files.")
    else:
        print("Database already populated - skipping reload.")

    conn.close()
    return fresh


def _load_csv_into_table(conn, csv_filename, table_name):
    path = os.path.join(DATA_DIR, csv_filename)
    if not os.path.exists(path):
        print(f"WARNING: {csv_filename} not found, skipping table {table_name}. "
              f"Run scripts/generate_data.py first.")
        return
    df = pd.read_csv(path)
    df.to_sql(table_name, conn, if_exists="append", index=False)


if __name__ == "__main__":
    init_database()
