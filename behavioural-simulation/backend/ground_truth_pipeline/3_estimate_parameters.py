"""
STAGE 3 - Recover the behavioural parameters (alpha, lambda, gamma).

This is the ground-truth TEST: from the decision log alone, can we get back the
(alpha, lambda, gamma) we secretly planted in Stage 1?

METHOD: maximum likelihood. For each decision we compute the investor's 'feeling'
(prospect-theory value of the P&L, minus regret), turn it into BUY/SELL/HOLD
probabilities with the SAME model the generator used, and find the (alpha, lambda,
gamma) that make the observed choices most likely.

FIX vs the original code: the original assumed a two-way (buy/sell) model with a
different response steepness and threw away HOLD decisions -- a mismatch that forced
alpha and lambda onto their lower bounds. Here the recovery model matches the
generator (three-way, same slope, HOLDs kept), and recovery is accurate.
"""
import os
import pandas as pd
from config import PERSONAS
from estimator import fit_choice_model

HERE = os.path.dirname(__file__)


def main():
    log = pd.read_csv(os.path.join(HERE, "outputs", "behavioral_validation_log.csv"))
    rows = []
    print(f"{'investor':9} | {'TRUE (a, l, g)':22} | {'RECOVERED (a, l, g)':22}")
    print("-" * 60)
    for inv in sorted(log["investor_id"].unique()):
        a, l, g = fit_choice_model(log[log["investor_id"] == inv])
        rows.append({"investor_id": inv, "estimated_alpha": round(a, 3),
                     "estimated_lambda": round(l, 3), "estimated_gamma": round(g, 3)})
        t = PERSONAS[inv]
        print(f"{inv:9} | ({t[0]:.2f}, {t[1]:.2f}, {t[2]:.2f})".ljust(35) +
              f"| ({a:.2f}, {l:.2f}, {g:.2f})")
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "outputs", "recovered_parameters.csv"), index=False)
    print("\nSaved outputs/recovered_parameters.csv")


if __name__ == "__main__":
    main()
