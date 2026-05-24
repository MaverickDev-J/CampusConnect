"use client";

import { motion } from "framer-motion";
import { BookOpen, ChevronRight } from "lucide-react";
import { cn } from "@/app/lib/cn";

interface YearSelectorProps {
    selectedYear: number;
    onSelect: (year: number) => void;
}

const years = [1, 2, 3, 4];

export default function YearSelector({ selectedYear, onSelect }: YearSelectorProps) {
    return (
        <div className="relative z-10 px-6 lg:px-10">
            <div className="flex items-center gap-3 mb-5">
                <BookOpen className="w-4 h-4 text-slate-500" />
                <span className="text-xs uppercase tracking-[0.2em] text-slate-500 font-medium">
                    Select Your Year
                </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {years.map((year, index) => {
                    const isActive = selectedYear === year;
                    return (
                        <motion.button
                            key={year}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 * index, duration: 0.4, ease: "easeOut" }}
                            whileHover={{ scale: 1.03, y: -2 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => onSelect(year)}
                            className={cn(
                                "relative group cursor-pointer rounded-2xl p-5 text-left transition-all duration-300",
                                "glass-card glow-cyan-hover",
                                isActive && "glow-purple"
                            )}
                        >
                            {/* Year number */}
                            <div className="flex items-center justify-between mb-3">
                                <span
                                    className={cn(
                                        "text-3xl font-black tracking-tighter",
                                        isActive
                                            ? "text-purple-400 text-glow"
                                            : "text-slate-600 group-hover:text-cyan-400 transition-colors"
                                    )}
                                >
                                    0{year}
                                </span>
                                <ChevronRight
                                    className={cn(
                                        "w-4 h-4 transition-all duration-300",
                                        isActive
                                            ? "text-purple-400 translate-x-0 opacity-100"
                                            : "text-slate-600 -translate-x-1 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 group-hover:text-cyan-400"
                                    )}
                                />
                            </div>

                            {/* Label */}
                            <span
                                className={cn(
                                    "text-sm font-bold tracking-widest",
                                    isActive ? "text-white" : "text-slate-400 group-hover:text-slate-200 transition-colors"
                                )}
                            >
                                YEAR {year}
                            </span>

                            {/* Semester info */}
                            <p className="mt-1 text-xs text-slate-500">
                                Sem {year * 2 - 1} &middot; Sem {year * 2}
                            </p>

                            {/* Active indicator */}
                            {isActive && (
                                <motion.div
                                    layoutId="activeYearIndicator"
                                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-1 bg-purple-500 rounded-t-full"
                                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                                />
                            )}
                        </motion.button>
                    );
                })}
            </div>
        </div>
    );
}
