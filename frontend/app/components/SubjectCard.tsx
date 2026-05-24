"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import * as LucideIcons from "lucide-react";
import type { Subject } from "@/app/data";
import { cn } from "@/app/lib/cn";

interface SubjectCardProps {
    subject: Subject;
    index: number;
    fileCount?: number;
}

export default function SubjectCard({ subject, index, fileCount = 0 }: SubjectCardProps) {
    // Dynamically resolve the icon
    const IconComponent =
        (LucideIcons as any)[subject.icon] ||
        LucideIcons.BookOpen;

    return (
        <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * index, duration: 0.35, ease: "easeOut" }}
            whileHover={{ scale: 1.04, y: -3 }}
            className={cn(
                "group relative cursor-pointer rounded-xl p-4 transition-all duration-300",
                "glass-card-sm glow-cyan-hover"
            )}
        >
            <div className="flex items-start gap-3">
                {/* Icon */}
                <div className="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/15 group-hover:bg-cyan-500/15 group-hover:border-cyan-500/30 transition-all">
                    <IconComponent className="w-4 h-4 text-cyan-400" />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-slate-200 group-hover:text-white transition-colors leading-tight truncate">
                        {subject.name}
                    </h4>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400 tracking-wider">
                            {subject.code}
                        </span>
                        <span className="text-[10px] text-slate-500">
                            {subject.credits} Credits
                        </span>
                        {fileCount > 0 && (
                            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                {fileCount} {fileCount === 1 ? 'File' : 'Files'}
                            </span>
                        )}
                    </div>
                </div>

                {/* Hover arrow */}
                <ArrowRight
                    className="flex-shrink-0 w-4 h-4 text-slate-600 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 group-hover:text-cyan-400 transition-all duration-300 mt-0.5"
                />
            </div>
        </motion.div>
    );
}
