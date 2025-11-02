import React from 'react';
import { Link } from 'react-router-dom';

interface IUser {
  _id: string;
  tgId: number;
  firstName: string;
  username?: string;
  createdAt: string; // ISO Date String
}

interface UserListProps {
  users: IUser[];
}

const UserList: React.FC<UserListProps> = ({ users }) => {
  if (users.length === 0) {
    return <p>Пользователи бота пока не найдены в базе данных.</p>;
  }

  return (
    <div>
      <h3>Список пользователей ({users.length})</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #333' }}>
            <th style={{ padding: '10px', textAlign: 'left' }}>Telegram ID</th>
            <th style={{ padding: '10px', textAlign: 'left' }}>Имя</th>
            <th style={{ padding: '10px', textAlign: 'left' }}>Username</th>
            <th style={{ padding: '10px', textAlign: 'left' }}>Дата регистрации</th>
            <th style={{ padding: '10px', textAlign: 'left' }}>Действия</th>
          </tr>
        </thead>
        <tbody>
        {users.map((user) => (
          <tr key={user._id} style={{ borderBottom: '1px solid #eee' }}>
            {/* ... другие <td> ... */}
            <td style={{ padding: '10px' }}>
              {/* Этот код с <Link> уже должен быть здесь */}
              <Link to={`/chats/${user.tgId}`} style={{ color: 'blue', textDecoration: 'none' }}>
                Посмотреть чаты
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
      </table>
    </div>
  );
};

export default UserList;