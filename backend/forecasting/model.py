"""
forecasting/model.py
---------------------
Feature engineering, training, evaluation, and prediction for the
demand-forecasting model used by DMart SmartStock AI.

Model: RandomForestRegressor (scikit-learn) trained on engineered
lag / rolling-mean / calendar features from the synthetic sales history.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(BASE_DIR, "data", "dmart_synthetic_sales.csv")
MODEL_PATH = os.path.join(BASE_DIR, "models", "demand_model.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "models", "metrics.json")

FEATURE_COLUMNS = [
    "lag_1", "lag_7", "lag_14", "lag_28",
    "rolling_mean_7", "rolling_mean_14", "rolling_mean_28",
    "day_of_week", "month", "weekend_flag", "festival_flag", "promotion",
    "selling_price", "branch_code", "sku_code", "category_code",
]
TARGET_COLUMN = "units_sold"


def load_sales_data():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"Sales dataset not found at {DATA_PATH}. Run scripts/generate_data.py first."
        )
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    return df.sort_values(["branch_id", "sku_id", "date"]).reset_index(drop=True)


def engineer_features(df):
    """Adds lag / rolling-mean / encoded categorical features per branch+SKU series."""
    df = df.copy()

    df["branch_code"] = df["branch_id"].astype("category").cat.codes
    df["sku_code"] = df["sku_id"].astype("category").cat.codes
    df["category_code"] = df["category"].astype("category").cat.codes

    grouped = df.groupby(["branch_id", "sku_id"])["units_sold"]

    df["lag_1"] = grouped.shift(1)
    df["lag_7"] = grouped.shift(7)
    df["lag_14"] = grouped.shift(14)
    df["lag_28"] = grouped.shift(28)

    df["rolling_mean_7"] = grouped.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    df["rolling_mean_14"] = grouped.transform(lambda s: s.shift(1).rolling(14, min_periods=1).mean())
    df["rolling_mean_28"] = grouped.transform(lambda s: s.shift(1).rolling(28, min_periods=1).mean())

    # fill early-series NaNs with the (already-shifted) rolling mean or 0
    for col in ["lag_1", "lag_7", "lag_14", "lag_28"]:
        df[col] = df[col].fillna(df["rolling_mean_7"]).fillna(0)
    df[["rolling_mean_7", "rolling_mean_14", "rolling_mean_28"]] = df[
        ["rolling_mean_7", "rolling_mean_14", "rolling_mean_28"]
    ].fillna(0)

    return df


def train_and_save_model():
    """Trains the RandomForest demand model and saves it + evaluation metrics to disk."""
    raw = load_sales_data()
    featured = engineer_features(raw)

    X = featured[FEATURE_COLUMNS]
    y = featured[TARGET_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(
        n_estimators=150,
        max_depth=14,
        min_samples_leaf=3,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    # MAPE, guarding against zero actuals
    nonzero_mask = y_test != 0
    mape = float(
        np.mean(np.abs((y_test[nonzero_mask] - preds[nonzero_mask]) / y_test[nonzero_mask])) * 100
    ) if nonzero_mask.sum() > 0 else None

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

    # Save mapping tables needed at inference time (category codes must match training)
    branch_map = dict(enumerate(raw["branch_id"].astype("category").cat.categories))
    sku_map = dict(enumerate(raw["sku_id"].astype("category").cat.categories))
    category_map = dict(enumerate(raw["category"].astype("category").cat.categories))

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "branch_categories": list(raw["branch_id"].astype("category").cat.categories),
        "sku_categories": list(raw["sku_id"].astype("category").cat.categories),
        "category_categories": list(raw["category"].astype("category").cat.categories),
        "metrics": {"mae": mae, "rmse": rmse, "mape": mape, "n_test_rows": int(len(y_test))},
    }
    joblib.dump(bundle, MODEL_PATH)

    import json
    with open(METRICS_PATH, "w") as f:
        json.dump(bundle["metrics"], f, indent=2)

    print(f"Model trained. MAE={mae:.2f}  RMSE={rmse:.2f}  MAPE={mape}")
    print(f"Saved model -> {MODEL_PATH}")
    return bundle["metrics"]


_bundle_cache = None


def load_model_bundle():
    global _bundle_cache
    if _bundle_cache is not None:
        return _bundle_cache
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. Run scripts/train_model.py first."
        )
    _bundle_cache = joblib.load(MODEL_PATH)
    return _bundle_cache


def _encode(value, categories):
    try:
        return categories.index(value)
    except ValueError:
        return -1


def predict_demand(branch_id, sku_id, horizon_days, sales_df=None):
    """
    Predicts total demand for (branch_id, sku_id) over the next `horizon_days`
    using a recursive one-step-ahead forecast with the trained RandomForest model.

    Returns dict with daily predictions and total.
    """
    bundle = load_model_bundle()
    model = bundle["model"]

    if sales_df is None:
        sales_df = load_sales_data()

    history = sales_df[
        (sales_df["branch_id"] == branch_id) & (sales_df["sku_id"] == sku_id)
    ].sort_values("date")

    if history.empty:
        raise ValueError(f"No history found for branch={branch_id}, sku={sku_id}")

    history = engineer_features(history)  # recompute so lags are consistent
    last_row = history.iloc[-1]
    recent_units = list(history["units_sold"].tail(28))  # most recent 28 actuals for rolling calcs

    branch_code = _encode(branch_id, bundle["branch_categories"])
    sku_code = _encode(sku_id, bundle["sku_categories"])
    category = last_row["category"]
    category_code = _encode(category, bundle["category_categories"])

    last_date = pd.to_datetime(last_row["date"])
    selling_price = float(last_row["selling_price"])

    daily_predictions = []
    running_units = list(recent_units)  # will grow as we predict forward

    for step in range(1, horizon_days + 1):
        future_date = last_date + pd.Timedelta(days=step)
        dow = future_date.dayofweek
        month = future_date.month
        weekend_flag = 1 if dow >= 5 else 0
        # Demo assumption: no known future festival/promotion unless caller adjusts later
        festival_flag = 0
        promotion = 0

        lag_1 = running_units[-1] if len(running_units) >= 1 else 0
        lag_7 = running_units[-7] if len(running_units) >= 7 else np.mean(running_units)
        lag_14 = running_units[-14] if len(running_units) >= 14 else np.mean(running_units)
        lag_28 = running_units[-28] if len(running_units) >= 28 else np.mean(running_units)

        roll_7 = np.mean(running_units[-7:]) if running_units else 0
        roll_14 = np.mean(running_units[-14:]) if running_units else 0
        roll_28 = np.mean(running_units[-28:]) if running_units else 0

        feature_row = pd.DataFrame([{
            "lag_1": lag_1, "lag_7": lag_7, "lag_14": lag_14, "lag_28": lag_28,
            "rolling_mean_7": roll_7, "rolling_mean_14": roll_14, "rolling_mean_28": roll_28,
            "day_of_week": dow, "month": month, "weekend_flag": weekend_flag,
            "festival_flag": festival_flag, "promotion": promotion,
            "selling_price": selling_price,
            "branch_code": branch_code, "sku_code": sku_code, "category_code": category_code,
        }])[bundle["feature_columns"]]

        pred = max(0.0, float(model.predict(feature_row)[0]))
        daily_predictions.append({"date": future_date.date().isoformat(), "predicted_units": round(pred, 1)})
        running_units.append(pred)

    total_demand = round(sum(d["predicted_units"] for d in daily_predictions))

    return {
        "branch_id": branch_id,
        "sku_id": sku_id,
        "horizon_days": horizon_days,
        "daily_predictions": daily_predictions,
        "total_predicted_demand": total_demand,
    }


def get_metrics():
    bundle = load_model_bundle()
    return bundle["metrics"]
