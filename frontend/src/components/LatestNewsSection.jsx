import styles from './LatestNewsSection.module.css';
import NewsCard from './NewsCard';

export default function LatestNewsSection({ articles }) {
  // Mock trending data
  const trending = [
    { num: 1, tag: 'BUSINESS', title: 'The Quiet Collapse of the Middle Class in Southern Europe', reads: '94K reading', colorClass: styles.catBusiness },
    { num: 2, tag: 'TECHNOLOGY', title: 'Why Your Next Prescription Might Be Written by an AI', reads: '71K reading', colorClass: styles.catTech },
    { num: 3, tag: 'POLITICS', title: 'The Country That Made Citizens Work Four Days a Week', reads: '58K reading', colorClass: styles.catPolitics },
    { num: 4, tag: 'SPORT', title: 'Champions League Final: Full Preview and Tactical Analysis', reads: '52K reading', colorClass: styles.catSport },
    { num: 5, tag: 'SCIENCE', title: 'Sleep Before Midnight Has Distinct Brain Benefits, Study Shows', reads: '39K reading', colorClass: styles.catScience },
    { num: 6, tag: 'CLIMATE', title: 'New Carbon Capture Plant in Iceland Exceeds All Expectations', reads: '31K reading', colorClass: styles.catClimate },
  ];

  // Placeholder for latest articles if none provided
  const latestArticles = articles !== undefined ? articles : [
    { id: 1, tag: 'WORLD', title: 'UN Security Council Calls Emergency Session Over Disputed Maritime Borders in South China Sea', desc: 'Diplomatic tensions surged overnight as three naval vessels exchanged warning shots in...', author: 'Kenji Watanabe', time: '45 min ago', readTime: 4, color: '#0369A1' },
    { id: 2, tag: 'SCIENCE', title: 'CERN Detects New Particle That Challenges the Standard Model of Matter', desc: 'Initial LHC readings show properties inconsistent with existing theory...', author: 'Dr. Osei', time: '2 hrs ago', readTime: 6, color: '#047857' },
    { id: 3, tag: 'SPORT', title: 'Champions League Final: Complete Tactical Preview and Predictions', desc: 'Saturday\'s showdown in Madrid pits a resurgent English side against...', author: 'Di Luca', time: '1 hr ago', readTime: 5, color: '#C2410C' },
    { id: 4, tag: 'CULTURE', title: 'Cannes Palme d\'Or Goes to an Unexpected First-Time Director From Algeria', desc: 'Yasmina Boudacud\'s debut feature left the audience silent for a full minute...', author: 'Chandrasekar', time: '5 hrs ago', readTime: 7, color: '#6D28D9' },
    { id: 5, tag: 'POLITICS', title: 'G7 Leaders Agree on New Framework for Digital Trade Barriers', desc: 'The summit\'s final communiqué includes binding provisions that would...', author: 'Fischer', time: '3 hrs ago', readTime: 4, color: '#1E293B' },
  ];

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>Latest News</h2>
        <a href="#" className={styles.seeAll}>See all &rarr;</a>
      </div>

      <div className={styles.container}>
        {/* Main Grid Area */}
        <div className={styles.mainGrid}>
          {latestArticles.map(article => (
            <NewsCard key={article.id} article={article} />
          ))}
        </div>

        {/* Trending Now Sidebar */}
        <div className={styles.sidebar}>
          <div className={styles.trendingCard}>
            <h3 className={styles.trendingTitle}>Trending Now</h3>
            <div className={styles.trendingList}>
              {trending.map((item) => (
                <div key={item.num} className={styles.trendingItem}>
                  <div className={styles.trendingNum}>{item.num}</div>
                  <div className={styles.trendingContent}>
                    <div className={`${styles.trendingTag} ${item.colorClass}`}>{item.tag}</div>
                    <h4 className={styles.trendingItemTitle}>{item.title}</h4>
                    <div className={styles.trendingReads}>{item.reads}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
