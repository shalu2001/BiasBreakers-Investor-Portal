import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPersona, type PersonaProfile } from '../../api/persona';
import { getPortfolio, type Holding } from '../../api/portfolio';
import { getNews, type NewsItem } from '../../api/news';
import { PERSONA_FIXTURE, PORTFOLIO_FIXTURE, NEWS_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { useSession } from '../../session/SessionContext';
import { profileToPersona } from '../../session/profileToPersona';
import styles from './DashboardPage.module.css';

const GOAL_LABELS: Record<string, string> = {
  grow: 'Grow wealth',
  income: 'Steady income',
  learn: 'Learn & experiment',
  beat: 'Beat the market',
};

export function DashboardPage() {
  const { profile, onboarding } = useSession();
  const [persona, setPersona] = useState<PersonaProfile>(
    () => (profile ? profileToPersona(profile) : null) ?? PERSONA_FIXTURE,
  );
  const [holdings, setHoldings] = useState<Holding[]>(PORTFOLIO_FIXTURE);
  const [news, setNews] = useState<NewsItem[]>(NEWS_FIXTURE.slice(0, 3));

  useEffect(() => {
    // The behavioural game's live result (if the user just played) takes
    // priority over the API/fixture persona.
    const mapped = profile ? profileToPersona(profile) : null;
    if (mapped) setPersona(mapped);
    else getPersona().then(setPersona).catch(() => setPersona(PERSONA_FIXTURE));
    getPortfolio().then(setHoldings).catch(() => setHoldings(PORTFOLIO_FIXTURE));
    getNews()
      .then((items) => setNews(items.slice(0, 3)))
      .catch(() => setNews(NEWS_FIXTURE.slice(0, 3)));
  }, [profile]);

  return (
    <div className={styles.page}>
      <section className={styles.archetypeCard}>
        <span className={styles.eyebrow}>Your archetype</span>
        <h1 className={styles.archetypeTitle}>{persona.archetype}</h1>
        <p className={styles.archetypeSummary}>{persona.summary}</p>
        {onboarding.investmentAmount != null && (
          <p className={styles.archetypeSummary} style={{ marginTop: 10, fontWeight: 600 }}>
            Your plan: LKR {new Intl.NumberFormat('en-LK').format(onboarding.investmentAmount)}
            {onboarding.goal && GOAL_LABELS[onboarding.goal]
              ? ` · ${GOAL_LABELS[onboarding.goal]}`
              : ''}
          </p>
        )}
        <Link to="/portfolio" className={styles.viewMoreLink}>
          View more
        </Link>
      </section>

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
          <div key={item.headline} className={styles.newsItem}>
            <div className={styles.newsTags}>
              {item.ticker && <span className={styles.tickerTag}>{item.ticker}</span>}
              <span className={styles.categoryTag}>
                {item.category === 'macro' ? 'Macro' : 'Micro'}
              </span>
            </div>
            <div className={styles.newsHeadline}>{item.headline}</div>
            <div className={styles.newsMeta}>
              {item.source} · {item.timeAgo}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
