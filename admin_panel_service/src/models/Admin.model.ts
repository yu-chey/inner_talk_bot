// src/models/Admin.model.ts
import mongoose, { Schema, Document } from 'mongoose';
import bcrypt from 'bcryptjs';

export interface IAdmin extends Document {
  email: string;
  passwordHash: string;
  comparePassword(password: string): Promise<boolean>;
}

const AdminSchema: Schema = new Schema({
  email: { type: String, required: true, unique: true, lowercase: true },
  passwordHash: { type: String, required: true },
});

// Хешируем пароль перед сохранением
AdminSchema.pre<IAdmin>('save', async function (next) {
  if (!this.isModified('passwordHash')) {
    return next();
  }
  const salt = await bcrypt.genSalt(10);
  this.passwordHash = await bcrypt.hash(this.passwordHash, salt);
  next();
});

// Метод для сравнения пароля
AdminSchema.methods.comparePassword = function (password: string): Promise<boolean> {
  return bcrypt.compare(password, this.passwordHash);
};

export const Admin = mongoose.model<IAdmin>('Admin', AdminSchema);