"use client";

import { use, useEffect, useState, useRef, memo } from "react";
import { useChat } from "@/app/hooks/useChat";
import { useClassroom } from "@/app/hooks/useClassrooms";
import { useAuth } from "@/app/context/auth-context";
import ThemeToggle from "@/app/components/ThemeToggle";
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
    LogIn,
    X
} from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Sidebar } from "@/app/components/Sidebar";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export const dynamic = "force-dynamic";

const ChatMarkdown = memo(function ChatMarkdown({ content }: { content: string }) {
    return <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{
        table: ({ children }) => <div role="region" aria-label="Answer table" tabIndex={0} className="my-4 max-w-full overflow-x-auto rounded-xl border border-slate-200"><table className="w-full min-w-[24rem] border-collapse text-left text-sm leading-6">{children}</table></div>,
        thead: ({ children }) => <thead className="border-b border-slate-200 bg-slate-50 text-slate-900">{children}</thead>,
        tbody: ({ children }) => <tbody className="divide-y divide-slate-100">{children}</tbody>,
        th: ({ children, style }) => <th scope="col" style={style} className="min-w-[9rem] px-4 py-3 align-top font-semibold">{children}</th>,
        td: ({ children, style }) => <td style={style} className="min-w-[9rem] whitespace-normal break-words px-4 py-3 align-top">{children}</td>,
        p: ({ children }) => <p className="mb-3 leading-7 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
        ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5 marker:text-primary">{children}</ul>,
        ol: ({ children, start }) => <ol start={start} className="my-3 list-decimal space-y-1.5 pl-5 marker:text-primary">{children}</ol>,
        li: ({ children }) => <li className="pl-1 leading-7">{children}</li>,
        h1: ({ children }) => <h1 className="mb-3 mt-5 text-xl font-semibold text-slate-900">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold text-slate-900">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold text-slate-900">{children}</h3>,
        code: ({ children, className }) => <code className={`rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-blue-700 ${className || ""}`}>{children}</code>,
        pre: ({ children }) => <pre className="my-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm text-white [&>code]:block [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-white">{children}</pre>,
    }}>{content}</ReactMarkdown>;
});

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
    const followLatest = useRef(true);
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState("");
    const [isOpenMobileHistory, setIsOpenMobileHistory] = useState(false);

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
        const frame = requestAnimationFrame(() => {
            if (scrollRef.current && followLatest.current) {
                scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: streaming ? "auto" : "smooth" });
            }
        });
        return () => cancelAnimationFrame(frame);
    }, [messages, streaming]);

    const handleSend = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || streaming) return;

        followLatest.current = true;
        const query = input;
        setInput("");
        await sendMessage(query, classroomId);
    };

    // Dynamic quick prompts — fetched from backend based on actual classroom content
    const [quickPrompts, setQuickPrompts] = useState<{icon: string; text: string; prompt: string}[]>([]);
    const [promptsLoading, setPromptsLoading] = useState(true);

    useEffect(() => {
        const fetchPrompts = async () => {
            const token = user?.token;
            if (!token) return;
            try {
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
    }, [classroomId, user?.token]);

    return (
        <div className="h-screen flex overflow-hidden">
            <Sidebar />

            <div className="min-w-0 flex-1 flex flex-col relative h-screen overflow-hidden">

                {/* Back to Classroom Navigation */}
                <div className="px-4 md:px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between gap-2 z-10 shrink-0">
                    <div className="flex items-center gap-4">
                        <Link 
                            href={`/classroom/${classroomId}`} 
                            className="flex items-center gap-2 text-slate-500 hover:text-blue-600 transition-all group py-1"
                        >
                            <div className="w-7 h-7 rounded-lg bg-white border border-slate-100 flex items-center justify-center group-hover:border-blue-600/20 shadow-sm group-hover:shadow transition-all">
                                <ArrowLeft size={14} />
                            </div>
                            <span className="text-xs font-medium">Classroom</span>
                        </Link>
                        <div className="h-4 w-px bg-slate-200" />
                        <span className="hidden md:block text-xs font-medium text-slate-500 truncate">Study chat</span>
                    </div>

                    <div className="flex items-center gap-2.5">
                        {/* Mobile Sessions Toggle Button */}
                        {!isDemo && (
                            <button
                                onClick={() => setIsOpenMobileHistory(true)}
                                className="lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-100 text-[10px] font-black uppercase tracking-widest hover:text-blue-600 transition-colors shadow-sm"
                            >
                                <History size={12} />
                                <span>Chats</span>
                            </button>
                        )}
                        <ThemeToggle />
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
                                    <Plus size={15} className="" />
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
                                                followLatest.current = true;
                                                loadHistory(s.session_id);
                                            }
                                        }}
                                        className={`w-full px-3 py-2.5 rounded-xl text-left transition-all relative cursor-pointer group ${
                                            activeSessionId === s.session_id 
                                            ? "bg-blue-50 shadow-sm border border-blue-200 text-blue-900"
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
                                                    className="w-full bg-white border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/10"
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
                                                        className="w-6 h-6 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400 hover:text-blue-600 transition-colors"
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
                            onScroll={e => { const el = e.currentTarget; followLatest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}
                            className="flex-1 overflow-y-auto px-6 md:px-10 py-8 space-y-6 relative custom-scrollbar"
                        >
                            {!activeSessionId && messages.length === 0 && (
                                <div className="h-full flex flex-col items-center justify-center text-center px-4 max-w-3xl mx-auto py-2 relative overflow-hidden">
                                    <motion.div 
                                        initial={false}
                                        animate={{ opacity: 1, scale: 1 }}
                                        className="w-full h-full flex flex-col items-center justify-center"
                                    >
                                        <div className="w-12 h-12 rounded-2xl bg-blue-500 flex items-center justify-center mb-3 mx-auto text-slate-900 shadow-2xl shadow-blue-500/30 relative shrink-0">
                                            <Bot size={24} />
                                        </div>
                                        <h3 className="text-2xl md:text-3xl font-semibold text-slate-900 mb-2 tracking-tighter leading-[0.9] shrink-0">
                                            Welcome to your<br/><span className="text-blue-600 ">study space.</span>
                                        </h3>
                                        <p className="text-slate-500 font-medium text-sm mb-5 max-w-md mx-auto shrink-0 leading-snug">
                                            Ask questions using the available materials in <span className="text-blue-600 font-bold">{classroom?.name}</span>.
                                            What would you like to study today?
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
                                                    initial={false}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{ delay: 0.2 + (i * 0.1) }}
                                                    onClick={() => setInput(p.prompt)}
                                                    className="p-4 rounded-xl bg-white border border-slate-100 hover:border-blue-600/30 hover:shadow-premium transition-all group relative overflow-hidden"
                                                >
                                                    <div className="absolute top-0 right-0 p-2 opacity-5 group-hover:opacity-10 transition-opacity">
                                                        <span className="text-3xl">{p.icon}</span>
                                                    </div>
                                                    <div className="relative z-10">
                                                        <div className="font-black text-slate-900 text-xs group-hover:text-blue-600 transition-colors tracking-tight mb-0.5">{p.text}</div>
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
                                    initial={false}
                                    animate={{ opacity: 1, y: 0 }}
                                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                                >
                                    <div className={`flex min-w-0 gap-3 max-w-[94%] md:max-w-[85%] ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                                        <div className={`w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center shadow-md transition-transform hover:scale-105 duration-300 ${
                                            msg.role === "user" 
                                            ? "bg-white text-slate-600 border border-slate-100" 
                                            : "bg-indigo-600 text-white shadow-indigo-600/20"
                                        }`}>
                                            {msg.role === "user" ? <User size={16} /> : <Bot size={18} />}
                                        </div>
                                        <div className={`min-w-0 max-w-full space-y-2 ${msg.role === "user" ? "text-right" : "text-left"}`}>
                                            <div className={`inline-block max-w-full px-5 py-3.5 rounded-2xl shadow-sm leading-relaxed text-sm tracking-tight ${
                                                msg.role === "user" 
                                                ? "bg-primary text-white rounded-tr-sm font-semibold"
                                                : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm font-normal"
                                            }`}>
                                                {msg.role === "user" ? msg.content : (
                                                    <div className="markdown-content">
                                                        <ChatMarkdown content={msg.content} />
                                                    </div>
                                                )}
                                            </div>
                                            
                                            {msg.sources && msg.sources.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5 mt-2 justify-start">
                                                    {msg.sources.map((s, i) => (
                                                        <motion.div 
                                                            key={i}
                                                            whileHover={{ scale: 1.05 }}
                                                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white border border-slate-100 text-[10px] font-black text-slate-500 hover:text-blue-600 hover:border-blue-600/20 transition-all shadow-sm cursor-default"
                                                        >
                                                            <BookOpen size={11} className="text-blue-600" />
                                                            <span>{s.file_name}</span>
                                                            {s.page_number != null && <span className="bg-blue-50 px-1.5 py-0.5 rounded text-[9px] text-blue-600">PG {s.page_number}</span>}
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
                                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500/40 animate-pulse" />
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
                                                <Loader2 size={16} className="animate-spin text-blue-600" />
                                                <div className="absolute inset-0 bg-blue-500/20 blur-lg animate-pulse" />
                                            </div>
                                            <span className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em]">{status}</span>
                                            <div className="flex gap-1 ml-2">
                                                {[1, 2, 3].map(i => (
                                                    <motion.div 
                                                        key={i}
                                                        animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.2, 1] }}
                                                        transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }}
                                                        className="w-1 h-1 rounded-full bg-blue-500"
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
                                <div className="absolute inset-0 bg-blue-500/5 rounded-2xl blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
                                <div className="relative flex items-center glass rounded-2xl border-white/40 shadow-sm overflow-hidden focus-within:border-blue-600/20 focus-within:shadow-premium transition-all">
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
                                            className="w-9 h-9 rounded-xl bg-blue-500 hover:bg-blue-600 text-slate-900 shadow-lg shadow-blue-500/20 transition-all active:scale-90 flex items-center justify-center disabled:opacity-30 disabled:grayscale"
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

            {/* Mobile Session History Drawer overlay */}
            <AnimatePresence>
                {isOpenMobileHistory && (
                    <>
                        {/* Mobile Backdrop */}
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 0.5 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setIsOpenMobileHistory(false)}
                            className="fixed inset-0 bg-slate-900/60 z-50 lg:hidden"
                        />

                        {/* Mobile History Drawer */}
                        <motion.aside
                            initial={{ x: "100%" }}
                            animate={{ x: 0 }}
                            exit={{ x: "100%" }}
                            transition={{ duration: 0.16, ease: "easeOut" }}
                            className="fixed right-0 top-0 h-screen w-72 bg-white z-50 shadow-premium flex flex-col lg:hidden border-l border-slate-200"
                        >
                            <div className="p-4 flex items-center justify-between border-b border-slate-100">
                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                                    <History size={12} />
                                    Recent Chats
                                </span>
                                <button
                                    onClick={() => setIsOpenMobileHistory(false)}
                                    className="p-1 rounded-lg hover:bg-slate-50 text-slate-400"
                                >
                                    <X size={16} />
                                </button>
                            </div>

                            <div className="p-4">
                                <button 
                                    onClick={() => {
                                        setActiveSessionId(null);
                                        setIsOpenMobileHistory(false);
                                        window.location.reload();
                                    }}
                                    className="btn-neumorphic-primary w-full py-3 rounded-xl flex items-center justify-center gap-2.5 text-xs font-black uppercase tracking-widest group"
                                >
                                    <Plus size={15} className="" />
                                    New Chat
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto px-3 space-y-1.5 pb-4 custom-scrollbar">
                                {sessions.map(s => (
                                    <div
                                        key={s.session_id}
                                        onClick={() => {
                                            if (editingSessionId !== s.session_id) {
                                                followLatest.current = true;
                                                loadHistory(s.session_id);
                                                setIsOpenMobileHistory(false);
                                            }
                                        }}
                                        className={`w-full px-3 py-2.5 rounded-xl text-left transition-all relative cursor-pointer group ${
                                            activeSessionId === s.session_id 
                                            ? "bg-blue-50 shadow-sm border border-blue-200 text-blue-900"
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
                                                    className="w-full bg-white border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/10"
                                                />
                                            </form>
                                        ) : (
                                            <>
                                                <div className="text-xs font-bold truncate pr-14 tracking-tight leading-tight">{s.title}</div>
                                                <div className="text-[8px] font-black opacity-40 mt-1 uppercase tracking-widest">
                                                    {new Date(s.updated_at).toLocaleDateString()}
                                                </div>
                                                
                                                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-100">
                                                    <button 
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setEditTitle(s.title);
                                                            setEditingSessionId(s.session_id);
                                                        }}
                                                        className="w-6 h-6 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400 hover:text-blue-600 transition-colors border border-slate-100"
                                                    >
                                                        <Pencil size={10} />
                                                    </button>
                                                    <button 
                                                        onClick={(e) => handleDelete(e, s.session_id)}
                                                        className="w-6 h-6 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400 hover:text-red-500 transition-colors border border-slate-100"
                                                    >
                                                        <Trash2 size={10} />
                                                    </button>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </div>
    );
}
