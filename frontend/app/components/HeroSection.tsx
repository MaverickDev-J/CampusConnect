"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

export default function HeroSection() {
    return (
        <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            className="relative z-10 text-center px-6 pt-16 pb-12 lg:pt-24 lg:pb-16"
        >
            {/* Badge */}
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2, duration: 0.5 }}
                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 mb-8"
            >
                <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                <span className="text-xs font-bold text-indigo-600 tracking-[0.2em] uppercase">
                    Connect Classroom Space
                </span>
            </motion.div>

            {/* Title */}
            <h2 className="text-4xl sm:text-5xl lg:text-7xl font-black text-slate-900 leading-[1.05] max-w-4xl mx-auto tracking-tight">
                Your Intelligent{" "}
                <span className="text-indigo-600">
                    Academic Hub.
                </span>
            </h2>

            {/* Subtitle */}
            <p className="mt-6 text-lg sm:text-xl text-slate-500 max-w-2xl mx-auto leading-relaxed">
                A unified classroom knowledge base for students and faculty. 
                Sync materials, engage with AI, and master your engineering journey.
            </p>

            {/* Decorative line */}
            <div className="mt-12 flex justify-center">
                <div className="w-32 h-[1px] bg-gradient-to-r from-transparent via-indigo-200 to-transparent rounded-full" />
            </div>
        </motion.section>
    );
}
