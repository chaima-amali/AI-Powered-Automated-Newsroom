import styles from './TopStorySection.module.css';
import { Link } from 'react-router-dom';

export default function TopStorySection({ mainStory, sideStories }) {


  // Fallback data for visual completeness matching design
  const _mainStory = mainStory !== undefined ? mainStory : {
    isLive: false,
    tag: 'WORLD AFFAIRS',
    title: 'Global Summit Reaches Landmark Agreement on AI Governance as Tensions Escalate Between Tech Giants and Regulators',
    desc: 'World leaders gathered in Toronto signed a historic framework establishing the first international protocols for AI oversight, binding 47 nations to common standards — what many are calling a defining moment in digital diplomacy.',
    time: '2 hrs ago',
    readTime: 8
  };

  const _sideStories = sideStories !== undefined ? sideStories : [
    { tag: 'BUSINESS', title: 'Fed Holds Rates as Inflation Exceeds Forecasts', time: '4 hrs ago', readTime: 5, colorClass: styles.catBusiness },
    { tag: 'POLITICS', title: 'European Parliament Expands Digital Rights Charter', time: '5 hrs ago', readTime: 4, colorClass: styles.catPolitics },
    { tag: 'SCIENCE', title: 'Microplastics Linked to Cognitive Decline in New Study', time: '6 hrs ago', readTime: 8, colorClass: styles.catScience }
  ];

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>Top Story</h2>
        <a href="#" className={styles.seeAll}>See all &rarr;</a>
      </div>

      <div className={styles.grid}>
        {/* Main Story (Left) */}
        <div 
          className={styles.mainCard}
          style={{
            backgroundImage: _mainStory?.image ? `linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.1) 100%), url("${_mainStory.image}")` : 'none',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            color: _mainStory?.image ? 'white' : 'inherit'
          }}
        >
          {_mainStory && _mainStory.isLive && (
            <div className={styles.liveTag}>
              <span className={styles.liveDot}></span> LIVE
            </div>
          )}
          {_mainStory ? (
            <div className={styles.mainContent}>
              <div className={styles.mainTag} style={_mainStory?.image ? {color: '#A78BFA'} : {}}>
                <span className={styles.tagIcon}>🌍</span> {_mainStory.tag}
              </div>
              <h3 className={styles.mainTitle} style={_mainStory?.image ? {color: 'white'} : {}}>{_mainStory.title}</h3>
              <p className={styles.mainDesc} style={_mainStory?.image ? {color: 'rgba(255,255,255,0.8)'} : {}}>{_mainStory.desc}</p>
              <div className={styles.mainFooter}>
                <div className={styles.mainMeta}>
                   <div className={styles.authorAvatars}>
                      <div className={styles.avatar} style={{ backgroundColor: '#8B5CF6', zIndex: 2 }}>S</div>
                      <div className={styles.avatar} style={{ backgroundColor: '#3B82F6', zIndex: 1, marginLeft: '-8px' }}>J</div>
                    </div>
                  <span className={styles.timeText}>{_mainStory.time} &middot; {_mainStory.readTime} min read</span>
                </div>
                {_mainStory.slug ? (
                  <Link to={`/article/${_mainStory.slug}`} className={styles.readNowBtn} style={{ textDecoration: 'none', display: 'inline-block' }}>Read Now &rarr;</Link>
                ) : (
                  <button className={styles.readNowBtn}>Read Now &rarr;</button>
                )}
              </div>
            </div>
          ) : (
            <div className={styles.mainContent}>
              <p style={{ color: 'var(--text-muted)' }}>No top story available for this date.</p>
            </div>
          )}
        </div>

        {/* Side Stories (Right) */}
        <div className={styles.sideStories}>
          {_sideStories && _sideStories.map((story, i) => (
            <Link to={`/article/${story.slug}`} key={i} className={styles.sideCard} style={{ textDecoration: 'none' }}>
              <div 
                className={styles.sideImagePlaceholder}
                style={{
                  backgroundImage: story.image ? `url("${story.image}")` : 'none',
                  backgroundSize: 'cover',
                  backgroundPosition: 'center'
                }}
              >
                {!story.image && (
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    <circle cx="8.5" cy="8.5" r="1.5"></circle>
                    <polyline points="21 15 16 10 5 21"></polyline>
                  </svg>
                )}
              </div>
              <div className={styles.sideContent}>
                <div className={`${styles.sideTag} ${story.colorClass || ''}`}>
                   {story.tag}
                </div>
                <h3 className={styles.sideTitle}>{story.title}</h3>
                <div className={styles.sideMeta}>
                  {story.time} &middot; {story.readTime} min
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
