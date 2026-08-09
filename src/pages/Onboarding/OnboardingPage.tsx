import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { saveOnboarding, type ExistingHolding } from '../../api/portal';
import { useSession } from '../../session/SessionContext';
import { ExistingHoldingsEditor } from '../../components/ExistingHoldingsEditor';
import styles from './OnboardingPage.module.css';

const GOALS = [
  { key: 'grow', title: 'Grow my wealth', sub: 'Long-term capital growth.' },
  { key: 'income', title: 'Steady income', sub: 'Prioritise stability over big swings.' },
  { key: 'learn', title: 'Learn & experiment', sub: 'Get comfortable with investing.' },
  { key: 'beat', title: 'Beat the market', sub: 'Chase above-index returns.' },
];

export function OnboardingPage() {
  const navigate = useNavigate();
  const { setOnboarding } = useSession();

  const [step, setStep] = useState(1);
  const [hasExisting, setHasExisting] = useState<boolean | null>(null);
  const [holdings, setHoldings] = useState<ExistingHolding[]>([]);
  const [amount, setAmount] = useState('');
  const [goal, setGoal] = useState<string | null>(null);

  // The holdings step only exists when they said "yes" -- computed from
  // current state so it also disappears cleanly if they go back and change
  // their answer to "no". No separate "amount" step for existing-portfolio
  // investors either: their budget is derived from what their entered
  // holdings are currently worth (shares x current price), not asked for.
  const steps = hasExisting ? ['existing', 'holdings', 'goal'] : ['existing', 'amount', 'goal'];
  const totalSteps = steps.length;
  const current = steps[step - 1];

  const amountNum = Number(amount.replace(/[^0-9.]/g, ''));
  const amountValid = amount.trim() !== '' && !Number.isNaN(amountNum) && amountNum > 0;

  const canProceed =
    current === 'existing' ? hasExisting !== null
    : current === 'holdings' ? true // optional -- always skippable
    : current === 'amount' ? amountValid
    : goal !== null;

  async function handleFinish() {
    const answers = {
      hasExistingPortfolio: hasExisting,
      investmentAmount: amountValid ? amountNum : null,
      goal,
      existingHoldings: hasExisting ? holdings : null,
    };
    setOnboarding(answers);
    // Save to the user's profile in Cosmos. Best-effort: a DB/backend hiccup
    // must not trap the user out of the game.
    try {
      await saveOnboarding(answers);
    } catch {
      /* keep going on the local session copy */
    }
    navigate('/behavioural-game');
  }

  return (
    <div className={styles.page}>
      <span className={styles.eyebrow}>
        Onboarding · Step {step} of {totalSteps}
      </span>
      <div className={styles.progress} aria-hidden>
        <span className={styles.progressFill} style={{ width: `${(step / totalSteps) * 100}%` }} />
      </div>

      {current === 'existing' && (
        <>
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
        </>
      )}

      {current === 'holdings' && (
        <>
          <h1 className={styles.question}>Which stocks do you currently hold?</h1>
          <p className={styles.subcopy}>
            This helps us show your real starting point instead of an estimate — and we'll work out
            your investable total from what you enter, so there's no separate budget question.
            Optional — skip if you're not sure yet.
          </p>
          <ExistingHoldingsEditor value={holdings} onChange={setHoldings} />
        </>
      )}

      {current === 'amount' && (
        <>
          <h1 className={styles.question}>How much are you planning to invest?</h1>
          <p className={styles.subcopy}>
            A rough figure is fine — it helps us size your allocations. You can change this later.
          </p>
          <div className={styles.amountField}>
            <span className={styles.amountPrefix}>LKR</span>
            <input
              className={styles.amountInput}
              inputMode="numeric"
              placeholder="100,000"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              autoFocus
            />
          </div>
        </>
      )}

      {current === 'goal' && (
        <>
          <h1 className={styles.question}>What's your main goal?</h1>
          <p className={styles.subcopy}>
            This shapes how your recommendations balance growth against comfort.
          </p>
          <div className={styles.options}>
            {GOALS.map((g) => (
              <button
                key={g.key}
                type="button"
                className={goal === g.key ? styles.optionSelected : styles.option}
                onClick={() => setGoal(g.key)}
              >
                <strong>{g.title}</strong>
                <span>{g.sub}</span>
              </button>
            ))}
          </div>
        </>
      )}

      <div className={styles.footer}>
        {step > 1 && (
          <button
            type="button"
            className={styles.backButton}
            onClick={() => setStep((s) => s - 1)}
          >
            ← Back
          </button>
        )}
        {step < totalSteps ? (
          <button
            type="button"
            className={styles.continueButton}
            disabled={!canProceed}
            onClick={() => setStep((s) => s + 1)}
          >
            Continue →
          </button>
        ) : (
          <button
            type="button"
            className={styles.continueButton}
            disabled={!canProceed}
            onClick={handleFinish}
          >
            Start the game →
          </button>
        )}
      </div>
    </div>
  );
}
