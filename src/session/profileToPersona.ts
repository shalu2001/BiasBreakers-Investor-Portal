import type { PersonaProfile } from '../api/persona';
import type { BehaviouralProfile } from './SessionContext';

// Translates the game's recovered parameters (alpha, lambda, gamma) into the
// dashboard's PersonaProfile. Two ORTHOGONAL axes:
//   Risk posture  <- loss aversion (lambda):  Bold / Balanced / Cautious
//   Market style  <- regret / FOMO (gamma):   Strategist / Realist / Momentum-Seeker
//
// SCORES ARE PERCENTILES. The recovered parameters cluster (the estimator +
// calibrator compress them), so a plain linear map slammed the tails to 0/100 --
// e.g. lambda 1.44 (a real, mild loss aversion at the ~14th population percentile)
// showed as "0/100, treats gains and losses evenly". Instead we map each value to
// its PERCENTILE RANK in the population, measured by running 75 synthetic
// investors through the real game (backend/experiments/archetype_calibration.py).
// So "loss aversion 14/100" literally means "more loss-averse than 14% of players".
// The tercile boundaries (p33 / p67) are the archetype band cut-offs, so bands and
// scores stay consistent.

// (value, percentile) anchors from the recovered distribution; piecewise-linear.
const LAM_ANCHORS: ReadonlyArray<readonly [number, number]> = [
  [1.13, 0], [1.34, 10], [1.61, 20], [1.97, 30], [2.0, 33],
  [2.27, 50], [2.53, 67], [2.95, 80], [3.58, 90], [4.12, 95], [6.13, 100],
];
const GAM_ANCHORS: ReadonlyArray<readonly [number, number]> = [
  [0.26, 0], [0.52, 10], [0.89, 20], [1.4, 30], [1.62, 33],
  [2.6, 50], [3.01, 67], [3.36, 80], [3.51, 90], [3.59, 95], [3.78, 100],
];

function percentileScore(value: number, anchors: ReadonlyArray<readonly [number, number]>): number {
  if (value <= anchors[0][0]) return anchors[0][1];
  const last = anchors[anchors.length - 1];
  if (value >= last[0]) return last[1];
  for (let i = 1; i < anchors.length; i++) {
    const [x0, p0] = anchors[i - 1];
    const [x1, p1] = anchors[i];
    if (value <= x1) return Math.round(p0 + ((value - x0) / (x1 - x0)) * (p1 - p0));
  }
  return last[1];
}

export function profileToPersona(p: BehaviouralProfile): PersonaProfile | null {
  if (p.lambda == null || p.gamma == null) return null;

  const lossAversion = percentileScore(p.lambda, LAM_ANCHORS);
  const regretAversion = percentileScore(p.gamma, GAM_ANCHORS);
  const riskTolerance = 100 - lossAversion;

  const risk = lossAversion >= 67 ? 'Cautious' : lossAversion >= 33 ? 'Balanced' : 'Bold';
  const style =
    regretAversion >= 67 ? 'Momentum-Seeker' : regretAversion >= 33 ? 'Realist' : 'Strategist';
  const archetype = `${risk} ${style}`;

  const riskClause =
    risk === 'Bold'
      ? "you're comfortable taking on risk for higher potential returns"
      : risk === 'Balanced'
        ? 'you balance the chase for returns against your comfort with risk'
        : 'you prioritise protecting your capital over chasing the biggest gains';
  const styleClause =
    style === 'Momentum-Seeker'
      ? ', and you tend to move with the market, so we damp impulsive, FOMO-driven switches for you.'
      : style === 'Strategist'
        ? ', and you stay disciplined, largely ignoring what the rest of the market is doing.'
        : ', with a measured response to what the wider market is doing.';
  const summary = `In short, ${riskClause}${styleClause}`;

  return { archetype, summary, riskTolerance, lossAversion, regretAversion };
}

// ---- richer dashboard insight ----------------------------------------------
// Turns the trait scores into a readable breakdown + takeaway. CONFIDENCE-AWARE:
// the game flags whether it actually measured each trait; when a trait is
// "uninformative" / "weak" we mark it provisional and DON'T assert claims built
// on it (e.g. we won't say "immune to FOMO" if gamma wasn't reliably read).

export interface TraitInsight {
  key: 'riskTolerance' | 'lossAversion' | 'regretAversion';
  label: string;
  score: number;
  band: 'low' | 'moderate' | 'high';
  reliable: boolean; // did the game measure this trait confidently?
  meaning: string;
}

export interface BehaviouralInsight {
  traits: TraitInsight[];
  narrative: string;
  strengths: string[];
  watchouts: string[];
  strategy: string;
}

export interface TraitConfidence {
  lambda?: string; // 'ok' | 'weak' | 'uninformative' | ...
  gamma?: string;
}

const bandOf = (s: number, lo: number, hi: number): 'low' | 'moderate' | 'high' =>
  s >= hi ? 'high' : s >= lo ? 'moderate' : 'low';

// undefined confidence (e.g. the mock fixture) counts as reliable.
const isReliable = (level?: string) =>
  level == null || (level !== 'uninformative' && level !== 'weak');

