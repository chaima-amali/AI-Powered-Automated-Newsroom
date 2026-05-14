import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './DashboardPage.module.css'; // Reuse styles

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
        <div className={styles.content}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Profile</h2>
            <div style={{ padding: '20px', background: '#f9f9f9', borderRadius: '8px' }}>
              <p><strong>Name:</strong> {user.name}</p>
              <p><strong>Email:</strong> {user.email}</p>
              <p><strong>Joined:</strong> {user.joined_date}</p>
              <p><strong>Preferences:</strong> {user.preferences?.join(', ')}</p>
              <button onClick={handleLogout} style={{ marginTop: '20px', padding: '10px 20px', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px' }}>
                Logout
              </button>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}