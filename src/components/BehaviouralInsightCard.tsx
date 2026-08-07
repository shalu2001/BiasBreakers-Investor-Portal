import { Link } from 'react-router-dom';
import { buildInsight, type TraitConfidence } from '../session/profileToPersona';
import type { PersonaProfile } from '../api/persona';
import styles from './BehaviouralInsightCard.module.css';

interface Props {
  persona: PersonaProfile;
  confidence?: TraitConfidence;
  variant?: 'compact' | 'full';
}

// One source of truth for the investing-personality card. `compact` is the
// trimmed dashboard teaser (archetype + one-line summary + trait bars + a link
// to the full page); `full` is the complete profile with narrative, strengths,
// watch-outs and strategy. Keeping both in one component keeps them in sync.
export function BehaviouralInsightCard({ persona, confidence, variant = 'full' }: Props) {
  const insight = buildInsight(persona, confidence);
  // archetype = "<risk> <style>", e.g. "Balanced Momentum-Seeker"
  const [riskWord, ...styleWords] = persona.archetype.split(' ');
  const styleWord = styleWords.join(' ');

  if (variant === 'compact') {
    return (
      <section className={styles.card}>
        <span className={styles.eyebrow}>Your investing personality</span>
        <h1 className={styles.archetypeTitle}>{persona.archetype}</h1>
        <p className={styles.summary}>{persona.summary ?? insight.narrative}</p>

        <div className={styles.traitGridCompact}>
          {insight.traits.map((t) => (
            <div key={t.key} className={styles.traitCompact}>
              <div className={styles.traitHead}>
                <span className={styles.traitLabel}>{t.label}</span>
                {!t.reliable && <span className={styles.traitProvisional}>early read</span>}
              </div>
              <div className={styles.traitTrack}>
                <span
                  className={styles.traitFill}
                  style={{ width: `${t.score}%`, opacity: t.reliable ? 1 : 0.45 }}
                />
              </div>
              <span className={styles.traitScoreSm}>
                {t.score}
                <span className={styles.traitScoreMax}>/100</span>
              </span>
            </div>
          ))}
        </div>

        <Link to="/behavioural-profile" className={styles.viewFull}>
          View full profile →
        </Link>
      </section>
    );
  }

  return (
    <section className={styles.card}>
      <span className={styles.eyebrow}>Your investing personality</span>
      <h1 className={styles.archetypeTitle}>{persona.archetype}</h1>
      <div className={styles.axes}>
        <span className={styles.axisChip}>
          <em className={styles.axisKey}>Risk appetite</em>
          {riskWord}
        </span>
        <span className={styles.axisChip}>
          <em className={styles.axisKey}>Market style</em>
          {styleWord}
        </span>
      </div>
      <p className={styles.narrative}>{insight.narrative}</p>

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
    </section>
  );
}
