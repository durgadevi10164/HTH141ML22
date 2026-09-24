"""
generate_data.py
-----------------
Generates a realistic SYNTHETIC dataset simulating 5 DMart-inspired branches
around Coimbatore, 20 supermarket SKUs, and 365 days of daily sales +
inventory history.

IMPORTANT: This data is 100% synthetic/simulated. It does NOT represent
real DMart sales, inventory, or business figures. It was built for a
hackathon demo of an inventory-constrained demand forecasting system.

Run:
    python scripts/generate_data.py
"""

import os
import random
import numpy as np
import pandas as pd
from datetime import date, timedelta

# ------------------------------------------------------------------
# Reproducibility
# ------------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ------------------------------------------------------------------
# Branches (simulated, around Coimbatore) with a relative demand weight
# ------------------------------------------------------------------
BRANCHES = [
    {"branch_id": "B01", "branch_name": "Singanallur", "demand_weight": 1.25, "city": "Coimbatore"},
    {"branch_id": "B02", "branch_name": "Podanur", "demand_weight": 1.15, "city": "Coimbatore"},
    {"branch_id": "B03", "branch_name": "Mettupalayam Road", "demand_weight": 1.00, "city": "Coimbatore"},
    {"branch_id": "B04", "branch_name": "Chinniyampalayam", "demand_weight": 0.80, "city": "Coimbatore"},
    {"branch_id": "B05", "branch_name": "Sulur", "demand_weight": 0.65, "city": "Coimbatore"},
]

# ------------------------------------------------------------------
# 20 SKUs across 5 categories with a base daily demand (per branch,
# before branch weighting) and price
# ------------------------------------------------------------------
PRODUCTS = [
    # GROCERY / STAPLES
    {"sku_id": "SKU001", "product_name": "Rice 5kg", "category": "Grocery", "subcategory": "Staples", "base_price": 340.0, "unit": "bag", "base_demand": 28},
    {"sku_id": "SKU002", "product_name": "Wheat Flour 5kg", "category": "Grocery", "subcategory": "Staples", "base_price": 220.0, "unit": "bag", "base_demand": 22},
    {"sku_id": "SKU003", "product_name": "Sugar 1kg", "category": "Grocery", "subcategory": "Staples", "base_price": 45.0, "unit": "pack", "base_demand": 26},
    {"sku_id": "SKU004", "product_name": "Cooking Oil 1L", "category": "Grocery", "subcategory": "Staples", "base_price": 150.0, "unit": "bottle", "base_demand": 24},
    # DAIRY & BEVERAGES
    {"sku_id": "SKU005", "product_name": "Milk 1L", "category": "Dairy & Beverages", "subcategory": "Dairy", "base_price": 60.0, "unit": "packet", "base_demand": 45},
    {"sku_id": "SKU006", "product_name": "Curd 500g", "category": "Dairy & Beverages", "subcategory": "Dairy", "base_price": 35.0, "unit": "cup", "base_demand": 30},
    {"sku_id": "SKU007", "product_name": "Tea 500g", "category": "Dairy & Beverages", "subcategory": "Beverages", "base_price": 210.0, "unit": "pack", "base_demand": 14},
    {"sku_id": "SKU008", "product_name": "Coffee 200g", "category": "Dairy & Beverages", "subcategory": "Beverages", "base_price": 180.0, "unit": "pack", "base_demand": 10},
    # SNACKS & PACKAGED FOOD
    {"sku_id": "SKU009", "product_name": "Biscuits", "category": "Snacks & Packaged Food", "subcategory": "Snacks", "base_price": 30.0, "unit": "pack", "base_demand": 40},
    {"sku_id": "SKU010", "product_name": "Potato Chips", "category": "Snacks & Packaged Food", "subcategory": "Snacks", "base_price": 20.0, "unit": "pack", "base_demand": 38},
    {"sku_id": "SKU011", "product_name": "Noodles", "category": "Snacks & Packaged Food", "subcategory": "Packaged Food", "base_price": 14.0, "unit": "pack", "base_demand": 42},
    {"sku_id": "SKU012", "product_name": "Breakfast Cereal", "category": "Snacks & Packaged Food", "subcategory": "Packaged Food", "base_price": 210.0, "unit": "box", "base_demand": 12},
    # PERSONAL CARE
    {"sku_id": "SKU013", "product_name": "Bath Soap", "category": "Personal Care", "subcategory": "Bath & Body", "base_price": 40.0, "unit": "piece", "base_demand": 20},
    {"sku_id": "SKU014", "product_name": "Shampoo", "category": "Personal Care", "subcategory": "Hair Care", "base_price": 150.0, "unit": "bottle", "base_demand": 15},
    {"sku_id": "SKU015", "product_name": "Toothpaste", "category": "Personal Care", "subcategory": "Oral Care", "base_price": 95.0, "unit": "tube", "base_demand": 18},
    {"sku_id": "SKU016", "product_name": "Hand Wash", "category": "Personal Care", "subcategory": "Bath & Body", "base_price": 85.0, "unit": "bottle", "base_demand": 13},
    # HOUSEHOLD
    {"sku_id": "SKU017", "product_name": "Detergent Powder", "category": "Household", "subcategory": "Laundry", "base_price": 180.0, "unit": "pack", "base_demand": 16},
    {"sku_id": "SKU018", "product_name": "Dishwash Liquid", "category": "Household", "subcategory": "Kitchen Care", "base_price": 99.0, "unit": "bottle", "base_demand": 17},
    {"sku_id": "SKU019", "product_name": "Floor Cleaner", "category": "Household", "subcategory": "Home Care", "base_price": 120.0, "unit": "bottle", "base_demand": 11},
    {"sku_id": "SKU020", "product_name": "Toilet Cleaner", "category": "Household", "subcategory": "Home Care", "base_price": 95.0, "unit": "bottle", "base_demand": 10},
]

