// ============================================================
//  Behavioural Trading Simulator - single-stock-at-a-time UI
// ============================================================
const API_BASE = "http://127.0.0.1:8000";

let sessionId = null;
let marketState = {};          // { ticker: {Open,High,Low,Close,Volume,ticker_return_pct} }
let fixedTicker = null;        // set by backend in the regret block (DIAL)
let lockedTicker = null;       // set by the frontend after the first decision of a scenario
let selectedTicker = null;     // which stock is currently shown / will be traded
let equity = 1_000_000;        // total equity right now (at this checkpoint)
let cash = 1_000_000;
let targetPct = 50;            // slider value (0..100)
let equityBeforeDecision = 1_000_000;
let firstDecisionOfFund = true;
let refStockPrice = null;      // the bound stock's price at the player's LAST decision (the reference point)
let refStockTicker = null;
let benchmark = null;          // S&P SL20 regret signal from the server (regret block only)
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const screens = {
  start: document.getElementById("screen-start"),
  trading: document.getElementById("screen-trading"),
  transition: document.getElementById("screen-transition"),
  events: document.getElementById("screen-events"),
  results: document.getElementById("screen-results"),
};
const $ = (id) => document.getElementById(id);

function showScreen(name) {
  Object.values(screens).forEach((s) => s.classList.add("hidden"));
  screens[name].classList.remove("hidden");
}
function formatMoney(n) {
  return "Rs. " + Math.round(n).toLocaleString();
}
// The stock this fund is bound to: fixed by the server, else locked once chosen this scenario.
function effectiveTicker() {
  return fixedTicker || lockedTicker || selectedTicker;
}
function isLocked() {
  return Boolean(fixedTicker || lockedTicker);
}

// ---------------- start ----------------
$("btn-start").addEventListener("click", async () => {
  const data = await (await fetch(`${API_BASE}/session/create`, { method: "POST" })).json();
  sessionId = data.session_id;
  fixedTicker = data.fixed_ticker;      // null in the loss-aversion block
  lockedTicker = null;
  marketState = data.market_state;
  benchmark = data.benchmark;
  equity = cash = data.cash;
  equityBeforeDecision = data.cash;
  firstDecisionOfFund = true;
  refStockPrice = null; refStockTicker = null;

  selectedTicker = fixedTicker || Object.keys(marketState)[0];
  updateTopbar(data.round_label, data.day, data.total_days, cash, equity);
  setConsequenceIntro();
  renderBenchmark();
  resetSlider();
  renderTickers();
  updateSelectedHeader();
  updateHoldingReadout();
  updatePreview();
  renderChart();
  showScreen("trading");
  startTour();
});

