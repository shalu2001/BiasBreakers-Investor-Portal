import pandas as pd
from game.allocation_checkpoint_session import AllocationCheckpointSession

SCENARIO_ORDER = ["2021_bull_run", "2022_crash", "2023_recovery"]
NEUTRAL_TICKER = "DIAL"

class MultiBlockSession:
    def __init__(self, scenario_data, starting_cash=1_000_000, n_per_bin=2):
        self.scenario_data = scenario_data
        self.starting_cash = starting_cash
        self.n_per_bin = n_per_bin
        self.block = "loss_aversion"
        self.scenario_idx = 0
        self.completed_logs = {"loss_aversion": [], "regret": []}
        self._current_finalized = False
        self.current_session = self._start_scenario()

    def _start_scenario(self):
        name = SCENARIO_ORDER[self.scenario_idx]
        stocks_df, index_df = self.scenario_data[name]
        return AllocationCheckpointSession(name, stocks_df, index_df, self.starting_cash, self.n_per_bin)

    def current_scenario_name(self):
        return SCENARIO_ORDER[self.scenario_idx]

    def get_market_state(self):
        return self.current_session.get_market_state()

    def get_tradable_ticker(self):
        return None if self.block == "loss_aversion" else NEUTRAL_TICKER

    def set_allocation(self, ticker, target_pct):
        if self.block == "regret":
            ticker = NEUTRAL_TICKER
        return self.current_session.set_target_allocation(ticker, target_pct)

    def is_fully_complete(self):
        return self.block == "regret" and self.scenario_idx == len(SCENARIO_ORDER) - 1 and self.current_session.is_session_over()

    def advance(self):
        result = self.current_session.advance_to_next_checkpoint()
        if result["status"] == "session_complete":
            self.completed_logs[self.block].append(self.current_session.get_trade_log_df())
            if self.scenario_idx < len(SCENARIO_ORDER) - 1:
                self.scenario_idx += 1
                self.current_session = self._start_scenario()
                return {"status": "new_scenario_started", "scenario_name": self.current_scenario_name(),
                        "date": str(self.current_session.current_date()),
                        "market_state": self.current_session.get_market_state(), "cash": self.current_session.cash}
            elif self.block == "loss_aversion":
                self.block = "regret"
                self.scenario_idx = 0
                self.current_session = self._start_scenario()
                return {"status": "new_block_started", "scenario_name": self.current_scenario_name(),
                        "date": str(self.current_session.current_date()),
                        "market_state": self.current_session.get_market_state(), "cash": self.current_session.cash,
                        "fixed_ticker": NEUTRAL_TICKER}
            else:
                self._current_finalized = True
                return {"status": "all_blocks_complete"}
        return {"status": "at_checkpoint", "scenario_name": self.current_scenario_name(),
                "date": str(self.current_session.current_date()),
                "market_state": self.current_session.get_market_state(), "cash": self.current_session.cash,
                "equity": self.current_session.total_equity()}

    def get_block_logs(self):
        logs = {"loss_aversion": list(self.completed_logs["loss_aversion"]), "regret": list(self.completed_logs["regret"])}
        if not self._current_finalized:
            current_log = self.current_session.get_trade_log_df()
            if not current_log.empty:
                logs[self.block].append(current_log)
        return (pd.concat(logs["loss_aversion"], ignore_index=True) if logs["loss_aversion"] else pd.DataFrame(),
                pd.concat(logs["regret"], ignore_index=True) if logs["regret"] else pd.DataFrame())