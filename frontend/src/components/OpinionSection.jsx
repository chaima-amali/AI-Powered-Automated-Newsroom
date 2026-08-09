import styles from './OpinionSection.module.css';

export default function OpinionSection({ opinions }) {
  const data = opinions || [
    {
      id: 1,
      author: 'Amara Osei',
      role: 'Science Correspondent',
      quote: '“The AI governance summit is a good start — and a dangerously comfortable one. We are celebrating a framework while the actual systems accelerate.”',
      time: '3 hrs ago',
      readTime: '5 min read',
      avatarColor: '#8B5CF6',
      avatarChar: 'A'
    },
    {
      id: 2,
      author: 'Reza Tehrani',
      role: 'Energy Editor',
      quote: '“We are pretending oil is over while quietly signing ten-year extraction contracts. The green transition is happening — just not where the cameras are.”',
      time: '5 hrs ago',
      readTime: '4 min read',
      avatarColor: '#F59E0B',
      avatarChar: 'R'
    },
    {
      id: 3,
      author: 'Claire Beaumont',
      role: 'Political Analyst',
      quote: '“Stop calling it polarization. What we are witnessing is something older, slower, and far more difficult to reverse than a news cycle suggests.”',
      time: 'Yesterday',
      readTime: '7 min read',
      avatarColor: '#3B82F6',
      avatarChar: 'C'
    }
  ];

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>Opinion</h2>
        <a href="#" className={styles.seeAll}>See all &rarr;</a>
      </div>

      <div className={styles.grid}>
        {data.map(opinion => (
          <div key={opinion.id} className={styles.card}>
            <div className={styles.authorHeader}>
              <div className={styles.avatar} style={{ backgroundColor: opinion.avatarColor }}>
                {opinion.avatarChar}
              </div>
              <div className={styles.authorInfo}>
                <h4 className={styles.authorName}>{opinion.author}</h4>
                <div className={styles.authorRole}>{opinion.role}</div>
              </div>
            </div>
            
            <p className={styles.quote}>{opinion.quote}</p>
            
            <div className={styles.footer}>
              {opinion.time} &middot; {opinion.readTime}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
