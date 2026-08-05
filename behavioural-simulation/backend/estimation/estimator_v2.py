"""
estimator_v2 -- robust behavioural parameter estimation.

Motivated by a parameter-recovery study (synthetic players with known
alpha/lambda/gamma played the real game engine, then were fitted back):

    parameter   old estimator (free-form MLE)   status
    ---------   -----------------------------   ------------------------------
    gamma       Pearson ~0.82                    identified well
    lambda      Pearson ~0.41, Spearman ~0.27    weakly identified
    alpha       Pearson ~ -0.20                  NOT identified (confounded)

Key changes here:
  * ALPHA is FIXED at the canonical Tversky-Kahneman value (0.88). It is not
    identifiable from a short interactive session -- it is confounded with the
    response-scale term -- and its population variance is small, so fixing it
    is both standard and honest.
  * LAMBDA is estimated from the loss-aversion block ONLY, with the regret
    (market_gap) term removed, so the loss response is not contaminated by
    FOMO. It uses a closed-form asymmetry regression: lambda = loss_slope /
    gain_slope. (NOTE: even so, free-form allocation identifies lambda only
    weakly -- see lambda_events.py for the matched-stakes fix.)
  * GAMMA is estimated from the regret block via the market_gap slope
    (recovery improves to Pearson ~0.86, bias roughly halved).
  * Every fit returns a CONFIDENCE diagnostic, so an unresponsive player is
    flagged instead of silently collapsing to the prior mean.
"""
import numpy as np

ALPHA_FIXED = 0.88
WC_SCALE_DIV = 200          # wealth_change / (starting_equity / WC_SCALE_DIV)
MIN_RESPONSE_VAR = 0.06     # variance of logit(target) below this = "didn't really play"


def _prep(df):
    if "is_checkpoint_decision" in df.columns:
        df = df[df["is_checkpoint_decision"]]
    return df[df["wealth_change"].notna() & df["market_gap"].notna()].reset_index(drop=True)


def _ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = float(resid @ resid) / dof
    cov = np.linalg.pinv(X.T @ X) * sigma2
    se = np.sqrt(np.abs(np.diag(cov)))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) + 1e-12
    r2 = 1.0 - float(resid @ resid) / ss_tot
    return beta, se, r2


def _confidence(resp_var, key_beta, key_se, n_pos, n_neg, block):
    if resp_var < MIN_RESPONSE_VAR:
        return {"level": "uninformative",
                "reason": (f"player barely moved the slider in the {block} block "
                           f"(response variance {resp_var:.3f}); estimate is not trustworthy")}
    if n_pos < 4 or n_neg < 4:
        return {"level": "weak", "reason": f"too few observations on one side (pos={n_pos}, neg={n_neg})"}
    tstat = abs(key_beta) / key_se if key_se and key_se > 0 else 0.0
    if tstat < 1.5:
        return {"level": "weak", "reason": f"key response coefficient not clearly non-zero (t={tstat:.2f})"}
    return {"level": "ok", "reason": f"clear, consistent response (t={tstat:.2f})"}


def fit_loss_aversion(block1_log, starting_equity=1_000_000.0, alpha=ALPHA_FIXED):
    """lambda from the loss-aversion block via a closed-form asymmetry regression."""
    df = _prep(block1_log)
    wc = df["wealth_change"].values / (starting_equity / WC_SCALE_DIV)
    p = np.clip(df["target_pct"].values, 0.02, 0.98)
    y = np.log(p / (1 - p))
    fg = np.power(np.maximum(wc, 0.0), alpha)      # gain feature
    fl = np.power(np.maximum(-wc, 0.0), alpha)     # loss feature
    X = np.column_stack([fg, fl, np.ones_like(wc)])
    beta, se, r2 = _ols(X, y)
    bg, bl_signed, _ = beta                        # expect bg>0, bl_signed<0
    bl = -bl_signed
    resp_var = float(np.var(y))
    n_gain, n_loss = int((wc > 0).sum()), int((wc < 0).sum())

    lam = bl / bg if bg > 1e-6 else np.nan
    if bg > 1e-6 and np.isfinite(lam):
        var_lam = (se[1] ** 2) / bg ** 2 + (bl ** 2) * (se[0] ** 2) / bg ** 4
        se_lam = float(np.sqrt(max(var_lam, 0.0)))
    else:
        se_lam = None

    conf = _confidence(resp_var, bg, se[0], n_gain, n_loss, "loss-aversion")
    lam_val = float(np.clip(lam, 0.3, 8.0)) if np.isfinite(lam) else None
    return {"estimate": lam_val, "se": se_lam, "r2": float(r2),
            "beta_gain": float(bg), "beta_loss": float(bl),
            "n_gain": n_gain, "n_loss": n_loss,
            "response_var": resp_var, "confidence": conf}


def fit_regret(block2_log, starting_equity=1_000_000.0, alpha=ALPHA_FIXED):
    """gamma from the regret block: sensitivity to market_gap, controlling for own P&L."""
    df = _prep(block2_log)
    wc = df["wealth_change"].values / (starting_equity / WC_SCALE_DIV)
    mg = df["market_gap"].values
    p = np.clip(df["target_pct"].values, 0.02, 0.98)
    y = np.log(p / (1 - p))
    v = np.where(wc >= 0, np.power(np.abs(wc), alpha), -np.power(np.abs(wc), alpha))
    X = np.column_stack([v, mg, np.ones_like(wc)])
    beta, se, r2 = _ols(X, y)
    bv, bm, _ = beta
    resp_var = float(np.var(y))
    gamma = bm / bv if abs(bv) > 1e-6 else bm
    conf = _confidence(resp_var, abs(bm), se[1], int((mg > 0).sum()), int((mg < 0).sum()), "regret")
    return {"estimate": float(np.clip(gamma, 0.0, 8.0)), "se": float(se[1]), "r2": float(r2),
            "beta_mg": float(bm), "response_var": resp_var, "confidence": conf}


def fit_profile_v2(loss_aversion_log, regret_log, starting_equity=1_000_000.0):
    la = fit_loss_aversion(loss_aversion_log, starting_equity)
    rg = fit_regret(regret_log, starting_equity)
    return {
        "alpha": ALPHA_FIXED,
        "alpha_note": "fixed at the canonical Tversky-Kahneman value; not identifiable from a short session",
        "lambda": la["estimate"],
        "gamma": rg["estimate"],
        "diagnostics": {"loss_aversion": la, "regret": rg},
        "confidence": {"lambda": la["confidence"], "gamma": rg["confidence"]},
    }
