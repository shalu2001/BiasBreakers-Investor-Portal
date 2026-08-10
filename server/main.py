"""FastAPI service that serves the v15 behavioral portfolio model to the
Investor Portal frontend. Endpoint paths/shapes match what src/api/*.ts
already expects (built ahead of this backend existing)."""
import datetime as dt
import glob
import json
import os
import sys
import types
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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

# For real ticker -> company name lookup (state["ticker_names"], populated
# at startup below) -- narrative_engine already loads this exact mapping
# from Cosmos for its own ticker resolution, so it's reused here rather
# than maintaining a second, inevitably-incomplete hardcoded list.
from narrative_engine.config import get_settings as get_narrative_settings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.data.ticker_info_repository import TickerInfoRepository

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'behavioral_ppo_candidate_list_v15.zip')

# Population-mean "typical investor" values used throughout training
# (ALPHA_POP_MEAN/LAMBDA_POP_MEAN/GAMMA_POP_MEAN) -- the fallback for any
# investor who hasn't completed the behavioral game yet (no portal_profiles
# doc, or one with empty `parameters`), and for any Cosmos lookup failure.
POPULATION_MEAN_PERSONA = np.array([0.88, 2.25, 2.00])

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
    state["bl_returns_date"] = dt.date.today()
    state["ticker_names"] = _fetch_ticker_names()


TICKER_NAMES_TIMEOUT_SECONDS = 30


def _load_ticker_reference():
    settings = get_narrative_settings()
    connection = MongoConnection(settings)
    try:
        return TickerInfoRepository(connection, settings).load()
    finally:
        connection.close()