// ---------------- first-trade tutorial (mechanics only, never the psychology) ----------------
let tourShown = false;
let tourIndex = 0;
let tourTarget = null;
const TOUR_STEPS = [
  { sel: ".topbar-right", title: "Your money", text: "Total Equity is all the money you have; Cash is the part not invested yet. You start with Rs. 1,000,000 in cash." },
  { sel: "#ticker-list", title: "The market", text: "These are the companies you can invest in, and how each one moved today. Click one to choose it." },
  { sel: ".selected-ticker-row", title: "Your position", text: "Your chosen company's price shows here (recent chart just below), along with how much of it you're currently holding." },
  { sel: ".beam-wrap", title: "Set your split", text: "This slider is the share of your money you want in the stock. 0% = all cash, 100% = all in — whatever's left stays as cash." },
  { sel: ".allocation-preview", title: "Before you confirm", text: "This previews what confirming will do: how much ends up in the stock, how much stays as cash, and the trade it makes." },
  { sel: "#btn-confirm", title: "Move forward", text: "When you're happy, lock it in to jump forward in time and see how your money did. That's the whole loop — enjoy!" },
];
// block user scrolling while the tour is up (programmatic scrollIntoView still works)
const TOUR_SCROLL_OPTS = { passive: false, capture: true };
function tourBlockScroll(e) { e.preventDefault(); }
function tourBlockKeys(e) {
  if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " ", "Spacebar"].includes(e.key)) e.preventDefault();
}
function lockTourScroll() {
  window.addEventListener("wheel", tourBlockScroll, TOUR_SCROLL_OPTS);
  window.addEventListener("touchmove", tourBlockScroll, TOUR_SCROLL_OPTS);
  window.addEventListener("keydown", tourBlockKeys, TOUR_SCROLL_OPTS);
  window.addEventListener("scroll", positionTour, true); // keep spotlight glued if anything shifts
}
function unlockTourScroll() {
  window.removeEventListener("wheel", tourBlockScroll, TOUR_SCROLL_OPTS);
  window.removeEventListener("touchmove", tourBlockScroll, TOUR_SCROLL_OPTS);
  window.removeEventListener("keydown", tourBlockKeys, TOUR_SCROLL_OPTS);
  window.removeEventListener("scroll", positionTour, true);
}
function startTour() {
  if (tourShown) return;
  tourShown = true; tourIndex = 0;
  $("tour").classList.remove("hidden");
  lockTourScroll();
  showTourStep();
}
function showTourStep() {
  const step = TOUR_STEPS[tourIndex];
  const target = document.querySelector(step.sel);
  if (!target) { endTour(); return; }
  tourTarget = target;
  $("tour-step").innerText = `${tourIndex + 1} / ${TOUR_STEPS.length}`;
  $("tour-title").innerText = step.title;
  $("tour-text").innerText = step.text;
  $("tour-next").innerHTML = tourIndex === TOUR_STEPS.length - 1 ? "Got it &check;" : "Next &rarr;";
  $("tour-card").style.visibility = "hidden";
  // scroll the target fully into view, THEN measure (so the spotlight lands exactly on it)
  target.scrollIntoView({ block: "center", inline: "nearest" });
  requestAnimationFrame(() => requestAnimationFrame(positionTour));
}
function positionTour() {
  if (!tourTarget) return;
  const r = tourTarget.getBoundingClientRect();
  const pad = 8, margin = 14, vw = window.innerWidth, vh = window.innerHeight;
  const spot = $("tour-spot");
  spot.style.top = (r.top - pad) + "px";
  spot.style.left = (r.left - pad) + "px";
  spot.style.width = (r.width + pad * 2) + "px";
  spot.style.height = (r.height + pad * 2) + "px";
  const card = $("tour-card");
  const cw = card.offsetWidth, ch = card.offsetHeight;
  const clampX = (x) => Math.max(10, Math.min(x, vw - cw - 10));
  const clampY = (y) => Math.max(10, Math.min(y, vh - ch - 10));
  let top, left;
  if (vh - r.bottom >= ch + margin) {            // below the element
    top = r.bottom + margin; left = clampX(r.left + r.width / 2 - cw / 2);
  } else if (r.top >= ch + margin) {             // above it
    top = r.top - ch - margin; left = clampX(r.left + r.width / 2 - cw / 2);
  } else if (vw - r.right >= cw + margin) {       // to its right
    left = r.right + margin; top = clampY(r.top + r.height / 2 - ch / 2);
  } else if (r.left >= cw + margin) {            // to its left
    left = r.left - cw - margin; top = clampY(r.top + r.height / 2 - ch / 2);
  } else {                                       // fallback: centre of screen
    left = clampX(vw / 2 - cw / 2); top = clampY(vh / 2 - ch / 2);
  }
  card.style.top = top + "px";
  card.style.left = left + "px";
  card.style.visibility = "visible";
}
function endTour() { $("tour").classList.add("hidden"); unlockTourScroll(); }

// ---------------- help modal (money mechanics, anytime) ----------------
$("help-btn").addEventListener("click", () => $("help-modal").classList.remove("hidden"));
$("help-close").addEventListener("click", () => $("help-modal").classList.add("hidden"));
$("help-backdrop").addEventListener("click", () => $("help-modal").classList.add("hidden"));
$("tour-next").addEventListener("click", () => {
  tourIndex++;
  if (tourIndex >= TOUR_STEPS.length) endTour(); else showTourStep();
});
$("tour-skip").addEventListener("click", endTour);
window.addEventListener("resize", () => { if (!$("tour").classList.contains("hidden")) showTourStep(); });

// ---------------- top bar & banners ----------------
function updateTopbar(roundLabel, day, totalDays, cashVal, equityVal) {
  $("round-label").innerText = roundLabel;
  $("stat-day").innerText = `${day} / ${totalDays}`;
  $("stat-cash").innerText = formatMoney(cashVal);
  $("stat-equity").innerText = formatMoney(equityVal);
}

