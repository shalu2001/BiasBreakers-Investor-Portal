"""
Continuum full-game recovery -- the "strong table" for the dissertation.

Draws N synthetic investors with RANDOM (alpha, lambda, gamma) spread across the
literature ranges, has each play the full onboarding game (Fund A -> Fund B -> the
matched-stakes event round) through the REAL engine, then recovers them exactly the
way app.py finish() does: calibration for alpha/gamma, matched-stakes for lambda.

Unlike game_recovery.py (5 fixed personas), this spreads true values across the whole
range, so Pearson r is meaningful. Install scikit-learn first so the calibrator uses
gradient boosting (stronger than the NumPy KNN fallback):

    pip install scikit-learn scipy

Run (from the Backend folder):

    python experiments/game_recovery_continuum.py 60

The number is how many players to simulate (60-150 is a good table; more = slower but
tighter). Prints a Pearson/MAE table and writes experiments/continuum_results.csv.
"""
import os, sys, csv, numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from multi_block_session import MultiBlockSession
from final_estimator import fit_full_profile
from estimator_v2 import fit_profile_v2
from calibration import load_default_calibrator, features_from_fits
from lambda_events import make_events, event_cpt_value, fit_lambda_events

WC = 5000.0
sig = lambda x: 1 / (1 + np.exp(-np.clip(x, -30, 30)))
CAL = load_default_calibrator()

# literature ranges (Tversky & Kahneman 1992; gamma is this framework's regret term)
ALPHA_RANGE = (0.55, 1.00)
LAMBDA_RANGE = (1.00, 4.50)
GAMMA_RANGE = (0.00, 4.50)


def _scenarios():
    d = {}
    for s in ["2021_bull_run", "2022_crash", "2023_recovery"]:
        b = os.path.join(BACKEND, "scenario_build", s)
        d[s] = (pd.read_csv(f"{b}_stocks.csv", parse_dates=["Date"]),
                pd.read_csv(f"{b}_index.csv", parse_dates=["Date"]))
    return d


def _play_blocks(a, l, g, k, noise, data, rng):
    s = MultiBlockSession(data, 1_000_000, n_per_bin=3)
    while True:
        st = s.current_session
        wc = (st.total_equity() - st._prev_day_equity) / WC
        v = wc ** a if wc >= 0 else -l * (abs(wc) ** a)
        mg = st.market_gap()
        tgt = float(np.clip(sig(k * (v + g * mg) + rng.normal(0, noise)), 0.02, 0.98))
        s.set_allocation(s.get_tradable_ticker() or "JKH", tgt)
        if s.advance()["status"] == "all_blocks_complete":
            break
    return s.get_block_logs()


def _play_events(lam, alpha, tau, noise, seed, rng):
    recs = []
    for (G, L) in make_events(seed=seed, n=16):
        val = event_cpt_value(G, L, lam, alpha)
        commit = float(np.clip(sig(tau * val + rng.normal(0, noise)), 0.02, 0.98))
        recs.append({"gain_pct": G, "loss_pct": L, "commit": commit})
    return recs


def _recover(l1, l2, ev):
    fit = fit_full_profile(l1, l2, starting_equity=1_000_000)
    v2 = fit_profile_v2(l1, l2, starting_equity=1_000_000)
    if CAL is not None:
        cal = CAL.calibrate(features_from_fits(fit["raw"], v2))
        prof = {"alpha": cal["alpha"], "lambda": cal["lambda"], "gamma": cal["gamma"]}
    else:
        prof = {"alpha": v2["alpha"],
                "lambda": v2["lambda"] if v2["lambda"] is not None else 2.25,
                "gamma": v2["gamma"]}
    el = fit_lambda_events(ev)
    if el and el.get("estimate") is not None and el["confidence"]["level"] != "uninformative":
        prof["lambda"] = float(el["estimate"])
    return prof


def _pear(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 and x.std() > 0 and y.std() > 0 else float("nan")


def main(N=60, seed=11):
    data = _scenarios()
    rng = np.random.default_rng(seed)
    rows = []
    print(f"Simulating {N} players through the full game "
          f"(calibrator backend: {'gradient_boosting' if CAL and CAL._backend=='gradient_boosting' else 'knn / none'})...")
    for i in range(N):
        a = rng.uniform(*ALPHA_RANGE); l = rng.uniform(*LAMBDA_RANGE); g = rng.uniform(*GAMMA_RANGE)
        k = rng.uniform(0.6, 1.0); noise = rng.uniform(0.12, 0.22); tau = rng.uniform(0.5, 1.1)
        prng = np.random.default_rng(5000 + i)
        l1, l2 = _play_blocks(a, l, g, k, noise, data, prng)
        ev = _play_events(l, a, tau, 0.22, 1000 + i, prng)
        p = _recover(l1, l2, ev)
        rows.append((a, l, g, p["alpha"], p["lambda"], p["gamma"]))
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{N} done")

    arr = np.array(rows)
    out = os.path.join(HERE, "continuum_results.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["true_alpha", "true_lambda", "true_gamma", "rec_alpha", "rec_lambda", "rec_gamma"])
        for r in rows:
            w.writerow([round(x, 4) for x in r])

    print("\n" + "=" * 58)
    print(f"CONTINUUM FULL-GAME RECOVERY  —  N = {N}")
    print("=" * 58)
    print(f"{'param':7} | {'Pearson r':>9} | {'MAE':>7}")
    for j, nm in [(0, "alpha"), (1, "lambda"), (2, "gamma")]:
        t, rec = arr[:, j], arr[:, j + 3]
        print(f"{nm:7} | {_pear(t, rec):9.3f} | {np.mean(np.abs(t - rec)):7.3f}")
    print("=" * 58)
    print("wrote", out)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    main(n)
