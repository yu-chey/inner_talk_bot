// src/pages/ChatPage.tsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const API_BASE_URL = 'http://localhost:5000/admin';

interface IChatMessage {
  _id: string;
  userId: number;
  role: 'user' | 'model';
  text: string;
  createdAt: string;
}

const ChatPage: React.FC = () => {
  // Получаем userId из URL, который мы задали в App.tsx
  const { userId } = useParams<{ userId: string }>(); 
  const navigate = useNavigate();
  const { token, logout } = useAuth();
  
  const [chats, setChats] = useState<IChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !userId) return;

    const fetchChats = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/user/${userId}/chats`, {
          headers: {
            Authorization: `Bearer ${token}`, // Отправляем JWT
          },
        });
        setChats(response.data);
        setLoading(false);
      } catch (err) {
        if (axios.isAxiosError(err) && err.response && err.response.status === 401) {
            logout(); 
            setError("Сессия истекла. Войдите снова.");
        } else {
            setError('Ошибка загрузки истории чатов.');
        }
        setLoading(false);
      }
    };

    fetchChats();
  }, [token, userId, logout]);

  if (loading) return <div style={{ padding: '20px' }}>Загрузка чата...</div>;
  if (error) return <div style={{ padding: '20px', color: 'red' }}>Ошибка: {error}</div>;

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <button onClick={() => navigate('/dashboard')} style={{ marginBottom: '20px', cursor: 'pointer' }}>
        &larr; Назад к пользователям
      </button>
      <h2>💬 История Чата для TG ID: {userId}</h2>
      
      {chats.length === 0 ? (
        <p>История чатов для этого пользователя не найдена.</p>
      ) : (
        <div style={{ maxHeight: '60vh', overflowY: 'scroll', border: '1px solid #ccc', padding: '10px' }}>
          {chats.map((msg) => (
            <div 
              key={msg._id} 
              style={{
                marginBottom: '15px', 
                padding: '10px',
                borderRadius: '10px',
                // Стилизуем сообщения по роли
                background: msg.role === 'user' ? '#e0f7fa' : '#f1f8e9', 
                marginLeft: msg.role === 'user' ? 'auto' : '0', 
                marginRight: msg.role === 'model' ? 'auto' : '0',
                maxWidth: '70%',
                wordWrap: 'break-word'
              }}
            >
              <strong>{msg.role === 'user' ? 'Пользователь:' : 'Gemini (Бот):'}</strong>
              <p style={{ margin: '5px 0 0 0' }}>{msg.text}</p>
              <small style={{ color: '#666', fontSize: '0.7em', display: 'block', textAlign: 'right' }}>
                {new Date(msg.createdAt).toLocaleString()}
              </small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChatPage;