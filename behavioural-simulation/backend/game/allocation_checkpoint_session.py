from game.allocation_engine import AllocationSession
from game.stratified_checkpoints import select_stratified_checkpoints


class AllocationCheckpointSession(AllocationSession):
    # Opening lead-in: keep this many trading days before the first decision so
    # the candlestick chart opens with a proper stretch of history (the session
    # used to open at day_idx 0, leaving a single bar / an empty chart). Capped
    # to a third of the scenario for short windows (e.g. the crash).
    MIN_LEADIN = 30

    def __init__(self, scenario_name, stocks_df, index_df, starting_cash=1_000_000, n_per_bin=5, seed=42):
        super().__init__(scenario_name, stocks_df, index_df, starting_cash)
        checkpoint_dates, self.bin_counts = select_stratified_checkpoints(index_df, n_per_bin=n_per_bin, seed=seed)
        date_to_idx = {d: i for i, d in enumerate(self.trading_days)}
        last = len(self.trading_days) - 1
        idxs = sorted(date_to_idx[d] for d in checkpoint_dates if d in date_to_idx)

        # Drop checkpoints inside the opening lead-in window (the earliest,
        # lowest-context days) so the first decision has candles behind it.
        leadin = min(self.MIN_LEADIN, max(0, last // 3))
        idxs = [i for i in idxs if i >= leadin]
        if not idxs:
            idxs = [min(leadin, last)]
        if last not in idxs:
            idxs.append(last)
        self.checkpoint_indices = sorted(idxs)

        # Open the session AT the first checkpoint, so the very first chart shows
        # a lead-in of history rather than a single bar.
        self.day_idx = self.checkpoint_indices[0]
        self._start_idx = self.checkpoint_indices[0]

    # Display numbering is relative to where play actually begins, so the on-screen
    # counter reads "1 / N" at the first decision rather than "22 / 240".
    def get_day_number(self):
        return self.day_idx - self._start_idx + 1

    def get_total_days(self):
        return (len(self.trading_days) - 1) - self._start_idx + 1

    def num_checkpoints(self):
        """How many decisions this fund actually asks for (small — for the UI)."""
        return len(self.checkpoint_indices)

    def advance_to_next_checkpoint(self):
        while not self.is_session_over():
            self.advance_day()
            if self.day_idx in self.checkpoint_indices:
                break
        return {"status": "session_complete" if self.is_session_over() else "at_checkpoint",
                "date": self.current_date()}