export function buildInsight(
  p: { riskTolerance: number; lossAversion: number; regretAversion: number },
  confidence?: TraitConfidence,
): BehaviouralInsight {
  const lamOk = isReliable(confidence?.lambda); // drives risk tolerance + loss aversion
  const gamOk = isReliable(confidence?.gamma); // drives regret / FOMO

  const rt = bandOf(p.riskTolerance, 33, 67);
  const la = bandOf(p.lossAversion, 33, 67);
  const rg = bandOf(p.regretAversion, 33, 67);

  const traits: TraitInsight[] = [
    {
      key: 'riskTolerance', label: 'Risk tolerance', score: p.riskTolerance, band: rt, reliable: lamOk,
      meaning:
        rt === 'high' ? "You're comfortable riding out volatility for the chance of higher returns."
        : rt === 'moderate' ? 'You balance the hunt for growth against the need for comfort.'
        : "You'd rather protect your capital than chase big gains.",
    },
    {
      key: 'lossAversion', label: 'Loss aversion', score: p.lossAversion, band: la, reliable: lamOk,
      meaning:
        la === 'high' ? 'Losses sting far more than equal gains, so sharp drops can tempt you to sell.'
        : la === 'moderate' ? 'You feel losses a little more than gains, but stay fairly steady.'
        : "You take gains and losses in your stride, without much fear of a dip.",
    },
    {
      key: 'regretAversion', label: 'Regret / FOMO', score: p.regretAversion, band: rg, reliable: gamOk,
      meaning:
        rg === 'high' ? 'You feel a real pull to move with the market when it runs.'
        : rg === 'moderate' ? "Some sensitivity to missing out on a rally, but it rarely drives you."
        : "The market's swings don't pull you around much.",
    },
  ];

  // --- narrative: confident where measured, gently forward-looking otherwise --
  const opening =
    rt === 'high' ? "You invest with a real appetite for growth, and short-term swings don't knock you off the long game."
    : rt === 'moderate' ? 'You take a measured approach: open to growth, but not at the cost of your peace of mind.'
    : 'You invest cautiously; keeping what you have matters more to you than chasing the biggest gains.';
  const lossLine =
    la === 'high' ? 'Losses, though, hit you hard: a sharp drop feels far worse than an equal gain feels good.'
    : la === 'moderate' ? 'You feel losses a little more than gains, but you generally hold your nerve through a dip.'
    : "You're also even-keeled about losses, so a red day rarely rattles you into rash moves.";
  const regretLine = gamOk
    ? (rg === 'high' ? 'And you feel a strong pull to move with the market when it runs, so momentum is your main tell.'
       : rg === 'moderate' ? 'You feel some tug to join a rally, but it rarely runs your decisions.'
       : "As for the wider market, its swings don't pull you off your own course.")
    : 'Your read on how the wider market sways you is still an early one, and it sharpens the more you play.';
  const narrative = [
    lamOk ? opening : 'Your read on how much risk you like is still an early one, and it firms up the more you play.',
    lamOk ? lossLine : '',
    regretLine,
  ].filter(Boolean).join(' ');

  // --- strengths (only claims from reliably-measured traits) -----------------
  const strengths: string[] = [];
  if (lamOk && rt === 'high') strengths.push('Comfortable holding through volatility in pursuit of long-term growth.');
  if (lamOk && la === 'low') strengths.push("Calm in drawdowns, so you're unlikely to panic-sell near the bottom.");
  if (gamOk && rg === 'low') strengths.push("Disciplined, so you don't chase hype or hot stocks.");
  if (lamOk && rt === 'low') strengths.push('You instinctively protect your capital and avoid reckless bets.');
  if (lamOk && la === 'moderate' && rt === 'moderate')
    strengths.push('A balanced temperament that adapts to both calm and choppy markets.');
  if (strengths.length === 0)
    strengths.push('A clear, consistent decision style the system can plan around.');

  // --- watch-outs ------------------------------------------------------------
  const watchouts: string[] = [];
  if (lamOk && la === 'high')
    watchouts.push('A sharp drop may tempt you to sell at the worst possible time, so your plan deliberately limits drawdowns to protect you from that instinct.');
  if (gamOk && rg === 'high')
    watchouts.push('Fear of missing out can pull you into rallies late, so the system damps impulsive switching for you.');
  if (lamOk && rt === 'high' && la === 'low')
    watchouts.push('A high appetite for risk can drift into over-concentration, so we keep you diversified and stop one bad bet dominating.');
  if (lamOk && rt === 'low')
    watchouts.push('Playing it very safe can quietly cost you growth over the years, so we make sure you still capture reasonable upside.');
  if (watchouts.length === 0)
    watchouts.push('Nothing extreme to flag from what we measured — we keep the plan steady.');

  // --- strategy --------------------------------------------------------------
  const parts: string[] = [];
  if (lamOk && rt === 'high' && la !== 'high') parts.push('tilt toward growth and let you ride volatility for higher returns');
  else if (lamOk && (rt === 'low' || la === 'high')) parts.push('cap your drawdowns and favour steadier holdings, even at the cost of some upside');
  else parts.push('aim for steady growth you can comfortably hold through the ups and downs');
  if (lamOk && la === 'high') parts.push('keep your worst-case losses gentle');
  if (gamOk && rg === 'high') parts.push("damp impulsive switches so you're not chasing every rally");
  const strategy = `Your recommendations will ${parts.join(', ')}.`;

  return { traits, narrative, strengths, watchouts, strategy };
}
