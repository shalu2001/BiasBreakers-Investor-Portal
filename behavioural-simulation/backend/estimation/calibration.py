"""
calibration.py -- simulation-based calibration of the behavioural parameters.

WHY
---
The raw MLE estimates are NOT the parameters. A one-parameter-at-a-time sweep
through the real game engine shows:
  * alpha: the raw estimate is an almost perfectly monotonic (|r|~0.98) but
    INVERTED and compressed function of true alpha -- rich signal, wrong scale.
  * gamma: raw estimate tracks true gamma well already.
  * lambda: from free-form allocation the raw estimate is non-monotonic in true
    lambda (rises then falls), so it needs either the matched-stakes event round
    (see lambda_events.py) or the multivariate calibration below.

Because the forward simulator (true params -> game behaviour -> raw estimate) is
fast and nearly deterministic, we can learn its INVERSE: a regressor that maps the
raw feature vector back to the true (alpha, lambda, gamma). This is indirect
inference / simulation-based calibration.

Out-of-fold recovery on 130 simulated players (honest held-out):

    parameter   raw estimate   calibrated (this module)
    ---------   ------------   ------------------------
    alpha       Pearson -0.25  Pearson +0.78   MAE 0.056
    lambda      Pearson +0.08  Pearson +0.67   MAE 0.58
    gamma       Pearson +0.83  Pearson +0.96   MAE 0.26

USAGE
-----
    # one-time / offline: build training data (slow -- runs the game many times)
    python calibration.py --generate 400

    # then, in the app:
    from estimation.calibration import load_default_calibrator
    cal = load_default_calibrator()               # trains from bundled CSV (fast)
    params = cal.calibrate(feature_dict)          # -> {"alpha":..,"lambda":..,"gamma":..}

FEATURES (must match between training and deployment): see FEATURES below.
"""
import os
from paths import ROOT as _ROOT
import numpy as np
import pandas as pd

FEATURES = ["ra", "rl", "rg2", "v2l", "v2g", "bg", "bl", "rv1", "rv2"]
TARGETS = ["ta", "tl", "tg"]
TARGET_ALIASES = {"ta": "alpha", "tl": "lambda", "tg": "gamma"}
DEFAULT_CSV = os.path.join(_ROOT, "calib_data.csv")


def features_from_fits(old_raw, v2):
    """Build the calibration feature vector from an old-estimator raw fit and a v2 fit.
    Used identically in training and at deployment so the mapping stays consistent."""
    la = v2["diagnostics"]["loss_aversion"]
    rg = v2["diagnostics"]["regret"]
    v2l = v2["lambda"] if v2["lambda"] is not None else old_raw["lambda"]
    return {
        "ra": old_raw["alpha"], "rl": old_raw["lambda"], "rg2": old_raw["gamma"],
        "v2l": v2l, "v2g": v2["gamma"],
        "bg": la["beta_gain"], "bl": la["beta_loss"],
        "rv1": la["response_var"], "rv2": rg["response_var"],
    }


class Calibrator:
    """Maps raw feature vectors -> (alpha, lambda, gamma). Uses gradient boosting
    if scikit-learn is available, else a pure-NumPy distance-weighted KNN."""

    def __init__(self, k=9):
        self.k = k
        self._mu = None
        self._sd = None
        self._Xs = None
        self._Y = None
        self._gbm = None
        self._backend = None

    def fit(self, df):
        X = df[FEATURES].values.astype(float)
        Y = df[TARGETS].values.astype(float)
        self._mu, self._sd = X.mean(0), X.std(0) + 1e-9
        self._Xs, self._Y = (X - self._mu) / self._sd, Y
        try:
            from sklearn.ensemble import GradientBoostingRegressor
            self._gbm = []
            for j in range(Y.shape[1]):
                m = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                              learning_rate=0.05, subsample=0.8, random_state=0)
                m.fit(self._Xs, Y[:, j])
                self._gbm.append(m)
            self._backend = "gradient_boosting"
        except Exception:
            self._backend = "knn"
        return self

    def _knn(self, xs):
        out = np.zeros(self._Y.shape[1])
        dist = np.sqrt(((self._Xs - xs) ** 2).sum(1))
        idx = np.argsort(dist)[:self.k]
        w = 1.0 / (dist[idx] + 1e-6)
        for j in range(self._Y.shape[1]):
            out[j] = np.sum(w * self._Y[idx, j]) / np.sum(w)
        return out

    def calibrate(self, feature_dict):
        x = np.array([feature_dict[f] for f in FEATURES], dtype=float)
        xs = (x - self._mu) / self._sd
        if self._backend == "gradient_boosting":
            vals = np.array([m.predict(xs.reshape(1, -1))[0] for m in self._gbm])
        else:
            vals = self._knn(xs)
        a, l, g = vals
        return {"alpha": float(np.clip(a, 0.4, 1.2)),
                "lambda": float(np.clip(l, 0.5, 6.0)),
                "gamma": float(np.clip(g, 0.0, 6.0)),
                "backend": self._backend}


