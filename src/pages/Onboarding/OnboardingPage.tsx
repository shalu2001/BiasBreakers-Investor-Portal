import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { submitHasExistingPortfolio } from '../../api/onboarding';
import styles from './OnboardingPage.module.css';

export function OnboardingPage() {
  const navigate = useNavigate();
  const [hasExisting, setHasExisting] = useState<boolean | null>(null);

  async function handleContinue() {
    if (hasExisting === null) return;
    await submitHasExistingPortfolio(hasExisting);
    // "Yes" hands off to the trading simulation (a separate app) to enter
    // holdings before the dashboard has anything to show.
    navigate('/');
  }

  return (
    <div className={styles.page}>
      <span className={styles.eyebrow}>Portfolio</span>
      <h1 className={styles.question}>Do you already hold any S&amp;P SL20 stocks?</h1>
      <p className={styles.subcopy}>
        If you have an existing portfolio, we'll fold it into your analysis instead of starting
        from zero.
      </p>

      <div className={styles.options}>
        <button
          type="button"
          className={hasExisting === true ? styles.optionSelected : styles.option}
          onClick={() => setHasExisting(true)}
        >
          <strong>Yes</strong>
          <span>I hold shares already.</span>
        </button>
        <button
          type="button"
          className={hasExisting === false ? styles.optionSelected : styles.option}
          onClick={() => setHasExisting(false)}
        >
          <strong>No</strong>
          <span>I'm starting fresh.</span>
        </button>
      </div>

      <div className={styles.footer}>
        <button
          type="button"
          className={styles.continueButton}
          disabled={hasExisting === null}
          onClick={handleContinue}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}
