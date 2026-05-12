import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import styles from './Navbar.module.css';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const handleLogout = () => { logout(); navigate('/'); };

  return (
    <nav className={styles.navbar}>
      <Link to="/" className={styles.logo}>
        <span className={styles.logoDot} />
        NewsDispatch
      </Link>

      <div className={styles.links}>
        {user ? (
          <>
            <Link to="/dashboard" className={`${styles.link} ${pathname === '/dashboard' ? styles.active : ''}`}>
              Dashboard
            </Link>
            <Link to="/pipeline"  className={`${styles.link} ${pathname === '/pipeline'  ? styles.active : ''}`}>
              Pipeline
            </Link>
            <div className={styles.userPill}>
              <span className={styles.avatar} style={{ background: user.avatar_color || '#4F46E5' }}>
                {(user.name || user.email || 'U')[0].toUpperCase()}
              </span>
              <span className={styles.userName}>{user.name?.split(' ')[0] || 'User'}</span>
            </div>
            <button className={styles.ghostBtn} onClick={handleLogout}>Sign Out</button>
          </>
        ) : (
          <>
            <Link to="/login"  className={styles.link}>Sign In</Link>
            <Link to="/signup" className={styles.primaryBtn}>Get Started</Link>
          </>
        )}
      </div>
    </nav>
  );
}
