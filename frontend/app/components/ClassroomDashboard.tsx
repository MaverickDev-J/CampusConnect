"use client";

import { useState } from "react";
import { useAuth } from "@/app/context/auth-context";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { ClassroomCard } from "./ClassroomCard";
import { Plus, UserPlus, Loader2, BookOpen, XCircle } from "lucide-react";
import confetti from "canvas-confetti";

export function ClassroomDashboard() {
    const { user } = useAuth();
    const { classrooms, loading, error, joinClassroom, createClassroom } = useClassrooms();
    const [isJoinModalOpen, setIsJoinModalOpen] = useState(false);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [joinCode, setJoinCode] = useState("");
    const [newClass, setNewClass] = useState({ name: "", description: "", subject: "" });
    const [submitting, setSubmitting] = useState(false);

    const handleJoin = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            await joinClassroom(joinCode);
            
            // Celebration!
            confetti({
                particleCount: 150,
                spread: 70,
                origin: { y: 0.6 },
                colors: ["#4f46e5", "#10b981", "#fbbf24", "#ef4444"]
            });

            setIsJoinModalOpen(false);
            setJoinCode("");
        } catch (err) {
            console.error(err);
        } finally {
            setSubmitting(false);
        }
    };

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            await createClassroom(newClass);
            setIsCreateModalOpen(false);
            setNewClass({ name: "", description: "", subject: "" });
        } catch (err) {
            console.error(err);
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-400">
                <Loader2 className="animate-spin mb-4 text-amber-600" size={32} />
                <p className="font-bold tracking-tight uppercase text-[10px] tracking-[0.2em]">Synchronizing Classroom...</p>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 selection:bg-indigo-500/20 font-sans">
            {/* Header / Actions Section */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-12 gap-8 relative z-10">
                <div className="space-y-1">
                    <h1 className="text-5xl font-black text-slate-900 tracking-tighter leading-none">My Classrooms</h1>
                    <p className="text-slate-400 font-bold tracking-tight text-lg">Welcome back, {user?.name}.</p>
                </div>

                <div className="flex items-center gap-4">
                    {user?.role === "student" && (
                        <button
                            onClick={() => setIsJoinModalOpen(true)}
                            className="inline-flex items-center px-8 py-4 rounded-2xl bg-white border border-slate-200 text-slate-900 hover:border-amber-600 hover:text-amber-600 font-black transition-all duration-300 shadow-soft active:scale-95 uppercase tracking-widest text-xs"
                        >
                            <UserPlus size={18} className="mr-3" />
                            Join Class
                        </button>
                    )}
                    {(user?.role === "teacher" || user?.role === "superadmin") && (
                        <button
                            onClick={() => setIsCreateModalOpen(true)}
                            className="btn-accent px-8 py-4 rounded-2xl shadow-premium active:scale-95 text-xs inline-flex items-center"
                        >
                            <Plus size={18} className="mr-3" />
                            Create Class
                        </button>
                    )}
                </div>
            </div>

            {/* Error Message */}
            {error && (
                <div className="mb-10 p-5 rounded-3xl bg-red-50 border border-red-100/60 text-red-600 text-sm font-black flex items-center gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
                    <XCircle size={20} />
                    {error}
                </div>
            )}

            {classrooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-32 px-10 rounded-3xl bg-white/50 backdrop-blur-sm border border-slate-200 border-dashed text-center shadow-soft group">
                    <div className="p-8 rounded-2xl bg-slate-50 mb-8 text-slate-300 group-hover:bg-indigo-50 group-hover:text-indigo-200 transition-colors duration-500">
                        <BookOpen size={64} strokeWidth={1.5} />
                    </div>
                    <h3 className="text-3xl font-black text-slate-900 mb-3 tracking-tighter">No Classrooms Yet</h3>
                    <p className="text-slate-400 max-w-sm font-bold leading-relaxed">
                        {user?.role === "student" 
                            ? "You haven't joined any classrooms yet. Use a join code from your teacher to get started." 
                            : "Start your teaching journey by creating your first academic classroom today."}
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
                    {classrooms.map((cls) => (
                        <ClassroomCard key={cls.classroom_id} classroom={cls} />
                    ))}
                </div>
            )}

            {/* Join Modal */}
            {isJoinModalOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-6 bg-slate-900/40 backdrop-blur-xl animate-in fade-in duration-300">
                    <div className="w-full max-w-md bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-premium animate-in zoom-in-95 duration-300">
                        <div className="p-10">
                            <h2 className="text-4xl font-black text-slate-900 mb-3 tracking-tighter">Join Class</h2>
                            <p className="text-slate-400 font-bold mb-8 leading-relaxed">Enter the unique 6-character code provided by your instructor.</p>
                            
                            <form onSubmit={handleJoin} className="space-y-8">
                                <div className="space-y-3">
                                    <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Access Code</label>
                                    <input 
                                        type="text" 
                                        maxLength={6}
                                        placeholder="AB12XY"
                                        value={joinCode}
                                        onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                                        className="w-full px-4 py-5 bg-slate-50 border-2 border-slate-50 rounded-3xl text-slate-900 focus:outline-none focus:border-amber-600/30 focus:ring-8 focus:ring-amber-600/5 transition-all uppercase placeholder:text-slate-200 font-black tracking-[0.3em] text-center text-3xl"
                                        required
                                    />
                                </div>
                                
                                <div className="flex gap-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsJoinModalOpen(false)}
                                        className="flex-1 px-4 py-4 rounded-2xl bg-slate-50 text-slate-500 font-black hover:bg-slate-100 transition-all uppercase tracking-widest text-[11px]"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={submitting}
                                        className="flex-1 px-4 py-4 rounded-2xl bg-amber-600 text-slate-900 font-black hover:bg-amber-700 transition-all shadow-xl shadow-amber-100 disabled:opacity-50 flex items-center justify-center uppercase tracking-widest text-[11px]"
                                    >
                                        {submitting ? <Loader2 size={24} className="animate-spin" /> : "Join Classroom"}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {/* Create Modal */}
            {isCreateModalOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-6 bg-slate-900/40 backdrop-blur-xl animate-in fade-in duration-300">
                    <div className="w-full max-w-lg bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-premium animate-in zoom-in-95 duration-300">
                        <div className="p-10">
                            <h2 className="text-4xl font-black text-slate-900 mb-3 tracking-tighter">New Classroom</h2>
                            <p className="text-slate-400 font-bold mb-8 leading-relaxed">Establish a new intelligent space for your course materials and students.</p>
                            
                            <form onSubmit={handleCreate} className="space-y-6">
                                <div className="grid grid-cols-1 gap-6">
                                    <div className="space-y-3">
                                        <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Classroom Name</label>
                                        <input 
                                            type="text" 
                                            placeholder="e.g. Theoretical Physics Group"
                                            value={newClass.name}
                                            onChange={(e) => setNewClass({...newClass, name: e.target.value})}
                                            className="w-full px-6 py-4 bg-slate-50 border-2 border-slate-50 rounded-2xl text-slate-900 focus:outline-none focus:border-amber-600/30 transition-all font-bold placeholder:text-slate-200"
                                            required
                                        />
                                    </div>
                                    <div className="space-y-3">
                                        <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Subject Field</label>
                                        <input 
                                            type="text" 
                                            placeholder="e.g. Theoretical Physics Group"
                                            value={newClass.subject}
                                            onChange={(e) => setNewClass({...newClass, subject: e.target.value})}
                                            className="w-full px-6 py-4 bg-slate-50 border-2 border-slate-50 rounded-2xl text-slate-900 focus:outline-none focus:border-amber-600/30 transition-all font-bold placeholder:text-slate-200"
                                        />
                                    </div>
                                    <div className="space-y-3">
                                        <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 ml-4">Brief Orientation</label>
                                        <textarea 
                                            placeholder="What will students learn here?"
                                            rows={3}
                                            value={newClass.description}
                                            onChange={(e) => setNewClass({...newClass, description: e.target.value})}
                                            className="w-full px-6 py-4 bg-slate-50 border-2 border-slate-50 rounded-2xl text-slate-900 focus:outline-none focus:border-amber-600/30 transition-all font-bold placeholder:text-slate-200 resize-none"
                                        />
                                    </div>
                                </div>
                                
                                <div className="flex gap-4 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsCreateModalOpen(false)}
                                        className="flex-1 px-4 py-4 rounded-2xl bg-slate-50 text-slate-500 font-black hover:bg-slate-100 transition-all uppercase tracking-widest text-[11px]"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={submitting}
                                        className="flex-1 px-4 py-4 rounded-2xl bg-amber-600 text-slate-900 font-black hover:bg-amber-700 transition-all shadow-xl shadow-amber-100 disabled:opacity-50 flex items-center justify-center uppercase tracking-widest text-[11px]"
                                    >
                                        {submitting ? <Loader2 size={24} className="animate-spin" /> : "Launch Classroom"}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
