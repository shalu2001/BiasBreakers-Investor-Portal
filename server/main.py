"""FastAPI service that serves the v14 behavioral portfolio model to the
Investor Portal frontend. Endpoint paths/shapes match what src/api/*.ts
already expects (built ahead of this backend existing)."""
import datetime as dt
import json
import os
import sys
import types
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stable_baselines3 import PPO

# Resolves because backend/gateway.py puts behavioural-simulation/backend on
# sys.path before importing this module. server/main.py is no longer
# independently runnable outside the gateway -- the recommendation feature
# now inherently depends on the portal's persona data, so that's accepted.
from portal.portal_auth import get_current_user_id
import portal.portal_db as portal_db

# finrl's own __init__.py unconditionally does `from finrl.{test,trade,train}
# import {test,trade,train}`, and those pull in unrelated broker/data-vendor
# SDKs (alpaca, wrds, yfinance, ...) that this service never uses -- only
# finrl.config.INDICATORS, FeatureEngineer, and StockPortfolioEnv are used
# below and in model_env.py. Stub the three submodules out before finrl is
# first imported so it loads without those optional extras installed.
for _name in ("test", "trade", "train"):
    _mod = types.ModuleType(f"finrl.{_name}")
    setattr(_mod, _name, None)
    sys.modules.setdefault(f"finrl.{_name}", _mod)

from finrl.config import INDICATORS

from model_env import PersonaPortfolioEnv, prepare_market_data, latest_day_frame, apply_live_bl_returns

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'behavioral_ppo_candidate_list_v14.zip')

# Population-mean "typical investor" values used throughout training
# (ALPHA_POP_MEAN/LAMBDA_POP_MEAN/GAMMA_POP_MEAN) -- the fallback for any
# investor who hasn't completed the behavioral game yet (no portal_profiles
# doc, or one with empty `parameters`), and for any Cosmos lookup failure.
POPULATION_MEAN_PERSONA = np.array([0.88, 2.25, 2.00])

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

    state["bl_returns"] = _fetch_bl_returns(tickers)


# Static snapshot the narrative/BL team drops here manually (same shape
# NarrativePredictionEngine.predict() itself returns:
# {"predictions": [{"ticker", "posterior", "prior", "tilt"}, ...]}) --
# not a live in-process call to their engine. That was tried first and
# reliably timed out in practice (Cosmos/OpenAI latency during their
# pipeline run), so this reads whatever they most recently exported instead.
# No live-refresh here yet -- read once at RL startup, same as the old
# live-call timing; re-upload the file and restart RL to pick up a refresh.
BL_PREDICTIONS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'narrative_engine', 'bl_predictions.json')
)


def _fetch_bl_returns(tickers) -> dict:
    """Black-Litterman posterior returns from BL_PREDICTIONS_PATH, mapped
    from narrative's short ticker form ('JKH') to RL's full suffixed form
    ('JKH.N0000') via RL's own already-loaded ticker list -- no extra
    Cosmos dependency needed. Any failure (file missing, malformed JSON,
    missing coverage) degrades to an empty dict, which downstream
    (apply_live_bl_returns) treats as all-zero/neutral, same as the
    disabled placeholder's semantics -- never blocks startup."""
    short_to_full = {t.split('.')[0]: t for t in tickers if '.' in t}
    try:
        with open(BL_PREDICTIONS_PATH, 'r') as f:
            data = json.load(f)
        bl_by_short = {
            p["ticker"]: p["posterior"]
            for p in data.get("predictions", [])
            if p.get("posterior") is not None
        }
    except FileNotFoundError:
        print(f"No BL predictions file at {BL_PREDICTIONS_PATH} yet, falling back to zeros.")
        bl_by_short = {}
    except Exception as e:
        print(f"Failed to read BL predictions from {BL_PREDICTIONS_PATH}, falling back to zeros: {e}")
        bl_by_short = {}

    bl_returns = {full: bl_by_short.get(short, 0.0) for short, full in short_to_full.items()}
    n_real = sum(1 for short in short_to_full if short in bl_by_short)
    print(f"BL returns: {n_real}/{len(short_to_full)} tickers have real coverage from {BL_PREDICTIONS_PATH}.")
    return bl_returns


def _get_profile_doc(uid: str) -> dict:
    """Single Cosmos lookup reused for both persona and existing-portfolio
    status below -- avoids two separate queries per recommendation request.
    Never raises: a Cosmos hiccup degrades to an empty doc (population-mean
    persona + no-existing-portfolio/initial-allocation framing), not a 500."""
    try:
        return portal_db.profiles().find_one({"user_id": uid}) or {}
    except Exception as e:
        print(f"Profile lookup failed for uid={uid}: {e}")
        return {}


