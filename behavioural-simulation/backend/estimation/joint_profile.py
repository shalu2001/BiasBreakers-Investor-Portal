"""
joint_profile.py -- joint maximum-likelihood recovery of loss aversion (lambda)
and regret (gamma).

Instead of fitting the loss-aversion block, the regret block, and the matched-
stakes events SEPARATELY (which wastes Fund A and leaves lambda/gamma noisy), this
pools ALL decision data into ONE likelihood with shared parameters. Fund A then
contributes to lambda, and recovery rises to r ~ 0.92 (lambda) / 0.96 (gamma),
versus 0.84 / 0.79 for the piecewise pipeline (see experiments/joint_estimator.py).

alpha is NOT taken from this fit -- it is confounded with the response scale here.
Alpha comes from the scale-free feature estimator (alpha_features.py). The joint
lambda/gamma come out well-ORDERED but on a compressed scale, so an affine rescale
(trained offline -> joint_estimator.json) maps them back to the CPT scale for the
reward model and the displayed profile.
"""
import os
import json
import numpy as np
from scipy.optimize import minimize

_HERE = os.path.dirname(os.path.abspath(__file__))
_CFG = None
WC = 5000.0


def _load():
    global _CFG
    if _CFG is None:
        with open(os.path.join(_HERE, "joint_estimator.json")) as f:
            _CFG = json.load(f)
    return _CFG


def _clogit(p):
    p = np.clip(np.asarray(p, float), 0.02, 0.98)
    return np.log(p / (1.0 - p))


def session_scale(*wc_arrays):
    """Per-session robust scale of |wealth_change|. Normalising by this keeps the
    value term O(1) for BOTH aggressive (saturating) and gentle (graded) players,
    so the response-sharpness k no longer pins to its floor on real human play --
    which was collapsing lambda/gamma/alpha to boundary values. Median (not mean)
    so a single big swing doesn't dominate; floored so tiny-change sessions don't
    blow the scale up."""
    w = np.concatenate([np.abs(np.asarray(a, float)).ravel() for a in wc_arrays])
    w = w[w > 0]
    med = float(np.median(w)) if w.size else WC
    return float(np.clip(med, 3000.0, 1.0e6))


def _varr(wc, a, lam, scale=WC):
    x = np.asarray(wc, float) / scale
    return np.where(x >= 0, np.abs(x) ** a, -lam * np.abs(x) ** a)


def fit_joint(block1_log, block2_log, event_records):
    """Raw joint fit -> (alpha, lambda, gamma, k, tau). Needs no config file."""
    wcA = block1_log["wealth_change"].values.astype(float); yA = _clogit(block1_log["target_pct"].values)
    wcB = block2_log["wealth_change"].values.astype(float); gB = block2_log["market_gap"].values.astype(float)
    yB = _clogit(block2_log["target_pct"].values)
    s = session_scale(wcA, wcB)
    G = np.array([e["gain_pct"] for e in event_records], float)
    L = np.array([e["loss_pct"] for e in event_records], float)
    yE = _clogit(np.array([e["commit"] for e in event_records], float))

    def nll(p):
        a, lam, gam, k, tau = p
        rA = yA - k * _varr(wcA, a, lam, s)
        rB = yB - k * (_varr(wcB, a, lam, s) + gam * gB)
        rE = yE - tau * (0.5 * np.abs(G) ** a - 0.5 * lam * np.abs(L) ** a)
        return float(np.sum(rA ** 2) + np.sum(rB ** 2) + np.sum(rE ** 2) + ((a - 0.88) / 0.15) ** 2)

    bounds = [(0.5, 1.05), (1.0, 5.0), (0.0, 5.0), (0.05, 6.0), (0.05, 4.0)]
    best = None
    for x0 in [(0.88, 2.25, 1.5, 1.0, 0.7), (0.8, 3.5, 3.0, 1.5, 0.9)]:
        r = minimize(nll, x0, bounds=bounds, method="L-BFGS-B")
        best = r if (best is None or r.fun < best.fun) else best
    return tuple(float(v) for v in best.x)


def recover_lambda_gamma(block1_log, block2_log, event_records):
    """Production: pooled lambda/gamma rescaled to the CPT scale, with confidence."""
    cfg = _load()
    a, lam, gam, k, tau = fit_joint(block1_log, block2_log, event_records)
    lr = cfg["lambda_rescale"]; gr = cfg["gamma_rescale"]
    lam_s = float(np.clip(lr[0] + lr[1] * lam, 1.0, 8.0))
    gam_s = float(np.clip(gr[0] + gr[1] * gam, 0.0, 6.0))
    # confidence: near-constant responses carry little signal
    yA = _clogit(block1_log["target_pct"].values)
    yB = _clogit(block2_log["target_pct"].values)
    var = float(np.var(np.concatenate([yA, yB]))) if (len(yA) + len(yB)) else 0.0
    level = "ok" if var >= 0.15 else ("weak" if var >= 0.05 else "uninformative")
    reason = f"pooled fit over all decision data (response variance {var:.2f})"
    return {"lambda": lam_s, "gamma": gam_s,
            "raw": {"alpha": a, "lambda": lam, "gamma": gam, "k": k, "tau": tau},
            "confidence": {"lambda": {"level": level, "reason": reason},
                           "gamma": {"level": level, "reason": reason}}}
