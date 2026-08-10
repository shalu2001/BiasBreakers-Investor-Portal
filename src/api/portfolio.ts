import { apiClient } from './client';

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface Holding {
  ticker: string;
  name: string;
  sector: string;
  weightPct: number;
  changePct: number;
  candles: Candle[];
}

export type PortfolioRange = '1M' | '3M' | '6M' | '1Y';

export async function getPortfolio(range: PortfolioRange = '3M'): Promise<Holding[]> {
  const { data } = await apiClient.get<Holding[]>('/portfolio/holdings', {
    params: { range },
  });
  return data;
}

export interface TickerCandles {
  ticker: string;
  name: string;
  changePct: number;
  candles: Candle[];
}

// Chart data only, for an explicit ticker list -- doesn't recompute a
// recommendation server-side, so it never drifts from whatever allocation
// the investor already approved via getRecommendation().
export async function getPortfolioCandles(
  tickers: string[],
  range: PortfolioRange = '3M',
): Promise<TickerCandles[]> {
  const { data } = await apiClient.get<TickerCandles[]>('/portfolio/candles', {
    params: { tickers: tickers.join(','), range },
  });
  return data;
}
