import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../session/AuthContext';
import { authErrorMessage } from '../../api/portal';
import { BrandLockup } from '../../components/BrandLockup';
import styles from './LoginPage.module.css';

export function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setBusy(true);
    try {
      await register(email.trim(), password, name.trim() || undefined);
      navigate('/onboarding'); // new account → straight into onboarding + game
    } catch (err) {
      setError(authErrorMessage(err, 'Could not create your account'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.split}>
      <div className={styles.brandSide}>
        <BrandLockup className={styles.brand} size={22} />
        <h1 className={styles.headline}>Understand your risk. Own your allocation.</h1>
        <p className={styles.subcopy}>
          Create an account, play a five-minute game, and get a portfolio tuned to how you
          actually feel about risk.
        </p>
      </div>
      <div className={styles.formSide}>
        <h2 className={styles.formTitle}>Create your account</h2>
        <p className={styles.formSubtitle}>It takes a few seconds.</p>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.label} htmlFor="name">Name <span style={{ opacity: 0.6 }}>(optional)</span></label>
          <input
            id="name" type="text" placeholder="Your name" value={name}
            onChange={(e) => setName(e.target.value)} className={styles.input}
          />
          <label className={styles.label} htmlFor="email">Email</label>
          <input
            id="email" type="email" placeholder="you@example.com" value={email}
            onChange={(e) => setEmail(e.target.value)} className={styles.input} required
          />
          <label className={styles.label} htmlFor="password">Password</label>
          <input
            id="password" type="password" placeholder="At least 6 characters" value={password}
            onChange={(e) => setPassword(e.target.value)} className={styles.input} required
          />

          {error && <p style={{ color: 'var(--color-danger, #c0392b)', fontSize: 13, margin: '4px 0 0' }}>{error}</p>}

          <button type="submit" className={styles.submitButton} disabled={busy}>
            {busy ? 'Creating…' : 'Create account →'}
          </button>

          <p className={styles.createAccount}>
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
