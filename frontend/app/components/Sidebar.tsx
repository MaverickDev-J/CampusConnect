"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
    Home,
    BookOpen,
    Calendar,
    ShieldCheck,
    Activity,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";
import { useAuth } from "@/app/context/auth-context";

export function Sidebar() {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [isOpenMobile, setIsOpenMobile] = useState(false);
    const pathname = usePathname();
    const { logout, user } = useAuth();

    const navItems = [
        { name: "Home", href: "/", icon: Home },
        { name: "Classrooms", href: "/classrooms", icon: BookOpen },
        { name: "Calendar", href: "/calendar", icon: Calendar },
        ...((user?.role === 'teacher' || user?.role === 'superadmin') && process.env.NEXT_PUBLIC_QUALITY_DASHBOARD === 'true'
            ? [{ name: 'Quality & Runs', href: '/quality', icon: Activity }] : []),
        ...(user?.role === "superadmin"
            ? [{ name: "Admin", href: "/admin", icon: ShieldCheck }]
            : []),
    ];

    const isActive = (href: string) => {
        if (href === "/") return pathname === "/";
        return pathname.startsWith(href);
    };

    useEffect(() => {
        const handleToggle = () => setIsOpenMobile(prev => !prev);
        const handleClose = () => setIsOpenMobile(false);
        window.addEventListener("toggle-mobile-sidebar", handleToggle);
        window.addEventListener("close-mobile-sidebar", handleClose);
        return () => {
            window.removeEventListener("toggle-mobile-sidebar", handleToggle);
            window.removeEventListener("close-mobile-sidebar", handleClose);
        };
    }, []);

    // Close mobile drawer on route changes
    useEffect(() => {
        setIsOpenMobile(false);
    }, [pathname]);

    return (
        <>
            {/* Desktop Sidebar (Sticky, only on md and larger) */}
            <aside
                className={`sticky left-0 top-0 h-screen bg-white border-r border-slate-200 z-40 transition-all duration-150 hidden md:flex flex-col shrink-0 ${
                    isCollapsed ? "w-16" : "w-56"
                }`}
            >
                {/* Logo */}
                <div className={`${isCollapsed ? "px-3" : "px-6"} py-6 flex items-center justify-between`}>
                    {!isCollapsed && (
                        <div className="flex items-center w-full mb-3">
                            <img src="/brand/logo_full.png" alt="Classroom Connect" className="w-[160px] h-auto object-contain mix-blend-multiply" />
                        </div>
                    )}
                    {isCollapsed && (
                        <Link href="/" className="w-10 h-10 bg-accent/20 rounded-2xl flex items-center justify-center mx-auto transition-all duration-150 hover:bg-accent/30 shadow-sm shadow-accent/10">
                            <BookOpen size={22} className="text-secondary" />
                        </Link>
                    )}
                </div>

                {/* Nav Items */}
                <nav className={`flex-1 ${isCollapsed ? "px-2" : "px-4"} space-y-2 mt-2`}>
                    {navItems.map((item) => {
                        const active = isActive(item.href);
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                title={isCollapsed ? item.name : undefined}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 group ${
                                    active
                                        ? "bg-blue-50 text-blue-700"
                                        : "text-slate-500 hover:bg-slate-50 hover:text-blue-600"
                                }`}
                            >
                                 <item.icon
                                    size={22}
                                    className={active ? "text-blue-700" : "group-hover:text-blue-600 transition-colors"}
                                />
                                {!isCollapsed && (
                                    <span className="font-bold text-sm tracking-tight">{item.name}</span>
                                )}
                            </Link>
                        );
                    })}
                </nav>

                <div className={`px-4 pb-8 space-y-2 pt-6`}>
                    <div className="h-px bg-slate-100 mb-6" />
                </div>

                {/* Collapse toggle */}
                <button
                    suppressHydrationWarning
                    aria-label={isCollapsed ? "Expand navigation" : "Collapse navigation"}
                    onClick={() => setIsCollapsed(!isCollapsed)}
                    className="absolute -right-3 top-20 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-soft text-slate-500 hover:text-blue-600 z-50 transition-colors"
                >
                    {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
                </button>
            </aside>

            {/* Mobile Drawer (Responsive Overlay below md) */}
            <AnimatePresence>
                {isOpenMobile && (
                    <>
                        {/* Backdrop overlay */}
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 0.5 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setIsOpenMobile(false)}
                            className="fixed inset-0 bg-slate-900/60 z-50 md:hidden"
                        />

                        {/* Drawer body */}
                        <motion.aside
                            initial={{ x: "-100%" }}
                            animate={{ x: 0 }}
                            exit={{ x: "-100%" }}
                            transition={{ duration: 0.16, ease: "easeOut" }}
                            className="fixed left-0 top-0 h-screen w-72 bg-white z-50 shadow-premium flex flex-col md:hidden border-r border-slate-200"
                        >
                            {/* Logo */}
                            <div className="px-6 py-6 flex items-center justify-between">
                                <div className="flex items-center w-full mb-3">
                                    <img src="/brand/logo_full.png" alt="Classroom Connect" className="w-[160px] h-auto object-contain mix-blend-multiply" />
                                </div>
                            </div>

                            {/* Nav Items */}
                            <nav className="flex-1 px-4 space-y-2 mt-2">
                                {navItems.map((item) => {
                                    const active = isActive(item.href);
                                    return (
                                        <Link
                                            key={item.name}
                                            href={item.href}
                                            onClick={() => setIsOpenMobile(false)}
                                            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 group ${
                                                active
                                                    ? "bg-blue-50 text-blue-700"
                                                    : "text-slate-500 hover:bg-slate-50 hover:text-blue-600"
                                            }`}
                                        >
                                             <item.icon
                                                size={22}
                                                className={active ? "text-blue-700" : "group-hover:text-blue-600 transition-colors"}
                                            />
                                            <span className="font-bold text-sm tracking-tight">{item.name}</span>
                                        </Link>
                                    );
                                })}
                            </nav>

                            <div className="px-4 pb-8 space-y-2 pt-6">
                                <div className="h-px bg-slate-100 mb-6" />
                            </div>
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </>
    );
}
