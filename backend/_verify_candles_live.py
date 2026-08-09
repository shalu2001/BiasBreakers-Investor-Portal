import random
import string

import requests

BASE = "http://localhost:8012"


def rand_email():
    return "e2e_" + "".join(random.choices(string.ascii_lowercase, k=8)) + "@test.local"


def main():
    r = requests.post(f"{BASE}/portal/auth/register", json={"email": rand_email(), "password": "testpass123"})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = requests.get(f"{BASE}/portfolio/holdings?range=1Y", headers=headers)
    r.raise_for_status()
    holdings = r.json()
    sample = holdings[0]
    candles = sample["candles"]
    print(f"Ticker: {sample['ticker']}, {len(candles)} candles")

    up = sum(1 for c in candles if c["close"] > c["open"])
    down = sum(1 for c in candles if c["close"] < c["open"])
    flat = sum(1 for c in candles if c["close"] == c["open"])
    print(f"Up days: {up}, Down days: {down}, Flat/first: {flat}")

    for c in candles[:5]:
        print(" ", c)

    assert down > 0, "expected at least some down (red) days over a 1Y window"
    assert up > 0, "expected at least some up (green) days too"
    # Sanity: open should sit within [low, high] for every candle now.
    for c in candles:
        assert c["low"] <= c["open"] <= c["high"], f"open outside wick range: {c}"

    print(f"\nPASS: real mix of up/down days now ({up} up, {down} down), open always within wick range")


if __name__ == "__main__":
    main()
