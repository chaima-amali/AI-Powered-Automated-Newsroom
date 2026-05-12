import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { health } from '../services/api';
import styles from './LandingPage.module.css';

const FEATURES = [
  { icon: '🕷️', title: 'Concurrent Scraping',    desc: 'Scrapes 16+ Algerian RSS feeds in parallel using thread pools, with per-domain rate limiting and adaptive backoff.' },
  { icon: '🧠', title: 'Semantic Clustering',     desc: 'multilingual-e5-base embeddings + DBSCAN groups related articles from different sources into coherent story clusters.' },
  { icon: '📝', title: 'Hybrid Summarization',    desc: 'Routes each cluster to the best strategy: BART for general news, LLM (Mistral/Llama) for political nuance.' },
  { icon: '✍️', title: 'AI Article Rewriting',    desc: 'LLM transforms cluster summaries into original, publication-ready French articles with SEO metadata and quality scoring.' },
  { icon: '📊', title: 'Live Pipeline Monitor',   desc: 'Server-Sent Events stream every pipeline stage directly to the browser — no polling, no refresh.' },
  { icon: '🔍', title: 'Semantic Search',         desc: 'pgvector cosine similarity search finds contextually related articles far beyond keyword matching.' },
];

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function LandingPage() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    health.get().then(setStats).catch(() => {});
  }, []);

  return (
    <div className={styles.page}>
      <Navbar />

      {/* ── Hero ──────────────────────────────────────────── */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.badge}>🤖 AI-Powered Newsroom</div>
          <h1 className={styles.heroTitle}>
            Algeria's stories,<br />
            <em className={styles.accent}>intelligently curated.</em>
          </h1>
          <p className={styles.heroDesc}>
            NewsDispatch automatically gathers, clusters, summarises, and rewrites
            news from 16+ Algerian sources — delivering publication-ready articles
            in real time, fully automated.
          </p>
          <div className={styles.heroBtns}>
            <Link to="/signup" className={styles.primaryBtn}>Start discovering →</Link>
            <Link to="/login"  className={styles.ghostBtn}>Sign in</Link>
          </div>

          {/* Live stats */}
          <div className={styles.statsRow}>
            <StatItem value={fmt(stats?.total_articles)} label="Articles scraped" />
            <StatItem value={fmt(stats?.total_clusters)}  label="Story clusters" />
            <StatItem value={fmt(stats?.published_count)} label="Published stories" />
            <StatItem value="16+"                         label="News sources" />
          </div>
        </div>

        {/* Decorative pipeline illustration */}
        <div className={styles.heroVisual} aria-hidden="true">
          <PipelineVisual />
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────── */}
      <section className={styles.features}>
        <div className="container">
          <p className={styles.sectionLabel}>Why NewsDispatch</p>
          <h2 className={styles.sectionTitle}>From raw RSS to polished article<br />in under 60 seconds.</h2>
          <div className={styles.featuresGrid}>
            {FEATURES.map(f => (
              <div key={f.title} className={styles.featureCard}>
                <div className={styles.featureIcon}>{f.icon}</div>
                <h3 className={styles.featureTitle}>{f.title}</h3>
                <p className={styles.featureDesc}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pipeline stages ────────────────────────────────── */}
      <section className={styles.pipeline}>
        <div className="container">
          <p className={styles.sectionLabel}>The Pipeline</p>
          <h2 className={styles.sectionTitle}>4 automated stages.</h2>
          <div className={styles.stagesRow}>
            {[
              { n: '01', icon: '🕷️', name: 'Scraper',    desc: 'RSS + sitemap + article parse' },
              { n: '02', icon: '🧠', name: 'Embedding',  desc: 'Vector encoding + DBSCAN cluster' },
              { n: '03', icon: '📝', name: 'Summarizer', desc: 'Hybrid extractive / LLM summary' },
              { n: '04', icon: '✍️', name: 'Rewriter',   desc: 'LLM article + quality gate + publish' },
            ].map((s, i, arr) => (
              <div key={s.n} className={styles.stageStep}>
                <div className={styles.stageCard}>
                  <span className={styles.stageNum}>{s.n}</span>
                  <span className={styles.stageIcon}>{s.icon}</span>
                  <strong className={styles.stageName}>{s.name}</strong>
                  <p className={styles.stageDesc}>{s.desc}</p>
                </div>
                {i < arr.length - 1 && <div className={styles.stageArrow}>→</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────── */}
      <section className={styles.cta}>
        <h2 className={styles.ctaTitle}>See the pipeline run live.</h2>
        <p className={styles.ctaDesc}>Sign in and open the Pipeline Monitor to trigger stages and watch real-time SSE logs.</p>
        <Link to="/signup" className={styles.ctaBtn}>Open Pipeline Monitor →</Link>
      </section>

      <footer className={styles.footer}>
        <p>© 2025 NewsDispatch · FastAPI + pgvector + React</p>
      </footer>
    </div>
  );
}

function StatItem({ value, label }) {
  return (
    <div className={styles.statItem}>
      <span className={styles.statVal}>{value}</span>
      <span className={styles.statLbl}>{label}</span>
    </div>
  );
}

function PipelineVisual() {
  return (
    <div className={styles.visualBox}>
      {['🕷️ Scraper', '🧠 Embedding', '📝 Summarizer', '✍️ Rewriter'].map((stage, i) => (
        <div key={stage} className={styles.visualStage} style={{ animationDelay: `${i * 0.15}s` }}>
          <div className={styles.visualDot} />
          <span>{stage}</span>
          <span className={styles.visualStatus}>ready</span>
        </div>
      ))}
    </div>
  );
}
