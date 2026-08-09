import { useEffect, useState } from 'react';
import type { PersonaProfile } from '../../api/persona';
import { getProfile } from '../../api/portal';
import { profileToPersona } from '../../session/profileToPersona';
import { useSession } from '../../session/SessionContext';
import {
  getRecommendation,
  getPastRecommendations,
  submitRecommendationFeedback,
  type ReallocationRow,
  type PastRecommendation,
} from '../../api/recommendation';
import { PERSONA_FIXTURE, PAST_RECOMMENDATIONS_FIXTURE } from '../../mocks/fixtures';
import { LoadingState, EmptyState } from '../../components/ui';
import styles from './RecommendPage.module.css';

const lkr = new Intl.NumberFormat('en-LK');
const formatLkr = (value: number) => `LKR ${lkr.format(Math.round(value))}`;

function assetLabel(row: ReallocationRow): string {
  if (row.ticker === 'CASH') return 'Cash Reserve';
  return row.name !== row.ticker ? `${row.name} (${row.ticker})` : row.ticker;
}

function formatValPct(value: number | null, pct: number): string {
  return value == null ? `${pct}%` : `${formatLkr(value)} (${pct}%)`;
}

function formatNetChange(row: ReallocationRow): string {
  // No budget set -- nothing to compute a value/share delta from, fall
  // back to a plain percentage-point delta.
  if (row.currentValue == null || row.recommendedValue == null) {
    const pctDiff = row.recommendedPct - row.currentPct;
    return pctDiff === 0 ? 'No change' : `${pctDiff > 0 ? '+' : ''}${pctDiff}%`;
  }
  const valueDiff = row.recommendedValue - row.currentValue;
  const valuePart = `${valueDiff >= 0 ? '+' : '-'}${formatLkr(Math.abs(valueDiff))}`;
  const qtyDiff =
    row.currentQty != null && row.recommendedQty != null ? row.recommendedQty - row.currentQty : null;
  // Cash has no share count to show alongside its value delta.
  if (row.ticker === 'CASH' || qtyDiff == null) return valuePart;
  return `${valuePart} (${qtyDiff >= 0 ? '+' : '-'}${Math.abs(qtyDiff)} sh)`;
}

// Action is driven by value (falls back to percentage with no budget set),
// with cash using deposit/withdraw language instead of buy/sell.
function getAction(row: ReallocationRow) {
  const diff =
    row.currentValue != null && row.recommendedValue != null
      ? row.recommendedValue - row.currentValue
      : row.recommendedPct - row.currentPct;

  if (diff === 0) return { label: 'HOLD', className: styles.badgeHold };
  if (row.ticker === 'CASH') {
    return diff > 0
      ? { label: 'DEPOSIT', className: styles.badgeBuy }
      : { label: 'WITHDRAW', className: styles.badgeSell };
  }
  return diff > 0
    ? { label: 'BUY', className: styles.badgeBuy }
    : { label: 'SELL', className: styles.badgeSell };
}

