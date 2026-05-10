import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar       from '../components/Navbar';
import ArticleCard  from '../components/ArticleCard';
import { useArticles, useHealth } from '../hooks/useData';
import { useAuth }  from '../context/AuthContext';
import styles from './DashboardPage.module.css';

const CATEGORIES = ['All', 'Politique', 'Économie', 'Sport', 'Société', 'International', 'Culture', 'Santé'];

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function useDebounce(fn, delay) {
  let timer;
  return useCallback((...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  }, [fn, delay]);
}

export default function DashboardPage() {
  const { user }  = useAuth();
  const navigate  = useNavigate();
  const { data: healthData } = useHealth();

  const [category, setCategory] = useState('All');
  const [search,   setSearch]   = useState('');
  const [searchInput, setSearchInput] = useState('');

  const { data, loading, error, hasMore, loadMore, pages, total } = useArticles({
    category: category === 'All' ? '' : category,
    search,
  });

  // Debounce search
  const applySearch = useCallback((q) => setSearch(q), []);
  const debouncedSearch = useCallback((val) => {
    setSearchInput(val);
    clearTimeout(window._searchTimer);
    window._searchTimer = setTimeout(() => applySearch(val), 400);
  }, [applySearch]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const firstName = user?.name?.split(' ')[0] || 'there';

  return (
    <div className={styles.page}>
      <Navbar />
      <main className={styles.main}>
        <div className="container">

          {/* ── Hero strip ──────────────────────────────── */}
          <div className={styles.heroStrip}>
            <div>
              <p className={styles.greeting}>{greeting}, {firstName} 👋</p>
              <h1 className={styles.pageTitle}>Today's Top Stories</h1>
              <p className={styles.pageSub}>Curated from 16+ Algerian sources, rewritten by AI.</p>
            </div>
            <button className={styles.pipelineBtn} onClick={() => navigate('/pipeline')}>
              🔧 Pipeline Monitor
            </button>
          </div>

          {/* ── Stats row ────────────────────────────────── */}
          <div className={styles.statsRow}>
            <StatCard val={fmt(healthData?.total_articles)}    label="Articles" icon="📄" />
            <StatCard val={fmt(healthData?.total_clusters)}     label="Clusters"  icon="🧩" />
            <StatCard val={fmt(healthData?.published_count)}    label="Published" icon="📰" />
            <StatCard val={fmt(healthData?.pending_embedding)}  label="Pending"   icon="⏳" />
          </div>

          {/* ── Search ───────────────────────────────────── */}
          <div className={styles.searchRow}>
            <div className={styles.searchWrap}>
              <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              </svg>
              <input
                type="text"
                className={styles.searchInput}
                placeholder="Search articles, topics…"
                value={searchInput}
                onChange={e => debouncedSearch(e.target.value)}
              />
              {searchInput && (
                <button className={styles.clearBtn} onClick={() => { setSearchInput(''); applySearch(''); }}>
                  ✕
                </button>
              )}
            </div>
          </div>

          {/* ── Category filters ─────────────────────────── */}
          <div className={styles.catRow}>
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                className={`${styles.catBtn} ${category === cat ? styles.catActive : ''}`}
                onClick={() => setCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* ── Results header ───────────────────────────── */}
          <div className={styles.resultsHeader}>
            <h2 className={styles.sectionTitle}>
              {search ? `Results for "${search}"` : category === 'All' ? 'Latest Stories' : category}
            </h2>
            {total > 0 && <span className={styles.totalBadge}>{total} articles</span>}
          </div>

          {/* ── Grid ─────────────────────────────────────── */}
          {error ? (
            <EmptyState
              icon="⚠️"
              title="Could not load articles"
              desc={error}
              action="Open Pipeline Monitor"
              onAction={() => navigate('/pipeline')}
            />
          ) : loading && data.length === 0 ? (
            <SkeletonGrid />
          ) : data.length === 0 ? (
            <EmptyState
              icon="📰"
              title="No articles yet"
              desc="Run the pipeline to generate articles, or try a different search."
              action="Open Pipeline Monitor"
              onAction={() => navigate('/pipeline')}
            />
          ) : (
            <div className={styles.grid}>
              {data.map((article, i) => (
                <ArticleCard key={article.id} article={article} featured={i === 0} />
              ))}
            </div>
          )}

          {/* ── Load more ─────────────────────────────────── */}
          {hasMore && !loading && (
            <div className={styles.loadMoreWrap}>
              <button className={styles.loadMoreBtn} onClick={loadMore}>
                Load more articles
              </button>
            </div>
          )}
          {loading && data.length > 0 && (
            <div className={styles.loadMoreWrap}>
              <div className={styles.spinner} />
            </div>
          )}
        </div>
      </main>
      <footer className={styles.footer}>© 2025 NewsDispatch</footer>
    </div>
  );
}

function StatCard({ val, label, icon }) {
  return (
    <div className={styles.statCard}>
      <span className={styles.statIcon}>{icon}</span>
      <span className={styles.statVal}>{val ?? '—'}</span>
      <span className={styles.statLbl}>{label}</span>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className={styles.grid}>
      {Array(6).fill(0).map((_, i) => (
        <div key={i} className={`${styles.skeletonCard} skeleton`} />
      ))}
    </div>
  );
}

function EmptyState({ icon, title, desc, action, onAction }) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>{icon}</div>
      <h3 className={styles.emptyTitle}>{title}</h3>
      <p className={styles.emptyDesc}>{desc}</p>
      {action && (
        <button className={styles.emptyAction} onClick={onAction}>{action}</button>
      )}
    </div>
  );
}
