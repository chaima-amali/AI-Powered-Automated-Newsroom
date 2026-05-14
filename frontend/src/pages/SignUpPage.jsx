import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '../services/auth';
import Navbar from '../components/Navbar';
import logo from '../assets/logo.png';
import styles from './AuthPage.module.css';

export default function SignUpPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handle = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const result = await register(form.name, form.email, form.password);
    if (result.success) {
      navigate('/dashboard', { replace: true });
    } else {
      setError(result.error);
      setLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <Navbar />
      <div className={styles.center}>
        <div className={styles.card}>
          {/* Left brand panel */}
          <div className={styles.brandPanel}>
            <div className={styles.brandBorder}>
              <div className={styles.brandInner}>
                <div className={styles.brandLogo}>
                  <img src={logo} alt="News Dispatch" className={styles.brandLogoImg} />
                </div>
              </div>
            </div>
          </div>

          {/* Right form panel */}
          <div className={styles.formPanel}>
            <h2 className={styles.formTitle}>Create Account</h2>
            <p className={styles.formSubtitle}>Create an account to get unforgettable experience</p>

            <form onSubmit={handleSubmit} className={styles.form}>
              <div className={styles.field}>
                <label className={styles.label}>Name</label>
                <input
                  type="text"
                  name="name"
                  value={form.name}
                  onChange={handle}
                  className={styles.input}
                  placeholder=""
                  required
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>Email</label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handle}
                  className={styles.input}
                  placeholder=""
                  required
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
                  placeholder=""
                  required
                />
              </div>

              <button type="submit" className={styles.submitBtn} disabled={loading}>
                {loading ? 'Signing Up...' : 'Sign Up'}
              </button>

              {error && <p className={styles.error}>{error}</p>}

              <p className={styles.switchText}>
                You already have an account? <Link to="/login" className={styles.switchLink}>Login</Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
