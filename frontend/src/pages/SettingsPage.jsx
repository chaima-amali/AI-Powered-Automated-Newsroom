import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './DashboardPage.module.css'; // Reuse styles

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
        <div className={styles.content}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Settings</h2>
            <div style={{ padding: '20px', background: '#f9f9f9', borderRadius: '8px' }}>
              <h3>Preferences</h3>
              {['Technology', 'Business', 'Politics', 'Sport'].map(pref => (
                <label key={pref} style={{ display: 'block', margin: '10px 0' }}>
                  <input
                    type="checkbox"
                    checked={preferences.includes(pref)}
                    onChange={() => handlePreferenceChange(pref)}
                  />
                  {pref}
                </label>
              ))}
              <button onClick={saveSettings} style={{ marginTop: '20px', padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}>
                Save Settings
              </button>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}