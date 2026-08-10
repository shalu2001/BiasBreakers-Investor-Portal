import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../session/AuthContext';
import { getProfile, updateAccount, saveOnboarding, authErrorMessage, type ExistingHolding } from '../../api/portal';
import { profileToPersona } from '../../session/profileToPersona';
import type { PersonaProfile } from '../../api/persona';
import { ExistingHoldingsEditor } from '../../components/ExistingHoldingsEditor';
import styles from './AccountPage.module.css';

export function AccountPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState(user?.name ?? '');
  const [amount, setAmount] = useState('');
  const [hasExisting, setHasExisting] = useState<boolean | null>(null);
  const [holdings, setHoldings] = useState<ExistingHolding[]>([]);
  const [persona, setPersona] = useState<PersonaProfile | null>(null);

  const [accountMsg, setAccountMsg] = useState<string | null>(null);
  const [planMsg, setPlanMsg] = useState<string | null>(null);
  const [savingAccount, setSavingAccount] = useState(false);
  const [savingPlan, setSavingPlan] = useState(false);

  const displayName = user?.name?.trim() ?? '';
  const initials = displayName
    ? displayName.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
    : (user?.email?.[0] ?? '?').toUpperCase();
  const TRAITS = persona
    ? [
        { label: 'Risk tolerance', score: persona.riskTolerance },
        { label: 'Loss aversion', score: persona.lossAversion },
        { label: 'Regret / FOMO', score: persona.regretAversion },
      ]
    : [];

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (cancelled) return;
        const ob = p.onboarding ?? {};
        setAmount(ob.investmentAmount != null ? String(ob.investmentAmount) : '');
        setHasExisting(ob.hasExistingPortfolio ?? null);
        setHoldings(ob.existingHoldings ?? []);
        const params = p.parameters ?? {};
        if (params.lambda != null || params.gamma != null) {
          setPersona(
            profileToPersona({
              alpha: params.alpha ?? null,
              lambda: params.lambda ?? null,
              gamma: params.gamma ?? null,
            }),
          );
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSaveAccount(e: React.FormEvent) {
    e.preventDefault();
    setSavingAccount(true);
    setAccountMsg(null);
    try {
      const updated = await updateAccount(name.trim());
      setUser(updated);
      setAccountMsg('Saved ✓');
    } catch (err) {
      setAccountMsg(authErrorMessage(err, 'Could not save'));
    } finally {
      setSavingAccount(false);
    }
  }

  async function handleSavePlan(e: React.FormEvent) {
    e.preventDefault();
    setSavingPlan(true);
    setPlanMsg(null);
    const amt = Number(amount.replace(/[^0-9.]/g, ''));
    try {
      await saveOnboarding({
        hasExistingPortfolio: hasExisting,
        // Existing-portfolio investors don't have a separate budget --
        // it's derived server-side from what their holdings are worth.
        // Force null here even if `amount` still holds a stale value from
        // before they switched their answer to "Yes".
        investmentAmount:
          hasExisting !== true && amount.trim() !== '' && !Number.isNaN(amt) && amt > 0 ? amt : null,
        goal: null,
        // Must be included here too -- PUT /portal/profile/onboarding
        // replaces the whole onboarding doc, so omitting this would
        // silently wipe out holdings entered during onboarding.
        existingHoldings: hasExisting ? holdings : null,
      });
      setPlanMsg('Saved ✓');
    } catch (err) {
      setPlanMsg(authErrorMessage(err, 'Could not save'));
    } finally {
      setSavingPlan(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.avatar}>{initials}</div>
        <div className={styles.headerText}>
          <h1 className={styles.title}>{displayName || 'Your account'}</h1>
          <span className={styles.email}>{user?.email}</span>
        </div>
      </header>

      <form className={styles.card} onSubmit={handleSaveAccount}>
        <span className={styles.cardTitle}>Your details</span>
        <label className={styles.label} htmlFor="email">Email</label>
        <input id="email" className={styles.input} value={user?.email ?? ''} disabled />
        <label className={styles.label} htmlFor="name">Name</label>
        <input
          id="name" className={styles.input} value={name}
          onChange={(e) => setName(e.target.value)} placeholder="Your name"
        />
        <div className={styles.actions}>
          <button type="submit" className={styles.saveBtn} disabled={savingAccount}>
            {savingAccount ? 'Saving…' : 'Save'}
          </button>
          {accountMsg && <span className={styles.msg}>{accountMsg}</span>}
        </div>
      </form>

      <form className={styles.card} onSubmit={handleSavePlan}>
        <span className={styles.cardTitle}>Your plan</span>

        <label className={styles.label}>Do you already hold S&amp;P SL20 stocks?</label>
        <div className={styles.chips}>
          <button type="button" className={hasExisting === true ? styles.chipOn : styles.chip} onClick={() => setHasExisting(true)}>Yes</button>
          <button type="button" className={hasExisting === false ? styles.chipOn : styles.chip} onClick={() => setHasExisting(false)}>No</button>
        </div>

        {hasExisting === true ? (
          <>
            <label className={styles.label}>Your current holdings</label>
            <ExistingHoldingsEditor value={holdings} onChange={setHoldings} />
            <p className={styles.hint}>
              Your investable total is worked out from these holdings' current value — no separate
              budget needed.
            </p>
          </>
        ) : (
          <>
            <label className={styles.label}>How much are you planning to invest?</label>
            <div className={styles.amountField}>
              <span className={styles.amountPrefix}>LKR</span>
              <input
                className={styles.amountInput} inputMode="numeric" value={amount}
                onChange={(e) => setAmount(e.target.value)} placeholder="100,000"
              />
            </div>
          </>
        )}

        <div className={styles.actions}>
          <button type="submit" className={styles.saveBtn} disabled={savingPlan}>
            {savingPlan ? 'Saving…' : 'Save'}
          </button>
          {planMsg && <span className={styles.msg}>{planMsg}</span>}
        </div>
      </form>

      <div className={styles.card}>
        <span className={styles.cardTitle}>Your investing personality</span>
        {persona ? (
          <>
            <div className={styles.archetype}>{persona.archetype}</div>
            <div className={styles.traits}>
              {TRAITS.map((t) => (
                <div key={t.label} className={styles.trait}>
                  <div className={styles.traitHead}>
                    <span className={styles.traitLabel}>{t.label}</span>
                    <span className={styles.mono}>{t.score}<span className={styles.scoreMax}>/100</span></span>
                  </div>
                  <div className={styles.meterTrack}>
                    <span className={styles.meterFill} style={{ width: `${t.score}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <p className={styles.hint}>
              Derived from your behavioural profile. This updates automatically as your trading
              activity is analysed.
            </p>
          </>
        ) : (
          <p className={styles.hint}>Your behavioural profile hasn’t been generated yet.</p>
        )}
        {/* DEV ONLY: replaying the game is a developer tool. For real users the
            parameters are recalculated from live trading activity (CSE / broker
            API), not by replaying the game. */}
        {import.meta.env.DEV && (
          <button type="button" className={styles.retakeBtn} onClick={() => navigate('/behavioural-game')}>
            {persona ? 'Retake the game (dev)' : 'Play the game (dev)'}
          </button>
        )}
      </div>
    </div>
  );
}
