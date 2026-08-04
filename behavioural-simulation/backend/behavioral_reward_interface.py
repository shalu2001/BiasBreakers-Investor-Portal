from utility_function import get_utility, calibrate_raw_estimate


class BehavioralRewardModel:
    """
    THE interface handed to the RL module.

    One of these gets created ONCE per user, right after their game session
    is fitted. From then on, the RL environment just calls .reward(...) at
    every single timestep during training -- it never needs to know alpha,
    lambda, gamma, or calibration exist at all.
    """

    def __init__(self, raw_alpha, raw_lambda, raw_gamma, starting_equity=1_000_000.0, apply_calibration=True):
        self.raw = {"alpha": raw_alpha, "lambda": raw_lambda, "gamma": raw_gamma}

        if apply_calibration:
            calibrated = calibrate_raw_estimate(raw_alpha, raw_lambda, raw_gamma)
        else:
            calibrated = dict(self.raw)

        self.alpha = calibrated["alpha"]
        self.lam = calibrated["lambda"]
        self.gamma = calibrated["gamma"]
        self.starting_equity = starting_equity
        self.calibrated = calibrated

    def reward(self, wealth_change, market_gap):
        """The only method the RL side ever calls. One number in, one number out."""
        return get_utility(wealth_change, market_gap, self.alpha, self.lam, self.gamma, self.starting_equity)

    def __repr__(self):
        return (f"BehavioralRewardModel(alpha={self.alpha:.3f}, "
                f"lambda={self.lam:.3f}, gamma={self.gamma:.3f})")