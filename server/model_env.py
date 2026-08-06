"""
Data pipeline + RL environment for the v14 behavioral portfolio model.

Adapted from BiasBreakers-porfolio-optimization/src/rl/evaluate_dynamicCandidateList_v14.py
-- PersonaAwareExtractor, PersonaPortfolioEnv, RunningStats and the market
data pipeline (prepare_market_data) are kept structurally IDENTICAL to that
file, because the trained model's policy network was fit against this exact
observation shape (persona(3) + utility(1) + weights(N) + vol(N) +
lambda_risk(N) + tracking_error(N) + bl_return(N), on top of FinRL's base
covariance + technical-indicator state) and this exact masking/cash logic.
Any drift from the training-time construction produces a technically-valid
but meaningless prediction, not an error -- so this file intentionally does
NOT try to simplify or "clean up" that logic, only trims the parts specific
to the historical backtest loop (investor CSV loading, day-by-day rollout)
that a live single-shot recommendation doesn't need.
"""
import os
import numpy as np
import pandas as pd
import gymnasium as gym
from scipy.stats import norm
import torch
import torch.nn as nn
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from pymongo import MongoClient
from dotenv import load_dotenv

from finrl.meta.preprocessor.preprocessors import FeatureEngineer
from finrl.meta.env_portfolio_allocation.env_portfolio import StockPortfolioEnv
from finrl.config import INDICATORS

BASE_DIR = os.path.dirname(__file__)
# BL_DIR = os.path.join(BASE_DIR, 'data', 'bl')  # disabled, see BL loader functions below


class PersonaAwareExtractor(BaseFeaturesExtractor):
    """Must match the trainer's PersonaAwareExtractor EXACTLY -- this is
    the custom policy feature extractor the model was trained with, and
    stable-baselines3 needs the class importable to unpickle the policy."""
    def __init__(self, observation_space, market_dim, stock_dim,
                 market_embed=128, persona_embed=32):
        super().__init__(observation_space, features_dim=market_embed + persona_embed)
        self.market_dim = market_dim
        self.stock_dim = stock_dim
        self.persona_dim = 3
        self.utility_dim = 1

        self.market_net = nn.Sequential(
            nn.Linear(market_dim + 5 * stock_dim, 256), nn.ReLU(),
            nn.Linear(256, market_embed), nn.ReLU(),
        )
        self.persona_net = nn.Sequential(
            nn.Linear(self.persona_dim + self.utility_dim, 64), nn.ReLU(),
            nn.Linear(64, persona_embed), nn.ReLU(),
        )

        self.register_buffer(
            "persona_mean", torch.tensor([0.88, 2.25, 2.00], dtype=torch.float32)
        )
        self.register_buffer(
            "persona_std", torch.tensor([0.15, 0.75, 1.50], dtype=torch.float32)
        )

    def forward(self, observations):
        market_end = self.market_dim
        persona_end = market_end + self.persona_dim
        utility_end = persona_end + self.utility_dim
        weights_end = utility_end + self.stock_dim
        vol_end = weights_end + self.stock_dim
        downside_end = vol_end + self.stock_dim
        track_end = downside_end + self.stock_dim

        market = observations[:, :market_end]
        persona = observations[:, market_end:persona_end]
        utility = observations[:, persona_end:utility_end]
        weights = observations[:, utility_end:weights_end]
        vol = observations[:, weights_end:vol_end]
        downside = observations[:, vol_end:downside_end]
        track = observations[:, downside_end:track_end]
        bl_ret = observations[:, track_end:]

        persona_norm = (persona - self.persona_mean) / self.persona_std

        market_feat = self.market_net(torch.cat([market, weights, vol, downside, track, bl_ret], dim=1))
        persona_feat = self.persona_net(torch.cat([persona_norm, utility], dim=1))

        return torch.cat([market_feat, persona_feat], dim=1)


