import styles from './MostInfluencingSection.module.css';
import { Link } from 'react-router-dom';

export default function MostInfluencingSection({ articles }) {
  // Mock data if no articles passed, mapping to the 5 cards in the screenshot
  const data = articles !== undefined ? articles : [
    { id: 1, tag: 'WORLD', title: 'Global Markets Rally Amid Economic Recovery Signs', time: '2h', readTime: 5, color: '#3B2A82', isLive: true, catColor: '#3B82F6' },
    { id: 2, tag: 'SPORT', title: 'Champions League Final: Two Cities, One Trophy and...', time: '1h', readTime: 4, color: '#C2410C', isLive: false, catColor: '#EA580C' },
    { id: 3, tag: 'CLIMATE', title: 'Arctic Ice Sheet Collapses at Unprecedented Speed This...', time: '3h', readTime: 6, color: '#047857', isLive: false, catColor: '#10B981' },
    { id: 4, tag: 'TECHNOLOGY', title: 'AI Code Agent Can Debug and Deploy Without Human...', time: '2h', readTime: 5, color: '#6D28D9', isLive: false, catColor: '#8B5CF6' },
    { id: 5, tag: 'BUSINESS', title: 'Apple Posts Record Quarter Beating All...', time: '4h', readTime: 3, color: '#1E293B', isLive: false, catColor: '#EAB308' },
  ];

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>Most Influencing</h2>
        <a href="#" className={styles.seeAll}>See all &rarr;</a>
      </div>

      <div className={styles.scrollContainer}>
        <div className={styles.carousel}>
          {data.map((article, index) => (
            <Link to={`/article/${article.slug}`} key={article.id} className={styles.card} style={{ textDecoration: 'none' }}>
              <div 
                className={styles.imageArea} 
                style={{ 
                  backgroundColor: article.color,
                  backgroundImage: article.image ? `url("${article.image}")` : 'none',
                  backgroundSize: 'cover',
                  backgroundPosition: 'center'
                }}
              >
                {article.isLive && (
                  <div className={styles.liveTag}>
                    <span className={styles.liveDot}></span> LIVE
                  </div>
                )}
                <div className={styles.largeNumber}>{index + 1}</div>
                {!article.image && (
                  <div className={styles.imageIcon}>
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                      <circle cx="8.5" cy="8.5" r="1.5"></circle>
                      <polyline points="21 15 16 10 5 21"></polyline>
                    </svg>
                  </div>
                )}
              </div>
              <div className={styles.contentArea}>
                <div className={styles.tag} style={{ color: article.catColor }}>
                   {article.tag === 'WORLD' ? '🌍' : 
                    article.tag === 'SPORT' ? '⚽' : 
                    article.tag === 'CLIMATE' ? '🍃' : 
                    article.tag === 'TECHNOLOGY' ? '💡' : '💼'} {article.tag}
                </div>
                <h3 className={styles.cardTitle}>{article.title}</h3>
                <div className={styles.footer}>
                  <div className={styles.authorAvatars}>
                    {/* Just simple circles for authors like in the screenshot */}
                    <div className={styles.avatar} style={{ backgroundColor: '#8B5CF6', zIndex: 2 }}>S</div>
                    <div className={styles.avatar} style={{ backgroundColor: '#3B82F6', zIndex: 1, marginLeft: '-8px' }}>J</div>
                  </div>
                  <div className={styles.meta}>
                    {article.time} &middot; {article.readTime} min
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
