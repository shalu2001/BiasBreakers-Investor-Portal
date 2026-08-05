"""
Shared estimator: the maximum-likelihood recovery of (alpha, lambda, gamma) from a
set of decisions. Used by BOTH Stage 3 (static recovery) and Stage 6 (drift
recovery), so the two experiments use the identical machinery.

The likelihood model matches the generator exactly: a three-way BUY/SELL/HOLD
choice with the generator's response slope and hold-baseline (see config.py).
"""
import numpy as np
from scipy.optimize import minimize
from config import SENT_SLOPE, HOLD_BASE, WC_SCALE

BOUNDS = [(0.5, 1.05), (1.0, 5.0), (0.0, 6.0)]
SEEDS = [(0.85, 2.0, 0.5), (0.70, 4.0, 0.1), (0.90, 1.3, 4.0), (0.75, 2.5, 0.8)]


def fit_choice_model(sub):
    """sub: DataFrame with columns wealth_change, market_gap, action.
    Returns (alpha, lambda, gamma) that make the observed choices most likely."""
    wc = sub["wealth_change"].values / WC_SCALE
    mg = sub["market_gap"].values
    is_buy = (sub["action"] == "BUY").astype(int).values
    is_sell = (sub["action"] == "SELL").astype(int).values
    is_hold = (sub["action"] == "HOLD").astype(int).values

    def neg_log_likelihood(params):
        alpha, lam, gamma = params
        v = np.where(wc >= 0, np.power(np.abs(wc), alpha), -lam * np.power(np.abs(wc), alpha))
        sentiment = v - gamma * mg
        w_buy = np.exp(np.clip(SENT_SLOPE * sentiment, -8, 8))
        w_sell = np.exp(np.clip(-SENT_SLOPE * sentiment, -8, 8))
        Z = w_buy + w_sell + HOLD_BASE
        eps = 1e-12
        ll = (is_buy * np.log(w_buy / Z + eps) +
              is_sell * np.log(w_sell / Z + eps) +
              is_hold * np.log(HOLD_BASE / Z + eps))
        return -ll.sum()

    best = None
    for s in SEEDS:
        r = minimize(neg_log_likelihood, s, bounds=BOUNDS, method="L-BFGS-B")
        if best is None or r.fun < best.fun:
            best = r
    return best.x
