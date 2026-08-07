import { Link } from 'react-router-dom';
import { BehaviouralInsightCard } from '../../components/BehaviouralInsightCard';
import { useBehaviouralProfile } from '../../session/useBehaviouralProfile';
import styles from './BehaviouralProfilePage.module.css';

export function BehaviouralProfilePage() {
  const { persona, confidence } = useBehaviouralProfile();

  return (
    <div className={styles.page}>
      <Link to="/" className={styles.back}>← Back to dashboard</Link>
      <div className={styles.intro}>
        <h1 className={styles.title}>Your behavioural profile</h1>
        <p className={styles.sub}>
          How you actually invest — read from the decisions you made, not a questionnaire. We use
          this to tailor how your portfolio is managed for you.
        </p>
      </div>
      <BehaviouralInsightCard persona={persona} confidence={confidence} variant="full" />
    </div>
  );
}
