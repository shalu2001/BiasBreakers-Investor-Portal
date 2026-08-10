import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useSession } from '../session/SessionContext';

// Gate for /portfolio: an investor has nothing to show there until their
// last optimization actually selected some stocks (CASH-only or an empty
// recommendation doesn't count) -- send them to /recommend to run one
// instead of rendering an empty portfolio page.
export function RequirePortfolio({ children }: { children: ReactNode }) {
  const { recommendation } = useSession();
  const hasSelectedStocks = (recommendation ?? []).some(
    (row) => row.ticker !== 'CASH' && row.recommendedPct > 0,
  );
  if (!hasSelectedStocks) return <Navigate to="/recommend" replace />;
  return <>{children}</>;
}
