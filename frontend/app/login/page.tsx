"use client";

import { useState, useEffect, type FormEvent } from "react";
import { Link2, ShieldCheck, Mail, Lock, Loader2, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/app/context/auth-context";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

export default function LoginPage() {
    const { login, loading, error, clearError, user } = useAuth();
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    useEffect(() => {
        if (user) router.push("/");
    }, [user, router]);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        clearError();
        await login(email, password);
    };

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center p-6 selection:bg-indigo-500/30 overflow-y-auto font-sans">
            {/* Background Decorative Elements */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-amber-500/5 blur-[120px] rounded-full" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-amber-500/5 blur-[120px] rounded-full" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[url('/grid.svg')] opacity-[0.03]" />
            </div>

            <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="w-full max-w-md relative"
            >
                {/* Logo Section */}
                <div className="text-center mb-10 flex flex-col items-center">
                    <img src="/brand/logo_vertical.png" alt="Classroom Connect" className="w-[280px] h-auto object-contain mix-blend-multiply brightness-[1.05] contrast-[1.05]" />
                    <p className="text-slate-400 font-black tracking-[0.2em] text-[10px] uppercase mt-4">Secure Learning Access</p>
                </div>

                <div className="bg-white/70 backdrop-blur-xl border border-slate-200 p-8 sm:p-12 rounded-3xl shadow-premium relative overflow-hidden group">
                    <form onSubmit={handleSubmit} className="space-y-8 relative z-10">
                        {error && (
                            <motion.div 
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="p-4 rounded-2xl bg-red-50 border border-red-100 text-red-600 text-xs font-black text-center"
                            >
                                {error}
                            </motion.div>
                        )}

                        <div className="space-y-3">
                            <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Authorized Email</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                <input 
                                    type="email" 
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="your@institute.edu"
                                    className="w-full bg-slate-50 border-2 border-slate-50 rounded-3xl py-4 pl-12 pr-4 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all text-sm font-bold placeholder:text-slate-300"
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-3">
                            <div className="flex justify-between items-center ml-4">
                                <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Security Key</label>
                                <button type="button" className="text-[10px] font-black uppercase tracking-[0.2em] text-amber-600 hover:text-amber-700 transition-colors">Forgot Key?</button>
                            </div>
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

                        <button 
                            type="submit"
                            disabled={loading}
                            className="w-full btn-accent py-5 rounded-3xl active:scale-95 disabled:opacity-50 flex items-center justify-center gap-3 uppercase tracking-[0.2em] text-xs"
                        >
                            {loading ? (
                                <Loader2 className="animate-spin" size={22} />
                            ) : (
                                <>
                                    Sign In
                                    <ArrowRight size={22} />
                                </>
                            )}
                        </button>
                    </form>
                </div>

                <p className="text-center mt-12 text-slate-400 text-sm font-bold">
                    New to the network? {" "}
                    <Link href="/signup" className="text-amber-600 hover:text-amber-700 font-black transition-colors uppercase tracking-widest text-xs border-b-2 border-amber-100 ml-2">
                        Signup
                    </Link>
                </p>
            </motion.div>
        </div>
    );
}