# ------------------------------------------------------------------
# SKU-specific festival demand boosts.
#
# Each festival maps to a dict of {sku_id: multiplier} for ONLY the
# SKUs that are realistically linked to that festival. Any SKU not
# listed for a given festival is left at its normal demand (implicit
# multiplier of 1.0) and only moves with the existing weekly/monthly
# seasonality + random noise already in the model - it does NOT get
# an artificial festival spike.
#
# SKU reference:
#   SKU001 Rice 5kg          SKU008 Coffee 200g        SKU015 Toothpaste
#   SKU002 Wheat Flour 5kg   SKU009 Biscuits           SKU016 Hand Wash
#   SKU003 Sugar 1kg         SKU010 Potato Chips       SKU017 Detergent Powder
#   SKU004 Cooking Oil 1L    SKU011 Noodles            SKU018 Dishwash Liquid
#   SKU005 Milk 1L           SKU012 Breakfast Cereal   SKU019 Floor Cleaner
#   SKU006 Curd 500g         SKU013 Bath Soap          SKU020 Toilet Cleaner
#   SKU007 Tea 500g          SKU014 Shampoo
# ------------------------------------------------------------------
FESTIVAL_SKU_BOOST = {
    # PONGAL: cooking/grocery essentials spike hard; personal care stays flat
    "Pongal": {
        "SKU001": 2.00,  # Rice
        "SKU004": 1.90,  # Cooking Oil
        "SKU003": 1.70,  # Sugar (also stands in for jaggery)
        "SKU002": 1.60,  # Wheat Flour / Atta
        "SKU009": 1.30,  # Biscuits (snacks)
        "SKU010": 1.30,  # Potato Chips (snacks)
        "SKU005": 1.25,  # Milk (Pongal cooking)
        "SKU007": 1.20,  # Tea (beverages)
        "SKU008": 1.15,  # Coffee (beverages)
        "SKU006": 1.15,  # Curd
        "SKU017": 1.15,  # Detergent - moderate household
        "SKU018": 1.15,  # Dishwash Liquid - moderate household
        "SKU019": 1.10,  # Floor Cleaner - moderate household
        "SKU020": 1.10,  # Toilet Cleaner - moderate household
    },
    # REPUBLIC DAY: mostly a normal day; only a mild snack/beverage bump
    "Republic Day": {
        "SKU010": 1.25,  # Potato Chips
        "SKU009": 1.25,  # Biscuits
        "SKU007": 1.20,  # Tea
        "SKU008": 1.20,  # Coffee
        "SKU011": 1.20,  # Noodles (packaged food)
        "SKU012": 1.15,  # Breakfast Cereal (packaged food)
    },
    # TAMIL NEW YEAR: similar cooking/grocery profile to Pongal
    "Tamil New Year": {
        "SKU001": 1.90,  # Rice
        "SKU004": 1.80,  # Cooking Oil
        "SKU003": 1.60,  # Sugar / jaggery
        "SKU002": 1.50,  # Wheat Flour / Atta
        "SKU009": 1.30,  # Biscuits
        "SKU010": 1.30,  # Potato Chips
        "SKU005": 1.25,  # Milk
        "SKU006": 1.20,  # Curd
        "SKU007": 1.15,  # Tea
        "SKU008": 1.15,  # Coffee
        "SKU017": 1.10,  # Detergent - moderate household
        "SKU018": 1.10,  # Dishwash Liquid - moderate household
        "SKU019": 1.05,  # Floor Cleaner - light household
        "SKU020": 1.05,  # Toilet Cleaner - light household
    },
    # INDEPENDENCE DAY: snacks/biscuits/beverages/packaged foods only
    "Independence Day": {
        "SKU009": 1.30,  # Biscuits
        "SKU010": 1.30,  # Potato Chips
        "SKU007": 1.20,  # Tea
        "SKU008": 1.20,  # Coffee
        "SKU011": 1.15,  # Noodles
        "SKU012": 1.15,  # Breakfast Cereal
    },
    # NAVRATRI: oil/rice/flour/sugar/dry-grocery + fasting dairy; Bath Soap
    # and other personal-care items are deliberately left OUT so they do
    # not get an artificial spike.
    "Navratri": {
        "SKU004": 1.70,  # Cooking Oil
        "SKU001": 1.50,  # Rice
        "SKU002": 1.40,  # Wheat Flour / Atta
        "SKU003": 1.40,  # Sugar
        "SKU006": 1.30,  # Curd (fasting-friendly)
        "SKU005": 1.25,  # Milk (fasting-friendly)
        "SKU009": 1.20,  # Biscuits
        "SKU010": 1.20,  # Potato Chips
        "SKU007": 1.15,  # Tea
        "SKU008": 1.15,  # Coffee
        # SKU013 Bath Soap intentionally NOT boosted for Navratri
    },
    # DIWALI: the strongest festival - broad but still SKU-specific
    "Diwali": {
        "SKU003": 2.00,  # Sugar (sweets)
        "SKU004": 1.90,  # Cooking Oil
        "SKU009": 1.90,  # Biscuits (sweets/snacks)
        "SKU010": 1.90,  # Potato Chips (snacks)
        "SKU002": 1.70,  # Wheat Flour / Atta
        "SKU007": 1.60,  # Tea
        "SKU008": 1.60,  # Coffee
        "SKU011": 1.50,  # Noodles (packaged food)
        "SKU012": 1.50,  # Breakfast Cereal (packaged food)
        "SKU017": 1.50,  # Detergent Powder (cleaning for Diwali)
        "SKU018": 1.50,  # Dishwash Liquid (cleaning)
        "SKU001": 1.50,  # Rice
        "SKU019": 1.45,  # Floor Cleaner
        "SKU020": 1.45,  # Toilet Cleaner
        "SKU005": 1.40,  # Milk (sweets making)
        "SKU006": 1.40,  # Curd
        "SKU013": 1.35,  # Bath Soap (gifting)
        "SKU014": 1.35,  # Shampoo (gifting)
        "SKU016": 1.30,  # Hand Wash (gifting)
        "SKU015": 1.15,  # Toothpaste - only mildly gifting-related
    },
    # CHRISTMAS: baking + chocolates/sweets + beverages, moderate household
    "Christmas": {
        "SKU003": 1.70,  # Sugar (baking/sweets)
        "SKU002": 1.60,  # Wheat Flour / Atta (baking)
        "SKU009": 1.60,  # Biscuits (chocolates/sweets stand-in)
        "SKU010": 1.60,  # Potato Chips (snacks)
        "SKU007": 1.50,  # Tea
        "SKU008": 1.50,  # Coffee
        "SKU011": 1.30,  # Noodles (packaged food)
        "SKU012": 1.30,  # Breakfast Cereal (packaged food)
        "SKU005": 1.30,  # Milk (baking)
        "SKU006": 1.20,  # Curd
        "SKU017": 1.20,  # Detergent - moderate household
        "SKU018": 1.15,  # Dishwash Liquid - moderate household
        "SKU019": 1.15,  # Floor Cleaner - moderate household
        "SKU013": 1.15,  # Bath Soap - moderate, gifting-adjacent
        "SKU020": 1.10,  # Toilet Cleaner - moderate household
        "SKU014": 1.10,  # Shampoo - moderate, gifting-adjacent
        "SKU001": 1.10,  # Rice - mild
        "SKU004": 1.10,  # Cooking Oil - mild
    },
    # NEW YEAR: party/consumption grocery items only
    "New Year": {
        "SKU010": 1.60,  # Potato Chips
        "SKU007": 1.60,  # Tea
        "SKU008": 1.60,  # Coffee
        "SKU009": 1.50,  # Biscuits
        "SKU011": 1.40,  # Noodles
        "SKU012": 1.35,  # Breakfast Cereal
        "SKU003": 1.30,  # Sugar (sweets/chocolates stand-in)
        "SKU005": 1.15,  # Milk
        "SKU006": 1.10,  # Curd
    },
}

