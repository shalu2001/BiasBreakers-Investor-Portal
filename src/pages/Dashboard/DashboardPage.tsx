import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PersonaProfile } from '../../api/persona';
import { getPortfolio, type Holding } from '../../api/portfolio';
import { getNews, type NewsItem } from '../../api/news';
import { PERSONA_FIXTURE, PORTFOLIO_FIXTURE, NEWS_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { useSession } from '../../session/SessionContext';
import { profileToPersona, buildInsight } from '../../session/profileToPersona';
import { getProfile } from '../../api/portal';
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
  const [plan, setPlan] = useState<{ amount: number | null; goal: string | null }>({
    amount: onboarding.investmentAmount,
    goal: onboarding.goal,
  });
  const [holdings, setHoldings] = useState<Holding[]>(PORTFOLIO_FIXTURE);
  const [news, setNews] = useState<NewsItem[]>(NEWS_FIXTURE.slice(0, 3));

  useEffect(() => {
    let cancelled = false;

    // Source of truth for a signed-in user is their saved Cosmos profile.
    // Fall back to the in-session game result, then to the mock persona.
    (async () => {
      try {
        const saved = await getProfile();
        if (cancelled) return;
        const p = saved.parameters ?? {};
        const mapped =
          p.lambda != null || p.gamma != null
            ? profileToPersona({ alpha: p.alpha ?? null, lambda: p.lambda ?? null, gamma: p.gamma ?? null })
            : null;
        if (mapped) setPersona(mapped);
        else if (profile) setPersona(profileToPersona(profile) ?? PERSONA_FIXTURE);
        const ob = saved.onboarding ?? {};
        if (ob.investmentAmount != null || ob.goal) {
          setPlan({ amount: ob.investmentAmount ?? null, goal: ob.goal ?? null });
        }
      } catch {
        if (!cancelled) {
          const mapped = profile ? profileToPersona(profile) : null;
          if (mapped) setPersona(mapped);
        }
      }
    })();

    getPortfolio().then((h) => !cancelled && setHoldings(h)).catch(() => !cancelled && setHoldings(PORTFOLIO_FIXTURE));
    getNews().then((n) => !cancelled && setNews(n.slice(0, 3))).catch(() => !cancelled && setNews(NEWS_FIXTURE.slice(0, 3)));

    return () => {
      cancelled = true;
    };
  }, [profile]);

  const insight = buildInsight(persona);

  return (
    <div className={styles.page}>
      <section className={styles.archetypeCard}>
        <span className={styles.eyebrow}>Your investing personality</span>
        <h1 className={styles.archetypeTitle}>{persona.archetype}</h1>
        <p className={styles.narrative}>{insight.narrative}</p>

        <div className={styles.traitGrid}>
          {insight.traits.map((t) => (
            <div key={t.key} className={styles.trait}>
              <div className={styles.traitHead}>
                <span className={styles.traitLabel}>{t.label}</span>
                <span className={styles.traitScore}>
                  {t.score}
                  <span className={styles.traitScoreMax}>/100</span>
                </span>
              </div>
              <div className={styles.traitTrack}>
                <span className={styles.traitFill} style={{ width: `${t.score}%` }} />
              </div>
              <p className={styles.traitMeaning}>{t.meaning}</p>
            </div>
          ))}
        </div>

        <div className={styles.insightCols}>
          <div className={styles.insightCol}>
            <span className={styles.insightColTitle}>What works in your favour</span>
            <ul className={styles.insightList}>
              {insight.strengths.map((s, i) => (
                <li key={i} className={styles.strengthItem}>{s}</li>
              ))}
            </ul>
          </div>
          <div className={styles.insightCol}>
            <span className={styles.insightColTitle}>What to watch</span>
            <ul className={styles.insightList}>
              {insight.watchouts.map((w, i) => (
                <li key={i} className={styles.watchItem}>{w}</li>
              ))}
            </ul>
          </div>
        </div>

        <p className={styles.implication}>
          <strong className={styles.implicationLead}>How we'll manage your money: </strong>
          {insight.strategy}
        </p>

        {plan.amount != null && (
          <p className={styles.planLine}>
            Your plan: LKR {new Intl.NumberFormat('en-LK').format(plan.amount)}
            {plan.goal && GOAL_LABELS[plan.goal] ? ` · ${GOAL_LABELS[plan.goal]}` : ''}
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
