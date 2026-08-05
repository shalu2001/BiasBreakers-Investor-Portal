"""
gamma_checkpoint_ab.py -- REAL game-engine A/B for checkpoint fix #1.

Same synthetic players (known gamma) play the actual MultiBlockSession twice:
  OLD selection : uniform n_per_bin across all 5 bins (incl. 'calm')
  NEW selection : fewer 'calm', more large-move checkpoints (the fix)
We recover gamma with the production estimator and compare Pearson r, MAE and the
share flagged 'uninformative'. Uses the real scenario data, so gap units are real.
"""
import os, sys, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game.multi_block_session import MultiBlockSession
from estimation.estimator_v2 import fit_regret
import game.allocation_checkpoint_session as allocation_checkpoint_session
from scipy.stats import pearsonr

sig = lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))
BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenario_build")


def load():
    d = {}
    for s in ["2021_bull_run", "2022_crash", "2023_recovery"]:
        d[s] = (pd.read_csv(f"{BASE}/{s}_stocks.csv", parse_dates=["Date"]),
                pd.read_csv(f"{BASE}/{s}_index.csv", parse_dates=["Date"]))
    return d


def old_select(index_df, n_per_bin=3, seed=42):
    """Pre-fix selection: uniform count per bin, including the low-signal 'calm' bin."""
    df = index_df.copy().sort_values("Date").reset_index(drop=True)
    df["index_return_pct"] = df["SP_SL20"].pct_change() * 100
    df = df.dropna(subset=["index_return_pct"])
    bins = [-np.inf, -3.0, -0.5, 0.5, 3.0, np.inf]
    labels = ["severe_drop", "moderate_drop", "calm", "moderate_rally", "severe_rally"]
    df["bin"] = pd.cut(df["index_return_pct"], bins=bins, labels=labels)
    rng = np.random.default_rng(seed); dates = []
    for label in labels:
        b = df[df["bin"] == label]; n = min(n_per_bin, len(b))
        if n > 0:
            dates.extend(rng.choice(b["Date"].values, size=n, replace=False))
    return sorted(dates), {}


def play(a, l, g, k, noise, data, rng):
    s = MultiBlockSession(data, 1_000_000, n_per_bin=2); rows = []
    while True:
        st = s.current_session
        wc = (st.total_equity() - st._prev_day_equity) / 5000.0
        v = wc ** a if wc >= 0 else -l * (abs(wc) ** a)
        tk = s.get_tradable_ticker(); regret = tk is not None
        gap = st.market_gap() if regret else 0.0
        tgt = float(np.clip(sig(k * (v + g * gap) + rng.normal(0, noise)), 0.02, 0.98))
        s.set_allocation(tk or "JKH", tgt)
        if regret:
            rows.append((wc * 5000.0, gap, tgt))
        if s.advance()["status"] == "all_blocks_complete":
            break
    df = pd.DataFrame(rows, columns=["wealth_change", "market_gap", "target_pct"])
    df["is_checkpoint_decision"] = True
    return df


def run_condition(label, selector, players, data):
    allocation_checkpoint_session.select_stratified_checkpoints = selector
    truth, rec, uninf, absgap = [], [], 0, []
    for p in players:
        rng = np.random.default_rng(p["seed"])
        df = play(p["alpha"], p["lambda"], p["gamma"], p["k"], p["noise"], data, rng)
        out = fit_regret(df, 1_000_000.0)
        truth.append(p["gamma"]); rec.append(out["estimate"])
        uninf += (out["confidence"]["level"] == "uninformative")
        absgap.append(df["market_gap"].abs().mean())
    truth, rec = np.array(truth), np.array(rec)
    r = pearsonr(truth, rec)[0]; mae = float(np.mean(np.abs(truth - rec)))
    print(f"{label:<22}{np.mean(absgap):>10.2f}{r:>9.3f}{mae:>8.3f}{100*uninf/len(players):>9.0f}%")


def main(n=18, seed=7):
    data = load()
    rng = np.random.default_rng(seed)
    players = [dict(seed=seed * 1000 + i, alpha=rng.uniform(0.78, 0.96),
                    **{"lambda": rng.uniform(1.0, 3.0)}, gamma=rng.uniform(0.0, 4.5),
                    k=rng.uniform(0.6, 1.0), noise=rng.uniform(0.12, 0.20)) for i in range(n)]
    print(f"REAL-engine gamma recovery, OLD vs NEW checkpoints  (n={n})\n")
    print(f"{'condition':<22}{'mean|gap|':>10}{'r':>9}{'MAE':>8}{'%uninf':>10}")
    print("-" * 59)
    new_sel = allocation_checkpoint_session.select_stratified_checkpoints  # current (fixed) version
    t0 = time.time()
    run_condition("OLD (calm-heavy)", old_select, players, data)
    run_condition("NEW (signal-heavy)", new_sel, players, data)
    print("-" * 59)
    print(f"elapsed {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