# Simulated (fixed, reproducible) festival dates for the data-generation year
FESTIVAL_DATES_2025 = {
    "Pongal": "2025-01-14",
    "Republic Day": "2025-01-26",
    "Tamil New Year": "2025-04-14",
    "Independence Day": "2025-08-15",
    "Navratri": "2025-09-29",
    "Diwali": "2025-10-20",
    "Christmas": "2025-12-25",
    "New Year": "2025-01-01",
}

START_DATE = date(2025, 1, 1)
NUM_DAYS = 365


def build_calendar():
    rows = []
    festival_by_date = {pd.to_datetime(v).date(): k for k, v in FESTIVAL_DATES_2025.items()}
    for i in range(NUM_DAYS):
        d = START_DATE + timedelta(days=i)
        dow = d.weekday()  # 0=Mon ... 6=Sun
        is_weekend = 1 if dow >= 5 else 0
        festival = festival_by_date.get(d, "")
        # +/- 1 day "festival window" gets a smaller boost too
        festival_flag = 1 if festival else 0
        rows.append({
            "date": d.isoformat(),
            "day_of_week": dow,
            "weekend_flag": is_weekend,
            "month": d.month,
            "festival": festival,
            "festival_flag": festival_flag,
        })
    cal = pd.DataFrame(rows)
    return cal


