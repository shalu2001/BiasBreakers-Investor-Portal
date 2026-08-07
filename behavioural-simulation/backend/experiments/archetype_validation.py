"""
archetype_validation.py

Validates the dashboard's archetype logic end-to-end, on a FRESH synthetic
sample (different seeds from the calibration that set the thresholds), so the
numbers are out-of-sample rather than circular.

Logic under test (see src/session/profileToPersona.ts):
    risk band  <- loss aversion (lambda):  Bold  / Balanced / Cautious
    market style <- regret / FOMO (gamma):  Strategist / Realist / Momentum
    thresholds = p33 / p67 of the RECOVERED distribution
        lambda: 2.00 / 2.53      gamma: 1.62 / 3.01

We generate players with known (alpha, lambda, gamma), play them through the
REAL MultiBlockSession + EventRound, recover via the production pipeline, and
report:
    1. recovery quality       Pearson r + MAE, lambda & gamma
    2. threshold sanity        do p33/p67 split the recovered sample into thirds?
    3. construct validity      mean TRUE param per recovered band (must be monotone)
                               + tercile-agreement accuracy vs chance (33%)
    4. axis independence       corr(recovered lambda, recovered gamma) ~ 0
    5. coverage                all 9 archetypes populated under uniform truth
"""
import os
import sys
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from game.event_round import EventRound
from estimation.final_estimator import fit_full_profile
from estimation.estimator_v2 import fit_profile_v2
from estimation.calibration import load_default_calibrator, features_from_fits
from estimation.lambda_events import event_cpt_value

WC_DIV = 5000.0
CAL = load_default_calibrator()
sig = lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

# thresholds exactly as the app uses them (percentile anchors -> terciles)
LAM_P33, LAM_P67 = 2.00, 2.53
GAM_P33, GAM_P67 = 1.62, 3.01


def load_scenarios():
    d = {}
    for n in ["2021_bull_run", "2022_crash", "2023_recovery"]:
        b = os.path.join(paths.SCENARIO_BUILD, n)
        d[n] = (pd.read_csv(f"{b}_stocks.csv", parse_dates=["Date"]),
                pd.read_csv(f"{b}_index.csv", parse_dates=["Date"]))
    return d
DATA = load_scenarios()


def gap_now(cs):
    try:
        return float(cs.get_index_return()) - float(cs.held_stock_return())
    except Exception:
        return 0.0


def value(wc, a, lam):
    x = wc / WC_DIV
    return x ** a if x >= 0 else -lam * (abs(x) ** a)


def play_and_recover(a, lam, g, tau, k, noise, seed):
    rng = np.random.default_rng(seed)
    s = MultiBlockSession(DATA, 1_000_000, n_per_bin=2)
    last = 1_000_000.0
    while True:
        cs = s.current_session; E = cs.total_equity(); wc = E - last
        v = value(wc, a, lam)
        if s.block == "loss_aversion":
            tgt = sig(k * v + rng.normal(0, noise)); tk = sorted(s.get_market_state().keys())[0]
        else:
            tgt = sig(k * (v + g * gap_now(cs)) + rng.normal(0, noise)); tk = "DIAL"
        s.set_allocation(tk, float(np.clip(tgt, 0.02, 0.98))); last = E
        st = s.advance()["status"]
        if st == "all_blocks_complete":
            break
        if st in ("new_scenario_started", "new_block_started"):
            last = s.current_session.total_equity()
    er = EventRound(n_events=16, seed=seed)
    while not er.is_complete():
        ev = er.current()
        commit = sig(tau * event_cpt_value(ev["gain_pct"], ev["loss_pct"], lam, a) + rng.normal(0, 0.18))
        er.commit(float(np.clip(commit, 0.02, 0.98)))
    l1, l2 = s.get_block_logs()
    fit = fit_full_profile(l1, l2, starting_equity=s.starting_cash)
    v2 = fit_profile_v2(l1, l2, starting_equity=s.starting_cash)
    cal = CAL.calibrate(features_from_fits(fit["raw"], v2))
    lam_hat, gam_hat = cal["lambda"], cal["gamma"]
    el = er.estimate_lambda()
    if el and el.get("estimate") is not None and el["confidence"]["level"] != "uninformative":
        lam_hat = float(el["estimate"])
    return lam_hat, gam_hat


def band(v, p33, p67):
    return 0 if v < p33 else 1 if v < p67 else 2   # 0 low, 1 mid, 2 high


