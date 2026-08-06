import { apiClient } from './client';

export interface ReallocationRow {
  ticker: string;
  name: string;
  currentPct: number;
  recommendedPct: number;
}

export interface PastRecommendation {
  date: string;
  description: string;
  // null until feedback submitted via submitRecommendationFeedback is
  // correlated back to a specific past recommendation (not built yet).
  rating: number | null;
}

export async function getRecommendation(): Promise<ReallocationRow[]> {
  const { data } = await apiClient.get<ReallocationRow[]>('/recommendation/current');
  return data;
}

export async function getPastRecommendations(): Promise<PastRecommendation[]> {
  const { data } = await apiClient.get<PastRecommendation[]>('/recommendation/history');
  return data;
}

// Feeds the user's comfort rating back into the optimization loop as a training signal.
export async function submitRecommendationFeedback(rating: number): Promise<void> {
  await apiClient.post('/recommendation/feedback', { rating });
}
