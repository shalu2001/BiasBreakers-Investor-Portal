"""
drift_validation.py -- proves the behavioural profile is DYNAMIC and trackable.

We simulate an investor whose TRUE loss aversion (lambda) and TRUE regret (gamma)
genuinely drift over time -- e.g. loss aversion spikes during a crash and relaxes
afterwards. We generate their ongoing decision stream, run the live dynamic
estimator over it, and check that the recovered lambda_t / gamma_t track the
moving true values.

  * gamma_t : tracked continuously from the passive decision window.
  * lambda_t: refreshed by periodic matched-stakes check-ins.

Run: python drift_validation.py  ->  drift_validation.png + metrics
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from estimation.dynamic_estimator import DynamicProfile
from estimation.lambda_events import EVENT_GRID, event_cpt_value

from paths import ROOT as BASE
SE = 1_000_000.0
sig = lambda x: 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def _market_stream():
    """A long stream of (stock_return, index_return) by concatenating the three
    scenarios and looping, so we have enough decisions for rolling windows."""
    sr, ir = [], []
    for name in ["2021_bull_run", "2022_crash", "2023_recovery"]:
        s = pd.read_csv(os.path.join(BASE, "scenario_build", f"{name}_stocks.csv"))
        i = pd.read_csv(os.path.join(BASE, "scenario_build", f"{name}_index.csv"))
        jkh = s[s["Ticker"] == "JKH"].sort_values("Date")
        sr.append(jkh["Close"].pct_change().dropna().values * 100)
        ir.append(i.sort_values("Date")["SP_SL20"].pct_change().dropna().values * 100)
    stock = np.concatenate(sr * 2)      # loop twice for length
    index = np.concatenate(ir * 2)
    n = min(len(stock), len(index))
    return stock[:n], index[:n]


def _true_schedules(n):
    """Ground-truth drifting parameters over the timeline."""
    t = np.linspace(0, 1, n)
    # lambda: 1.8 -> spikes to 3.6 mid-stream (a 'crash' fear) -> relaxes to 2.2
    lam = 1.8 + 1.8 * np.exp(-((t - 0.5) ** 2) / (2 * 0.09 ** 2)) + 0.4 * t
    # gamma: rises 0.5 -> 3.0 then eases to 1.2
    gam = 0.5 + 2.5 * np.clip(np.sin(np.pi * t), 0, None) * (t < 0.75) + 0.7 * (t >= 0.75)
    return lam, gam


def _checkin_records(true_lambda, rng, n_events=16):
    recs = []
    for (g, l) in EVENT_GRID[:n_events]:
        val = event_cpt_value(g, l, true_lambda)
        c = float(np.clip(sig(0.9 * val + rng.normal(0, 0.2)), 0.02, 0.98))
        recs.append({"gain_pct": g, "loss_pct": l, "commit": c})
    return recs


def main():
    rng = np.random.default_rng(0)
    stock, index = _market_stream()
    n = len(stock)
    lam_true, gam_true = _true_schedules(n)
    alpha_true, k = 0.85, 0.8

    # --- generate the investor's decision stream under drifting psychology ---
    rows = []
    prev_f = 0.5
    for t in range(n):
        wc = prev_f * SE * (stock[t] / 100.0)
        mg = index[t] - stock[t]
        wcs = wc / 5000.0
        v = wcs ** alpha_true if wcs >= 0 else -lam_true[t] * (abs(wcs) ** alpha_true)
        f = float(np.clip(sig(k * (v + gam_true[t] * mg) + rng.normal(0, 0.18)), 0.02, 0.98))
        rows.append({"target_pct": f, "wealth_change": wc, "market_gap": mg, "is_checkpoint_decision": True})
        prev_f = f
    decisions = pd.DataFrame(rows)

    # --- lambda check-ins every ~130 decisions (uses the true lambda at that time) ---
    checkin_idx = list(range(130, n, 130))
    checkins = {i: _checkin_records(lam_true[i], rng) for i in checkin_idx}

    # --- run the live dynamic estimator ---
    prof = DynamicProfile(window=45, prior={"alpha": 0.88, "lambda": lam_true[0], "gamma": 0.5})
    ts = prof.track(decisions, step=8, checkins=dict(checkins))

    # lambda check-in estimates (for plotting the discrete refreshes)
    from estimation.lambda_events import fit_lambda_events
    ci_t = checkin_idx
    ci_lam = [fit_lambda_events(checkins[i])["estimate"] for i in checkin_idx]

    # --- metrics ---
    from scipy.stats import pearsonr
    gam_true_at = np.interp(ts["t"], np.arange(n), gam_true)
    lam_true_at = np.array([lam_true[min(i, n - 1)] for i in ci_t])
    g_r = pearsonr(gam_true_at, ts["gamma"])[0]
    l_r = pearsonr(lam_true_at, ci_lam)[0]
    print("=== DRIFT TRACKING ===")
    print(f"  gamma (continuous):  tracking correlation r = {g_r:.3f}")
    print(f"  lambda (check-ins):  tracking correlation r = {l_r:.3f}  ({len(ci_t)} check-ins)")

    # --- plot ---
    fig, ax = plt.subplots(1, 2, figsize=(15, 5))
    ax[0].plot(np.arange(n), lam_true, color="#1A365D", lw=2.2, label="true λ (drifting)")
    ax[0].scatter(ci_t, ci_lam, color="#E0605A", s=70, zorder=5, label="λ from check-ins")
    ax[0].set_title(f"Loss aversion λ tracked over time\ncheck-in correlation r = {l_r:.2f}", weight="bold")
    ax[0].set_xlabel("decision # (time)"); ax[0].set_ylabel("λ"); ax[0].legend()
    ax[1].plot(gam_true, color="#1A365D", lw=2.2, label="true γ (drifting)")
    ax[1].plot(ts["t"], ts["gamma"], color="#D4A73C", lw=2, label="γ tracked (rolling window)")
    ax[1].set_title(f"Regret γ tracked over time\ncontinuous correlation r = {g_r:.2f}", weight="bold")
    ax[1].set_xlabel("decision # (time)"); ax[1].set_ylabel("γ"); ax[1].legend()
    plt.tight_layout()
    out = os.path.join(BASE, "drift_validation.png")
    plt.savefig(out, dpi=150); plt.close()
    print("saved", out)


if __name__ == "__main__":
    main()