def train_from_csv(csv_path=DEFAULT_CSV):
    df = pd.read_csv(csv_path)
    df["v2l"] = pd.to_numeric(df["v2l"], errors="coerce").fillna(df["rl"])
    return Calibrator().fit(df)


_DEFAULT = None
def load_default_calibrator():
    """Cached calibrator trained from the bundled CSV. Returns None if unavailable."""
    global _DEFAULT
    if _DEFAULT is None:
        try:
            _DEFAULT = train_from_csv(DEFAULT_CSV)
        except Exception:
            _DEFAULT = False
    return _DEFAULT or None


# --------------------------------------------------------------------------
def _generate(n, out_csv, seed=0):
    """Slow: run the game with known params to build calibration training data."""
    import csv, warnings
    warnings.filterwarnings("ignore")
    from game.multi_block_session import MultiBlockSession
    from estimation.final_estimator import fit_full_profile
    from estimation.estimator_v2 import fit_profile_v2
    scn = ["2021_bull_run", "2022_crash", "2023_recovery"]
    base = _ROOT
    data = {}
    for s in scn:
        b = os.path.join(base, "scenario_build", s)
        data[s] = (pd.read_csv(f"{b}_stocks.csv", parse_dates=["Date"]),
                   pd.read_csv(f"{b}_index.csv", parse_dates=["Date"]))
    WC = 5000.0
    sig = lambda x: 1 / (1 + np.exp(-np.clip(x, -30, 30)))
    rng = np.random.default_rng(seed)

    def play(a, l, g, k, noise):
        s = MultiBlockSession(data, 1_000_000, n_per_bin=3)
        while True:
            st = s.current_session
            wc = (st.total_equity() - st._prev_day_equity) / WC
            mg = st.market_gap()
            v = wc ** a if wc >= 0 else -l * (abs(wc) ** a)
            tgt = float(np.clip(sig(k * (v + g * mg) + rng.normal(0, noise)), 0.02, 0.98))
            s.set_allocation(s.get_tradable_ticker() or "JKH", tgt)
            if s.advance()["status"] == "all_blocks_complete":
                break
        l1, l2 = s.get_block_logs()
        old = fit_full_profile(l1, l2, starting_equity=1_000_000)["raw"]
        v2 = fit_profile_v2(l1, l2, starting_equity=1_000_000)
        feat = features_from_fits(old, v2)
        return {"ta": round(a, 4), "tl": round(l, 4), "tg": round(g, 4),
                **{key: round(val, 5) for key, val in feat.items()}}

    head = not os.path.exists(out_csv)
    with open(out_csv, "a", newline="") as fh:
        w = None
        for _ in range(n):
            r = play(rng.uniform(0.6, 1.0), rng.uniform(1.0, 4.5), rng.uniform(0.0, 4.5),
                     rng.uniform(0.5, 1.1), rng.uniform(0.10, 0.25))
            if w is None:
                w = csv.DictWriter(fh, fieldnames=list(r.keys()))
                if head:
                    w.writeheader()
            w.writerow(r); fh.flush()
    print(f"appended {n} rows to {out_csv}")


def _validate(csv_path=DEFAULT_CSV):
    from scipy.stats import pearsonr, spearmanr
    try:
        from sklearn.model_selection import KFold
        from sklearn.ensemble import GradientBoostingRegressor
    except Exception:
        print("scikit-learn not installed; skipping OOF validation."); return
    df = pd.read_csv(csv_path)
    df["v2l"] = pd.to_numeric(df["v2l"], errors="coerce").fillna(df["rl"])
    X = df[FEATURES].values.astype(float)
    print(f"Out-of-fold calibration recovery (N={len(df)}):")
    for tcol, raw in [("ta", "ra"), ("tl", "rl"), ("tg", "rg2")]:
        y = df[tcol].values; pred = np.zeros(len(y))
        for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
            m = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                          subsample=0.8, random_state=0).fit(X[tr], y[tr])
            pred[te] = m.predict(X[te])
        print(f"  {TARGET_ALIASES[tcol]:6s} raw r={pearsonr(y, df[raw].values)[0]:+.2f} "
              f"-> calibrated r={pearsonr(y, pred)[0]:+.2f}, MAE={np.mean(np.abs(pred - y)):.3f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "--generate":
        _generate(int(sys.argv[2]), DEFAULT_CSV, seed=int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else:
        _validate()
