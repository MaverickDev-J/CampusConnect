"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useAuth } from "@/app/context/auth-context";
import {
    ArrowRight,
    Sparkles,
    Cpu,
    Database,
    Zap,
    MessageSquare,
    FileText,
    Timer,
    Loader2,
    Github,
    Layers,
    Network,
} from "lucide-react";
import { useState } from "react";

// ── Tech Stack Cards ──────────────────────────────────────────────

const techStack = [
    {
        name: "FastAPI",
        role: "Async API Server",
        icon: Zap,
        color: "from-emerald-400 to-teal-500",
        bg: "bg-emerald-50",
    },
    {
        name: "LangGraph",
        role: "Multi-Agent Pipeline",
        icon: Network,
        color: "from-violet-400 to-purple-500",
        bg: "bg-violet-50",
    },
    {
        name: "Celery",
        role: "Task Queue",
        icon: Layers,
        color: "from-lime-400 to-green-500",
        bg: "bg-lime-50",
    },
    {
        name: "Redis",
        role: "Cache · Broker · PubSub",
        icon: Zap,
        color: "from-red-400 to-rose-500",
        bg: "bg-red-50",
    },
    {
        name: "MongoDB",
        role: "Document Store",
        icon: Database,
        color: "from-green-400 to-emerald-600",
        bg: "bg-green-50",
    },
    {
        name: "ChromaDB",
        role: "Vector Embeddings",
        icon: Cpu,
        color: "from-amber-400 to-orange-500",
        bg: "bg-amber-50",
    },
];

// ── Feature Cards ─────────────────────────────────────────────────

const features = [
    {
        icon: MessageSquare,
        title: "Multi-Agent AI Chat",
        description:
            "6-node LangGraph pipeline with real-time token streaming. Router → Classifier → Retriever → Web Search → Synthesis → Guardrail.",
        accent: "from-indigo-500 to-blue-600",
        badge: "LangGraph",
    },
    {
        icon: FileText,
        title: "3-Tier Document Processing",
        description:
            "Gemini multimodal extraction for tables & diagrams, Docling for structured text, PyMuPDF as bulletproof fallback. Every PDF gets processed.",
        accent: "from-amber-500 to-orange-600",
        badge: "Celery",
    },
    {
        icon: Timer,
        title: "Semantic Caching",
        description:
            "Sub-10ms responses for similar queries via cosine similarity (0.93 threshold). Redis-backed with 24h TTL and per-classroom namespacing.",
        accent: "from-emerald-500 to-teal-600",
        badge: "Redis",
    },
];

// ── Animation Variants ────────────────────────────────────────────

const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: { staggerChildren: 0.08, delayChildren: 0.2 },
    },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

// ── Component ─────────────────────────────────────────────────────

