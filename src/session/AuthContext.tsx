import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  login as apiLogin,
  register as apiRegister,
  fetchMe,
  setToken,
  loadToken,
  type PortalUser,
} from '../api/portal';

interface AuthContextValue {
  user: PortalUser | null;
  token: string | null;
  ready: boolean; // false until we've checked any stored token on first load
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  setUser: (user: PortalUser) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => loadToken());
  const [user, setUser] = useState<PortalUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      if (token) {
        try {
          setUser(await fetchMe());
        } catch {
          setToken(null);
          setTok(null); // stored token was invalid/expired
        }
      }
      setReady(true);
    })();
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(email: string, password: string) {
    const res = await apiLogin(email, password);
    setToken(res.token);
    setTok(res.token);
    setUser(res.user);
  }

  async function register(email: string, password: string, name?: string) {
    const res = await apiRegister(email, password, name);
    setToken(res.token);
    setTok(res.token);
    setUser(res.user);
  }

  function logout() {
    setToken(null);
    setTok(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, ready, login, register, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
