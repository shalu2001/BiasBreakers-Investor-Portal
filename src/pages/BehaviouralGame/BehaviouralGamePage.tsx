import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../session/SessionContext';
import { saveParameters } from '../../api/portal';
import {
  createSession, getHistory, allocate, advance, commitEvent, finishSession,
  type MarketState, type Benchmark, type HistoryBar, type GameEvent, type FinishResult,
} from '../../api/behaviouralGame';
import { AllocationSlider } from './AllocationSlider';
import { GameCandles } from './GameCandles';
import { HelpModal } from './HelpModal';
import { GameTour, type TourStep } from './GameTour';
import { DevAutoplayPanel } from './DevAutoplayPanel';
import styles from './game.module.css';

// ============================================================================
//  Behavioural-simulation onboarding game, React port of the standalone
//  research instrument. Single-stock-at-a-time UI over the FastAPI game engine.
// ============================================================================

type Screen = 'start' | 'trading' | 'transition' | 'events' | 'results';
type Tone = 'neutral' | 'gain' | 'loss';
interface Consequence { tone: Tone; text: string }
interface DriftInfo { dir: 'up' | 'down'; ticker: string; priceChg: number; from: number; to: number }
interface TransitionInfo { title: string; sub: string; onContinue: () => void }
// One row in the Activity log. Built on the client at each checkpoint so it can
// carry the full story (allocation, outcome, and the market-vs-you gap), and is
// reset per round so the panel only ever shows the current round's decisions.
interface ActivityEntry {
  n: number;
  ticker: string;
  allocationPct: number;
  pnl: number;
  pnlPct: number;
  gap: { index: number; you: number } | null;
}

const REDUCED_MOTION = typeof window !== 'undefined'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const money = (n: number) => 'Rs. ' + Math.round(n).toLocaleString();
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

const TOUR_STEPS: TourStep[] = [
  { key: 'money', title: 'Your money', text: 'Total Equity is all the money you have; Cash is the part not invested yet. You start with Rs. 1,000,000 in cash.' },
  { key: 'market', title: 'The market', text: 'These are the companies you can invest in, and how each one moved today. Click one to choose it.' },
  { key: 'position', title: 'Your position', text: "Your chosen company's price shows here (recent chart just below), along with how much of it you're currently holding." },
  { key: 'slider', title: 'Set your split', text: "This slider is the share of your money you want in the stock. 0% = all cash, 100% = all in, and whatever's left stays as cash." },
  { key: 'preview', title: 'Before you confirm', text: 'This previews what confirming will do: how much ends up in the stock, how much stays as cash, and the trade it makes.' },
  { key: 'confirm', title: 'Move forward', text: "When you're happy, lock it in to jump forward in time and see how your money did. That's the whole loop. Enjoy!" },
];

