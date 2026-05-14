import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getToken } from '../services/auth';
import NewsCard from '../components/NewsCard';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './DashboardPage.module.css';

const CATEGORIES = ['All', 'Business', 'Technology', 'Sport', 'Politics'];
const TODAY = new Date().toISOString().split('T')[0];

const INFLUENCING = [
  { tag: 'Business',    title: 'Global Markets Rally Amid Economic Recovery Signs',     time: 'Apr 27 2024', readTime: 5, image: 'https://picsum.photos/seed/inf1/400/240' },
  { tag: 'Technology',  title: 'AI Breakthroughs Reshape the Future of Work and Jobs',  time: 'Apr 27 2024', readTime: 4, image: 'https://picsum.photos/seed/inf2/400/240' },
  { tag: 'Sport',       title: 'Champions League Semi-Finals Deliver Record Viewership', time: 'Apr 27 2024', readTime: 3, image: 'https://picsum.photos/seed/inf3/400/240' },
];

const LATEST = [
  { tag: 'Business',   title: 'Federal Reserve Signals Potential Rate Cuts in Late 2024',      time: 'Apr 27 2024', readTime: 5, image: 'https://picsum.photos/seed/lat1/400/240' },
  { tag: 'Politics',   title: 'Global Leaders Convene for Emergency Climate Summit',           time: 'Apr 26 2024', readTime: 4, image: 'https://picsum.photos/seed/lat2/400/240' },
  { tag: 'Technology', title: 'Apple Unveils New AR Headset Features at Developer Conference', time: 'Apr 26 2024', readTime: 6, image: 'https://picsum.photos/seed/lat3/400/240' },
  { tag: 'Sport',      title: 'Algerian Athletes Break Three World Records at European Cup',   time: 'Apr 25 2024', readTime: 3, image: 'https://picsum.photos/seed/lat4/400/240' },
  { tag: 'Business',   title: 'Oil Prices Surge as OPEC+ Announces Production Cuts',          time: 'Apr 25 2024', readTime: 5, image: 'https://picsum.photos/seed/lat5/400/240' },
  { tag: 'Politics',   title: 'Senate Passes Landmark Infrastructure Bill with Bipartisan Support', time: 'Apr 24 2024', readTime: 4, image: 'https://picsum.photos/seed/lat6/400/240' },
];

export default function DashboardPage() {
  const [activeCategory, setActiveCategory] = useState('All');
  const [search, setSearch] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDate, setSelectedDate] = useState(TODAY);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const fetchArticles = async () => {
    setLoading(true);
    setError('');

    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }

    try {
      const url = new URL('http://localhost:8000/api/v1/articles');
      url.searchParams.set('page', '1');
      url.searchParams.set('limit', '100');
      if (activeCategory !== 'All') {
        url.searchParams.set('category', activeCategory);
      }
      if (search.trim()) {
        url.searchParams.set('q', search.trim());
      }
      if (selectedDate) {
        url.searchParams.set('date', selectedDate);
      }

      const res = await fetch(url.toString(), {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.status === 401) {
        logout();
        navigate('/login');
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch articles');
      const data = await res.json();
      setArticles(data.data.filter(a => a && a.title));
    } catch (err) {
      setError('Failed to load articles');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArticles();
  }, [navigate, logout, activeCategory, search, selectedDate]);

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  return (
    <div className={styles.page}>

      {/* ── APP NAVBAR ── */}
      <Navbar />

      <main className={styles.main}>
        {/* ── HERO ── */}
        <section className={styles.hero}>
          <div className={styles.heroBg} aria-hidden />
          <div className={styles.heroContent}>
            <p className={styles.heroGreeting}>Good morning, {user?.name?.split(' ')[0]} 👋</p>
            <h1 className={styles.heroTitle}>Today's Top Stories</h1>
            <p className={styles.heroDesc}>Discover the latest news, insights, and stories from around the world, curated for you.</p>
            <button className={styles.discoverBtn}>Let's Discover</button>
          </div>
        </section>

        <div className={styles.content}>
          {/* Search + Date */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div style={{ flex: '1 1 520px', minWidth: '260px' }}>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.9rem', color: '#334155' }}>
                Search
              </label>
              <div className={styles.searchBox}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.searchIcon}>
                  <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                </svg>
                <input
                  type="text"
                  placeholder="Search Articles, Topics or News..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className={styles.searchInput}
                />
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: '220px', alignItems: 'flex-end' }}>
              <label style={{ display: 'block', marginBottom: '0', fontSize: '0.9rem', color: '#334155' }}>
                Date
              </label>
              <input
                type="date"
                value={selectedDate}
                onChange={e => setSelectedDate(e.target.value)}
                className={styles.searchInput}
                style={{ width: '220px' }}
              />
            </div>

            <button type="button" className={styles.filterBtn} onClick={fetchArticles} style={{ minWidth: '100px', height: '42px' }}>
              Apply
            </button>
          </div>

          {/* Categories */}
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Categories</h2>
            <div className={styles.categories}>
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  className={`${styles.catBtn} ${activeCategory === cat ? styles.catActive : ''}`}
                  onClick={() => setActiveCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>{selectedDate === TODAY ? "Today's Articles" : `Articles for ${new Date(selectedDate).toLocaleDateString()}`}</h2>
            {loading && <p>Loading...</p>}
            {error && <p className={styles.error}>{error}</p>}
            <div className={styles.grid3}>
              {articles.map((article) => {
                const category = article.category || 'News';
                const categoryTag = category.charAt(0).toUpperCase() + category.slice(1).toLowerCase();
                const articleLink = article.slug || String(article.id);
                return (
                  <NewsCard
                    key={article.id}
                    tag={categoryTag}
                    title={article.title}
                    time={article.generated_at ? new Date(article.generated_at).toLocaleDateString() : article.published_at ? new Date(article.published_at).toLocaleDateString() : 'Today'}
                    readTime={article.reading_time_min || 5}
                    image={article.cover_image_url || undefined}
                    provider={article.provider_name}
                    onRead={() => navigate(`/article/${articleLink}`)}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
