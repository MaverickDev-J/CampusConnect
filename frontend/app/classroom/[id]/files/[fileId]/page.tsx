"use client";

import { use, useState, useEffect, useCallback } from "react";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import { 
    ArrowLeft, 
    Download, 
    FileText, 
    Loader2, 
    ChevronLeft,
    Maximize,
    Minimize
} from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";

export default function FileViewerPage({ params }: { params: Promise<{ id: string; fileId: string }> }) {
    const { id: classroomId, fileId } = use(params);
    const { user } = useAuth();
    const [fileData, setFileData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    const fetchFile = useCallback(async () => {
        if (!user?.token) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/files/${fileId}`, {
                headers: { "Authorization": `Bearer ${user.token}` }
            });
            const data = await res.json();
            setFileData(data);
        } catch (error) {
            console.error("Failed to fetch file:", error);
        } finally {
            setLoading(false);
        }
    }, [user?.token, fileId]);

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
                <Loader2 className="w-10 h-10 text-indigo-600 animate-spin" />
            </div>
        );
    }

    if (!fileData) return null;

    return (
        <div className="min-h-screen bg-slate-900 flex flex-col">
            {/* Header bar */}
            <header className="h-16 bg-slate-800 border-b border-slate-700 px-6 flex items-center justify-between text-white z-10 shadow-lg">
                <div className="flex items-center gap-4">
                    <Link href={`/classroom/${classroomId}`} className="p-2 hover:bg-slate-700 rounded-lg transition">
                        <ArrowLeft size={20} />
                    </Link>
                    <div>
                        <h1 className="text-sm font-black truncate max-w-md">{fileData.original_name}</h1>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            {fileData.file_type} Viewer
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <a 
                        href={`http://localhost:8000/api/files/${fileId}/download`}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 font-black text-xs transition"
                    >
                        <Download size={16} /> Download
                    </a>
                </div>
            </header>

            {/* Viewer area */}
            <main className={`flex-1 relative bg-slate-950 overflow-hidden ${
                fileData.file_type !== "pdf" ? "flex flex-col items-center justify-center" : ""
            }`}>
                {fileData.file_type === "pdf" ? (
                    <iframe 
                        src={`http://localhost:8000${fileData.playback_url}#toolbar=0`}
                        className="w-full h-[calc(100vh-64px)] border-none bg-white"
                        title={fileData.original_name}
                    />
                ) : fileData.file_type === "image" ? (
                    <img 
                        src={`http://localhost:8000${fileData.playback_url}`}
                        alt={fileData.original_name}
                        className="max-w-full max-h-[85vh] object-contain shadow-2xl"
                    />
                ) : (
                    <div className="text-center text-slate-500">
                        <FileText size={48} className="mx-auto mb-4 text-slate-700" />
                        <p className="font-bold text-slate-300">Preview not available for this file type.</p>
                        <a 
                            href={`http://localhost:8000/api/files/${fileId}/download`}
                            className="text-indigo-400 mt-4 inline-block hover:underline font-bold"
                        >
                            Download to view locally
                        </a>
                    </div>
                )}
            </main>
        </div>
    );
}
