"use client";

import { useState, useEffect } from "react";
import { X, Sparkles, ArrowRight } from "lucide-react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

export default function DemoBanner() {
    const [dismissed, setDismissed] = useState(true); // Start hidden to avoid flash

    useEffect(() => {
        // Check sessionStorage on mount
        const wasDismissed = sessionStorage.getItem("demo-banner-dismissed");
        setDismissed(wasDismissed === "true");
    }, []);

    const handleDismiss = () => {
        setDismissed(true);
        sessionStorage.setItem("demo-banner-dismissed", "true");
    };

    return (
        <AnimatePresence>
            {!dismissed && (
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3, ease: "easeOut" }}
                    className="relative mx-8 mt-4 mb-2"
                >
                    <div className="relative overflow-hidden rounded-2xl border border-amber-200/60 bg-gradient-to-r from-amber-50/80 via-orange-50/60 to-amber-50/80 backdrop-blur-sm px-6 py-3.5 flex items-center justify-between gap-4">
                        {/* Decorative gradient line at top */}
                        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-amber-400 to-transparent" />

                        <div className="flex items-center gap-3 min-w-0">
                            <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-amber-100 flex items-center justify-center">
                                <Sparkles size={16} className="text-amber-600" />
                            </div>
                            <p className="text-sm font-bold text-slate-700 truncate">
                                You&apos;re exploring CampusConnect in{" "}
                                <span className="text-amber-700 font-black">demo mode</span>
                                <span className="hidden sm:inline text-slate-500 font-medium">
                                    {" "}— Try chatting with the AI or uploading a PDF
                                </span>
                            </p>
                        </div>

                        <div className="flex items-center gap-3 flex-shrink-0">
                            <Link
                                href="/signup"
                                className="hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600 text-white text-[10px] font-black uppercase tracking-wider hover:bg-amber-700 transition-colors shadow-sm shadow-amber-200"
                            >
                                Sign Up <ArrowRight size={12} />
                            </Link>
                            <button
                                onClick={handleDismiss}
                                className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-white/60 transition-all"
                                aria-label="Dismiss demo banner"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
