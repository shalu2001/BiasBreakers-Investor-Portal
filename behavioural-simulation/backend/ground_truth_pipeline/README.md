# Ground-Truth Pipeline (pre-simulation foundation)

This folder is the **foundation** of the Behavioural Preference Modelling module —
the work done *before* the onboarding game. Its job is to prove one thing:

> If we know an investor's psychology, and they trade, can we get that psychology
> back from their trades alone?

Because real retail trade records are confidential and unavailable, we **manufacture**
investors whose psychology we set ourselves — giving us a known answer key to test
recovery against. This is standard *parameter recovery* validation.

## The five stages

| Stage | Script | What it does |
|------|--------|--------------|
| 1 | `1_generate_transactions.py` | Five personas with **known** (α, λ, γ) trade the real S&P SL20 stocks day by day, driven by prospect theory + regret. → `transaction_ledger.csv`, `portfolio_snapshots.csv` |
| 2 | `2_reconstruct_log.py` | Replays the ledger to compute, for each decision, the **wealth-change** and **market-gap** that drove it (holds included). → `behavioral_validation_log.csv` |
| 3 | `3_estimate_parameters.py` | Works backwards: recovers (α, λ, γ) from the decisions by maximum likelihood. → `recovered_parameters.csv` |
| 4 | `4_compute_utility.py` | Uses the recovered parameters to score every day with a Behavioural Utility number U. → `behavioral_utility.csv` |
| 5 | `5_evaluate.py` | Compares recovered vs. true parameters, prints metrics, saves figures. → `recovery_comparison.png`, `prospect_theory_curve.png` |
| 6 | `6_drift_recovery.py` | **Proves psychology can be tracked when it changes.** One investor whose loss aversion **drifts** (spikes during the real 2022 crash, relaxes after); recovered over time with a rolling window using the same estimator. → `drift_recovery.png` |

Shared helpers: `market_data.py` (loads the real CSE stock prices **and** the real
S&P SL20 index, stitched from `07Market Indices - Daily.xls` (2020–2025) +
`CSE_Index_Data.csv` (2025–2026)) and `config.py` (the ground-truth personas + the
generator's response constants). All data is the actual CSE data.

## The bug that was fixed

The **original** recovery collapsed α and λ onto their lower bounds — it did *not*
work. The cause was a **model mismatch**: the generator let investors choose among
three actions (buy / sell / **hold**) with a gentle response, but the recovery code
assumed only two actions (buy / sell), dropped every hold, and assumed a much
sharper response. Fitting the wrong model flattened everything and pushed α and λ to
their floors.

The fix: recover with **the same model used to generate** (three-way, same response
slope, holds kept — see `config.py`). Recovery is then accurate.

## Result (this run)

| Parameter | MAE | Correlation (true vs recovered) |
|-----------|-----|--------------------------------|
| α (sensitivity) | 0.05 | 0.95 |
| λ (loss aversion) | 0.18 | 0.99 |
| γ (regret / FOMO) | 0.14 | 1.00 |

(Using the real S&P SL20 index throughout — stocks and benchmark both from CSE data.)

## Drift recovery (Stage 6) — why we need *dynamic* utility

Stages 1–5 prove recovery when psychology is **stable**. But the project claims
psychology **changes over time**, which is the justification for re-estimating the
utility dynamically instead of fixing it. Stage 6 proves that claim: one investor's
true loss aversion is made to **spike during the real 2022 crash and relax afterwards**,
and a rolling-window re-run of the same estimator **tracks the moving value**
(tracking correlation r ≈ 0.71 across 52 time windows).

Two honest caveats to state in the write-up:
1. This is a **planted** drift — it proves *"if psychology drifts, we can follow it,"*
   not that real investors' psychology drifts (that needs real longitudinal data).
2. The rolling window **lags and smooths** a sharp change — a short window tracks a
   spike faster but is noisier; a long window is smoother but slower. That
   bias–variance trade-off is inherent to windowed estimation and is a tunable choice.

## Why this and the onboarding game are different

This ledger has ~1,200 decisions per investor — plenty of data, so direct estimation
works. The onboarding **game** has only ~30 decisions, which is why it needs the extra
machinery (simulation-based calibration + matched-stakes gambles). Same idea,
different data budget → different tools. This pipeline is also the template for the
**live / dynamic** path, where parameters are re-estimated from an investor's ongoing
real trades.

## How to run

```
python 1_generate_transactions.py
python 2_reconstruct_log.py
python 3_estimate_parameters.py
python 4_compute_utility.py
python 5_evaluate.py
python 6_drift_recovery.py    # proves drifting psychology can be tracked
```

Everything is seeded, so results are reproducible. Source market data is in `data/`;
all generated files land in `outputs/`.
