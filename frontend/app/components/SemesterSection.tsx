"use client";

import { motion, AnimatePresence, Variants } from "framer-motion";
import { GraduationCap } from "lucide-react";
import SubjectCard from "./SubjectCard";
import type { Semester } from "@/app/data";

interface SemesterSectionProps {
    semesters: Semester[];
    yearId: number;
    fileCounts?: Record<string, number>;
}

const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.08,
            delayChildren: 0.1,
        },
    },
    exit: {
        opacity: 0,
        y: -10,
        transition: { duration: 0.2, ease: "easeIn" },
    },
};

const semesterVariants: Variants = {
    hidden: { opacity: 0, y: 25 },
    visible: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.45, ease: "easeOut" },
    },
};

export default function SemesterSection({ semesters, yearId, fileCounts }: SemesterSectionProps) {
    return (
        <div className="relative z-10 px-6 lg:px-10 mt-8">
            <AnimatePresence mode="wait">
                <motion.div
                    key={yearId}
                    variants={containerVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    className="space-y-8"
                >
                    {semesters.map((semester) => (
                        <motion.div
                            key={semester.id}
                            variants={semesterVariants}
                            className="glass-card p-6"
                        >
                            {/* Semester heading */}
                            <div className="flex items-center gap-3 mb-5">
                                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20">
                                    <GraduationCap className="w-4 h-4 text-purple-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-bold text-white tracking-wide">
                                        {semester.label}
                                    </h3>
                                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">
                                        {semester.subjects.length} Courses
                                    </p>
                                </div>
                                <div className="flex-1 h-px bg-gradient-to-r from-slate-700/50 to-transparent ml-3" />
                            </div>

                            {/* Subjects grid */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {semester.subjects.map((subject, index) => (
                                    <SubjectCard
                                        key={subject.id}
                                        subject={subject}
                                        index={index}
                                        fileCount={fileCounts?.[subject.slug] || 0}
                                    />
                                ))}
                            </div>
                        </motion.div>
                    ))}
                </motion.div>
            </AnimatePresence>
        </div>
    );
}
