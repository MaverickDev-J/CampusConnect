"use client";

import { use, useEffect, useState, useRef } from "react";
import { useChat } from "@/app/hooks/useChat";
import { useClassroom } from "@/app/hooks/useClassrooms";
import { useAuth } from "@/app/context/auth-context";
import Header from "@/app/components/Header";
import { 
    Send, 
    Bot, 
    User, 
    Loader2, 
    ArrowLeft, 
    BookOpen,
    Plus,
    History,
    ShieldCheck,
    Pencil,
    Trash2,
    LogIn
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Sidebar } from "@/app/components/Sidebar";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export const dynamic = "force-dynamic";

export default function ClassroomChatPage({ params }: { params: Promise<{ id: string }> }) {
    const { id: classroomId } = use(params);
    const { user, isDemo } = useAuth();
    const { classroom } = useClassroom(classroomId);
    const { 
        messages, 
        sendMessage, 
        streaming, 
        status, 
        thoughts,
        sessions, 
        activeSessionId, 
        loadHistory, 
        listSessions,
        setActiveSessionId,
        deleteSession,
        renameSession
    } = useChat();

    const [input, setInput] = useState("");
    const scrollRef = useRef<HTMLDivElement>(null);
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState("");

    const handleRename = async (e: React.FormEvent | React.FocusEvent, sessionId: string) => {
        e.preventDefault();
        e.stopPropagation();
        if (!editTitle.trim() || !user?.token) {
            setEditingSessionId(null);
            return;
        }
        await renameSession(sessionId, editTitle, classroomId);
        setEditingSessionId(null);
    };

    const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
        e.stopPropagation();
        if (confirm("Are you sure you want to permanently delete this AI chat session?")) {
            await deleteSession(sessionId, classroomId);
        }
    };

    useEffect(() => {
        // Skip loading old sessions for demo users — clean slate
        if (classroomId && !isDemo) {
            listSessions(classroomId);
        }
    }, [classroomId, listSessions, isDemo]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTo({
                top: scrollRef.current.scrollHeight,
                behavior: "smooth"
            });
        }
    }, [messages, streaming]);

    const handleSend = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || streaming) return;

        const query = input;
        setInput("");
        await sendMessage(query, classroomId);
    };

    // Dynamic quick prompts — fetched from backend based on actual classroom content
    const [quickPrompts, setQuickPrompts] = useState<{icon: string; text: string; prompt: string}[]>([]);
    const [promptsLoading, setPromptsLoading] = useState(true);

    useEffect(() => {
        const fetchPrompts = async () => {
            try {
                const token = localStorage.getItem("token");
                if (!token) return;
                const res = await fetch(
                    `${require("@/app/config").API_BASE_URL}/api/chat/quick-prompts?classroom_id=${classroomId}`,
                    { headers: { Authorization: `Bearer ${token}` } }
                );
                if (res.ok) {
                    const data = await res.json();
                    setQuickPrompts(data.prompts || []);
                }
            } catch (err) {
                console.warn("Failed to fetch quick prompts:", err);
            } finally {
                setPromptsLoading(false);
            }
        };
        fetchPrompts();
    }, [classroomId]);

    return (
        <div className="h-screen flex overflow-hidden">
            <Sidebar />

            <div className="flex-1 flex flex-col transition-all duration-300 relative h-screen overflow-hidden">

                {/* Back to Classroom Navigation */}
                <div className="px-6 py-2 border-b border-white/40 bg-white/30 backdrop-blur-md flex items-center justify-between gap-4 z-10 shrink-0">
                    <div className="flex items-center gap-4">
                        <Link 
                            href={`/classroom/${classroomId}`} 
                            className="flex items-center gap-2 text-slate-500 hover:text-amber-600 transition-all group py-1"
                        >
                            <div className="w-7 h-7 rounded-lg bg-white border border-slate-100 flex items-center justify-center group-hover:border-amber-600/20 shadow-sm group-hover:shadow transition-all">
                                <ArrowLeft size={14} />
                            </div>
                            <span className="text-[10px] font-black uppercase tracking-[0.2em]">Return to Classroom</span>
                        </Link>
                        <div className="h-4 w-px bg-slate-200" />
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest truncate">AI Learning Assistant</span>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="text-xs font-black text-slate-900 tracking-tight hidden sm:block">Study Assistant</span>
                        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-[9px] text-amber-700 font-black tracking-widest uppercase mr-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" /> Active
                        </div>
                        {isDemo && (
                            <Link
                                href="/login"
                                className="btn-neumorphic-primary px-4 py-1.5 rounded-lg flex items-center justify-center gap-2 text-[10px] font-black uppercase tracking-widest group"
                            >
                                <LogIn size={12} className="group-hover:translate-x-0.5 transition-transform" />
                                Sign Up
                            </Link>
                        )}
                    </div>
                </div>

                <div className="flex-1 flex overflow-hidden">
                    {!isDemo && (
                        <aside className="hidden lg:flex w-64 flex-col glass border-r border-white/40 z-20">
                            <div className="p-4">
                                <button 
                                    onClick={() => {
                                        setActiveSessionId(null);
                                        window.location.reload();
                                    }}
                                    className="btn-neumorphic-primary w-full py-3 rounded-xl flex items-center justify-center gap-2.5 text-xs font-black uppercase tracking-widest group"
                                >
                                    <Plus size={15} className="group-hover:rotate-90 transition-transform" />
                                    New Chat
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto px-3 space-y-1.5 pb-4 custom-scrollbar">
                                <div className="flex items-center gap-2 px-2 pb-2 text-[9px] font-black text-slate-400 uppercase tracking-[0.3em]">
                                    <History size={10} />
                                    Recent Chats
                                </div>
                                {sessions.map(s => (
                                    <div
                                        key={s.session_id}
                                        onClick={() => {
                                            if (editingSessionId !== s.session_id) {
                                                loadHistory(s.session_id);
                                            }
                                        }}
                                        className={`w-full px-3 py-2.5 rounded-xl text-left transition-all relative cursor-pointer group ${
                                            activeSessionId === s.session_id 
                                            ? "bg-amber-50 shadow-sm border border-amber-200 text-amber-900" 
                                            : "text-slate-500 hover:bg-white/50 hover:text-slate-900"
                                        }`}
                                    >
                                        {editingSessionId === s.session_id ? (
                                            <form onSubmit={(e) => handleRename(e, s.session_id)} className="flex items-center">
                                                <input 
                                                    type="text"
                                                    autoFocus
                                                    value={editTitle}
                                                    onChange={e => setEditTitle(e.target.value)}
                                                    onBlur={(e) => handleRename(e, s.session_id)}
                                                    onClick={e => e.stopPropagation()}
                                                    className="w-full bg-white border border-amber-200 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500/10"
                                                />
                                            </form>
                                        ) : (
                                            <>
                                                <div className="text-xs font-bold truncate pr-14 tracking-tight leading-tight">{s.title}</div>
                                                <div className="text-[8px] font-black opacity-40 mt-1 uppercase tracking-widest">
                                                    {new Date(s.updated_at).toLocaleDateString()}
                                                </div>
                                                
                                                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button 
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setEditTitle(s.title);
                                                            setEditingSessionId(s.session_id);
                                                        }}
                                                        className="w-6 h-6 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400 hover:text-amber-600 transition-colors"
                                                    >
                                                        <Pencil size={10} />
                                                    </button>
                                                    <button 
                                                        onClick={(e) => handleDelete(e, s.session_id)}
                                                        className="w-6 h-6 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400 hover:text-red-500 transition-colors"
                                                    >
                                                        <Trash2 size={10} />
                                                    </button>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </aside>
                    )}

                    <main className="flex-1 flex flex-col relative h-full overflow-hidden bg-slate-50/50">

                        <div 
                            ref={scrollRef}
                            className="flex-1 overflow-y-auto px-6 md:px-10 py-8 space-y-6 scroll-smooth relative custom-scrollbar"
                        >
                            {!activeSessionId && messages.length === 0 && (
                                <div className="h-full flex flex-col items-center justify-center text-center px-4 max-w-3xl mx-auto py-2 relative overflow-hidden">
                                    <motion.div 
                                        initial={{ opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        className="w-full h-full flex flex-col items-center justify-center"
                                    >
                                        <div className="w-12 h-12 rounded-2xl bg-amber-500 flex items-center justify-center mb-3 mx-auto text-slate-900 shadow-2xl shadow-amber-500/30 relative shrink-0">
                                            <Bot size={24} />
                                            <div className="absolute inset-0 bg-amber-400 blur-3xl opacity-20 -z-10" />
                                        </div>
                                        <h3 className="text-2xl md:text-3xl font-black text-slate-900 mb-2 tracking-tighter leading-[0.9] shrink-0">
                                            Welcome to your<br/><span className="text-amber-600 italic">study space.</span>
                                        </h3>
                                        <p className="text-slate-500 font-medium text-sm mb-5 max-w-md mx-auto shrink-0 leading-snug">
                                            I've processed all materials in <span className="text-amber-600 font-bold">{classroom?.name}</span>. 
                                            How can I help you study today?
                                        </p>
                                        {promptsLoading ? (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-left w-full overflow-hidden shrink">
                                                {[1,2,3,4].map(i => (
                                                    <div key={i} className="p-4 rounded-xl bg-white border border-slate-100 animate-pulse">
                                                        <div className="h-3 bg-slate-100 rounded w-3/4 mb-2" />
                                                        <div className="h-2 bg-slate-50 rounded w-full" />
                                                    </div>
                                                ))}
                                            </div>
                                        ) : quickPrompts.length > 0 ? (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-left w-full overflow-hidden shrink">
                                                {quickPrompts.map((p, i) => (
                                                <motion.button
                                                    key={i}
                                                    initial={{ opacity: 0, y: 15 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.2 + (i * 0.1) }}
                                                    onClick={() => setInput(p.prompt)}
                                                    className="p-4 rounded-xl bg-white border border-slate-100 hover:border-amber-600/30 hover:shadow-premium transition-all group relative overflow-hidden"
                                                >
                                                    <div className="absolute top-0 right-0 p-2 opacity-5 group-hover:opacity-10 transition-opacity">
                                                        <span className="text-3xl">{p.icon}</span>
                                                    </div>
                                                    <div className="relative z-10">
                                                        <div className="font-black text-slate-900 text-xs group-hover:text-amber-600 transition-colors tracking-tight mb-0.5">{p.text}</div>
                                                        <div className="text-[9px] text-slate-400 font-medium italic line-clamp-1 opacity-60 group-hover:opacity-100 transition-opacity">"{p.prompt}"</div>
                                                    </div>
                                                </motion.button>
                                            ))}
                                        </div>
                                        ) : null}
                                    </motion.div>
                                </div>
                            )}

                            {messages.map((msg, idx) => (
                                <motion.div 
                                    key={msg.id || idx}
                                    initial={{ opacity: 0, y: 15 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                                >
                                    <div className={`flex gap-3 max-w-[85%] ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                                        <div className={`w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center shadow-md transition-transform hover:scale-105 duration-300 ${
                                            msg.role === "user" 
                                            ? "bg-white text-slate-600 border border-slate-100" 
                                            : "bg-indigo-600 text-white shadow-indigo-600/20"
                                        }`}>
                                            {msg.role === "user" ? <User size={16} /> : <Bot size={18} />}
                                        </div>
                                        <div className={`space-y-2 ${msg.role === "user" ? "text-right" : "text-left"}`}>
                                            <div className={`inline-block px-5 py-3.5 rounded-2xl shadow-sm leading-relaxed text-sm tracking-tight ${
                                                msg.role === "user" 
                                                ? "bg-slate-900 text-white rounded-tr-sm font-semibold" 
                                                : "bg-white border border-slate-100 text-slate-800 rounded-tl-sm font-medium"
                                            }`}>
                                                {msg.role === "user" ? msg.content : (
                                                    <div className="markdown-content">
                                                        <ReactMarkdown 
                                                            remarkPlugins={[remarkMath]}
                                                            rehypePlugins={[rehypeKatex]}
                                                            components={{
                                                                p: ({ children }: any) => <p className="leading-relaxed mb-3 last:mb-0">{children}</p>,
                                                                strong: ({ children }: any) => <strong className="text-amber-900 font-black tracking-tight">{children}</strong>,
                                                                ul: ({ children }: any) => <ul className="space-y-2 my-3">{children}</ul>,
                                                                li: ({ children }: any) => (
                                                                    <li className="flex gap-2 items-start">
                                                                        <span className="text-indigo-600 font-black mt-0.5 text-sm leading-none">•</span>
                                                                        <span className="flex-1">{children}</span>
                                                                    </li>
                                                                ),
                                                                h1: ({ children }: any) => <h1 className="text-2xl font-black text-amber-900 mt-6 mb-4 tracking-tighter">{children}</h1>,
                                                                h2: ({ children }: any) => <h2 className="text-xl font-black text-amber-900 mt-5 mb-3 tracking-tighter">{children}</h2>,
                                                                h3: ({ children }: any) => <h3 className="text-lg font-black text-amber-900 mt-4 mb-2 tracking-tight">{children}</h3>,
                                                                code: ({ children }: any) => <code className="bg-slate-100 rounded-md px-1.5 py-0.5 font-mono text-xs text-amber-700">{children}</code>,
                                                                pre: ({ children }: any) => <pre className="bg-slate-950 text-white p-4 rounded-xl overflow-x-auto my-4 shadow-premium text-xs">{children}</pre>,
                                                            }}
                                                        >
                                                            {msg.content}
                                                        </ReactMarkdown>
                                                    </div>
                                                )}
                                            </div>
                                            
                                            {msg.sources && msg.sources.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5 mt-2 justify-start">
                                                    {msg.sources.map((s, i) => (
                                                        <motion.div 
                                                            key={i}
                                                            whileHover={{ scale: 1.05 }}
                                                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white border border-slate-100 text-[10px] font-black text-slate-500 hover:text-amber-600 hover:border-amber-600/20 transition-all shadow-sm cursor-default"
                                                        >
                                                            <BookOpen size={11} className="text-amber-600" />
                                                            <span>{s.file_name}</span>
                                                            <span className="bg-amber-50 px-1.5 py-0.5 rounded text-[9px] text-amber-600">PG {s.page_number}</span>
                                                        </motion.div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </motion.div>
                            ))}

                            {streaming && (status || thoughts.length > 0) && (
                                <div className="flex flex-col gap-3 pl-11 max-w-2xl">
                                    <AnimatePresence mode="popLayout">
                                        {thoughts.map((thought, i) => (
                                            <motion.div
                                                key={`thought-${i}`}
                                                initial={{ opacity: 0, x: -15, scale: 0.95 }}
                                                animate={{ opacity: 1, x: 0, scale: 1 }}
                                                exit={{ opacity: 0, scale: 0.9 }}
                                                className="flex items-center gap-3 px-4 py-2 rounded-xl bg-white/40 border border-white/60 shadow-sm backdrop-blur-sm"
                                            >
                                                <div className="w-1.5 h-1.5 rounded-full bg-amber-500/40 animate-pulse" />
                                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">{thought}</span>
                                            </motion.div>
                                        ))}
                                    </AnimatePresence>

                                    {status && (
                                        <motion.div 
                                            initial={{ opacity: 0, y: 8 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="flex items-center gap-3 px-5 py-3 rounded-2xl bg-white border border-slate-100 shadow-sm"
                                        >
                                            <div className="relative">
                                                <Loader2 size={16} className="animate-spin text-amber-600" />
                                                <div className="absolute inset-0 bg-amber-500/20 blur-lg animate-pulse" />
                                            </div>
                                            <span className="text-[10px] font-black text-amber-600 uppercase tracking-[0.2em]">{status}</span>
                                            <div className="flex gap-1 ml-2">
                                                {[1, 2, 3].map(i => (
                                                    <motion.div 
                                                        key={i}
                                                        animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.2, 1] }}
                                                        transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }}
                                                        className="w-1 h-1 rounded-full bg-amber-500"
                                                    />
                                                ))}
                                            </div>
                                        </motion.div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Compact centered input bar */}
                        <div className="px-6 pb-5 pt-3 shrink-0 relative">
                            <form 
                                onSubmit={handleSend}
                                className="max-w-2xl mx-auto relative group"
                            >
                                <div className="absolute inset-0 bg-amber-500/5 rounded-2xl blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
                                <div className="relative flex items-center glass rounded-2xl border-white/40 shadow-sm overflow-hidden focus-within:border-amber-600/20 focus-within:shadow-premium transition-all">
                                    <input 
                                        type="text" 
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        placeholder="Ask anything about this classroom..."
                                        disabled={streaming}
                                        className="w-full bg-transparent text-slate-900 pl-5 pr-14 py-4 focus:outline-none placeholder:text-slate-400 font-semibold text-sm"
                                    />
                                    <div className="absolute right-2">
                                        <button 
                                            type="submit"
                                            disabled={!input.trim() || streaming}
                                            className="w-9 h-9 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-900 shadow-lg shadow-amber-500/20 transition-all active:scale-90 flex items-center justify-center disabled:opacity-30 disabled:grayscale"
                                        >
                                            {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                                        </button>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </main>
                </div>
            </div>
        </div>
    );
}
