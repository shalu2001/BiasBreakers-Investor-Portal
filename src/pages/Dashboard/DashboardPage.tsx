import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPortfolioCandles, type Candle, type Holding } from '../../api/portfolio';
import { getUniverse } from '../../api/portal';
import { getNarratives, type NarrativeItem } from '../../api/narratives';
import { HoldingCard } from '../../components/HoldingCard';
import { Carousel } from '../../components/Carousel';
import { BehaviouralInsightCard } from '../../components/BehaviouralInsightCard';
import { useBehaviouralProfile } from '../../session/useBehaviouralProfile';
import { useSession } from '../../session/SessionContext';
import styles from './DashboardPage.module.css';

interface TickerSnapshot {
  ticker: string;
  name: string;
  changePct: number;
  candles: Candle[];
}

export function DashboardPage() {
  const { persona, confidence } = useBehaviouralProfile();
  const { recommendation } = useSession();
  // Same gate as RequirePortfolio -- no point linking to /portfolio before
  // an optimization has actually selected any stocks.
  const hasSelectedStocks = (recommendation ?? []).some(
    (row) => row.ticker !== 'CASH' && row.recommendedPct > 0,
  );
  // The whole S&P SL20 universe, always -- this carousel is a market
  // snapshot, not "your holdings", so it doesn't filter down to whatever a
  // recommendation happened to select.
  const [tickerData, setTickerData] = useState<TickerSnapshot[]>([]);
  const [snapshotStatus, setSnapshotStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [narratives, setNarratives] = useState<NarrativeItem[]>([]);
  const [narrativeStatus, setNarrativeStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const universe = await getUniverse();
        const series = await getPortfolioCandles(universe.map((u) => u.ticker));
        if (cancelled) return;
        const byTicker = new Map(series.map((s) => [s.ticker, s]));
        setTickerData(
          universe.map((u) => ({
            ticker: u.ticker,
            name: u.name,
            changePct: byTicker.get(u.ticker)?.changePct ?? 0,
            candles: byTicker.get(u.ticker)?.candles ?? [],
          })),
        );
        setSnapshotStatus('ready');
      } catch {
        if (!cancelled) setSnapshotStatus('error');
      }
    })();
    getNarratives()
      .then((res) => {
        if (cancelled) return;
        setNarratives(res.narratives);
        setNarrativeStatus('ready');
      })
      .catch(() => !cancelled && setNarrativeStatus('error'));
    return () => {
      cancelled = true;
    };
  }, []);

  // Weight only means something for tickers the last optimization actually
  // selected -- 0 (not fabricated) for the rest of the universe.
  const weightByTicker = new Map((recommendation ?? []).map((row) => [row.ticker, row.recommendedPct]));
  const holdings: Holding[] = tickerData.map((t) => ({
    ticker: t.ticker,
    name: t.name,
    sector: '',
    weightPct: weightByTicker.get(t.ticker) ?? 0,
    changePct: t.changePct,
    candles: t.candles,
  }));

  return (
    <div className={styles.page}>
      <div className={styles.archetypeWrap}>
        <BehaviouralInsightCard persona={persona} confidence={confidence} variant="compact" />
      </div>

      <div className={styles.snapshotHeader}>
        <h2 className={styles.sectionTitle}>Portfolio snapshot</h2>
        <div className={styles.snapshotActions}>
          {hasSelectedStocks && (
            <Link to="/portfolio" className={styles.viewFullLink}>
              View full portfolio
            </Link>
          )}
          <Link to="/recommend" className={styles.optimizeButton}>
            Optimize portfolio ↻
          </Link>
        </div>
      </div>

      <div className={styles.snapshotCarousel}>
        {snapshotStatus === 'loading' && (
          <p className={styles.narrativeMessage}>Loading market snapshot…</p>
        )}
        {snapshotStatus === 'error' && (
          <p className={styles.narrativeMessage}>Couldn’t load market data right now.</p>
        )}
        {snapshotStatus === 'ready' && (
          <Carousel ariaLabel="Portfolio snapshot">
            {holdings.map((holding) => (
              <HoldingCard
                key={holding.ticker}
                holding={holding}
                dateRangeLabel="17 Jul – 28 Jul 2026"
                footerNote="Click a candle for detail"
              />
            ))}
          </Carousel>
        )}
      </div>

      <div className={styles.newsHeader}>
        <h2 className={styles.sectionTitle}>Latest narratives</h2>
        <Link to="/news" className={styles.viewFullLink}>
          View all news
        </Link>
      </div>

      <div className={styles.narrativeList}>
        {narrativeStatus === 'loading' && (
          <p className={styles.narrativeMessage}>Loading latest narratives…</p>
        )}
        {narrativeStatus === 'error' && (
          <p className={styles.narrativeMessage}>Couldn’t load narratives right now.</p>
        )}
        {narrativeStatus === 'ready' && narratives.length === 0 && (
          <p className={styles.narrativeMessage}>No narratives available yet.</p>
        )}
        {narratives.map((n) => (
          <div key={n.id} className={styles.narrativeItem}>
            <div className={styles.newsTags}>
              <span className={styles.categoryTag}>{n.type === 'macro' ? 'Macro' : 'Micro'}</span>
            </div>
            <p className={styles.narrativeTitle}>{n.title}</p>
            {n.stocks.length > 0 && (
              <div className={styles.stockChips}>
                {n.stocks.map((s) => (
                  <span key={`${n.id}-${s.ticker}-${s.name}`} className={styles.stockChip}>
                    {s.ticker && <span className={styles.stockTicker}>{s.ticker}</span>}
                    <span className={styles.stockName}>{s.name}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
