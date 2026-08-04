"""
STAGE 5 - Evaluate the ground-truth recovery and produce figures.

Reports how well the recovered parameters match the planted truth, and saves:
  - recovery_comparison.png : true vs recovered for alpha, lambda, gamma
  - prospect_theory_curve.png : the fitted S-shaped value function
  - metrics printed to console (MAE and correlation per parameter)
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from config import PERSONAS, WC_SCALE

HERE = os.path.dirname(__file__)


def main():
    rec = pd.read_csv(os.path.join(HERE, "outputs", "recovered_parameters.csv")).set_index("investor_id")
    invs = list(PERSONAS.keys())
    true = {p: np.array([PERSONAS[i][j] for i in invs]) for j, p in enumerate(["alpha", "lambda", "gamma"])}
    est = {"alpha": rec["estimated_alpha"].reindex(invs).values,
           "lambda": rec["estimated_lambda"].reindex(invs).values,
           "gamma": rec["estimated_gamma"].reindex(invs).values}

    print("=== GROUND-TRUTH RECOVERY METRICS ===")
    for p in ["alpha", "lambda", "gamma"]:
        mae = np.mean(np.abs(est[p] - true[p]))
        r = pearsonr(true[p], est[p])[0]
        print(f"  {p:6}: MAE = {mae:.3f},  correlation(true, recovered) = {r:+.3f}")

    # --- recovery comparison bar charts ---
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
    x = np.arange(len(invs))
    for a, p in zip(ax, ["alpha", "lambda", "gamma"]):
        a.bar(x - 0.2, true[p], 0.4, label="true", color="#1A365D")
        a.bar(x + 0.2, est[p], 0.4, label="recovered", color="#D4A73C")
        a.set_xticks(x); a.set_xticklabels(invs, rotation=30, fontsize=8)
        a.set_title(p, weight="bold"); a.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "outputs", "recovery_comparison.png"), dpi=150)
    plt.close()

    # --- fitted prospect-theory value curve (using a recovered persona) ---
    inv = "INV_02"  # strongly loss-averse
    a, l = rec.loc[inv, "estimated_alpha"], rec.loc[inv, "estimated_lambda"]
    wc = np.linspace(-60000, 60000, 400)
    x = wc / WC_SCALE
    v = np.where(x >= 0, np.power(np.abs(x), a), -l * np.power(np.abs(x), a))
    plt.figure(figsize=(7, 5))
    plt.plot(wc / 1000, v, color="#E0605A", lw=2.3)
    plt.axhline(0, color="#888", lw=0.8); plt.axvline(0, color="#888", lw=0.8)
    plt.title(f"Recovered prospect-theory value curve ({inv}: α={a:.2f}, λ={l:.2f})", weight="bold")
    plt.xlabel("period P&L (Rs. thousands)"); plt.ylabel("value")
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "outputs", "prospect_theory_curve.png"), dpi=150)
    plt.close()
    print("\nSaved recovery_comparison.png and prospect_theory_curve.png")


if __name__ == "__main__":
    main()
