// ─── Backend API Auth ───────────────────────────────────────────────
const API_BASE = 'http://localhost:8000/api/v1';

export async function login(email, password) {
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      return { success: false, error: error.detail || 'Login failed' };
    }
    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    return { success: true, user: data.user };
  } catch (err) {
    return { success: false, error: 'Network error' };
  }
}

export function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

export function getSession() {
  try {
    const user = localStorage.getItem('user');
    const token = localStorage.getItem('token');
    return user && token ? JSON.parse(user) : null;
  } catch {
    return null;
  }
}

export function getToken() {
  return localStorage.getItem('token');
}

export async function register(name, email, password) {
  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password })
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      return { success: false, error: error.detail || 'Registration failed' };
    }
    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    return { success: true, user: data.user };
  } catch (err) {
    return { success: false, error: 'Network error' };
  }
}
