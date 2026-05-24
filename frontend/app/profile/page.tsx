"use client";

import { useAuth } from "@/app/context/auth-context";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import { API_BASE_URL } from "@/app/config";
import { motion, AnimatePresence } from "framer-motion";
import { 
    User, 
    Mail, 
    Shield, 
    Calendar as CalendarIcon, 
    BookOpen, 
    ArrowLeft,
    Settings,
    Bell,
    Lock,
    X,
    CheckCircle2,
    Loader2
} from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";

export default function ProfilePage() {
    const { user, updateProfile, changePassword } = useAuth();
    const { classrooms } = useClassrooms();
    const [activeTasksCount, setActiveTasksCount] = useState(0);
    const [isEditingProfile, setIsEditingProfile] = useState(false);
    const [isChangingPassword, setIsChangingPassword] = useState(false);
    const [isUpdating, setIsUpdating] = useState(false);
    const [successMsg, setSuccessMsg] = useState<string | null>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // Form states
    const [newName, setNewName] = useState(user?.name || "");
    const [passwordData, setPasswordData] = useState({ old_password: "", new_password: "", confirm_password: "" });

    // Notification states (mock persistence)
    const [notifications, setNotifications] = useState({
        email: true,
        inApp: true,
        marketing: false
    });

    useEffect(() => {
        if (user?.token) {
            // Fetch calendar events to count tasks (deadlines/exams)
            fetch(`${API_BASE_URL}/api/calendar/events`, {
                headers: { "Authorization": `Bearer ${user.token}` }
            })
            .then(res => res.json())
            .then(data => {
                const tasks = data.events.filter((e: any) => e.type === "deadline" || e.type === "exam");
                setActiveTasksCount(tasks.length);
            })
            .catch(err => console.error("Failed to fetch tasks count:", err));
        }

        // Load notifications from local storage if needed
        const saved = localStorage.getItem("cm_notifications");
        if (saved) setNotifications(JSON.parse(saved));
    }, [user?.token]);

    const handleUpdateProfile = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsUpdating(true);
        setErrorMsg(null);
        try {
            await updateProfile(newName);
            setSuccessMsg("Profile updated successfully!");
            setTimeout(() => { setSuccessMsg(null); setIsEditingProfile(false); }, 2000);
        } catch (err: any) {
            setErrorMsg(err.message || "Failed to update profile");
        } finally {
            setIsUpdating(false);
        }
    };

    const handleChangePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        if (passwordData.new_password !== passwordData.confirm_password) {
            setErrorMsg("Passwords do not match");
            return;
        }
        setIsUpdating(true);
        setErrorMsg(null);
        try {
            await changePassword({ 
                old_password: passwordData.old_password, 
                new_password: passwordData.new_password 
            });
            setSuccessMsg("Password changed successfully!");
            setPasswordData({ old_password: "", new_password: "", confirm_password: "" });
            setTimeout(() => { setSuccessMsg(null); setIsChangingPassword(false); }, 2000);
        } catch (err: any) {
            setErrorMsg(err.message || "Failed to change password");
        } finally {
            setIsUpdating(false);
        }
    };

    const toggleNotification = (key: keyof typeof notifications) => {
        const updated = { ...notifications, [key]: !notifications[key] };
        setNotifications(updated);
        localStorage.setItem("cm_notifications", JSON.stringify(updated));
    };

    const initials = user?.name
        ? user.name
            .split(" ")
            .map((n) => n[0])
            .join("")
            .toUpperCase()
            .slice(0, 2)
        : "CC";

    return (
        <div className="flex min-h-screen bg-slate-50">
            <Sidebar />
            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300 relative overflow-hidden text-slate-900">
                {/* Background Brand Glows */}
                <div className="fixed inset-0 pointer-events-none">
                    <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-yellow-400/5 blur-[120px] rounded-full" />
                    <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full" />
                </div>

                <Header />

                <div className="max-w-5xl mx-auto px-8 py-12 relative z-10">
                    <div className="mb-12 flex items-center justify-between">
                        <Link href="/" className="flex items-center gap-2 text-slate-400 hover:text-primary transition-colors group">
                            <div className="w-10 h-10 rounded-xl bg-white border border-slate-100 flex items-center justify-center group-hover:border-primary/20 shadow-soft">
                                <ArrowLeft size={18} />
                            </div>
                            <span className="text-xs font-black uppercase tracking-widest">Dashboard</span>
                        </Link>
                        <h1 className="text-3xl font-black text-slate-900 tracking-tighter">Account Profile</h1>
                        <div className="w-10 h-10" />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                        {/* Profile Hero Card */}
                        <motion.div 
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="lg:col-span-1"
                        >
                            <div className="bg-white rounded-[3rem] p-10 shadow-premium border border-slate-100 flex flex-col items-center text-center relative overflow-hidden h-full">
                                <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-br from-primary/10 to-transparent" />
                                
                                <div className="relative mb-8">
                                    <div className="w-32 h-32 rounded-[2.5rem] bg-primary flex items-center justify-center text-white text-4xl font-black shadow-2xl shadow-primary/30 relative z-10 transition-transform hover:scale-105 duration-500">
                                        {initials}
                                    </div>
                                    <div className="absolute -bottom-2 -right-2 w-10 h-10 bg-emerald-500 rounded-2xl border-4 border-white flex items-center justify-center text-white z-20 shadow-lg">
                                        <div className="w-2.5 h-2.5 bg-white rounded-full animate-pulse" />
                                    </div>
                                </div>

                                <h2 className="text-2xl font-black text-slate-900 tracking-tight mb-2">{user?.name}</h2>
                                <p className="text-primary font-black text-[10px] uppercase tracking-[0.2em] mb-8 flex items-center gap-2">
                                    <Shield size={12} /> {user?.role}
                                </p>

                                <div className="w-full space-y-4 pt-6 border-t border-slate-50">
                                    <div className="flex items-center gap-4 text-left p-4 rounded-2xl bg-slate-50/50 border border-slate-100 group transition-all hover:bg-white hover:shadow-soft">
                                        <div className="w-10 h-10 rounded-xl bg-white border border-slate-100 flex items-center justify-center text-slate-400 group-hover:text-primary transition-colors">
                                            <Mail size={18} />
                                        </div>
                                        <div className="flex-1 block overflow-hidden">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">Email</p>
                                            <p className="text-sm font-bold text-slate-700 truncate">{user?.email}</p>
                                        </div>
                                    </div>
                                    
                                    <button 
                                        onClick={() => { setIsEditingProfile(true); setNewName(user?.name || ""); }}
                                        className="w-full py-4 rounded-2xl bg-primary/5 text-primary text-xs font-black uppercase tracking-widest hover:bg-primary hover:text-white transition-all shadow-sm hover:shadow-xl hover:shadow-primary/20 active:scale-95"
                                    >
                                        Edit Personal Info
                                    </button>
                                </div>
                            </div>
                        </motion.div>

                        {/* Content Area */}
                        <div className="lg:col-span-2 space-y-8">
                            {/* Stats Grid */}
                            <div className="grid grid-cols-2 gap-6">
                                <motion.div 
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.1 }}
                                    className="p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-soft flex items-center gap-6 group hover:border-primary/20 transition-all cursor-default"
                                >
                                    <div className="w-14 h-14 rounded-2xl bg-primary/5 flex items-center justify-center text-primary shadow-inner group-hover:scale-110 transition-transform">
                                        <BookOpen size={24} />
                                    </div>
                                    <div>
                                        <div className="text-3xl font-black text-slate-900 leading-none mb-1">{classrooms.length}</div>
                                        <div className="text-[10px] text-slate-400 font-black uppercase tracking-widest leading-none">Classrooms</div>
                                    </div>
                                </motion.div>

                                <motion.div 
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.2 }}
                                    className="p-8 rounded-[2.5rem] bg-white border border-slate-100 shadow-soft flex items-center gap-6 group hover:border-emerald-500/20 transition-all cursor-default"
                                >
                                    <div className="w-14 h-14 rounded-2xl bg-emerald-500/5 flex items-center justify-center text-emerald-500 shadow-inner group-hover:scale-110 transition-transform">
                                        <CalendarIcon size={24} />
                                    </div>
                                    <div>
                                        <div className="text-3xl font-black text-slate-900 leading-none mb-1">{activeTasksCount}</div>
                                        <div className="text-[10px] text-slate-400 font-black uppercase tracking-widest leading-none">Active Tasks</div>
                                    </div>
                                </motion.div>
                            </div>

                            {/* Settings Sections */}
                            <motion.div 
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.3 }}
                                className="bg-white rounded-[2.5rem] border border-slate-100 shadow-premium overflow-hidden"
                            >
                                <div className="p-8 border-b border-slate-50 flex items-center justify-between">
                                    <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">Account Preferences</h3>
                                    <Settings size={18} className="text-slate-300" />
                                </div>
                                <div className="p-4 space-y-2">
                                    {/* Notifications Toggle Header */}
                                    <div className="p-4 rounded-2xl bg-slate-50/50 mb-2">
                                        <div className="flex items-center gap-3 mb-4">
                                            <Bell size={16} className="text-primary" />
                                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Communication</span>
                                        </div>
                                        <div className="space-y-4">
                                            {Object.entries(notifications).map(([key, value]) => (
                                                <div key={key} className="flex items-center justify-between">
                                                    <span className="text-sm font-bold capitalize text-slate-700"> {key.replace(/([A-Z])/g, ' $1')} Notifications</span>
                                                    <button 
                                                        onClick={() => toggleNotification(key as any)}
                                                        className={`w-11 h-6 rounded-full transition-all relative ${value ? 'bg-primary shadow-lg shadow-primary/20' : 'bg-slate-200'}`}
                                                    >
                                                        <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${value ? 'left-6' : 'left-1'}`} />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Security Trigger */}
                                    <button 
                                        onClick={() => setIsChangingPassword(true)}
                                        className="w-full flex items-center justify-between p-4 rounded-2xl hover:bg-slate-50 transition-all group text-left"
                                    >
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-primary/5 group-hover:text-primary transition-all">
                                                <Lock size={20} />
                                            </div>
                                            <div>
                                                <p className="text-sm font-black text-slate-800 tracking-tight">Security & Password</p>
                                                <p className="text-[11px] text-slate-400 font-medium italic">Update your account credentials</p>
                                            </div>
                                        </div>
                                        <div className="w-8 h-8 rounded-full border border-slate-100 flex items-center justify-center group-hover:bg-primary group-hover:text-white transition-all">
                                            <X size={14} className="rotate-135" />
                                        </div>
                                    </button>
                                </div>
                            </motion.div>
                        </div>
                    </div>
                </div>

                {/* MODALS */}
                <AnimatePresence>
                    {(isEditingProfile || isChangingPassword) && (
                        <motion.div 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 z-[100] flex items-center justify-center p-6"
                        >
                            <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-md" onClick={() => { setIsEditingProfile(false); setIsChangingPassword(false); setErrorMsg(null); }} />
                            
                            <motion.div 
                                initial={{ scale: 0.9, opacity: 0, y: 20 }}
                                animate={{ scale: 1, opacity: 1, y: 0 }}
                                exit={{ scale: 0.9, opacity: 0, y: 20 }}
                                className="relative w-full max-w-md bg-white rounded-[2.5rem] shadow-2xl p-10 overflow-hidden"
                            >
                                <div className="absolute top-0 left-0 w-full h-2 bg-primary" />
                                
                                <button 
                                    onClick={() => { setIsEditingProfile(false); setIsChangingPassword(false); setErrorMsg(null); }}
                                    className="absolute top-6 right-6 p-2 rounded-xl hover:bg-slate-50 text-slate-400 transition-all"
                                >
                                    <X size={20} />
                                </button>

                                {isEditingProfile ? (
                                    <form onSubmit={handleUpdateProfile}>
                                        <h3 className="text-2xl font-black text-slate-900 tracking-tight mb-8">Edit Profile</h3>
                                        <div className="space-y-6">
                                            <div>
                                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2 px-1">Full Name</label>
                                                <input 
                                                    type="text" 
                                                    value={newName}
                                                    onChange={(e) => setNewName(e.target.value)}
                                                    className="w-full px-6 py-4 bg-slate-50 border border-slate-100 rounded-2xl focus:bg-white focus:border-primary/30 focus:outline-none transition-all font-bold text-slate-700" 
                                                    required
                                                />
                                            </div>
                                            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 flex items-center gap-3">
                                                <Lock size={16} className="text-slate-300" />
                                                <span className="text-xs font-bold text-slate-400">Email cannot be changed currently</span>
                                            </div>
                                        </div>

                                        {errorMsg && <p className="mt-4 text-xs font-bold text-red-500 bg-red-50 p-3 rounded-xl">{errorMsg}</p>}
                                        {successMsg && <p className="mt-4 text-xs font-bold text-emerald-500 bg-emerald-50 p-3 rounded-xl flex items-center gap-2"><CheckCircle2 size={14} /> {successMsg}</p>}

                                        <button 
                                            disabled={isUpdating}
                                            className="w-full mt-10 py-5 bg-primary text-white rounded-2xl font-black text-sm shadow-xl shadow-primary/20 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-3 disabled:opacity-50"
                                        >
                                            {isUpdating ? <Loader2 className="animate-spin" size={20} /> : "Save Changes"}
                                        </button>
                                    </form>
                                ) : (
                                    <form onSubmit={handleChangePassword}>
                                        <h3 className="text-2xl font-black text-slate-900 tracking-tight mb-8">Update Security</h3>
                                        <div className="space-y-4">
                                            <input 
                                                type="password" 
                                                placeholder="Current Password"
                                                value={passwordData.old_password}
                                                onChange={(e) => setPasswordData({...passwordData, old_password: e.target.value})}
                                                className="w-full px-6 py-4 bg-slate-50 border border-slate-100 rounded-2xl focus:bg-white focus:border-primary/30 focus:outline-none transition-all font-bold text-slate-700" 
                                                required
                                            />
                                            <div className="h-px bg-slate-50 my-2" />
                                            <input 
                                                type="password" 
                                                placeholder="New Password"
                                                value={passwordData.new_password}
                                                onChange={(e) => setPasswordData({...passwordData, new_password: e.target.value})}
                                                className="w-full px-6 py-4 bg-slate-50 border border-slate-100 rounded-2xl focus:bg-white focus:border-primary/30 focus:outline-none transition-all font-bold text-slate-700" 
                                                required
                                            />
                                            <input 
                                                type="password" 
                                                placeholder="Confirm New Password"
                                                value={passwordData.confirm_password}
                                                onChange={(e) => setPasswordData({...passwordData, confirm_password: e.target.value})}
                                                className="w-full px-6 py-4 bg-slate-50 border border-slate-100 rounded-2xl focus:bg-white focus:border-primary/30 focus:outline-none transition-all font-bold text-slate-700" 
                                                required
                                            />
                                        </div>

                                        {errorMsg && <p className="mt-4 text-xs font-bold text-red-500 bg-red-50 p-3 rounded-xl">{errorMsg}</p>}
                                        {successMsg && <p className="mt-4 text-xs font-bold text-emerald-500 bg-emerald-50 p-3 rounded-xl flex items-center gap-2"><CheckCircle2 size={14} /> {successMsg}</p>}

                                        <button 
                                            disabled={isUpdating}
                                            className="w-full mt-10 py-5 bg-slate-900 text-white rounded-2xl font-black text-sm shadow-xl shadow-slate-900/20 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-3 disabled:opacity-50"
                                        >
                                            {isUpdating ? <Loader2 className="animate-spin" size={20} /> : "Update Password"}
                                        </button>
                                    </form>
                                )}
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
