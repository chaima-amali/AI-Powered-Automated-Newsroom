/**
 * context/AuthContext.jsx
 * ------------------------
 * Real JWT authentication context.
 *
 * REPLACES the original fake sessionStorage auth:
 *  - Calls the real /api/v1/auth/login endpoint
 *  - Stores JWT in localStorage (survives page refresh)
 *  - Listens for auth:logout events (triggered on 401 by api.js)
 *  - Exposes isAuthenticated, user, login, logout, register
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { auth, setToken, setStoredUser, clearToken, getStoredUser, getToken } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(() => getStoredUser());
  const [loading, setLoading] = useState(false);

  // Listen for token expiry (401 → auth:logout event from api.js)
  useEffect(() => {
    const handler = () => { setUser(null); };
    window.addEventListener('auth:logout', handler);
    return () => window.removeEventListener('auth:logout', handler);
  }, []);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    try {
      const data = await auth.login(email, password);
      setToken(data.access_token);
      setStoredUser(data.user);
      setUser(data.user);
      return { success: true, user: data.user };
    } catch (e) {
      return { success: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (name, email, password) => {
    setLoading(true);
    try {
      const data = await auth.register(name, email, password);
      setToken(data.access_token);
      setStoredUser(data.user);
      setUser(data.user);
      return { success: true, user: data.user };
    } catch (e) {
      return { success: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      logout,
      register,
      isAuthenticated: !!user && !!getToken(),
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
