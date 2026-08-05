"""
STAGE 6 - Prove that DRIFTING psychology can be recovered over time.

Stages 1-5 assume each investor has ONE fixed personality. But a core claim of the
project is that behaviour changes over time -- which is why the utility must be
re-estimated dynamically rather than fixed. This stage proves that claim.

WHAT IT DOES: it creates one investor whose true loss aversion (lambda) is NOT
constant -- it spikes during the real 2022 market crash and relaxes afterwards
(a realistic "fear rises in a crash" story). The investor trades the real market
under this drifting lambda. We then recover lambda over time with a ROLLING WINDOW
-- re-running the same maximum-likelihood estimator (estimator.py) on each trailing
window of decisions -- and check that the recovered path follows the true path.

If it tracks, we have proven: psychology drifts AND we can follow the drift ->
which is exactly the justification for dynamic (re-estimated) utility.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

from market_data import load_market, build_lookup
from estimator import fit_choice_model
from config import SENT_SLOPE, HOLD_BASE, WC_SCALE

HERE = os.path.dirname(__file__)
SEED = 7
STARTING_CASH = 1_000_000.0
FEE = 0.01
BUY_FRACTION, SELL_FRACTION = 0.15, 0.25

# fixed traits
ALPHA_TRUE, GAMMA_TRUE = 0.85, 1.0
# lambda drifts: baseline 2.0, spikes to ~4.0 around the 2022 crash, relaxes to ~2.5
LAM_BASE, LAM_PEAK = 2.0, 4.0
PEAK_DATE = pd.Timestamp("2022-06-01")
PEAK_WIDTH_DAYS = 160

WINDOW = 300     # trailing decisions per estimate (~1 year)
STEP = 25        # slide every 25 days


def true_lambda(date):
    d = (pd.Timestamp(date) - PEAK_DATE).days
    bump = (LAM_PEAK - LAM_BASE) * np.exp(-(d ** 2) / (2 * PEAK_WIDTH_DAYS ** 2))
    tail = 0.5 * max(0.0, (pd.Timestamp(date) - PEAK_DATE).days) / 900.0  # slight post-crash elevation
    return LAM_BASE + bump + tail


def value_fn(x, alpha, lam):
    return abs(x) ** alpha if x >= 0 else -lam * (abs(x) ** alpha)


def generate_drifting_investor():
    rng = np.random.default_rng(SEED)
    lookup, tickers = build_lookup(load_market())
    days = sorted(lookup.keys())
    cash = STARTING_CASH
    holds = {t: 0 for t in tickers}
    prev_equity = STARTING_CASH
    rows = []
    for today in days:
        day = lookup[today]
        pmap, idx_ret = day["price_map"], day["index_return"]
        avail = list(pmap.keys())
        if not avail:
            continue
        lam_t = true_lambda(today)

        stock_val = sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
        equity = cash + stock_val
        wc = equity - prev_equity
        inv_ret = ((equity / prev_equity) - 1) * 100 if prev_equity > 0 else 0
        market_gap = idx_ret - inv_ret

        sentiment = value_fn(wc / WC_SCALE, ALPHA_TRUE, lam_t) - GAMMA_TRUE * market_gap
        w_buy = np.exp(np.clip(SENT_SLOPE * sentiment, -8, 8))
        w_sell = np.exp(np.clip(-SENT_SLOPE * sentiment, -8, 8))
        probs = np.array([w_buy, w_sell, HOLD_BASE]); probs /= probs.sum()
        action = rng.choice(["BUY", "SELL", "HOLD"], p=probs)

        if action == "BUY" and cash > 50_000:
            tk = avail[rng.integers(len(avail))]; price = pmap[tk]
            qty = int((cash * BUY_FRACTION) / price)
            if qty > 0:
                cash -= qty * price * (1 + FEE); holds[tk] += qty
            else:
                action = "HOLD"
        elif action == "SELL":
            owned = [t for t, q in holds.items() if q > 0]
            if owned:
                tk = owned[rng.integers(len(owned))]; price = pmap.get(tk, 0.0)
                qty = min(int(np.ceil(holds[tk] * SELL_FRACTION)), holds[tk])
                if qty > 0 and price > 0:
                    cash += qty * price * (1 - FEE); holds[tk] -= qty
                else:
                    action = "HOLD"
            else:
                action = "HOLD"

        post_equity = cash + sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
        rows.append({"date": pd.Timestamp(today), "action": action,
                     "wealth_change": wc, "market_gap": market_gap, "true_lambda": lam_t})
        prev_equity = post_equity
    return pd.DataFrame(rows)


def main():
    log = generate_drifting_investor()
    log.to_csv(os.path.join(HERE, "outputs", "drift_investor_log.csv"), index=False)

    # rolling-window recovery
    ts = []
    for end in range(WINDOW, len(log) + 1, STEP):
        win = log.iloc[end - WINDOW:end]
        a, lam_hat, g = fit_choice_model(win)
        ts.append({"date": win["date"].iloc[-1],
                   "true_lambda": win["true_lambda"].mean(),
                   "recovered_lambda": lam_hat})
    ts = pd.DataFrame(ts)
    r = pearsonr(ts["true_lambda"], ts["recovered_lambda"])[0]
    mae = np.mean(np.abs(ts["recovered_lambda"] - ts["true_lambda"]))
    print("=== DRIFT RECOVERY ===")
    print(f"  windows: {len(ts)}  |  tracking correlation r = {r:.3f}  |  MAE = {mae:.3f}")

    plt.figure(figsize=(11, 5.2))
    plt.plot(log["date"], log["true_lambda"], color="#1A365D", lw=2.4, label="true λ (drifts with the crash)")
    plt.plot(ts["date"], ts["recovered_lambda"], color="#D4A73C", lw=2, marker="o", ms=3,
             label="recovered λ (rolling window)")
    plt.axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31"), color="#E0605A", alpha=0.08)
    plt.text(pd.Timestamp("2022-06-15"), LAM_BASE - 0.15, "2022 crash", color="#E0605A", ha="center", fontsize=9)
    plt.title(f"Recovering a DRIFTING loss aversion over time   (r = {r:.2f})", weight="bold", fontsize=13)
    plt.xlabel("time"); plt.ylabel("λ (loss aversion)"); plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "outputs", "drift_recovery.png"), dpi=150)
    plt.close()
    ts.to_csv(os.path.join(HERE, "outputs", "drift_recovery_series.csv"), index=False)
    print("  saved outputs/drift_recovery.png")


if __name__ == "__main__":
    main()
