import { apiClient } from './client';

export type NewsCategory = 'macro' | 'micro';

export interface NewsItem {
  ticker?: string;
  category: NewsCategory;
  headline: string;
  source: string;
  timeAgo: string;
}

export interface NewsFilters {
  category?: NewsCategory;
  tickers?: string[];
}

// TODO: confirm the real path/shape with the backend.
export async function getNews(filters: NewsFilters = {}): Promise<NewsItem[]> {
  const { data } = await apiClient.get<NewsItem[]>('/news', { params: filters });
  return data;
}
