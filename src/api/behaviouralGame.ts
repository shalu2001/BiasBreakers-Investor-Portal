import axios from 'axios';

// The behavioural-simulation game talks to its own FastAPI backend (the trading
// engine + estimators), which is separate from the portal API. Its base URL is
// configured independently so this feature stays decoupled from the portal's
// `apiClient`. Set VITE_GAME_API_BASE_URL in .env (defaults to localhost:8000).
const gameClient = axios.create({
  baseURL: import.meta.env.VITE_GAME_API_BASE_URL ?? 'http://127.0.0.1:8000',
  timeout: 15_000,
});

// ---- shapes returned by the backend ----------------------------------------
export interface TickerInfo {
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
  ticker_return_pct: number | null;
}
export type MarketState = Record<string, TickerInfo>;

export interface Benchmark {
  index_return: number;
  held_return: number;
  market_gap: number;
  in_cash: boolean;
  show: boolean;
}

export interface SessionState {
  session_id: string;
  round_label: string;
  day: number;
  total_days: number;
  market_state: MarketState;
  cash: number;
  fixed_ticker: string | null;
  benchmark: Benchmark | null;
}

export interface HistoryBar {
  day: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface GameEvent {
  index: number;
  total: number;
  ticker: string;
  gain_pct: number;
  loss_pct: number;
  stake: number;
}

export interface LogEntry {
  ticker: string | null;
  target_pct: number | null;
  wealth_change: number | null;
}

export type AdvanceResult =
  | ({ status: 'at_checkpoint'; round_label: string; day: number; total_days: number;
       market_state: MarketState; cash: number; equity: number; benchmark: Benchmark | null })
  | ({ status: 'new_scenario_started' | 'new_block_started'; round_label: string; day: number;
       total_days: number; market_state: MarketState; cash: number; fixed_ticker: string | null;
       benchmark: Benchmark | null })
  | ({ status: 'events_started'; event: GameEvent; total_events: number })
  | ({ status: 'all_blocks_complete' });

export type EventCommitResult =
  | { status: 'next_event'; event: GameEvent }
  | { status: 'events_complete' };

export interface Confidence { level: 'ok' | 'weak' | 'uninformative'; reason?: string }

export interface FinishResult {
  profile: { alpha: number | null; lambda: number | null; gamma: number | null };
  confidence?: Partial<Record<'alpha' | 'lambda' | 'gamma', Confidence>>;
  lambda_source?: string;
  n_obs_block1?: number;
  n_obs_block2?: number;
}

// ---- endpoint wrappers ------------------------------------------------------
export async function createSession(): Promise<SessionState> {
  const { data } = await gameClient.post<SessionState>('/session/create');
  return data;
}

export async function getHistory(sessionId: string, ticker: string, lookback = 15): Promise<HistoryBar[]> {
  const { data } = await gameClient.get<{ history: HistoryBar[] }>(
    `/session/${sessionId}/history/${ticker}`, { params: { lookback } },
  );
  return data.history;
}

export async function allocate(sessionId: string, ticker: string, targetPct: number): Promise<void> {
  await gameClient.post(`/session/${sessionId}/allocate`, { ticker, target_pct: targetPct });
}

export async function advance(sessionId: string): Promise<AdvanceResult> {
  const { data } = await gameClient.post<AdvanceResult>(`/session/${sessionId}/advance`);
  return data;
}

export async function getLog(sessionId: string): Promise<LogEntry[]> {
  const { data } = await gameClient.get<{ log: LogEntry[] }>(`/session/${sessionId}/log`);
  return data.log ?? [];
}

export async function commitEvent(sessionId: string, fraction: number): Promise<EventCommitResult> {
  const { data } = await gameClient.post<EventCommitResult>(
    `/session/${sessionId}/event/commit`, { fraction },
  );
  return data;
}

export async function finishSession(sessionId: string): Promise<FinishResult> {
  const { data } = await gameClient.post<FinishResult>(`/session/${sessionId}/finish`);
  return data;
}

// ---- DEV ONLY: skip the game, auto-play, and validate parameter recovery ----
export interface DevAutoplayParams {
  alpha: number;
  lam: number; // lambda (reserved word on the wire -> 'lam')
  gamma: number;
  k?: number;
  noise?: number;
  seed?: number;
}

export interface DevAutoplayResult {
  chosen: { alpha: number; lambda: number; gamma: number };
  recovered: { alpha: number; lambda: number; gamma: number };
  errors: { alpha: number; lambda: number; gamma: number };
  profile_source: string;
  lambda_source: string;
  confidence: Partial<Record<'alpha' | 'lambda' | 'gamma', Confidence>>;
  n_obs_block1?: number;
  n_obs_block2?: number;
}

export async function devAutoplay(params: DevAutoplayParams): Promise<DevAutoplayResult> {
  const { data } = await gameClient.post<DevAutoplayResult>('/session/dev/autoplay', params, {
    timeout: 60_000, // full engine play + recovery
  });
  return data;
}
