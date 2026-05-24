"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { type Classroom } from "@/app/lib/api";
import { Users, BookOpen, ArrowRight, MessageSquare } from "lucide-react";
import { motion } from "framer-motion";

interface ClassroomCardProps {
    classroom: Classroom;
}

export function ClassroomCard({ classroom }: ClassroomCardProps) {
    const router = useRouter();

    const handleCardClick = () => {
        router.push(`/classroom/${classroom.classroom_id}`);
    };

    return (
        <motion.div 
            whileHover={{ y: -12, scale: 1.02, transition: { duration: 0.4, ease: "easeOut" } }}
            onClick={handleCardClick}
            className="group block rounded-3xl bg-white border border-slate-200/60 hover:border-primary/30 transition-all duration-500 relative overflow-hidden shadow-soft hover:shadow-[0_30px_60px_-12px_rgba(0,102,255,0.15)] cursor-pointer"
        >
            {/* Subject-Themed Gradient Background Pattern */}
            <div className={`absolute inset-0 opacity-[0.03] pointer-events-none transition-opacity group-hover:opacity-[0.08] ${
                classroom.subject?.toLowerCase().includes("ml") ? "bg-[radial-gradient(circle_at_top_right,#0066FF_0%,transparent_70%)]" :
                classroom.subject?.toLowerCase().includes("cs") ? "bg-[radial-gradient(circle_at_top_right,#10b981_0%,transparent_70%)]" :
                "bg-[radial-gradient(circle_at_top_right,#f59e0b_0%,transparent_70%)]"
            }`} />

            {/* Top Accent Bar with glassmorphism flare */}
            <div className="h-2 w-full relative overflow-hidden">
                <div className={`absolute inset-0 bg-gradient-to-r ${
                    classroom.subject?.toLowerCase().includes("ml") ? "from-primary to-blue-600" :
                    classroom.subject?.toLowerCase().includes("cs") ? "from-emerald-500 to-emerald-600" :
                    "from-amber-500 to-amber-600"
                }`} />
                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/40 to-white/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000 ease-in-out" />
            </div>

            <div className="p-8 relative z-10">
                <div className="flex justify-between items-start mb-8">
                    <div className={`p-4 rounded-2xl shadow-sm transition-transform group-hover:rotate-6 group-hover:scale-110 duration-500 ${
                        classroom.subject?.toLowerCase().includes("ml") ? "bg-primary/10 text-primary" :
                        classroom.subject?.toLowerCase().includes("cs") ? "bg-emerald-50 text-emerald-600" :
                        "bg-amber-50 text-amber-600"
                    }`}>
                        <BookOpen size={28} />
                    </div>
                    <div className="flex items-center gap-2 text-slate-400 text-[10px] font-black uppercase tracking-widest bg-slate-50 px-3 py-1.5 rounded-full border border-slate-100">
                        <Users size={14} className="text-slate-400" />
                        <span>{classroom.member_count} Members</span>
                    </div>
                </div>

                <h3 className="text-2xl font-black text-slate-900 mb-2 group-hover:text-primary transition-colors tracking-tighter leading-none truncate pr-2">
                    {classroom.name}
                </h3>
                
                {classroom.subject && (
                    <div className="inline-block px-2.5 py-1 rounded-lg bg-primary/5 mb-4">
                        <p className="text-primary text-[10px] font-black uppercase tracking-[0.2em]">
                            {classroom.subject}
                        </p>
                    </div>
                )}

                <div className="mb-8 h-10 flex flex-col justify-center">
                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-1">Lead Instructor</span>
                    <p className="text-slate-900 text-sm font-black tracking-tight flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                        Taught by {classroom.created_by_name || "Department Faculty"}
                    </p>
                </div>

                <div className="flex items-center justify-between pt-6 border-t border-slate-100/60">
                    <div className="flex items-center gap-2">
                        <div className="status-dot-animated" />
                        <span className="text-primary text-xs font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 transform translate-x-[-10px] group-hover:translate-x-0 transition-all duration-500">
                            Enter Hub
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Link 
                            href={`/classroom/${classroom.classroom_id}/chat`}
                            onClick={(e) => e.stopPropagation()}
                            className="w-11 h-11 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-400 hover:bg-primary/10 hover:text-primary transition-all duration-300 border border-transparent hover:border-primary/20 shadow-sm"
                            title="Direct Chat"
                        >
                            <MessageSquare size={18} />
                        </Link>
                        <div className="w-11 h-11 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-primary group-hover:text-white group-hover:shadow-lg group-hover:shadow-primary/25 transition-all duration-300">
                            <ArrowRight size={22} />
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
