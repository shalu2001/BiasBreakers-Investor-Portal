import { useEffect, useState } from 'react';
import { getPersona, type PersonaProfile } from '../../api/persona';
import {
  getRecommendation,
  getPastRecommendations,
  submitRecommendationFeedback,
  type ReallocationRow,
  type PastRecommendation,
} from '../../api/recommendation';
import {
  PERSONA_FIXTURE,
  RECOMMENDATION_FIXTURE,
  PAST_RECOMMENDATIONS_FIXTURE,
} from '../../mocks/fixtures';
import styles from './RecommendPage.module.css';

function changeBadge(current: number, recommended: number) {
  const diff = recommended - current;
  if (diff === 0) return { label: 'Hold', className: styles.badgeHold };
  if (diff > 0) return { label: `Buy +${diff}%`, className: styles.badgeBuy };
  return { label: `Sell ${diff}%`, className: styles.badgeSell };
}

export function RecommendPage() {
  const [persona, setPersona] = useState<PersonaProfile>(PERSONA_FIXTURE);
  const [rows, setRows] = useState<ReallocationRow[]>(RECOMMENDATION_FIXTURE);
  const [pastRecommendations, setPastRecommendations] = useState<PastRecommendation[]>(
    PAST_RECOMMENDATIONS_FIXTURE,
  );
  const [rating, setRating] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    getPersona().then(setPersona).catch(() => setPersona(PERSONA_FIXTURE));
    getRecommendation().then(setRows).catch(() => setRows(RECOMMENDATION_FIXTURE));
    getPastRecommendations()
      .then(setPastRecommendations)
      .catch(() => setPastRecommendations(PAST_RECOMMENDATIONS_FIXTURE));
  }, []);

  async function handleSubmitFeedback() {
    if (rating === null) return;
    await submitRecommendationFeedback(rating).catch(() => undefined);
    setSubmitted(true);
  }

  return (
    <div className={styles.page}>
      <span className={styles.eyebrow}>
        Reallocation, tuned to {persona.archetype.toLowerCase()}
      </span>
      <h1 className={styles.title}>Recommended reallocation</h1>
      <p className={styles.subcopy}>
        Based on your archetype and current holdings, here's how the model would shift your
        weights. This is a suggestion — nothing changes until you approve it.
      </p>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Stock name</th>
            <th>Current</th>
            <th>Recommended</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const badge = changeBadge(row.currentPct, row.recommendedPct);
            return (
              <tr key={row.ticker}>
                <td className={styles.ticker}>{row.ticker}</td>
                <td>{row.name}</td>
                <td>{row.currentPct}%</td>
                <td>{row.recommendedPct}%</td>
                <td>
                  <span className={badge.className}>{badge.label}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <section className={styles.reactionCard}>
        <span className={styles.eyebrow}>Your reaction</span>
        <h2 className={styles.reactionTitle}>How do you feel about this new allocation?</h2>
        <p className={styles.reactionSubcopy}>
          Your answer helps tune future recommendations — it feeds straight back into the
          optimization loop.
        </p>

        <div className={styles.ratingRow}>
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              className={rating === value ? styles.ratingButtonActive : styles.ratingButton}
              onClick={() => setRating(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <div className={styles.ratingLabels}>
          <span>Uncomfortable</span>
          <span>Very comfortable</span>
        </div>

        <button
          type="button"
          className={styles.submitButton}
          disabled={rating === null}
          onClick={handleSubmitFeedback}
        >
          {submitted ? 'Feedback submitted' : 'Submit feedback'}
        </button>
      </section>

      <h2 className={styles.sectionTitle}>Past recommendations</h2>
      <div className={styles.pastList}>
        {pastRecommendations.map((item) => (
          <div key={item.date} className={styles.pastItem}>
            <div className={styles.pastDate}>{item.date.toUpperCase()}</div>
            <p className={styles.pastDescription}>{item.description}</p>
            <div className={styles.pastFooter}>
              <span>Rated {item.rating}/5</span>
              <a href="#">View →</a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
