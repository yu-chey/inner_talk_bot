import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import UserList from '../components/UserList';

const API_BASE_URL = 'http://localhost:5000/admin'; 

const DashboardPage: React.FC = () => {
  const { token, logout } = useAuth();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUsers = async () => {
      if (!token) {
        setError("Неавторизован");
        setLoading(false);
        return;
      }

      try {
        const response = await axios.get(`${API_BASE_URL}/users`, {
          headers: {
            Authorization: `Bearer ${token}`, // Отправляем JWT
          },
        });
        setUsers(response.data);
        setLoading(false);
      } catch (err) {
        if (axios.isAxiosError(err) && err.response && err.response.status === 401) {
            // Если токен недействителен, разлогиниваемся
            logout(); 
            setError("Сессия истекла. Войдите снова.");
        } else {
            setError('Ошибка загрузки данных');
        }
        setLoading(false);
      }
    };

    fetchUsers();
  }, [token, logout]);

  if (loading) return <div style={{ padding: '20px' }}>Загрузка...</div>;
  if (error && error !== "Неавторизован") return <div style={{ padding: '20px', color: 'red' }}>Ошибка: {error}</div>;

  return (
    <div style={{ padding: '20px' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #ccc', paddingBottom: '10px', marginBottom: '20px' }}>
        <h1>👥 Панель Администратора</h1>
        <button onClick={logout} style={{ padding: '8px 15px', cursor: 'pointer' }}>Выход</button>
      </header>
      
      <UserList users={users} />
    </div>
  );
};

export default DashboardPage;