// src/models/Admin.model.ts (ПРОВЕРЬТЕ КАЖДУЮ СТРОКУ)

import mongoose, { Schema, Document, Model } from 'mongoose';
import bcrypt from 'bcryptjs';

// 1. ИНТЕРФЕЙС ДОКУМЕНТА (использует 'password')
export interface IAdmin extends Document {
    email: string;
    password: string; 
    comparePassword(password: string): Promise<boolean>;
}

// 2. ИНТЕРФЕЙС МОДЕЛИ
export interface AdminModel extends Model<IAdmin> {} 


// 3. СХЕМА (использует 'password')
const AdminSchema = new Schema<IAdmin, AdminModel>({ 
    email: { type: String, required: true, unique: true },
    password: { type: String, required: true },
}, { timestamps: true });


// 4. ХУК ХЕШИРОВАНИЯ
AdminSchema.pre<IAdmin>('save', async function (next) {
    if (!this.isModified('password')) { 
        return next();
    }
    try {
        const salt = await bcrypt.genSalt(10);
        this.password = await bcrypt.hash(this.password, salt); 
        next();
    } catch (err) {
        next(err as any);
    }
});


// 5. МЕТОД СРАВНЕНИЯ (использует 'this.password')
AdminSchema.methods.comparePassword = function (password: string): Promise<boolean> {
    return bcrypt.compare(password, this.password);
};


// 6. ЭКСПОРТ
export const Admin = mongoose.model<IAdmin, AdminModel>('Admin', AdminSchema);