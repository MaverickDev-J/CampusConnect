"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import Link from "next/link";
import { motion } from "framer-motion";
import {
    ShieldCheck,
    UserPlus,
    Users,
    Mail,
    Loader2,
    Check,
    X,
    Trash2,
    Eye,
    EyeOff
} from "lucide-react";

interface ManagedUser {
    user_id: string;
    name: string;
    email: string;
    role: string;
}

export default function AdminPage() {
    const { user } = useAuth();
    const [users, setUsers] = useState<ManagedUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [form, setForm] = useState({ name: "", email: "", password: "" });
    const [showPassword, setShowPassword] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [success, setSuccess] = useState("");
    const [error, setError] = useState("");
    const [roleFilter, setRoleFilter] = useState("all");

    useEffect(() => {
        if (user?.token) fetchUsers();
    }, [user?.token]);

    const fetchUsers = async () => {
        if (!user?.token) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/superadmin/users`, {
                headers: { Authorization: `Bearer ${user.token}` },
            });
            const data = await res.json();
            setUsers(data.users || []);
        } catch {
            setError("Failed to load users");
        } finally {
            setLoading(false);
        }
    };

    const handleProvision = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError("");
        setSuccess("");
        try {
            const res = await fetch("http://localhost:8000/api/superadmin/provision-teacher", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${user?.token}`,
                },
                body: JSON.stringify(form),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to create teacher");
            }
            setSuccess(`Teacher account created for ${form.name}!`);
            setForm({ name: "", email: "", password: "" });
            fetchUsers();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Something went wrong");
        } finally {
            setSubmitting(false);
        }
    };

    const filtered = roleFilter === "all" ? users : users.filter(u => u.role === roleFilter);

    if (user?.role !== "superadmin") {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
                <div className="text-center">
                    <ShieldCheck size={48} className="text-slate-200 mx-auto mb-4" />
                    <h2 className="text-2xl font-black text-slate-900">Access Denied</h2>
                    <p className="text-slate-500 mt-2">You need superadmin privileges to view this page.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 flex">
            <Sidebar />
            <main className="flex-1 ml-20 lg:ml-64 transition-all duration-300">
                <Header />

                <div className="max-w-6xl mx-auto px-6 py-10">
                    <div className="flex items-center gap-4 mb-10">
                        <div className="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-100">
                            <ShieldCheck size={24} className="text-white" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h1 className="text-3xl font-black text-slate-900 tracking-tighter">Admin Panel</h1>
                                <Link href="/" className="ml-4 text-[10px] font-black text-indigo-600 uppercase tracking-widest hover:underline flex items-center gap-1">
                                    Back to Dashboard
                                </Link>
                            </div>
                            <p className="text-slate-500 font-medium">Manage teachers and institution users</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {/* Provision Teacher Form */}
                        <div className="lg:col-span-1">
                            <div className="bg-white rounded-3xl p-8 border border-slate-100 shadow-soft sticky top-24">
                                <h2 className="text-lg font-black text-slate-900 mb-6 flex items-center gap-2">
                                    <UserPlus size={20} className="text-indigo-600" /> Create Teacher Account
                                </h2>
                                <form onSubmit={handleProvision} className="space-y-4">
                                    {[
                                        { label: "Full Name", key: "name", type: "text", placeholder: "Dr. Jane Smith", icon: Users },
                                        { label: "Email Address", key: "email", type: "email", placeholder: "teacher@college.edu", icon: Mail },
                                    ].map(field => (
                                        <div key={field.key}>
                                            <label className="block text-[11px] font-black text-slate-500 uppercase tracking-widest mb-1.5">
                                                {field.label}
                                            </label>
                                            <input
                                                type={field.type}
                                                placeholder={field.placeholder}
                                                value={(form as any)[field.key]}
                                                onChange={e => setForm(prev => ({ ...prev, [field.key]: e.target.value }))}
                                                required
                                                className="w-full px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:ring-4 focus:ring-indigo-600/5 focus:border-indigo-600/30 transition-all font-medium text-sm"
                                            />
                                        </div>
                                    ))}
                                    <div>
                                        <label className="block text-[11px] font-black text-slate-500 uppercase tracking-widest mb-1.5">
                                            Temporary Password
                                        </label>
                                        <div className="relative">
                                            <input
                                                type={showPassword ? "text" : "password"}
                                                placeholder="Min 8 characters"
                                                value={form.password}
                                                onChange={e => setForm(prev => ({ ...prev, password: e.target.value }))}
                                                required
                                                minLength={8}
                                                className="w-full px-4 py-3 pr-12 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:ring-4 focus:ring-indigo-600/5 focus:border-indigo-600/30 transition-all font-medium text-sm"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => setShowPassword(!showPassword)}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                                            >
                                                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                            </button>
                                        </div>
                                    </div>

                                    {error && (
                                        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 text-red-600 text-sm font-semibold">
                                            <X size={16} /> {error}
                                        </div>
                                    )}
                                    {success && (
                                        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 text-emerald-600 text-sm font-semibold">
                                            <Check size={16} /> {success}
                                        </div>
                                    )}
                                    <button
                                        type="submit"
                                        disabled={submitting}
                                        className="w-full py-3.5 rounded-xl bg-indigo-600 text-white font-black hover:bg-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2 text-sm"
                                    >
                                        {submitting ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
                                        {submitting ? "Creating..." : "Create Teacher Account"}
                                    </button>
                                </form>
                            </div>
                        </div>

                        {/* Users Table */}
                        <div className="lg:col-span-2">
                            <div className="bg-white rounded-3xl border border-slate-100 shadow-soft overflow-hidden">
                                <div className="p-6 border-b border-slate-100 flex items-center justify-between">
                                    <h2 className="text-lg font-black text-slate-900 flex items-center gap-2">
                                        <Users size={20} className="text-indigo-600" /> All Users
                                        <span className="ml-2 px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-black">{users.length}</span>
                                    </h2>
                                    <div className="flex items-center gap-2">
                                        {["all", "superadmin", "teacher", "student"].map(r => (
                                            <button
                                                key={r}
                                                onClick={() => setRoleFilter(r)}
                                                className={`px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-wide transition-all ${
                                                    roleFilter === r
                                                        ? "bg-indigo-600 text-white"
                                                        : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                                                }`}
                                            >
                                                {r}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div className="divide-y divide-slate-50">
                                    {loading ? (
                                        <div className="p-12 flex items-center justify-center">
                                            <Loader2 size={32} className="animate-spin text-indigo-600" />
                                        </div>
                                    ) : filtered.length === 0 ? (
                                        <div className="p-12 text-center text-slate-400 font-medium">No users found.</div>
                                    ) : (
                                        filtered.map((u, i) => (
                                            <motion.div
                                                key={u.user_id}
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                transition={{ delay: i * 0.03 }}
                                                className="flex items-center justify-between px-6 py-4 hover:bg-slate-50 transition-colors group"
                                            >
                                                <div className="flex items-center gap-4">
                                                    <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                                                        <span className="text-sm font-black text-indigo-700">{u.name.charAt(0).toUpperCase()}</span>
                                                    </div>
                                                    <div>
                                                        <div className="font-bold text-slate-900">{u.name}</div>
                                                        <div className="text-xs text-slate-400 font-medium">{u.email}</div>
                                                    </div>
                                                </div>
                                                <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${
                                                    u.role === "superadmin" ? "bg-red-100 text-red-700" :
                                                    u.role === "teacher" ? "bg-amber-100 text-amber-700" :
                                                    "bg-emerald-100 text-emerald-700"
                                                }`}>
                                                    {u.role}
                                                </span>
                                            </motion.div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
