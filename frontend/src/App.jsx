import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './styles/globals.css';

import { AuthProvider } from './context/AuthContext';
import ProtectedRoute   from './components/ProtectedRoute';

import LandingPage   from './pages/LandingPage';
import DashboardPage from './pages/DashboardPage';
import ArticlePage   from './pages/ArticlePage';
import SignUpPage    from './pages/SignUpPage';
import LoginPage     from './pages/LoginPage';
import ProfilePage   from './pages/ProfilePage';
import SettingsPage  from './pages/SettingsPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/"       element={<LandingPage />} />
          <Route path="/login"  element={<LoginPage />} />
          <Route path="/signup" element={<SignUpPage />} />

          {/* Protected routes */}
          <Route path="/dashboard" element={
            <ProtectedRoute><DashboardPage /></ProtectedRoute>
          }/>
          <Route path="/article/:slug" element={
            <ProtectedRoute><ArticlePage /></ProtectedRoute>
          }/>
          <Route path="/profile" element={
            <ProtectedRoute><ProfilePage /></ProtectedRoute>
          }/>
          <Route path="/settings" element={
            <ProtectedRoute><SettingsPage /></ProtectedRoute>
          }/>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
