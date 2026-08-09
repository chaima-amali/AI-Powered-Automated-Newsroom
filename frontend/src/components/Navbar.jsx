import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import logo from '../assets/logo.png';
import styles from './Navbar.module.css';

export default function Navbar() {
  const location    = useLocation();
  const navigate    = useNavigate();
  const [searchParams] = useSearchParams();
  const isApp = ['/dashboard', '/article', '/profile', '/settings'].some(p => location.pathname.startsWith(p));

  // Sync input with URL ?q= param
  const [searchValue, setSearchValue] = useState(searchParams.get('q') || '');

  useEffect(() => {
    setSearchValue(searchParams.get('q') || '');
  }, [searchParams]);

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') {
      const q = searchValue.trim();
      if (q) {
        navigate(`/dashboard?q=${encodeURIComponent(q)}`);
      } else {
        navigate('/dashboard');
      }
    }
  };

  const handleSearchClear = () => {
    setSearchValue('');
    navigate('/dashboard');
  };

  // Determine active state manually since React Router's NavLink can be tricky with exact matches
  const currentPath = location.pathname;

  return (
    <nav className={styles.navbar}>
      <div className={styles.navContainer}>
        {/* Left: Logo */}
        <Link to="/" className={styles.logo}>
          <div className={styles.logoIcon}>
            <img src={logo} alt="NewsDispatch" style={{ height: '56px', width: 'auto', display: 'block' }} />
          </div>
        </Link>

        {/* Center: Links */}
        <div className={styles.linksContainer}>
          <div className={styles.linksPill}>
            {isApp ? (
              <>
                <Link to="/dashboard" className={`${styles.link} ${currentPath === '/dashboard' || currentPath === '/' ? styles.active : ''}`}>News</Link>
                <Link to="/profile" className={`${styles.link} ${currentPath === '/profile' ? styles.active : ''}`}>Profile</Link>
                <Link to="/settings" className={`${styles.link} ${currentPath === '/settings' ? styles.active : ''}`}>Settings</Link>
              </>
            ) : (
              <>
                <Link to="/#features" className={styles.link}>Features</Link>
                <Link to="/#how-it-works" className={styles.link}>How it works</Link>
                <Link to="/login" className={styles.link}>Login</Link>
              </>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className={styles.actions}>
          {isApp ? (
            <>
              <div className={styles.searchBar}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <input
                  type="text"
                  placeholder="Search articles... (Enter)"
                  value={searchValue}
                  onChange={(e) => setSearchValue(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  aria-label="Search articles"
                />
                {searchValue && (
                  <button
                    className={styles.searchClearBtn}
                    onClick={handleSearchClear}
                    aria-label="Clear search"
                    title="Clear search"
                  >
                    ✕
                  </button>
                )}
              </div>
              <button className={styles.iconBtn}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                  <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                </svg>
                <span className={styles.notificationDot}></span>
              </button>
              <div className={styles.avatar}>A</div>
            </>
          ) : (
            <Link to="/signup" className={styles.ctaBtn}>Join Us</Link>
          )}
        </div>
      </div>
    </nav>
  );
}
