import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import styles from './AuthPage.module.css';

export default function SignUpPage() {
  const { register } = useAuth();
  const navigate     = useNavigate();

  const [name,     setName]     = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    setError(''); setLoading(true);
    const result = await register(name.trim(), email.trim(), password);
    setLoading(false);
    if (result.success) {
      navigate('/dashboard', { replace: true });
    } else {
      setError(result.error || 'Registration failed.');
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <Link to="/" className={styles.logoWrap}>
          <span className={styles.logoDot} />
          NewsDispatch
        </Link>

        <h1 className={styles.title}>Create account</h1>
        <p className={styles.sub}>Join the NewsDispatch platform</p>

        {error && <div className={styles.errorBox}>{error}</div>}

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="name">Full name</label>
            <input id="name" type="text" placeholder="Alex Johnson" required
              value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className={styles.field}>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" placeholder="your@email.com" required
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className={styles.field}>
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="new-password" placeholder="Min. 8 characters" required
              value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <button type="submit" className={styles.submit} disabled={loading}>
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <p className={styles.switchLine}>
          Already have an account?{' '}
          <Link to="/login" className={styles.switchLink}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}
