import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import NewsCard from '../components/NewsCard';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './DashboardPage.module.css';

const CATEGORIES = ['All', 'Business', 'Technology', 'Sport', 'Politics'];

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
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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
          {/* Search */}
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
            <button className={styles.filterBtn} title="Filter">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="11" y1="18" x2="13" y2="18"/>
              </svg>
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

          {/* Most Influencing */}
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Most Influencing</h2>
              <div className={styles.arrows}>
                <button className={styles.arrowBtn}>‹</button>
                <button className={styles.arrowBtn}>›</button>
              </div>
            </div>
            <div className={styles.grid3}>
              {INFLUENCING.map((item, i) => (
                <NewsCard key={i} {...item} size="large" onRead={() => navigate('/article')} />
              ))}
            </div>
          </div>

          {/* Latest News */}
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Latest News</h2>
            <div className={styles.grid3}>
              {LATEST.map((item, i) => (
                <NewsCard key={i} {...item} onRead={() => navigate('/article')} />
              ))}
            </div>
            <div className={styles.loadMoreWrap}>
              <button className={styles.loadMore}>Load More</button>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
