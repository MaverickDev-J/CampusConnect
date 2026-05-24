"use client";

import { useAuth } from "@/app/context/auth-context";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import Link from "next/link";
import { motion } from "framer-motion";
import {
    BookOpen,
    MessageSquare,
    ArrowRight,
    Users,
    Zap,
    Plus,
} from "lucide-react";

import { ClassroomCard } from "@/app/components/ClassroomCard";

export default function HomePage() {
    const { user } = useAuth();
    const { classrooms, loading } = useClassrooms();

    const recentClassrooms = classrooms.slice(0, 4);
    const isTeacher = user?.role === "teacher" || user?.role === "superadmin";

    const greeting = () => {
        const hour = new Date().getHours();
        if (hour < 12) return "Good morning";
        if (hour < 17) return "Good afternoon";
        return "Good evening";
    };

    return (
        <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300">
                <Header />

                <div className="max-w-[1400px] mx-auto px-8 py-10">
                    {/* Bento Grid Layout */}
                    <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-6">
                        
                        {/* 1. Large Welcome Hero (Bento: 4x2) */}
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="md:col-span-4 lg:col-span-4 row-span-2 relative overflow-hidden rounded-[2.5rem] bg-primary p-12 text-white shadow-2xl shadow-primary/20"
                        >
                            <div className="relative z-10 h-full flex flex-col justify-between">
                                <div>
                                    <motion.p 
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.2 }}
                                        className="text-white/60 font-black text-sm uppercase tracking-[0.3em] mb-4"
                                    >
                                        {greeting()}
                                    </motion.p>
                                    <motion.h1 
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.3 }}
                                        className="text-6xl font-black tracking-tighter mb-6 leading-[0.9]"
                                    >
                                        Welcome back,<br/>
                                        <span className="text-white/80">{user?.name?.split(" ")[0]}</span>
                                    </motion.h1>
                                    <motion.p 
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        transition={{ delay: 0.4 }}
                                        className="text-white/70 text-lg font-medium max-w-md leading-relaxed"
                                    >
                                        {isTeacher
                                            ? "Your academic command center is ready. Manage your classrooms and student progress with ease."
                                            : `You have ${classrooms.length} active classrooms. Ready to explore your AI-powered Classroom Connect environment?`}
                                    </motion.p>
                                </div>
                                
                                <motion.div 
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.5 }}
                                    className="pt-10"
                                >
                                    <Link href="/classrooms" className="inline-flex items-center gap-3 px-8 py-4 bg-white text-primary rounded-2xl font-black text-sm shadow-xl hover:scale-105 transition-transform group">
                                        View All Classrooms <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                                    </Link>
                                </motion.div>
                            </div>

                            {/* Decorative Elements */}
                            <div className="absolute top-[-100px] right-[-100px] w-80 h-80 bg-white/10 rounded-full blur-[100px]" />
                            <div className="absolute bottom-[-50px] left-[-50px] w-64 h-64 bg-black/10 rounded-full blur-[60px]" />
                            <BookOpen className="absolute right-[-20px] bottom-[-20px] w-64 h-64 text-white/5 -rotate-12" />
                        </motion.div>

                        {/* 2. Quick Stats (Bento Side Column) */}
                        <div className="md:col-span-2 lg:col-span-2 grid grid-cols-1 gap-6">
                            {[
                                { label: "Total Members", value: classrooms.reduce((acc, curr) => acc + (curr.member_count || 0), 0), icon: Users, color: "bg-amber-100 text-amber-600" },
                                { label: "Active Classrooms", value: classrooms.length, icon: Zap, color: "bg-emerald-100 text-emerald-600" },
                            ].map((stat, i) => (
                                <motion.div 
                                    key={stat.label}
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.2 + (i * 0.1) }}
                                    className="p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-soft flex items-center gap-6"
                                >
                                    <div className={`w-16 h-16 rounded-2xl flex items-center justify-center flex-shrink-0 ${stat.color} shadow-sm shadow-inherit`}>
                                        <stat.icon size={28} />
                                    </div>
                                    <div>
                                        <div className="text-3xl font-black text-slate-900 tracking-tight leading-none mb-1">{stat.value}</div>
                                        <div className="text-[10px] text-slate-400 font-black uppercase tracking-widest">{stat.label}</div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>

                        {/* Recent Activity Section Removed as per request */}

                        {/* 4. Classroom Stream (Bento: Full Width Row) */}
                        <div className="md:col-span-6 lg:col-span-6 pt-10">
                            <div className="flex items-center justify-between mb-8">
                                <motion.h2 
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="text-4xl font-black text-slate-900 tracking-tighter"
                                >
                                    My Classrooms
                                </motion.h2>
                                <motion.div 
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                >
                                    <Link href="/classrooms" className="text-primary font-black text-xs uppercase tracking-widest hover:bg-primary/5 px-6 py-3 rounded-2xl border border-primary/10 transition-all">Explore All</Link>
                                </motion.div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                {loading ? (
                                    [1, 2, 3, 4].map(i => (
                                        <div key={i} className="h-64 rounded-[2.5rem] bg-white border border-slate-100 animate-pulse" />
                                    ))
                                ) : recentClassrooms.length === 0 ? (
                                    <div className="col-span-full p-20 glass rounded-[3rem] text-center">
                                        <div className="w-20 h-20 bg-primary/5 text-primary rounded-3xl flex items-center justify-center mx-auto mb-6">
                                            <BookOpen size={40} />
                                        </div>
                                        <h3 className="text-xl font-black text-slate-900 mb-2">Get Started</h3>
                                        <p className="text-slate-500 font-medium mb-8">Ready to create or join your first classroom?</p>
                                        <Link href="/classrooms" className="inline-flex items-center gap-3 px-8 py-4 bg-primary text-white rounded-2xl font-black text-sm shadow-xl shadow-primary/20 hover:scale-105 transition-all">
                                            <Plus size={18} /> {isTeacher ? "Create Class" : "Join Class"}
                                        </Link>
                                    </div>
                                ) : (
                                    recentClassrooms.map((cls, i) => (
                                        <motion.div
                                            key={cls.classroom_id}
                                            initial={{ opacity: 0, y: 20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.7 + (i * 0.1) }}
                                        >
                                            <ClassroomCard classroom={cls} />
                                        </motion.div>
                                    ))
                                )}
                            </div>
                        </div>

                    </div>
                </div>
            </main>
        </div>
    );
}
