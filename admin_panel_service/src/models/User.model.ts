// src/models/User.model.ts
import mongoose, { Schema, Document } from 'mongoose';

export interface IUser extends Document {
  tgId: number; // ID из Telegram
  firstName: string;
  username?: string;
  createdAt: Date;
}

// Указываем Mongoose, что коллекция называется 'users'
const UserSchema: Schema = new Schema({
  tgId: { type: Number, required: true, unique: true },
  firstName: { type: String },
  username: { type: String },
}, { 
  timestamps: true, // Добавляет createdAt и updatedAt
  collection: 'users' // Читаем из той же коллекции, куда пишет бот
});

export const User = mongoose.model<IUser>('User', UserSchema);