// src/models/Chat.model.ts
import mongoose, { Schema, Document } from 'mongoose';

export interface IChat extends Document {
  userId: number; // tgId
  role: 'user' | 'model'; // 'model' - это Gemini
  text: string;
  createdAt: Date;
}

const ChatSchema: Schema = new Schema({
  userId: { type: Number, required: true, index: true },
  role: { type: String, enum: ['user', 'model'], required: true },
  text: { type: String, required: true },
}, { 
  timestamps: true,
  collection: 'chats' // Читаем из коллекции 'chats'
});

export const Chat = mongoose.model<IChat>('Chat', ChatSchema);