def simulate_sales(calendar_df):
    """Builds the ~36,500-row sales dataset with realistic patterns."""
    records = []

    # Promotion calendar: each branch/SKU combo gets random promo days (~6% of days)
    for branch in BRANCHES:
        for product in PRODUCTS:
            # per-branch-per-sku slight random variation so no two series are identical
            sku_branch_noise_scale = np.random.uniform(0.85, 1.15)
            trend_slope = np.random.uniform(-0.02, 0.05)  # mild growth/decline over the year

            # pre-generate which days are on promotion for this branch/sku (~6% of days, in short bursts)
            promo_days = set()
            n_promo_bursts = np.random.randint(4, 9)
            for _ in range(n_promo_bursts):
                start_idx = np.random.randint(0, NUM_DAYS - 5)
                length = np.random.randint(2, 5)
                for j in range(length):
                    promo_days.add(start_idx + j)

            opening_stock = np.random.randint(60, 150)

            for idx, cal_row in calendar_df.iterrows():
                day_of_week = cal_row["day_of_week"]
                weekend_flag = cal_row["weekend_flag"]
                month = cal_row["month"]
                festival = cal_row["festival"]
                festival_flag = cal_row["festival_flag"]

                base = product["base_demand"] * branch["demand_weight"] * sku_branch_noise_scale

                # weekly seasonality: weekends generally higher for most categories,
                # dairy/beverages/snacks especially so
                if weekend_flag:
                    if product["category"] in ("Dairy & Beverages", "Snacks & Packaged Food"):
                        base *= 1.35
                    else:
                        base *= 1.15

                # mild day-of-week wave (e.g. dip mid-week) on top of weekend effect
                base *= (1 + 0.05 * np.sin((day_of_week / 7.0) * 2 * np.pi))

                # slow trend across the year
                base *= (1 + trend_slope * (idx / NUM_DAYS))

                # monthly pattern (e.g. slightly higher in Oct-Dec festive season, lower in June)
                month_factor = 1.0 + 0.08 * np.sin((month / 12.0) * 2 * np.pi)
                base *= month_factor

                # festival boost - SKU-specific, not the same for every product.
                # SKUs not listed for this festival simply keep their normal
                # demand (multiplier 1.0) plus the usual random noise below.
                if festival_flag and festival in FESTIVAL_SKU_BOOST:
                    boost = FESTIVAL_SKU_BOOST[festival].get(product["sku_id"], 1.0)
                    base *= boost

                # promotion boost
                promotion = 1 if idx in promo_days else 0
                if promotion:
                    base *= np.random.uniform(1.25, 1.6)

                # random noise (Poisson-like, keeps integers realistic & non-negative)
                noisy_demand = np.random.normal(loc=base, scale=max(1.0, base * 0.15))
                units_sold = int(max(0, round(noisy_demand)))

                # price: base price with small promo discount
                selling_price = product["base_price"]
                if promotion:
                    selling_price = round(product["base_price"] * np.random.uniform(0.85, 0.95), 2)

                # inventory logic tied to sales
                closing_stock = opening_stock - units_sold
                if closing_stock < 20:
                    # simulate a restock from warehouse when running low
                    restock = np.random.randint(80, 180)
                    closing_stock += restock
                closing_stock = max(closing_stock, 0)

                warehouse_stock = np.random.randint(2500, 5000)  # snapshot, informational per row

                records.append({
                    "date": cal_row["date"],
                    "branch_id": branch["branch_id"],
                    "branch_name": branch["branch_name"],
                    "sku_id": product["sku_id"],
                    "product_name": product["product_name"],
                    "category": product["category"],
                    "units_sold": units_sold,
                    "selling_price": selling_price,
                    "promotion": promotion,
                    "festival": festival,
                    "festival_flag": festival_flag,
                    "weekend_flag": weekend_flag,
                    "month": month,
                    "day_of_week": day_of_week,
                    "opening_stock": opening_stock,
                    "closing_stock": closing_stock,
                    "warehouse_stock": warehouse_stock,
                })

                opening_stock = closing_stock  # tomorrow starts where today ended

    df = pd.DataFrame.from_records(records)
    return df


