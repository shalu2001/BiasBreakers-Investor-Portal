import pandas as pd
import numpy as np


def select_stratified_checkpoints(index_df, n_per_bin=3, seed=42):
    df = index_df.copy().sort_values("Date").reset_index(drop=True)
    df["index_return_pct"] = df["SP_SL20"].pct_change() * 100
    df = df.dropna(subset=["index_return_pct"])

    bins = [-np.inf, -3.0, -0.5, 0.5, 3.0, np.inf]
    labels = ["severe_drop", "moderate_drop", "calm", "moderate_rally", "severe_rally"]
    df["bin"] = pd.cut(df["index_return_pct"], bins=bins, labels=labels)

    rng = np.random.default_rng(seed)
    selected_dates = []
    bin_counts = {}
    for label in labels:
        bucket = df[df["bin"] == label]
        n_take = min(n_per_bin, len(bucket))
        bin_counts[label] = (n_take, len(bucket))
        if n_take > 0:
            chosen = rng.choice(bucket["Date"].values, size=n_take, replace=False)
            selected_dates.extend(chosen)

    return sorted(selected_dates), bin_counts