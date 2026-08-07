import { Outlet, useLocation } from 'react-router-dom';
import { NavBar } from './NavBar';
import styles from './AppLayout.module.css';

export function AppLayout() {
  const { pathname } = useLocation();
  return (
    <div>
      <NavBar />
      <main className={styles.main}>
        {/* keyed by route so each navigation replays a subtle enter animation */}
        <div key={pathname} className={styles.pageEnter}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
