import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './SettingsPage.module.css';

export default function SettingsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [preferences, setPreferences] = useState(user?.preferences || []);

  const handlePreferenceChange = (pref) => {
    setPreferences(prev =>
      prev.includes(pref) ? prev.filter(p => p !== pref) : [...prev, pref]
    );
  };

  const saveSettings = () => {
    // In a real app, send to backend
    alert('Settings saved!');
  };

  if (!user) return <div>Loading...</div>;

  return (
    <div className={styles.page}>
      <Navbar />

      <main className={styles.main}>
        <div className={styles.settingsCard}>
          <div className={styles.header}>
            <div>
              <h1>Settings</h1>
              <p className={styles.subtitle}>Customize your preferences and account options.</p>
            </div>
          </div>

          <div className={styles.section}>
            <h2>Preferences</h2>
            <div className={styles.preferencesGrid}>
              {['Technology', 'Business', 'Politics', 'Sport'].map(pref => (
                <label key={pref} className={styles.prefItem}>
                  <input
                    type="checkbox"
                    checked={preferences.includes(pref)}
                    onChange={() => handlePreferenceChange(pref)}
                  />
                  <span>{pref}</span>
                </label>
              ))}
            </div>
          </div>

          <div className={styles.actions}>
            <button className={styles.primaryBtn} onClick={saveSettings}>
              Save Settings
            </button>
            <button className={styles.secondaryBtn} onClick={() => navigate('/profile')}>
              Back to Profile
            </button>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}