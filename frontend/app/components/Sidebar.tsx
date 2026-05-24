"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Home,
    BookOpen,
    Calendar,
    ShieldCheck,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";
import { useAuth } from "@/app/context/auth-context";

export function Sidebar() {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const pathname = usePathname();
    const { logout, user } = useAuth();

    const navItems = [
        { name: "Home", href: "/", icon: Home },
        { name: "Classrooms", href: "/classrooms", icon: BookOpen },
        { name: "Calendar", href: "/calendar", icon: Calendar },
        ...(user?.role === "superadmin"
            ? [{ name: "Admin", href: "/admin", icon: ShieldCheck }]
            : []),
    ];

    const isActive = (href: string) => {
        if (href === "/") return pathname === "/";
        return pathname.startsWith(href);
    };

    return (
        <aside
            className={`fixed left-0 top-0 h-screen bg-white border-r border-slate-200 z-50 transition-all duration-300 flex flex-col shadow-soft ${
                isCollapsed ? "w-20" : "w-64"
            }`}
        >
            {/* Logo */}
            <div className="p-8 flex items-center justify-between">
                {!isCollapsed && (
                    <div className="flex items-center w-full mb-10 mt-2">
                        <img src="/brand/logo_full.png" alt="Classroom Connect" className="w-[180px] h-auto object-contain mix-blend-multiply" />
                    </div>
                )}
                {isCollapsed && (
                    <Link href="/" className="w-10 h-10 bg-accent/20 rounded-2xl flex items-center justify-center mx-auto transition-all duration-300 hover:bg-accent/30 shadow-sm shadow-accent/10">
                        <BookOpen size={22} className="text-secondary" />
                    </Link>
                )}
            </div>

            {/* Nav Items */}
            <nav className="flex-1 px-4 space-y-2 mt-2">
                {navItems.map((item) => {
                    const active = isActive(item.href);
                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            title={isCollapsed ? item.name : undefined}
                            className={`flex items-center gap-4 px-4 py-3.5 rounded-2xl transition-all duration-300 group ${
                                active
                                    ? "bg-indigo-600 text-white shadow-xl shadow-indigo-600/20 scale-[1.02]"
                                    : "text-slate-500 hover:bg-slate-50 hover:text-amber-600"
                            }`}
                        >
                             <item.icon
                                size={22}
                                className={active ? "text-white" : "group-hover:text-amber-600 transition-colors"}
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
                {/* User section removed as it is present in top header */}
            </div>

            {/* Collapse toggle */}
            <button
                suppressHydrationWarning
                onClick={() => setIsCollapsed(!isCollapsed)}
                className="absolute -right-3 top-20 w-6 h-6 bg-white border border-slate-200 rounded-full flex items-center justify-center shadow-soft text-slate-500 hover:text-amber-600 z-50 transition-colors"
            >
                {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
        </aside>
    );
}
