import pandas as pd
import numpy as np
from game.trading_engine_v2 import TradingSession


class AllocationSession(TradingSession):
    """
    Replaces free-form buy/sell/hold with a mandatory target allocation
    decision at every checkpoint. There is no costless skip.
    """

    def set_target_allocation(self, ticker, target_pct):
        """target_pct: 0.0 to 1.0, fraction of total equity to hold in `ticker`.

        This is a MEASUREMENT instrument, not a brokerage, so the rebalance is
        exact and frictionless: the position is set to precisely target_pct of
        equity (continuous weight -- no whole-share rounding), with no fee. This
        keeps every number verifiable (cash + stock == equity, to the rupee) and
        avoids penalising the active rebalancing the estimator needs to observe.
        """
        prices = self.get_market_state()
        if ticker not in prices:
            raise ValueError(f"{ticker} not tradable on {self.current_date()}")

        mg = self.market_gap()
        equity = self.total_equity()
        price = prices[ticker]["Close"]
        target_value = target_pct * equity

        # exact, fee-free rebalance to a single-stock position
        self.holdings = {ticker: target_value / price} if target_value > 0 else {}
        self.cash = equity - target_value

        equity_after = self.total_equity()
        record = {
            "date": self.current_date(), "ticker": ticker, "action": "REBALANCE",
            "target_pct": target_pct, "quantity": None, "price": price, "fee": 0.0,
            "wealth_change": equity_after - self._prev_day_equity,
            "market_gap": mg,
            "is_checkpoint_decision": True,
            "cash_after": self.cash, "equity_after": equity_after, "cear_after": self.cear(),
        }
        self.trade_log.append(record)
        self._prev_day_equity = equity_after
        return record