function setConsequenceIntro() {
  const c = $("consequence");
  $("drift-note").className = "drift-note hidden";   // no drift on a fresh fund
  c.className = "consequence consequence-neutral";
  if (fixedTicker) {
    $("consequence-text").innerText =
      `New fund. You can only trade ${fixedTicker} this round — but watch how the rest of the market moves.`;
  } else {
    $("consequence-text").innerText =
      "Fresh fund, all in cash. Pick a company and decide how much of your money to commit.";
  }
}

// Show what happened to their money since the last decision -- this is the
// same equity change (wealth_change) the estimator reads, so what the player
// feels and what we measure are the exact same signal.
function showConsequence(delta) {
  const c = $("consequence");
  const pct = equityBeforeDecision > 0 ? (delta / equityBeforeDecision) * 100 : 0;
  if (Math.abs(delta) < 1) {
    c.className = "consequence consequence-neutral";
    $("consequence-text").innerText = "Barely moved. Your call held its ground.";
    return;
  }
  const gained = delta > 0;
  c.className = "consequence " + (gained ? "consequence-gain" : "consequence-loss");
  const verb = gained ? "gained" : "lost";
  $("consequence-text").innerText =
    `Your fund ${verb} ${formatMoney(Math.abs(delta))} (${gained ? "+" : "-"}${Math.abs(pct).toFixed(1)}%) since your last move. Now what?`;
}

