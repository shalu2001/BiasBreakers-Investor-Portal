import styles from './game.module.css';

interface AllocationSliderProps {
  value: number;                 // 0..100
  onChange: (v: number) => void;
  leftLabel: string;
  rightLabel: string;
  showNudges?: boolean;
}

// The continuous "position dial" — a custom track/fill/handle with an invisible
// range input on top for accessibility and dragging. Used in both the trading
// screen and the matched-stakes event round.
export function AllocationSlider({ value, onChange, leftLabel, rightLabel, showNudges = true }: AllocationSliderProps) {
  const clamp = (v: number) => Math.max(0, Math.min(100, Math.round(v)));
  return (
    <div className={styles.beamWrap}>
      <div className={styles.beamTrack}>
        <div className={styles.beamFill} style={{ width: `${value}%` }} />
        <div className={styles.beamHandle} style={{ left: `${value}%` }} />
      </div>
      <input
        type="range" min={0} max={100} step={1} value={value} className={styles.beamInput}
        onChange={(e) => onChange(clamp(parseInt(e.target.value, 10)))}
      />
      <div className={styles.beamLabels}>
        <span>{leftLabel}</span>
        <div className={styles.beamCenter}>
          <div className={styles.nudge}>
            {showNudges && (
              <>
                <button type="button" className={styles.nudgeBtn} onClick={() => onChange(clamp(value - 5))}>&minus;5</button>
                <button type="button" className={styles.nudgeBtn} onClick={() => onChange(clamp(value - 1))}>&minus;1</button>
              </>
            )}
            <span className={`${styles.beamPct} ${styles.mono}`}>{value}%</span>
            {showNudges && (
              <>
                <button type="button" className={styles.nudgeBtn} onClick={() => onChange(clamp(value + 1))}>+1</button>
                <button type="button" className={styles.nudgeBtn} onClick={() => onChange(clamp(value + 5))}>+5</button>
              </>
            )}
          </div>
        </div>
        <span>{rightLabel}</span>
      </div>
    </div>
  );
}