export function RecommendPage() {
  const { profile, recommendation, setRecommendation } = useSession();
  const [persona, setPersona] = useState<PersonaProfile>(
    () => (profile ? profileToPersona(profile) : null) ?? PERSONA_FIXTURE,
  );
  // Seeded from the session so a previously-computed reallocation is still
  // shown after navigating away and back, instead of being wiped and
  // re-run on every visit. null/[] means "not optimized yet".
  const [rows, setRows] = useState<ReallocationRow[]>(recommendation ?? []);
  const [pastRecommendations, setPastRecommendations] = useState<PastRecommendation[]>(
    PAST_RECOMMENDATIONS_FIXTURE,
  );
  // Drives whether the table shows a "Current" column at all (pointless
  // when it's always 0) and whether the second column reads "Recommended"
  // (a fresh initial allocation) or "Rebalanced" (moving from a real
  // current position) -- from the same getProfile() call already made for
  // persona above, no extra request.
  const [hasExistingPortfolio, setHasExistingPortfolio] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeError, setOptimizeError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // Same source-of-truth chain as DashboardPage: saved Cosmos profile ->
    // in-session game result -> fixture. Keeps the archetype label
    // consistent across pages for the same signed-in user (there's no
    // /persona/me route -- this data already lives on /portal/profile).
    (async () => {
      try {
        const saved = await getProfile();
        if (cancelled) return;
        setHasExistingPortfolio(saved.onboarding?.hasExistingPortfolio === true);
        const p = saved.parameters ?? {};
        const mapped =
          p.lambda != null || p.gamma != null
            ? profileToPersona({ alpha: p.alpha ?? null, lambda: p.lambda ?? null, gamma: p.gamma ?? null })
            : null;
        if (mapped) setPersona(mapped);
        else if (profile) setPersona(profileToPersona(profile) ?? PERSONA_FIXTURE);
      } catch {
        if (!cancelled) {
          const mapped = profile ? profileToPersona(profile) : null;
          if (mapped) setPersona(mapped);
        }
      }
    })();

    // Rebalancing is expensive/meaningful, so it's never triggered
    // automatically here -- only handleOptimize (the button) calls
    // getRecommendation(). History is just a read, safe to load eagerly.
    getPastRecommendations()
      .then((data) => !cancelled && setPastRecommendations(data))
      .catch(() => !cancelled && setPastRecommendations(PAST_RECOMMENDATIONS_FIXTURE));

    return () => {
      cancelled = true;
    };
  }, [profile]);

  async function handleOptimize() {
    setOptimizing(true);
    setOptimizeError(false);
    try {
      const data = await getRecommendation();
      setRows(data);
      setRecommendation(data);
    } catch {
      setOptimizeError(true);
    } finally {
      setOptimizing(false);
    }
  }

  async function handleSubmitFeedback() {
    if (rating === null) return;
    await submitRecommendationFeedback(rating).catch(() => undefined);
    setSubmitted(true);
  }

  return (
    <div className={styles.page}>
      <div className={styles.titleRow}>
        <div>
          <span className={styles.eyebrow}>
            Reallocation, tuned to {persona.archetype.toLowerCase()}
          </span>
          <h1 className={styles.title}>Recommended reallocation</h1>
        </div>
        {rows.length > 0 && !optimizing && (
          <button type="button" className={styles.optimizeButton} onClick={handleOptimize}>
            Optimize portfolio ↻
          </button>
        )}
      </div>
      <p className={styles.subcopy}>
        Based on your archetype and current holdings, here's how the model would shift your
        weights. This is a suggestion — nothing changes until you approve it.
      </p>

      {optimizing ? (
        <LoadingState label="Optimizing your portfolio…" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon="↻"
          title="No optimization run yet"
          message={
            optimizeError
              ? "Something went wrong running the optimizer. Try again."
              : "Click optimize to generate a reallocation based on your archetype and current holdings."
          }
          action={
            <button type="button" className={styles.optimizeButton} onClick={handleOptimize}>
              Optimize portfolio ↻
            </button>
          }
        />
      ) : (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Asset / Stock</th>
                {hasExistingPortfolio && <th>Current (Val &amp; %)</th>}
                <th>{hasExistingPortfolio ? 'Rebalanced' : 'Recommended'} (Val &amp; %)</th>
                <th>Net Change (Val &amp; Shares)</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const action = getAction(row);
                return (
                  <tr key={row.ticker}>
                    <td>{assetLabel(row)}</td>
                    {hasExistingPortfolio && (
                      <td>{formatValPct(row.currentValue, row.currentPct)}</td>
                    )}
                    <td>{formatValPct(row.recommendedValue, row.recommendedPct)}</td>
                    <td>{formatNetChange(row)}</td>
                    <td>
                      <span className={action.className}>{action.label}</span>
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
        </>
      )}

      <h2 className={styles.sectionTitle}>Past recommendations</h2>
      <div className={styles.pastList}>
        {pastRecommendations.map((item) => (
          <div key={item.date} className={styles.pastItem}>
            <div className={styles.pastDate}>{item.date.toUpperCase()}</div>
            <p className={styles.pastDescription}>{item.description}</p>
            <div className={styles.pastFooter}>
              <span>{item.rating != null ? `Rated ${item.rating}/5` : 'Not yet rated'}</span>
              <a href="#">View →</a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
