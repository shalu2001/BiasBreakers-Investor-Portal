"""
gamma_drift_recovery_test.py

Question: does concentrating the regret checkpoints on LARGE-MOVE days
(stratified_checkpoints fix #1: fewer "calm" checkpoints, more rally/drop ones)
improve gamma recovery -- and does it push borderline players out of the
"uninformative" confidence flag?

Mechanism: gamma is the slope of allocation on the benchmark gap. Its estimate is
only as identifiable as the SPREAD of gaps the player is exposed to. Calm-heavy
checkpoints give near-zero gaps (little X-variance -> huge SE -> "uninformative").
Signal-heavy checkpoints give large, varied gaps (lots of X-variance -> tight
gamma). Here we hold the estimator fixed (production fit_regret) and vary only the
gap magnitude the player sees, across a mix of trading patterns (drift up/down,
noisy), and report:

    r        Pearson(recovered gamma, true gamma)
    MAE      mean |recovered - true|
    %uninf   share of players the confidence system flags 'uninformative'

Pure numpy, fast, deterministic.
"""
import os
import sys
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from estimation.estimator_v2 import fit_regret, WC_SCALE_DIV

STARTING_EQUITY = 1_000_000.0
WC_DIV = STARTING_EQUITY / WC_SCALE_DIV
N_SUBBLOCKS, N_PER_SUB = 3, 11
sig = lambda x: 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

# gap regime = what checkpoint selection exposes the player to
GAP_REGIMES = {
    "calm-heavy checkpoints (old)": 0.8,   # mostly near-flat days -> tiny gaps
    "balanced":                      1.6,
    "signal-heavy checkpoints (new)": 3.0,  # concentrated on large index moves
}

# a spread of trading patterns, pooled inside every gap regime
PATTERNS = [dict(drift=0.0, noise=0.14), dict(drift=0.10, noise=0.16),
            dict(drift=-0.10, noise=0.16), dict(drift=0.03, noise=0.26)]


def simulate_player(true, gap_sd, pat, rng):
    a, lam, g, k = true["alpha"], true["lambda"], true["gamma"], true["k"]
    rows = []
    for _ in range(N_SUBBLOCKS):
        rows.append((0.5, 0.0, 0.0))                      # scenario restart
        for t in range(1, N_PER_SUB):
            mg = rng.normal(0.0, gap_sd)                  # gap magnitude set by checkpoint selection
            wc = rng.normal(0.0, 2.0)
            v = wc ** a if wc >= 0 else -lam * (abs(wc) ** a)
            z = k * (v + g * mg) + pat["drift"] * t + rng.normal(0.0, pat["noise"])
            rows.append((float(np.clip(sig(z), 0.02, 0.98)), wc * WC_DIV, mg))
    df = pd.DataFrame(rows, columns=["target_pct", "wealth_change", "market_gap"])
    df["is_checkpoint_decision"] = True
    return df


def run(n_players=240, seed=11):
    print(f"Gamma recovery vs. checkpoint gap magnitude   (n={n_players} players / regime)\n")
    print(f"{'gap regime':<32}{'mean|gap|':>11}{'r':>8}{'MAE':>8}{'%uninf':>9}")
    print("-" * 68)
    for name, gap_sd in GAP_REGIMES.items():
        rng = np.random.default_rng(seed + int(gap_sd * 100))
        truth, rec, uninf, absgap = [], [], 0, []
        for i in range(n_players):
            true = dict(alpha=rng.uniform(0.75, 0.98), **{"lambda": rng.uniform(1.0, 3.5)},
                        gamma=rng.uniform(0.0, 4.5), k=rng.uniform(0.6, 1.0))
            pat = PATTERNS[i % len(PATTERNS)]
            df = simulate_player(true, gap_sd, pat, rng)
            out = fit_regret(df, STARTING_EQUITY)
            truth.append(true["gamma"]); rec.append(out["estimate"])
            uninf += (out["confidence"]["level"] == "uninformative")
            absgap.append(df["market_gap"].abs().mean())
        truth, rec = np.array(truth), np.array(rec)
        r = pearsonr(truth, rec)[0]; mae = np.mean(np.abs(truth - rec))
        print(f"{name:<32}{np.mean(absgap):>11.2f}{r:>8.3f}{mae:>8.3f}{100*uninf/n_players:>8.0f}%")
    print("-" * 68)
    print("Reading: as checkpoints move off 'calm' onto large-move days, the gap the")
    print("player sees widens, gamma recovery (r) rises, and far fewer players are")
    print("flagged 'uninformative'. Same estimator throughout -- only the gaps change.")


if __name__ == "__main__":
    run()
