"""
STAGE 2 - Reconstruct a clean decision log from the transaction ledger.

WHY: to recover the parameters we don't need the raw trades themselves -- we need,
for EACH decision, the two things that drove it: how much the investor's money
changed (wealth_change) and how they did versus the market (market_gap). This stage
replays the ledger day-by-day and records those, INCLUDING the days they chose to
HOLD (a hold is a decision too, and it carries information).

Output: outputs/behavioral_validation_log.csv with columns
    investor_id, date, action, wealth_change, market_gap
"""
import os
import numpy as np
import pandas as pd
from market_data import load_market, build_lookup

HERE = os.path.dirname(__file__)
STARTING_CASH = 1_000_000.0
FEE = 0.01


def reconstruct():
    market = load_market()
    lookup, tickers = build_lookup(market)
    days = sorted(lookup.keys())
    ledger = pd.read_csv(os.path.join(HERE, "outputs", "transaction_ledger.csv"))
    ledger["Date"] = pd.to_datetime(ledger["Date"]).dt.date

    rows = []
    for inv in sorted(ledger["Investor_ID"].unique()):
        trades = ledger[ledger["Investor_ID"] == inv].set_index("Date")
        cash = STARTING_CASH
        holds = {t: 0 for t in tickers}
        prev_equity = STARTING_CASH
        for today in days:
            day = lookup[today]
            pmap = day["price_map"]
            idx_ret = day["index_return"]

            # value yesterday's holdings at today's prices -> the P&L that is felt
            pre_stock = sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
            pre_equity = cash + pre_stock
            wc = pre_equity - prev_equity
            inv_ret = ((pre_equity / prev_equity) - 1) * 100 if prev_equity > 0 else 0
            market_gap = idx_ret - inv_ret

            action = "HOLD"
            if today in trades.index:
                row = trades.loc[today]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                tk, qty, act = row["Ticker"], int(row["Executed_Quantity"]), row["Action"]
                price = pmap.get(tk)
                if price is not None:
                    if act == "BUY":
                        cash -= qty * price * (1 + FEE); holds[tk] += qty; action = "BUY"
                    elif act == "SELL" and holds.get(tk, 0) >= qty:
                        cash += qty * price * (1 - FEE); holds[tk] -= qty; action = "SELL"

            post_equity = cash + sum(q * pmap[t] for t, q in holds.items() if q > 0 and t in pmap)
            rows.append({"investor_id": inv, "date": today, "action": action,
                         "wealth_change": round(wc, 2), "market_gap": round(market_gap, 4)})
            prev_equity = post_equity

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "outputs", "behavioral_validation_log.csv"), index=False)
    print(f"Reconstructed {len(out)} decisions.")
    print(out.groupby("investor_id")["action"].value_counts())


if __name__ == "__main__":
    reconstruct()
