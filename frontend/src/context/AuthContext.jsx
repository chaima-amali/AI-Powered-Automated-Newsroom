import { createContext, useContext, useState } from 'react';
import { login as authLogin, logout as authLogout, getSession } from '../services/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getSession());

  async function login(email, password) {
    const result = await authLogin(email, password);
    if (result.success) setUser(result.user);
    return result;
  }

  function logout() {
    authLogout();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
