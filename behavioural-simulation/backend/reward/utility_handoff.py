"""
utility_handoff.py -- where the Behavioural Preference Modelling module ends.

This module's job: given a fitted investor profile (alpha, lambda, gamma), compute
the BEHAVIOURAL UTILITY SCORE U for any period the agent experiences, described by
(wealth_change, market_gap).

    U = prospect-theory value of the period's P&L            (loss aversion via
        lambda, diminishing sensitivity via alpha)
      - gamma * regret                                       (penalty for lagging
                                                              the market)

U is the SINGLE NUMBER handed to the reward-function colleague. What she does with
it -- how U is weighted, shaped, or combined with returns / turnover penalties
inside the RL reward -- is entirely her side. This module does not build the
reward; it only produces the psychological utility that feeds it.

Example
-------
    from reward.utility_handoff import BehaviouralUtility
    u = BehaviouralUtility.from_profile(profile)     # profile from /finish
    U_t = u.utility(wealth_change=+12500, market_gap=-0.8)   # -> hand this over
"""
import json
import numpy as np
from reward.utility_function import get_utility


class BehaviouralUtility:
    def __init__(self, alpha, lam, gamma, starting_equity=1_000_000.0):
        self.alpha = float(alpha)
        self.lam = float(lam)
        self.gamma = float(gamma)
        self.starting_equity = float(starting_equity)

    @classmethod
    def from_profile(cls, profile, starting_equity=1_000_000.0):
        """profile: {'alpha':.., 'lambda':.., 'gamma':..} as returned by /finish."""
        return cls(profile["alpha"], profile["lambda"], profile["gamma"], starting_equity)

    def utility(self, wealth_change, market_gap):
        """The behavioural utility score U for one period. This is the value handed
        to the reward-function side; it is NOT itself the reward."""
        return get_utility(wealth_change, market_gap, self.alpha, self.lam, self.gamma,
                           self.starting_equity)

    def utility_series(self, wealth_changes, market_gaps):
        """Vectorised U over a whole trajectory (for batching / analysis)."""
        wc = np.asarray(wealth_changes, dtype=float)
        mg = np.asarray(market_gaps, dtype=float)
        return np.array([self.utility(w, m) for w, m in zip(wc, mg)])

    def to_json(self):
        """Serialised profile to hand over alongside the utility scores."""
        return json.dumps({"alpha": self.alpha, "lambda": self.lam, "gamma": self.gamma,
                           "starting_equity": self.starting_equity})

    def __repr__(self):
        return f"BehaviouralUtility(alpha={self.alpha:.3f}, lambda={self.lam:.3f}, gamma={self.gamma:.3f})"
