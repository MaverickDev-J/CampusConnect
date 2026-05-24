"use client";

import { useState, useEffect, type FormEvent } from "react";
import { User, Mail, Lock, GraduationCap, ArrowRight, Loader2, Sparkles, Link2 } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/app/context/auth-context";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

export default function SignupPage() {
    const { signup, loading, error, clearError, user } = useAuth();
    const router = useRouter();

    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [rollNo, setRollNo] = useState("");
    
    const [localError, setLocalError] = useState<string | null>(null);

    useEffect(() => {
        if (user) router.push("/");
    }, [user, router]);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        clearError();
        setLocalError(null);

        if (password !== confirmPassword) {
            setLocalError("Passwords do not match.");
            return;
        }
        if (password.length < 6) {
            setLocalError("Password must be at least 6 characters.");
            return;
        }

        try {
            await signup(name, email, password, { roll_no: rollNo });
        } catch (err) {
            // Error is handled by AuthContext
        }
    };

    const displayError = localError || error;

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center p-6 selection:bg-indigo-500/30 overflow-y-auto font-sans">
            {/* Background Decorative Elements */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-amber-500/5 blur-[120px] rounded-full" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-amber-500/5 blur-[120px] rounded-full" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[url('/grid.svg')] opacity-[0.03]" />
            </div>

            <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full max-w-lg relative py-12"
            >
                {/* Logo Section */}
                <div className="text-center mb-10 flex flex-col items-center">
                    <img src="/brand/logo_vertical.png" alt="Classroom Connect" className="w-[280px] h-auto object-contain mix-blend-multiply brightness-[1.05] contrast-[1.05]" />
                    <p className="text-slate-400 font-black tracking-[0.2em] text-[10px] uppercase mt-4">Intelligent Classroom Environment</p>
                </div>

                <div className="bg-white/70 backdrop-blur-xl border border-slate-200 p-8 sm:p-12 rounded-3xl shadow-premium relative overflow-hidden group">
                    <form onSubmit={handleSubmit} className="space-y-8 relative z-10">
                        {displayError && (
                            <motion.div 
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="p-4 rounded-2xl bg-red-50 border border-red-100 text-red-600 text-xs font-black text-center"
                            >
                                {displayError}
                            </motion.div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div className="space-y-3">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Full Name</label>
                                <div className="relative">
                                    <User className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                    <input 
                                        type="text" 
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        placeholder="Full Name"
                                        className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="space-y-3">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">ID / Roll No</label>
                                <div className="relative">
                                    <GraduationCap className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                    <input 
                                        type="text" 
                                        value={rollNo}
                                        onChange={(e) => setRollNo(e.target.value)}
                                        placeholder="21XXXXX"
                                        className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                        required
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Authorized Email</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                <input 
                                    type="email" 
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="name@institute.edu"
                                    className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                    required
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div className="space-y-3">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Password</label>
                                <div className="relative">
                                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                    <input 
                                        type="password" 
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="space-y-3">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Confirm</label>
                                <div className="relative">
                                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                    <input 
                                        type="password" 
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                        required
                                    />
                                </div>
                            </div>
                        </div>

                        <button 
                            type="submit"
                            disabled={loading}
                            className="w-full btn-accent py-5 rounded-3xl active:scale-95 disabled:opacity-50 flex items-center justify-center gap-3 uppercase tracking-[0.2em] text-xs mt-6"
                        >
                            {loading ? (
                                <Loader2 className="animate-spin" size={22} />
                            ) : (
                                <>
                                    Complete Classroom Registration
                                    <ArrowRight size={22} />
                                </>
                            )}
                        </button>
                    </form>
                </div>

                <p className="text-center mt-12 text-slate-400 text-sm font-bold">
                    Already part of the network? {" "}
                    <Link href="/login" className="text-amber-600 hover:text-amber-700 font-black transition-colors uppercase tracking-widest text-xs border-b-2 border-amber-100 ml-2">
                        Sign In
                    </Link>
                </p>
            </motion.div>
        </div>
    );
}
