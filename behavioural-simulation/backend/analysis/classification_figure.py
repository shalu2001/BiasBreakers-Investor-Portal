"""
classification_figure.py -- "can we tell one psychology from another?"

Produces confusion matrices for each behavioural parameter: given an investor of a
known behavioural BAND (e.g. loss-neutral / moderate / strongly loss-averse), what
band do we classify them into after they play? A strong diagonal = we reliably
recover the type.

  * lambda  -> from the matched-stakes event round (16 events)
  * gamma   -> from the free-play calibration (out-of-fold)
  * alpha   -> from the free-play calibration (out-of-fold)

Run:  python classification_figure.py   ->  validation_classification.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from paths import ROOT as BASE

BANDS = {
    "lambda": ([(-1, 1.5), (1.5, 2.75), (2.75, 99)], ["Loss-\nneutral", "Moderate", "Strongly\nloss-averse"]),
    "gamma":  ([(-1, 1.0), (1.0, 2.5), (2.5, 99)],  ["Regret-\nindifferent", "Regret-\nsensitive", "Strong\nFOMO"]),
    "alpha":  ([(-1, 0.75), (0.75, 0.9), (0.9, 9)], ["Strongly\ndiminishing", "Moderate", "Near-\nlinear"]),
}


def _bin(v, edges):
    for i, (lo, hi) in enumerate(edges):
        if lo <= v < hi:
            return i
    return len(edges) - 1


def _confusion(true_vals, rec_vals, edges):
    n = len(edges)
    M = np.zeros((n, n))
    for t, r in zip(true_vals, rec_vals):
        M[_bin(t, edges), _bin(r, edges)] += 1
    acc = np.trace(M) / M.sum()
    Mn = M / M.sum(1, keepdims=True).clip(min=1) * 100
    return Mn, acc


def lambda_recovery(n=800, n_events=16, seed=0):
    from estimation.lambda_events import EVENT_GRID, event_cpt_value, fit_lambda_events
    rng = np.random.default_rng(seed)
    grid = EVENT_GRID[:n_events]
    tl, el = [], []
    for _ in range(n):
        lam = rng.uniform(1.0, 4.5); tau = rng.uniform(0.5, 1.2); noise = rng.uniform(0.15, 0.30)
        recs = []
        for (g, l) in grid:
            val = event_cpt_value(g, l, lam)
            c = 1 / (1 + np.exp(-(tau * val + rng.normal(0, noise))))
            recs.append({"gain_pct": g, "loss_pct": l, "commit": float(np.clip(c, 0.02, 0.98))})
        est = fit_lambda_events(recs)["estimate"]
        if est is not None:
            tl.append(lam); el.append(est)
    return np.array(tl), np.array(el)


def oof_recovery(param):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import KFold
    import estimation.calibration as C
    df = pd.read_csv(os.path.join(BASE, "calib_data.csv"))
    df["v2l"] = pd.to_numeric(df["v2l"], errors="coerce").fillna(df["rl"])
    X = df[C.FEATURES].values
    y = df[{"alpha": "ta", "gamma": "tg"}[param]].values
    pred = np.zeros(len(y))
    for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
        m = GradientBoostingRegressor(n_estimators=350, max_depth=3, learning_rate=0.05,
                                      subsample=0.8, random_state=0).fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return y, pred


def main():
    panels = [
        ("lambda", "Loss aversion (λ)\nfrom matched-stakes events", *lambda_recovery()),
        ("gamma", "Regret / FOMO (γ)\nfrom free-play", *oof_recovery("gamma")),
        ("alpha", "Diminishing sensitivity (α)\nfrom free-play", *oof_recovery("alpha")),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
    for ax, (key, title, tv, rv) in zip(axes, panels):
        edges, labels = BANDS[key]
        M, acc = _confusion(tv, rv, edges)
        im = ax.imshow(M, cmap="YlGnBu", vmin=0, vmax=100)
        ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9); ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("Classified as", fontsize=11); ax.set_ylabel("True type", fontsize=11)
        ax.set_title(f"{title}\naccuracy = {acc*100:.0f}%", fontsize=12, weight="bold")
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{M[i,j]:.0f}%", ha="center", va="center",
                        color="white" if M[i, j] > 55 else "#1A365D", fontsize=11, weight="bold")
    plt.tight_layout()
    out = os.path.join(BASE, "validation_classification.png")
    plt.savefig(out, dpi=150); plt.close()
    print("saved", out)


if __name__ == "__main__":
    main()
