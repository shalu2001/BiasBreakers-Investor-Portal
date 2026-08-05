from game.trading_engine_v2 import TradingSession
from game.stratified_checkpoints import select_stratified_checkpoints


class CheckpointedSession(TradingSession):
    """
    Wraps TradingSession so the player only makes decisions at a handful
    of checkpoints -- selected by how much the market genuinely moved that
    day (severe drop, moderate drop, calm, moderate rally, severe rally),
    rather than blind even time-spacing. This ensures a real range of
    magnitudes, needed to identify curvature (alpha), not just direction.
    """

    def __init__(self, scenario_name, stocks_df, index_df, starting_cash=1_000_000, n_per_bin=3, seed=42):
        super().__init__(scenario_name, stocks_df, index_df, starting_cash)

        checkpoint_dates, self.bin_counts = select_stratified_checkpoints(index_df, n_per_bin=n_per_bin, seed=seed)
        date_to_idx = {d: i for i, d in enumerate(self.trading_days)}
        self.checkpoint_indices = sorted(date_to_idx[d] for d in checkpoint_dates if d in date_to_idx)
        if (len(self.trading_days) - 1) not in self.checkpoint_indices:
            self.checkpoint_indices.append(len(self.trading_days) - 1)
        self._checkpoint_cursor = 0

    def is_at_checkpoint(self):
        return self.day_idx in self.checkpoint_indices

    def next_checkpoint_date(self):
        remaining = [i for i in self.checkpoint_indices if i > self.day_idx]
        return self.trading_days[remaining[0]] if remaining else None

    def advance_to_next_checkpoint(self):
        """
        Call this after the player decides at the current checkpoint.
        Auto-holds through every day until (and including) the next
        checkpoint, or the end of the scenario -- whichever comes first.
        """
        while not self.is_session_over():
            self.advance_day()
            if self.day_idx not in self.checkpoint_indices:
                self.log_hold()
                self.trade_log[-1]["is_checkpoint_decision"] = False
            else:
                break
        return {"status": "session_complete" if self.is_session_over() else "at_checkpoint",
                "date": self.current_date()}