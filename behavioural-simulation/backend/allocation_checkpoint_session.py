from allocation_engine import AllocationSession
from stratified_checkpoints import select_stratified_checkpoints


class AllocationCheckpointSession(AllocationSession):
    def __init__(self, scenario_name, stocks_df, index_df, starting_cash=1_000_000, n_per_bin=5, seed=42):
        super().__init__(scenario_name, stocks_df, index_df, starting_cash)
        checkpoint_dates, self.bin_counts = select_stratified_checkpoints(index_df, n_per_bin=n_per_bin, seed=seed)
        date_to_idx = {d: i for i, d in enumerate(self.trading_days)}
        self.checkpoint_indices = sorted(date_to_idx[d] for d in checkpoint_dates if d in date_to_idx)
        if (len(self.trading_days) - 1) not in self.checkpoint_indices:
            self.checkpoint_indices.append(len(self.trading_days) - 1)

    def advance_to_next_checkpoint(self):
        while not self.is_session_over():
            self.advance_day()
            if self.day_idx in self.checkpoint_indices:
                break
        return {"status": "session_complete" if self.is_session_over() else "at_checkpoint",
                "date": self.current_date()}