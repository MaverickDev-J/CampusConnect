"use client";

import { use, useState, useCallback, useEffect } from "react";
import { API_BASE_URL } from "@/app/config";
import { useClassroom } from "@/app/hooks/useClassrooms";
import { useFiles } from "@/app/hooks/useFiles";
import { useAnnouncements } from "@/app/hooks/useAnnouncements";
import { useAuth } from "@/app/context/auth-context";
import Header from "@/app/components/Header";
import Link from "next/link";
import { 
    CheckCircle2,
    AlertCircle,
    RotateCcw,
    Check,
    X,
    FileText,
    MessageSquare,
    Upload,
    Users,
    Plus,
    MoreVertical,
    ChevronRight,
    Globe,
    Lock,
    Search,
    Send,
    Loader2,
    Calendar,
    Download,
    Eye,
    Bot,
    Trash2,
    User,
    ArrowLeft
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Sidebar } from "@/app/components/Sidebar";
import { useClassroomSocket } from "@/app/hooks/useClassroomSocket";

export default function ClassroomPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const { user } = useAuth();
    const { classroom, loading: classLoading } = useClassroom(id);
    const { files, loading: filesLoading, uploadFile } = useFiles(id);
    const { announcements, loading: annLoading, postAnnouncement, refresh: refreshAnnouncements } = useAnnouncements(id);

    const [annContent, setAnnContent] = useState("");
    const [posting, setPosting] = useState(false);
    const [uploadProgress, setUploadProgress] = useState<{ name: string; percent: number } | null>(null);
    const [successToast, setSuccessToast] = useState<string | null>(null);
    const [upcomingEvent, setUpcomingEvent] = useState<any>(null);

    const fetchClassroomEvents = useCallback(async () => {
        if (!user?.token) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/calendar/events?classroom_id=${id}`, {
                headers: { "Authorization": `Bearer ${user.token}` }
            });
            if (res.ok) {
                const data = await res.json();
                const now = new Date();
                const upcoming = data.events
                    .map((e: any) => ({ ...e, date: new Date(e.date) }))
                    .filter((e: any) => e.date >= now)
                    .sort((a: any, b: any) => a.date.getTime() - b.date.getTime())[0];
                setUpcomingEvent(upcoming);
            }
        } catch (err) {
            console.error("Failed to fetch classroom events:", err);
        }
    }, [id, user?.token]);

    useEffect(() => {
        fetchClassroomEvents();
    }, [fetchClassroomEvents]);

    const isTeacher = user?.role === "teacher" || user?.role === "superadmin";

    const handleWebSocketMessage = useCallback((msg: any) => {
        // Log handshake acks for diagnostics
        if (msg.type === "connection_established") {
            console.log(`[useClassroomSocket] ✅ Server Ack: ${msg.classroom_id}`);
            return;
        }

        if (msg.type === "announcement_updated" || msg.type === "file_processed") {
            console.log(`[useClassroomSocket] 🔔 Event Received: ${msg.type}`);
            refreshAnnouncements();
            if (msg.type === "file_processed" && msg.status === "ready") {
                setSuccessToast(`Material processed and ready!`);
                setTimeout(() => setSuccessToast(null), 5000);
            }
        }
    }, [refreshAnnouncements]);

    // ── WebSocket Integration ──
    useClassroomSocket(id, user, handleWebSocketMessage);

    const handlePost = async () => {
        if (!annContent.trim() && !stagedFileId) return;
        setPosting(true);
        try {
            // @ts-ignore - Backend now supports file_id
            await postAnnouncement(annContent, stagedFileId);
            setAnnContent("");
            setStagedFileId(null);
            refreshAnnouncements();
        } catch (err) {
            alert("Failed to post announcement");
        } finally {
            setPosting(false);
        }
    };

    const [stagedFileId, setStagedFileId] = useState<string | null>(null);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploadProgress({ name: file.name, percent: 0 });
        try {
            const res = await uploadFile(file, "academic_material", (percent) => {
                setUploadProgress({ name: file.name, percent });
            });
            if (res && res.file_id) {
                setStagedFileId(res.file_id);
            }
            setTimeout(() => setUploadProgress(null), 1000);
        } catch (err) {
            alert(err instanceof Error ? err.message : "Upload failed");
            setUploadProgress(null);
        }
    };

    const handleRetryProcessing = async (fileId: string) => {
        if (!user?.token) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/files/${fileId}/retry`, {
                method: "POST",
                headers: { Authorization: `Bearer ${user.token}` },
            });
            if (!res.ok) throw new Error("Retry failed");
            refreshAnnouncements();
        } catch (err) {
            alert("Retry failed");
        }
    };

    const handleDeleteAnnouncement = async (announcementId: string) => {
        if (!confirm("Are you sure? This will permanently delete the post, attached files, and all AI knowledge of it.")) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/announcements/${announcementId}`, {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${user?.token}` },
            });
            if (res.ok) {
                refreshAnnouncements();
            } else {
                alert("Failed to delete announcement.");
            }
        } catch (err) {
            console.error("Delete err:", err);
            alert("Delete failed");
        }
    };

    if (classLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="flex flex-col items-center gap-6">
                    <div className="relative">
                        <Loader2 className="w-12 h-12 text-primary animate-spin" />
                        <div className="absolute inset-0 bg-primary blur-2xl opacity-20" />
                    </div>
                    <p className="text-slate-400 font-black uppercase tracking-[0.3em] text-[10px]">Entering Classroom...</p>
                </div>
            </div>
        );
    }

    if (!classroom) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center">
                <motion.div 
                    initial={{ scale: 0.9, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="w-20 h-20 rounded-[2rem] glass-dark flex items-center justify-center mb-8 shadow-premium"
                >
                    <Lock className="text-rose-500 w-10 h-10" />
                </motion.div>
                <h2 className="text-4xl font-black text-slate-900 mb-3 tracking-tighter">Classroom Not Found</h2>
                <p className="text-slate-500 max-w-sm mb-10 font-medium leading-relaxed">
                    The requested classroom is either restricted or does not exist.
                </p>
                <Link href="/classrooms" className="btn-neumorphic-primary px-10 py-4 rounded-2xl font-black uppercase tracking-widest text-xs">
                    Back to Classrooms
                </Link>
            </div>
        );
    }

    return (
        <div className="flex min-h-screen">
            <Sidebar />

            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300 relative min-h-screen flex flex-col overflow-hidden">
                {/* Background Brand Glows */}
                <div className="fixed inset-0 pointer-events-none">
                    <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-amber-400/5 blur-[120px] rounded-full" />
                    <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-amber-400/5 blur-[120px] rounded-full" />
                </div>
                <Header />

                {/* Sticky Progress Bar */}
                <AnimatePresence>
                    {uploadProgress && (
                        <motion.div 
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="bg-primary/95 backdrop-blur-md px-10 py-4 text-white flex items-center justify-between overflow-hidden shadow-premium z-20 border-b border-white/10"
                        >
                            <div className="flex items-center gap-4 truncate">
                                <div className="p-2 bg-white/10 rounded-xl">
                                    <Loader2 className="animate-spin" size={18} />
                                </div>
                                <div className="truncate">
                                    <span className="text-sm font-black truncate block uppercase tracking-widest">Uploading File...</span>
                                    <span className="text-[10px] font-bold opacity-60 truncate block">{uploadProgress.name}</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-6 flex-shrink-0">
                                <div className="w-48 h-2 bg-white/10 rounded-full overflow-hidden shadow-inner">
                                    <motion.div 
                                        initial={{ width: 0 }}
                                        animate={{ width: `${uploadProgress.percent}%` }}
                                        className="h-full bg-white shadow-[0_0_15px_rgba(255,255,255,0.5)]" 
                                    />
                                </div>
                                <span className="text-xs font-black w-10 text-right">{uploadProgress.percent}%</span>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <div className="max-w-6xl mx-auto w-full px-10 py-12 flex-1 relative z-10">
                    {/* Back Button */}
                    <div className="mb-8">
                        <Link href="/classrooms" className="inline-flex items-center gap-2 text-slate-400 hover:text-amber-600 transition-all group">
                            <div className="w-10 h-10 rounded-xl bg-white border border-slate-100 flex items-center justify-center group-hover:border-amber-600/20 shadow-soft transition-all group-hover:shadow-md">
                                <ArrowLeft size={18} />
                            </div>
                            <span className="text-xs font-black uppercase tracking-widest">All Classrooms</span>
                        </Link>
                    </div>

                    {/* Hero Banner Section */}
                    <motion.div 
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="relative rounded-[3rem] overflow-hidden bg-slate-950 shadow-premium mb-12 h-64 md:h-80 group"
                    >
                        <div className="absolute inset-0 bg-gradient-to-br from-amber-400 via-amber-600 to-amber-900 opacity-60 group-hover:opacity-70 transition-opacity duration-700" />
                        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-10 mix-blend-overlay" />
                        
                        <div className="p-10 md:p-16 relative z-10 flex flex-col justify-end h-full">
                            <motion.div 
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.2 }}
                                className="flex items-center gap-3 px-4 py-2 rounded-2xl bg-white/10 border border-white/20 w-fit mb-6 backdrop-blur-md shadow-lg"
                            >
                                <Globe className="w-4 h-4 text-white/70" />
                                <span className="text-[11px] font-black text-white tracking-[0.3em] uppercase">
                                    {classroom.subject || "General Space"}
                                </span>
                            </motion.div>
                            <motion.h1 
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.3 }}
                                className="text-4xl md:text-6xl font-black tracking-tighter text-white leading-[0.9] mb-4"
                            >
                                {classroom.name}
                            </motion.h1>
                            <motion.div 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.4 }}
                                className="flex flex-wrap items-center gap-8 text-white/60 text-[10px] font-black uppercase tracking-[0.3em]"
                            >
                                <div className="flex items-center gap-2.5">
                                    <Users size={14} className="text-white/40" />
                                    <span>{classroom.member_count} Members</span>
                                </div>
                                <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 backdrop-blur-sm"> 
                                    <Lock size={12} className="text-white/40" /> Join Code: <span className="text-white tracking-widest">{classroom.join_code}</span>
                                </div>
                            </motion.div>
                        </div>
                    </motion.div>

                    <div className="grid grid-cols-1 lg:grid-cols-4 gap-10 items-start">
                        {/* Sidebar Column */}
                        <div className="lg:col-span-1 space-y-8">
                            <div className="p-8 rounded-[2.5rem] glass border border-white/40 shadow-premium">
                                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] mb-6">Assignments</h3>
                                <div className="space-y-4">
                                    <div className="p-4 rounded-2xl bg-amber-50 border border-amber-100 flex flex-col gap-1">
                                        <div className="text-[10px] font-black text-amber-600 uppercase tracking-widest">{upcomingEvent ? upcomingEvent.type : 'Upcoming'}</div>
                                        <div className="text-sm font-bold text-slate-700">
                                            {upcomingEvent ? (
                                                <div className="flex flex-col">
                                                    <span className="truncate">{upcomingEvent.title}</span>
                                                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mt-0.5">
                                                        {upcomingEvent.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                                                    </span>
                                                </div>
                                            ) : (
                                                "No upcoming tasks."
                                            )}
                                        </div>
                                    </div>
                                    <Link href="/calendar" className="flex items-center justify-center w-full py-3 rounded-xl bg-white border border-slate-100 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] hover:text-amber-600 hover:border-amber-600/20 transition-all shadow-soft">
                                        View Calendar
                                    </Link>
                                </div>
                            </div>

                            <Link 
                                href={`/classroom/${id}/chat`}
                                className="btn-neumorphic-primary flex flex-col items-center justify-center gap-4 p-8 rounded-[2.5rem] transition-all group relative overflow-hidden h-48"
                            >
                                <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:scale-110 transition-transform">
                                    <Bot size={80} />
                                </div>
                                <div className="w-14 h-14 rounded-2xl bg-white/20 flex items-center justify-center backdrop-blur-md shadow-lg mb-2">
                                    <MessageSquare size={28} className="text-white" />
                                </div>
                                <div className="text-center relative z-10">
                                    <span className="block uppercase tracking-[0.3em] text-xs font-black text-white mb-1">Study Assistant</span>
                                    <span className="block text-[10px] font-bold text-white/70">Ask questions about materials</span>
                                </div>
                            </Link>
                        </div>

                        {/* Stream / Announcements Column */}
                        <div className="lg:col-span-3 space-y-8">
                            {/* Announce Box - Teacher Action */}
                            {isTeacher && (
                                <motion.div 
                                    layout
                                    className="p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-premium"
                                >
                                    {posting || annContent ? (
                                        <div className="space-y-6">
                                            <div className="relative">
                                                <textarea
                                                    placeholder="Share an announcement with the class..."
                                                    value={annContent}
                                                    onChange={e => setAnnContent(e.target.value)}
                                                    className="w-full p-6 rounded-[2rem] bg-slate-50 border border-transparent text-slate-900 focus:outline-none focus:bg-white focus:ring-4 focus:ring-amber-500/5 focus:border-amber-500/20 transition-all font-semibold min-h-[160px] text-lg"
                                                />
                                            </div>
                                            <div className="flex items-center justify-between gap-4">
                                                <div className="flex gap-3">
                                                    <label className="w-14 h-14 rounded-2xl bg-slate-100 text-slate-500 hover:text-amber-600 hover:bg-white hover:shadow-soft cursor-pointer transition-all flex items-center justify-center border border-transparent hover:border-amber-600/10 group">
                                                        <Plus size={24} className="group-hover:rotate-90 transition-transform" />
                                                        <input type="file" className="hidden" onChange={handleFileUpload} />
                                                    </label>
                                                    {stagedFileId && (
                                                        <div className="px-5 py-2.5 rounded-2xl bg-amber-50 border border-amber-200 flex items-center gap-3">
                                                            <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                                                            <span className="text-[10px] font-black text-amber-600 uppercase tracking-widest whitespace-nowrap">File Attached</span>
                                                            <button 
                                                                onClick={() => setStagedFileId(null)}
                                                                className="ml-2 text-primary hover:text-rose-500 transition-colors"
                                                            >
                                                                <X size={14} />
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="flex gap-4">
                                                    <button onClick={() => {setAnnContent(""); setStagedFileId(null);}} className="px-8 py-3.5 rounded-2xl text-slate-400 font-black text-sm uppercase tracking-widest hover:bg-slate-50 transition-all font-sans">Cancel</button>
                                                    <button 
                                                        disabled={posting || (!annContent.trim() && !stagedFileId)}
                                                        onClick={handlePost}
                                                        className="btn-neumorphic-primary px-10 py-3.5 rounded-2xl font-black text-sm flex items-center gap-3 uppercase tracking-widest"
                                                    >
                                                        {posting ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
                                                        Post
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div 
                                            onClick={() => setAnnContent(" ")}
                                            className="flex items-center gap-6 cursor-pointer group"
                                        >
                                            <div className="w-14 h-14 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-amber-600 group-hover:text-slate-900 transition-all duration-500 group-hover:shadow-lg group-hover:shadow-amber-500/20 group-hover:rotate-6">
                                                <Plus size={28} />
                                            </div>
                                            <span className="text-xl font-black text-slate-400 group-hover:text-slate-900 transition-all duration-300 tracking-tight">Make an announcement...</span>
                                        </div>
                                    )}
                                </motion.div>
                            )}

                            {!isTeacher && (
                                <div className="p-8 rounded-[2.5rem] glass border border-white/40 shadow-premium flex items-center gap-6">
                                    <div className="w-14 h-14 rounded-2xl bg-amber-50 flex items-center justify-center text-amber-600 shadow-inner">
                                        <RotateCcw size={28} className="animate-pulse" />
                                    </div>
                                    <div>
                                        <h3 className="text-xl font-black text-slate-900 tracking-tighter">Live Resource Stream</h3>
                                        <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mt-1 opacity-60">Live updates from your instructor</p>
                                    </div>
                                </div>
                            )}

                            {/* Stream Feed items */}
                            <div className="space-y-8 pb-20">
                                {annLoading ? (
                                    [1,2,3].map(i => (
                                        <div key={i} className="h-48 rounded-[2.5rem] bg-white border border-slate-50 animate-pulse shadow-soft" />
                                    ))
                                ) : announcements.length === 0 ? (
                                    <motion.div 
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="py-32 text-center"
                                    >
                                        <div className="w-20 h-20 rounded-[2rem] glass mx-auto flex items-center justify-center text-slate-200 mb-6">
                                            <Calendar size={40} />
                                        </div>
                                        <p className="text-slate-400 font-bold uppercase tracking-[0.2em] text-[10px]">Your learning journey starts here. Ask your tutor anything!</p>
                                    </motion.div>
                                ) : (
                                    announcements.map((ann, idx) => (
                                        <motion.div 
                                            key={ann.announcement_id}
                                            initial={{ opacity: 0, y: 30 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: idx * 0.05 }}
                                            className="p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-premium relative overflow-hidden group"
                                        >
                                            <div className="flex items-center justify-between mb-8">
                                                <div className="flex items-center gap-4">
                                                    <div className="w-12 h-12 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-400 shadow-inner group-hover:bg-amber-50 group-hover:text-amber-600 transition-colors">
                                                        <User size={24} />
                                                    </div>
                                                    <div>
                                                        <div className="text-lg font-black text-slate-900 leading-none tracking-tight">{ann.author_name}</div>
                                                        <div className="text-[9px] text-slate-400 font-black uppercase tracking-[0.2em] mt-2 flex items-center gap-2">
                                                            <div className="w-1.5 h-1.5 rounded-full bg-slate-200" />
                                                            {new Date(ann.created_at).toLocaleString(undefined, {
                                                                dateStyle: 'medium',
                                                                timeStyle: 'short'
                                                            })}
                                                        </div>
                                                    </div>
                                                </div>
                                                {isTeacher && (
                                                    <button 
                                                        onClick={() => handleDeleteAnnouncement(ann.announcement_id)}
                                                        className="w-10 h-10 flex items-center justify-center text-slate-200 hover:text-rose-500 hover:bg-rose-50 rounded-xl transition-all"
                                                        title="Terminate Broadcast"
                                                    >
                                                        <Trash2 size={18} />
                                                    </button>
                                                )}
                                            </div>
                                            <div className="text-lg text-slate-700 font-medium whitespace-pre-wrap leading-relaxed tracking-tight mb-8">
                                                {ann.content}
                                            </div>

                                            {ann.file && (
                                                <div className="p-6 rounded-[2rem] bg-slate-50 border border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-6 group/file hover:bg-white transition-all duration-300">
                                                    <div className="flex items-center gap-5">
                                                        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg transition-transform group-hover/file:rotate-6 ${
                                                            ann.file.file_type === "pdf" ? "bg-rose-50 text-rose-500 shadow-rose-100" : "bg-amber-50 text-amber-600 shadow-amber-100"
                                                        }`}>
                                                            <FileText size={28} />
                                                        </div>
                                                        <div>
                                                            <h4 className="font-black text-slate-900 tracking-tight">{ann.file.original_name}</h4>
                                                            <div className="flex items-center gap-3 mt-1.5">
                                                                <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest bg-slate-100 px-2 py-0.5 rounded-lg">
                                                                    {(ann.file.file_size_bytes / 1024 / 1024).toFixed(1)} MB
                                                                </p>
                                                                <div className="status-dot-animated opacity-40" />
                                                                <div className="flex items-center">
                                                                    {ann.file.processing?.status === "completed" && (
                                                                        <div className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100 flex items-center gap-2">
                                                                            <Check size={12} strokeWidth={3} />
                                                                            <span className="text-[9px] font-black uppercase tracking-widest italic">Ready for AI Chat</span>
                                                                        </div>
                                                                    )}
                                                                    {(ann.file.processing?.status === "pending" || ann.file.processing?.status === "processing") && (
                                                                        <div className="px-3 py-1 rounded-full bg-amber-50 text-amber-600 border border-amber-100 flex items-center gap-2">
                                                                            <Loader2 size={12} className="animate-spin" />
                                                                            <span className="text-[9px] font-black uppercase tracking-widest animate-pulse">AI is Reading File...</span>
                                                                        </div>
                                                                    )}
                                                                    {ann.file.processing?.status === "failed" && (
                                                                        <div className="px-3 py-1 rounded-full bg-rose-50 text-rose-600 border border-rose-100 flex items-center gap-2">
                                                                            <AlertCircle size={12} />
                                                                            <span className="text-[9px] font-black uppercase tracking-widest">Processing Failed</span>
                                                                            {isTeacher && (
                                                                                <button 
                                                                                    onClick={() => handleRetryProcessing(ann.file.file_id)}
                                                                                    className="ml-2 pl-2 border-l border-rose-200 hover:text-rose-900 transition-colors flex items-center gap-1.5"
                                                                                >
                                                                                    <RotateCcw size={10} />
                                                                                    <span className="text-[8px] font-black">RETRY</span>
                                                                                </button>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                                                                   <div className="flex items-center gap-3">
                                                        <a 
                                                            href={`${API_BASE_URL}/api/files/${ann.file.file_id}/download?token=${user?.token}`}
                                                            target="_blank"
                                                            className="w-12 h-12 flex items-center justify-center rounded-2xl bg-white text-slate-400 hover:text-amber-600 hover:shadow-premium transition-all border border-slate-100"
                                                            title="Download Original"
                                                        >
                                                            <Download size={20} />
                                                        </a>
                                                        <Link 
                                                            href={`/classroom/${id}/files/${ann.file.file_id}`}
                                                            className="w-12 h-12 flex items-center justify-center rounded-2xl bg-white text-slate-400 hover:text-amber-600 hover:shadow-premium transition-all border border-slate-100" 
                                                            title="Analyze View"
                                                        >
                                                            <Eye size={20} />
                                                        </Link>
                                                    </div>
      </div>
                                                </div>
                                            )}
                                        </motion.div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </main>

            {/* Mobile/Floating Context Notification */}
            <AnimatePresence>
                {successToast && (
                    <motion.div
                        initial={{ opacity: 0, x: 50, scale: 0.9 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8, x: 50 }}
                        className="fixed bottom-12 right-12 z-[100] p-6 glass-dark text-white rounded-[2.5rem] shadow-premium flex items-center gap-5 border border-white/10"
                    >
                        <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 flex items-center justify-center text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.3)]">
                            <CheckCircle2 size={24} />
                        </div>
                        <div className="pr-6">
                            <p className="text-lg font-black tracking-tighter leading-none mb-1">{successToast}</p>
                            <div className="flex items-center gap-2">
                                <div className="status-dot-animated" />
                                <p className="text-[10px] text-white/40 font-black uppercase tracking-[0.2em] italic">Classroom materials updated</p>
                            </div>
                        </div>
                        <button onClick={() => setSuccessToast(null)} className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 text-white/20 hover:text-white transition-all flex items-center justify-center">
                            <X size={18} />
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
