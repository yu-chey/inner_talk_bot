import React, { createContext, useState, useContext, ReactNode } from 'react';
import axios from 'axios';

// 1. Константа для базового URL бэкенда
const API_URL = 'http://localhost:5000/auth'; // Используем ваш порт 5000

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Ищем токен в локальном хранилище при запуске
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const isAuthenticated = !!token;

  const login = async (email: String , password: String) => {
    try {
      const response = await axios.post(`${API_URL}/login`, { email, password });
      const newToken = response.data.token;
      
      localStorage.setItem('token', newToken); // Сохраняем токен
      setToken(newToken); // Обновляем состояние
      
    } catch (error) {
      if (axios.isAxiosError(error) && error.response) {
        throw new Error(error.response.data.message || 'Ошибка входа');
      }
      throw new Error('Произошла неизвестная ошибка');
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  return (
    <AuthContext.Provider value={{ token, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth должен использоваться внутри AuthProvider');
  }
  return context;
};