class RunningStats:
    """Online mean/std tracker. Must match the trainer EXACTLY."""
    def __init__(self, eps=1e-8):
        self.eps = eps
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x):
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def std(self):
        if self.count < 2:
            return 1.0
        return float(np.sqrt(max(self.m2 / self.count, self.eps)))

    def normalize(self, x):
        self.update(x)
        return (x - self.mean) / self.std

    def normalize_scale(self, x):
        self.update(x)
        return x / self.std


class PersonaPortfolioEnv(StockPortfolioEnv):
    """Must match dynamicCandidateList_v14.py's trainer EXACTLY -- see that
    file's module docstring for the full rationale behind every fix
    referenced below."""
    ALPHA_POP_MEAN, ALPHA_POP_STD = 0.88, 0.15
    LAMBDA_POP_MEAN, LAMBDA_POP_STD = 2.25, 0.75
    GAMMA_POP_MEAN, GAMMA_POP_STD = 2.00, 1.50

    MIN_CANDIDATES = 5
    DRIFT_THRESHOLD_RELATIVE = 0.20
    # BL_WEIGHT = 0.3  # disabled -- Black-Litterman pipeline is a teammate's
    # in-progress module, not wired up here yet. See _unified_candidate_rank()
    # below: the bl_rank term is commented out of combined_badness entirely
    # (not just zero-weighted), so the mask currently ranks on alpha/lambda/
    # gamma only. Re-enable both once the real BL data is ready.

    BASE_CASH_WEIGHT = 0.10
    CASH_SENSITIVITY = 0.06
    MIN_CASH_WEIGHT = 0.02
    MAX_CASH_WEIGHT = 0.30

    def __init__(self, persona=None, is_training=False, tickers=None,
                 financial_mode='log_return', vol_window=20,
                 risk_penalty_alpha=1.0, dsr_eta=0.01,
                 w_fin=1.0, w_behavioral=0.5, w_risk=0.3,
                 w_fit=0.5, reward_scale=1.0, **kwargs):
        super().__init__(**kwargs)

        flat_size = int(np.prod(self.observation_space.shape))
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(flat_size + 3 + 1 + 5 * self.stock_dim,),
            dtype=np.float32
        )

        self.lambda_turnover = 0.02
        self.persona = persona if persona is not None else np.array([1.0, 1.0, 0.0])
        self.is_training = is_training
        self.tickers = tickers

        self.financial_mode = financial_mode
        self.vol_window = vol_window
        self.risk_penalty_alpha = risk_penalty_alpha
        self.dsr_eta = dsr_eta
        self.w_fin = w_fin
        self.w_behavioral = w_behavioral
        self.w_risk = w_risk
        self.w_fit = w_fit
        self.reward_scale = reward_scale

        self._fin_stats = RunningStats()
        self._util_stats = RunningStats()
        self._risk_stats = RunningStats()
        self._fit_stats = RunningStats()

        self._return_history = []
        self._dsr_A = 0.0
        self._dsr_B = 0.0
        self._last_pool_badness = None

        self.utility = 0.0
        self.prev_value = self.initial_amount
        self.current_weights = np.ones(self.stock_dim) / self.stock_dim
        self.last_raw_state = None

        self.last_rebalance_target = None
        self.last_rebalanced = True

    def _unified_candidate_rank(self, real_tickers, alpha, lam, gamma,
                                 stock_volatility, stock_lambda_risk, stock_tracking_error,
                                 stock_bl_return):
        if len(real_tickers) <= self.MIN_CANDIDATES:
            self._last_pool_badness = None
            return set(real_tickers)

        def _intensity(x, mean, std):
            return float(np.clip(abs(norm.cdf((x - mean) / std) - 0.5) * 2.0, 0.0, 1.0))

        alpha_intensity = _intensity(alpha, self.ALPHA_POP_MEAN, self.ALPHA_POP_STD)
        lam_intensity = _intensity(lam, self.LAMBDA_POP_MEAN, self.LAMBDA_POP_STD)
        gamma_intensity = _intensity(gamma, self.GAMMA_POP_MEAN, self.GAMMA_POP_STD)

        vol = stock_volatility.reindex(real_tickers)
        downside = stock_lambda_risk.reindex(real_tickers)
        track_err = stock_tracking_error.reindex(real_tickers)
        # bl_return = stock_bl_return.reindex(real_tickers)  # disabled, see BL_WEIGHT comment above

        vol_rank = vol.rank(pct=True)
        downside_rank = downside.rank(pct=True)
        track_err_rank = track_err.rank(pct=True)
        # bl_rank = (1.0 - bl_return.rank(pct=True)).fillna(0.5)  # disabled, see BL_WEIGHT comment above

        alpha_rank = (vol_rank if alpha < self.ALPHA_POP_MEAN else (1.0 - vol_rank)).fillna(0.5)
        lam_rank = (downside_rank if lam >= self.LAMBDA_POP_MEAN else (1.0 - downside_rank)).fillna(0.5)
        gamma_rank = (track_err_rank if gamma >= self.GAMMA_POP_MEAN else (1.0 - track_err_rank)).fillna(0.5)

        combined_badness = (
            alpha_intensity * alpha_rank
            + lam_intensity * lam_rank
            + gamma_intensity * gamma_rank
            # + self.BL_WEIGHT * bl_rank  # disabled, see BL_WEIGHT comment above
        )

        overall_intensity = (
            1.0
            - (1.0 - alpha_intensity)
            * (1.0 - lam_intensity)
            * (1.0 - gamma_intensity)
        )

        keep_fraction = 1.0 - 0.7 * overall_intensity
        keep_n = max(self.MIN_CANDIDATES, int(len(real_tickers) * keep_fraction))

        selected = combined_badness.sort_values(ascending=True).index[:keep_n]
        self._last_pool_badness = combined_badness.reindex(selected)

        return set(selected)

    def _generate_mask(self):
        alpha, lam, gamma = self.persona

        stock_volatility = pd.Series(self.data['vol_arr'].values[0], index=self.tickers)
        stock_lambda_risk = pd.Series(self.data['lambda_risk_arr'].values[0], index=self.tickers)
        stock_tracking_error = pd.Series(self.data['tracking_error_arr'].values[0], index=self.tickers)
        # bl_return_arr is a neutral all-zero placeholder for now (see
        # _load_bl_stats_placeholder below) -- still read here so the call
        # signature/observation shape stay unchanged, but _unified_candidate_rank
        # no longer factors it into ranking.
        stock_bl_return = pd.Series(self.data['bl_return_arr'].values[0], index=self.tickers)

        real_tickers = [t for t in self.tickers if t != 'CASH']

        candidate_list = self._unified_candidate_rank(
            real_tickers, alpha, lam, gamma,
            stock_volatility, stock_lambda_risk, stock_tracking_error,
            stock_bl_return
        )
        candidate_list.add('CASH')

        mask = np.array([1.0 if tic in candidate_list else 0.0 for tic in self.tickers])
        if mask.sum() == 0:
            mask[:] = 1.0
        return mask

    def _persona_cash_target(self):
        alpha, lam, _gamma = self.persona
        alpha_z = (self.ALPHA_POP_MEAN - alpha) / self.ALPHA_POP_STD
        lam_z = (lam - self.LAMBDA_POP_MEAN) / self.LAMBDA_POP_STD
        cash_score = 0.5 * alpha_z + 0.5 * lam_z
        return float(np.clip(
            self.BASE_CASH_WEIGHT + self.CASH_SENSITIVITY * cash_score,
            self.MIN_CASH_WEIGHT, self.MAX_CASH_WEIGHT
        ))

    def _apply_cash_policy(self, weights):
        if self.tickers is None or 'CASH' not in self.tickers:
            return weights

        cash_idx = self.tickers.index('CASH')
        cash_target = self._persona_cash_target()

        stock_mask = np.ones(len(weights), dtype=bool)
        stock_mask[cash_idx] = False

        stock_sum = float(weights[stock_mask].sum())
        out = np.zeros_like(weights)

        if stock_sum <= 1e-8:
            out[cash_idx] = 1.0
            return out

        out[stock_mask] = weights[stock_mask] / stock_sum * (1.0 - cash_target)
        out[cash_idx] = cash_target
        return out

    def reset(self, seed=None, options=None):
        self.utility = 0.0
        self.prev_value = self.initial_amount

        self.last_rebalance_target = None
        self.last_rebalanced = True

        self._return_history = []
        self._dsr_A = 0.0
        self._dsr_B = 0.0
        self._last_pool_badness = None

        state, info = super().reset(seed=seed)
        self.last_raw_state = state

        mask = self._generate_mask()
        eligible = mask > 0
        init_weights = np.zeros(self.stock_dim)
        init_weights[eligible] = 1.0 / eligible.sum()
        self.current_weights = init_weights

        return self._augment(state), info

    def step(self, actions):
        old_weights = self.current_weights.copy()

        if self.last_rebalance_target is None:
            should_rebalance = True
        else:
            target = self.last_rebalance_target
            rel_drift = np.where(
                target > 1e-8,
                np.abs(old_weights - target) / np.maximum(target, 1e-8),
                0.0
            )
            should_rebalance = bool(rel_drift.max() >= self.DRIFT_THRESHOLD_RELATIVE)

        if should_rebalance:
            mask = self._generate_mask()
            penalized_actions = np.where(mask == 1.0, actions, -1e9)
            state, _, terminated, truncated, info = super().step(penalized_actions)
        else:
            today_returns = np.nan_to_num(
                self.data.set_index('tic')['daily_return'].reindex(self.tickers).values,
                nan=0.0
            )
            w_drift = old_weights * (1.0 + today_returns)
            total = w_drift.sum()
            w_drift = w_drift / total if total > 1e-8 else old_weights.copy()
            synthetic_action = np.log(np.clip(w_drift, 1e-12, None))
            state, _, terminated, truncated, info = super().step(synthetic_action)

        self.last_raw_state = state

        weights = (
            self.actions_memory[-1]
            if hasattr(self, 'actions_memory') and len(self.actions_memory) > 0
            else self.current_weights
        )

        PRUNE_THRESHOLD = 0.01
        weights = np.where(weights < PRUNE_THRESHOLD, 0.0, weights)
        if weights.sum() > 0:
            weights = weights / weights.sum()

        if should_rebalance:
            weights = self._apply_cash_policy(weights)
            self.last_rebalance_target = weights.copy()
            turnover_sum = np.sum(np.abs(weights - old_weights))
        else:
            turnover_sum = 0.0

        self.last_rebalanced = should_rebalance
        self.current_weights = weights

        # Reward computation is irrelevant to a live single-shot
        # recommendation (nothing here is trained further), but step()'s
        # side effects (mask, cash policy, self.current_weights) are what we
        # actually need -- kept so this stays a faithful copy of the trainer
        # rather than a re-derivation that could silently drift from it.
        if should_rebalance and self._last_pool_badness is not None and len(self._last_pool_badness) > 0:
            badness = self._last_pool_badness
            pool_avg_badness = float(badness.mean())
            held = pd.Series(weights, index=self.tickers).reindex(badness.index).fillna(0.0)
            held_total = float(held.sum())
            portfolio_avg_badness = (
                float((held * badness).sum() / held_total) if held_total > 1e-8
                else pool_avg_badness
            )
            fit_raw = pool_avg_badness - portfolio_avg_badness
        else:
            fit_raw = 0.0

        V_now, V_next = self.prev_value, self.portfolio_value
        r_t = np.log(V_next / V_now) if V_now > 0 else 0.0
        step_return = (V_next - V_now) / V_now if V_now > 0 else 0.0
        self.prev_value = self.portfolio_value

        if self.financial_mode == 'log_return':
            self._return_history.append(r_t)
            if len(self._return_history) > self.vol_window:
                self._return_history.pop(0)
            sig2 = float(np.var(self._return_history)) if len(self._return_history) > 1 else 0.0
            fin = r_t
            risk = self.risk_penalty_alpha * sig2
        else:
            fin = 0.0
            risk = 0.0

        index_return = (
            self.data['sl20_proxy_return'].values[0]
            if 'sl20_proxy_return' in self.data.columns
            else 0.0
        )
        market_gap = index_return - step_return

        alpha, lam, gamma = self.persona
        abs_step_return = abs(step_return)
        if step_return >= 0:
            v = abs_step_return ** alpha
        else:
            v = -lam * (abs_step_return ** alpha)

        regret = gamma * max(0, market_gap)
        raw_utility = v - regret
        self.utility = np.clip(raw_utility, -5, 5)
        util = self.utility

        fin_n = self._fin_stats.normalize(fin)
        util_n = self._util_stats.normalize(util)
        risk_n = self._risk_stats.normalize_scale(risk)

        if should_rebalance:
            fit_n = self._fit_stats.normalize_scale(fit_raw)
        else:
            fit_n = 0.0

        reward = (
            self.w_fin * fin_n
            + self.w_behavioral * util_n
            - self.w_risk * risk_n
            + self.w_fit * fit_n
        ) * self.reward_scale

        return self._augment(state), reward, terminated, truncated, info

    def _augment(self, state):
        vol_arr = np.nan_to_num(np.asarray(self.data['vol_arr'].values[0], dtype=np.float32), nan=0.0)
        downside_arr = np.nan_to_num(np.asarray(self.data['lambda_risk_arr'].values[0], dtype=np.float32), nan=0.0)
        track_arr = np.nan_to_num(np.asarray(self.data['tracking_error_arr'].values[0], dtype=np.float32), nan=0.0)
        bl_arr = np.nan_to_num(np.asarray(self.data['bl_return_arr'].values[0], dtype=np.float32), nan=0.0)

        return np.concatenate([
            state.flatten(),
            self.persona,
            [self.utility],
            self.current_weights,
            vol_arr,
            downside_arr,
            track_arr,
            bl_arr,
        ])


