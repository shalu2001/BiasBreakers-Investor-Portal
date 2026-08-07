import { CandlestickChart } from '../../components/CandlestickChart';
import { Spinner } from '../../components/ui';
import type { Candle } from '../../api/portfolio';
import type { HistoryBar } from '../../api/behaviouralGame';
import styles from './game.module.css';

// Adapts the game backend's OHLC history (indexed by relative "day") to the
// portal's shared CandlestickChart (lightweight-charts), so the game's chart is
// visually identical to the rest of the app. Relative day indices are mapped to
// synthetic ascending dates, which lightweight-charts requires as its time axis.
const BASE = Date.UTC(2000, 0, 1);
function dayToTime(day: number): string {
  return new Date(BASE + day * 86_400_000).toISOString().slice(0, 10);
}

export function GameCandles({ history }: { history: HistoryBar[] }) {
  if (!history || history.length < 5) {
    return (
      <div className={styles.chartWrap}>
        <div
          className={styles.chartBuilding}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}
        >
          <Spinner size={22} />
          <span>Building price history…</span>
        </div>
      </div>
    );
  }
  const candles: Candle[] = history.map((b) => ({
    time: dayToTime(b.day),
    open: b.open, high: b.high, low: b.low, close: b.close,
  }));
  return (
    <div className={styles.chartWrap}>
      <CandlestickChart candles={candles} height={160} />
    </div>
  );
}
