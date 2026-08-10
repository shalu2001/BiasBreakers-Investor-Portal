import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../session/AuthContext';
import { useSession } from '../session/SessionContext';
import { BrandLockup } from './BrandLockup';
import styles from './NavBar.module.css';

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/recommend', label: 'Recommendation' },
  { to: '/news', label: 'News' },
  { to: '/account', label: 'Account' },
];

export function NavBar() {
  const { logout } = useAuth();
  const { reset, recommendation } = useSession();
  const navigate = useNavigate();

  // Same gate as RequirePortfolio -- no point linking to a page that would
  // just bounce back to /recommend.
  const hasSelectedStocks = (recommendation ?? []).some(
    (row) => row.ticker !== 'CASH' && row.recommendedPct > 0,
  );
  const visibleLinks = links.filter((link) => link.to !== '/portfolio' || hasSelectedStocks);

  function handleLogout() {
    logout();
    // Clears the sessionStorage-backed recommendation/onboarding/profile
    // state too -- otherwise it outlives the login (sessionStorage isn't
    // tied to who's signed in), so the next account in this tab would land
    // on /recommend and see the previous user's optimized table already
    // populated instead of the "click Optimize" empty state.
    reset();
    navigate('/login');
  }

  return (
    <header className={styles.header}>
      <BrandLockup className={styles.brand} size={20} />
      <div className={styles.right}>
        <nav className={styles.nav}>
          {visibleLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <button type="button" className={styles.logout} onClick={handleLogout}>
          Log out
        </button>
      </div>
    </header>
  );
}
