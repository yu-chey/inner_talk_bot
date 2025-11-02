import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ChatPage from './pages/ChatPage'; // Убедитесь, что ChatPage импортирован
import { AuthProvider, useAuth } from './context/AuthContext'; 

// -------------------------------------------------------------------
// ЭТО ОПРЕДЕЛЕНИЕ ДОЛЖНО БЫТЬ В App.tsx
// Компонент-обёртка для защищённых роутов
const ProtectedRoute: React.FC = () => {
  const { isAuthenticated } = useAuth();
  
  // Если не авторизован, перенаправляем на страницу входа
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  // Иначе, рендерим дочерние элементы (<Outlet /> рендерит вложенный <Route>)
  return <Outlet />;
};
// -------------------------------------------------------------------

// src/App.tsx (фрагмент)

// ... ваши импорты вверху ...

const App: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <Routes>
          {/* ИСПОЛЬЗУЕМ LoginPage */}
          <Route path="/login" element={<LoginPage />} /> 
          
          <Route element={<ProtectedRoute />}>
            {/* ИСПОЛЬЗУЕМ DashboardPage */}
            <Route path="/dashboard" element={<DashboardPage />} /> 
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            
            {/* ИСПОЛЬЗУЕМ ChatPage */}
            <Route path="/chats/:userId" element={<ChatPage />} /> 
          </Route>
          
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </Router>
  );
};

export default App;