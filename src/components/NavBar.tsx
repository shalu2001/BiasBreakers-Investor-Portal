import { NavLink } from 'react-router-dom';
import styles from './NavBar.module.css';

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/recommend', label: 'Recommendation' },
  { to: '/news', label: 'News' },
];

export function NavBar() {
  return (
    <header className={styles.header}>
      <span className={styles.brand}>SL20 Invest</span>
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
    </header>
  );
}
