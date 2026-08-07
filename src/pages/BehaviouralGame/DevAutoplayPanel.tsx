import { useState } from 'react';
import { devAutoplay, type DevAutoplayResult } from '../../api/behaviouralGame';
import styles from './devPanel.module.css';

// DEV ONLY. Rendered on the game start screen behind an `import.meta.env.DEV`
// gate, so it never ships in a production build. Lets a developer pick a ground
// truth (alpha, lambda, gamma), auto-play the real engine, and see how well the
// production pipeline recovers those parameters -- a one-click validation that
// also skips the 5-minute game while testing everything downstream.

// All nine archetypes: risk (Bold / Balanced / Cautious, set by lambda) x
// market style (Strategist / Realist / Momentum, set by gamma). lambda/gamma
// values sit in the middle of each percentile band (see profileToPersona).
const PRESETS: { label: string; alpha: number; lam: number; gamma: number }[] = [
  { label: 'Bold Strategist', alpha: 0.88, lam: 1.4, gamma: 0.6 },
  { label: 'Bold Realist', alpha: 0.88, lam: 1.4, gamma: 2.4 },
  { label: 'Bold Momentum', alpha: 0.88, lam: 1.4, gamma: 3.4 },
  { label: 'Balanced Strategist', alpha: 0.88, lam: 2.25, gamma: 0.6 },
  { label: 'Balanced Realist', alpha: 0.88, lam: 2.25, gamma: 2.4 },
  { label: 'Balanced Momentum', alpha: 0.88, lam: 2.25, gamma: 3.4 },
  { label: 'Cautious Strategist', alpha: 0.88, lam: 3.4, gamma: 0.6 },
  { label: 'Cautious Realist', alpha: 0.88, lam: 3.4, gamma: 2.4 },
  { label: 'Cautious Momentum', alpha: 0.88, lam: 3.4, gamma: 3.4 },
];

const fmt = (x: number, d = 2) => x.toFixed(d);

type UseProfileFn = (
  p: { alpha: number; lambda: number; gamma: number },
  confidence: DevAutoplayResult['confidence'],
) => void;

export function DevAutoplayPanel({ onUseProfile }: { onUseProfile: UseProfileFn }) {
  const [alpha, setAlpha] = useState(0.88);
  const [lam, setLam] = useState(2.25);
  const [gamma, setGamma] = useState(1.5);
  const [seed, setSeed] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<DevAutoplayResult | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    setRes(null);
    try {
      const r = await devAutoplay({ alpha, lam, gamma, seed: seed ? Number(seed) : undefined });
      setRes(r);
    } catch {
      setErr('Auto-play failed — is the game backend running on :8000?');
    } finally {
      setBusy(false);
    }
  }

  const rows: { key: 'alpha' | 'lambda' | 'gamma'; label: string }[] = [
    { key: 'alpha', label: 'α  sensitivity' },
    { key: 'lambda', label: 'λ  loss aversion' },
    { key: 'gamma', label: 'γ  regret / FOMO' },
  ];

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <span className={styles.badge}>DEV</span>
        <span className={styles.title}>Skip &amp; validate recovery</span>
      </div>
      <p className={styles.sub}>
        Auto-plays the real engine with a generative policy driven by your chosen parameters, then
        recovers them through the exact production pipeline.
      </p>

      <div className={styles.presetsLabel}>Archetype presets</div>
      <div className={styles.presets}>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            className={styles.preset}
            onClick={() => {
              setAlpha(p.alpha);
              setLam(p.lam);
              setGamma(p.gamma);
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className={styles.sliders}>
        <SliderRow label="α  diminishing sensitivity" min={0.5} max={1} step={0.01} value={alpha} onChange={setAlpha} />
        <SliderRow label="λ  loss aversion" min={1} max={5} step={0.05} value={lam} onChange={setLam} />
        <SliderRow label="γ  regret / FOMO" min={0} max={4.5} step={0.05} value={gamma} onChange={setGamma} />
      </div>

      <div className={styles.actions}>
        <input
          className={styles.seed}
          placeholder="seed (optional)"
          value={seed}
          onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ''))}
        />
        <button type="button" className={styles.run} onClick={run} disabled={busy}>
          {busy ? 'Auto-playing…' : 'Auto-play & recover'}
        </button>
      </div>

      {err && <div className={styles.err}>{err}</div>}

      {res && (
        <div className={styles.result}>
          <div className={styles.tableHead}>
            <span>parameter</span>
            <span>chosen</span>
            <span>recovered</span>
            <span>|err|</span>
          </div>
          {rows.map((r) => {
            const level = res.confidence[r.key]?.level;
            const good = res.errors[r.key] <= 0.35;
            return (
              <div key={r.key} className={styles.tableRow}>
                <span className={styles.pName}>
                  {r.label}
                  {level && level !== 'ok' && <em className={styles.lowconf}>{level}</em>}
                </span>
                <span className={styles.mono}>{fmt(res.chosen[r.key])}</span>
                <span className={styles.mono}>{fmt(res.recovered[r.key])}</span>
                <span className={`${styles.mono} ${good ? styles.good : styles.off}`}>{fmt(res.errors[r.key])}</span>
              </div>
            );
          })}
          <p className={styles.note}>
            λ recovered from {res.lambda_source === 'matched_stakes_events' ? 'matched-stakes events' : 'free-play'}.
            α is weakly identifiable by design (the calibrator regresses it toward the population centre), so
            treat its recovery as indicative only — λ and γ are the meaningful reads.
          </p>
          <button
            type="button"
            className={styles.use}
            onClick={() =>
              onUseProfile(
                { alpha: res.recovered.alpha, lambda: res.recovered.lambda, gamma: res.recovered.gamma },
                res.confidence,
              )
            }
          >
            Use this profile → Dashboard
          </button>
        </div>
      )}
    </div>
  );
}

function SliderRow({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className={styles.sliderRow}>
      <div className={styles.sliderTop}>
        <span className={styles.sliderLabel}>{label}</span>
        <span className={styles.sliderVal}>{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.range}
      />
    </label>
  );
}
