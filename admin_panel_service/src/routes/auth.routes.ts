// src/routes/auth.routes.ts
import { Router, Request, Response } from 'express'; // <-- 1. ИМПОРТИРОВАТЬ ТИПЫ
import { Admin } from '../models/Admin.model';
import jwt from 'jsonwebtoken';
import { body, validationResult } from 'express-validator';

const router = Router();

// POST /auth/login
router.post(
  '/login',
  [
    body('email', 'Введите корректный email').isEmail(),
    body('password', 'Пароль не должен быть пустым').notEmpty(),
  ],
  async (req: Request, res: Response) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() });
    }

    const { email, password } = req.body;

    try {
      const admin = await Admin.findOne({ email });
      if (!admin) {
        return res.status(400).json({ message: 'Неверные учетные данные (email)' });
      }

      const isMatch = await admin.comparePassword(password);
      if (!isMatch) {
        return res.status(400).json({ message: 'Неверные учетные данные (пароль)' });
      }

      const payload = { id: admin.id };
      const jwtSecret = process.env.JWT_SECRET || 'fallback_secret';
      
      const token = jwt.sign(payload, jwtSecret, { expiresIn: '7d' });

      res.status(200).json({ token });
    } catch (err) {
      console.error(err);
      res.status(500).send('Server Error');
    }
  }
);

// POST /auth/register (ВРЕМЕННО - для создания первого админа)
// После создания админа этот роут можно удалить или закомментировать
router.post('/register', async (req: Request, res: Response) => {
    try {
        const { email, password } = req.body;
        let admin = await Admin.findOne({ email });
        if (admin) {
            return res.status(400).json({ message: "Админ уже существует" });
        }
        
        // ВАЖНО: мы сохраняем 'password' в поле 'passwordHash',
        // pre-save хук в модели его автоматически захэширует.
        admin = new Admin({ email, password: password });
        await admin.save();
        
        res.status(201).json({ message: "Админ создан" });

    } catch (err) {
        console.error(err);
        res.status(500).send('Server Error');
    }
});


export default router;