import { useState, useRef, useEffect } from 'react';
import Navbar from '../components/Navbar';
import { usePipelineStatus } from '../hooks/useData';
import { pipeline as pipelineApi } from '../services/api';
import styles from './PipelinePage.module.css';

const STAGE_CONFIG = [
  { id: 'scraper',    icon: '🕷️', label: 'Scraper',    desc: 'RSS feeds, sitemap crawl, article parsing' },
  { id: 'embedding',  icon: '🧠', label: 'Embedding',  desc: 'Multilingual vectors + DBSCAN clustering' },
  { id: 'summarizer', icon: '📝', label: 'Summarizer', desc: 'Hybrid extractive + LLM per cluster' },
  { id: 'rewriter',   icon: '✍️', label: 'Rewriter',   desc: 'LLM article + quality gate + publish' },
];

const STATUS_LABELS = { idle: 'Idle', pending: 'Pending', running: 'Running…', done: 'Done', failed: 'Failed' };

export default function PipelinePage() {
  const { status, connected, logs, clearLogs } = usePipelineStatus();
  const [apiKey,    setApiKey]    = useState('');
  const [triggering, setTriggering] = useState('');
  const [toast,      setToast]     = useState(null);
  const logRef = useRef(null);

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  function showToast(msg, type = 'info') {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function triggerStage(stage) {
    const key = apiKey || prompt('Enter your API secret key (X-Api-Key):', '') || '';
    if (!key) return;
    if (!apiKey) setApiKey(key);
    setTriggering(stage);
    try {
      const result = await pipelineApi.trigger(stage, key);
      const started = result.started?.join(', ') || 'none';
      const running = result.already_running?.join(', ');
      showToast(
        running
          ? `Already running: ${running}. Started: ${started || 'none'}`
          : `▶ Started: ${started}`,
        'success'
      );
    } catch (e) {
      showToast(`Error: ${e.message}`, 'error');
    } finally {
      setTriggering('');
    }
  }

  return (
    <div className={styles.page}>
      <Navbar />
      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}

      <main className={styles.main}>
        <div className="container">

          {/* ── Header ─────────────────────────────────── */}
          <div className={styles.header}>
            <div>
              <h1 className={styles.title}>Pipeline Monitor</h1>
              <p className={styles.sub}>
                Trigger pipeline stages and watch real-time SSE execution logs.
              </p>
            </div>
            <button
              className={styles.runAllBtn}
              onClick={() => triggerStage('all')}
              disabled={!!triggering}
            >
              {triggering === 'all' ? '⏳ Running…' : '▶ Run Full Pipeline'}
            </button>
          </div>

          {/* ── API key input ───────────────────────────── */}
          <div className={styles.keyRow}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <input
              type="password"
              className={styles.keyInput}
              placeholder="API secret key (X-Api-Key) — set API_SECRET_KEY in .env"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
            />
          </div>

          {/* ── Main layout ─────────────────────────────── */}
          <div className={styles.layout}>

            {/* Stage cards */}
            <div className={styles.stageList}>
              {STAGE_CONFIG.map(s => {
                const stageStatus = status[s.id] || 'idle';
                const isRunning   = stageStatus === 'running';
                const isBusy      = !!triggering;
                return (
                  <div
                    key={s.id}
                    className={`${styles.stageCard} ${styles[stageStatus] || ''}`}
                  >
                    <div className={styles.stageTop}>
                      <div className={styles.stageLabel}>
                        <span className={styles.stageIcon}>{s.icon}</span>
                        <span className={styles.stageName}>{s.label}</span>
                      </div>
                      <div className={styles.stageRight}>
                        <span className={`status-dot ${stageStatus}`}>
                          {STATUS_LABELS[stageStatus] || stageStatus}
                        </span>
                        <button
                          className={styles.runBtn}
                          onClick={() => triggerStage(s.id)}
                          disabled={isRunning || isBusy}
                        >
                          {triggering === s.id ? '⏳' : '▶ Run'}
                        </button>
                      </div>
                    </div>
                    <p className={styles.stageDesc}>{s.desc}</p>

                    {/* Progress bar when running */}
                    {isRunning && <div className={styles.progressBar}><div className={styles.progressFill} /></div>}
                  </div>
                );
              })}
            </div>

            {/* Log panel */}
            <div className={styles.logPanel}>
              <div className={styles.logHeader}>
                <div className={styles.logTitle}>
                  <span
                    className={styles.sseDot}
                    style={{ background: connected ? 'var(--green)' : 'var(--red)' }}
                  />
                  Live Logs
                  <span className={styles.sseLabel}>{connected ? 'SSE connected' : 'SSE offline'}</span>
                </div>
                <button className={styles.clearBtn} onClick={clearLogs}>clear</button>
              </div>

              <div className={styles.logEntries} ref={logRef}>
                {logs.length === 0 ? (
                  <div className={styles.logEmpty}>
                    No events yet — trigger a stage to see real-time logs.
                  </div>
                ) : (
                  logs.map((entry, i) => (
                    <div key={i} className={`${styles.logLine} ${styles[entry.level] || ''}`}>
                      <span className={styles.ts}>{entry.ts}</span>
                      <span>{entry.msg}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* ── Job history ─────────────────────────────── */}
          <JobHistory />
        </div>
      </main>

      <footer className={styles.footer}>© 2025 NewsDispatch</footer>
    </div>
  );
}

function JobHistory() {
  const [jobs,    setJobs]    = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    pipelineApi.jobs(10)
      .then(d => { setJobs(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (!jobs.length) return null;

  return (
    <div className={styles.history}>
      <h2 className={styles.historyTitle}>Recent Jobs</h2>
      <div className={styles.historyTable}>
        <div className={styles.tableHead}>
          <span>Stage</span><span>Status</span><span>Started</span><span>Duration</span>
        </div>
        {jobs.map(job => {
          const started  = job.started_at  ? new Date(job.started_at) : null;
          const finished = job.finished_at ? new Date(job.finished_at) : null;
          const durSec   = (started && finished)
            ? Math.round((finished - started) / 1000)
            : null;
          return (
            <div key={job.id} className={styles.tableRow}>
              <span className={styles.jobType}>{job.job_type}</span>
              <span className={`status-dot ${job.status}`}>{job.status}</span>
              <span className={styles.jobDate}>{started ? started.toLocaleString() : '—'}</span>
              <span className={styles.jobDur}>{durSec != null ? `${durSec}s` : '—'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
