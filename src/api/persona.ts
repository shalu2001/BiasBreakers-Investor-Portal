import { apiClient } from './client';

export interface PersonaProfile {
  archetype: string;
  summary: string;
  riskTolerance: number;
  lossAversion: number;
  regretAversion: number;
}

// TODO: confirm the real path/shape with the trading-simulation backend.
export async function getPersona(): Promise<PersonaProfile> {
  const { data } = await apiClient.get<PersonaProfile>('/persona/me');
  return data;
}
