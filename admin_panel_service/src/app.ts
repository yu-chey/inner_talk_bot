// src/app.ts
import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import connectDB from './config/db';
import authRoutes from './routes/auth.routes';
import adminRoutes from './routes/admin.routes';

// Загружаем переменные окружения
dotenv.config();

// Подключаемся к БД
connectDB();

const app = express();

// Middleware
app.use(cors()); // Разрешаем запросы с других доменов (для фронтенда)
app.use(express.json()); // Разрешаем парсить JSON в теле запроса

// Роуты
app.use('/auth', authRoutes);
app.use('/admin', adminRoutes);

app.get('/', (req, res) => {
  res.send('Admin Panel Service API is running...');
});

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(`Admin Service запущен на порту ${PORT}`);
});