"""
lambda_events -- matched-stakes event round for identifying loss aversion (lambda).

WHY THIS EXISTS
---------------
A parameter-recovery study showed that free-form allocation decisions cannot
identify lambda (loss aversion): rank correlation between true and recovered
lambda was only ~0.13, because the gain/loss magnitudes a player experiences
are endogenous, correlated with the regret signal, and the slider saturates.

A short round of MATCHED-STAKES events fixes this. Each event is a framed,
in-world 50/50 bet where the potential GAIN and LOSS magnitudes are known and
controlled. Because we set the stakes, the player's committed fraction directly
reveals the Cumulative-Prospect-Theory value of the bet, and lambda is read off
the gain/loss asymmetry.

Validated recovery (alpha fixed at 0.88, synthetic players, noisy commitments):

    events per player      lambda Pearson   lambda Spearman
    -----------------      --------------   ---------------
    12                     0.66             0.77
    20                     0.78             0.89
    20 (low noise)         0.83             0.95

This keeps the simulator feel (it reads as a market event, not a survey) while
giving clean identification -- comparable to how well gamma already recovers.

USAGE
-----
    events = make_events()                 # ordered list of (gain_pct, loss_pct)
    # ... present each to the player, collect committed fraction in [0, 1] ...
    records = [{"gain_pct": g, "loss_pct": l, "commit": c}, ...]
    result = fit_lambda_events(records)    # {"estimate": lambda, "confidence": {...}, ...}
"""
import numpy as np

ALPHA_FIXED = 0.88
MIN_RESPONSE_VAR = 0.06

# Matched & tilted stakes (gain%, loss%). A spread of symmetric, loss-tilted and
# gain-tilted bets is what makes the gain-slope and loss-slope separately
# estimable. Percentages are of the event stake, not the whole portfolio.
EVENT_GRID = [
    (3, 3), (5, 5), (8, 8), (10, 10), (6, 6), (4, 4),
    (3, 5), (5, 8), (4, 7), (6, 9), (5, 7), (4, 6),
    (5, 3), (8, 5), (7, 4), (9, 6), (7, 5), (6, 4),
    (8, 6), (6, 8),
]


def make_events(seed=42, n=20):
    """Return up to `n` (gain_pct, loss_pct) events in a shuffled but reproducible order."""
    rng = np.random.default_rng(seed)
    grid = list(EVENT_GRID[:n])
    rng.shuffle(grid)
    return grid


def event_cpt_value(gain_pct, loss_pct, lam, alpha=ALPHA_FIXED):
    """Per-unit CPT value of a 50/50 bet -- positive means attractive to accept."""
    return 0.5 * (gain_pct ** alpha) - 0.5 * lam * (loss_pct ** alpha)


def fit_lambda_events(records, alpha=ALPHA_FIXED):
    """
    Estimate lambda from matched-stakes events via a closed-form regression.

    Model: logit(commit) = tau*(0.5*G^a) - (tau*lam)*(0.5*L^a) + b0
           => OLS on [0.5*G^a, -0.5*L^a, 1];  lambda = coef_loss / coef_gain.

    records: iterable of dicts with keys gain_pct, loss_pct, commit (0..1).
    """
    G = np.array([r["gain_pct"] for r in records], dtype=float)
    L = np.array([r["loss_pct"] for r in records], dtype=float)
    c = np.clip(np.array([r["commit"] for r in records], dtype=float), 0.02, 0.98)
    y = np.log(c / (1 - c))

    fg = 0.5 * np.power(G, alpha)
    fl = 0.5 * np.power(L, alpha)
    X = np.column_stack([fg, -fl, np.ones_like(fg)])

    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(len(y) - 3, 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.abs(np.diag(np.linalg.pinv(X.T @ X))) * sigma2)
    r2 = 1.0 - float(resid @ resid) / (float(np.sum((y - y.mean()) ** 2)) + 1e-12)

    b_tau, b_taulam = beta[0], beta[1]        # tau, tau*lambda
    lam = b_taulam / b_tau if abs(b_tau) > 1e-6 else np.nan
    resp_var = float(np.var(y))

    if resp_var < MIN_RESPONSE_VAR:
        conf = {"level": "uninformative",
                "reason": f"player committed almost the same amount to every event (variance {resp_var:.3f})"}
    else:
        tstat = abs(b_tau) / se[0] if se[0] > 0 else 0.0
        conf = ({"level": "ok", "reason": f"clear response to stakes (t={tstat:.2f})"} if tstat >= 1.5
                else {"level": "weak", "reason": f"weak response to gain stakes (t={tstat:.2f})"})

    lam_val = float(np.clip(lam, 0.3, 8.0)) if np.isfinite(lam) else None
    return {"estimate": lam_val, "r2": float(r2), "n": len(y),
            "response_var": resp_var, "confidence": conf}


# --------------------------------------------------------------------------
# Self-contained recovery validation (run: python lambda_events.py)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    from scipy.stats import pearsonr, spearmanr

    def simulate_player(lam, tau, noise, grid, rng):
        recs = []
        for (G, L) in grid:
            val = event_cpt_value(G, L, lam)
            commit = 1.0 / (1.0 + np.exp(-(tau * val + rng.normal(0, noise))))
            recs.append({"gain_pct": G, "loss_pct": L, "commit": float(np.clip(commit, 0.02, 0.98))})
        return recs

    def run(n_events, noise, N=300, seed=1):
        rng = np.random.default_rng(seed)
        grid = EVENT_GRID[:n_events]
        t, e = [], []
        for _ in range(N):
            lam = rng.uniform(1.0, 4.5)
            tau = rng.uniform(0.3, 1.2)
            est = fit_lambda_events(simulate_player(lam, tau, noise, grid, rng))["estimate"]
            if est is not None:
                t.append(lam); e.append(est)
        t, e = np.array(t), np.array(e)
        print(f"  {n_events:>2} events, noise={noise}:  "
              f"Pearson={pearsonr(t, e)[0]:+.3f}  Spearman={spearmanr(t, e)[0]:+.3f}  "
              f"MAE={np.abs(e - t).mean():.3f}")

    print("Lambda recovery from matched-stakes events (alpha fixed at 0.88):")
    run(12, 0.25)
    run(20, 0.25)
    run(20, 0.15)
