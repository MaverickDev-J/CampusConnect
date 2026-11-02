"use client";

import { useAuth } from "@/app/context/auth-context";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import DemoBanner from "@/app/components/DemoBanner";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion } from "framer-motion";
import {
    BookOpen,
    MessageSquare,
    ArrowRight,
    Users,
    Zap,
    Plus,
    Loader2,
} from "lucide-react";

import { ClassroomCard } from "@/app/components/ClassroomCard";

const LandingPage = dynamic(() => import("@/app/landing/page"));

// ── Smart Root Page ─────────────────────────────────────────────────
// Unauthenticated users → landing page
// Authenticated users → dashboard

export default function RootPage() {
    const { user, loading, isDemo } = useAuth();

    // Show a minimal loading state while auth is hydrating
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-slate-50">
                <Loader2 className="animate-spin text-blue-500" size={32} />
            </div>
        );
    }

    // Not logged in → show the landing page
    if (!user) {
        return <LandingPage />;
    }

    // Logged in → show the dashboard
    return <DashboardPage isDemo={isDemo} />;
}


// ── Dashboard (previously the entire page.tsx) ──────────────────────

function DashboardPage({ isDemo }: { isDemo: boolean }) {
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
            <main className="flex-1 transition-all duration-300">
                <Header />
                {isDemo && <DemoBanner />}

                <div className="max-w-[1400px] mx-auto px-4 md:px-8 py-6 md:py-10">
                    {/* Bento Grid Layout */}
                    <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-4 md:gap-6">
                        
                        {/* 1. Large Welcome Hero (Bento: 4x2) */}
                        <motion.div
                            initial={false}
                            animate={{ opacity: 1, scale: 1 }}
                            className="md:col-span-4 lg:col-span-4 row-span-2 relative overflow-hidden rounded-3xl md:rounded-[2.5rem] bg-primary p-6 md:p-9 text-white"
                        >
                            <div className="relative z-10 h-full flex flex-col justify-between">
                                <div>
                                    <motion.p 
                                        initial={false}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.2 }}
                                        className="text-white/80 text-sm font-medium mb-3"
                                    >
                                        {greeting()}
                                    </motion.p>
                                    <motion.h1 
                                        initial={false}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.3 }}
                                        className="text-3xl md:text-4xl font-black tracking-tighter mb-6 leading-tight"
                                    >
                                        Welcome back,<br/>
                                        <span className="text-white/80">{user?.name?.split(" ")[0]}</span>
                                    </motion.h1>
                                    <motion.p 
                                        initial={false}
                                        animate={{ opacity: 1 }}
                                        transition={{ delay: 0.4 }}
                                        className="text-white/90 text-sm md:text-lg font-medium max-w-md leading-relaxed"
                                    >
                                        {isTeacher
                                            ? "Manage your classes, materials, and upcoming sessions."
                                            : `You have ${classrooms.length} active classrooms. Choose a classroom to review materials or continue studying.`}
                                    </motion.p>
                                </div>
                                
                                <motion.div 
                                    initial={false}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.5 }}
                                    className="pt-6 md:pt-10"
                                >
                                    <Link href="/classrooms" className="inline-flex items-center gap-3 px-6 md:px-8 py-3 md:py-4 bg-white text-primary rounded-xl md:rounded-2xl font-black text-xs md:text-sm shadow-sm hover:bg-slate-50 transition-colors group">
                                        View All Classrooms <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                                    </Link>
                                </motion.div>
                            </div>

                            {/* Decorative Elements */}


                            <BookOpen className="absolute right-[-20px] bottom-[-20px] w-64 h-64 text-white/5 -rotate-12" />
                        </motion.div>

                        {/* 2. Quick Stats (Bento Side Column) */}
                        <div className="md:col-span-2 lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-1 gap-4 md:gap-6">
                            {[
                                { label: "Total Members", value: classrooms.reduce((acc, curr) => acc + (curr.member_count || 0), 0), icon: Users, color: "bg-blue-100 text-blue-600" },
                                { label: "Active Classrooms", value: classrooms.length, icon: Zap, color: "bg-emerald-100 text-emerald-600" },
                            ].map((stat, i) => (
                                <motion.div 
                                    key={stat.label}
                                    initial={false}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.2 + (i * 0.1) }}
                                    className="p-6 md:p-8 rounded-2xl md:rounded-[2.5rem] bg-white border border-slate-100 shadow-soft flex items-center gap-4 md:gap-6"
                                >
                                    <div className={`w-12 h-12 md:w-16 md:h-16 rounded-xl md:rounded-2xl flex items-center justify-center flex-shrink-0 ${stat.color} shadow-sm shadow-inherit`}>
                                        <stat.icon size={24} className="md:w-7 md:h-7" />
                                    </div>
                                    <div>
                                        <div className="text-2xl md:text-3xl font-black text-slate-900 tracking-tight leading-none mb-1">{stat.value}</div>
                                        <div className="text-[9px] md:text-[10px] text-slate-400 font-black uppercase tracking-widest">{stat.label}</div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>

                        {/* Recent Activity Section Removed as per request */}

                        {/* 4. Classroom Stream (Bento: Full Width Row) */}
                        <div className="md:col-span-6 lg:col-span-6 pt-6 md:pt-10">
                            <div className="flex items-center justify-between mb-6 md:mb-8">
                                <motion.h2 
                                    initial={false}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="text-2xl md:text-3xl font-semibold text-slate-900 tracking-tighter"
                                >
                                    My Classrooms
                                </motion.h2>
                                <motion.div 
                                    initial={false}
                                    animate={{ opacity: 1, x: 0 }}
                                >
                                    <Link href="/classrooms" className="text-primary font-black text-[10px] md:text-xs uppercase tracking-widest hover:bg-primary/5 px-4 md:px-6 py-2 md:py-3 rounded-xl md:rounded-2xl border border-primary/10 transition-all">Explore All</Link>
                                </motion.div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
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
                                            initial={false}
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