# ==========================================
# Black-Litterman posterior returns -- DISABLED
# ==========================================
# The real loader (reads a teammate's in-progress BL pipeline output from
# src/data/bl/bl-YYYY-MM/posterior_returns.csv) is commented out below. That
# data isn't part of this repo, and the pipeline that produces it is still
# being built elsewhere. Re-enable this block (and BL_WEIGHT /
# _unified_candidate_rank's bl_rank term above) once that's ready -- until
# then, _load_bl_stats_placeholder() below supplies neutral zeros instead so
# the model's observation shape (which was TRAINED expecting a 5th per-stock
# array here) stays structurally correct.
#
# BL_TICKER_SUFFIX_MAP = {
#     'HAYL': 'HAYL.N', 'HHL': 'HHL.N', 'HNB': 'HNB.N',
#     'JKH': 'JKH.N', 'LIOC': 'LIOC.N',
# }
#
#
# def _load_bl_monthly_returns():
#     monthly = {}
#     for entry in sorted(os.listdir(BL_DIR)):
#         if not entry.startswith('bl-'):
#             continue
#         month_key = entry[len('bl-'):]
#         csv_path = os.path.join(BL_DIR, entry, 'posterior_returns.csv')
#         if not os.path.exists(csv_path):
#             continue
#         bl_df = pd.read_csv(csv_path)
#         bl_df['tic'] = bl_df['ticker'].map(lambda t: BL_TICKER_SUFFIX_MAP.get(t, t))
#         monthly[month_key] = bl_df.set_index('tic')['posterior_expected_return']
#     return monthly
#
#
# def _load_bl_stats_df(processed, tickers):
#     bl_monthly_returns = _load_bl_monthly_returns()
#
#     def _bl_row_for_date(date):
#         month_key = pd.Timestamp(date).strftime('%Y-%m')
#         series = bl_monthly_returns.get(month_key)
#         if series is None:
#             return np.zeros(len(tickers))
#         return series.reindex(tickers).fillna(0.0).values
#
#     bl_dates = sorted(processed['date'].unique())
#     return pd.DataFrame({
#         'date': bl_dates,
#         'bl_return_arr': [_bl_row_for_date(d) for d in bl_dates],
#     })