def _persona_from_doc(doc: dict) -> np.ndarray:
    """Real fitted persona for this investor, or the population-mean
    fallback if they haven't completed the behavioral game yet (no
    `parameters` saved -- the default state set at registration)."""
    params = doc.get("parameters") or {}
    # Stored key is literally "lambda" (Mongo doc), not lambda_ (that's only
    # the Pydantic write-side alias in portal_routes.py).
    alpha, lam, gamma = params.get("alpha"), params.get("lambda"), params.get("gamma")
    if alpha is None or lam is None or gamma is None:
        return POPULATION_MEAN_PERSONA
    return np.array([float(alpha), float(lam), float(gamma)])


def _has_existing_portfolio(doc: dict) -> bool:
    """From the onboarding question ("do you already have a portfolio?").
    Defaults to False (initial-allocation framing, not a rebalance) if
    onboarding hasn't been completed or the question wasn't answered --
    safer than assuming a rebalance-from-existing-holdings framing without
    evidence."""
    onboarding = doc.get("onboarding") or {}
    return bool(onboarding.get("hasExistingPortfolio"))


def _existing_holdings_from_doc(doc: dict) -> dict | None:
    """{ticker: weightPct} from onboarding.existingHoldings, or None if the
    investor never entered any (they said "yes" to having a portfolio but
    skipped the holdings step, or this is an older account from before that
    step existed) -- None signals the caller to fall back to the uniform
    placeholder, distinct from an empty dict (which would mean "entered
    holdings, all zero" -- not the same thing)."""
    holdings = (doc.get("onboarding") or {}).get("existingHoldings")
    if not holdings:
        return None
    return {h["ticker"]: float(h["weightPct"]) for h in holdings if h.get("ticker") is not None}


def _run_recommendation(uid: str):
    tickers = state["tickers"]
    today_df, latest_date = latest_day_frame(state["processed"])
    today_df = apply_live_bl_returns(today_df, state["bl_returns"], tickers)
    stock_dim = len(tickers)

    doc = _get_profile_doc(uid)
    has_existing_portfolio = _has_existing_portfolio(doc)
    existing_holdings = _existing_holdings_from_doc(doc) if has_existing_portfolio else None

    env = PersonaPortfolioEnv(
        df=today_df,
        persona=_persona_from_doc(doc),
        is_training=False,
        tickers=tickers,
        state_space=stock_dim,
        stock_dim=stock_dim,
        action_space=stock_dim,
        **ENV_KWARGS_BASE,
    )
    obs, _ = env.reset()
    # reset() seeds current_weights uniformly across this persona's eligible
    # (mask-passing) tickers -- there's no real per-ticker position source
    # wired up (see onboarding), so this uniform baseline is the best
    # available proxy for "current holdings" and is what the model itself
    # was trained against as its reset-time observation input -- kept
    # unchanged here regardless of has_existing_portfolio below, so the
    # model's own prediction isn't affected by that branch, only the
    # DISPLAYED currentPct is.
    current_weights = env.current_weights.copy()

    raw_action, _ = state["model"].predict(obs, deterministic=True)
    env.step(raw_action)
    recommended_weights = env.current_weights

    rows = []
    for i, ticker in enumerate(tickers):
        if existing_holdings is not None:
            # Real holdings the investor entered during onboarding/account
            # settings -- 0 for anything they didn't list. Independent of
            # current_weights (the model's own internal reset-time baseline,
            # unaffected by any of this -- see the comment above reset()).
            current_pct = round(existing_holdings.get(ticker, 0.0))
        elif has_existing_portfolio:
            # Said "yes" but never entered real holdings (skipped the step,
            # or an older account from before it existed) -- fall back to
            # the uniform-eligible-tickers placeholder.
            current_pct = round(float(current_weights[i]) * 100)
        else:
            # No existing portfolio -- initial allocation, nothing to
            # rebalance from.
            current_pct = 0
        rows.append({
            "ticker": ticker,
            "name": TICKER_NAMES.get(ticker, ticker),
            "currentPct": current_pct,
            "recommendedPct": round(float(recommended_weights[i]) * 100),
        })

    # Only the selected tickers -- most of the universe gets masked out to 0%
    # by the persona-based candidate ranking (or, for no-existing-portfolio
    # investors, currentPct is always 0), so showing all ~20 rows is mostly
    # noise. A ticker earns a row by being currently held OR recommended.
    rows = [row for row in rows if row["currentPct"] > 0 or row["recommendedPct"] > 0]

    _save_recommendation(uid, latest_date, rows)
    return rows, latest_date


