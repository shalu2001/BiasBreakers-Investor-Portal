import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../session/AuthContext';
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
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <header className={styles.header}>
      <BrandLockup className={styles.brand} size={20} />
      <div className={styles.right}>
        <nav className={styles.nav}>
          {links.map((link) => (
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