def build_inventory_snapshot(sales_df):
    """Current (latest date) inventory snapshot per branch/SKU with reorder & safety stock levels."""
    latest_date = sales_df["date"].max()
    snap = sales_df[sales_df["date"] == latest_date].copy()

    rows = []
    for _, r in snap.iterrows():
        product = next(p for p in PRODUCTS if p["sku_id"] == r["sku_id"])
        avg_daily_demand = product["base_demand"]
        safety_stock = int(round(avg_daily_demand * 3))     # ~3 days of average demand
        reorder_level = int(round(avg_daily_demand * 5))    # ~5 days of average demand
        rows.append({
            "branch_id": r["branch_id"],
            "branch_name": r["branch_name"],
            "sku_id": r["sku_id"],
            "product_name": r["product_name"],
            "category": r["category"],
            "current_stock": int(r["closing_stock"]),
            "safety_stock": safety_stock,
            "reorder_level": reorder_level,
        })
    return pd.DataFrame(rows)


def main():
    print("Generating calendar...")
    calendar_df = build_calendar()
    calendar_df.to_csv(os.path.join(DATA_DIR, "calendar.csv"), index=False)

    print("Generating branches.csv / products.csv...")
    pd.DataFrame(BRANCHES).to_csv(os.path.join(DATA_DIR, "branches.csv"), index=False)
    pd.DataFrame(PRODUCTS).to_csv(os.path.join(DATA_DIR, "products.csv"), index=False)

    print("Simulating ~365 days x 5 branches x 20 SKUs of sales... (this can take a few seconds)")
    sales_df = simulate_sales(calendar_df)
    sales_path = os.path.join(DATA_DIR, "dmart_synthetic_sales.csv")
    sales_df.to_csv(sales_path, index=False)
    print(f"Saved {len(sales_df):,} rows -> {sales_path}")

    print("Building current inventory snapshot...")
    inv_df = build_inventory_snapshot(sales_df)
    inv_df.to_csv(os.path.join(DATA_DIR, "inventory.csv"), index=False)

    print("\nDone. All files written to:", DATA_DIR)
    print("NOTE: This dataset is 100% SYNTHETIC/SIMULATED for demo purposes only.")


if __name__ == "__main__":
    main()