def _save_recommendation(uid: str, latest_date, rows: list):
    """Upsert (not insert-always) keyed on (user_id, date) -- one document
    per investor per day, so repeated page loads on the same day don't
    accumulate duplicates. Never raises: a Cosmos write failure shouldn't
    break an already-successfully-computed recommendation response."""
    try:
        date_str = latest_date.strftime("%Y-%m-%d")
        portal_db.recommendations().update_one(
            {"user_id": uid, "date": date_str},
            {"$set": {
                "user_id": uid,
                "date": date_str,
                "rows": rows,
                "created_at": dt.datetime.utcnow(),
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"Failed to persist recommendation for uid={uid}: {e}")


def _synthesize_description(rows: list) -> str:
    """Best-effort human-readable summary from the largest allocation
    deltas -- a placeholder stand-in, not a real narrative description."""
    moved = [r for r in rows if r["recommendedPct"] != r["currentPct"]]
    if not moved:
        return "No changes recommended."
    moved.sort(key=lambda r: abs(r["recommendedPct"] - r["currentPct"]), reverse=True)
    parts = []
    for r in moved[:2]:
        diff = r["recommendedPct"] - r["currentPct"]
        verb = "Increase" if diff > 0 else "Reduce"
        parts.append(f"{verb} {r['ticker']} ({diff:+d}%)")
    return ", ".join(parts)


PORTFOLIO_RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}


def _candles_for_range(processed: pd.DataFrame, ticker: str, latest_date, range_key: str) -> list:
    """Real daily OHLC for one ticker over the requested lookback window,
    sliced from the same processed market data the RL model itself uses --
    not fabricated. Defaults to the 3M window's day count for an
    unrecognized range_key rather than erroring on a minor request mismatch."""
    days = PORTFOLIO_RANGE_DAYS.get(range_key, PORTFOLIO_RANGE_DAYS["3M"])
    start_date = latest_date - pd.Timedelta(days=days)
    sub = processed[
        (processed["tic"] == ticker) & (processed["date"] >= start_date) & (processed["date"] <= latest_date)
    ].sort_values("date")
    return [
        {
            "time": row.date.strftime("%Y-%m-%d"),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for row in sub.itertuples()
    ]


def _change_pct(candles: list) -> float:
    if len(candles) < 2 or candles[0]["close"] == 0:
        return 0.0
    first, last = candles[0]["close"], candles[-1]["close"]
    return round((last - first) / first * 100, 2)


@app.get("/portfolio/holdings")
def get_portfolio_holdings(range: str = "3M", uid: str = Depends(get_current_user_id)):
    """Reuses _run_recommendation() entirely rather than re-deriving the
    current/no-existing-portfolio fallback logic here -- guarantees this
    page shows the exact same weights as /recommend, not a second
    independently-computed version that could drift out of sync. Per your
    call: no-existing-portfolio investors see the model's recommended
    allocation here (not raw currentPct, which is always 0 for them) --
    more in keeping with a behavioral-finance app than showing generic
    "top performers" would be. CASH is excluded (no candlestick chart for
    it). `sector` is not backed by real data yet -- left blank rather than
    invented."""
    rows, latest_date = _run_recommendation(uid)
    processed = state["processed"]

    result = []
    for row in rows:
        ticker = row["ticker"]
        if ticker == "CASH":
            continue
        candles = _candles_for_range(processed, ticker, latest_date, range)
        result.append({
            "ticker": ticker,
            "name": row["name"],
            "sector": "",
            "weightPct": row["currentPct"] if row["currentPct"] > 0 else row["recommendedPct"],
            "changePct": _change_pct(candles),
            "candles": candles,
        })
    return result


@app.get("/universe")
def get_universe():
    """The real tracked ticker universe (name-mapped, CASH excluded -- it's
    not a stock an investor would report "holding"), for the onboarding
    existing-holdings picker so it doesn't have to hardcode/guess at the
    S&P SL20 constituent list. No auth needed -- not investor-specific."""
    return [
        {"ticker": t, "name": TICKER_NAMES.get(t, t)}
        for t in state["tickers"] if t != "CASH"
    ]


@app.get("/recommendation/current")
def get_recommendation(uid: str = Depends(get_current_user_id)):
    rows, latest_date = _run_recommendation(uid)
    return rows


@app.get("/recommendation/history")
def get_recommendation_history(uid: str = Depends(get_current_user_id)):
    docs = portal_db.recommendations().find({"user_id": uid}).sort("date", -1).limit(50)
    return [
        {
            "date": d["date"],
            "description": _synthesize_description(d["rows"]),
            # Not yet correlated to /recommendation/feedback -- that would
            # need feedback to reference which recommendation it's rating
            # and persist that back here, not built yet.
            "rating": None,
        }
        for d in docs
    ]


@app.post("/recommendation/feedback")
def submit_feedback(payload: dict, uid: str = Depends(get_current_user_id)):
    # TODO: persist and feed back into the training loop. For now just
    # accept it so the frontend's feedback flow doesn't error out.
    print(f"Received recommendation feedback from {uid}: {payload}")
    return {"status": "received"}
