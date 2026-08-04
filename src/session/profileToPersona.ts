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
