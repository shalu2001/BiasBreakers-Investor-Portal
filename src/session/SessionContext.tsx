import { createContext, useContext, useState, type ReactNode } from 'react';

// App-wide session that threads the onboarding answers and the behavioural
// game result through the whole journey (Login -> Onboarding -> Game ->
// Dashboard). Backed by sessionStorage so a page refresh mid-flow doesn't wipe
// what the user already told us. This is frontend-only state; nothing here
// depends on a portal backend existing.

export interface OnboardingAnswers {
  hasExistingPortfolio: boolean | null;
  investmentAmount: number | null;
  goal: string | null;
}

export interface BehaviouralProfile {
  alpha: number | null;
  lambda: number | null;
  gamma: number | null;
}

interface SessionState {
  onboarding: OnboardingAnswers;
  profile: BehaviouralProfile | null;
}

interface SessionContextValue extends SessionState {
  setOnboarding: (answers: OnboardingAnswers) => void;
  setProfile: (profile: BehaviouralProfile) => void;
  reset: () => void;
}

const STORAGE_KEY = 'sl20.session';

const EMPTY: SessionState = {
  onboarding: { hasExistingPortfolio: null, investmentAmount: null, goal: null },
  profile: null,
};

function load(): SessionState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return { ...EMPTY, ...(JSON.parse(raw) as Partial<SessionState>) };
  } catch {
    /* ignore malformed/absent storage */
  }
  return EMPTY;
}

function persist(state: SessionState) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable (private mode etc.) — degrade to in-memory only */
  }
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(load);

  function setOnboarding(onboarding: OnboardingAnswers) {
    setState((s) => {
      const next = { ...s, onboarding };
      persist(next);
      return next;
    });
  }

  function setProfile(profile: BehaviouralProfile) {
    setState((s) => {
      const next = { ...s, profile };
      persist(next);
      return next;
    });
  }

  function reset() {
    persist(EMPTY);
    setState(EMPTY);
  }

  return (
    <SessionContext.Provider value={{ ...state, setOnboarding, setProfile, reset }}>
      {children}
    </SessionContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within a SessionProvider');
  return ctx;
}
