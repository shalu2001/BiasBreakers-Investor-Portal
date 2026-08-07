import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PersonaProfile } from '../../api/persona';
import { getPortfolio, type Holding } from '../../api/portfolio';
import { getNews, type NewsItem } from '../../api/news';
import { formatTimeAgo } from '../../utils/timeAgo';
import { PERSONA_FIXTURE, PORTFOLIO_FIXTURE, NEWS_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { useSession } from '../../session/SessionContext';
import { profileToPersona, buildInsight, type TraitConfidence } from '../../session/profileToPersona';
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
  const [confidence, setConfidence] = useState<TraitConfidence>({});

  useEffect(() => {
    let cancelled = false;

    // Source of truth for a signed-in user is their saved Cosmos profile.
    // Fall back to the in-session game result, then to the mock persona.
    (async () => {
      try {
        const saved = await getProfile();
        if (cancelled) return;
        const p = saved.parameters ?? {};
        const conf = (p.confidence ?? {}) as { lambda?: { level?: string }; gamma?: { level?: string } };
        setConfidence({ lambda: conf.lambda?.level, gamma: conf.gamma?.level });
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

  const insight = buildInsight(persona, confidence);

  return (
    <div className={styles.page}>
      <section className={styles.archetypeCard}>
        <span className={styles.eyebrow}>Your investing personality</span>
        <h1 className={styles.archetypeTitle}>{persona.archetype}</h1>
        <p className={styles.narrative}>{insight.narrative}</p>

        {insight.caveat && (
          <div className={styles.caveat}>
            <span className={styles.caveatIcon}>✦</span>
            <span>{insight.caveat}</span>
          </div>
        )}

        <div className={styles.traitGrid}>
          {insight.traits.map((t) => (
            <div key={t.key} className={styles.trait}>
              <div className={styles.traitHead}>
                <span className={styles.traitLabel}>{t.label}</span>
                {!t.reliable && <span className={styles.traitProvisional}>early read</span>}
              </div>
              <div className={styles.traitScore}>
                {t.score}
                <span className={styles.traitScoreMax}>/100</span>
              </div>
              <div className={styles.traitTrack}>
                <span
                  className={styles.traitFill}
                  style={{ width: `${t.score}%`, opacity: t.reliable ? 1 : 0.45 }}
                />
              </div>
              <p className={styles.traitMeaning}>{t.meaning}</p>
            </div>
          ))}
        </div>

        <div className={styles.insightPanels}>
          <div className={`${styles.insightPanel} ${styles.strengthsPanel}`}>
            <div className={styles.panelHead}>What works for you</div>
            <ul className={styles.panelList}>
              {insight.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
          <div className={`${styles.insightPanel} ${styles.watchPanel}`}>
            <div className={styles.panelHead}>Worth watching</div>
            <ul className={styles.panelList}>
              {insight.watchouts.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className={styles.strategyBox}>
          <span className={styles.strategyLabel}>How we'll manage your money</span>
          <p className={styles.strategyText}>{insight.strategy}</p>
        </div>

        <div className={styles.cardFooter}>
          {plan.amount != null && (
            <span className={styles.planLine}>
              Your plan: <b>LKR {new Intl.NumberFormat('en-LK').format(plan.amount)}</b>
              {plan.goal && GOAL_LABELS[plan.goal] ? ` · ${GOAL_LABELS[plan.goal]}` : ''}
            </span>
          )}
          <Link to="/behavioural-game" className={styles.retakeLink}>
            Retake the game →
          </Link>
        </div>
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
              {item.source} · {formatTimeAgo(item.publishedDate)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
