import type { PersonaProfile } from '../api/persona';
import type { BehaviouralProfile } from './SessionContext';

// Translates the behavioural game's raw parameters (alpha, lambda, gamma) into
// the PersonaProfile the dashboard already knows how to render. This is the
// "logic bridge" that carries the game result into the rest of the app.
//
//   lambda (loss aversion)   ~1.0 (even) .. ~4.5 (very loss-averse)
//   gamma  (regret / FOMO)   ~0.0 (calm) .. ~4.5 (strong chaser)
//   alpha  (diminishing sensitivity) ~0.55 .. 1.0  (kept for future use)

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const toScore = (x: number) => Math.round(clamp01(x) * 100);

export function profileToPersona(p: BehaviouralProfile): PersonaProfile | null {
  if (p.lambda == null || p.gamma == null) return null;

  const lossAversion = toScore((p.lambda - 1) / 3.5); // λ 1..4.5 -> 0..100
  const regretAversion = toScore(p.gamma / 4.5); // γ 0..4.5 -> 0..100
  const riskTolerance = toScore(1 - (p.lambda - 1) / 3.5); // inverse of loss aversion

  const riskLabel = riskTolerance >= 66 ? 'Bold' : riskTolerance >= 33 ? 'Balanced' : 'Cautious';
  const styleLabel =
    regretAversion >= 60 ? 'Momentum-Seeker' : lossAversion >= 60 ? 'Capital-Preserver' : 'Realist';
  const archetype = `${riskLabel} ${styleLabel}`;

  const riskClause =
    riskTolerance >= 66
      ? "you're comfortable riding out volatility for upside"
      : riskTolerance >= 33
        ? 'you weigh upside against comfort fairly evenly'
        : 'you prioritise protecting capital over chasing gains';

  const styleClause =
    regretAversion >= 60
      ? ', though a strong pull to chase the market when it runs without you means we damp impulsive switches.'
      : lossAversion >= 60
        ? ', and because losses weigh heavily on you, we keep drawdowns gentle.'
        : ', with a fairly balanced response to gains and losses.';

  const summary =
    `Read live from your five-minute game: risk tolerance ${riskTolerance}/100, ` +
    `loss aversion ${lossAversion}/100, regret sensitivity ${regretAversion}/100. In short, ${riskClause}${styleClause}`;

  return { archetype, summary, riskTolerance, lossAversion, regretAversion };
}

// ---- richer dashboard insight ----------------------------------------------
// Turns the three trait scores (which any PersonaProfile already carries, game-
// derived or fixture) into a readable breakdown plus a concrete portfolio
// takeaway, so the dashboard shows an INSIGHT rather than just an archetype label.

export interface TraitInsight {
  key: 'riskTolerance' | 'lossAversion' | 'regretAversion';
  label: string;
  score: number;
  band: 'low' | 'moderate' | 'high';
  meaning: string;
}

export interface BehaviouralInsight {
  traits: TraitInsight[];
  narrative: string; // who you are as an investor (a few sentences)
  strengths: string[]; // behavioural edges to lean on
  watchouts: string[]; // behavioural risks the plan manages for you
  strategy: string; // what the system will do with this profile
}

const bandOf = (s: number, lo: number, hi: number): 'low' | 'moderate' | 'high' =>
  s >= hi ? 'high' : s >= lo ? 'moderate' : 'low';

