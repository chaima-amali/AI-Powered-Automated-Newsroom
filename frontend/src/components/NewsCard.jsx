import styles from './NewsCard.module.css';
import { Link } from 'react-router-dom';

export default function NewsCard({ article, tag, title, time, readTime, image, provider, onRead }) {
  // Use passed individual props or the `article` object 
  const data = article || {
    tag: tag || 'News',
    title: title || 'Untitled Article',
    time: time || 'Just now',
    readTime: readTime || 5,
    author: provider || 'Unknown Author',
    color: '#3B82F6',
    desc: 'Description not available for this article...',
    id: 1,
  };

  const catColor = 
    data.tag?.toUpperCase() === 'WORLD' ? 'var(--cat-business)' : 
    data.tag?.toUpperCase() === 'SPORT' ? 'var(--cat-sport)' : 
    data.tag?.toUpperCase() === 'SCIENCE' ? 'var(--cat-science)' : 
    data.tag?.toUpperCase() === 'CULTURE' ? 'var(--cat-culture)' : 
    data.tag?.toUpperCase() === 'POLITICS' ? 'var(--cat-politics)' : 'var(--primary)';

  const catIcon = 
    data.tag?.toUpperCase() === 'WORLD' ? '🌍' : 
    data.tag?.toUpperCase() === 'SPORT' ? '⚽' : 
    data.tag?.toUpperCase() === 'SCIENCE' ? '🔬' : 
    data.tag?.toUpperCase() === 'CULTURE' ? '🎭' : 
    data.tag?.toUpperCase() === 'POLITICS' ? '🏛️' : '📰';

  return (
    <Link to={`/article/${data.slug}`} className={styles.card} onClick={onRead} style={{ textDecoration: 'none' }}>
      <div 
        className={styles.imageArea} 
        style={{ 
          backgroundColor: data.color || '#1E293B',
          backgroundImage: data.image ? `url("${data.image}")` : 'none',
          backgroundSize: 'cover',
          backgroundPosition: 'center'
        }}
      >
        {!data.image && (
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
        )}
      </div>
      
      <div className={styles.content}>
        <div className={styles.tag} style={{ color: catColor }}>
          <span className={styles.tagIcon}>{catIcon}</span> {data.tag}
        </div>
        
        <h3 className={styles.title}>{data.title}</h3>
        
        {data.desc && (
          <p className={styles.desc}>{data.desc}</p>
        )}
        
        <div className={styles.footer}>
          <div className={styles.meta}>
            {data.author && <span>{data.author} &middot; </span>}
            <span>{data.time} &middot; {data.readTime} min read</span>
          </div>
          <div className={styles.readMore}>
            Read &rarr;
          </div>
        </div>
      </div>
    </Link>
  );
}