// ---------------- benchmark strip (regret block only) ----------------
// Surfaces the EXACT signal the estimator reads for gamma: today's S&P SL20 move
// vs the move of the stock you're actually holding. Hidden in Fund A (which has no
// benchmark by design), so what the player perceives == what we measure.
function renderBenchmark() {
  const el = $("benchmark");
  if (!benchmark || !benchmark.show) { el.className = "benchmark hidden"; return; }
  const fmt = (v) => (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
  const cls = (v) => "mono " + (v > 0 ? "up" : v < 0 ? "down" : "flat");

  const idxEl = $("bm-index");
  idxEl.innerText = fmt(benchmark.index_return);
  idxEl.className = cls(benchmark.index_return);

  const heldEl = $("bm-held");
  if (benchmark.in_cash) {
    heldEl.innerText = "in cash";
    heldEl.className = "mono flat";
  } else {
    heldEl.innerText = fmt(benchmark.held_return);
    heldEl.className = cls(benchmark.held_return);
  }

  // market_gap = index - your holding. Positive => the market ran ahead of you (FOMO).
  const gap = benchmark.market_gap;
  const gapEl = $("bm-gap");
  if (Math.abs(gap) < 0.05) {
    gapEl.innerText = "You're level with the market";
    el.className = "benchmark benchmark-even";
  } else if (gap > 0) {
    gapEl.innerText = `You're ${gap.toFixed(2)}% behind the market`;
    el.className = "benchmark benchmark-behind";
  } else {
    gapEl.innerText = `You're ${Math.abs(gap).toFixed(2)}% ahead of the market`;
    el.className = "benchmark benchmark-ahead";
  }
}

// ---------------- market list ----------------
function renderTickers() {
  const list = $("ticker-list");
  const note = $("fixed-ticker-note");
  list.innerHTML = "";
  note.classList.toggle("hidden", !isLocked());

  const boundTicker = effectiveTicker();

  Object.entries(marketState).forEach(([ticker, info]) => {
    // When locked, only the bound stock is interactive; the rest stay visible
    // (so the player can see the market running) but disabled.
    const disabled = isLocked() && ticker !== boundTicker;
    const selected = ticker === selectedTicker;
    const change = info.ticker_return_pct;
    const changeClass = change == null ? "flat" : change > 0 ? "up" : change < 0 ? "down" : "flat";
    const changeText = change == null ? "—" : (change > 0 ? "+" : "") + change.toFixed(2) + "%";

    const row = document.createElement("div");
    row.className = "ticker-row" + (selected ? " selected" : "") + (disabled ? " disabled" : "");
    row.innerHTML = `
      <span class="ticker-name">${ticker}</span>
      <span class="ticker-right">
        <span class="ticker-price mono">${info.Close.toFixed(2)}</span>
        <span class="ticker-change ${changeClass}">${changeText}</span>
      </span>`;
    if (!disabled) {
      row.addEventListener("click", () => {
        selectedTicker = ticker;
        renderTickers();
        updateSelectedHeader();
        updateHoldingReadout();
        updatePreview();
        renderChart();
      });
    }
    list.appendChild(row);
  });
}

// ---------------- selected stock header / holding ----------------
function updateSelectedHeader() {
  $("selected-ticker-name").innerText = selectedTicker || "—";
  const info = marketState[selectedTicker];
  $("selected-ticker-price").innerText = info ? info.Close.toFixed(2) : "—";

  // Reference point = the stock's price when the player LAST made a decision on it.
  // This matches the "since your last move" fund banner, so the whole screen uses
  // ONE consistent reference (prospect theory is defined relative to a reference point).
  const prevEl = $("selected-ticker-prev");
  if (!info) { prevEl.innerText = ""; prevEl.className = "selected-ticker-prev mono"; return; }
  if (refStockPrice == null || refStockTicker !== selectedTicker) {
    prevEl.innerText = "your starting point";
    prevEl.className = "selected-ticker-prev mono flat";
    return;
  }
  const chg = (info.Close / refStockPrice - 1) * 100;
  const sign = chg > 0 ? "+" : "";
  prevEl.innerText = `since your last move ${sign}${chg.toFixed(2)}%`;
  prevEl.className = "selected-ticker-prev mono " + (chg > 0 ? "up" : chg < 0 ? "down" : "flat");
}

// The % of equity currently sitting in the bound stock (last confirmed target).
let confirmedPct = 0;
function currentHoldingPct() {
  return confirmedPct;
}
// Shows the ACTUAL current position (equity minus real cash), not an idealised
// "target % of equity" -- so it always reconciles with the cash shown in the top bar.
function updateHoldingReadout() {
  const value = Math.max(0, equity - cash);
  const pct = equity > 0 ? (value / equity) * 100 : 0;
  $("holding-readout").innerHTML = `${Math.round(pct)}% &middot; ${formatMoney(value)}`;
}

// Explains a slider % that moved on its own: the price shifted your share since your
// last confirmed target. Spells out the exact price change and the % it caused, and
// reassures that no trade happened. Hidden unless a real drift occurred.
function renderDriftNote(actualPct) {
  const el = $("drift-note");
  const tk = effectiveTicker();
  if (firstDecisionOfFund || refStockPrice == null || refStockTicker !== tk || !marketState[tk]) {
    el.className = "drift-note hidden"; return;
  }
  const priceChg = (marketState[tk].Close / refStockPrice - 1) * 100;
  const drift = actualPct - confirmedPct;
  if (Math.abs(drift) < 1 || Math.abs(priceChg) < 0.01) { el.className = "drift-note hidden"; return; }
  const dir = priceChg > 0 ? "rose" : "fell";
  el.className = "drift-note " + (drift > 0 ? "up" : "down");
  el.innerHTML =
    `${tk} ${dir} <b>${Math.abs(priceChg).toFixed(2)}%</b> since your last move, so your share shifted from ` +
    `<b>${confirmedPct}%</b> to <b>${actualPct}%</b> on its own — no trade, just the price. Slide only to change it.`;
}

// ---------------- candlestick chart ----------------
async function renderChart() {
  const svg = $("candle-chart");
  if (!selectedTicker) { svg.innerHTML = ""; return; }
  const data = await (await fetch(`${API_BASE}/session/${sessionId}/history/${selectedTicker}?lookback=15`)).json();
  drawCandles(svg, data.history);
}
function drawCandles(svg, history) {
  svg.innerHTML = "";
  if (!history || history.length === 0) return;
  if (history.length < 5) {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", "280"); t.setAttribute("y", "90");
    t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "var(--text-dim)");
    t.setAttribute("font-size", "13"); t.textContent = "Building price history…";
    svg.appendChild(t); return;
  }
  const w = 560, h = 180, pad = 8;
  const prices = history.flatMap((d) => [d.high, d.low]);
  const minP = Math.min(...prices), maxP = Math.max(...prices);
  const range = (maxP - minP) || 1;
  const cw = (w - pad * 2) / history.length;
  const scaleY = (p) => h - pad - ((p - minP) / range) * (h - pad * 2);
  history.forEach((d, i) => {
    const x = pad + i * cw + cw / 2;
    const up = d.close >= d.open;
    const top = scaleY(Math.max(d.open, d.close));
    const bot = scaleY(Math.min(d.open, d.close));
    const bh = Math.max(1.5, bot - top);
    const wick = document.createElementNS("http://www.w3.org/2000/svg", "line");
    wick.setAttribute("x1", x); wick.setAttribute("x2", x);
    wick.setAttribute("y1", scaleY(d.high)); wick.setAttribute("y2", scaleY(d.low));
    wick.setAttribute("class", "candle-wick"); svg.appendChild(wick);
    const body = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    body.setAttribute("x", x - cw * 0.32); body.setAttribute("y", top);
    body.setAttribute("width", cw * 0.64); body.setAttribute("height", bh);
    body.setAttribute("class", up ? "candle-body-up" : "candle-body-down");
    svg.appendChild(body);
  });
}

