from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import pandas as pd
import math
import uuid

from game.multi_block_session import MultiBlockSession
from estimation.final_estimator import fit_full_profile
from estimation.estimator_v2 import fit_profile_v2
from estimation.calibration import load_default_calibrator, features_from_fits
from game.event_round import EventRound
from reward.behavioral_reward_interface import BehavioralRewardModel

CALIBRATOR = load_default_calibrator()   # simulation-based inverse map; None if unavailable

app = FastAPI(title="Behavioral Trading Simulator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Portal auth + profile API (Cosmos-backed). Mounted defensively so the game
# engine still runs even if the DB / .env isn't configured on this machine.
try:
    from portal.portal_routes import router as portal_router
    app.include_router(portal_router)

    @app.on_event("startup")
    def _portal_startup():
        try:
            import portal.portal_db as portal_db
            portal_db.ensure_indexes()
            print("[portal] Cosmos collections ready (portal_users, portal_profiles)")
        except Exception as e:
            print("[portal] DB not initialised (portal routes will 500 until .env is set):", e)
except Exception as e:  # pragma: no cover
    print("[portal] portal routes unavailable:", e)

SESSIONS = {}
EVENT_ROUNDS = {}                          # session_id -> EventRound (matched-stakes lambda round)
BASE_DIR = Path(__file__).resolve().parent
SCENARIO_NAMES = ["2021_bull_run", "2022_crash", "2023_recovery"]

class AllocationRequest(BaseModel):
    ticker: str | None = None
    target_pct: float

class CommitRequest(BaseModel):
    fraction: float

def _load_all_scenarios():
    data = {}
    for name in SCENARIO_NAMES:
        base = BASE_DIR / "scenario_build" / name
        stocks = pd.read_csv(f"{base}_stocks.csv", parse_dates=["Date"])
        index = pd.read_csv(f"{base}_index.csv", parse_dates=["Date"])
        data[name] = (stocks, index)
    return data

def _sanitize(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

def _get_session(session_id):
    if session_id not in SESSIONS:
        raise HTTPException(404, "Session not found or already finished")
    return SESSIONS[session_id]

def _round_label(session):
    return "Fund A" if session.block == "loss_aversion" else "Fund B"

def _benchmark(session):
    """The S&P SL20 regret signal, exactly as the estimator reads it at a checkpoint:
    today's index move vs the move of the stock the player is actually holding
    (market_gap = index_return - held_return; positive => the market ran ahead of you).

    Surfaced so the player can perceive the very gap gamma is fitted on. Only shown in
    the regret block (Fund B) -- Fund A deliberately has no benchmark, to keep the
    loss-aversion read uncontaminated."""
    cs = session.current_session
    idx = cs.get_index_return()
    held = cs.held_stock_return()
    holding = any(q > 0 for q in cs.holdings.values())
    return {
        "index_return": round(idx, 2),
        "held_return": round(held, 2),
        "market_gap": round(idx - held, 2),
        "in_cash": not holding,
        "show": session.get_tradable_ticker() is not None,   # True only in the regret fund
    }

@app.post("/session/create")
def create_session(starting_cash: float = 1_000_000):
    scenario_data = _load_all_scenarios()
    session = MultiBlockSession(scenario_data, starting_cash, n_per_bin=2)
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = session
    return {
        "session_id": session_id,
        "round_label": _round_label(session),
        "day": session.current_session.get_day_number(),
        "total_days": session.current_session.get_total_days(),
        "market_state": _sanitize(session.get_market_state()),
        "cash": session.current_session.cash,
        "fixed_ticker": session.get_tradable_ticker(),
        "benchmark": _benchmark(session),
    }

@app.get("/session/{session_id}/state")
def get_state(session_id: str):
    session = _get_session(session_id)
    return {
        "round_label": _round_label(session),
        "day": session.current_session.get_day_number(),
        "total_days": session.current_session.get_total_days(),
        "market_state": _sanitize(session.get_market_state()),
        "cash": session.current_session.cash,
        "holdings": session.current_session.holdings,
        "equity": session.current_session.total_equity(),
        "fixed_ticker": session.get_tradable_ticker(),
        "benchmark": _benchmark(session),
    }

@app.get("/session/{session_id}/history/{ticker}")
def get_history(session_id: str, ticker: str, lookback: int = 15):
    session = _get_session(session_id)
    return {"history": session.current_session.get_recent_history(ticker, lookback)}

@app.post("/session/{session_id}/allocate")
def allocate(session_id: str, req: AllocationRequest):
    session = _get_session(session_id)
    print(f"\n[ALLOCATE] session={session_id[:8]} block={session.block} ticker={req.ticker} target_pct={req.target_pct}")
    record = session.set_allocation(req.ticker, req.target_pct)
    print(f"  -> wealth_change={record['wealth_change']:.2f}, market_gap={record['market_gap']}")
    return _sanitize({k: (str(v) if hasattr(v, "isoformat") else v) for k, v in record.items()})

@app.post("/session/{session_id}/advance")
def advance(session_id: str):
    session = _get_session(session_id)
    result = session.advance()
    print(f"[ADVANCE] status={result['status']} block={session.block} scenario_idx={session.scenario_idx}")
    if "date" in result:
        del result["date"]
    if result.get("status") in ("at_checkpoint", "new_scenario_started", "new_block_started"):
        result["round_label"] = _round_label(session)
        result["day"] = session.current_session.get_day_number()
        result["total_days"] = session.current_session.get_total_days()
        result["benchmark"] = _benchmark(session)
    # After the two free-play blocks, launch the matched-stakes event round
    # (which cleanly identifies loss aversion) instead of finishing.
    if result.get("status") == "all_blocks_complete":
        er = EventRound(n_events=16)
        EVENT_ROUNDS[session_id] = er
        result = {"status": "events_started", "event": er.current(), "total_events": er.total()}
    return _sanitize(result)

@app.get("/session/{session_id}/event")
def get_event(session_id: str):
    er = EVENT_ROUNDS.get(session_id)
    if er is None:
        raise HTTPException(404, "No event round for this session")
    return _sanitize({"event": er.current(), "total_events": er.total(), "complete": er.is_complete()})

@app.post("/session/{session_id}/event/commit")
def commit_event(session_id: str, req: CommitRequest):
    er = EVENT_ROUNDS.get(session_id)
    if er is None:
        raise HTTPException(404, "No event round for this session")
    res = er.commit(req.fraction)
    print(f"[EVENT] session={session_id[:8]} committed={req.fraction:.2f} -> {res['status']}")
    return _sanitize(res)

@app.get("/session/{session_id}/log")
def get_log(session_id: str):
    session = _get_session(session_id)
    log1, log2 = session.get_block_logs()
    combined = pd.concat([log1, log2], ignore_index=True) if not log1.empty or not log2.empty else pd.DataFrame()
    if combined.empty:
        return {"log": []}
    records = combined.to_dict("records")
    for r in records:
        r["date"] = str(r["date"])
    return {"log": _sanitize(records)}

@app.post("/session/{session_id}/finish")
def finish_session(session_id: str):
    session = _get_session(session_id)
    log1, log2 = session.get_block_logs()

    print("\n" + "="*60)
    print("ROUND 1 (loss-aversion) FULL LOG:")
    print(log1[["date","ticker","target_pct","wealth_change","market_gap"]].to_string(index=False))
    print("\nROUND 2 (regret) FULL LOG:")
    print(log2[["date","ticker","target_pct","wealth_change","market_gap"]].to_string(index=False))
    print("="*60)

    # Legacy free-form MLE fit (kept for comparison / backward compatibility).
    fit = fit_full_profile(log1, log2, starting_equity=session.starting_cash)

    # Robust estimate: alpha fixed at 0.88, decoupled lambda, improved gamma,
    # plus per-parameter confidence flags. This is the profile we now report.
    v2 = fit_profile_v2(log1, log2, starting_equity=session.starting_cash)

    # Simulation-based calibration: map the raw feature vector back to the true
    # (alpha, lambda, gamma). This is what recovers alpha (raw estimate is inverted)
    # and sharpens lambda/gamma. Falls back to the v2 point estimates if the
    # calibrator or its training data is unavailable.
    if CALIBRATOR is not None:
        feats = features_from_fits(fit["raw"], v2)
        cal = CALIBRATOR.calibrate(feats)
        profile = {"alpha": cal["alpha"], "lambda": cal["lambda"], "gamma": cal["gamma"]}
        profile_source = f"calibrated ({cal['backend']})"
    else:
        # POLICY: the reward function always receives the ACTUAL COMPUTED estimate.
        # A low-confidence flag never suppresses or overwrites the value -- it is
        # reported alongside (see `confidence` below) so downstream can weight it,
        # but the number handed over is still the one we measured. The 2.25 prior
        # is a LAST RESORT used only when lambda is literally uncomputable (None,
        # e.g. a degenerate regression with no usable variation) -- not when it is
        # merely low-confidence.
        LAMBDA_LAST_RESORT_PRIOR = 2.25   # T-K (1992) population median; flagged if used
        lam_computed = v2["lambda"]
        profile = {"alpha": v2["alpha"],
                   "lambda": lam_computed if lam_computed is not None else LAMBDA_LAST_RESORT_PRIOR,
                   "gamma": v2["gamma"]}
        profile_source = "v2_uncalibrated" if lam_computed is not None else "v2_uncalibrated+lambda_prior"

    confidence = {k: dict(v) for k, v in v2["confidence"].items()}
    free_play_lambda = profile["lambda"]   # before any event-round override

    # Matched-stakes event round: cleanly identifies lambda regardless of the
    # player's free-play style. When available and confident, it OVERRIDES the
    # free-play lambda (alpha and gamma still come from the calibration).
    er = EVENT_ROUNDS.pop(session_id, None)
    event_lambda = None
    lambda_source = "free_play_calibration"
    if er is not None:
        el = er.estimate_lambda()
        if el is not None and el.get("estimate") is not None:
            event_lambda = float(el["estimate"])
            if el["confidence"]["level"] != "uninformative":
                profile["lambda"] = event_lambda
                confidence["lambda"] = el["confidence"]
                lambda_source = "matched_stakes_events"

    _conf_levels = {k: v["level"] for k, v in confidence.items()}
    print("FINAL profile:", {k: round(v, 3) for k, v in profile.items()},
          "| source:", profile_source, "| lambda_source:", lambda_source, "| confidence:", _conf_levels)

    # Reward model handed to the RL side uses the calibrated parameters directly.
    reward_model = BehavioralRewardModel(
        raw_alpha=profile["alpha"], raw_lambda=profile["lambda"], raw_gamma=profile["gamma"],
        starting_equity=session.starting_cash, apply_calibration=False,
    )
    del SESSIONS[session_id]

    def _f(x):
        return None if x is None else float(x)

    return {
        # primary result -- calibrated profile (lambda from events when available)
        "profile": {k: _f(v) for k, v in profile.items()},
        "profile_source": profile_source,
        "lambda_source": lambda_source,
        "confidence": confidence,
        "n_obs_block1": fit["n_obs_block1"],
        "n_obs_block2": fit["n_obs_block2"],
        # diagnostics / legacy (kept so nothing downstream breaks)
        "event_lambda": _f(event_lambda),
        "free_play_lambda": _f(free_play_lambda),
        "v2_estimate": {"alpha": v2["alpha"], "lambda": _f(v2["lambda"]), "gamma": v2["gamma"]},
        "raw_estimate": fit["raw"],
        "calibration_validated": False,
    }