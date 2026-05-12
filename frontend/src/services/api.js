/**
 * services/api.js
 * ----------------
 * Centralised API client for the NewsDispatch backend.
 *
 * All fetch calls go through this module so:
 *  - Auth headers are added automatically
 *  - 401 responses trigger logout
 *  - Errors are normalised into { message, status } objects
 *  - Base URL is configurable via VITE_API_BASE env var
 *
 * REPLACES: scattered fetch() calls with hardcoded URLs and no auth handling.
 */

const BASE = import.meta.env.VITE_API_BASE || '/api/v1';

// ── Token storage ─────────────────────────────────────────────────────────────
export function getToken()           { return localStorage.getItem('nd_token'); }
export function setToken(t)          { localStorage.setItem('nd_token', t); }
export function clearToken()         { localStorage.removeItem('nd_token'); localStorage.removeItem('nd_user'); }
export function getStoredUser()      { try { return JSON.parse(localStorage.getItem('nd_user') || 'null'); } catch { return null; } }
export function setStoredUser(user)  { localStorage.setItem('nd_user', JSON.stringify(user)); }

function authHeaders() {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });

  // Handle 401 globally — token expired or invalid
  if (resp.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent('auth:logout'));
    throw new Error('Session expired — please sign in again.');
  }

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const d = await resp.json();
      detail = d.detail || d.message || detail;
    } catch {}
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }

  return resp.json();
}

const get  = (path, params) => {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request(`${path}${qs}`);
};
const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });

// ── Auth ──────────────────────────────────────────────────────────────────────
export const auth = {
  login:    (email, password) => post('/auth/login',    { email, password }),
  register: (name, email, password) => post('/auth/register', { name, email, password }),
  me:       () => get('/auth/me'),
};

// ── Articles ──────────────────────────────────────────────────────────────────
export const articles = {
  list:     (params) => get('/articles', params),
  latest:   (limit = 6, language) => get('/articles/latest', { limit, ...(language ? { language } : {}) }),
  trending: (limit = 6) => get('/articles/trending', { limit }),
  bySlug:   (slug) => get(`/articles/${slug}`),
};

// ── Search ────────────────────────────────────────────────────────────────────
export const search = {
  query: (q, limit = 10, language) => get('/search', { q, limit, ...(language ? { language } : {}) }),
};

// ── Health ────────────────────────────────────────────────────────────────────
export const health = {
  get:        () => get('/health'),
  categories: () => get('/categories'),
};

// ── Pipeline ──────────────────────────────────────────────────────────────────
export const pipeline = {
  status:  ()            => get('/pipeline/status'),
  jobs:    (limit = 20)  => get('/pipeline/jobs', { limit }),
  trigger: (stage, apiKey) => fetch(`${BASE}/pipeline/trigger`, {
    method: 'POST',
    headers: { ...authHeaders(), 'X-Api-Key': apiKey },
    body: JSON.stringify({ stage }),
  }).then(r => {
    if (!r.ok) return r.json().then(d => Promise.reject(new Error(d.detail || r.statusText)));
    return r.json();
  }),
};

// ── SSE ───────────────────────────────────────────────────────────────────────
/**
 * Connect to the Server-Sent Events stream.
 * Returns an object with a .close() method.
 *
 * @param {(event: object) => void} onEvent
 * @param {() => void} onConnect
 * @param {() => void} onError
 */
export function connectSSE({ onEvent, onConnect, onError } = {}) {
  const url = (import.meta.env.VITE_API_BASE || '').replace('/api/v1', '') + '/api/v1/events';
  const es  = new EventSource(url);

  es.onopen    = () => onConnect?.();
  es.onerror   = () => onError?.();
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent?.(data);
    } catch {}
  };

  return { close: () => es.close() };
}
