import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getToken } from '../services/auth';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './ArticlePage.module.css';
import { cleanText } from '../utils/cleanText';

export default function ArticlePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { slug } = useParams();
  const { logout } = useAuth();
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchArticle = async () => {
      const token = getToken();
      if (!token) {
        navigate('/login');
        return;
      }
      try {
        const res = await fetch(`http://localhost:8000/api/v1/articles/${slug}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.status === 401) {
          logout();
          navigate('/login');
          return;
        }
        if (res.status === 404) {
          setError('Article not found');
          return;
        }
        if (!res.ok) throw new Error('Failed to fetch');
        const data = await res.json();
        setArticle(data);
      } catch (err) {
        setError('Failed to load article');
      } finally {
        setLoading(false);
      }
    };
    if (slug) fetchArticle();
  }, [slug, navigate, logout]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div className={styles.error}>{error}</div>;
  if (!article) return <div>Article not found</div>;

  return (
    <div className={styles.page}>
      <Navbar />

      <main className={styles.main}>
        <div className={styles.container}>
          <button className={styles.backBtn} onClick={() => navigate(location.search ? `/dashboard${location.search}` : '/dashboard')}>
            ← Back to News
          </button>

          <article className={styles.article}>
            {/* Tag + Actions */}
            <div className={styles.articleTop}>
              <span className={styles.tag}>News</span>
              <div className={styles.actions}>
                <button className={styles.actionBtn} title="Share">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                  </svg>
                </button>
                <button className={styles.actionBtn} title="Save">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
                  </svg>
                </button>
                <button className={styles.actionBtn} title="More">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
                  </svg>
                </button>
              </div>
            </div>

            {/* Title */}
            <h1 className={styles.title}>
              {article.title}
            </h1>

            {/* Meta */}
            <div className={styles.meta}>
              <span>📅 {article.published_at ? new Date(article.published_at).toLocaleDateString() : 'Today'}</span>
              <span>·</span>
              <span>⏱ {article.reading_time_min || 5} min Read</span>
            </div>

            {/* Hero Image */}
            { (article.cover_image_url || article.image_url) && (
              <div className={styles.heroImage}>
                <img
                  src={article.cover_image_url || article.image_url}
                  alt={article.title}
                />
              </div>
            ) }

            {/* Highlighted Quote */}
            {article.excerpt && (
              <blockquote className={styles.quote}>
                {cleanText(article.excerpt)}
              </blockquote>
            )}

            {/* Body */}
            <div className={styles.body}>
              <p>{cleanText(article.body || article.raw_summary)}</p>
            </div>
          </article>
        </div>
      </main>

      <Footer />
    </div>
  );
}