export function buildInsight(p: {
  riskTolerance: number;
  lossAversion: number;
  regretAversion: number;
}): BehaviouralInsight {
  const rt = bandOf(p.riskTolerance, 33, 66);
  const la = bandOf(p.lossAversion, 33, 66);
  const rg = bandOf(p.regretAversion, 30, 60);

  const traits: TraitInsight[] = [
    {
      key: 'riskTolerance', label: 'Risk tolerance', score: p.riskTolerance, band: rt,
      meaning:
        rt === 'high' ? "You're comfortable riding out volatility for the chance of higher returns."
        : rt === 'moderate' ? 'You balance the hunt for growth against the need for comfort.'
        : "You'd rather protect your capital than chase big gains.",
    },
    {
      key: 'lossAversion', label: 'Loss aversion', score: p.lossAversion, band: la,
      meaning:
        la === 'high' ? 'Losses sting far more than equal gains, so sharp drops can tempt you to sell.'
        : la === 'moderate' ? 'You feel losses a little more than gains, but stay fairly steady.'
        : 'You treat gains and losses evenly and rarely panic on a dip.',
    },
    {
      key: 'regretAversion', label: 'Regret / FOMO', score: p.regretAversion, band: rg,
      meaning:
        rg === 'high' ? 'A strong pull to chase the market when it runs without you.'
        : rg === 'moderate' ? 'Some sensitivity to missing out on a rally.'
        : 'Largely unbothered by what the rest of the market is doing.',
    },
  ];

  // --- narrative: three sentences woven from the three traits ---------------
  const opening =
    rt === 'high' ? "You invest with a real appetite for growth, and short-term swings don't knock you off the long game."
    : rt === 'moderate' ? 'You take a measured approach: open to growth, but not at the cost of your peace of mind.'
    : 'You invest cautiously; keeping what you have matters more to you than chasing the biggest gains.';
  const lossLine =
    la === 'high' ? 'Losses, though, hit you hard: a sharp drop feels far worse than an equal gain feels good, which can tempt you to sell at exactly the wrong moment.'
    : la === 'moderate' ? 'You feel losses a little more than gains, but you generally hold your nerve through a dip.'
    : "You're also unusually even-keeled about losses, and a red day rarely rattles you into rash moves.";
  const regretLine =
    rg === 'high' ? 'On top of that, you feel a strong pull to chase the market when it runs without you, so FOMO is your biggest behavioural risk.'
    : rg === 'moderate' ? 'You feel some tug to join a rally, but it rarely runs your decisions.'
    : "And you're largely immune to FOMO; what other stocks are doing doesn't pull you off course.";
  const narrative = `${opening} ${lossLine} ${regretLine}`;

  // --- strengths -------------------------------------------------------------
  const strengths: string[] = [];
  if (rt === 'high') strengths.push('Comfortable holding through volatility in pursuit of long-term growth.');
  if (la === 'low') strengths.push("Calm in drawdowns, so you're unlikely to panic-sell near the bottom.");
  if (rg === 'low') strengths.push("Disciplined, so you don't chase hype or hot stocks.");
  if (rt === 'low') strengths.push('You instinctively protect your capital and avoid reckless bets.');
  if (la === 'moderate' && rt === 'moderate')
    strengths.push('A balanced temperament that adapts to both calm and choppy markets.');
  if (strengths.length === 0)
    strengths.push('A clear, consistent decision style the system can plan around.');

  // --- watch-outs ------------------------------------------------------------
  const watchouts: string[] = [];
  if (la === 'high')
    watchouts.push('A sharp drop may tempt you to sell at the worst possible time, so your plan deliberately limits drawdowns to protect you from that instinct.');
  if (rg === 'high')
    watchouts.push('Fear of missing out can pull you into rallies late, so the system damps impulsive switching for you.');
  if (rt === 'high' && la === 'low')
    watchouts.push('A high appetite for risk can drift into over-concentration, so we keep you diversified and stop one bad bet dominating.');
  if (rt === 'low')
    watchouts.push('Playing it very safe can quietly cost you growth over the years, so we make sure you still capture reasonable upside.');
  if (watchouts.length === 0)
    watchouts.push('Nothing extreme to flag: your profile is well-balanced, so we simply keep the plan steady.');

  // --- strategy --------------------------------------------------------------
  const parts: string[] = [];
  if (rt === 'high' && la !== 'high') parts.push('tilt toward growth and let you ride volatility for higher returns');
  else if (rt === 'low' || la === 'high') parts.push('cap your drawdowns and favour steadier holdings, even at the cost of some upside');
  else parts.push('aim for steady growth you can comfortably hold through the ups and downs');
  if (la === 'high') parts.push('keep your worst-case losses gentle');
  if (rg === 'high') parts.push("damp impulsive switches so you're not chasing every rally");
  const strategy = `Your recommendations will ${parts.join(', ')}.`;

  return { traits, narrative, strengths, watchouts, strategy };
}