def _fetch_ticker_names() -> dict:
    """Real S&P SL20 company names from narrative_engine's authoritative
    Ticker_Info Cosmos collection (the exact same source narrative uses for
    its own ticker resolution) -- replaces what used to be a hardcoded,
    always-incomplete 6-of-20 map. A single Cosmos query here is far
    lighter than narrative's full predict() pipeline, but any network call
    has proven unreliable enough in this environment (see
    BL_FETCH_TIMEOUT_SECONDS above) to still need a bounded timeout rather
    than trusting it to fail cleanly on its own. Any failure or timeout
    degrades to an empty dict, so callers just fall back to showing raw
    ticker codes -- same behavior as the old dict's default, just now
    populated for everything when it works instead of only 6 tickers."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_load_ticker_reference)
        reference = future.result(timeout=TICKER_NAMES_TIMEOUT_SECONDS)
        names = dict(reference.ticker_to_company)
    except FutureTimeoutError:
        print(f"Ticker name lookup timed out after {TICKER_NAMES_TIMEOUT_SECONDS}s, using raw ticker codes.")
        names = {}
    except Exception as e:
        print(f"Ticker name lookup failed, using raw ticker codes: {e}")
        names = {}
    finally:
        pool.shutdown(wait=False)

    names["CASH"] = "Cash"  # synthetic, never in the real ticker-info collection
    print(f"Ticker names: {len(names) - 1} real company names loaded.")
    return names


# narrative_engine's own on-disk prediction cache -- every successful
# POST /predict on the narrative service writes here (see
# narrative_engine/api/app.py's _write_response_cache), one file per
# (as_of date, lookback_days, macro mode). Reading straight from here keeps
# RL in sync with whatever narrative has actually computed, instead of the
# older bl_predictions.json below, which had to be manually re-exported and
# dropped in by hand.
NARRATIVE_CACHE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'narrative_engine', 'cache')
)

# Manually-dropped fallback snapshot (same {"predictions": [...]} shape) from
# before the cache directory existed -- kept as a last resort for a fresh
# checkout where narrative has never run yet.
BL_PREDICTIONS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'narrative_engine', 'bl_predictions.json')
)


def _latest_bl_cache_path() -> str | None:
    """Freshest narrative_engine/cache/prediction_<date>_<lookback>d_<mode>.json
    at or before today, for the lookback/macro settings narrative is
    currently configured with. Dated at-or-before-today (not "closest
    overall") so this never picks up a stray future-dated file and always
    reflects what narrative actually knew as of today -- there's no
    guarantee today's own file has landed yet (the pipeline runs on its own
    schedule), so this falls back to the most recent earlier day rather than
    requiring an exact match."""
    settings = get_narrative_settings()
    macro = "macro" if settings.use_macro_overrides else "nomacro"
    pattern = os.path.join(NARRATIVE_CACHE_DIR, f"prediction_*_{settings.lookback_days}d_{macro}.json")
    today_str = dt.date.today().isoformat()

    dated_paths = []
    for path in glob.glob(pattern):
        name = os.path.basename(path)
        date_part = name[len("prediction_"):len("prediction_") + 10]  # YYYY-MM-DD
        if date_part <= today_str:
            dated_paths.append((date_part, path))

    if not dated_paths:
        return None
    dated_paths.sort(key=lambda pair: pair[0])
    return dated_paths[-1][1]


def _fetch_bl_returns(tickers) -> dict:
    """Black-Litterman posterior returns for today, sourced from narrative's
    prediction cache (falling back to the static BL_PREDICTIONS_PATH export
    if the cache has nothing yet). RL's own tickers are already the same
    short form narrative uses ('JKH', not a '.N0000'-suffixed variant --
    confirmed via GET /universe against the live data), so this is a direct
    ticker-string match, no format conversion needed. CASH is excluded --
    narrative never has a BL view on cash itself. Any failure (no cache file,
    malformed JSON, missing coverage) degrades to an empty dict, which
    downstream (apply_live_bl_returns) treats as all-zero/neutral rather than
    blocking a request."""
    real_tickers = [t for t in tickers if t != "CASH"]
    source_path = _latest_bl_cache_path() or BL_PREDICTIONS_PATH
    try:
        with open(source_path, 'r') as f:
            data = json.load(f)
        bl_by_ticker = {
            p["ticker"]: p["posterior"]
            for p in data.get("predictions", [])
            if p.get("posterior") is not None
        }
    except FileNotFoundError:
        print(f"No BL predictions found at {source_path} yet, falling back to zeros.")
        bl_by_ticker = {}
    except Exception as e:
        print(f"Failed to read BL predictions from {source_path}, falling back to zeros: {e}")
        bl_by_ticker = {}

    bl_returns = {t: bl_by_ticker.get(t, 0.0) for t in real_tickers}
    n_real = sum(1 for t in real_tickers if t in bl_by_ticker)
    print(f"BL returns: {n_real}/{len(real_tickers)} tickers have real coverage from {source_path}.")
    return bl_returns


def _current_bl_returns(tickers) -> dict:
    """Re-resolves the BL cache file whenever the calendar day has rolled
    over since the last fetch, so a long-running RL process picks up each
    new day's narrative snapshot without needing a restart. A no-op state
    check on every other request in the same day."""
    today = dt.date.today()
    if state.get("bl_returns_date") != today:
        state["bl_returns"] = _fetch_bl_returns(tickers)
        state["bl_returns_date"] = today
    return state["bl_returns"]


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
    """{ticker: shares} from onboarding.existingHoldings, or None if the
    investor never entered any (they said "yes" to having a portfolio but
    skipped the holdings step, or this is an older account from before that
    step existed) -- None signals the caller to fall back to the uniform
    placeholder, distinct from an empty dict (which would mean "entered
    holdings, holds nothing" -- not the same thing). Real share counts, not
    a self-reported percentage -- value/pct are derived from this plus the
    current price, not asked for directly (avoids the investor having to do
    that math themselves, and avoids a self-reported value silently
    disagreeing with the share count if the price has moved)."""
    holdings = (doc.get("onboarding") or {}).get("existingHoldings")
    if not holdings:
        return None
    return {h["ticker"]: float(h["shares"]) for h in holdings if h.get("ticker") is not None}


def _investment_amount_from_doc(doc: dict) -> float | None:
    """From the onboarding "how much are you planning to invest?" question.
    None if never set (or a non-positive/garbage value) -- callers use this
    to decide whether to compute a share quantity at all, rather than
    showing a meaningless number derived from a missing budget."""
    amount = (doc.get("onboarding") or {}).get("investmentAmount")
    return float(amount) if amount is not None and amount > 0 else None


def _quantity(pct: float, investment_amount: float | None, price: float | None) -> int | None:
    """Whole shares this pct of the investor's stated budget would buy at
    the given price -- None (not 0) when we don't have enough to compute a
    real number (no budget set, no price for this ticker (CASH), or a
    non-positive price), so the frontend can distinguish "unknown" from
    "literally zero shares". Rounds down: a fractional remainder becomes
    leftover cash, same as any real brokerage order would leave -- not
    fabricating fractional-share support the CSE may not actually offer."""
    if investment_amount is None or price is None or price <= 0:
        return None
    return int((pct / 100 * investment_amount) // price)


def _value(pct: float, investment_amount: float | None) -> float | None:
    """LKR value this pct of the investor's stated budget represents. None
    (not 0) when there's no budget to compute it from."""
    if investment_amount is None:
        return None
    return round(pct / 100 * investment_amount)


def _run_recommendation(uid: str):
    tickers = state["tickers"]
    today_df, latest_date = latest_day_frame(state["processed"])
    today_df = apply_live_bl_returns(today_df, _current_bl_returns(tickers), tickers)
    stock_dim = len(tickers)

    doc = _get_profile_doc(uid)
    has_existing_portfolio = _has_existing_portfolio(doc)
    existing_holdings = _existing_holdings_from_doc(doc) if has_existing_portfolio else None
    # Real current close price per ticker, for converting pct -> share
    # quantity. today_df has 2 rows per ticker (latest_day_frame's day0/day1
    # duplication) with identical close values, so this just overwrites
    # each ticker's entry with the same price twice -- harmless.
    prices = dict(zip(today_df["tic"], today_df["close"]))

    if existing_holdings is not None:
        # Real shares entered -- the budget for a rebalance is naturally
        # whatever their current holdings are already worth, so onboarding
        # doesn't separately ask "how much are you investing" for these
        # investors; it's derived, not collected.
        total_value = sum(
            shares * prices[t] for t, shares in existing_holdings.items() if prices.get(t)
        )
        investment_amount = total_value if total_value > 0 else None
    else:
        # No real holdings to derive a total from (no existing portfolio, or
        # said yes but skipped the holdings step) -- fall back to the
        # separately-asked onboarding budget.
        investment_amount = _investment_amount_from_doc(doc)

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

    # Real per-ticker share counts only count as "real" if we also have a
    # budget to price them against -- without investment_amount there's no
    # denominator to turn shares into a %, so that combination falls back to
    # the uniform placeholder below, same as "said yes but entered nothing".
    have_real_shares = existing_holdings is not None and investment_amount is not None

    rows = []
    for i, ticker in enumerate(tickers):
        # No share-quantity/price concept for cash itself.
        price = None if ticker == "CASH" else prices.get(ticker)

        if have_real_shares:
            # 0 for anything they didn't list -- distinct from never having
            # entered holdings at all (have_real_shares would be False then).
            shares_held = existing_holdings.get(ticker, 0.0)
            current_value = round(shares_held * price) if price else 0.0
            current_pct = round(current_value / investment_amount * 100)
            # No share-quantity concept for cash -- None (not a possibly-
            # nonzero share count someone could have entered against it, and
            # not the misleading 0 that int(shares_held) would give here).
            current_qty = None if ticker == "CASH" else int(shares_held)
        elif has_existing_portfolio:
            # Said "yes" but never entered real holdings (skipped the step,
            # or an older account from before it existed), or entered
            # holdings but no budget to price them against -- fall back to
            # the uniform-eligible-tickers placeholder. Independent of
            # current_weights (the model's own internal reset-time baseline,
            # unaffected by any of this -- see the comment above reset()).
            current_pct = round(float(current_weights[i]) * 100)
            current_value = _value(current_pct, investment_amount)
            current_qty = _quantity(current_pct, investment_amount, price)
        else:
            # No existing portfolio -- initial allocation, nothing to
            # rebalance from.
            current_pct = 0
            current_value = _value(current_pct, investment_amount)
            current_qty = _quantity(current_pct, investment_amount, price)

        recommended_pct = round(float(recommended_weights[i]) * 100)
        rows.append({
            "ticker": ticker,
            "name": state["ticker_names"].get(ticker, ticker),
            "currentPct": current_pct,
            "recommendedPct": recommended_pct,
            "currentValue": current_value,
            "recommendedValue": _value(recommended_pct, investment_amount),
            "currentQty": current_qty,
            "recommendedQty": _quantity(recommended_pct, investment_amount, price),
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
    candles = [
        {
            "time": row.date.strftime("%Y-%m-%d"),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for row in sub.itertuples()
    ]
    # The underlying Cosmos data is end-of-day only -- open always equals
    # close on every row, not genuine intraday OHLC. Since the chart colors
    # a candle green whenever close >= open, that made every single candle
    # trivially green regardless of real price movement (open == close is
    # always ">="), never red. Re-pointing each day's open at the PREVIOUS
    # day's close is the standard fix for daily-close-only data: the color
    # then reflects whether today's close beat yesterday's, which is what
    # "up/down day" actually means for EOD data. First candle in the
    # window keeps its own (open == close) value -- there's no prior day
    # in range to compare it against.
    for i in range(len(candles) - 1, 0, -1):
        candles[i]["open"] = candles[i - 1]["close"]
        # high/low were computed as a band around the day's own (old)
        # open==close value, so a prior close that gapped past that band
        # would otherwise sit outside the wick -- clamp so open is always
        # visually inside [low, high], same as any real candle guarantees.
        candles[i]["high"] = max(candles[i]["high"], candles[i]["open"])
        candles[i]["low"] = min(candles[i]["low"], candles[i]["open"])
    return candles


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


@app.get("/portfolio/candles")
def get_portfolio_candles(tickers: str, range: str = "3M", uid: str = Depends(get_current_user_id)):
    """Real OHLC candles for an explicit, caller-supplied set of tickers --
    the ones the investor's last approved recommendation actually selected
    (see GET /recommendation/current), not a fresh recomputation. Unlike
    /portfolio/holdings, this never calls _run_recommendation(): the
    Portfolio page should render exactly the allocation the investor already
    saw and approved on /recommend, not silently re-run the optimizer (and
    re-upsert a new saved recommendation, possibly with different weights if
    a day boundary or narrative refresh happened in between) just to draw a
    chart. `uid` is required only to keep this behind auth like every other
    investor-specific endpoint -- the response itself doesn't depend on it.
    Unknown/CASH tickers are silently skipped rather than erroring, since
    the caller-supplied list already comes from the investor's own saved
    recommendation."""
    processed = state["processed"]
    latest_date = processed["date"].max()
    requested = [t.strip() for t in tickers.split(",") if t.strip()]

    result = []
    for ticker in requested:
        if ticker == "CASH" or ticker not in state["tickers"]:
            continue
        candles = _candles_for_range(processed, ticker, latest_date, range)
        result.append({
            "ticker": ticker,
            "name": state["ticker_names"].get(ticker, ticker),
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
        {"ticker": t, "name": state["ticker_names"].get(t, t)}
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
