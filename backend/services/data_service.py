"""
services/data_service.py
--------------------------
Read-only data access helpers backed by the SQLite database.
"""
import pandas as pd
from database import get_connection


def get_branches():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM branches ORDER BY branch_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY sku_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_categories():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def get_festivals():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT festival, month FROM sales WHERE festival_flag = 1 AND festival != '' "
        "ORDER BY month"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory(branch_id=None, sku_id=None):
    conn = get_connection()
    query = "SELECT * FROM inventory WHERE 1=1"
    params = []
    if branch_id:
        query += " AND branch_id = ?"
        params.append(branch_id)
    if sku_id:
        query += " AND sku_id = ?"
        params.append(sku_id)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_for(branch_id, sku_id):
    rows = get_inventory(branch_id, sku_id)
    if not rows:
        return None
    return rows[0]


def get_sales_dataframe():
    """Loads the full sales table as a DataFrame (used by the forecasting module)."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM sales", conn, parse_dates=["date"])
    conn.close()
    return df.sort_values(["branch_id", "sku_id", "date"]).reset_index(drop=True)


def get_historical_series(branch_id, sku_id, last_n_days=60):
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, units_sold FROM sales WHERE branch_id = ? AND sku_id = ? "
        "ORDER BY date DESC LIMIT ?",
        (branch_id, sku_id, last_n_days),
    ).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return list(reversed(data))


def branch_exists(branch_id):
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
    conn.close()
    return row is not None


def sku_exists(sku_id):
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM products WHERE sku_id = ?", (sku_id,)).fetchone()
    conn.close()
    return row is not None
