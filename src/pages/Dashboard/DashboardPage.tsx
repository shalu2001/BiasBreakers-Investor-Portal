import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPortfolio, type Holding } from '../../api/portfolio';
import { getNarratives, type NarrativeItem } from '../../api/narratives';
import { PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { Carousel } from '../../components/Carousel';
import { BehaviouralInsightCard } from '../../components/BehaviouralInsightCard';
import { useBehaviouralProfile } from '../../session/useBehaviouralProfile';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  const { persona, confidence } = useBehaviouralProfile();
  const [holdings, setHoldings] = useState<Holding[]>(PORTFOLIO_FIXTURE);
  const [narratives, setNarratives] = useState<NarrativeItem[]>([]);
  const [narrativeStatus, setNarrativeStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    getPortfolio().then((h) => !cancelled && setHoldings(h)).catch(() => !cancelled && setHoldings(PORTFOLIO_FIXTURE));
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

  return (
    <div className={styles.page}>
      <div className={styles.archetypeWrap}>
        <BehaviouralInsightCard persona={persona} confidence={confidence} variant="compact" />
      </div>

      <div className={styles.snapshotHeader}>
        <h2 className={styles.sectionTitle}>Portfolio snapshot</h2>
        <div className={styles.snapshotActions}>
          <Link to="/portfolio" className={styles.viewFullLink}>
            View full portfolio
          </Link>
          <Link to="/recommend" className={styles.optimizeButton}>
            Optimize portfolio ↻
          </Link>
        </div>
      </div>

      <div className={styles.snapshotCarousel}>
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
