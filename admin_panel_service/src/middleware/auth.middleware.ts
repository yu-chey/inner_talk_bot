// src/middleware/auth.middleware.ts
import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

// Расширяем интерфейс Request, чтобы добавить в него свойство user
export interface AuthRequest extends Request {
  adminId?: string;
}

export const authMiddleware = (req: AuthRequest, res: Response, next: NextFunction) => {
  const token = req.header('Authorization')?.replace('Bearer ', '');

  if (!token) {
    return res.status(401).json({ message: 'Нет токена, авторизация отклонена' });
  }

  try {
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      throw new Error('JWT_SECRET не определен');
    }
    
    const decoded = jwt.verify(token, jwtSecret) as { id: string };
    req.adminId = decoded.id; // Добавляем ID админа в запрос
    next();
  } catch (err) {
    res.status(401).json({ message: 'Токен недействителен' });
  }
};