// ---------------- slider (continuous position dial) ----------------
const slider = $("allocation-slider");
const beamFill = $("beam-fill");
const beamHandle = $("beam-handle");
const beamPct = $("beam-pct");

function applySlider(v) {
  targetPct = Math.max(0, Math.min(100, Math.round(v)));
  slider.value = targetPct;
  beamFill.style.width = targetPct + "%";
  beamHandle.style.left = targetPct + "%";
  beamPct.innerText = targetPct + "%";
  updatePreview();
}
slider.addEventListener("input", () => applySlider(parseInt(slider.value)));
document.querySelectorAll(".nudge-btn").forEach((b) => {
  b.addEventListener("click", () => applySlider(targetPct + parseInt(b.dataset.delta)));
});
function resetSlider() { applySlider(50); }

function updatePreview() {
  const tk = effectiveTicker() || "the stock";
  const targetValue = (targetPct / 100) * equity;       // where the slider would put you
  const currentValue = Math.max(0, equity - cash);      // where you actually are now
  const diff = targetValue - currentValue;
  const noChange = Math.abs(diff) < equity * 0.008;     // negligible (e.g. integer-rounding)
  const beamTk = $("beam-ticker"); if (beamTk) beamTk.innerText = tk;
  const prevTk = $("preview-ticker"); if (prevTk) prevTk.innerText = tk;

  // When the move is negligible, show your ACTUAL current split so the panel
  // reconciles exactly with the top bar; only project a new split for a real move.
  $("preview-target-value").innerText = formatMoney(noChange ? currentValue : targetValue);
  $("preview-cash-value").innerText = formatMoney(noChange ? cash : (equity - targetValue));

  const act = $("preview-action");
  if (!act) return;
  if (noChange) {
    act.className = "preview-action flat";
    act.innerText = "No change to your position";
  } else if (diff > 0) {
    act.className = "preview-action buy";
    act.innerText = `Buys ${formatMoney(diff)} of ${tk}`;
  } else {
    act.className = "preview-action sell";
    act.innerText = `Sells ${formatMoney(-diff)} of ${tk}`;
  }
}