def _load_bl_stats_placeholder(processed, tickers):
    """Neutral stand-in for _load_bl_stats_df() above, until the teammate's
    BL pipeline is ready. Same output contract (date, bl_return_arr), all
    zeros -- see the DISABLED block's comment for why this slot can't just
    be removed."""
    bl_dates = sorted(processed['date'].unique())
    return pd.DataFrame({
        'date': bl_dates,
        'bl_return_arr': [np.zeros(len(tickers)) for _ in bl_dates],
    })


# ==========================================
# Market data pipeline
# ==========================================
def prepare_market_data():
    """Rebuilds `processed` (technical indicators + covariance + rolling
    mask stats + BL returns, one row per ticker per date) EXACTLY as the
    trainer/evaluator do. Trimmed relative to evaluate_dynamicCandidateList_v14.py's
    prepare_data(): the synthetic-investor CSV loading is dropped, since a
    live recommendation doesn't backtest against historical investor trades
    -- see main.py for how persona/current-holdings are supplied instead."""
    load_dotenv()
    client = MongoClient(os.getenv("AZURE_COSMOS_CONNECTION_STRING"), retryWrites=False)
    db = client[os.getenv("DATABASE_NAME")]

    stock_collection = db[os.getenv("COLLECTION_NAME")]
    df = pd.DataFrame(list(stock_collection.find({}, {"_id": 0})))
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['date', 'tic']).reset_index(drop=True)[
        ['date', 'tic', 'open', 'high', 'low', 'close', 'volume']
    ]

    CASH_ANNUAL_RETURN = 0.05
    CASH_ANNUAL_VOL = 0.01
    cash_daily_mean = (1 + CASH_ANNUAL_RETURN) ** (1 / 252) - 1
    cash_daily_std = CASH_ANNUAL_VOL / np.sqrt(252)

    cash_dates = df['date'].unique()
    cash_rng = np.random.RandomState(7)
    cash_returns = cash_rng.normal(cash_daily_mean, cash_daily_std, len(cash_dates))
    cash_price = np.cumprod(1 + cash_returns)

    cash_df = pd.DataFrame({
        'date': cash_dates,
        'tic': 'CASH',
        'open': cash_price,
        'high': cash_price,
        'low': cash_price,
        'close': cash_price,
        'volume': 0,
    })
    df = pd.concat([df, cash_df], ignore_index=True).sort_values(['date', 'tic']).reset_index(drop=True)

    index_df = pd.DataFrame(list(db["sp_sl20_index"].find({}, {"_id": 0})))
    index_df['date'] = pd.to_datetime(index_df['date'])
    index_df = index_df.sort_values('date').reset_index(drop=True)

    unique_tickers = df.tic.unique()
    unique_dates = index_df.date.unique()
    full_combination = pd.MultiIndex.from_product(
        [unique_dates, unique_tickers], names=['date', 'tic']
    ).to_frame(index=False)
    df = pd.merge(full_combination, df, on=['date', 'tic'], how='left').sort_values(['tic', 'date'])

    cols_to_fill = ['open', 'high', 'low', 'close', 'volume']
    df[cols_to_fill] = df.groupby('tic')[cols_to_fill].transform(lambda x: x.ffill().bfill())
    df['daily_return'] = df.groupby('tic')['close'].pct_change()

    if 'sp_sl20_close' in index_df.columns:
        index_df['sl20_proxy_return'] = index_df['sp_sl20_close'].pct_change()
    else:
        index_returns = df.groupby('date')['daily_return'].mean().reset_index()
        index_returns.columns = ['date', 'sl20_proxy_return']
        index_df = index_returns

    df = pd.merge(df, index_df[['date', 'sl20_proxy_return']], on='date', how='left').fillna(0)

    fe = FeatureEngineer(
        use_technical_indicator=True,
        tech_indicator_list=INDICATORS,
        use_turbulence=True
    )
    processed = fe.preprocess_data(df)

    df_pivot = processed.pivot_table(index='date', columns='tic', values='close')
    df_returns = df_pivot.pct_change().dropna()

    lookback = 60
    cov_list = [
        df_returns.iloc[i - lookback:i].cov().values
        for i in range(lookback, len(df_returns))
    ]
    cov_df = pd.DataFrame({'date': df_returns.index[lookback:], 'cov_list': cov_list})

    processed = (
        pd.merge(processed, cov_df, on='date')
        .dropna()
        .sort_values(["date", "tic"])
    )

    tickers = df_returns.std().index.tolist()
    mask_lookback = 90

    returns_ordered = df_returns.reindex(columns=tickers)
    index_return_series = (
        index_df.set_index('date')['sl20_proxy_return']
        .reindex(df_returns.index)
        .fillna(0)
    )

    rolling_vol = (
        returns_ordered.rolling(mask_lookback).std().shift(1) * np.sqrt(252)
    )

    LAMBDA_LOOKBACK = 180

    def _trailing_max_drawdown(a):
        cum = np.cumprod(1.0 + a)
        peak = np.maximum.accumulate(cum)
        return float(-np.min((cum - peak) / peak))

    rolling_lambda_risk = (
        returns_ordered
        .rolling(LAMBDA_LOOKBACK)
        .apply(_trailing_max_drawdown, raw=True)
        .shift(1)
    )

    return_gap = returns_ordered.sub(index_return_series, axis=0)
    rolling_tracking_error = (
        return_gap.rolling(mask_lookback).std().shift(1) * np.sqrt(252)
    )

    valid_dates = (
        rolling_vol.dropna(how='any').index
        .intersection(rolling_lambda_risk.dropna(how='any').index)
        .intersection(rolling_tracking_error.dropna(how='any').index)
    )

    mask_stats_df = pd.DataFrame({
        'date': valid_dates,
        'vol_arr': [rolling_vol.loc[d].values for d in valid_dates],
        'lambda_risk_arr': [rolling_lambda_risk.loc[d].values for d in valid_dates],
        'tracking_error_arr': [rolling_tracking_error.loc[d].values for d in valid_dates],
    })

    processed = (
        pd.merge(processed, mask_stats_df, on='date')
        .dropna()
        .sort_values(["date", "tic"])
    )

    # processed = pd.merge(
    #     processed, _load_bl_stats_df(processed, tickers), on='date'
    # ).dropna().sort_values(["date", "tic"])  # disabled, see BL section above
    processed = pd.merge(
        processed, _load_bl_stats_placeholder(processed, tickers), on='date'
    ).dropna().sort_values(["date", "tic"])

    return processed, df_returns, tickers


def latest_day_frame(processed):
    """Slices `processed` down to just the most recent date, duplicated into
    two consecutive index days (0 and 1) -- the same index-per-unique-date
    convention FinRL's data_split() produces, but for "today" repeated twice
    rather than a historical backtest window.

    A single day isn't enough: StockPortfolioEnv.step() treats
    `self.day >= len(self.df.index.unique()) - 1` as terminal, and with only
    one day that's true on the very first step -- its terminal branch never
    sets self.reward (crashes with AttributeError) and never appends to
    self.actions_memory, so the model's real predicted action would be
    silently discarded even if it didn't crash. Duplicating today's row into
    a second day makes step() take the normal branch instead; since both
    days have identical prices, the resulting "return" for this throwaway
    step is exactly 0 (correct -- no time has actually passed), and
    PersonaPortfolioEnv.step()'s own post-processing (mask, cash policy,
    current_weights) is unaffected since it reads day 0's data before this
    step ever advances to day 1."""
    latest_date = processed['date'].max()
    today_df = processed[processed['date'] == latest_date].copy()
    day0 = today_df.copy()
    day0.index = [0] * len(day0)
    day1 = today_df.copy()
    day1.index = [1] * len(day1)
    return pd.concat([day0, day1]), latest_date
