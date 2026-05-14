import { Link, useLocation } from 'react-router-dom';
import styles from './Navbar.module.css';
import logo from '../assets/logo.png';

export default function Navbar() {
  const location = useLocation();
  const isApp = ['/dashboard', '/article', '/profile', '/settings'].some(p => location.pathname.startsWith(p));

  return (
    <nav className={styles.navbar}>
      <div className={styles.navContainer}>
        <Link to="/" className={styles.logo}>
          <img src={logo} alt="News Dispatch" className={styles.logoIcon} />
        </Link>

        <div className={styles.links}>
          {isApp ? (
            <>
              <Link to="/dashboard" className={`${styles.link} ${location.pathname === '/dashboard' ? styles.active : ''}`}>News</Link>
              <Link to="/profile" className={styles.link}>Profile</Link>
              <Link to="/settings" className={styles.link}>Settings</Link>
            </>
          ) : (
            <>
              <Link to="/#features" className={styles.link}>Features</Link>
              <Link to="/#how-it-works" className={styles.link}>How it works</Link>
              <Link to="/login" className={styles.link}>Login</Link>
              <Link to="/signup" className={styles.ctaBtn}>Join Us</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
