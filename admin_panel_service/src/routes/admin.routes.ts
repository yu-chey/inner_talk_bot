// src/routes/admin.routes.ts
import { Router, Response } from 'express';
import { User } from '../models/User.model';
import { Chat } from '../models/Chat.model';
import { authMiddleware, AuthRequest } from '../middleware/auth.middleware';

const router = Router();

// Все роуты здесь защищены
router.use(authMiddleware);

// GET /admin/users
router.get('/users', async (req: AuthRequest, res: Response) => {
  try {
    const users = await User.find().sort({ createdAt: -1 });
    res.json(users);
  } catch (err) {
    console.error(err);
    res.status(500).send('Server Error');
  }
});

// GET /admin/user/:userId/chats
// :userId здесь - это tgId
router.get('/user/:userId/chats', async (req: AuthRequest, res: Response) => {
  try {
    const { userId } = req.params;
    const chats = await Chat.find({ userId: Number(userId) }).sort({ createdAt: 1 });
    
    if (!chats) {
      return res.status(404).json({ message: 'Чаты для этого пользователя не найдены' });
    }
    
    res.json(chats);
  } catch (err) {
    console.error(err);
    res.status(500).send('Server Error');
  }
});

export default router;