export function BehaviouralGamePage() {
  const [screen, setScreen] = useState<Screen>('start');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [marketState, setMarketState] = useState<MarketState>({});
  const [fixedTicker, setFixedTicker] = useState<string | null>(null);
  const [lockedTicker, setLockedTicker] = useState<string | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string>('');
  const [equity, setEquity] = useState(1_000_000);
  const [cash, setCash] = useState(1_000_000);
  const [targetPct, setTargetPct] = useState(50);
  const [roundLabel, setRoundLabel] = useState('Fund A');
  const [day, setDay] = useState(0);
  const [totalDays, setTotalDays] = useState(0);
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [consequence, setConsequence] = useState<Consequence>({ tone: 'neutral', text: '' });
  const [drift, setDrift] = useState<DriftInfo | null>(null);
  const [roundLog, setRoundLog] = useState<ActivityEntry[]>([]);
  const [history, setHistory] = useState<HistoryBar[]>([]);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const [transition, setTransition] = useState<TransitionInfo | null>(null);
  const [event, setEvent] = useState<GameEvent | null>(null);
  const [eventCommit, setEventCommit] = useState(50);
  const [commitBusy, setCommitBusy] = useState(false);
  const [results, setResults] = useState<FinishResult | null>(null);
  const navigate = useNavigate();
  const { setProfile } = useSession();

  // Session bookkeeping that must not trigger re-render (read inside async handlers).
  const equityBeforeDecision = useRef(1_000_000);
  const firstDecisionOfFund = useRef(true);
  const refStockPrice = useRef<number | null>(null);
  const refStockTicker = useRef<string | null>(null);
  const confirmedPct = useRef(0);

  const effectiveTicker = () => fixedTicker || lockedTicker || selectedTicker;
  const isLocked = Boolean(fixedTicker || lockedTicker);

  // Refetch the selected stock's chart history each time the stock or checkpoint changes.
  useEffect(() => {
    if (!sessionId || !selectedTicker) return;
    let alive = true;
    getHistory(sessionId, selectedTicker).then((h) => { if (alive) setHistory(h); }).catch(() => {});
    return () => { alive = false; };
  }, [sessionId, selectedTicker, day]);

  function introConsequence(fixed: string | null): Consequence {
    return {
      tone: 'neutral',
      text: fixed
        ? `New fund. You can only trade ${fixed} this round, but watch how the rest of the market moves.`
        : 'Fresh fund, all in cash. Pick a company and decide how much of your money to commit.',
    };
  }

  function consequenceFromDelta(delta: number, before: number): Consequence {
    if (Math.abs(delta) < 1) return { tone: 'neutral', text: 'Barely moved. Your call held its ground.' };
    const pct = before > 0 ? (delta / before) * 100 : 0;
    const gained = delta > 0;
    return {
      tone: gained ? 'gain' : 'loss',
      text: `Your fund ${gained ? 'gained' : 'lost'} ${money(Math.abs(delta))} (${gained ? '+' : '-'}${Math.abs(pct).toFixed(1)}%) since your last move. Now what?`,
    };
  }

  function computeDrift(tk: string, actualPct: number, ms: MarketState): DriftInfo | null {
    if (firstDecisionOfFund.current || refStockPrice.current == null || refStockTicker.current !== tk || !ms[tk]) return null;
    const priceChg = (ms[tk].Close / refStockPrice.current - 1) * 100;
    const d = actualPct - confirmedPct.current;
    if (Math.abs(d) < 1 || Math.abs(priceChg) < 0.01) return null;
    return { dir: d > 0 ? 'up' : 'down', ticker: tk, priceChg, from: confirmedPct.current, to: actualPct };
  }

  async function startGame() {
    const data = await createSession();
    setSessionId(data.session_id);
    setFixedTicker(data.fixed_ticker);
    setLockedTicker(null);
    setMarketState(data.market_state);
    setBenchmark(data.benchmark);
    setEquity(data.cash); setCash(data.cash);
    equityBeforeDecision.current = data.cash;
    firstDecisionOfFund.current = true;
    refStockPrice.current = null; refStockTicker.current = null; confirmedPct.current = 0;
    const sel = data.fixed_ticker || Object.keys(data.market_state)[0];
    setSelectedTicker(sel);
    setRoundLabel(data.round_label); setDay(data.day); setTotalDays(data.total_days);
    setConsequence(introConsequence(data.fixed_ticker));
    setDrift(null); setTargetPct(50); setRoundLog([]);
    setScreen('trading');
    setTourActive(true);
  }

  function startFreshFund(
    data: Extract<Awaited<ReturnType<typeof advance>>, { status: 'new_scenario_started' | 'new_block_started' }>,
    title: string, sub: string, isNewBlock: boolean,
  ) {
    const newFixed = isNewBlock ? data.fixed_ticker : fixedTicker;
    setMarketState(data.market_state);
    setBenchmark(data.benchmark);
    setEquity(data.cash); setCash(data.cash);
    setFixedTicker(newFixed); setLockedTicker(null);
    confirmedPct.current = 0; firstDecisionOfFund.current = true;
    refStockPrice.current = null; refStockTicker.current = null; equityBeforeDecision.current = data.cash;
    const sel = newFixed || Object.keys(data.market_state)[0];
    setSelectedTicker(sel);
    setRoundLabel(data.round_label); setDay(data.day); setTotalDays(data.total_days);
    setConsequence(introConsequence(newFixed)); setDrift(null); setTargetPct(50);
    setRoundLog([]); // a fresh fund starts a fresh activity log
    setTransition({ title, sub, onContinue: () => { setTransition(null); setScreen('trading'); } });
    setScreen('transition');
  }

  async function handleConfirm() {
    if (!sessionId) return;
    setConfirmBusy(true);
    const ticker = effectiveTicker();
    await allocate(sessionId, ticker, targetPct / 100);

    const lockedLocal = fixedTicker || lockedTicker || selectedTicker;
    if (!fixedTicker && !lockedTicker) setLockedTicker(selectedTicker);
    confirmedPct.current = targetPct;
    firstDecisionOfFund.current = false;
    equityBeforeDecision.current = equity;
    refStockPrice.current = marketState[ticker] ? marketState[ticker].Close : null;
    refStockTicker.current = ticker;

    const decidedTicker = lockedLocal;
    const decidedPct = targetPct;
    if (!REDUCED_MOTION) { setAdvancing(true); await sleep(620); }

    const data = await advance(sessionId);
    setAdvancing(false);
    setConfirmBusy(false);

    if (data.status === 'at_checkpoint') {
      const bound = lockedLocal;
      setMarketState(data.market_state);
      setBenchmark(data.benchmark);
      setEquity(data.equity); setCash(data.cash);
      setSelectedTicker(bound);
      setRoundLabel(data.round_label); setDay(data.day); setTotalDays(data.total_days);
      const before = equityBeforeDecision.current;
      const delta = data.equity - before;
      setConsequence(consequenceFromDelta(delta, before));
      const actualPct = data.equity > 0 ? Math.round(((data.equity - data.cash) / data.equity) * 100) : 0;
      setTargetPct(actualPct);
      setDrift(computeDrift(bound, actualPct, data.market_state));
      const b = data.benchmark;
      setRoundLog((prev) => [
        ...prev,
        {
          n: prev.length + 1,
          ticker: decidedTicker,
          allocationPct: decidedPct,
          pnl: delta,
          pnlPct: before > 0 ? (delta / before) * 100 : 0,
          gap: b && b.show ? { index: b.index_return, you: b.held_return } : null,
        },
      ]);
    } else if (data.status === 'new_scenario_started') {
      startFreshFund(data, 'New Market Conditions',
        'A new era begins. Your fund resets to a fresh Rs. 1,000,000. Pick a company and start again.', false);
    } else if (data.status === 'new_block_started') {
      startFreshFund(data, `${data.round_label}: A Different Fund`,
        'You are handed a new fund, tied to a single stock. Watch the S&P SL20 benchmark bar at the top: when the market runs ahead and you fall behind, that gap is the moment that counts.', true);
    } else if (data.status === 'events_started') {
      const total = data.total_events || 16;
      setTransition({
        title: 'One last thing: quick market calls',
        sub: 'A handful of one-off 50/50 bets. Decide how much you would commit to each. This is where your instinct for risk really shows.',
        onContinue: () => { setTransition(null); setEvent({ ...data.event, total }); setEventCommit(50); setScreen('events'); },
      });
      setScreen('transition');
    } else if (data.status === 'all_blocks_complete') {
      await finish();
    }
  }

  async function handleCommit() {
    if (!sessionId) return;
    setCommitBusy(true);
    const res = await commitEvent(sessionId, eventCommit / 100);
    setCommitBusy(false);
    if (res.status === 'events_complete') await finish();
    else { setEvent(res.event); setEventCommit(50); }
  }

  async function finish() {
    if (!sessionId) return;
    const data = await finishSession(sessionId);
    setResults(data);
    // Carry the measured behavioural profile into the app session so the
    // dashboard can greet the user with their real result.
    setProfile(data.profile);
    // Persist to the user's profile in Cosmos (best-effort, a DB hiccup must
    // not break the results screen).
    try {
      await saveParameters({
        alpha: data.profile.alpha,
        lambda: data.profile.lambda,
        gamma: data.profile.gamma,
        confidence: (data.confidence ?? null) as Record<string, unknown> | null,
        source: 'behavioural_game',
      });
    } catch {
      /* keep the local session copy */
    }
    setScreen('results');
  }

  // DEV ONLY (start screen): take an auto-played/recovered profile, persist it
  // exactly like a real finish, and jump straight to the dashboard.
  async function useDevProfile(
    profile: { alpha: number; lambda: number; gamma: number },
    confidence: Record<string, { level?: string }> | null,
  ) {
    setProfile(profile);
    try {
      await saveParameters({
        alpha: profile.alpha,
        lambda: profile.lambda,
        gamma: profile.gamma,
        confidence: (confidence ?? null) as Record<string, unknown> | null,
        source: 'dev_autoplay',
      });
    } catch {
      /* keep the local session copy */
    }
    navigate('/');
  }

  // ---- derived render values -------------------------------------------------
  const holdingValue = Math.max(0, equity - cash);
  const holdingPct = equity > 0 ? Math.round((holdingValue / equity) * 100) : 0;
  const bound = effectiveTicker();
  const targetValue = (targetPct / 100) * equity;
  const currentValue = Math.max(0, equity - cash);
  const diff = targetValue - currentValue;
  const noChange = Math.abs(diff) < equity * 0.008;

  if (screen === 'start') {
    return (
      <div className={styles.game}>
        <div className={styles.centered}>
          <div className={styles.startStack}>
            <div className={styles.card}>
              <div className={styles.mark}>◆</div>
              <h1>Portfolio Session</h1>
              <p className={styles.subcopy}>
                You will run two funds through real historical market conditions. Each fund starts with{' '}
                <span className={styles.mono}>Rs.&nbsp;1,000,000</span>. Grow it, protect it, react however you see fit.
              </p>
              <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={startGame}>Begin Session</button>
            </div>
            {import.meta.env.DEV && <DevAutoplayPanel onUseProfile={useDevProfile} />}
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'transition' && transition) {
    return (
      <div className={styles.game}>
        <div className={styles.centered}>
          <div className={styles.card}>
            <div className={styles.transitionIcon}>→</div>
            <h2>{transition.title}</h2>
            <p className={styles.subcopy}>{transition.sub}</p>
            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={transition.onContinue}>Continue</button>
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'events' && event) {
    const stakeCommit = (eventCommit / 100) * event.stake;
    return (
      <div className={styles.game}>
        <div className={styles.centered}>
          <div className={styles.eventsWrap}>
            <div className={styles.eventsHead}>
              <span className={styles.markSmall}>◆</span>
              <span className={styles.topbarLabel}>Quick Market Calls</span>
              <span className={styles.roundBadge}>{event.index} / {event.total}</span>
            </div>
            <div className={styles.eventCard}>
              <p className={styles.eventIntro}>A one-off market call. Equal odds either way, so you decide how much to put on it.</p>
              <h2 className={styles.eventTitle}><span className={styles.mono}>{event.ticker}</span></h2>

              <div className={styles.eventOdds}>
                <div className={styles.oddsBar}>
                  <span className={`${styles.oddsHalf} ${styles.oddsUp}`}>50%</span>
                  <span className={`${styles.oddsHalf} ${styles.oddsDown}`}>50%</span>
                </div>
                <p className={styles.oddsCaption}>Equal odds, <b>50% chance each way</b></p>
              </div>

              <div className={styles.eventOutcomes}>
                <div className={`${styles.outcome} ${styles.outcomeUp}`}>
                  <span className={styles.outcomeLabel}>Gain</span>
                  <span className={`${styles.outcomeVal} ${styles.mono}`}>+{event.gain_pct}%</span>
                </div>
                <div className={styles.outcomeVs}>or</div>
                <div className={`${styles.outcome} ${styles.outcomeDown}`}>
                  <span className={styles.outcomeLabel}>Loss</span>
                  <span className={`${styles.outcomeVal} ${styles.mono}`}>-{event.loss_pct}%</span>
                </div>
              </div>

              <p className={styles.eventClarify}>These percentages are <b>how far the stock moves</b>, not how likely. Both outcomes are equally likely.</p>
              <p className={styles.eventPrompt}>How much of your <span className={styles.mono}>{money(event.stake)}</span> stake do you commit?</p>

              <AllocationSlider value={eventCommit} onChange={setEventCommit} leftLabel="Skip it (0%)" rightLabel="All in (100%)" showNudges={false} />

              <div className={styles.preview}>
                <div className={styles.previewRow}>
                  <span>You commit</span>
                  <span className={styles.mono}>{money(stakeCommit)}</span>
                </div>
              </div>
              <button type="button" className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFull}`} disabled={commitBusy} onClick={handleCommit}>Commit ▸</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (screen === 'results' && results) {
    return (
      <div className={styles.game}>
        <div className={styles.centered}>
          <div className={styles.card}>
            <div className={styles.mark}>◆</div>
            <h1>Session Complete</h1>
            <p className={styles.subcopy}>Your behavioural profile, decoded from how you actually traded.</p>
            <ResultsGrid results={results} />
            <p className={styles.resultsNote}>
              Fitted from {results.n_obs_block1 ?? '?'} loss-aversion decisions and {results.n_obs_block2 ?? '?'} regret decisions.
              {results.lambda_source === 'matched_stakes_events' ? ' Loss aversion measured from your matched-stakes calls.' : ''}
            </p>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFull}`}
              onClick={() => navigate('/')}
            >
              Continue to Dashboard ▸
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ---- trading screen --------------------------------------------------------
  const consequenceClass = consequence.tone === 'gain' ? styles.consequenceGain
    : consequence.tone === 'loss' ? styles.consequenceLoss : styles.consequenceNeutral;
  const info = marketState[selectedTicker];
  let prevText = '', prevTone = styles.flat;
  if (info) {
    if (refStockPrice.current == null || refStockTicker.current !== selectedTicker) {
      prevText = 'your starting point'; prevTone = styles.flat;
    } else {
      const chg = (info.Close / refStockPrice.current - 1) * 100;
      prevText = `since your last move ${chg > 0 ? '+' : ''}${chg.toFixed(2)}%`;
      prevTone = chg > 0 ? styles.up : chg < 0 ? styles.down : styles.flat;
    }
  }

  return (
    <div className={styles.game}>
      {/* top bar */}
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          <span className={styles.markSmall}>◆</span>
          <span className={styles.topbarLabel}>Portfolio Session</span>
          <span className={styles.roundBadge}>{roundLabel}</span>
          <button type="button" className={styles.helpBtn} title="How the numbers work" onClick={() => setHelpOpen(true)}>?</button>
        </div>
        <div className={styles.topbarRight} data-tour="money">
          <div className={styles.stat}><span className={styles.statLabel}>Decision</span><span className={`${styles.statValue} ${styles.mono}`}>{day} / {totalDays}</span></div>
          <div className={styles.stat}><span className={styles.statLabel}>Total Equity</span><span className={`${styles.statValue} ${styles.mono}`}>{money(equity)}</span></div>
          <div className={styles.stat}><span className={styles.statLabel}>Cash</span><span className={`${styles.statValue} ${styles.mono}`}>{money(cash)}</span></div>
        </div>
      </header>

      {/* session progress within this fund */}
      <div className={styles.progressTrack} title={`Decision ${day} of ${totalDays}`}>
        <span
          className={styles.progressFill}
          style={{ width: `${totalDays ? Math.min(100, (day / totalDays) * 100) : 0}%` }}
        />
      </div>

      {/* consequence strip */}
      <div className={`${styles.consequence} ${consequenceClass}`}><span>{consequence.text}</span></div>

      {/* benchmark strip (regret fund only) */}
      {benchmark?.show && <BenchmarkStrip b={benchmark} />}

      <main className={styles.mainGrid}>
        {/* MARKET */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Market</h2>
            {isLocked && <span className={styles.panelNote}>Locked for this fund</span>}
          </div>
          <div className={styles.marketSubcap}><span>Company</span><span>Price · move today</span></div>
          <div className={styles.tickerList} data-tour="market">
            {Object.entries(marketState).map(([ticker, ti]) => {
              const disabled = isLocked && ticker !== bound;
              const change = ti.ticker_return_pct;
              const changeCls = change == null ? styles.flat : change > 0 ? styles.up : change < 0 ? styles.down : styles.flat;
              const changeText = change == null ? '-' : (change > 0 ? '+' : '') + change.toFixed(2) + '%';
              return (
                <div
                  key={ticker}
                  className={`${styles.tickerRow} ${ticker === selectedTicker ? styles.tickerSelected : ''} ${disabled ? styles.tickerDisabled : ''}`}
                  onClick={disabled ? undefined : () => setSelectedTicker(ticker)}
                >
                  <span className={styles.tickerName}>{ticker}</span>
                  <span className={styles.tickerRight}>
                    <span className={`${styles.tickerPrice} ${styles.mono}`}>{ti.Close.toFixed(2)}</span>
                    <span className={`${styles.tickerChange} ${changeCls}`}>{changeText}</span>
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* POSITION */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}><h2>Your Position</h2></div>

          <div className={styles.selectedRow} data-tour="position">
            <span className={`${styles.selectedName} ${styles.mono}`}>{selectedTicker || '-'}</span>
            <span className={styles.selectedPrices}>
              <span className={`${styles.selectedPrice} ${styles.mono}`}>{info ? info.Close.toFixed(2) : '-'}</span>
              <span className={`${styles.selectedPrev} ${styles.mono} ${prevTone}`}>{prevText}</span>
            </span>
          </div>

          <GameCandles history={history} />

          <div className={styles.positionReadout}>
            <span>Currently holding</span>
            <span className={styles.mono}>{holdingPct}% · {money(holdingValue)}</span>
          </div>

          {drift && (
            <div className={`${styles.driftNote} ${drift.dir === 'up' ? styles.driftUp : styles.driftDown}`}>
              {drift.ticker} {drift.priceChg > 0 ? 'rose' : 'fell'} <b>{Math.abs(drift.priceChg).toFixed(2)}%</b> since your last move,
              so your share shifted from <b>{drift.from}%</b> to <b>{drift.to}%</b> on its own, no trade, just the price. Slide only to change it.
            </div>
          )}

          <div className={styles.beamCaption}>
            Share of your <b>current total money</b> held in <span className={styles.mono}>{bound || '-'}</span>{' '}
            <span className={styles.beamHint} title="A percentage of your CURRENT total money (top right), not your starting million. It shifts as the stock moves, and a rising stock becomes a bigger share even if you don't trade.">ⓘ</span>
          </div>
          <div data-tour="slider">
            <AllocationSlider value={targetPct} onChange={setTargetPct} leftLabel="0% · all cash" rightLabel="100% · all in" />
          </div>

          <div className={styles.preview} data-tour="preview">
            <div className={styles.previewHead}>If you confirm this</div>
            <div className={styles.previewRow}><span>Held in {bound || 'the stock'}</span><span className={styles.mono}>{money(noChange ? currentValue : targetValue)}</span></div>
            <div className={styles.previewRow}><span>Kept as cash</span><span className={styles.mono}>{money(noChange ? cash : equity - targetValue)}</span></div>
            <div className={`${styles.previewAction} ${noChange ? styles.previewFlat : diff > 0 ? styles.previewBuy : styles.previewSell}`}>
              {noChange ? 'No change to your position' : diff > 0 ? `Buys ${money(diff)} of ${bound}` : `Sells ${money(-diff)} of ${bound}`}
            </div>
          </div>

          <button type="button" className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFull}`} disabled={confirmBusy} onClick={handleConfirm} data-tour="confirm">
            Lock in &amp; advance ▸
          </button>
        </section>

        {/* ACTIVITY — current round only */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Activity</h2>
            <span className={`${styles.logRound} ${styles.mono}`}>{roundLabel}</span>
          </div>
          <div className={styles.logList}>
            {roundLog.length === 0 ? (
              <div className={styles.logEmpty}>No decisions yet this round.</div>
            ) : (
              roundLog.slice().reverse().map((e) => {
                const pnlCls = e.pnl > 0 ? styles.up : e.pnl < 0 ? styles.down : styles.flat;
                const rs = (e.pnl > 0 ? '+' : e.pnl < 0 ? '-' : '') + 'Rs. ' + Math.abs(Math.round(e.pnl)).toLocaleString();
                const pct = (e.pnlPct > 0 ? '+' : '') + e.pnlPct.toFixed(1) + '%';
                const gClass = (v: number) => (v > 0 ? styles.up : v < 0 ? styles.down : styles.flat);
                const gFmt = (v: number) => (v > 0 ? '+' : '') + v.toFixed(1) + '%';
                return (
                  <div key={e.n} className={styles.logEntry}>
                    <span className={`${styles.logDate} ${styles.mono}`}>#{e.n}</span>
                    <div className={styles.logMain}>
                      <span className={styles.logDetail}>
                        Moved to <b>{e.allocationPct}%</b> in <span className={styles.mono}>{e.ticker}</span>
                      </span>
                      {e.gap && (
                        <span className={`${styles.logGap} ${styles.mono}`}>
                          market <span className={gClass(e.gap.index)}>{gFmt(e.gap.index)}</span>
                          {'  ·  '}you <span className={gClass(e.gap.you)}>{gFmt(e.gap.you)}</span>
                        </span>
                      )}
                    </div>
                    <span className={styles.logPnl}>
                      <span className={`${styles.mono} ${pnlCls}`}>{rs}</span>
                      <span className={styles.logPnlPct}>{pct}</span>
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </section>
      </main>

      {advancing && (
        <div className={styles.advanceOverlay}>
          <div className={styles.advanceInner}>
            <div className={styles.advanceSpinner} />
            <span>Days pass…</span>
          </div>
        </div>
      )}

      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      {tourActive && <GameTour steps={TOUR_STEPS} onDone={() => setTourActive(false)} />}
    </div>
  );
}

// ---- small presentational helpers -------------------------------------------
function BenchmarkStrip({ b }: { b: Benchmark }) {
  const fmt = (v: number) => (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%';
  const cls = (v: number) => (v > 0 ? styles.up : v < 0 ? styles.down : styles.flat);
  const gap = b.market_gap;
  let verdict: string, wrap: string;
  if (Math.abs(gap) < 0.05) { verdict = "You're level with the market"; wrap = styles.benchmarkEven; }
  else if (gap > 0) { verdict = `You're ${gap.toFixed(2)}% behind the market`; wrap = styles.benchmarkBehind; }
  else { verdict = `You're ${Math.abs(gap).toFixed(2)}% ahead of the market`; wrap = styles.benchmarkAhead; }
  return (
    <div className={`${styles.benchmark} ${wrap}`}>
      <span className={styles.benchmarkLabel}>S&amp;P SL20</span>
      <span className={styles.benchmarkGap}>{verdict}</span>
      <span className={styles.benchmarkDetail}>
        market <span className={`${styles.mono} ${cls(b.index_return)}`}>{fmt(b.index_return)}</span>
        <span className={styles.benchmarkSep}>·</span>
        you <span className={`${styles.mono} ${b.in_cash ? styles.flat : cls(b.held_return)}`}>{b.in_cash ? 'in cash' : fmt(b.held_return)}</span>
      </span>
    </div>
  );
}

function ResultsGrid({ results }: { results: FinishResult }) {
  const est = results.profile;
  const confidence = results.confidence ?? {};
  const meta: Record<'alpha' | 'lambda' | 'gamma', { label: string; blurb: (v: number) => string }> = {
    alpha: { label: 'Diminishing Sensitivity (α)', blurb: (v) => v <= 0.75 ? 'Big swings quickly stop feeling proportionally bigger to you.' : 'You feel gains and losses close to their true size.' },
    lambda: { label: 'Loss Aversion (λ)', blurb: (v) => v >= 2.5 ? 'Losses hurt far more than equal gains please.' : v >= 1.5 ? 'Mild asymmetry between losses and gains.' : 'You treat gains and losses fairly evenly.' },
    gamma: { label: 'Regret / FOMO (γ)', blurb: (v) => v >= 2.0 ? 'Strong pull to chase the market when it runs without you.' : v >= 0.8 ? 'Some sensitivity to missing out.' : 'Largely unbothered by what the market does elsewhere.' },
  };
  const order: Array<'lambda' | 'gamma' | 'alpha'> = ['lambda', 'gamma', 'alpha'];
  return (
    <div className={styles.resultsGrid}>
      {order.map((key) => {
        const value = est[key];
        if (value == null) return null;
        const conf = confidence[key];
        const showConf = conf && conf.level && conf.level !== 'ok';
        return (
          <div key={key} className={styles.resultCard}>
            <div className={styles.resultLabel}>{meta[key].label}</div>
            <div className={`${styles.resultValue} ${styles.mono}`}>{Number(value).toFixed(2)}</div>
            {showConf && (
              <div className={`${styles.resultConf} ${conf!.level === 'uninformative' ? styles.confBad : styles.confWarn}`} title={conf!.reason ?? ''}>
                {conf!.level === 'uninformative' ? 'Not reliable' : 'Low confidence'}
              </div>
            )}
            <div className={styles.resultBlurb}>{meta[key].blurb(Number(value))}</div>
          </div>
        );
      })}
    </div>
  );
}
