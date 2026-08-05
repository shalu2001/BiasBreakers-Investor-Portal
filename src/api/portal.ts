import axios from 'axios';

// Portal auth + profile API. These routes live on the same FastAPI backend as
// the behavioural game (mounted under /portal), so we reuse its base URL. The
// JWT is attached to every request and persisted in sessionStorage so a refresh
// keeps you signed in for the session.
const BASE = import.meta.env.VITE_GAME_API_BASE_URL ?? 'http://127.0.0.1:8000';
export const portalClient = axios.create({ baseURL: BASE, timeout: 15_000 });

const TOKEN_KEY = 'sl20.token';

export function setToken(token: string | null) {
  if (token) {
    sessionStorage.setItem(TOKEN_KEY, token);
    portalClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
    delete portalClient.defaults.headers.common.Authorization;
  }
}

export function loadToken(): string | null {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) portalClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  return token;
}

export interface PortalUser {
  id: string;
  email: string;
  name: string | null;
}

interface AuthResponse {
  token: string;
  user: PortalUser;
}

export interface OnboardingAnswers {
  hasExistingPortfolio: boolean | null;
  investmentAmount: number | null;
  goal: string | null;
}

export interface SavedParameters {
  alpha?: number | null;
  lambda?: number | null;
  gamma?: number | null;
  confidence?: Record<string, unknown> | null;
  source?: string | null;
}

export interface SavedProfile {
  onboarding: Partial<OnboardingAnswers>;
  parameters: SavedParameters;
  updated_at: string | null;
}

export async function register(email: string, password: string, name?: string): Promise<AuthResponse> {
  const { data } = await portalClient.post<AuthResponse>('/portal/auth/register', { email, password, name });
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await portalClient.post<AuthResponse>('/portal/auth/login', { email, password });
  return data;
}

export async function fetchMe(): Promise<PortalUser> {
  const { data } = await portalClient.get<PortalUser>('/portal/auth/me');
  return data;
}

export async function updateAccount(name: string): Promise<PortalUser> {
  const { data } = await portalClient.put<PortalUser>('/portal/account', { name });
  return data;
}

export async function getProfile(): Promise<SavedProfile> {
  const { data } = await portalClient.get<SavedProfile>('/portal/profile');
  return data;
}

export async function saveOnboarding(answers: OnboardingAnswers): Promise<void> {
  await portalClient.put('/portal/profile/onboarding', answers);
}

export async function saveParameters(params: SavedParameters): Promise<void> {
  await portalClient.put('/portal/profile/parameters', params);
}

// Turn an axios error into a short, user-facing message.
export function authErrorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (err.code === 'ERR_NETWORK') return 'Cannot reach the server. Is the backend running?';
  }
  return fallback;
}
