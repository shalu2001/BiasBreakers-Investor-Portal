"""
validation.py -- parameter-recovery validation of the behavioural estimation.

This is the "true validation" leg of the validation-vs-deployment design:
we KNOW each synthetic investor's (alpha, lambda, gamma), have them trade the
real game according to that psychology, recover the parameters via the
simulation-based calibration, and check we get the truth back.

Two evidence layers:
  1. CONTINUUM recovery -- random (alpha, lambda, gamma) across the standard
     literature ranges; honest out-of-fold recovery (correlation, rank, MAE),
     plus single-session error (the realistic case, since a human plays once).
  2. ARCHETYPE recovery -- named, literature-grounded personas, each played
     many times; the recovered distribution should bracket the true value.
     Held-out: the calibrator is trained on the random continuum, never on
     the archetype points.
  3. DISCRIMINATION -- can we correctly separate a loss-averse investor from a
     loss-tolerant one? (accuracy / AUC). This is the practical claim a single
     human sanity-check relies on.

Run:
    python validation.py --archetypes 12     # generate archetype sessions (slow)
    python validation.py --analyze           # metrics + plots (fast)

Parameter ranges follow Tversky & Kahneman (1992, "Advances in Prospect
Theory"): median alpha = 0.88, lambda = 2.25. Empirical lambda across studies
typically falls in ~1.0-3.5; alpha in ~0.5-1.0. gamma (regret/FOMO sensitivity)
is a model parameter of this framework, ranged 0.0-4.5.
"""
import os, csv, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

BASE = os.path.dirname(__file__)
ARCH_CSV = os.path.join(BASE, "archetype_data.csv")
CALIB_CSV = os.path.join(BASE, "calib_data.csv")

# Literature-grounded named personas: (alpha, lambda, gamma)
ARCHETYPES = {
    "Rational (loss-neutral)":        (0.90, 1.05, 0.10),
    "Canonical PT (T-K 1992)":        (0.88, 2.25, 1.00),
    "Strong loss-averse":             (0.80, 3.50, 1.00),
    "Loss-tolerant risk-seeker":      (0.95, 1.20, 0.50),
    "FOMO chaser":                    (0.88, 1.80, 4.00),
    "Regret-immune veteran":          (0.85, 2.50, 0.10),
}


def _load_scenarios():
    scn = ["2021_bull_run", "2022_crash", "2023_recovery"]
    d = {}
    for s in scn:
        b = os.path.join(BASE, "scenario_build", s)
        d[s] = (pd.read_csv(f"{b}_stocks.csv", parse_dates=["Date"]),
                pd.read_csv(f"{b}_index.csv", parse_dates=["Date"]))
    return d


def _play_and_featurize(a, l, g, k, noise, data, rng):
    from multi_block_session import MultiBlockSession
    from final_estimator import fit_full_profile
    from estimator_v2 import fit_profile_v2
    from calibration import features_from_fits
    WC = 5000.0
    sig = lambda x: 1 / (1 + np.exp(-np.clip(x, -30, 30)))
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
    return features_from_fits(old, v2)


def generate_archetypes(reps, seed=0):
    data = _load_scenarios()
    rng = np.random.default_rng(seed)
    head = not os.path.exists(ARCH_CSV)
    with open(ARCH_CSV, "a", newline="") as fh:
        w = None
        for name, (a, l, g) in ARCHETYPES.items():
            for _ in range(reps):
                k = rng.uniform(0.6, 1.0)         # individual responsiveness
                noise = rng.uniform(0.12, 0.22)   # individual consistency
                feat = _play_and_featurize(a, l, g, k, noise, data, rng)
                row = {"persona": name, "ta": a, "tl": l, "tg": g,
                       **{key: round(val, 5) for key, val in feat.items()}}
                if w is None:
                    w = csv.DictWriter(fh, fieldnames=list(row.keys()))
                    if head:
                        w.writeheader()
                w.writerow(row); fh.flush()
        print(f"appended {reps} reps/persona to {ARCH_CSV}")


