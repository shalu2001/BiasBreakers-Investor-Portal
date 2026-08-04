"""
dynamic_estimator.py -- turns a live stream of logged platform decisions into a
TIME-VARYING behavioural profile (alpha, lambda, gamma), so the utility adapts as
the investor's psychology drifts.

This is the deployment counterpart of the onboarding game. The onboarding game
anchors the profile at cold-start (especially lambda, via matched-stakes events);
this module keeps it current from the investor's ongoing decisions.

DATA CONTRACT (what the platform must log per decision -- this is the schema you
own and hand to the platform team):
    - transaction / decision events: date, action (BUY/SELL/HOLD/REBALANCE),
      ticker, target allocation, price, quantity, cash after
    - daily portfolio snapshot: date, cash, holdings, total_equity
    - market feed: daily close per ticker + benchmark index
From these, `reconstruct_decisions` builds the per-decision (wealth_change,
market_gap) the estimator consumes -- identical to what the game produces.

TWO SIGNALS, matching identifiability:
    - gamma (regret) and alpha : tracked CONTINUOUSLY from the passive decision
      window (well identified from ordinary trading).
    - lambda (loss aversion)   : refreshed by an occasional matched-stakes
      CHECK-IN (a few quick 50/50 bets), because loss aversion is hard to read
      from passive trades alone. Between check-ins it drifts slowly from its prior.
"""
import numpy as np
import pandas as pd

from estimator_v2 import fit_loss_aversion, fit_regret
from lambda_events import fit_lambda_events


def reconstruct_decisions(snapshots, index_returns, target_col=None):
    """
    Map the logged ledger -> per-decision (wealth_change, market_gap).

    snapshots: DataFrame with columns [date, total_equity, invested_fraction]
               (invested_fraction = value in risky assets / total_equity)
    index_returns: DataFrame [date, index_return_pct]
    Returns a decisions DataFrame with wealth_change, market_gap, target_pct.
    """
    df = snapshots.sort_values("date").reset_index(drop=True).merge(index_returns, on="date", how="left")
    df["wealth_change"] = df["total_equity"].diff()
    # market_gap = how much the market moved vs what the investor actually captured
    port_ret = df["total_equity"].pct_change() * 100
    df["market_gap"] = df["index_return_pct"].fillna(0) - port_ret.fillna(0)
    df["target_pct"] = df[target_col] if target_col else df.get("invested_fraction", 0.5)
    df["is_checkpoint_decision"] = True
    return df.dropna(subset=["wealth_change", "market_gap"]).reset_index(drop=True)


class DynamicProfile:
    """Rolling-window behavioural profile that updates as decisions arrive."""

    def __init__(self, window=45, prior=None):
        self.window = window
        # prior = onboarding-game estimate; lambda especially is anchored here
        self.prior = prior or {"alpha": 0.88, "lambda": 2.25, "gamma": 1.0}
        self.lambda_current = self.prior["lambda"]

    def passive_update(self, decisions_window):
        """Continuous update of gamma (and a weak passive lambda) from a window of
        ordinary decisions. Returns the current estimates + confidence."""
        rg = fit_regret(decisions_window, starting_equity=1_000_000)
        la = fit_loss_aversion(decisions_window, starting_equity=1_000_000)
        return {
            "gamma": rg["estimate"], "gamma_conf": rg["confidence"]["level"],
            "lambda_passive": la["estimate"], "lambda_conf": la["confidence"]["level"],
            "n": len(decisions_window),
        }

    def lambda_checkin(self, event_records):
        """Refresh lambda from a short matched-stakes check-in (a few 50/50 bets).
        This is the reliable lambda reading; it re-anchors self.lambda_current."""
        res = fit_lambda_events(event_records)
        if res["estimate"] is not None and res["confidence"]["level"] != "uninformative":
            self.lambda_current = res["estimate"]
        return res

    def track(self, decisions, step=8, checkins=None):
        """
        Roll a window over the full decision stream and emit a time series of
        estimates. `checkins` is an optional dict {decision_index: event_records}
        that injects a lambda check-in at that point in the stream.
        """
        checkins = checkins or {}
        rows = []
        for end in range(self.window, len(decisions) + 1, step):
            win = decisions.iloc[end - self.window:end]
            est = self.passive_update(win)
            # apply any check-ins that fall inside this step
            for idx in list(checkins.keys()):
                if end - step < idx <= end:
                    self.lambda_checkin(checkins.pop(idx))
            rows.append({"t": end, "gamma": est["gamma"], "gamma_conf": est["gamma_conf"],
                         "lambda": self.lambda_current, "lambda_passive": est["lambda_passive"]})
        return pd.DataFrame(rows)
