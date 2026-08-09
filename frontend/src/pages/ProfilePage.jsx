import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './ProfilePage.module.css';

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  if (!user) return <div>Loading...</div>;

  return (
    <div className={styles.page}>
      <Navbar />

      <main className={styles.main}>
        <div className={styles.profileCard}>
          <div className={styles.header}>
            <div className={styles.avatar}>{user.name?.charAt(0)?.toUpperCase() || 'U'}</div>
            <div>
              <h1>{user.name}</h1>
              <p className={styles.email}>{user.email}</p>
              <p className={styles.subtitle}>Member since {user.joined_date || 'N/A'}</p>
            </div>
          </div>

          <div className={styles.detailsGrid}>
            <div className={styles.detailItem}>
              <span>Full Name</span>
              <strong>{user.name}</strong>
            </div>
            <div className={styles.detailItem}>
              <span>Email Address</span>
              <strong>{user.email}</strong>
            </div>
            <div className={styles.detailItem}>
              <span>Preferences</span>
              <strong>{user.preferences?.join(', ') || 'None selected'}</strong>
            </div>
            <div className={styles.detailItem}>
              <span>Role</span>
              <strong>{user.role || 'Reader'}</strong>
            </div>
          </div>

          <div className={styles.actions}>
            <button className={styles.primaryBtn} onClick={() => navigate('/settings')}>
              Edit Settings
            </button>
            <button className={styles.secondaryBtn} onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}