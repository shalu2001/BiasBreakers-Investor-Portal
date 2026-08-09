import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPortfolio, type Holding } from '../../api/portfolio';
import { getNews, type NewsItem } from '../../api/news';
import { formatTimeAgo } from '../../utils/timeAgo';
import { PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { BehaviouralInsightCard } from '../../components/BehaviouralInsightCard';
import { useBehaviouralProfile } from '../../session/useBehaviouralProfile';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  const { persona, confidence } = useBehaviouralProfile();
  const [holdings, setHoldings] = useState<Holding[]>(PORTFOLIO_FIXTURE);
  const [news, setNews] = useState<NewsItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    getPortfolio().then((h) => !cancelled && setHoldings(h)).catch(() => !cancelled && setHoldings(PORTFOLIO_FIXTURE));
    getNews().then((n) => !cancelled && setNews(n.slice(0, 3))).catch(() => undefined);
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
          <button type="button" className={styles.optimizeButton}>
            Optimize portfolio ↻
          </button>
        </div>
      </div>

      <div className={styles.snapshotScroll}>
        {holdings.map((holding) => (
          <div key={holding.ticker} className={styles.snapshotCard}>
            <HoldingCard
              holding={holding}
              dateRangeLabel="17 Jul – 28 Jul 2026"
              footerNote="Click a candle for detail"
            />
          </div>
        ))}
      </div>

      <div className={styles.newsHeader}>
        <h2 className={styles.sectionTitle}>Market news</h2>
        <Link to="/news" className={styles.viewFullLink}>
          View all news
        </Link>
      </div>

      <div className={styles.newsList}>
        {news.map((item) => (
          <Link
            key={item.headline}
            to="/news/article"
            state={{ article: item }}
            className={styles.newsItem}
          >
            <div className={styles.newsTags}>
              {item.ticker && <span className={styles.tickerTag}>{item.ticker}</span>}
              <span className={styles.categoryTag}>
                {item.category === 'macro' ? 'Macro' : 'Micro'}
              </span>
            </div>
            <div className={styles.newsHeadline}>{item.headline}</div>
            <div className={styles.newsMeta}>
              {item.source} · {formatTimeAgo(item.publishedDate)}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
