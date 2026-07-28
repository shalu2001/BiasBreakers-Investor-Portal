import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './LoginPage.module.css';

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // TODO: wire up to the real auth endpoint once it exists.
    navigate('/onboarding');
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
          <label className={styles.label} htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={styles.input}
          />

          <label className={styles.label} htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={styles.input}
          />

          <a href="#" className={styles.forgotLink}>
            Forgot password?
          </a>

          <button type="submit" className={styles.submitButton}>
            Sign in →
          </button>

          <p className={styles.createAccount}>
            New here? <a href="#">Create an account</a>
          </p>
        </form>
      </div>
    </div>
  );
}
