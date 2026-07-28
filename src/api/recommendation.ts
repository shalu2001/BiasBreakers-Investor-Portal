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
  rating: number;
}

// TODO: confirm the real path/shape with the RL optimization backend.
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
