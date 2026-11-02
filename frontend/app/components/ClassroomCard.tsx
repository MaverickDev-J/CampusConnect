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
            whileHover={{ y: -2, transition: { duration: 0.15 } }}
            onClick={handleCardClick}
            className="group block rounded-3xl bg-white border border-slate-200/60 hover:border-primary/30 transition-all duration-150 relative overflow-hidden shadow-soft hover:shadow-md cursor-pointer"
        >
            <div className="p-6 relative z-10">
                <div className="flex justify-between items-start mb-5">
                    <div className={`p-4 rounded-2xl shadow-sm transition-transform  duration-150 ${
                        classroom.subject?.toLowerCase().includes("ml") ? "bg-primary/10 text-primary" :
                        classroom.subject?.toLowerCase().includes("cs") ? "bg-emerald-50 text-emerald-600" :
                        "bg-blue-50 text-blue-600"
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

                <div className="mb-5 h-10 flex flex-col justify-center">
                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-1">Lead Instructor</span>
                    <p className="text-slate-900 text-sm font-black tracking-tight flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                        Taught by {classroom.created_by_name || "Department Faculty"}
                    </p>
                </div>

                <div className="flex items-center justify-between pt-6 border-t border-slate-100/60">
                    <div className="flex items-center gap-2">
                        <div className="status-dot-animated" />
                        <span className="text-primary text-xs font-black uppercase tracking-widest  transition-all duration-150">
                            Open classroom
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