// ---------------- confirm & advance ----------------
$("btn-confirm").addEventListener("click", async () => {
  const btn = $("btn-confirm");
  btn.disabled = true;

  const ticker = effectiveTicker();
  await fetch(`${API_BASE}/session/${sessionId}/allocate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, target_pct: targetPct / 100 }),
  });

  // Lock this fund to the chosen stock for the rest of the scenario.
  if (!fixedTicker && !lockedTicker) { lockedTicker = selectedTicker; }
  confirmedPct = targetPct;
  firstDecisionOfFund = false;
  equityBeforeDecision = equity;
  // Remember the price we acted at — it's the reference point for the next decision.
  refStockPrice = marketState[ticker] ? marketState[ticker].Close : null;
  refStockTicker = ticker;

  await refreshLog();
  await showAdvancing();

  const data = await (await fetch(`${API_BASE}/session/${sessionId}/advance`, { method: "POST" })).json();
  hideAdvancing();
  btn.disabled = false;

  if (data.status === "at_checkpoint") {
    marketState = data.market_state;
    benchmark = data.benchmark;
    equity = data.equity;
    cash = data.cash;
    selectedTicker = effectiveTicker();
    updateTopbar(data.round_label, data.day, data.total_days, cash, equity);
    showConsequence(equity - equityBeforeDecision);
    renderBenchmark();
    renderTickers();
    updateSelectedHeader();
    updateHoldingReadout();
    // Start the slider at your ACTUAL current allocation — the market may have drifted
    // it away from your last target — so "confirm" without moving means NO trade.
    const actualPct = equity > 0 ? Math.round(((equity - cash) / equity) * 100) : 0;
    applySlider(actualPct);
    renderDriftNote(actualPct);
    renderChart();

  } else if (data.status === "new_scenario_started") {
    startFreshFund(data, "New Market Conditions",
      "A new era begins. Your fund resets to a fresh Rs. 1,000,000 — pick a company and start again.", false);

  } else if (data.status === "new_block_started") {
    startFreshFund(data, `${data.round_label}: A Different Fund`,
      "You're handed a new fund, tied to a single stock. Watch the S&P SL20 benchmark bar at the top: when the market runs ahead and you fall behind, that gap is the moment that counts.", true);

  } else if (data.status === "events_started") {
    startEvents(data);
  } else if (data.status === "all_blocks_complete") {
    // (fallback if the event round is disabled server-side)
    await finishSession();
  }
});

// ---------------- matched-stakes event round ----------------
let eventTotal = 16;
let eventCommit = 50;

function startEvents(data) {
  eventTotal = data.total_events || 16;
  showTransition(
    "One last thing — quick market calls",
    "A handful of one-off 50/50 bets. Decide how much you'd commit to each. This is where your instinct for risk really shows.",
    () => { renderEvent(data.event); showScreen("events"); }
  );
}

function renderEvent(ev) {
  if (!ev) return;
  $("event-progress").innerText = `${ev.index} / ${ev.total}`;
  $("event-ticker").innerText = ev.ticker;
  $("event-gain").innerText = `+${ev.gain_pct}%`;
  $("event-loss").innerText = `-${ev.loss_pct}%`;
  $("event-stake").innerText = formatMoney(ev.stake);
  applyEventSlider(50);
}

const evSlider = $("event-slider");
const evFill = $("ev-beam-fill");
const evHandle = $("ev-beam-handle");
const evPct = $("ev-beam-pct");

function applyEventSlider(v) {
  eventCommit = Math.max(0, Math.min(100, Math.round(v)));
  evSlider.value = eventCommit;
  evFill.style.width = eventCommit + "%";
  evHandle.style.left = eventCommit + "%";
  evPct.innerText = eventCommit + "%";
  const stakeText = $("event-stake").innerText.replace("Rs. ", "").replace(/,/g, "");
  const stake = parseFloat(stakeText) || 200000;
  $("event-commit-value").innerText = formatMoney((eventCommit / 100) * stake);
}
evSlider.addEventListener("input", () => applyEventSlider(parseInt(evSlider.value)));

$("btn-commit").addEventListener("click", async () => {
  const btn = $("btn-commit");
  btn.disabled = true;
  const res = await (await fetch(`${API_BASE}/session/${sessionId}/event/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fraction: eventCommit / 100 }),
  })).json();
  btn.disabled = false;
  if (res.status === "events_complete") {
    await finishSession();
  } else {
    renderEvent(res.event);
  }
});

function startFreshFund(data, title, sub, isNewBlock) {
  marketState = data.market_state;
  benchmark = data.benchmark;
  equity = cash = data.cash;
  equityBeforeDecision = data.cash;
  fixedTicker = isNewBlock ? data.fixed_ticker : fixedTicker; // block change assigns DIAL
  lockedTicker = null;
  confirmedPct = 0;
  firstDecisionOfFund = true;
  refStockPrice = null; refStockTicker = null;
  selectedTicker = fixedTicker || Object.keys(marketState)[0];

  showTransition(title, sub, () => {
    updateTopbar(data.round_label, data.day, data.total_days, cash, equity);
    setConsequenceIntro();
    renderBenchmark();
    resetSlider();
    renderTickers();
    updateSelectedHeader();
    updateHoldingReadout();
    updatePreview();
    renderChart();
    showScreen("trading");
  });
}

