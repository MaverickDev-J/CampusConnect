"use client";

import { Search, GraduationCap, Bell, LogOut, ChevronDown, User } from "lucide-react";
import { useAuth } from "@/app/context/auth-context";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import { Megaphone, Calendar as CalendarIcon, Loader2 as LoaderIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { API_BASE_URL } from "@/app/config";

export default function Header() {
    const { user, logout } = useAuth();
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const [searchQuery, setSearchQuery] = useState("");
    const [showNotifications, setShowNotifications] = useState(false);
    const [notifications, setNotifications] = useState<any[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [showProfileMenu, setShowProfileMenu] = useState(false);

    // Sync header search with URL
    useEffect(() => {
        const q = searchParams.get("q");
        if (q) setSearchQuery(q);
        else setSearchQuery("");
    }, [searchParams]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchQuery.trim()) {
            router.push(`/classrooms?q=${encodeURIComponent(searchQuery.trim())}`);
        } else {
            router.push("/classrooms");
        }
    };

    const fetchNotifications = useCallback(async () => {
        if (!user?.token) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/notifications`, {
                headers: { "Authorization": `Bearer ${user.token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setNotifications(data.notifications);
                setUnreadCount(data.count);
            }
        } catch (err) {
            console.error("Failed to fetch notifications:", err);
        }
    }, [user?.token]);

    useEffect(() => {
        fetchNotifications();
        const interval = setInterval(fetchNotifications, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, [fetchNotifications]);

    const markAsRead = async (id: string, link: string) => {
        if (!user?.token) return;
        try {
            await fetch(`${API_BASE_URL}/api/notifications/${id}/read`, {
                method: "PATCH",
                headers: { "Authorization": `Bearer ${user.token}` }
            });
            fetchNotifications();
            // Optional: navigate to link
        } catch (err) {
            console.error("Failed to mark as read:", err);
        }
    };

    const tabs = [
        { id: "dashboard", label: "Dashboard", path: "/" },
    ];

    const activeTab = "Dashboard";

    // Get user initials for avatar
    const initials = user?.name
        ? user.name
            .split(" ")
            .map((n) => n[0])
            .join("")
            .toUpperCase()
            .slice(0, 2)
        : "CC";

    return (
        <header className="relative z-40 flex items-center justify-between px-8 h-24 sticky top-0 transition-all">
            <div className="flex-shrink-0 flex items-center gap-4">
                <h1 className="text-2xl font-black text-slate-900 tracking-tighter">
                    {pathname === "/" ? "Dashboard" : "Classroom"}
                </h1>
            </div>

            {/* Centered Search */}
            <div className="flex-1 flex justify-center max-w-xl mx-auto px-8">
                <div className="relative w-full group">
                    <div className="absolute inset-0 bg-primary/5 rounded-2xl blur-xl group-focus-within:bg-primary/10 transition-all duration-500 opacity-0 group-focus-within:opacity-100" />
                    <form 
                        onSubmit={handleSearch}
                        className="relative glass rounded-2xl flex items-center px-5 py-3 border-white/40 shadow-soft group-focus-within:shadow-premium group-focus-within:border-amber-600/20 transition-all duration-300"
                    >
                        <Search className="w-5 h-5 text-slate-400 group-focus-within:text-amber-600 transition-colors" />
                            <input
                                suppressHydrationWarning
                                type="text"
                                value={searchQuery}
                                onChange={(e) => {
                                    setSearchQuery(e.target.value);
                                    if (pathname === "/classrooms") {
                                        router.replace(`/classrooms?q=${encodeURIComponent(e.target.value)}`);
                                    }
                                }}
                                placeholder="Search classrooms..."
                                className="bg-transparent border-none outline-none flex-1 ml-3 text-sm font-semibold text-slate-700 placeholder:text-slate-400"
                            />
                    </form>
                </div>
            </div>

            {/* Right side actions */}
            <div className="flex items-center gap-5">
                <div className="relative">
                    <button 
                        suppressHydrationWarning
                        onClick={() => setShowNotifications(!showNotifications)}
                        className="relative flex items-center justify-center w-12 h-12 rounded-2xl bg-white/50 border border-slate-200 hover:border-amber-600/40 hover:bg-white transition-all shadow-soft group"
                    >
                        <Bell className="w-5 h-5 text-slate-400 group-hover:text-amber-600 transition-colors" />
                        {unreadCount > 0 && (
                            <span className="absolute top-3.5 right-3.5 w-2.5 h-2.5 bg-accent rounded-full border-2 border-white shadow-lg animate-pulse" />
                        )}
                    </button>

                    <AnimatePresence>
                        {showNotifications && (
                            <motion.div 
                                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute right-0 top-full mt-4 w-96 glass rounded-[2.5rem] shadow-premium p-8 z-50"
                            >
                                <div className="flex items-center justify-between mb-6">
                                    <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">Notifications</h3>
                                    {unreadCount > 0 && (
                                        <span className="px-2.5 py-1 rounded-full bg-amber-100 text-[10px] text-amber-700 font-black uppercase tracking-wider">{unreadCount} New</span>
                                    )}
                                </div>
                                <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                                    {notifications.length === 0 ? (
                                        <div className="text-center py-10">
                                            <div className="w-12 h-12 bg-slate-50 rounded-2xl flex items-center justify-center mx-auto mb-3">
                                                <Bell className="text-slate-200" size={24} />
                                            </div>
                                            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest">Quiet here...</p>
                                        </div>
                                    ) : (
                                        notifications.map((notif) => (
                                            <Link 
                                                key={notif.notification_id}
                                                href={notif.link || "#"}
                                                onClick={() => markAsRead(notif.notification_id, notif.link)}
                                                >
                                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-sm ${
                                                    notif.type === "announcement" ? "bg-amber-100 text-amber-600" : "bg-emerald-100 text-emerald-600"
                                                }`}>
                                                    {notif.type === "announcement" ? <Megaphone size={18} /> : <CalendarIcon size={18} />}
                                                </div>
                                                <div className="flex-1">
                                                    <p className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors leading-tight mb-1">
                                                        {notif.title}
                                                    </p>
                                                    <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed italic">
                                                        {notif.message}
                                                    </p>
                                                    <div className="mt-2 flex items-center justify-between">
                                                        <span className="text-[9px] text-slate-300 font-black uppercase tracking-wider">
                                                            {new Date(notif.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                        <span className="text-[9px] text-amber-600 opacity-0 group-hover:opacity-100 font-black uppercase tracking-wider transition-opacity">View Details</span>
                                                    </div>
                                                </div>
                                            </Link>
                                        ))
                                    )}
                                </div>
                                {notifications.length > 0 && (
                                    <button 
                                        onClick={async () => {
                                            await fetch(`${API_BASE_URL}/api/notifications/clear`, {
                                                method: "DELETE",
                                                headers: { "Authorization": `Bearer ${user?.token}` }
                                            });
                                            fetchNotifications();
                                        }}
                                        className="w-full mt-6 py-4 text-[10px] font-black text-slate-400 hover:text-amber-600 uppercase tracking-[0.2em] border-t border-slate-100 transition-colors"
                                    >
                                        Clear all alerts
                                    </button>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                <div className="relative flex items-center gap-3 pl-2 border-l border-slate-200">
                    <div className="text-right hidden sm:block">
                        <div className="text-sm font-black text-slate-900 leading-none">{user?.name}</div>
                        <div className="text-[10px] text-amber-600 font-black uppercase tracking-widest mt-1 opacity-70 border-b border-amber-600/20 pb-0.5">{user?.role}</div>
                    </div>
                    <div 
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                        className="relative flex items-center justify-center w-12 h-12 rounded-2xl bg-white shadow-soft border border-slate-100 group cursor-pointer hover:border-primary/20 transition-all overflow-hidden"
                    >
                        <div className="absolute inset-0 bg-primary opacity-0 group-hover:opacity-5 transition-opacity" />
                        <span className="text-sm font-black text-primary relative z-10 transition-transform group-hover:scale-110 duration-300">
                            {initials}
                        </span>
                    </div>

                    <AnimatePresence>
                        {showProfileMenu && (
                            <motion.div
                                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute right-0 top-full mt-4 w-72 glass rounded-[2rem] shadow-premium p-4 z-50 border border-white/40"
                            >
                                <div className="px-4 py-4 mb-2 border-b border-slate-100/50">
                                    <div className="text-sm font-black text-slate-900 leading-none mb-1">{user?.name}</div>
                                    <div className="text-[11px] text-slate-400 font-medium truncate">{user?.email}</div>
                                    <div className="mt-3 inline-flex px-2 py-0.5 rounded-lg bg-primary/10 text-primary text-[9px] font-black uppercase tracking-wider">
                                        {user?.role}
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <Link
                                        href="/profile"
                                        onClick={() => setShowProfileMenu(false)}
                                        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-slate-600 hover:bg-primary/5 hover:text-primary transition-all group"
                                    >
                                        <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                                            <User size={16} />
                                        </div>
                                        <span className="text-sm font-bold">Account Profile</span>
                                    </Link>
                                    <button
                                        onClick={logout}
                                        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-slate-600 hover:bg-red-50 hover:text-red-600 transition-all group"
                                    >
                                        <div className="w-8 h-8 rounded-lg bg-red-50/50 flex items-center justify-center group-hover:bg-red-100 transition-colors">
                                            <LogOut size={16} className="text-red-500" />
                                        </div>
                                        <span className="text-sm font-bold">Sign out</span>
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </header>
    );
}
