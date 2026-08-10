import { useEffect, useState } from 'react';
import { getPortfolioCandles, type Candle, type Holding, type PortfolioRange } from '../../api/portfolio';
import { useSession } from '../../session/SessionContext';
import { HoldingCard } from '../../components/HoldingCard';
import { EmptyState, LoadingState } from '../../components/ui';
import styles from './PortfolioPage.module.css';

const RANGES: PortfolioRange[] = ['1M', '3M', '6M', '1Y'];

// Chart-ready shape for HoldingCard, built from the investor's own
// recommendation rows (weight, name) joined against real candle data for
// just those tickers -- no fixture fallback, and no re-running the
// optimizer just to render a chart. `sector` isn't backed by real data yet
// (same gap the old /portfolio/holdings response had) -- left blank rather
// than invented.
type DisplayHolding = Holding;

function toDisplayHolding(ticker: string, name: string, weightPct: number, chart?: { changePct: number; candles: Candle[] }): DisplayHolding {
  return {
    ticker,
    name,
    sector: '',
    weightPct,
    changePct: chart?.changePct ?? 0,
    candles: chart?.candles ?? [],
  };
}

export function PortfolioPage() {
  const { recommendation } = useSession();
  const [range, setRange] = useState<PortfolioRange>('3M');
  const [holdings, setHoldings] = useState<DisplayHolding[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  // The stocks the last approved optimization actually selected -- CASH and
  // anything the model zeroed out have nothing to chart.
  const selectedRows = (recommendation ?? []).filter(
    (row) => row.ticker !== 'CASH' && row.recommendedPct > 0,
  );

  useEffect(() => {
    if (selectedRows.length === 0) {
      setHoldings([]);
      setStatus('ready');
      return;
    }
    let cancelled = false;
    setStatus('loading');
    getPortfolioCandles(
      selectedRows.map((row) => row.ticker),
      range,
    )
      .then((series) => {
        if (cancelled) return;
        const byTicker = new Map(series.map((s) => [s.ticker, s]));
        setHoldings(
          selectedRows.map((row) =>
            toDisplayHolding(row.ticker, row.name, row.recommendedPct, byTicker.get(row.ticker)),
          ),
        );
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, recommendation]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Your portfolio</h1>
        <div className={styles.rangeTabs}>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={r === range ? styles.rangeTabActive : styles.rangeTab}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <p className={styles.helperText}>
        The stocks selected by your last optimization, shown in percentage terms — prices move
        constantly, so weight is what matters here. Hover a candle for its close.
      </p>

      {status === 'loading' ? (
        <LoadingState label="Loading your portfolio…" />
      ) : status === 'error' ? (
        <EmptyState
          icon="⌾"
          title="Couldn't load your portfolio"
          message="Something went wrong fetching your holdings. Try again shortly."
        />
      ) : holdings.length === 0 ? (
        <EmptyState
          icon="⌾"
          title="No holdings to show yet"
          message="Once you optimize your portfolio, your selected positions and their recent moves will appear here."
        />
      ) : (
        <div className={styles.grid}>
          {holdings.map((holding) => (
            <HoldingCard key={holding.ticker} holding={holding} chartHeight={280} />
          ))}
        </div>
      )}
    </div>
  );
}
