"""
regret_personas_demo.py -- named regret investors play the REAL game engine.

Each persona has a KNOWN gamma and a distinct trading pattern (how strongly and
how cleanly they react to the S&P SL20 benchmark gap). They play the actual
MultiBlockSession; we then recover gamma with the production estimator and show
true vs. recovered plus the confidence flag. Averaged over a few seeds for
stability. Demonstrates that the instrument reads regret well when it is present
and correctly abstains when it isn't.
"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from multi_block_session import MultiBlockSession
from estimator_v2 import fit_regret

sig = lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))
BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenario_build")

# name -> (gamma, k=responsiveness, noise, blurb)
PERSONAS = {
    "The Chaser (strong FOMO)":     (4.0, 0.90, 0.14, "piles in whenever the market runs ahead"),
    "Momentum Rider":               (2.2, 0.85, 0.15, "leans into a rising benchmark, with restraint"),
    "Balanced":                     (1.2, 0.80, 0.16, "mild pull toward what he's missing"),
    "Disciplined (ignores market)": (0.3, 0.80, 0.15, "sticks to plan regardless of the gap"),
    "Noisy Trader":                 (2.5, 0.80, 0.34, "reacts to FOMO but erratically"),
    "Barely Plays (low signal)":    (2.0, 0.07, 0.05, "hardly moves the slider at all"),
}
SEEDS = [1, 2, 3]


def load():
    d = {}
    for s in ["2021_bull_run", "2022_crash", "2023_recovery"]:
        d[s] = (pd.read_csv(f"{BASE}/{s}_stocks.csv", parse_dates=["Date"]),
                pd.read_csv(f"{BASE}/{s}_index.csv", parse_dates=["Date"]))
    return d


def play(gamma, k, noise, data, rng, alpha=0.88, lam=2.0):
    s = MultiBlockSession(data, 1_000_000, n_per_bin=2); rows = []
    while True:
        st = s.current_session
        wc = (st.total_equity() - st._prev_day_equity) / 5000.0
        v = wc ** alpha if wc >= 0 else -lam * (abs(wc) ** alpha)
        tk = s.get_tradable_ticker(); regret = tk is not None
        gap = st.market_gap() if regret else 0.0
        tgt = float(np.clip(sig(k * (v + gamma * gap) + rng.normal(0, noise)), 0.02, 0.98))
        s.set_allocation(tk or "JKH", tgt)
        if regret:
            rows.append((wc * 5000.0, gap, tgt))
        if s.advance()["status"] == "all_blocks_complete":
            break
    df = pd.DataFrame(rows, columns=["wealth_change", "market_gap", "target_pct"])
    df["is_checkpoint_decision"] = True
    return df


def main():
    data = load()
    print("Regret personas on the real engine  (gamma averaged over 3 seeds)\n")
    print(f"{'persona':<30}{'true g':>8}{'recovered':>11}{'confidence':>14}")
    print("-" * 63)
    for name, (g, k, noise, _) in PERSONAS.items():
        recs, confs = [], []
        for sd in SEEDS:
            df = play(g, k, noise, data, np.random.default_rng(sd * 97 + len(name)))
            out = fit_regret(df, 1_000_000.0)
            recs.append(out["estimate"]); confs.append(out["confidence"]["level"])
        rec = np.mean(recs)
        conf = max(set(confs), key=confs.count)   # most common level across seeds
        print(f"{name:<30}{g:>8.1f}{rec:>11.2f}{conf:>14}")
    print("-" * 63)
    print("Read: responsive personas recover close to their true gamma and grade 'ok'.")
    print("The disciplined (near-zero gamma) player is graded 'weak' -- a flat response")
    print("is genuinely hard to pin. A barely-moving player's magnitude gets compressed")
    print("toward the middle, which is exactly why the confidence flag rides alongside.")


if __name__ == "__main__":
    main()
