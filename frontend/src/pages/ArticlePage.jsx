import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { articles as articleApi } from '../services/api';
import styles from './ArticlePage.module.css';

function formatDate(d) {
  if (!d) return '';
  try { return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' }); }
  catch { return ''; }
}

function formatBody(body) {
  if (!body) return [];
  // Split on double newlines into paragraphs; detect markdown headings
  return body.split(/\n\n+/).map(block => {
    if (block.startsWith('## '))  return { type: 'h2',   text: block.slice(3).trim() };
    if (block.startsWith('### ')) return { type: 'h3',   text: block.slice(4).trim() };
    if (block.startsWith('# '))   return { type: 'h1',   text: block.slice(2).trim() };
    return { type: 'p', text: block.trim() };
  }).filter(b => b.text);
}

export default function ArticlePage() {
  const { slug }  = useParams();
  const navigate  = useNavigate();
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');

  useEffect(() => {
    setLoading(true); setError(''); setArticle(null);
    articleApi.bySlug(slug)
      .then(a => { setArticle(a); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [slug]);

  const share = () => {
    if (navigator.share) {
      navigator.share({ title: article?.title, url: window.location.href });
    } else {
      navigator.clipboard?.writeText(window.location.href);
    }
  };

  return (
    <div className={styles.page}>
      <Navbar />
      <main className={styles.main}>
        <div className={styles.container}>
          <button className={styles.backBtn} onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>

          {loading && <ArticleSkeleton />}

          {error && (
            <div className={styles.errorState}>
              <span className={styles.errorIcon}>⚠️</span>
              <h2>Article not found</h2>
              <p>{error}</p>
              <button className={styles.backAction} onClick={() => navigate('/dashboard')}>
                Return to Dashboard
              </button>
            </div>
          )}

          {article && !loading && (
            <div className={styles.article}>
              {/* Meta header */}
              <div className={styles.metaHeader}>
                <span className={styles.categoryTag}>{article.category || 'News'}</span>
                <div className={styles.actions}>
                  <button className={styles.actionBtn} title="Share article" onClick={share}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                    </svg>
                  </button>
                </div>
              </div>

              {/* Title */}
              <h1 className={styles.title}>{article.title}</h1>

              {/* Article meta */}
              <div className={styles.meta}>
                {article.published_at && <span>📅 {formatDate(article.published_at)}</span>}
                {article.reading_time_min && <span>⏱ {article.reading_time_min} min read</span>}
                {article.language && <span>🌐 {article.language.toUpperCase()}</span>}
                {article.view_count > 0 && <span>👁 {article.view_count.toLocaleString()} views</span>}
              </div>

              {/* Cover image */}
              {article.cover_image_url && (
                <div className={styles.coverWrap}>
                  <img
                    src={article.cover_image_url}
                    alt={article.title}
                    className={styles.coverImg}
                    onError={e => { e.target.parentElement.style.display = 'none'; }}
                  />
                </div>
              )}

              {/* Excerpt / pull-quote */}
              {article.excerpt && (
                <blockquote className={styles.pullQuote}>{article.excerpt}</blockquote>
              )}

              {/* Body */}
              <div className={styles.body}>
                {formatBody(article.body).map((block, i) => {
                  if (block.type === 'h1') return <h1 key={i} className={styles.bodyH1}>{block.text}</h1>;
                  if (block.type === 'h2') return <h2 key={i} className={styles.bodyH2}>{block.text}</h2>;
                  if (block.type === 'h3') return <h3 key={i} className={styles.bodyH3}>{block.text}</h3>;
                  return <p key={i}>{block.text}</p>;
                })}
              </div>

              {/* Tags */}
              {article.tags?.length > 0 && (
                <div className={styles.tagsSection}>
                  <span className={styles.tagsLabel}>Tags</span>
                  <div className={styles.tagsList}>
                    {article.tags.map(tag => (
                      <span key={tag} className={styles.tagPill}>{tag}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* SEO description as "About this story" */}
              {article.seo_description && (
                <div className={styles.aboutBox}>
                  <h4>About this story</h4>
                  <p>{article.seo_description}</p>
                </div>
              )}

              {/* Navigation */}
              <div className={styles.navLinks}>
                <button className={styles.navBack} onClick={() => navigate('/dashboard')}>
                  ← Back to all stories
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
      <footer className={styles.footer}>© 2025 NewsDispatch</footer>
    </div>
  );
}

function ArticleSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="skeleton" style={{ height: 32, width: '40%' }} />
      <div className="skeleton" style={{ height: 56, width: '90%' }} />
      <div className="skeleton" style={{ height: 20, width: '60%' }} />
      <div className="skeleton" style={{ height: 360, borderRadius: 12 }} />
      <div className="skeleton" style={{ height: 20, width: '100%' }} />
      <div className="skeleton" style={{ height: 20, width: '95%' }} />
      <div className="skeleton" style={{ height: 20, width: '88%' }} />
      <div className="skeleton" style={{ height: 20, width: '92%' }} />
    </div>
  );
}
