"""
event_round.py -- the matched-stakes event round that cleanly identifies
loss aversion (lambda), regardless of the player's free-play trading style.

After the two free-play blocks, the player is shown a sequence of framed 50/50
bets with KNOWN gain/loss magnitudes ("NDB: 50/50 to jump +8% or drop -5% by
tomorrow -- how much do you commit?"). Because the stakes are set rather than
endogenous, the committed fraction across events directly reveals the CPT
gain/loss asymmetry, and lambda is estimated with rank correlation ~0.9
(vs ~0.1 from free allocation). See lambda_events.py for the validation.
"""
import numpy as np
from estimation.lambda_events import make_events, fit_lambda_events

EVENT_STAKE = 200_000                       # nominal LKR stake per event (framing only)
TICKERS = ["COMB", "DIAL", "HNB", "JKH", "LIOC", "NDB"]


class EventRound:
    def __init__(self, n_events=16, seed=None):
        seed = int(seed) if seed is not None else int(np.random.randint(1, 100000))
        self.events = make_events(seed=seed, n=n_events)     # list of (gain_pct, loss_pct)
        rng = np.random.default_rng(seed)
        self._tickers = [TICKERS[int(rng.integers(len(TICKERS)))] for _ in self.events]
        self.idx = 0
        self.records = []                                    # {gain_pct, loss_pct, commit}

    def total(self):
        return len(self.events)

    def is_complete(self):
        return self.idx >= len(self.events)

    def current(self):
        if self.is_complete():
            return None
        g, l = self.events[self.idx]
        return {
            "index": self.idx + 1,
            "total": len(self.events),
            "ticker": self._tickers[self.idx],
            "gain_pct": float(g),
            "loss_pct": float(l),
            "stake": EVENT_STAKE,
        }

    def commit(self, fraction):
        """Record the player's committed fraction (0..1) for the current event."""
        if self.is_complete():
            return {"status": "events_complete"}
        g, l = self.events[self.idx]
        self.records.append({"gain_pct": float(g), "loss_pct": float(l),
                             "commit": float(np.clip(fraction, 0.0, 1.0))})
        self.idx += 1
        if self.is_complete():
            return {"status": "events_complete"}
        return {"status": "next_event", "event": self.current()}

    def estimate_lambda(self):
        """Returns {'estimate', 'confidence', ...} or None if too few responses."""
        if len(self.records) < 4:
            return None
        return fit_lambda_events(self.records)
