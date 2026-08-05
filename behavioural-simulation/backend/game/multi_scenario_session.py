import pandas as pd
from game.checkpointed_session import CheckpointedSession


class MultiScenarioSession:
    """
    Walks a player through all 3 scenarios in sequence (fresh $1M cash each
    time), then combines all their decisions across all three into one
    trade log for a single, combined parameter fit.
    """

    SCENARIO_ORDER = ["2021_bull_run", "2022_crash", "2023_recovery"]

    def __init__(self, scenario_data, starting_cash=1_000_000, n_per_bin=3):
        """
        scenario_data: dict like {"2021_bull_run": (stocks_df, index_df), ...}
        """
        self.starting_cash = starting_cash
        self.n_per_bin = n_per_bin
        self.scenario_data = scenario_data
        self.scenario_idx = 0
        self.completed_logs = []  # trade log DataFrames from finished scenarios
        self._final_scenario_finalized = False  # guards against double-counting the last scenario's log
        self.current_session = self._start_scenario(self.scenario_idx)

    def _start_scenario(self, idx):
        name = self.SCENARIO_ORDER[idx]
        stocks_df, index_df = self.scenario_data[name]
        return CheckpointedSession(name, stocks_df, index_df, self.starting_cash, self.n_per_bin)

    def current_scenario_name(self):
        return self.SCENARIO_ORDER[self.scenario_idx]

    def is_fully_complete(self):
        return self.scenario_idx >= len(self.SCENARIO_ORDER) - 1 and self.current_session.is_session_over()

    def submit_trade(self, ticker, action, quantity):
        return self.current_session.submit_trade(ticker, action, quantity)

    def log_hold(self):
        return self.current_session.log_hold()

    def advance(self):
        """
        Advances within the current scenario. If that scenario just finished,
        automatically moves on to the next one (fresh $1M), unless it was
        the last scenario -- then the whole multi-scenario session is done.
        """
        result = self.current_session.advance_to_next_checkpoint()

        if result["status"] == "session_complete":
            self.completed_logs.append(self.current_session.get_trade_log_df())

            if self.scenario_idx < len(self.SCENARIO_ORDER) - 1:
                self.scenario_idx += 1
                self.current_session = self._start_scenario(self.scenario_idx)
                return {
                    "status": "new_scenario_started",
                    "scenario_name": self.current_scenario_name(),
                    "date": str(self.current_session.current_date()),
                    "market_state": self.current_session.get_market_state(),
                    "cash": self.current_session.cash,
                }
            else:
                self._final_scenario_finalized = True
                return {"status": "all_scenarios_complete"}

        return {
            "status": "at_checkpoint",
            "scenario_name": self.current_scenario_name(),
            "date": str(self.current_session.current_date()),
            "market_state": self.current_session.get_market_state(),
            "cash": self.current_session.cash,
            "equity": self.current_session.total_equity(),
        }

    def get_combined_trade_log(self):
        """Combines the finished scenarios' logs with whatever's in the current
        (possibly still in-progress) scenario, for fitting at any point."""
        logs = list(self.completed_logs)
        if not self._final_scenario_finalized:
            current_log = self.current_session.get_trade_log_df()
            if not current_log.empty:
                logs.append(current_log)
        return pd.concat(logs, ignore_index=True) if logs else pd.DataFrame()