def analyze():
    from scipy.stats import pearsonr, spearmanr
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import KFold
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import calibration as C

    feats = C.FEATURES
    df = pd.read_csv(CALIB_CSV)
    df["v2l"] = pd.to_numeric(df["v2l"], errors="coerce").fillna(df["rl"])
    X = df[feats].values

    # ---- 1. Continuum recovery (out-of-fold) ----
    labels = [("alpha", "ta", "ra"), ("lambda", "tl", "rl"), ("gamma", "tg", "rg2")]
    oof = {}
    print(f"=== CONTINUUM RECOVERY (out-of-fold, N={len(df)}) ===")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, (nm, tc, rc) in zip(axes, labels):
        y = df[tc].values
        pred = np.zeros(len(y))
        for tr, te in KFold(5, shuffle=True, random_state=0).split(X):
            m = GradientBoostingRegressor(n_estimators=350, max_depth=3, learning_rate=0.05,
                                          subsample=0.8, random_state=0).fit(X[tr], y[tr])
            pred[te] = m.predict(X[te])
        oof[nm] = pred
        r, rho = pearsonr(y, pred)[0], spearmanr(y, pred)[0]
        mae = np.mean(np.abs(pred - y))
        print(f"  {nm:6s}: Pearson r={r:+.3f}  Spearman={rho:+.3f}  MAE={mae:.3f}  R2={r**2:.3f}")
        ax.scatter(y, pred, s=14, alpha=0.5, color="#1A365D")
        lo, hi = min(y.min(), pred.min()), max(y.max(), pred.max())
        ax.plot([lo, hi], [lo, hi], "--", color="#D4A73C", lw=1.5)
        ax.set_title(f"{nm}   r={r:.2f}, MAE={mae:.2f}", weight="bold")
        ax.set_xlabel("true"); ax.set_ylabel("recovered")
    plt.tight_layout(); plt.savefig(os.path.join(BASE, "validation_recovery_scatter.png"), dpi=150)
    plt.close()

    # ---- 2. Discrimination: loss-averse (lambda>=2.25) vs not ----
    yl = df["tl"].values; pl = oof["lambda"]
    thr = 2.25
    true_hi = yl >= thr
    acc = np.mean((pl >= thr) == true_hi)
    try:
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(true_hi, pl)
    except Exception:
        auc = float("nan")
    print(f"\n=== DISCRIMINATION (loss-averse lambda>=2.25) ===")
    print(f"  accuracy={acc:.3f}  AUC={auc:.3f}")

    # single-session absolute error percentiles (realistic: human plays once)
    print("\n=== SINGLE-SESSION ERROR (|recovered - true|) ===")
    for nm in ("alpha", "lambda", "gamma"):
        e = np.abs(oof[nm] - df[{"alpha":"ta","lambda":"tl","gamma":"tg"}[nm]].values)
        print(f"  {nm:6s}: median={np.median(e):.3f}  90th pct={np.percentile(e,90):.3f}")

    # ---- 3. Archetype recovery (held-out) ----
    if os.path.exists(ARCH_CSV):
        cal = C.train_from_csv(CALIB_CSV)     # trained on continuum only
        adf = pd.read_csv(ARCH_CSV)
        adf["v2l"] = pd.to_numeric(adf["v2l"], errors="coerce").fillna(adf["rl"])
        print(f"\n=== ARCHETYPE RECOVERY (held-out, {len(adf)} sessions) ===")
        rows = []
        for name in ARCHETYPES:
            sub = adf[adf["persona"] == name]
            if sub.empty:
                continue
            recs = [cal.calibrate({f: float(r[f]) for f in feats}) for _, r in sub.iterrows()]
            for p in ("alpha", "lambda", "gamma"):
                est = np.array([r[p] for r in recs])
                true = float(sub.iloc[0][{"alpha":"ta","lambda":"tl","gamma":"tg"}[p]])
                rows.append((name, p, true, est.mean(), est.std()))
            la = np.array([r["lambda"] for r in recs])
            tl = float(sub.iloc[0]["tl"])
            print(f"  {name:28s} true lambda={tl:.2f}  recovered={la.mean():.2f} +/- {la.std():.2f}")

        # bar chart: true vs recovered lambda per persona
        personas = list(ARCHETYPES.keys())
        tl = [ARCHETYPES[p][1] for p in personas]
        rec = [np.mean([r[3] for r in rows if r[0] == p and r[1] == "lambda"]) for p in personas]
        err = [np.mean([r[4] for r in rows if r[0] == p and r[1] == "lambda"]) for p in personas]
        x = np.arange(len(personas))
        plt.figure(figsize=(11, 5))
        plt.bar(x - 0.2, tl, 0.4, label="true lambda", color="#1A365D")
        plt.bar(x + 0.2, rec, 0.4, yerr=err, label="recovered lambda", color="#D4A73C", capsize=4)
        plt.xticks(x, personas, rotation=20, ha="right", fontsize=9)
        plt.ylabel("lambda (loss aversion)"); plt.legend(); plt.title("Archetype loss-aversion recovery", weight="bold")
        plt.tight_layout(); plt.savefig(os.path.join(BASE, "validation_archetypes.png"), dpi=150)
        plt.close()
        pd.DataFrame(rows, columns=["persona", "param", "true", "recovered_mean", "recovered_sd"]).to_csv(
            os.path.join(BASE, "validation_archetype_results.csv"), index=False)
    print("\nSaved: validation_recovery_scatter.png, validation_archetypes.png, validation_archetype_results.csv")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--archetypes":
        generate_archetypes(int(sys.argv[2]) if len(sys.argv) > 2 else 10,
                            seed=int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else:
        analyze()