// ---------------- advancing beat ----------------
function showAdvancing() {
  return new Promise((resolve) => {
    if (REDUCED_MOTION) return resolve();
    $("advance-overlay").classList.remove("hidden");
    setTimeout(resolve, 620);
  });
}
function hideAdvancing() { $("advance-overlay").classList.add("hidden"); }

// ---------------- transitions ----------------
function showTransition(title, sub, onContinue) {
  $("transition-title").innerText = title;
  $("transition-sub").innerText = sub;
  showScreen("transition");
  const btn = $("btn-continue");
  const handler = () => { btn.removeEventListener("click", handler); onContinue(); };
  btn.addEventListener("click", handler);
}

// ---------------- activity log ----------------
async function refreshLog() {
  const data = await (await fetch(`${API_BASE}/session/${sessionId}/log`)).json();
  const list = $("log-list");
  list.innerHTML = "";
  if (!data.log || data.log.length === 0) {
    list.innerHTML = `<div class="log-empty">No decisions yet.</div>`;
    return;
  }
  data.log.slice().reverse().forEach((entry, i) => {
    const n = data.log.length - i;
    const detail = entry.target_pct != null
      ? `${Math.round(entry.target_pct * 100)}% in ${entry.ticker}`
      : "—";
    const wc = entry.wealth_change;
    const wcClass = wc == null ? "flat" : wc > 0 ? "up" : wc < 0 ? "down" : "flat";
    const wcText = wc == null ? "" : (wc > 0 ? "+" : "") + Math.round(wc).toLocaleString();
    const row = document.createElement("div");
    row.className = "log-entry";
    row.innerHTML = `
      <span class="log-date mono">#${n}</span>
      <span class="log-detail">${detail}</span>
      <span class="log-pnl mono ${wcClass}">${wcText}</span>`;
    list.appendChild(row);
  });
}

// ---------------- results ----------------
async function finishSession() {
  const data = await (await fetch(`${API_BASE}/session/${sessionId}/finish`, { method: "POST" })).json();
  // Prefer the robust v2 profile (alpha fixed, decoupled lambda, confidence flags).
  const est = data.profile || data.calibrated_estimate || data.raw_estimate;
  const confidence = data.confidence || {};

  const meta = {
    alpha: { label: "Diminishing Sensitivity (α)", blurb: (v) => v <= 0.75 ? "Big swings quickly stop feeling proportionally bigger to you." : "You feel gains and losses close to their true size." },
    lambda: { label: "Loss Aversion (λ)", blurb: (v) => v >= 2.5 ? "Losses hurt far more than equal gains please." : v >= 1.5 ? "Mild asymmetry between losses and gains." : "You treat gains and losses fairly evenly." },
    gamma: { label: "Regret / FOMO (γ)", blurb: (v) => v >= 2.0 ? "Strong pull to chase the market when it runs without you." : v >= 0.8 ? "Some sensitivity to missing out." : "Largely unbothered by what the market does elsewhere." },
  };

  const grid = $("results-grid");
  grid.innerHTML = "";
  ["lambda", "gamma", "alpha"].forEach((key) => {
    if (est[key] == null) return;
    const m = meta[key];
    const conf = confidence[key];               // {level, reason} for lambda / gamma
    let confHtml = "";
    if (conf && conf.level && conf.level !== "ok") {
      const cls = conf.level === "uninformative" ? "conf-bad" : "conf-warn";
      const label = conf.level === "uninformative" ? "Not reliable" : "Low confidence";
      confHtml = `<div class="result-conf ${cls}" title="${conf.reason || ""}">${label}</div>`;
    }
    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-label">${m.label}</div>
      <div class="result-value mono">${Number(est[key]).toFixed(2)}</div>
      ${confHtml}
      <div class="result-blurb">${m.blurb(Number(est[key]))}</div>`;
    grid.appendChild(card);
  });
  const lamNote = data.lambda_source === "matched_stakes_events"
    ? " Loss aversion measured from your matched-stakes calls."
    : "";
  $("results-note").innerText =
    `Fitted from ${data.n_obs_block1 ?? "?"} loss-aversion decisions and ${data.n_obs_block2 ?? "?"} regret decisions.${lamNote}`;
  showScreen("results");
}