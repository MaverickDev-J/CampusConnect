"use client";

import { useClassrooms } from "@/app/hooks/useClassrooms";
import { useAuth } from "@/app/context/auth-context";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import { ClassroomCard } from "@/app/components/ClassroomCard";
import { motion, AnimatePresence } from "framer-motion";
import {
    BookOpen,
    Plus,
    UserPlus,
    X,
    Search,
    Loader2
} from "lucide-react";
import confetti from "canvas-confetti";

export default function ClassroomsPage() {
    const { user } = useAuth();
    const { classrooms, loading, createClassroom, joinClassroom } = useClassrooms();
    const [showCreate, setShowCreate] = useState(false);
    const [showJoin, setShowJoin] = useState(false);
    const [joinCode, setJoinCode] = useState("");
    const [joinLoading, setJoinLoading] = useState(false);
    const [joinError, setJoinError] = useState("");
    const [createData, setCreateData] = useState({ name: "", subject: "" });
    const [createLoading, setCreateLoading] = useState(false);
    const [createError, setCreateError] = useState("");
    const [search, setSearch] = useState("");
    
    const searchParams = useSearchParams();

    useEffect(() => {
        const q = searchParams.get("q");
        if (q !== null) setSearch(q);
    }, [searchParams]);

    const isTeacher = user?.role === "teacher" || user?.role === "superadmin";

    const filtered = classrooms.filter(c =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        (c.subject || "").toLowerCase().includes(search.toLowerCase())
    );

    const fireConfetti = () => {
        confetti({
            particleCount: 150,
            spread: 70,
            origin: { y: 0.6 },
            colors: ["#0066FF", "#FFB800", "#10b981"]
        });
    };

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreateLoading(true);
        setCreateError("");
        try {
            await createClassroom(createData);
            setShowCreate(false);
            setCreateData({ name: "", subject: "" });
            fireConfetti();
        } catch (err) {
            setCreateError(err instanceof Error ? err.message : "Failed to create");
        } finally {
            setCreateLoading(false);
        }
    };

    const handleJoin = async (e: React.FormEvent) => {
        e.preventDefault();
        setJoinLoading(true);
        setJoinError("");
        try {
            await joinClassroom(joinCode.trim().toUpperCase());
            setShowJoin(false);
            setJoinCode("");
            fireConfetti();
        } catch (err) {
            setJoinError(err instanceof Error ? err.message : "Invalid code");
        } finally {
            setJoinLoading(false);
        }
    };

    return (
        <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300">
                <Header />

                <div className="max-w-7xl mx-auto px-10 py-12">
                    {/* Header Section */}
                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 mb-12">
                        <div>
                            <motion.h1 
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="text-5xl font-black text-slate-900 tracking-tighter mb-2"
                            >
                                Your Learning Hubs
                            </motion.h1>
                            <motion.p 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.1 }}
                                className="text-slate-400 font-black uppercase tracking-[0.2em] text-xs"
                            >
                                {classrooms.length} Classroom{classrooms.length !== 1 ? "s" : ""} Connected
                            </motion.p>
                        </div>
                        
                        <div className="flex flex-wrap items-center gap-4">
                            <div className="relative group">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-primary transition-colors" />
                                <input
                                    type="text"
                                    placeholder="Filter by name or subject..."
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    className="pl-12 pr-6 py-3.5 text-sm bg-white border border-slate-200 rounded-2xl focus:outline-none focus:ring-4 focus:ring-primary/5 focus:border-primary/20 transition-all font-semibold w-72 shadow-soft"
                                />
                            </div>
                            
                            <button
                                onClick={() => setShowJoin(true)}
                                className="btn-neumorphic px-6 py-3.5 rounded-2xl text-slate-600 font-black text-sm flex items-center gap-2"
                            >
                                <UserPlus size={18} /> Join Hub
                            </button>
                            
                            {isTeacher && (
                                <button
                                    onClick={() => setShowCreate(true)}
                                    className="btn-neumorphic-primary px-8 py-3.5 rounded-2xl font-black text-sm flex items-center gap-2"
                                >
                                    <Plus size={20} /> Create New
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Classrooms Grid */}
                    {loading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
                            {[1, 2, 3, 4, 5, 6].map(i => (
                                <div key={i} className="h-72 rounded-[2.5rem] bg-white border border-slate-100 animate-pulse" />
                            ))}
                        </div>
                    ) : filtered.length === 0 ? (
                        <motion.div 
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="flex flex-col items-center justify-center p-24 rounded-[3rem] glass border border-white/40 text-center shadow-premium"
                        >
                            <div className="w-24 h-24 bg-primary/5 text-primary rounded-[2rem] flex items-center justify-center mb-8 shadow-inner">
                                <BookOpen size={48} />
                            </div>
                            <h3 className="text-2xl font-black text-slate-900 mb-3 tracking-tight">
                                {search ? "Quiet Classroom" : "Begin Your Journey"}
                            </h3>
                            <p className="text-slate-500 font-medium max-w-sm mx-auto leading-relaxed">
                                {search ? `No results for "${search}". Try adjusting your filters.` : isTeacher ? "Initialize your first classroom node to begin managing student success." : "Join your academic circles using the access codes provided by instructors."}
                            </p>
                        </motion.div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
                            {filtered.map((cls, i) => (
                                <motion.div
                                    key={cls.classroom_id}
                                    initial={{ opacity: 0, y: 30 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: i * 0.05, type: "spring", damping: 15 }}
                                >
                                    <ClassroomCard classroom={cls} />
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </main>

            {/* Modals with Premium Redesign */}
            <AnimatePresence>
                {(showCreate || showJoin) && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center z-50 p-6"
                        onClick={() => { setShowCreate(false); setShowJoin(false); }}
                    >
                        <motion.div
                            initial={{ scale: 0.9, y: 40, rotateX: 15 }}
                            animate={{ scale: 1, y: 0, rotateX: 0 }}
                            exit={{ scale: 0.9, y: 40, rotateX: 15 }}
                            onClick={e => e.stopPropagation()}
                            className="glass-dark rounded-[3rem] p-10 w-full max-w-xl shadow-premium border-white/10 relative overflow-hidden"
                        >
                            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/20 blur-[60px] rounded-full -translate-y-1/2 translate-x-1/2" />
                            
                            <div className="flex items-center justify-between mb-10 relative z-10">
                                <div>
                                    <h2 className="text-3xl font-black text-white tracking-tighter">
                                        {showCreate ? "Create Hub" : "Join Network"}
                                    </h2>
                                    <p className="text-white/40 font-bold text-[10px] uppercase tracking-[0.3em] mt-1">Classroom Integration</p>
                                </div>
                                <button 
                                    onClick={() => { setShowCreate(false); setShowJoin(false); }} 
                                    className="w-12 h-12 rounded-2xl bg-white/5 hover:bg-white/10 text-white/40 hover:text-white transition-all flex items-center justify-center border border-white/5"
                                >
                                    <X size={24} />
                                </button>
                            </div>

                            {showCreate ? (
                                <form onSubmit={handleCreate} className="space-y-6 relative z-10">
                                    {[
                                        { label: "Classroom Name", key: "name", placeholder: "e.g. Advanced AI Synthesis" },
                                        { label: "Core Subject", key: "subject", placeholder: "e.g. Computer Science" },
                                    ].map(field => (
                                        <div key={field.key}>
                                            <label className="block text-[10px] font-black text-white/30 uppercase tracking-[0.2em] mb-3 ml-1">{field.label}</label>
                                            <input
                                                type="text"
                                                placeholder={field.placeholder}
                                                value={(createData as any)[field.key]}
                                                onChange={e => setCreateData(prev => ({ ...prev, [field.key]: e.target.value }))}
                                                required={field.key === "name"}
                                                className="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:ring-4 focus:ring-primary/10 focus:border-primary/40 transition-all font-semibold"
                                            />
                                        </div>
                                    ))}
                                    {createError && <p className="text-rose-400 text-sm font-bold bg-rose-400/10 p-4 rounded-2xl border border-rose-400/20">{createError}</p>}
                                    <button
                                        type="submit"
                                        disabled={createLoading || !createData.name}
                                        className="w-full py-5 rounded-[2rem] bg-primary text-white font-black text-lg hover:bg-blue-600 transition-all shadow-xl shadow-primary/20 flex items-center justify-center gap-3 disabled:opacity-50 mt-4 h-16"
                                    >
                                        {createLoading ? <Loader2 size={24} className="animate-spin" /> : <Plus size={24} />}
                                        {createLoading ? "Creating..." : "Create Classroom"}
                                    </button>
                                </form>
                            ) : (
                                <form onSubmit={handleJoin} className="space-y-8 relative z-10">
                                    <div className="text-center">
                                        <label className="block text-[10px] font-black text-white/30 uppercase tracking-[0.2em] mb-6">Enter Access Protocol</label>
                                        <input
                                            type="text"
                                            placeholder="XXXX XXXX"
                                            value={joinCode}
                                            onChange={e => setJoinCode(e.target.value.toUpperCase())}
                                            maxLength={10}
                                            className="w-full bg-transparent border-none text-white text-center text-5xl font-black tracking-[0.5em] focus:outline-none placeholder:text-white/10 uppercase"
                                        />
                                        <div className="h-px w-full bg-gradient-to-r from-transparent via-white/20 to-transparent mt-4" />
                                    </div>
                                    {joinError && <p className="text-rose-400 text-sm font-bold bg-rose-400/10 p-4 rounded-2xl border border-rose-400/20 text-center">{joinError}</p>}
                                    <button
                                        type="submit"
                                        disabled={joinLoading || joinCode.length < 4}
                                        className="w-full py-5 rounded-[2rem] bg-white text-slate-900 font-black text-lg hover:bg-slate-50 transition-all shadow-xl flex items-center justify-center gap-3 disabled:opacity-50 h-16"
                                    >
                                        {joinLoading ? <Loader2 size={24} className="animate-spin" /> : <UserPlus size={24} />}
                                        {joinLoading ? "Connecting..." : "Connect to Classroom"}
                                    </button>
                                </form>
                            )}
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
