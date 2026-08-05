# Narrative Intelligence Prediction Engine

A standalone, portable backend that turns a **30-day window of enriched financial news** into
**Black-Litterman posterior expected returns** for the SL20 universe, exposed over a small
FastAPI service. It bundles the full LLM narrative pipeline (BERTopic clustering with OpenAI
topic labelling), the LLM macro-to-ticker basket mapping, per-view confidence weighting, and
the Black-Litterman posterior computation.

All data is read from **Cosmos DB (Mongo API)**. The heavy enrichment layer (FinBERT
sentiment, embeddings, macro/micro classification) is assumed to be already applied upstream
and stored on the articles — this engine starts at **clustering**.

## Pipeline

```
news (FinancialNewsDB, 30-day window, pre-enriched)
  └─ split macro / micro
     ├─ macro: BERTopic cluster → narrative views (OpenAI topic labels)
     └─ micro: per-company BERTopic cluster → narrative views
  └─ Qi expected-return views (sentiment · persistence · attention · diffusion) + calibration
  └─ LLM macro-view → market-cap-weighted ticker basket (OpenAI)               [optional]
  └─ Black-Litterman:
       prices  (SPSL20_DB.tickerdata_2020-2026, trailing 30 trading days, Ledoit-Wolf)
       caps    (SPSL20_DB.marketcap_2026, latest on/before as_of)
       index   (SPSL20_DB.sp_sl20_index, same window → market-implied risk aversion)
       mapping (FinancialNewsDB.Ticker_Info)
       confidence → Idzorek omega
  └─ per-ticker posterior / prior / tilt  +  underlying narrative views
```

> **Note on databases:** prices, market caps, and the index all live in **`SPSL20_DB`**
> (`SPSL2_DB` is empty). All database/collection names are configurable via env vars.

### CSE announcements

`CSE_Annoucements` carries enriched corporate disclosures with no `market_classification`.
A dedicated adapter folds them in as **micro** news: it drops zero-sentiment noise, recovers
text from `remarks`/`title` when `content` is empty, resolves the ticker via
`companyId → symbol → company name` against `Ticker_Info`, keeps only SL20-universe names, and
merges them into each company's micro pool (so they cluster alongside DailyFT/EconomyNext/LBO
micro news). Degenerate all-zero embeddings are rejected. Companies with too few docs to form
a BERTopic cluster simply yield no view.

## Data sources (Cosmos DB, Mongo API)

| Purpose      | Database          | Collection              | Key fields |
|--------------|-------------------|-------------------------|------------|
| News         | `FinancialNewsDB` | all except `Ticker_Info`| `published_date`, `content`, `final_embedding`, `final_sentiment_score`, `market_classification`, `matched_company_name`, `matched_symbol` |
| Ticker ref   | `FinancialNewsDB` | `Ticker_Info`           | `Company`, `CSE Ticker`, `GICS Sector/Industry/Sub-Industry` |
| Prices       | `SPSL20_DB`       | `tickerdata_2020-2026`  | `ticker`, `date`, `closing price` |
| Market caps  | `SPSL20_DB`       | `marketcap_2026`        | `ticker`, `date`, `marketcap` |
| Market index | `SPSL20_DB`       | `sp_sl20_index`         | `date`, `sp_sl20_close` |

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r narrative_engine/requirements.txt
cp narrative_engine/.env.example narrative_engine/.env   # then fill in secrets
```

## Run the API

```bash
uvicorn narrative_engine.api.app:app --host 0.0.0.0 --port 8000
```

- `GET /health` → `{ "status": "ok", "mongo": "ok" }`
- `POST /predict`

```bash
curl -s -X POST http://localhost:8000/predict \
  -H 'content-type: application/json' \
  -d '{"as_of_date": "2026-07-15"}'
```

### Request

| field                | type    | default | meaning |
|----------------------|---------|---------|---------|
| `as_of_date`         | date    | —       | anchor date; news lookback ends here |
| `lookback_days`      | int     | 30      | news lookback window |
| `use_macro_overrides`| bool    | true    | apply the LLM macro-to-ticker basket mapping |

### Response (shape)

```jsonc
{
  "as_of": "2026-07-15",
  "lookback_days": 30,
  "universe": ["JKH", "COMB", ...],
  "predictions": [
    { "ticker": "JKH", "posterior": 0.14, "prior": 0.11, "tilt": 0.03 }
  ],
  "views": [
    { "view_id": "...", "view_type": "macro", "topic_name": "...",
      "Qi": 0.02, "Si": 0.3, "Si_normalized": 0.29, "persistence": 0.4,
      "attention": 12, "cluster_size": 12, "confidence": 0.6,
      "mapped_tickers": [["JKH", 0.5], ["HNB", 0.5]] }
  ],
  "meta": { "window_start": "2026-06-15", "window_end": "2026-07-15", "...": "..." }
}
```

`tilt = posterior - prior` is the narrative signal (the equilibrium prior is dominated by the
always-positive market-implied return, so the tilt is what the narrative actually adds).

## Use as a library

```python
from narrative_engine import NarrativePredictionEngine, get_settings

engine = NarrativePredictionEngine(get_settings())
result = engine.predict("2026-07-15")          # PredictionResult
print(result.predictions[0], result.meta)
```

## Notes

- **Latency:** a full run does BERTopic clustering + several OpenAI calls and takes seconds to
  a minute. Results are cached in-process by `(as_of_date, lookback_days, use_macro_overrides)`.
  For high throughput, front `/predict` with an async job queue.
- **Horizon:** predictions are the native (annualized) Black-Litterman posterior/prior/tilt.
  Any "N-day-ahead" framing is an interpretation applied downstream, not a model parameter.
- **Portability:** this package has no imports from the research `src/` tree — copy the
  `narrative_engine/` directory into another repo and it runs against the same Cosmos data.
