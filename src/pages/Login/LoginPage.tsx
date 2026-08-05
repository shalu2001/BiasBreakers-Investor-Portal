import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../session/AuthContext';
import { authErrorMessage } from '../../api/portal';
import styles from './LoginPage.module.css';

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate('/');
    } catch (err) {
      setError(authErrorMessage(err, 'Invalid email or password'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.split}>
      <div className={styles.brandSide}>
        <span className={styles.brand}>SL20 Invest</span>
        <h1 className={styles.headline}>Understand your risk. Own your allocation.</h1>
        <p className={styles.subcopy}>
          A companion dashboard built on the S&amp;P SL20 — grounded in behavioral analysis of
          how you actually invest.
        </p>
      </div>
      <div className={styles.formSide}>
        <h2 className={styles.formTitle}>Sign in</h2>
        <p className={styles.formSubtitle}>Welcome back. Enter your details to continue.</p>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.label} htmlFor="email">Email</label>
          <input
            id="email" type="email" placeholder="you@example.com" value={email}
            onChange={(e) => setEmail(e.target.value)} className={styles.input} required
          />
          <label className={styles.label} htmlFor="password">Password</label>
          <input
            id="password" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)} className={styles.input} required
          />

          {error && <p style={{ color: 'var(--color-danger, #c0392b)', fontSize: 13, margin: '4px 0 0' }}>{error}</p>}

          <button type="submit" className={styles.submitButton} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in →'}
          </button>

          <p className={styles.createAccount}>
            New here? <Link to="/register">Create an account</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
