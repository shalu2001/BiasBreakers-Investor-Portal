import numpy as np

CALIBRATION = {
    "alpha": {"a": 0.7090, "b": 0.2269},
    "lambda": {"a": 0.0528, "b": 1.3167},
    "gamma": {"a": -0.1770, "b": 0.7669},
}

def get_utility(wealth_change, market_gap, alpha, lam, gamma, starting_equity=1_000_000.0):
    wc_scale = starting_equity / 200
    wc_scaled = wealth_change / wc_scale

    if wc_scaled >= 0:
        value = wc_scaled ** alpha
    else:
        value = -lam * (abs(wc_scaled) ** alpha)

    # Stays as MINUS -- underperforming genuinely hurts (reward), even though
    # the estimator (predicting behavior) correctly uses the opposite sign
    # to capture the resulting FOMO-chasing response.
    regret_penalty = gamma * market_gap
    return value - regret_penalty


def calibrate_raw_estimate(raw_alpha, raw_lambda, raw_gamma):
    return {
        "alpha": CALIBRATION["alpha"]["a"] + CALIBRATION["alpha"]["b"] * raw_alpha,
        "lambda": CALIBRATION["lambda"]["a"] + CALIBRATION["lambda"]["b"] * raw_lambda,
        "gamma": CALIBRATION["gamma"]["a"] + CALIBRATION["gamma"]["b"] * raw_gamma,
    }