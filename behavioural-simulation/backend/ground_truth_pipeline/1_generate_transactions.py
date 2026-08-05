"""
STAGE 1 - Generate synthetic investors and their transaction ledger.

WHY: real retail trade records are confidential/unavailable, so we manufacture
investors whose psychology (alpha, lambda, gamma) we SET ourselves. That gives us
a known answer key to test parameter recovery against later.

WHAT IT DOES: five personas trade the real S&P SL20 stocks day by day. Each day,
each persona 'feels' their gain/loss through a Cumulative Prospect Theory value
function (loss aversion lambda, curvature alpha) minus a regret term for lagging
the market (gamma). That feeling is turned into BUY / SELL / HOLD probabilities and
one action is taken. Output: a realistic transaction ledger + daily portfolio
snapshots, saved to outputs/.

NOTE: seeded for reproducibility. The response 'gentleness' (SENT_SLOPE) and the
hold-baseline (HOLD_BASE) are fixed constants of the generator; the recovery stage
must use the SAME values (that consistency is what the original code got wrong).
"""
import os
import numpy as np
import pandas as pd
from market_data import load_market, build_lookup

SEED = 42
START, END = "2020-01-01", "2026-04-30"
STARTING_CASH = 1_000_000.0
FEE = 0.01                 # 1% broker fee
BUY_FRACTION = 0.15        # spend 15% of cash on a buy
SELL_FRACTION = 0.25       # sell 25% of a holding
SENT_SLOPE = 0.4           # how sharply feeling turns into action (generator constant)
HOLD_BASE = 0.85           # baseline tendency to hold (patience)
WC_SCALE = 10_000.0        # wealth_change is scaled by this inside the value function

# The five ground-truth personas: (alpha, lambda, gamma)
PERSONAS = {
    "INV_01": (0.88, 2.25, 0.5),   # canonical prospect-theory investor
    "INV_02": (0.70, 4.50, 0.1),   # strongly loss-averse
    "INV_03": (0.92, 1.25, 4.5),   # loss-tolerant but strong FOMO
    "INV_04": (0.98, 1.05, 0.0),   # almost rational, no regret
    "INV_05": (0.75, 2.75, 0.8),   # moderate everything
}

HERE = os.path.dirname(__file__)
XLSX = os.path.join(HERE, "data", "S&P SL20.xlsx")


def value_function(scaled_wc, alpha, lam):
    """Prospect-theory value: concave gains, steeper convex losses (x lambda)."""
    if scaled_wc >= 0:
        return abs(scaled_wc) ** alpha
    return -lam * (abs(scaled_wc) ** alpha)


def simulate():
    rng = np.random.default_rng(SEED)
    market = load_market()
    lookup, tickers = build_lookup(market)
    days = sorted(lookup.keys())

    ledger, snapshots = [], []
    tx = 100001
    for inv, (alpha, lam, gamma) in PERSONAS.items():
        cash = STARTING_CASH
        holds = {t: 0 for t in tickers}
        prev_equity = STARTING_CASH
        for today in days:
            day = lookup[today]
            pmap = day["price_map"]
            idx_ret = day["index_return"]
            avail = list(pmap.keys())
            if not avail:
                continue

            stock_val = sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
            equity = cash + stock_val
            wc = equity - prev_equity
            inv_ret = ((equity / prev_equity) - 1) * 100 if prev_equity > 0 else 0
            market_gap = idx_ret - inv_ret

            # --- the persona 'feels' the period, then chooses ---
            sentiment = value_function(wc / WC_SCALE, alpha, lam) - gamma * market_gap
            w_buy = np.exp(np.clip(SENT_SLOPE * sentiment, -8, 8))
            w_sell = np.exp(np.clip(-SENT_SLOPE * sentiment, -8, 8))
            probs = np.array([w_buy, w_sell, HOLD_BASE])
            probs /= probs.sum()
            action = rng.choice(["BUY", "SELL", "HOLD"], p=probs)

            ticker, price, qty = "NONE", 0.0, 0
            if action == "BUY" and cash > 50_000:
                ticker = avail[rng.integers(len(avail))]
                price = pmap[ticker]
                qty = int((cash * BUY_FRACTION) / price)
                if qty > 0:
                    cash -= qty * price * (1 + FEE)
                    holds[ticker] += qty
                else:
                    action = "HOLD"
            elif action == "SELL":
                owned = [t for t, q in holds.items() if q > 0]
                if owned:
                    ticker = owned[rng.integers(len(owned))]
                    price = pmap.get(ticker, 0.0)
                    qty = int(np.ceil(holds[ticker] * SELL_FRACTION))
                    qty = min(qty, holds[ticker])
                    if qty > 0 and price > 0:
                        cash += qty * price * (1 - FEE)
                        holds[ticker] -= qty
                    else:
                        action = "HOLD"
                else:
                    action = "HOLD"

            if action in ("BUY", "SELL") and qty > 0:
                ledger.append({"Transaction_ID": f"TX_{tx}", "Investor_ID": inv,
                               "Date": today, "Action": action, "Ticker": ticker,
                               "Execution_Price": round(float(price), 2),
                               "Executed_Quantity": int(qty), "Cash_Balance_Post": round(cash, 2)})
                tx += 1

            stock_val = sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
            equity = cash + stock_val
            snap = {"Date": today, "Investor_ID": inv, "Cash_Balance": round(cash, 2),
                    "Stock_Value": round(stock_val, 2), "Total_Equity": round(equity, 2)}
            for t in tickers:
                snap[f"Qty_{t}"] = holds[t]
            snapshots.append(snap)
            prev_equity = equity

    out = os.path.join(HERE, "outputs")
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(ledger).to_csv(os.path.join(out, "transaction_ledger.csv"), index=False)
    pd.DataFrame(snapshots).to_csv(os.path.join(out, "portfolio_snapshots.csv"), index=False)
    print(f"Generated {len(ledger)} trades across {len(PERSONAS)} investors over {len(days)} days.")


if __name__ == "__main__":
    simulate()
