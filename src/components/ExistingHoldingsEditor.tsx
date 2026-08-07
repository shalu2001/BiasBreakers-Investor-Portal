import { useEffect, useState } from 'react';
import { getUniverse, type ExistingHolding, type UniverseTicker } from '../api/portal';
import styles from './ExistingHoldingsEditor.module.css';

interface Row {
  ticker: string;
  shares: string;
}

interface Props {
  value: ExistingHolding[];
  onChange: (holdings: ExistingHolding[]) => void;
}

function toRows(holdings: ExistingHolding[]): Row[] {
  return holdings.map((h) => ({ ticker: h.ticker, shares: String(h.shares) }));
}

// Complete rows (ticker chosen, shares > 0) only -- an in-progress empty row
// (freshly added, nothing picked yet) shouldn't be reported upward as a
// "holding" until it's actually filled in.
function toHoldings(rows: Row[]): ExistingHolding[] {
  return rows
    .filter((r) => r.ticker && Number(r.shares) > 0)
    .map((r) => ({ ticker: r.ticker, shares: Number(r.shares) }));
}

export function ExistingHoldingsEditor({ value, onChange }: Props) {
  const [universe, setUniverse] = useState<UniverseTicker[]>([]);
  const [universeError, setUniverseError] = useState(false);
  // Seeded once from `value` -- this component owns row-level editing state
  // (including an in-progress empty row) locally, and only reports the
  // valid subset upward via onChange, rather than making the parent manage
  // ephemeral per-row state too.
  const [rows, setRows] = useState<Row[]>(() => (value.length > 0 ? toRows(value) : [{ ticker: '', shares: '' }]));

  useEffect(() => {
    let cancelled = false;
    getUniverse()
      .then((u) => !cancelled && setUniverse(u))
      .catch(() => !cancelled && setUniverseError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  function update(rows: Row[]) {
    setRows(rows);
    onChange(toHoldings(rows));
  }

  function setTicker(i: number, ticker: string) {
    update(rows.map((r, idx) => (idx === i ? { ...r, ticker } : r)));
  }

  function setShares(i: number, shares: string) {
    const cleaned = shares.replace(/[^0-9]/g, '');
    update(rows.map((r, idx) => (idx === i ? { ...r, shares: cleaned } : r)));
  }

  function addRow() {
    update([...rows, { ticker: '', shares: '' }]);
  }

  function removeRow(i: number) {
    const next = rows.filter((_, idx) => idx !== i);
    update(next.length > 0 ? next : [{ ticker: '', shares: '' }]);
  }

  const usedTickers = new Set(rows.map((r) => r.ticker).filter(Boolean));
  const canAddMore = universe.some((u) => !usedTickers.has(u.ticker));

  if (universeError) {
    return (
      <p className={styles.error}>
        Couldn't load the stock list right now — you can skip this and add your holdings later
        from Account settings.
      </p>
    );
  }

  return (
    <div className={styles.editor}>
      {rows.map((row, i) => (
        <div key={i} className={styles.row}>
          <select
            className={styles.select}
            value={row.ticker}
            onChange={(e) => setTicker(i, e.target.value)}
          >
            <option value="">Select a stock…</option>
            {universe
              .filter((u) => u.ticker === row.ticker || !usedTickers.has(u.ticker))
              .map((u) => (
                <option key={u.ticker} value={u.ticker}>
                  {u.name}
                </option>
              ))}
          </select>
          <div className={styles.weightField}>
            <input
              className={styles.weightInput}
              inputMode="numeric"
              placeholder="0"
              value={row.shares}
              onChange={(e) => setShares(i, e.target.value)}
            />
            <span className={styles.weightSuffix}>sh</span>
          </div>
          <button
            type="button"
            className={styles.removeButton}
            onClick={() => removeRow(i)}
            aria-label="Remove holding"
          >
            ×
          </button>
        </div>
      ))}

      <button
        type="button"
        className={styles.addButton}
        onClick={addRow}
        disabled={!canAddMore || universe.length === 0}
      >
        + Add holding
      </button>

      <p className={styles.hint}>
        Enter the number of shares you hold for each — we'll work out the value and weighting
        using the current price. Only need what you're sure of — leave anything out, or skip this
        entirely and add it later from Account settings.
      </p>
    </div>
  );
}
