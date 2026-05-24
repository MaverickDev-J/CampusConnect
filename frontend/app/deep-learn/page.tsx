"use client";

import { useState, useEffect, useRef, type KeyboardEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Header from "@/app/components/Header";
import {
    MessageSquare,
    Plus,
    PanelLeft,
    PanelRight,
    Send,
    BookOpen,
    FileText,
    Sparkles,
    X,
    ArrowLeft,
    Loader2,
    StopCircle,
    Image,
    Video,
} from "lucide-react";
import { useChat, type ChatMessage, type SourceRef } from "@/app/hooks/useChat";
import { useFiles, type FileMetadata } from "@/app/hooks/useFiles";
import { useAuth } from "@/app/context/auth-context";

// ── View States ─────────────────────────────────────────────────
type View = "sessions" | "file-select" | "chat";

export default function DeepLearnPage() {
    const { user } = useAuth();
    const {
        sessions,
        activeSessionId,
        messages,
        sources,
        status,
        streaming,
        loading,
        error,
        listSessions,
        createSession,
        loadHistory,
        sendMessage,
        stopStreaming,
    } = useChat();

    const { files, loading: filesLoading } = useFiles({});

    const [view, setView] = useState<View>("sessions");
    const [leftOpen, setLeftOpen] = useState(true);
    const [rightOpen, setRightOpen] = useState(true);
    const [inputText, setInputText] = useState("");

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // ── Load sessions on mount ──────────────────────────────────
    useEffect(() => {
        listSessions();
    }, [listSessions]);

    // ── Auto-scroll to bottom ───────────────────────────────────
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, status]);

    // ── Processed files only ────────────────────────────────────
    const processedFiles = files.filter(
        (f) => f.processing.status === "completed"
    );

    // ── Handlers ────────────────────────────────────────────────

    const handleNewChat = () => {
        setView("file-select");
    };

    const handleFileSelect = async (file: FileMetadata) => {
        const sid = await createSession(file.original_name, file.file_id);
        if (sid) {
            setView("chat");
            setRightOpen(false);
        }
    };

    const handleSessionClick = async (sessionId: string) => {
        await loadHistory(sessionId);
        setView("chat");
    };

    const handleSend = async () => {
        const q = inputText.trim();
        if (!q || streaming) return;
        setInputText("");
        setRightOpen(true);
        await sendMessage(q);
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // ── Group sessions by date ──────────────────────────────────
    const todaySessions = sessions.filter((s) => {
        const d = new Date(s.updated_at || s.created_at);
        const now = new Date();
        return d.toDateString() === now.toDateString();
    });
    const olderSessions = sessions.filter((s) => {
        const d = new Date(s.updated_at || s.created_at);
        const now = new Date();
        return d.toDateString() !== now.toDateString();
    });

    // ── File icon helper ────────────────────────────────────────
    const FileIcon = ({ type }: { type: string }) => {
        if (type === "image") return <Image className="w-5 h-5" />;
        if (type === "video") return <Video className="w-5 h-5" />;
        return <FileText className="w-5 h-5" />;
    };

    return (
        <div className="flex flex-col h-screen w-full overflow-hidden bg-[#0a0e1a] text-slate-200">
            <Header />

            <div className="flex flex-1 overflow-hidden relative">
                {/* ── Left Sidebar: Sessions ────────────────────────── */}
                <AnimatePresence mode="wait">
                    {leftOpen && (
                        <motion.aside
                            initial={{ width: 0, opacity: 0 }}
                            animate={{ width: 280, opacity: 1 }}
                            exit={{ width: 0, opacity: 0 }}
                            className="h-full border-r border-slate-800/50 bg-[#070b14] flex flex-col"
                        >
                            {/* New Chat Button */}
                            <div className="p-4">
                                <button
                                    onClick={handleNewChat}
                                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-medium shadow-lg shadow-purple-900/20 transition-all"
                                >
                                    <Plus className="w-5 h-5" />
                                    New Chat
                                </button>
                            </div>

                            {/* Session List */}
                            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6">
                                {todaySessions.length > 0 && (
                                    <div>
                                        <h3 className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                                            Today
                                        </h3>
                                        <div className="space-y-1">
                                            {todaySessions.map((s) => (
                                                <button
                                                    key={s.session_id}
                                                    onClick={() =>
                                                        handleSessionClick(
                                                            s.session_id
                                                        )
                                                    }
                                                    className={`w-full text-left px-3 py-2.5 rounded-lg flex items-center gap-3 transition-colors ${activeSessionId ===
                                                            s.session_id
                                                            ? "bg-slate-800/80 text-white shadow-sm border border-slate-700/50"
                                                            : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                                                        }`}
                                                >
                                                    <MessageSquare className="w-4 h-4 shrink-0" />
                                                    <span className="text-sm truncate">
                                                        {s.title}
                                                    </span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {olderSessions.length > 0 && (
                                    <div>
                                        <h3 className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                                            Earlier
                                        </h3>
                                        <div className="space-y-1">
                                            {olderSessions.map((s) => (
                                                <button
                                                    key={s.session_id}
                                                    onClick={() =>
                                                        handleSessionClick(
                                                            s.session_id
                                                        )
                                                    }
                                                    className="w-full text-left px-3 py-2.5 rounded-lg flex items-center gap-3 text-slate-400 hover:bg-slate-800/40 hover:text-slate-200 transition-colors"
                                                >
                                                    <MessageSquare className="w-4 h-4 shrink-0" />
                                                    <span className="text-sm truncate">
                                                        {s.title}
                                                    </span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {sessions.length === 0 && (
                                    <div className="text-center text-slate-600 text-sm py-8">
                                        No conversations yet
                                    </div>
                                )}
                            </div>

                            {/* Session count */}
                            <div className="p-4 border-t border-slate-800/50">
                                <div className="flex items-center justify-between text-xs text-slate-400">
                                    <span>Total Sessions</span>
                                    <span className="text-purple-400 font-medium">
                                        {sessions.length}
                                    </span>
                                </div>
                            </div>
                        </motion.aside>
                    )}
                </AnimatePresence>

                {/* ── Middle: Main Content ────────────────────────────── */}
                <main className="flex-1 flex flex-col relative min-w-0">
                    {/* Sidebar Toggles */}
                    <button
                        onClick={() => setLeftOpen(!leftOpen)}
                        className="absolute top-4 left-4 z-10 p-2 rounded-lg text-slate-500 hover:bg-slate-800/50 transition-colors"
                    >
                        <PanelLeft className="w-5 h-5" />
                    </button>
                    {view === "chat" && (
                        <button
                            onClick={() => setRightOpen(!rightOpen)}
                            className="absolute top-4 right-4 z-10 p-2 rounded-lg text-slate-500 hover:bg-slate-800/50 transition-colors"
                        >
                            <PanelRight className="w-5 h-5" />
                        </button>
                    )}

                    {/* ── View: Sessions (Start Screen) ─────────────── */}
                    {view === "sessions" && (
                        <div className="flex-1 flex flex-col items-center justify-center px-6">
                            <div className="relative mb-6">
                                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-600/20 to-purple-600/20 border border-indigo-500/30 flex items-center justify-center">
                                    <Sparkles className="w-10 h-10 text-indigo-400" />
                                </div>
                            </div>
                            <h2 className="text-2xl font-bold text-white mb-2">
                                Deep Learn
                            </h2>
                            <p className="text-slate-400 text-sm max-w-md text-center mb-8">
                                Ask questions about your uploaded course
                                materials. Select a file to start a
                                contextual AI conversation.
                            </p>
                            <button
                                onClick={handleNewChat}
                                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold shadow-lg shadow-purple-900/30 transition-all"
                            >
                                <Plus className="w-5 h-5" />
                                Start New Chat
                            </button>
                        </div>
                    )}

                    {/* ── View: File Selection ──────────────────────── */}
                    {view === "file-select" && (
                        <div className="flex-1 overflow-y-auto p-6 lg:p-10">
                            <div className="h-12" />
                            <button
                                onClick={() => setView("sessions")}
                                className="flex items-center gap-2 text-slate-400 hover:text-white mb-6 transition-colors"
                            >
                                <ArrowLeft className="w-4 h-4" />
                                <span className="text-sm">Back</span>
                            </button>

                            <h2 className="text-xl font-bold text-white mb-2">
                                Select a File
                            </h2>
                            <p className="text-slate-400 text-sm mb-8">
                                Choose a processed file to scope your AI
                                conversation.
                            </p>

                            {filesLoading ? (
                                <div className="flex items-center justify-center py-20">
                                    <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
                                </div>
                            ) : processedFiles.length === 0 ? (
                                <div className="text-center py-20 text-slate-500">
                                    <FileText className="w-12 h-12 mx-auto mb-4 opacity-30" />
                                    <p className="font-medium">
                                        No processed files available
                                    </p>
                                    <p className="text-xs mt-2">
                                        Upload files in Deep Base and wait
                                        for processing to complete.
                                    </p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                    {processedFiles.map((file) => (
                                        <motion.button
                                            key={file.file_id}
                                            onClick={() =>
                                                handleFileSelect(file)
                                            }
                                            whileHover={{ y: -4, scale: 1.02 }}
                                            className="group text-left bg-[#0f1523] border border-slate-800 rounded-xl overflow-hidden hover:border-indigo-500/50 hover:shadow-xl hover:shadow-indigo-500/10 transition-all"
                                        >
                                            <div className="h-24 bg-gradient-to-br from-slate-800 to-slate-900 p-4 flex items-end group-hover:from-indigo-900/40 group-hover:to-slate-900 transition-colors">
                                                <div className="flex items-center gap-2">
                                                    <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                                                        <FileIcon
                                                            type={
                                                                file.file_type
                                                            }
                                                        />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-medium text-white truncate">
                                                            {
                                                                file.original_name
                                                            }
                                                        </p>
                                                        <p className="text-[10px] text-slate-400 uppercase">
                                                            {
                                                                file.academic
                                                                    .subject
                                                            }{" "}
                                                            •{" "}
                                                            {
                                                                file.academic
                                                                    .branch
                                                            }
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="p-3 flex items-center justify-between text-xs text-slate-500">
                                                <span>
                                                    {
                                                        file.processing
                                                            .chunk_count
                                                    }{" "}
                                                    chunks
                                                </span>
                                                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-bold uppercase">
                                                    Ready
                                                </span>
                                            </div>
                                        </motion.button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── View: Chat ────────────────────────────────── */}
                    {view === "chat" && (
                        <>
                            {/* Messages Area */}
                            <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-10 space-y-8 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                                <div className="h-12" />

                                {loading ? (
                                    <div className="flex items-center justify-center py-20">
                                        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
                                    </div>
                                ) : messages.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-full text-slate-500 opacity-60">
                                        <Sparkles className="w-12 h-12 mb-4 text-indigo-500/50" />
                                        <p className="text-lg font-medium">
                                            Ask something about your file
                                        </p>
                                        <p className="text-sm mt-1">
                                            Your AI tutor is ready
                                        </p>
                                    </div>
                                ) : (
                                    messages.map((msg) => (
                                        <MessageBubble
                                            key={msg.id}
                                            msg={msg}
                                        />
                                    ))
                                )}

                                {/* Status indicator */}
                                {status && (
                                    <div className="flex items-center gap-3 text-sm text-indigo-400">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        <span>{status}</span>
                                    </div>
                                )}

                                {/* Error */}
                                {error && (
                                    <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                                        {error}
                                    </div>
                                )}

                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input Area */}
                            <div className="p-4">
                                <div className="max-w-4xl mx-auto relative group">
                                    <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                                    <div className="relative bg-[#0f1523] border border-slate-700/50 rounded-2xl p-2 flex items-end gap-2 shadow-2xl">
                                        <textarea
                                            ref={textareaRef}
                                            placeholder="Ask anything about your coursework..."
                                            className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none text-slate-200 placeholder-slate-500 resize-none py-3 px-3 max-h-32 text-sm"
                                            rows={1}
                                            value={inputText}
                                            onChange={(e) =>
                                                setInputText(e.target.value)
                                            }
                                            onKeyDown={handleKeyDown}
                                            disabled={streaming}
                                        />
                                        {streaming ? (
                                            <button
                                                onClick={stopStreaming}
                                                className="p-3 bg-red-600 hover:bg-red-500 text-white rounded-xl shadow-lg transition-all"
                                            >
                                                <StopCircle className="w-5 h-5" />
                                            </button>
                                        ) : (
                                            <button
                                                onClick={handleSend}
                                                disabled={
                                                    !inputText.trim()
                                                }
                                                className="p-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-lg shadow-indigo-900/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                                            >
                                                <Send className="w-5 h-5" />
                                            </button>
                                        )}
                                    </div>
                                    <p className="text-center text-[10px] text-slate-600 mt-2">
                                        CampusAI can make mistakes. Verify
                                        important information from your
                                        course materials.
                                    </p>
                                </div>
                            </div>
                        </>
                    )}
                </main>

                {/* ── Right Sidebar: Sources ───────────────────────── */}
                <AnimatePresence mode="wait">
                    {rightOpen && view === "chat" && (
                        <motion.aside
                            initial={{ width: 0, opacity: 0 }}
                            animate={{ width: 320, opacity: 1 }}
                            exit={{ width: 0, opacity: 0 }}
                            className="h-full border-l border-slate-800/50 bg-[#070b14] flex flex-col"
                        >
                            {/* Header */}
                            <div className="p-4 border-b border-slate-800/50 flex items-center justify-between">
                                <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                                    <BookOpen className="w-4 h-4 text-indigo-400" />
                                    Sources & Citations
                                </h2>
                                <button
                                    onClick={() => setRightOpen(false)}
                                    className="text-slate-500 hover:text-slate-300 transition-colors"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            {/* Content */}
                            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                                {sources.length === 0 ? (
                                    <div className="text-center text-slate-600 text-sm py-10">
                                        <BookOpen className="w-8 h-8 mx-auto mb-3 opacity-30" />
                                        <p>
                                            Sources will appear here after
                                            the AI responds
                                        </p>
                                    </div>
                                ) : (
                                    sources.map(
                                        (src: SourceRef, i: number) => (
                                            <div
                                                key={i}
                                                className="p-3 rounded-xl bg-[#0f1523] border border-slate-800 hover:border-indigo-500/30 transition-colors group"
                                            >
                                                <div className="flex items-start gap-3">
                                                    <div className="w-6 h-6 rounded bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold text-xs shrink-0 mt-0.5">
                                                        {i + 1}
                                                    </div>
                                                    <div className="space-y-1.5 min-w-0">
                                                        <p className="text-xs font-semibold text-slate-200 group-hover:text-indigo-400 transition-colors truncate">
                                                            {src.file_name}
                                                        </p>
                                                        {src.chunk_preview && (
                                                            <p className="text-[10px] text-slate-400 leading-relaxed line-clamp-3">
                                                                &ldquo;
                                                                {
                                                                    src.chunk_preview
                                                                }
                                                                &rdquo;
                                                            </p>
                                                        )}
                                                        <div className="flex items-center gap-2 pt-1">
                                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                                                                Page{" "}
                                                                {
                                                                    src.page_number
                                                                }
                                                            </span>
                                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                                                                {(
                                                                    src.relevance_score *
                                                                    100
                                                                ).toFixed(
                                                                    0
                                                                )}
                                                                % match
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        )
                                    )
                                )}
                            </div>
                        </motion.aside>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

// ── Message Bubble Component ────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
    return (
        <div
            className={`flex gap-4 ${msg.role === "user" ? "justify-end" : "justify-start"
                }`}
        >
            {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0 border border-indigo-500/30">
                    <Sparkles className="w-4 h-4" />
                </div>
            )}

            <div className="max-w-[80%] space-y-2">
                <div
                    className={`p-4 rounded-2xl text-sm leading-relaxed ${msg.role === "user"
                            ? "bg-blue-600 text-white rounded-tr-sm"
                            : "bg-[#0f1523] border border-slate-800 text-slate-200 rounded-tl-sm shadow-xl"
                        }`}
                >
                    <p className="whitespace-pre-wrap">{msg.content || (msg.role === "assistant" ? "..." : "")}</p>
                </div>

                {msg.timestamp && (
                    <div
                        className={`flex items-center gap-2 text-[10px] text-slate-500 ${msg.role === "user"
                                ? "justify-end"
                                : "justify-start"
                            }`}
                    >
                        <span>
                            {new Date(msg.timestamp).toLocaleTimeString(
                                [],
                                {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                }
                            )}
                        </span>
                    </div>
                )}
            </div>

            {msg.role === "user" && (
                <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-white">U</span>
                </div>
            )}
        </div>
    );
}
