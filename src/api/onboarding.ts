import { apiClient } from './client';

// TODO: confirm the real path/shape with the trading-simulation backend.
// On "Yes", the user is handed off to the (separate) trading simulation app
// to enter their existing holdings before returning here.
export async function submitHasExistingPortfolio(hasExistingPortfolio: boolean): Promise<void> {
  await apiClient.post('/onboarding/existing-portfolio', { hasExistingPortfolio });
}
