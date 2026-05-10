/**
 * hooks/useArticles.js — hook for paginated article list
 * hooks/useHealth.js   — hook for pipeline health stats
 * hooks/usePipeline.js — hook for pipeline status + SSE events
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { articles as articleApi, health as healthApi, pipeline as pipelineApi, connectSSE } from '../services/api';

// ── useArticles ───────────────────────────────────────────────────────────────
export function useArticles({ category, search, language, limit = 9 } = {}) {
  const [data,    setData]    = useState([]);
  const [page,    setPage]    = useState(1);
  const [total,   setTotal]   = useState(0);
  const [pages,   setPages]   = useState(1);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const fetchPage = useCallback(async (p = 1, reset = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = { page: p, limit };
      if (category && category !== 'All') params.category = category;
      if (search)   params.q        = search;
      if (language) params.language = language;

      const result = await articleApi.list(params);
      setData(prev => reset ? result.data : [...prev, ...result.data]);
      setTotal(result.pagination.total);
      setPages(result.pagination.pages);
      setPage(p);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [category, search, language, limit]);

  // Re-fetch when filters change
  useEffect(() => {
    fetchPage(1, true);
  }, [fetchPage]);

  const loadMore = () => { if (page < pages) fetchPage(page + 1, false); };
  const refresh  = ()  => fetchPage(1, true);

  return { data, loading, error, page, pages, total, loadMore, refresh, hasMore: page < pages };
}

// ── useHealth ─────────────────────────────────────────────────────────────────
export function useHealth() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    healthApi.get()
      .then(d  => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { data, loading };
}

// ── usePipelineStatus ─────────────────────────────────────────────────────────
export function usePipelineStatus() {
  const [status,    setStatus]    = useState({});
  const [connected, setConnected] = useState(false);
  const [logs,      setLogs]      = useState([]);
  const sseRef = useRef(null);

  // Poll status on mount
  useEffect(() => {
    pipelineApi.status()
      .then(d => setStatus(d.stages || {}))
      .catch(() => {});
  }, []);

  // SSE connection
  useEffect(() => {
    sseRef.current = connectSSE({
      onConnect: () => {
        setConnected(true);
        addLog('info', '🔗 Connected to live event stream');
      },
      onError: () => {
        setConnected(false);
        addLog('warn', '⚠️ SSE disconnected');
      },
      onEvent: (ev) => {
        handleSSEEvent(ev);
      },
    });
    return () => sseRef.current?.close();
  }, []);

  function addLog(level, msg) {
    const entry = { level, msg, ts: new Date().toLocaleTimeString() };
    setLogs(prev => [...prev.slice(-299), entry]);
  }

  function handleSSEEvent(ev) {
    const { type } = ev;
    switch (type) {
      case 'stage_start':
        setStatus(prev => ({ ...prev, [ev.stage]: 'running' }));
        addLog('stage', `▶ [${ev.stage}] started`);
        break;
      case 'stage_done':
        setStatus(prev => ({ ...prev, [ev.stage]: 'done' }));
        addLog('success', `✅ [${ev.stage}] done in ${ev.elapsed_sec}s`);
        if (ev.result) addLog('info', `   ${String(ev.result).slice(0, 120)}`);
        break;
      case 'stage_error':
        setStatus(prev => ({ ...prev, [ev.stage]: 'failed' }));
        addLog('error', `❌ [${ev.stage}] error: ${ev.error}`);
        break;
      case 'scraper_started':
        addLog('info', `🕷️ Scraper started — ${ev.source_count} sources`);
        break;
      case 'source_done':
        addLog('info', `  ✔ ${ev.source} [${ev.progress}/${ev.total}] +${ev.inserted}`);
        break;
      case 'source_error':
        addLog('warn', `  ✘ ${ev.source}: ${ev.error}`);
        break;
      case 'scraper_done':
        addLog('success', `🕷️ Scraper done — ${ev.inserted} inserted`);
        break;
      case 'embedding_started':
        addLog('info', `🧠 Embedding started — model: ${ev.model}`);
        break;
      case 'embedding_done':
        addLog('success', `🧠 Embedding done — ${ev.clusters_created} clusters`);
        break;
      case 'summarizer_started':
        addLog('info', `📝 Summarizer — ${ev.cluster_count} clusters`);
        break;
      case 'summarizer_done':
        addLog('success', `📝 Summarizer done — ${ev.success} ok, ${ev.failed} failed`);
        break;
      case 'rewriter_started':
        addLog('info', `✍️ Rewriter — ${ev.summary_count} summaries`);
        break;
      case 'rewriter_done':
        addLog('success', `✍️ Rewriter done — ${ev.published} published, ${ev.drafted} drafted`);
        break;
      case 'rewriter_article':
        addLog(ev.status === 'published' ? 'success' : 'info',
          `  ${ev.status === 'published' ? '📰' : '📝'} [${ev.pub_id}] ${ev.title}`);
        break;
      default:
        if (ev.type !== 'connected') addLog('info', JSON.stringify(ev).slice(0, 120));
    }
  }

  return { status, connected, logs, clearLogs: () => setLogs([]) };
}
