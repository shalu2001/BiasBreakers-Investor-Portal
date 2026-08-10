"""
alpha_features.py -- production estimator for diminishing sensitivity (alpha).

WHY A SPECIAL ESTIMATOR: alpha (the curvature of the CPT value function) is
confounded with the response scale in a direct maximum-likelihood fit, so
free-fitting it fails -- it pins to a bound or comes out *negatively* correlated
with the truth. But SCALE-FREE summary features of the loss-aversion block carry
it, because correlation/spread are invariant to the response scale that breaks the
MLE:

    gain_corr       how tightly allocation tracks the SIZE of a gain
                    (near-linear investors scale their bet with the gain; curved
                    ones saturate)
    alloc_std       spread of allocations (graded vs all-or-nothing)
    gain_curvature  quadratic curvature of the allocation-vs-gain response

A small regression trained offline on synthetic investors of known alpha
(experiments/alpha_recovery.py -> alpha_regressor.json) maps those to alpha. This
is the SAME simulation-based-calibration idea used elsewhere in the pipeline.
Out-of-sample recovery: r ~ 0.73 (leave-one-out) and ~0.82 (train/test split),
versus ~0 for the previous fixed-0.88 approach.
"""
import os
import json
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODEL = None


def _load():
    global _MODEL
    if _MODEL is None:
        with open(os.path.join(_HERE, "alpha_regressor.json")) as f:
            _MODEL = json.load(f)
    return _MODEL


def _clogit(p):
    p = np.clip(np.asarray(p, dtype=float), 0.02, 0.98)
    return np.log(p / (1.0 - p))


def _session_scale(wc):
    """Per-session robust scale of |wealth_change| (matches joint_profile.session_scale)
    so the curvature feature is stable whether the player made small or huge swings."""
    w = np.abs(np.asarray(wc, float)); w = w[w > 0]
    med = float(np.median(w)) if w.size else 5000.0
    return float(np.clip(med, 3000.0, 1.0e6))


def _features(block1_log):
    """Scale-free alpha features from the loss-aversion block; None if too few gains."""
    m = _load()
    wc = block1_log["wealth_change"].values.astype(float)
    y = _clogit(block1_log["target_pct"].values)
    gains = wc > 0
    if int(gains.sum()) < int(m.get("min_gain_obs", 4)):
        return None
    s = _session_scale(wc)
    x, yy = wc[gains] / s, y[gains]           # normalise so curvature is scale-stable
    gc = float(np.corrcoef(x, yy)[0, 1]) if (np.std(x) > 0 and np.std(yy) > 0) else 0.0
    if not np.isfinite(gc):
        gc = 0.0
    alloc_std = float(np.std(block1_log["target_pct"].values))
    X = np.column_stack([x, x ** 2, np.ones_like(x)])
    b = np.linalg.lstsq(X, yy, rcond=None)[0]
    curv = float(b[1] / (abs(b[0]) + 1e-9))
    return np.array([gc, alloc_std, curv], dtype=float)


def estimate_alpha(block1_log):
    """Recover alpha from the loss-aversion block.

    Returns {"alpha": float, "confidence": {"level","reason"}}. Falls back to the
    canonical Tversky-Kahneman value (0.88) when the block has too few gain
    decisions to read curvature.
    """
    m = _load()
    f = _features(block1_log)
    if f is None:
        return {"alpha": float(m["alpha_prior"]),
                "confidence": {"level": "uninformative",
                               "reason": "too few gain decisions to read curvature"}}
    z = (f - np.array(m["mu"])) / np.array(m["sd"])
    beta = np.array(m["beta"])
    raw = float(np.dot(z, beta[:-1]) + beta[-1])
    lo, hi = m.get("clip", [0.5, 1.0])
    # When the raw prediction lands well OUTSIDE the identifiable range, the player's
    # features are off the end of the training distribution -- typically a near-linear,
    # gentle response (small allocation spread) that carries no real curvature signal.
    # Reporting a confident clipped value there is dishonest, so we fall back to the
    # population prior and flag it, instead of pinning a spurious alpha = 1.0.
    if raw > hi + 0.05 or raw < lo - 0.05:
        return {"alpha": float(m["alpha_prior"]),
                "confidence": {"level": "weak",
                               "reason": "near-linear response; curvature (diminishing sensitivity) "
                                         "not reliably identifiable from this session"}}
    a = float(np.clip(raw, lo, hi))
    return {"alpha": a,
            "confidence": {"level": "ok",
                           "reason": f"recovered from loss-block curvature (validated r~{m.get('loo_r', 0):.2f})"}}
