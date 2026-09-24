"""
train_model.py
---------------
Trains the demand-forecasting RandomForest model on the synthetic sales
dataset and saves it (with evaluation metrics) to /models/demand_model.pkl.

Run:
    python scripts/train_model.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from forecasting.model import train_and_save_model  # noqa: E402

if __name__ == "__main__":
    metrics = train_and_save_model()
    print("\nFinal evaluation metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
