import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import styles from './ArticlePage.module.css';

export default function ArticlePage() {
  const navigate = useNavigate();

  return (
    <div className={styles.page}>
      <Navbar />

      <main className={styles.main}>
        <div className={styles.container}>
          <button className={styles.backBtn} onClick={() => navigate('/dashboard')}>
            ← Back to News
          </button>

          <article className={styles.article}>
            {/* Tag + Actions */}
            <div className={styles.articleTop}>
              <span className={styles.tag}>Business</span>
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
              Global Markets Rally Amid Economic Recovery Signs
            </h1>

            {/* Meta */}
            <div className={styles.meta}>
              <span>📅 Apr 27 2024</span>
              <span>·</span>
              <span>⏱ 5 min Read</span>
            </div>

            {/* Hero Image */}
            <div className={styles.heroImage}>
              <img
                src="https://picsum.photos/seed/article-hero/800/400"
                alt="Global Markets Rally"
              />
            </div>

            {/* Highlighted Quote */}
            <blockquote className={styles.quote}>
              Stock markets worldwide recorded significant gains as investors responded positively to a series of promising economic indicators released Monday.
            </blockquote>

            {/* Body */}
            <div className={styles.body}>
              <p>
                Major stock indices around the globe posted impressive gains today as investors responded to a flurry of positive economic indicators, signalling that the global recovery may be gaining momentum. The S&P 500 climbed nearly 1.8%, while the Dow Jones Industrial Average and the Nasdaq followed closely behind. Analysts attribute the upturn to a combination of stronger-than-expected corporate earnings and a renewed sense of optimism in financial markets.
              </p>
              <p>
                The developments represent a significant milestone in the field, with experts predicting long-lasting impact for years to come. Experts highlighted how these results are in stark contrast to the volatility seen earlier this year, when rising interest rates and a slowdown in consumer spending had created significant turbulence across global exchanges.
              </p>
              <p>
                As the story continued to unfold, our team was already deploying coverage and live reporting across all platforms. The events described illustrate the breadth of News Dispatch's commitment to helping readers make sense of complex, fast-moving economic developments. We remain committed to providing clear, accurate, and timely reporting on everything that drives markets today.
              </p>
            </div>
          </article>
        </div>
      </main>

      <Footer />
    </div>
  );
}
