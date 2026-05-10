import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './styles/globals.css';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute   from './components/ProtectedRoute';
import LandingPage      from './pages/LandingPage';
import LoginPage        from './pages/LoginPage';
import SignUpPage       from './pages/SignUpPage';
import DashboardPage    from './pages/DashboardPage';
import ArticlePage      from './pages/ArticlePage';
import PipelinePage     from './pages/PipelinePage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/"          element={<LandingPage />} />
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/signup"    element={<SignUpPage />} />
          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/article/:slug" element={<ProtectedRoute><ArticlePage /></ProtectedRoute>} />
          <Route path="/pipeline"  element={<ProtectedRoute><PipelinePage /></ProtectedRoute>} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
