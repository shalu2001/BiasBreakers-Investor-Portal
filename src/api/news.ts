import { apiClient } from './client';

export type NewsCategory = 'macro' | 'micro';

export interface NewsItem {
  ticker?: string;
  category: NewsCategory;
  headline: string;
  content: string;
  source: string;
  /** ISO 8601 publish timestamp; the frontend derives the relative "time ago" label. */
  publishedDate?: string;
}

export interface TickerOption {
  ticker: string;
  name: string;
}

interface NewsItemResponse {
  ticker?: string | null;
  category: NewsCategory;
  headline: string;
  content?: string;
  source?: string;
  published_date?: string | null;
}

// Backend returns the full news window; filtering by category/ticker happens client-side.
export async function getNews(): Promise<NewsItem[]> {
  const { data } = await apiClient.get<NewsItemResponse[]>('/news');
  return data.map((item) => ({
    ticker: item.ticker ?? undefined,
    category: item.category,
    headline: item.headline,
    content: item.content ?? '',
    source: item.source ?? '',
    publishedDate: item.published_date ?? undefined,
  }));
}

// SL20 ticker → company options for the news filter dropdown.
export async function getTickers(): Promise<TickerOption[]> {
  const { data } = await apiClient.get<TickerOption[]>('/tickers');
  return data;
}
