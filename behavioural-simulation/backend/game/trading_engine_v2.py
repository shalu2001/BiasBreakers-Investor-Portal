import pandas as pd
import numpy as np

class TradingSession:
    """
    Core trading engine. Tracks cash, holdings, wealth changes, and the
    validated 'market_gap' signal (index return vs. the value-weighted
    return of what the user actually held).
    """

    TRANSACTION_COST_PCT = 0.01

    def __init__(self, scenario_name, stocks_df, index_df, starting_cash=1_000_000):
        self.scenario_name = scenario_name
        self.starting_cash = starting_cash
        self.stocks_df = stocks_df.copy()
        self.index_df = index_df.copy().sort_values("Date").reset_index(drop=True)

        self.stocks_df = self.stocks_df.sort_values(["Ticker", "Date"])
        self.stocks_df["ticker_return_pct"] = self.stocks_df.groupby("Ticker")["Close"].pct_change() * 100

        if "SP_SL20" in self.index_df.columns:
            self.index_df["index_return_pct"] = self.index_df["SP_SL20"].pct_change() * 100
        else:
            raise ValueError("index_df must contain an SP_SL20 column")

        self.trading_days = sorted(self.stocks_df["Date"].unique())
        self.day_idx = 0

        self.cash = starting_cash
        self.holdings = {}
        self.trade_log = []
        self._prev_day_equity = starting_cash

    def current_date(self):
        return self.trading_days[self.day_idx]

    def is_session_over(self):
        return self.day_idx >= len(self.trading_days) - 1

    def get_market_state(self):
        day_prices = self.stocks_df[self.stocks_df["Date"] == self.current_date()]
        return day_prices.set_index("Ticker")[["Open", "High", "Low", "Close", "Volume", "ticker_return_pct"]].to_dict("index")

    def get_day_number(self):
        """Abstracted position in the session (1-indexed), never the real calendar date --
        prevents a player from recognizing a specific historical event and reacting to
        foreknowledge rather than genuine in-the-moment judgment."""
        return self.day_idx + 1

    def get_total_days(self):
        return len(self.trading_days)

    def get_recent_history(self, ticker, lookback=15):
        """Last `lookback` trading days of OHLC for a ticker, up to and including today --
        used for the candlestick chart. Returns relative day labels, not real dates."""
        end_idx = self.day_idx
        start_idx = max(0, end_idx - lookback + 1)
        window_dates = self.trading_days[start_idx:end_idx + 1]
        subset = self.stocks_df[(self.stocks_df["Ticker"] == ticker) & (self.stocks_df["Date"].isin(window_dates))]
        subset = subset.sort_values("Date").reset_index(drop=True)

        records = []
        for i, row in subset.iterrows():
            relative_day = start_idx + i + 1
            records.append({
                "day": relative_day, "open": row["Open"], "high": row["High"],
                "low": row["Low"], "close": row["Close"],
            })
        return records

    def get_index_return(self):
        row = self.index_df[self.index_df["Date"] == self.current_date()]
        if row.empty or pd.isna(row.iloc[0]["index_return_pct"]):
            return 0.0
        return float(row.iloc[0]["index_return_pct"])

    def total_equity(self):
        prices = self.get_market_state()
        equity = self.cash
        for ticker, qty in self.holdings.items():
            if ticker in prices:
                equity += qty * prices[ticker]["Close"]
        return equity

    def held_stock_return(self):
        prices = self.get_market_state()
        held_value, weighted_return = 0.0, 0.0
        for ticker, qty in self.holdings.items():
            if qty > 0 and ticker in prices:
                val = qty * prices[ticker]["Close"]
                r = prices[ticker]["ticker_return_pct"]
                r = 0.0 if pd.isna(r) else r
                held_value += val
                weighted_return += val * r
        return (weighted_return / held_value) if held_value > 0 else 0.0

    def market_gap(self):
        """How much the market moved compared to what you actually held."""
        return self.get_index_return() - self.held_stock_return()

    def cear(self):
        equity = self.total_equity()
        return self.cash / equity if equity > 0 else None

    def submit_trade(self, ticker, action, quantity):
        if action not in ("buy", "sell"):
            raise ValueError("action must be 'buy' or 'sell'")
        prices = self.get_market_state()
        if ticker not in prices:
            raise ValueError(f"{ticker} not tradable on {self.current_date()}")

        price = prices[ticker]["Close"]
        notional = price * quantity
        fee = notional * self.TRANSACTION_COST_PCT
        mg = self.market_gap()

        if action == "buy":
            total_cost = notional + fee
            if total_cost > self.cash:
                return {"status": "rejected", "reason": "insufficient_cash",
                        "cash_available": self.cash, "cost_requested": total_cost}
            self.cash -= total_cost
            self.holdings[ticker] = self.holdings.get(ticker, 0) + quantity
        else:
            held = self.holdings.get(ticker, 0)
            if quantity > held:
                return {"status": "rejected", "reason": "insufficient_holdings",
                        "held": held, "requested": quantity}
            proceeds = notional - fee
            self.cash += proceeds
            self.holdings[ticker] -= quantity
            if self.holdings[ticker] == 0:
                del self.holdings[ticker]

        equity_after = self.total_equity()
        record = {
            "date": self.current_date(), "ticker": ticker, "action": action.upper(),
            "quantity": quantity, "price": price, "fee": fee,
            "wealth_change": equity_after - self._prev_day_equity,
            "market_gap": mg,
            "is_checkpoint_decision": True,
            "cash_after": self.cash, "equity_after": equity_after, "cear_after": self.cear(),
        }
        self.trade_log.append(record)
        self._prev_day_equity = equity_after
        return {"status": "executed", **record}

    def log_hold(self):
        mg = self.market_gap()
        equity_after = self.total_equity()
        record = {
            "date": self.current_date(), "ticker": None, "action": "HOLD",
            "quantity": 0, "price": None, "fee": 0.0,
            "wealth_change": equity_after - self._prev_day_equity,
            "market_gap": mg,
            "is_checkpoint_decision": True,
            "cash_after": self.cash, "equity_after": equity_after, "cear_after": self.cear(),
        }
        self.trade_log.append(record)
        self._prev_day_equity = equity_after
        return record

    def advance_day(self):
        if self.is_session_over():
            return {"status": "session_complete"}
        self.day_idx += 1
        return {"status": "advanced", "new_date": self.current_date()}

    def get_trade_log_df(self):
        return pd.DataFrame(self.trade_log)