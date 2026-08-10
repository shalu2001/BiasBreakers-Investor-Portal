"""
regret_gamma.py -- dedicated estimator for regret / FOMO (gamma).

WHY A DEDICATED ESTIMATOR (and not the joint gamma)
---------------------------------------------------
The joint estimator models allocation LEVELS as a memoryless function of the
current step's value + market gap. Real players don't decide that way: they carry
their previous allocation and NUDGE it (allocation inertia / partial adjustment),
so their level is dominated by a slow trend, not by the instantaneous gap. Against
that, the joint's gap coefficient collapses to its 0 floor even when the player is
clearly reacting to the market -- and two sessions that chased the market to
different degrees both read gamma = 0.

The fix: work on the CHANGE in allocation. Under partial adjustment,

    Delta clogit(alloc)_t  ~  k * ( v(wc_t)  +  gamma * gap_t )

so differencing removes the sticky trend, and regressing the allocation change on
the current value term and the current gap recovers gamma = (gap coef)/(value coef)
-- scale-free in k, and robust to inertia. This is what the regret block was
designed to expose. gamma is allowed to be ~0 for a genuine non-chaser, but it is
no longer HARD-floored, and it cleanly separates players who chased more from
players who chased less. An affine rescale (trained offline -> regret_gamma.json)
maps the raw slope onto the CPT gamma scale.
"""
import os
import json
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_CFG = None
ALPHA0 = 0.85          # gamma is insensitive to alpha; a fixed curvature is plenty here
MIN_OBS = 6


def _load():
    global _CFG
    if _CFG is None:
        p = os.path.join(_HERE, "regret_gamma.json")
        _CFG = json.load(open(p)) if os.path.exists(p) else {
            "gamma_rescale": [0.0, 1.0], "gam_terciles": [1.7, 2.6], "gam_anchors": []}
    return _CFG


def _clogit(p):
    p = np.clip(np.asarray(p, float), 0.02, 0.98)
    return np.log(p / (1.0 - p))


def _scale(wc):
    w = np.abs(np.asarray(wc, float)); w = w[w > 0]
    med = float(np.median(w)) if w.size else 5000.0
    return float(np.clip(med, 3000.0, 1.0e6))


def raw_gamma_slope(block2_log):
    """Inertia-robust raw FOMO signal from the regret block. Returns (raw, tstat, n)."""
    alloc = block2_log["target_pct"].values.astype(float)
    wc = block2_log["wealth_change"].values.astype(float)
    gap = block2_log["market_gap"].values.astype(float)
    y = _clogit(alloc)
    s = _scale(wc)
    v = np.sign(wc) * np.abs(wc / s) ** ALPHA0
    dy = np.diff(y); vv = v[1:]; gg = gap[1:]
    if len(dy) < MIN_OBS or np.std(gg) < 1e-9 or np.std(dy) < 1e-9:
        return None, 0.0, len(dy)
    # STANDARDISED partial slope of the gap on the allocation CHANGE, controlling for
    # the wealth-change value term. This is the standard partial-effect measure: it is
    # bounded and stable (no ratio blow-up when the value response is small), never
    # hard-floors at 0, and cleanly separates a strong chaser from a weak one. An
    # affine rescale (trained offline) maps it onto the CPT gamma scale.
    z = lambda a: (a - a.mean()) / (a.std() + 1e-9)
    vz, gz, dyz = z(vv), z(gg), z(dy)
    X = np.column_stack([vz, gz, np.ones_like(gz)])
    beta, *_ = np.linalg.lstsq(X, dyz, rcond=None)
    resid = dyz - X @ beta
    dof = max(len(dy) - 3, 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.abs(np.diag(np.linalg.pinv(X.T @ X))) * sigma2)
    cg = beta[1]
    tstat = abs(cg) / se[1] if se[1] > 0 else 0.0
    return float(cg), float(tstat), len(dy)


def estimate_gamma(block2_log):
    """Recover gamma from the regret block. Returns {gamma, raw, confidence}."""
    cfg = _load()
    raw, tstat, n = raw_gamma_slope(block2_log)
    if raw is None:
        return {"gamma": float(cfg["gam_terciles"][0]), "raw": None,
                "confidence": {"level": "uninformative",
                               "reason": "too few regret-block decisions to read a market response"}}
    a, b = cfg["gamma_rescale"]
    lo, hi = cfg.get("raw_winsor", [-1e9, 1e9])
    rawc = float(np.clip(raw, lo, hi))          # tame the ratio tail, as in training
    gamma = float(np.clip(a + b * rawc, 0.0, 6.0))
    level = "ok" if tstat >= 1.3 else ("weak" if tstat >= 0.6 else "uninformative")
    reason = f"reaction of allocation CHANGES to the market gap (t={tstat:.2f})"
    return {"gamma": gamma, "raw": float(raw),
            "confidence": {"level": level, "reason": reason}}
