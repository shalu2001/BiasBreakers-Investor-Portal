"""Shared market-data loader used by every stage (single source of truth).

Uses the REAL CSE data:
  - S&P SL20.xlsx            : per-ticker daily closes
  - 07Market Indices - Daily.xls : the historical S&P Sri Lanka 20 index (2020-2025)
  - CSE_Index_Data.csv       : the recent S&P SL20 index (2025-2026)
The two index sources are stitched into one continuous daily index return series.
"""
import os
import pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
XLSX = os.path.join(DATA, "S&P SL20.xlsx")
HIST_XLS = os.path.join(DATA, "07Market Indices - Daily.xls")
CSE_CSV = os.path.join(DATA, "CSE_Index_Data.csv")
START, END = "2020-01-01", "2026-04-30"


def load_index():
    """Real S&P Sri Lanka 20 index return (%), historical .xls + recent CSV."""
    raw = pd.read_excel(HIST_XLS, sheet_name="Index", header=None)
    d = raw.iloc[5:, [0, 3]].copy()          # col 0 = date, col 3 = S&P Sri Lanka 20
    d.columns = ["Date", "SL20"]
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    d["SL20"] = pd.to_numeric(d["SL20"], errors="coerce")
    hist = d.dropna()
    hist = hist[hist["Date"] >= pd.to_datetime(START)]

    cse = pd.read_csv(CSE_CSV, encoding="unicode_escape")
    cse["Date"] = pd.to_datetime(cse["Date"], dayfirst=True, errors="coerce")
    cse["SL20"] = pd.to_numeric(cse["Index_Price"].astype(str).str.replace(",", ""), errors="coerce")
    cse = cse[["Date", "SL20"]].dropna()

    cutoff = hist["Date"].max()
    idx = (pd.concat([hist, cse[cse["Date"] > cutoff]])
           .drop_duplicates("Date").sort_values("Date"))
    idx["Index_Return"] = idx["SL20"].pct_change() * 100
    idx["Date"] = idx["Date"].dt.date
    return idx[["Date", "Index_Return"]].fillna(0)


def load_market():
    """Per-ticker daily closes merged with the real S&P SL20 index return."""
    xl = pd.ExcelFile(XLSX)
    frames = []
    for sheet in xl.sheet_names:
        if sheet in ("Tickers", "S&P SL20"):
            continue
        df = pd.read_excel(XLSX, sheet_name=sheet)
        if "Date" not in df.columns or "Close" not in df.columns:
            continue
        df = df[["Date", "Close"]].copy()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["Ticker"] = sheet.replace(".N", "")
        frames.append(df.dropna(subset=["Date"]))
    market = pd.concat(frames, ignore_index=True)

    market = market.merge(load_index(), on="Date", how="left")
    market["Index_Return"] = market["Index_Return"].fillna(0)
    lo, hi = pd.to_datetime(START).date(), pd.to_datetime(END).date()
    return market[(market["Date"] >= lo) & (market["Date"] <= hi)]


def build_lookup(market):
    lookup = {}
    for date, g in market.groupby("Date"):
        lookup[date] = {"index_return": g["Index_Return"].iloc[0],
                        "price_map": dict(zip(g["Ticker"], g["Close"]))}
    return lookup, sorted(market["Ticker"].unique())
