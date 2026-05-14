import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/logo.png';
import Navbar from '../components/Navbar';
import styles from './AuthPage.module.css';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm]   = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handle = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const result = await login(form.email, form.password);
    if (result.success) {
      navigate('/dashboard', { replace: true });
    } else {
      setError(result.error);
      setLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Inline minimal nav */}
      <Navbar />

      <div className={styles.center}>
        <div className={styles.card}>
          {/* Left brand panel */}
          <div className={styles.brandPanel}>
            <div className={styles.brandInner}>
              <div className={styles.brandLogo}>
                <img src={logo} alt="News Dispatch" className={styles.brandLogoImg} />
              </div>
            </div>
          </div>

          {/* Right form panel */}
          <div className={styles.formPanel}>
            <h2 className={styles.formTitle}>Welcome Back</h2>
            <p className={styles.formSubtitle}>Sign in to your News Dispatch account</p>

            {/* Hint box */}
            <div className={styles.hintBox}>
              <span className={styles.hintIcon}>💡</span>
              <div>
                <div className={styles.hintTitle}>Demo credentials</div>
                <div className={styles.hintCreds}>alex@newsdispatch.com</div>
                <div className={styles.hintCreds}>news1234</div>
              </div>
            </div>

            <form onSubmit={handleSubmit} className={styles.form}>
              {error && <div className={styles.errorMsg}>{error}</div>}

              <div className={styles.field}>
                <label className={styles.label}>Email</label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handle}
                  className={styles.input}
                  placeholder="your@email.com"
                  required
                  autoComplete="email"
                />
              </div>

              <div className={styles.field}>
                <label className={styles.label}>Password</label>
                <input
                  type="password"
                  name="password"
                  value={form.password}
                  onChange={handle}
                  className={styles.input}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                />
                <div className={styles.forgotWrap}>
                  <Link to="/forgot-password" className={styles.forgotLink}>Forget Password?</Link>
                </div>
              </div>

              <button type="submit" className={styles.submitBtn} disabled={loading}>
                {loading ? 'Signing in…' : 'Login'}
              </button>

              <p className={styles.switchText}>
                Don't have an account? <Link to="/signup" className={styles.switchLink}>Sign Up</Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
