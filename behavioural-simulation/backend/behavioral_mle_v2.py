import numpy as np
from scipy.optimize import minimize

PRIOR_MEANS = {"alpha": 0.88, "lambda": 2.25, "gamma": 1.5}
PRIOR_STDS  = {"alpha": 0.15, "lambda": 1.25, "gamma": 3.0}
W_ALPHA_LAMBDA = 8.0
W_GAMMA = 0.3

CALIBRATION = {
    "alpha": {"a": 0.7090, "b": 0.2269},
    "lambda": {"a": 0.0528, "b": 1.3167},
    "gamma": {"a": -0.1770, "b": 0.7669},
}


def _compute_std_errors(objective, x_opt, epsilon=1e-4):
    """
    Approximates how uncertain each parameter estimate is, using a numerical
    Hessian (curvature) of the objective at the fitted point. A sharp,
    narrow curve means high confidence; a shallow, flat curve means the
    data barely constrained that parameter -- this is exactly the kind of
    honest uncertainty a small sample should report, rather than a single
    falsely-precise number.
    """
    n = len(x_opt)
    hessian = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            x_pp, x_pm, x_mp, x_mm = [x_opt.copy() for _ in range(4)]
            x_pp[i] += epsilon; x_pp[j] += epsilon
            x_pm[i] += epsilon; x_pm[j] -= epsilon
            x_mp[i] -= epsilon; x_mp[j] += epsilon
            x_mm[i] -= epsilon; x_mm[j] -= epsilon
            hessian[i, j] = (objective(x_pp) - objective(x_pm) - objective(x_mp) + objective(x_mm)) / (4 * epsilon ** 2)

    try:
        cov = np.linalg.inv(hessian)
        std_errors = np.sqrt(np.abs(np.diag(cov)))[:3]
    except np.linalg.LinAlgError:
        std_errors = np.full(3, np.nan)
    return std_errors


def fit_behavioral_params(trade_log_df, starting_equity=1_000_000.0, n_starts=8, seed=42, apply_calibration=True):
    """
    Fits (alpha, lambda, gamma) from a live session's trade log using the
    validated 3-way multinomial model (BUY/SELL/HOLD), corrected wealth-change
    scaling, and the decoupled market_gap signal.

    trade_log_df must have columns: wealth_change, market_gap, action (BUY/SELL/HOLD)
    """
    if "is_checkpoint_decision" in trade_log_df.columns:
        trade_log_df = trade_log_df[trade_log_df["is_checkpoint_decision"]].reset_index(drop=True)

    wc_scale = starting_equity / 200
    wc_scaled = trade_log_df["wealth_change"].values / wc_scale
    mg = trade_log_df["market_gap"].values

    is_buy = (trade_log_df["action"] == "BUY").astype(int).values
    is_sell = (trade_log_df["action"] == "SELL").astype(int).values
    is_hold = (trade_log_df["action"] == "HOLD").astype(int).values

    def neg_log_posterior(params):
        alpha, lam, gamma, k, c = params
        v = np.where(wc_scaled >= 0, np.power(np.abs(wc_scaled), alpha), -lam * np.power(np.abs(wc_scaled), alpha))
        sentiment = v - gamma * mg
        u_b, u_s, u_h = k * sentiment, -k * sentiment, np.full_like(sentiment, c)
        m = np.maximum(np.maximum(u_b, u_s), u_h)
        e_b, e_s, e_h = np.exp(u_b - m), np.exp(u_s - m), np.exp(u_h - m)
        denom = e_b + e_s + e_h
        p_b, p_s, p_h = e_b / denom, e_s / denom, e_h / denom
        eps = 1e-15
        ll = is_buy * np.log(p_b + eps) + is_sell * np.log(p_s + eps) + is_hold * np.log(p_h + eps)
        penalty = (
            W_ALPHA_LAMBDA * (((alpha - PRIOR_MEANS["alpha"]) / PRIOR_STDS["alpha"]) ** 2 +
                               ((lam - PRIOR_MEANS["lambda"]) / PRIOR_STDS["lambda"]) ** 2) +
            W_GAMMA * ((gamma - PRIOR_MEANS["gamma"]) / PRIOR_STDS["gamma"]) ** 2
        )
        return -np.sum(ll) + penalty

    bounds = [(0.3, 1.2), (0.5, 6.0), (0.0, 6.0), (0.001, 3.0), (-3.0, 3.0)]
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_starts):
        x0 = [rng.uniform(0.5, 1.0), rng.uniform(1.0, 4.0), rng.uniform(0.2, 2.0),
              rng.uniform(0.05, 1.0), rng.uniform(-1.0, 1.0)]
        res = minimize(neg_log_posterior, x0, bounds=bounds, method="L-BFGS-B",
                        options={"ftol": 1e-10, "gtol": 1e-10})
        if best is None or res.fun < best.fun:
            best = res

    raw_alpha, raw_lambda, raw_gamma, k_hat, c_hat = best.x
    std_errors = _compute_std_errors(neg_log_posterior, best.x)

    result = {
        "raw": {"alpha": raw_alpha, "lambda": raw_lambda, "gamma": raw_gamma},
        "std_errors": {"alpha": std_errors[0], "lambda": std_errors[1], "gamma": std_errors[2]},
        "n_obs": len(trade_log_df),
        "converged": best.success,
    }

    if apply_calibration:
        result["calibrated"] = {
            "alpha": CALIBRATION["alpha"]["a"] + CALIBRATION["alpha"]["b"] * raw_alpha,
            "lambda": CALIBRATION["lambda"]["a"] + CALIBRATION["lambda"]["b"] * raw_lambda,
            "gamma": CALIBRATION["gamma"]["a"] + CALIBRATION["gamma"]["b"] * raw_gamma,
        }
        result["lambda_caveat"] = (
            "Lambda calibration does not reliably extrapolate beyond the validated "
            "persona range (true lambda 1.05-4.50). Treat as directionally useful "
            "(relative ordering validated, rank correlation 0.90) rather than exact."
        )

    return result