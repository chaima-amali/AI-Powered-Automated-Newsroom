import { useNavigate } from 'react-router-dom';
import styles from './ArticleCard.module.css';

const CATEGORY_COLORS = {
  politique:     'red',
  politics:      'red',
  économie:      'gold',
  economie:      'gold',
  economy:       'gold',
  sport:         'blue',
  sports:        'blue',
  société:       'green',
  societe:       'green',
  society:       'green',
  international: 'purple',
  technologie:   'teal',
  technology:    'teal',
  santé:         'pink',
  health:        'pink',
  culture:       'orange',
};

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch { return ''; }
}

export default function ArticleCard({ article, featured = false }) {
  const navigate = useNavigate();
  const { title, slug, excerpt, cover_image_url, category, reading_time_min, published_at } = article;
  const colorKey = (category || '').toLowerCase().replace(/[éè]/g, 'e').replace(/[ô]/g, 'o');
  const color    = CATEGORY_COLORS[colorKey] || '';

  return (
    <article
      className={`${styles.card} ${featured ? styles.featured : ''}`}
      onClick={() => navigate(`/article/${slug}`)}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && navigate(`/article/${slug}`)}
    >
      <div className={styles.imageWrap}>
        {cover_image_url ? (
          <img
            src={cover_image_url}
            alt={title}
            className={styles.image}
            loading="lazy"
            onError={e => { e.target.style.display = 'none'; }}
          />
        ) : (
          <div className={styles.imagePlaceholder}>📰</div>
        )}
      </div>
      <div className={styles.body}>
        <span className={`${styles.tag} ${styles[color] || ''}`}>
          {category || 'News'}
        </span>
        <h3 className={styles.title}>{title}</h3>
        <div className={styles.meta}>
          {published_at && <span>📅 {formatDate(published_at)}</span>}
          {reading_time_min && <span>⏱ {reading_time_min} min</span>}
        </div>
        {excerpt && <p className={styles.excerpt}>{excerpt}</p>}
        <button
          className={styles.readBtn}
          onClick={e => { e.stopPropagation(); navigate(`/article/${slug}`); }}
        >
          Read article →
        </button>
      </div>
    </article>
  );
}