def tercile_rank(x):
    """rank-based tercile label per player (robust to scale)."""
    order = np.argsort(np.argsort(x))
    n = len(x)
    return np.where(order < n / 3, 0, np.where(order < 2 * n / 3, 1, 2))


def run(n=120, base_seed=90000):
    print(f"Archetype validation  (n={n} out-of-sample synthetic investors)\n")
    rows = []
    for i in range(n):
        rng = np.random.default_rng(base_seed + i)
        a = rng.uniform(0.72, 0.96)
        lam = rng.uniform(1.1, 4.2)      # spans all three risk bands
        g = rng.uniform(0.0, 4.0)        # spans all three style bands
        tau = rng.uniform(0.4, 1.0); k = rng.uniform(0.6, 1.0); noise = rng.uniform(0.10, 0.20)
        lam_hat, gam_hat = play_and_recover(a, lam, g, tau, k, noise, base_seed + i)
        rows.append((lam, g, lam_hat, gam_hat))
    df = pd.DataFrame(rows, columns=["lam", "gam", "lam_hat", "gam_hat"])

    # 1. recovery quality
    rl = pearsonr(df.lam, df.lam_hat)[0]; rg = pearsonr(df.gam, df.gam_hat)[0]
    print("1. RECOVERY QUALITY")
    print(f"   lambda : r={rl:.3f}   MAE={np.mean(np.abs(df.lam-df.lam_hat)):.3f}")
    print(f"   gamma  : r={rg:.3f}   MAE={np.mean(np.abs(df.gam-df.gam_hat)):.3f}\n")

    # 2. threshold sanity: do the app thresholds cut the recovered sample ~1/3 each?
    rb = df.lam_hat.apply(lambda v: band(v, LAM_P33, LAM_P67))
    sb = df.gam_hat.apply(lambda v: band(v, GAM_P33, GAM_P67))
    print("2. THRESHOLD SPLIT (share of recovered sample per band; ideal 33/33/33)")
    print(f"   risk  (lambda @ {LAM_P33}/{LAM_P67}): "
          f"Bold {100*(rb==0).mean():.0f}%  Balanced {100*(rb==1).mean():.0f}%  Cautious {100*(rb==2).mean():.0f}%")
    print(f"   style (gamma  @ {GAM_P33}/{GAM_P67}): "
          f"Strat {100*(sb==0).mean():.0f}%  Realist {100*(sb==1).mean():.0f}%  Momentum {100*(sb==2).mean():.0f}%\n")

    # 3. construct validity: TRUE param must rise monotonically across recovered band
    print("3. CONSTRUCT VALIDITY (mean TRUE param within each recovered band; must be monotone)")
    print("   risk band :", {["Bold","Balanced","Cautious"][b]: round(df.lam[rb==b].mean(),2) for b in [0,1,2] if (rb==b).any()})
    print("   style band:", {["Strat","Realist","Momentum"][b]: round(df.gam[sb==b].mean(),2) for b in [0,1,2] if (sb==b).any()})
    # tercile agreement vs chance (rank-based, scale-free)
    true_r, rec_r = tercile_rank(df.lam.values), tercile_rank(df.lam_hat.values)
    true_s, rec_s = tercile_rank(df.gam.values), tercile_rank(df.gam_hat.values)
    print(f"   tercile agreement  risk={100*(true_r==rec_r).mean():.0f}%   "
          f"style={100*(true_s==rec_s).mean():.0f}%   (chance = 33%)\n")

    # 4. axis independence
    print("4. AXIS INDEPENDENCE (the two axes should be ~uncorrelated)")
    print(f"   corr(true lambda, true gamma)      = {pearsonr(df.lam, df.gam)[0]:+.3f}")
    print(f"   corr(recovered lambda, rec. gamma) = {pearsonr(df.lam_hat, df.gam_hat)[0]:+.3f}\n")

    # 5. coverage: all 9 archetypes populated
    RN = ["Bold","Balanced","Cautious"]; SN = ["Strategist","Realist","Momentum"]
    print("5. COVERAGE (recovered archetype counts across the 3x3 grid)")
    grid = pd.crosstab(rb.map(dict(enumerate(RN))), sb.map(dict(enumerate(SN))))
    grid = grid.reindex(index=RN, columns=SN, fill_value=0)
    print(grid.to_string())
    filled = int((grid.values > 0).sum())
    print(f"\n   {filled}/9 archetypes populated under uniform ground truth.")


if __name__ == "__main__":
    run()
