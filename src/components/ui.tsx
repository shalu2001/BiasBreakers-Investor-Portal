import type { ReactNode } from 'react';
import styles from './ui.module.css';

export function Spinner({ size = 28 }: { size?: number }) {
  return (
    <span
      className={styles.spinner}
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className={styles.loadingWrap}>
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  icon = '⌾',
  title,
  message,
  action,
}: {
  icon?: string;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className={styles.emptyWrap}>
      <div className={styles.emptyIcon}>{icon}</div>
      <div className={styles.emptyTitle}>{title}</div>
      {message && <div className={styles.emptyMsg}>{message}</div>}
      {action && <div className={styles.emptyAction}>{action}</div>}
    </div>
  );
}
