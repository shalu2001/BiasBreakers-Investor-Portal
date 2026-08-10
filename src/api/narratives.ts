import { apiClient } from './client';

export interface NarrativeStock {
  ticker: string;
  name: string;
}

export interface NarrativeItem {
  id: string;
  type: 'macro' | 'micro';
  title: string;
  stocks: NarrativeStock[];
}

export interface NarrativesResponse {
  as_of: string;
  narratives: NarrativeItem[];
}

// Latest narratives (ranked by confidence) and the stocks each one affects.
// Sourced from the most recent prediction cache file on the backend.
export async function getNarratives(): Promise<NarrativesResponse> {
  const { data } = await apiClient.get<NarrativesResponse>('/narratives', { timeout: 30_000 });
  return data;
}
