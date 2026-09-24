"""
services/forecast_service.py
------------------------------
Wraps the ML forecasting model for use by the API layer, with a small
in-memory cache of the sales dataframe so repeated forecasts don't
reload the whole table from SQLite every time.
"""
from forecasting import model as forecasting_model
from services.data_service import get_sales_dataframe

_sales_df_cache = None


def _sales_df():
    global _sales_df_cache
    if _sales_df_cache is None:
        _sales_df_cache = get_sales_dataframe()
    return _sales_df_cache


def refresh_cache():
    global _sales_df_cache
    _sales_df_cache = get_sales_dataframe()


def forecast_for(branch_id, sku_id, horizon_days):
    return forecasting_model.predict_demand(branch_id, sku_id, horizon_days, sales_df=_sales_df())


def forecast_all_branches(branch_ids, sku_id, horizon_days):
    """Runs a forecast for one SKU across multiple branches (used by the dashboard)."""
    results = []
    for branch_id in branch_ids:
        try:
            r = forecast_for(branch_id, sku_id, horizon_days)
            results.append(r)
        except ValueError:
            continue
    return results


def model_metrics():
    return forecasting_model.get_metrics()
