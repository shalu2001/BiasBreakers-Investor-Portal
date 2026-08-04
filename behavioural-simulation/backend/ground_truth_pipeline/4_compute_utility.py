"""
STAGE 4 - Compute the behavioural utility score (the dynamic utility).

Using each investor's RECOVERED (alpha, lambda, gamma), we score every day of their
history with a single Behavioural Utility number U:

    U = value(wealth_change; alpha, lambda) - gamma * market_gap

value() is the prospect-theory curve (gains dampened by alpha, losses amplified by
lambda); the second term penalises lagging the market (regret). This per-day U is
the signal that would be handed to the reinforcement-learning reward.

Output: outputs/behavioral_utility.csv  (investor_id, date, wealth_change,
market_gap, utility_score)
"""
import os
import numpy as np
import pandas as pd
from config import WC_SCALE

HERE = os.path.dirname(__file__)


def utility(wc, mg, alpha, lam, gamma):
    x = wc / WC_SCALE
    value = x ** alpha if x >= 0 else -lam * (abs(x) ** alpha)
    return value - gamma * mg


def main():
    log = pd.read_csv(os.path.join(HERE, "outputs", "behavioral_validation_log.csv"))
    params = pd.read_csv(os.path.join(HERE, "outputs", "recovered_parameters.csv"))
    df = log.merge(params, on="investor_id")

    df["utility_score"] = [
        utility(w, m, a, l, g)
        for w, m, a, l, g in zip(df["wealth_change"], df["market_gap"],
                                 df["estimated_alpha"], df["estimated_lambda"], df["estimated_gamma"])
    ]
    out = df[["investor_id", "date", "wealth_change", "market_gap", "utility_score"]]
    out.to_csv(os.path.join(HERE, "outputs", "behavioral_utility.csv"), index=False)
    print("Saved outputs/behavioral_utility.csv")
    print(out.groupby("investor_id")["utility_score"].agg(["mean", "std", "min", "max"]).round(3))


if __name__ == "__main__":
    main()
