"""FastAPI service that serves the v14 behavioral portfolio model to the
Investor Portal frontend. Endpoint paths/shapes match what src/api/*.ts
already expects (built ahead of this backend existing)."""
import os
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stable_baselines3 import PPO
from finrl.config import INDICATORS

from model_env import PersonaPortfolioEnv, prepare_market_data, latest_day_frame

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'behavioral_ppo_candidate_list_v14.zip')

# TODO: persona should come from a teammate's behavioral-profiling module
# (risk_aversion/loss_aversion/regret_aversion per investor). Hardcoded to
# the population-mean "typical investor" values used throughout training
# (ALPHA_POP_MEAN/LAMBDA_POP_MEAN/GAMMA_POP_MEAN) until that's wired up.
PLACEHOLDER_PERSONA = np.array([0.88, 2.25, 2.00])

# Best-effort ticker -> display name. Fill in the rest of the S&P SL20
# constituents as they come up; falls back to the raw ticker otherwise.
TICKER_NAMES = {
    'JKH.N0000': 'John Keells Holdings',
    'COMB.N0000': 'Commercial Bank',
    'LOLC.N0000': 'LOLC Holdings',
    'DIAL.N0000': 'Dialog Axiata',
    'HHL.N0000': 'Hemas Holdings',
    'SAMP.N0000': 'Sampath Bank',
    'CASH': 'Cash',
}

ENV_KWARGS_BASE = {
    "hmax": 100,
    "initial_amount": 1_000_000,
    "transaction_cost_pct": 0.001,
    "tech_indicator_list": INDICATORS + ['sl20_proxy_return'],
    "reward_scaling": 1e-4,
    "financial_mode": 'log_return',
    "vol_window": 20,
    "risk_penalty_alpha": 1.0,
    "dsr_eta": 0.01,
    "w_fin": 1.0,
    "w_behavioral": 0.5,
    "w_risk": 0.3,
    "w_fit": 2.0,
    "reward_scale": 1.0,
}

app = FastAPI(title="BiasBreakers Investor Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

state = {}


@app.on_event("startup")
def load_model_and_data():
    """Both the model and the market-data pipeline are expensive to load
    (Azure pull + feature engineering can take a while) -- doing this once
    at startup, not per-request, is why this is a long-running service
    rather than a script invoked fresh each time."""
    print("Loading model...")
    state["model"] = PPO.load(MODEL_PATH)

    print("Preparing market data (Azure pull + feature engineering)...")
    processed, df_returns, tickers = prepare_market_data()
    state["processed"] = processed
    state["tickers"] = tickers
    print(f"Ready. {len(tickers)} tickers, data through {processed['date'].max()}.")


def _run_recommendation():
    tickers = state["tickers"]
    today_df, latest_date = latest_day_frame(state["processed"])
    stock_dim = len(tickers)

    env = PersonaPortfolioEnv(
        df=today_df,
        persona=PLACEHOLDER_PERSONA,
        is_training=False,
        tickers=tickers,
        state_space=stock_dim,
        stock_dim=stock_dim,
        action_space=stock_dim,
        **ENV_KWARGS_BASE,
    )
    obs, _ = env.reset()
    # reset() seeds current_weights uniformly across this persona's eligible
    # (mask-passing) tickers -- used as the "current holdings" baseline
    # since there's no real position source wired up yet (see onboarding).
    current_weights = env.current_weights.copy()

    raw_action, _ = state["model"].predict(obs, deterministic=True)
    env.step(raw_action)
    recommended_weights = env.current_weights

    rows = []
    for i, ticker in enumerate(tickers):
        rows.append({
            "ticker": ticker,
            "name": TICKER_NAMES.get(ticker, ticker),
            "currentPct": round(float(current_weights[i]) * 100),
            "recommendedPct": round(float(recommended_weights[i]) * 100),
        })

    return rows, latest_date


@app.get("/recommendation/current")
def get_recommendation():
    rows, latest_date = _run_recommendation()
    return rows


@app.get("/recommendation/history")
def get_recommendation_history():
    # TODO: no persisted history yet -- feedback submitted via
    # /recommendation/feedback below isn't stored anywhere yet either.
    return []


@app.post("/recommendation/feedback")
def submit_feedback(payload: dict):
    # TODO: persist and feed back into the training loop. For now just
    # accept it so the frontend's feedback flow doesn't error out.
    print(f"Received recommendation feedback: {payload}")
    return {"status": "received"}
