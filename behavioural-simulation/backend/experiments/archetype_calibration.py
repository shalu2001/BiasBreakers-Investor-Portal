"""
archetype_calibration.py -- measure the REAL distribution of recovered (lambda,
gamma) the game produces for a population of investors, so the dashboard's
archetype cut-offs can be set on that distribution instead of on the theoretical
[1,4.5] / [0,4.5] ranges (which the recovery compresses).

Each synthetic investor has known true (alpha, lambda, gamma) and plays the ACTUAL
MultiBlockSession + EventRound using the estimators' own generative models:
  * loss-aversion / regret free play:  logit(target) = k*(value(wc) + gamma*gap)
  * matched-stakes events:             commit = sigmoid(tau*CPT_value(G,L,lambda))
We then recover with the production finish (fit_full_profile + fit_profile_v2 +
calibration + event lambda) and log true vs recovered. Resumable: appends to
archetype_calibration.csv so it fits the shell time limit across a few calls.
"""
import os, sys, csv, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
from game.multi_block_session import MultiBlockSession
from game.event_round import EventRound
from estimation.final_estimator import fit_full_profile
from estimation.estimator_v2 import fit_profile_v2
from estimation.lambda_events import event_cpt_value
from estimation.calibration import load_default_calibrator, features_from_fits

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archetype_calibration.csv")
N_TARGET = 75
WC_DIV = 5000.0
CAL = load_default_calibrator()
sig = lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


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


def make_player(i):
    rng = np.random.default_rng(7000 + i)
    return dict(i=i, alpha=rng.uniform(0.70, 0.98), lam=rng.uniform(1.2, 4.0),
                gamma=rng.uniform(0.0, 3.5), tau=rng.uniform(0.4, 1.0),
                k=rng.uniform(0.6, 1.0), noise=rng.uniform(0.10, 0.20), seed=7000 + i)


def play_and_recover(p):
    rng = np.random.default_rng(p["seed"])
    a, lam, g, k, noise = p["alpha"], p["lam"], p["gamma"], p["k"], p["noise"]
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
    er = EventRound(n_events=16, seed=p["seed"])
    while not er.is_complete():
        ev = er.current(); G, L = ev["gain_pct"], ev["loss_pct"]
        commit = sig(p["tau"] * event_cpt_value(G, L, lam, a) + rng.normal(0, 0.18))
        er.commit(float(np.clip(commit, 0.02, 0.98)))
    l1, l2 = s.get_block_logs()
    fit = fit_full_profile(l1, l2, starting_equity=s.starting_cash)
    v2 = fit_profile_v2(l1, l2, starting_equity=s.starting_cash)
    cal = CAL.calibrate(features_from_fits(fit["raw"], v2))
    lam_hat, gamma_hat, alpha_hat = cal["lambda"], cal["gamma"], cal["alpha"]
    gconf = v2["confidence"]["gamma"]["level"]
    el = er.estimate_lambda(); lconf = "n/a"
    if el and el.get("estimate") is not None:
        lconf = el["confidence"]["level"]
        if lconf != "uninformative":
            lam_hat = float(el["estimate"])
    return dict(alpha_hat=alpha_hat, lam_hat=lam_hat, gamma_hat=gamma_hat,
                gconf=gconf, lconf=lconf)


def done_ids():
    if not os.path.exists(CSV):
        return set()
    return set(int(r["i"]) for r in csv.DictReader(open(CSV)))


def main(budget_s=38):
    done = done_ids()
    new = os.path.exists(CSV)
    fh = open(CSV, "a", newline="")
    cols = ["i", "alpha", "lam", "gamma", "tau", "k", "noise",
            "alpha_hat", "lam_hat", "gamma_hat", "gconf", "lconf"]
    w = csv.DictWriter(fh, fieldnames=cols)
    if not new:
        w.writeheader()
    t0 = time.time(); n = 0
    for i in range(N_TARGET):
        if i in done:
            continue
        if time.time() - t0 > budget_s:
            break
        p = make_player(i)
        r = play_and_recover(p)
        row = {c: p.get(c) for c in ["i", "alpha", "lam", "gamma", "tau", "k", "noise"]}
        row.update(r); w.writerow(row); fh.flush(); n += 1
    fh.close()
    total = len(done_ids())
    print(f"processed {n} this call; total in CSV = {total}/{N_TARGET}")


if __name__ == "__main__":
    main()
