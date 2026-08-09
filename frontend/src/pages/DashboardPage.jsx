import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useArticles } from '../hooks/useData';
import Navbar from '../components/Navbar';
import ArticleCard from '../components/ArticleCard';
import TopStorySection from '../components/TopStorySection';
import MostInfluencingSection from '../components/MostInfluencingSection';
import LatestNewsSection from '../components/LatestNewsSection';
import OpinionSection from '../components/OpinionSection';
import Footer from '../components/Footer';
import styles from './DashboardPage.module.css';
import { cleanText } from '../utils/cleanText';


// Helper to format timestamps to relative time strings
function getRelativeTime(dateString) {
  if (!dateString) return 'Just now';
  const diff = Date.now() - new Date(dateString).getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// Helper to map DB ArticleSummary to the expected visual card format
function formatArticle(article) {
  return {
    id: article.id,
    tag: (article.category || 'News').toUpperCase(),
    title: article.title,
    desc: cleanText(article.excerpt) || '',
    author: 'Editorial',
    time: getRelativeTime(article.published_at || article.generated_at),
    readTime: article.reading_time_min || 5,
    slug: article.slug,
    image: article.cover_image_url || article.image_url || null,
    color: '#1E293B',
    catColor: '#8B5CF6',
    // Pass raw fields through so ArticleCard can use them directly
    published_at: article.published_at,
    reading_time_min: article.reading_time_min,
    cover_image_url: article.cover_image_url || article.image_url || null,
    category: article.category,
  };
}

// Helper to get today's date in YYYY-MM-DD format in local timezone
const getTodayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export default function DashboardPage() {
  // ── All filter state lives in the URL so it survives "Read More" navigation ──
  const [searchParams, setSearchParams] = useSearchParams();

  // activeCategory holds the French DB value (or 'All')
  const activeCategory = searchParams.get('category') || 'All';
  const selectedDate   = searchParams.get('date')     || '';   // empty = no date filter
  const searchQuery    = searchParams.get('q')         || '';

  // Fallback toggle stays local — it's a display preference, not a filter
  const [useFallback, setUseFallback] = useState(true);

  // ── Dynamic categories from backend ──────────────────────────────────────
  const [categories, setCategories] = useState(['All']);
  useEffect(() => {
    fetch('/api/v1/categories')
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        // data = [{ category: 'Actualité', article_count: 5 }, ...]
        const cats = ['All', ...data.map(c => c.category).filter(Boolean)];
        setCategories(cats);
      })
      .catch(() => {}); // keep default 'All' on error
  }, []);

  // ── URL param setters (preserves existing params) ─────────────────────────
  const setParam = (key, value, defaultValue) => {
    const next = new URLSearchParams(searchParams);
    if (value === defaultValue || value == null) next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  // cat is the French DB value from CATEGORIES[].value
  const handleCategoryChange = (cat) => setParam('category', cat, 'All');
  const handleDateChange     = (val) => setParam('date', val, '');  // clear when reset

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: articles, loading, error } = useArticles({
    category: activeCategory,
    date:     selectedDate  || undefined,  // only sent when user picks a date
    search:   searchQuery   || undefined,
    limit:    20,
  });

  const formattedArticles = articles ? articles.map(formatArticle) : [];

  // Switch to grid view when any filter is active
  const isFilterActive = !!searchQuery || activeCategory !== 'All';

  // Fallback mock data only in the normal home view
  const shouldFallback   = !isFilterActive && useFallback && formattedArticles.length === 0;
  const mainStory        = shouldFallback ? undefined : (formattedArticles[0] || null);
  const sideStories      = shouldFallback ? undefined : formattedArticles.slice(1, 4);

  // MostInfluencing: use articles 4-8, but if there aren't enough, wrap around from the beginning
  const influencingStories = shouldFallback ? undefined : (() => {
    if (formattedArticles.length === 0) return [];
    const raw = formattedArticles.slice(4, 9);
    if (raw.length >= 5 || formattedArticles.length < 5) return raw;
    // pad by cycling through all articles
    const padded = [...raw];
    let i = 0;
    while (padded.length < 5) {
      padded.push(formattedArticles[i % formattedArticles.length]);
      i++;
    }
    return padded;
  })();

  // Latest News: use articles from index 9+, but if empty/few, recycle all articles
  const latestStories = shouldFallback ? undefined : (() => {
    if (formattedArticles.length === 0) return [];
    const raw = formattedArticles.slice(9);
    if (raw.length > 0) return raw;
    // Not enough articles — reuse all articles so the section is never empty
    return formattedArticles;
  })();

  return (
    <div className={styles.page}>
      <Navbar />

      <main className={styles.main}>
        {/* ── HERO SECTION ── */}
        <section className={styles.heroSection}>
          <div className={styles.heroContent}>
            <div className={styles.heroGreeting}>FRIDAY, MAY 15 &middot; GOOD MORNING</div>
            <h1 className={styles.heroTitle}>Today's Top Stories</h1>
            <p className={styles.heroDesc}>
              Discover the latest news, insights and stories from across the world,
              curated just for you.
            </p>
            <div className={styles.heroButtons}>
              <button className={styles.btnPrimary}>Let's Discover</button>
              <button className={styles.btnSecondary}>My Bookmarks</button>
            </div>
          </div>
        </section>

        {/* ── CATEGORIES & DATE PICKER ── */}
        <div className={styles.categoriesSection}>
          <div className={styles.categoriesList}>
            {categories.map(cat => (
              <button
                key={cat}
                className={`${styles.catBtn} ${activeCategory === cat ? styles.catActive : ''}`}
                onClick={() => handleCategoryChange(cat)}
              >
                {cat}
              </button>
            ))}
          </div>
          <div className={styles.filtersWrapper}>

            <input
              type="date"
              className={styles.datePicker}
              value={selectedDate}
              onChange={(e) => handleDateChange(e.target.value)}
              title="Pick a date to filter by date (leave blank for all dates)"
            />
            {selectedDate && (
              <button
                onClick={() => handleDateChange('')}
                title="Clear date filter"
                style={{ marginLeft: '4px', cursor: 'pointer', background: 'none', border: 'none', color: '#94a3b8', fontSize: '14px' }}
              >
                ✕
              </button>
            )}
            <button className={styles.filterBtn}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="4" y1="21" x2="4" y2="14"></line>
                <line x1="4" y1="10" x2="4" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12" y2="3"></line>
                <line x1="20" y1="21" x2="20" y2="16"></line>
                <line x1="20" y1="12" x2="20" y2="3"></line>
                <line x1="1" y1="14" x2="7" y2="14"></line>
                <line x1="9" y1="8" x2="15" y2="8"></line>
                <line x1="17" y1="16" x2="23" y2="16"></line>
              </svg>
              Filters
            </button>
          </div>
        </div>

        {/* ── CONTENT SECTIONS ── */}
        <div className={styles.contentSections}>
          {error && (
            <div style={{ color: '#EF4444', backgroundColor: '#FEE2E2', padding: '16px', borderRadius: '8px', marginBottom: '16px', fontWeight: 'bold' }}>
              Error fetching data: {error}
            </div>
          )}
          {loading && <div className={styles.loadingState}>Loading articles...</div>}

          {/* ── FILTER / SEARCH RESULTS GRID ── */}
          {isFilterActive && !loading && (
            <>
              <div className={styles.resultsHeader}>
                <span className={styles.resultsCount}>
                  {searchQuery
                    ? (formattedArticles.length > 0
                        ? `${formattedArticles.length} result${formattedArticles.length !== 1 ? 's' : ''} for`
                        : 'No results for')
                    : `${formattedArticles.length} article${formattedArticles.length !== 1 ? 's' : ''} in`
                  }
                </span>
                <span className={styles.resultsLabel}>
                  {searchQuery ? `"${searchQuery}"` : activeCategory}
                </span>
                {selectedDate && (
                  <span className={styles.resultsBadge}>📅 {selectedDate}</span>
                )}
              </div>

              {formattedArticles.length > 0 ? (
                <div className={styles.resultsGrid}>
                  {formattedArticles.map(a => (
                    <ArticleCard
                      key={a.id}
                      article={{
                        id:               a.id,
                        title:            a.title,
                        slug:             a.slug,
                        excerpt:          a.desc,
                        cover_image_url:  a.cover_image_url,
                        category:         a.category,
                        reading_time_min: a.reading_time_min,
                        published_at:     a.published_at,
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div className={styles.emptyState}>
                  <span>🔍</span>
                  <p>Try a different search term or category.</p>
                </div>
              )}
            </>
          )}

          {/* ── NORMAL HOME VIEW ── */}
          {!isFilterActive && !loading && (
            <>

              <TopStorySection mainStory={mainStory} sideStories={sideStories} />
              <MostInfluencingSection articles={influencingStories} />
              <LatestNewsSection articles={latestStories} />
              <OpinionSection />
            </>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}
