"""
Automated persona bots for sanity-testing the trading simulator.
Run this while your FastAPI server (`uvicorn app:app --reload`) is running.

Usage:
    python persona_bot.py loss_averse
    python persona_bot.py loss_tolerant
    python persona_bot.py fomo_chaser
    python persona_bot.py regret_indifferent
"""

import requests
import random
import sys

API_BASE = "http://127.0.0.1:8000"


def run_persona(persona_name, decide_round1, decide_round2, seed=42):
    random.seed(seed)
    resp = requests.post(f"{API_BASE}/session/create").json()
    session_id = resp["session_id"]

    selected_ticker = None

    while True:
        state = requests.get(f"{API_BASE}/session/{session_id}/state").json()
        prices = state["market_state"]
        fixed_ticker = state["fixed_ticker"]

        if fixed_ticker:
            ticker = fixed_ticker
            target_pct = decide_round2(prices, state)
        else:
            ticker = selected_ticker or list(prices.keys())[0]
            target_pct = decide_round1(prices, state)
            selected_ticker = ticker

        requests.post(f"{API_BASE}/session/{session_id}/allocate",
                      json={"ticker": ticker, "target_pct": target_pct})

        adv = requests.post(f"{API_BASE}/session/{session_id}/advance").json()

        if adv["status"] == "all_blocks_complete":
            break
        elif adv["status"] == "new_block_started":
            selected_ticker = None

    result = requests.post(f"{API_BASE}/session/{session_id}/finish").json()
    print(f"\n=== {persona_name} ===")
    print("Raw estimate:", {k: round(v, 3) for k, v in result["raw_estimate"].items()})
    print(f"(n_obs: block1={result['n_obs_block1']}, block2={result['n_obs_block2']})")
    return result


def loss_averse_round1(prices, state):
    equity = state["equity"]
    prev = getattr(loss_averse_round1, "_prev_equity", 1_000_000)
    ret = (equity - prev) / prev if prev else 0
    loss_averse_round1._prev_equity = equity
    if ret < -0.02:
        return round(random.uniform(0.0, 0.15), 2)
    elif ret < -0.005:
        return round(random.uniform(0.15, 0.35), 2)
    return round(random.uniform(0.4, 0.7), 2)

def neutral_round2(prices, state):
    return round(random.uniform(0.4, 0.6), 2)


def loss_tolerant_round1(prices, state):
    equity = state["equity"]
    prev = getattr(loss_tolerant_round1, "_prev_equity", 1_000_000)
    ret = (equity - prev) / prev if prev else 0
    loss_tolerant_round1._prev_equity = equity
    if ret < -0.25:
        return round(random.uniform(0.4, 0.6), 2)
    return round(random.uniform(0.6, 0.9), 2)


def neutral_round1(prices, state):
    return round(random.uniform(0.4, 0.6), 2)

def fomo_chaser_round2(prices, state):
    others = [v["ticker_return_pct"] for k, v in prices.items() if v["ticker_return_pct"] is not None]
    avg_other_return = sum(others) / len(others) if others else 0
    base = 0.5
    if avg_other_return > 1.0:
        return round(min(0.95, base + random.uniform(0.3, 0.45)), 2)
    elif avg_other_return < -1.0:
        return round(max(0.05, base - random.uniform(0.2, 0.35)), 2)
    return round(random.uniform(0.4, 0.6), 2)

def indifferent_round2(prices, state):
    return round(random.uniform(0.4, 0.6), 2)


PERSONAS = {
    "loss_averse": (loss_averse_round1, neutral_round2),
    "loss_tolerant": (loss_tolerant_round1, neutral_round2),
    "fomo_chaser": (neutral_round1, fomo_chaser_round2),
    "regret_indifferent": (neutral_round1, indifferent_round2),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PERSONAS:
        print(f"Usage: python persona_bot.py [{'|'.join(PERSONAS.keys())}]")
        sys.exit(1)

    name = sys.argv[1]
    r1, r2 = PERSONAS[name]
    run_persona(name, r1, r2)