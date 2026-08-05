import numpy as np
from scipy.optimize import minimize

PRIOR_MEANS = {"alpha": 0.88, "lambda": 2.25, "gamma": 1.5}
PRIOR_STDS  = {"alpha": 0.15, "lambda": 1.25, "gamma": 3.0}
PRIOR_WEIGHT = 2.0

CALIBRATION = {
    "alpha": {"a": 0.7090, "b": 0.2269},
    "lambda": {"a": 0.0528, "b": 1.3167},
    "gamma": {"a": -0.1770, "b": 0.7669},
}


def _fit_block(trade_log_df, starting_equity, n_starts=8, seed=42):
    if "is_checkpoint_decision" in trade_log_df.columns:
        trade_log_df = trade_log_df[trade_log_df["is_checkpoint_decision"]].reset_index(drop=True)

    trade_log_df = trade_log_df[trade_log_df["wealth_change"].notna() & trade_log_df["market_gap"].notna()].reset_index(drop=True)

    wc_scale = starting_equity / 200
    wc = trade_log_df["wealth_change"].values / wc_scale
    mg = trade_log_df["market_gap"].values
    target_pct = np.clip(trade_log_df["target_pct"].values, 0.001, 0.999)
    y = np.log(target_pct / (1 - target_pct))

    def objective(params):
        alpha, lam, gamma, k, c = params
        v = np.where(wc >= 0, np.power(np.abs(wc), alpha), -lam * np.power(np.abs(wc), alpha))
        sentiment = v + gamma * mg
        pred = k * sentiment + c
        sse = np.sum((y - pred) ** 2)
        penalty = PRIOR_WEIGHT * (
            ((alpha - PRIOR_MEANS["alpha"]) / PRIOR_STDS["alpha"]) ** 2 +
            ((lam - PRIOR_MEANS["lambda"]) / PRIOR_STDS["lambda"]) ** 2 +
            ((gamma - PRIOR_MEANS["gamma"]) / PRIOR_STDS["gamma"]) ** 2
        )
        return sse + penalty

    bounds = [(0.3, 1.2), (0.5, 6.0), (0.0, 6.0), (0.001, 5.0), (-5.0, 5.0)]
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_starts):
        x0 = [rng.uniform(0.5, 1.0), rng.uniform(1.0, 4.0), rng.uniform(0.2, 2.0),
              rng.uniform(0.1, 2.0), rng.uniform(-1.0, 1.0)]
        res = minimize(objective, x0, bounds=bounds, method="L-BFGS-B")
        if best is None or res.fun < best.fun:
            best = res

    alpha, lam, gamma, k, c = best.x
    return {"alpha": alpha, "lambda": lam, "gamma": gamma, "n_obs": len(trade_log_df)}


def fit_full_profile(loss_aversion_log, regret_log, starting_equity=1_000_000.0, apply_calibration=True):
    block1_fit = _fit_block(loss_aversion_log, starting_equity)
    block2_fit = _fit_block(regret_log, starting_equity)

    raw = {"alpha": block1_fit["alpha"], "lambda": block1_fit["lambda"], "gamma": block2_fit["gamma"]}
    result = {"raw": raw, "n_obs_block1": block1_fit["n_obs"], "n_obs_block2": block2_fit["n_obs"]}

    if apply_calibration:
        result["calibrated"] = {
            "alpha": CALIBRATION["alpha"]["a"] + CALIBRATION["alpha"]["b"] * raw["alpha"],
            "lambda": CALIBRATION["lambda"]["a"] + CALIBRATION["lambda"]["b"] * raw["lambda"],
            "gamma": CALIBRATION["gamma"]["a"] + CALIBRATION["gamma"]["b"] * raw["gamma"],
        }
    return result