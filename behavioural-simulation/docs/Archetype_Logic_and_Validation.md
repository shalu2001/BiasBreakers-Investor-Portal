# Investor Archetypes — Logic & Validation

*Behavioural Preference Modelling module · Bias Breakers*

This note documents how the dashboard turns a player's recovered behavioural
parameters into an investor **archetype**, why the thresholds are set where they
are, and the evidence that the mapping is sound. It covers three questions a
reviewer is likely to ask: *what is the logic, where do the numbers come from,
and does it actually work?*

Reference implementation: `src/session/profileToPersona.ts`
Validation harness: `behavioural-simulation/backend/experiments/archetype_validation.py`

---

## 1. The logic

The game recovers three Cumulative-Prospect / Regret-Theory parameters:

| Parameter | Meaning | Used for the archetype? |
|-----------|---------|--------------------------|
| **α** (diminishing sensitivity) | how quickly extra gain/loss stops mattering | **No** — see §4 |
| **λ** (loss aversion) | how much losses outweigh equal gains | **Yes → risk axis** |
| **γ** (regret / FOMO) | how strongly the wider market pulls the player | **Yes → style axis** |

The archetype is built on **two orthogonal axes**, each driven by one parameter:

```
   risk posture   ← λ (loss aversion):   Bold  ·  Balanced  ·  Cautious
   market style   ← γ (regret / FOMO):   Strategist · Realist · Momentum-Seeker
```

This gives a **3 × 3 grid of nine archetypes** (Bold Strategist … Cautious
Momentum-Seeker). The two axes are kept separate on purpose: loss aversion is
*how much risk you can stomach*, regret sensitivity is *how much you move with
the crowd* — conceptually independent traits that should be reported as such,
not collapsed into a single "risk score".

Risk tolerance shown on the dashboard is simply `100 − lossAversion`, so the
Bold ↔ Cautious axis and the risk-tolerance meter never contradict each other.

---

## 2. Where the thresholds come from

Scores are **percentiles**, not raw parameter values. The recovered parameters
cluster (the estimator + calibrator compress them), so a naïve linear map slams
the tails to 0/100 — e.g. a real λ ≈ 1.44 wrongly showing "0/100, treats gains
and losses evenly". Instead each value is mapped to its **percentile rank** in
the recovered population, and the band cut-offs are the **terciles (p33 / p67)**
of that population:

| Axis | p33 threshold | p67 threshold |
|------|---------------|---------------|
| λ (loss aversion) | **2.00** | **2.53** |
| γ (regret / FOMO) | **1.62** | **3.01** |

These come from running synthetic investors through the **real** engine
(`backend/experiments/archetype_calibration.py`) and reading off the empirical
terciles of the recovered distribution. Using data-driven terciles rather than
textbook parameter ranges is what keeps the three bands roughly equal in size
and stops everyone landing in the middle ("everyone's a Realist").

---

## 3. Validation

Run on a **fresh, out-of-sample** set of 60 synthetic investors (seeds disjoint
from the calibration that set the thresholds), each played through the actual
`MultiBlockSession` + matched-stakes `EventRound` and recovered through the
production pipeline.

**3.1 Recovery quality** — can we read the parameter back at all?

| Parameter | Pearson r (true vs recovered) | MAE |
|-----------|------------------------------|-----|
| λ (loss aversion) | **0.84** | 0.41 |
| γ (regret / FOMO) | **0.93** | 0.49 |

Both parameters are recovered with strong correlation; γ is actually the
best-identified because the regret block deliberately concentrates checkpoints
on large-move days where the FOMO signal is strongest.

**3.2 Threshold sanity** — do the p33/p67 cut-offs split the sample into thirds?

| Axis | Low | Mid | High |
|------|-----|-----|------|
| risk (λ) | 33% | 25% | 42% |
| style (γ) | 32% | 25% | 43% |

Close to the ideal 33/33/33, with a mild skew toward the outer bands on this
particular sample (expected — the fresh uniform-truth sample isn't identical to
the calibration population). Crucially, **no band collapses**; all three stay
well populated.

**3.3 Construct validity** — does a higher band mean a genuinely higher trait?
Mean of the **true** parameter within each **recovered** band is cleanly
monotone:

| Risk band | mean true λ | | Style band | mean true γ |
|-----------|-------------|---|------------|-------------|
| Bold | 1.71 | | Strategist | 0.61 |
| Balanced | 2.62 | | Realist | 1.95 |
| Cautious | 3.60 | | Momentum | 2.97 |

Rank-based tercile agreement (recovered band == true band):

| Axis | Agreement | Chance |
|------|-----------|--------|
| risk | **93%** | 33% |
| style | **83%** | 33% |

Both far above the 33% you'd get by guessing — the labels track the truth.

**3.4 Axis independence** — the two axes should be roughly uncorrelated.
`corr(recovered λ, recovered γ) = −0.37` (true generated `−0.20` at n=60, i.e.
much of this is small-sample noise). There is a **mild** negative coupling in
recovery — when λ is over-read, γ tends to be slightly under-read — but nowhere
near enough to make the axes redundant. Worth keeping in mind, not a defect.

**3.5 Coverage** — under uniform ground truth, all **9/9** archetypes are
populated; no cell is unreachable.

---

## 4. Why α is *not* an archetype axis (and is fixed at 0.88 in the dev presets)

Two independent reasons:

1. **It isn't part of the archetype definition.** The archetype is a function of
   λ (risk) and γ (style) only; α never enters `profileToPersona`. So varying α
   across the presets would change nothing about the resulting archetype — which
   is exactly why the dev presets hold it at the population value 0.88.

2. **It is weakly identifiable.** Free-play trading barely constrains the
   curvature of the value function, so the calibrator regresses α back toward the
   population centre (~0.63–0.88) almost regardless of the true value. Reporting
   an α-based band would therefore be reading confidence into a number the game
   can't reliably measure. α is still recovered and handed to the reward model
   (it shapes the *magnitude* of the behavioural utility), but it is deliberately
   **not** surfaced as a personality trait.

---

## 5. Reproducing these numbers

```bash
cd behavioural-simulation/backend
python experiments/archetype_validation.py          # ~a few minutes for n=60
```

Change `n` in `run(n=...)` for a larger sample (runtime scales linearly — each
player is a full engine play-through). Thresholds live in
`src/session/profileToPersona.ts` (`LAM_ANCHORS` / `GAM_ANCHORS`); the tercile
cut-offs in this doc are the p33/p67 rows of those anchor tables.
