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