export default function LandingPage() {
    const { demoLogin } = useAuth();
    const [demoLoading, setDemoLoading] = useState(false);

    const handleDemoLogin = async () => {
        setDemoLoading(true);
        try {
            await demoLogin();
        } catch {
            // Error is handled by auth context
        } finally {
            setDemoLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-amber-500/20 overflow-x-hidden">
            {/* ── Background Decorations ─────────────────────────── */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-20%] right-[-10%] w-[60%] h-[60%] bg-amber-500/[0.03] blur-[150px] rounded-full" />
                <div className="absolute bottom-[-20%] left-[-10%] w-[50%] h-[50%] bg-indigo-500/[0.03] blur-[150px] rounded-full" />
            </div>

            {/* ── Header ─────────────────────────────────────────── */}
            <header className="relative z-10 flex items-center justify-between px-8 md:px-16 py-6">
                <div className="flex items-center gap-3">
                    <img
                        src="/brand/logo_full.png"
                        alt="CampusConnect"
                        className="h-10 w-auto object-contain mix-blend-multiply"
                    />
                </div>
                <div className="flex items-center gap-3">
                    <Link
                        href="/login"
                        className="px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest text-slate-500 hover:text-amber-700 hover:bg-amber-50 transition-all"
                    >
                        Sign In
                    </Link>
                    <button
                        onClick={handleDemoLogin}
                        disabled={demoLoading}
                        className="px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest bg-slate-900 text-white hover:bg-slate-800 transition-all disabled:opacity-50"
                    >
                        {demoLoading ? (
                            <Loader2 className="animate-spin" size={14} />
                        ) : (
                            "Try Demo"
                        )}
                    </button>
                </div>
            </header>

            {/* ── Hero Section ────────────────────────────────────── */}
            <motion.section
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                className="relative z-10 max-w-6xl mx-auto px-8 md:px-16 pt-16 md:pt-24 pb-20"
            >
                <motion.div variants={itemVariants} className="text-center max-w-3xl mx-auto">
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-50 border border-amber-200/50 mb-8">
                        <Sparkles size={14} className="text-amber-600" />
                        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-amber-700">
                            AI-Powered Learning Platform
                        </span>
                    </div>

                    <h1 className="text-5xl md:text-7xl font-black tracking-tighter leading-[0.9] mb-6">
                        Intelligent Learning,
                        <br />
                        <span className="bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 bg-clip-text text-transparent">
                            Engineered for Scale
                        </span>
                    </h1>

                    <p className="text-lg md:text-xl text-slate-500 font-medium leading-relaxed max-w-2xl mx-auto mb-12">
                        A distributed, multi-agent classroom platform powered by LangGraph, 
                        Celery, and Redis. Upload documents, ask questions, get AI-synthesized 
                        answers — all in real time.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <motion.button
                            whileHover={{ scale: 1.03 }}
                            whileTap={{ scale: 0.97 }}
                            onClick={handleDemoLogin}
                            disabled={demoLoading}
                            className="btn-accent px-10 py-5 rounded-2xl flex items-center gap-3 text-sm disabled:opacity-50 shadow-xl shadow-amber-200/40"
                        >
                            {demoLoading ? (
                                <Loader2 className="animate-spin" size={20} />
                            ) : (
                                <>
                                    <Sparkles size={20} />
                                    Try Live Demo
                                    <ArrowRight size={20} />
                                </>
                            )}
                        </motion.button>

                        <Link
                            href="/login"
                            className="px-10 py-5 rounded-2xl border-2 border-slate-200 text-sm font-black uppercase tracking-widest text-slate-500 hover:border-slate-300 hover:text-slate-700 transition-all"
                        >
                            Sign In
                        </Link>
                    </div>
                </motion.div>
            </motion.section>

            {/* ── Tech Stack ──────────────────────────────────────── */}
            <motion.section
                variants={containerVariants}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-100px" }}
                className="relative z-10 max-w-6xl mx-auto px-8 md:px-16 py-16"
            >
                <motion.div variants={itemVariants} className="text-center mb-12">
                    <p className="text-[10px] font-black uppercase tracking-[0.3em] text-amber-600 mb-3">
                        Architecture
                    </p>
                    <h2 className="text-3xl md:text-4xl font-black tracking-tighter">
                        Built with Production-Grade Infrastructure
                    </h2>
                </motion.div>

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    {techStack.map((tech, i) => (
                        <motion.div
                            key={tech.name}
                            variants={itemVariants}
                            whileHover={{ y: -4, scale: 1.02 }}
                            className="group relative p-6 rounded-[2rem] bg-white border border-slate-100 shadow-soft hover:shadow-premium transition-all duration-300 text-center"
                        >
                            <div
                                className={`w-12 h-12 rounded-2xl ${tech.bg} flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300`}
                            >
                                <tech.icon size={22} className="text-slate-600" />
                            </div>
                            <div className="text-sm font-black text-slate-900 mb-1">{tech.name}</div>
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider leading-tight">
                                {tech.role}
                            </div>
                        </motion.div>
                    ))}
                </div>
            </motion.section>

            {/* ── Features ────────────────────────────────────────── */}
            <motion.section
                variants={containerVariants}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-100px" }}
                className="relative z-10 max-w-6xl mx-auto px-8 md:px-16 py-16"
            >
                <motion.div variants={itemVariants} className="text-center mb-12">
                    <p className="text-[10px] font-black uppercase tracking-[0.3em] text-amber-600 mb-3">
                        Core Features
                    </p>
                    <h2 className="text-3xl md:text-4xl font-black tracking-tighter">
                        Not Just Another Chat UI
                    </h2>
                </motion.div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {features.map((feature, i) => (
                        <motion.div
                            key={feature.title}
                            variants={itemVariants}
                            whileHover={{ y: -4 }}
                            className="group relative p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-soft hover:shadow-premium transition-all duration-300"
                        >
                            {/* Badge */}
                            <div className="inline-flex items-center px-3 py-1 rounded-full bg-slate-50 border border-slate-100 mb-6">
                                <span className="text-[9px] font-black uppercase tracking-wider text-slate-400">
                                    {feature.badge}
                                </span>
                            </div>

                            <div
                                className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${feature.accent} flex items-center justify-center mb-5 shadow-lg group-hover:scale-110 transition-transform duration-300`}
                            >
                                <feature.icon size={24} className="text-white" />
                            </div>

                            <h3 className="text-xl font-black text-slate-900 tracking-tight mb-3">
                                {feature.title}
                            </h3>
                            <p className="text-sm text-slate-500 font-medium leading-relaxed">
                                {feature.description}
                            </p>
                        </motion.div>
                    ))}
                </div>
            </motion.section>

            {/* ── CTA Section ─────────────────────────────────────── */}
            <motion.section
                variants={containerVariants}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                className="relative z-10 max-w-6xl mx-auto px-8 md:px-16 py-20"
            >
                <motion.div
                    variants={itemVariants}
                    className="relative overflow-hidden rounded-[3rem] bg-slate-900 p-12 md:p-20 text-center"
                >
                    <div className="absolute top-[-50px] right-[-50px] w-64 h-64 bg-amber-500/10 rounded-full blur-[80px]" />
                    <div className="absolute bottom-[-50px] left-[-50px] w-48 h-48 bg-indigo-500/10 rounded-full blur-[80px]" />

                    <div className="relative z-10">
                        <h2 className="text-3xl md:text-5xl font-black tracking-tighter text-white mb-4">
                            See It In Action
                        </h2>
                        <p className="text-lg text-slate-400 font-medium mb-10 max-w-lg mx-auto">
                            No sign up required. Jump straight into a pre-loaded AI classroom 
                            and explore the system architecture through conversation.
                        </p>

                        <motion.button
                            whileHover={{ scale: 1.03 }}
                            whileTap={{ scale: 0.97 }}
                            onClick={handleDemoLogin}
                            disabled={demoLoading}
                            className="inline-flex items-center gap-3 px-10 py-5 rounded-2xl bg-amber-500 text-slate-900 text-sm font-black uppercase tracking-widest shadow-xl shadow-amber-500/30 hover:bg-amber-400 transition-all disabled:opacity-50"
                        >
                            {demoLoading ? (
                                <Loader2 className="animate-spin" size={20} />
                            ) : (
                                <>
                                    <Sparkles size={20} />
                                    Launch Demo
                                    <ArrowRight size={20} />
                                </>
                            )}
                        </motion.button>
                    </div>
                </motion.div>
            </motion.section>

            {/* ── Footer ──────────────────────────────────────────── */}
            <footer className="relative z-10 border-t border-slate-100 py-10 text-center">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                    Built by Jatin &middot; CampusConnect &copy; {new Date().getFullYear()}
                </p>
            </footer>
        </div>
    );
}
