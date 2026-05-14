import styles from './NewsCard.module.css';

const TAG_COLORS = {
  Business: '#4F46E5',
  Technology: '#7C3AED',
  Sport: '#EC4899',
  Politics: '#0EA5E9',
  Breaking: '#EF4444',
};

export default function NewsCard({ tag, title, time, readTime, image, provider, providerLogo, size = 'medium', onRead }) {
  const tagColor = TAG_COLORS[tag] || '#4F46E5';
  const providerSrc = providerLogo || (provider ? `/newspapers/${provider.toLowerCase().replace(/\s+/g, '-')}.png` : null);

  return (
    <div className={`${styles.card} ${styles[size]}`}>
      <div className={styles.imageWrap}>
        <img src={image || `https://picsum.photos/seed/${encodeURIComponent(title)}/400/240`} alt={title} />
        <span className={styles.tag} style={{ background: tagColor }}>{tag}</span>
        <button className={styles.bookmark}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        </button>
      </div>
      <div className={styles.body}>
        <h3 className={styles.title}>{title}</h3>
        <div className={styles.meta}>
          <span>{time}</span>
          <span>·</span>
          <span>{readTime} min read</span>
        </div>
        {provider && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px', fontSize: '0.85rem', color: '#64748b' }}>
            {providerSrc ? (
              <img src={providerSrc} alt={provider} style={{ width: 24, height: 24, objectFit: 'contain', borderRadius: 4 }} />
            ) : (
              <span style={{ width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9', borderRadius: 4 }}>
                📰
              </span>
            )}
            <span>{provider}</span>
          </div>
        )}
        <button className={styles.readBtn} onClick={onRead}>Read More</button>
      </div>
    </div>
  );
}
