import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../session/AuthContext';

// Gate for protected routes: sends you to /login until you're signed in.
// Waits for the initial token check so a valid session isn't bounced on refresh.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, ready } = useAuth();
  if (!ready) return null;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
