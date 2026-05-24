"use client";

import { useState, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Header from "@/app/components/Header";
import {
    Filter,
    BookOpen,
    Video,
    FileText,
    Beaker,
    TrendingUp,
    Users,
    ChevronDown,
    Star,
    Plus,
    X,
    Upload,
    Image,
    PlayCircle,
    CheckCircle2,
    AlertCircle,
    Loader2
} from "lucide-react";
import { useFiles, type FileMetadata } from "@/app/hooks/useFiles";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";
import {
    BRANCHES,
    YEARS,
    DOC_TYPES,
    ACADEMIC_SUBJECTS,
    type Subject
} from "@/app/constants/academic";

// Mock Notebooks (Keep for now)
const NOTEBOOKS = [
    {
        id: "1",
        title: "Quantum Mechanics Notes",
        lastModified: "Dec 29",
        thumbnail: "bg-gradient-to-br from-indigo-900 to-slate-900",
        chats: 12
    },
    {
        id: "2",
        title: "Advanced AI Project",
        lastModified: "Dec 19",
        thumbnail: "bg-gradient-to-br from-purple-900 to-slate-900",
        chats: 8
    },
];

const FILTER_SECTIONS = [
    {
        id: "year",
        name: "Year",
        options: YEARS.map(y => ({ label: y.label, value: y.value.toString() }))
    },
    {
        id: "branch",
        name: "Branch",
        options: BRANCHES.map(b => ({ label: b.label, value: b.value }))
    },
    {
        id: "type",
        name: "Type",
        options: DOC_TYPES.map(d => ({ label: d.label, value: d.value })).concat([
            { label: "Video", value: "video" }, // Special case for file_type=video
        ])
    }
];

// Helper to map UI filters to API params
const mapFiltersToApi = (selected: Record<string, string[]>) => {
    const filters: any = {};

    // Year Mapping
    if (selected.year?.length) {
        filters.year = parseInt(selected.year[0]);
    }

    // Branch Mapping
    if (selected.branch?.length) {
        filters.branch = selected.branch[0];
    }

    // Type Mapping
    if (selected.type?.length) {
        const t = selected.type[0];
        if (t === "video") filters.file_type = "video";
        else filters.doc_type = t;
    }

    return filters;
};

export default function DeepBasePage() {
    const { user } = useAuth();
    const [activeTab, setActiveTab] = useState<"all" | "notebook">("all");
    const [selectedFilters, setSelectedFilters] = useState<Record<string, string[]>>({});
    const [openSections, setOpenSections] = useState<Record<string, boolean>>({
        year: true,
        branch: true,
        type: true
    });

    // Derive API filters from state
    const apiFilters = useMemo(() => mapFiltersToApi(selectedFilters), [selectedFilters]);

    // Fetch data
    const { files, loading, error, refetch } = useFiles(apiFilters);

    // Upload Modal State
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [uploadStep, setUploadStep] = useState<"details" | "file">("details");
    const [uploadData, setUploadData] = useState({
        year: "",
        branch: "",
        subject: "",
        unit: "1",
        doc_type: "notes",
        file: null as File | null
    });
    const [isUploading, setIsUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<"idle" | "success" | "error">("idle");
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Derived subject list for upload modal
    const availableSubjects = useMemo(() => {
        if (!uploadData.branch || !uploadData.year) return [];
        const yr = parseInt(uploadData.year);
        // Handle common first year if branch is not strictly defined in user map for year 1?
        // User map has year 1 for all branches.
        return ACADEMIC_SUBJECTS[uploadData.branch]?.[yr] || [];
    }, [uploadData.branch, uploadData.year]);

    const toggleSection = (id: string) => {
        setOpenSections(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const toggleFilter = (sectionId: string, optionValue: string) => {
        setSelectedFilters(prev => {
            const current = prev[sectionId] || [];
            // Single select behavior
            return {
                ...prev,
                [sectionId]: current.includes(optionValue) ? [] : [optionValue]
            };
        });
    };

    const handleUpload = async () => {
        if (!uploadData.file || !uploadData.year || !uploadData.branch || !uploadData.subject || !uploadData.doc_type) return;

        setIsUploading(true);
        try {
            const formData = new FormData();
            formData.append("file", uploadData.file);
            formData.append("year", uploadData.year);
            formData.append("branch", uploadData.branch);
            formData.append("subject", uploadData.subject);
            formData.append("unit", uploadData.unit);
            formData.append("doc_type", uploadData.doc_type);

            const res = await fetch(`${API_BASE_URL}/api/upload/file`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${user?.token}`
                },
                body: formData
            });

            if (!res.ok) throw new Error("Upload failed");

            setUploadStatus("success");
            setTimeout(() => {
                setShowUploadModal(false);
                setUploadStatus("idle");
                setUploadData({ year: "", branch: "", subject: "", unit: "1", doc_type: "notes", file: null });
                refetch?.(); // Refresh list if useFiles supports it (adding refetch to useFiles check next)
                window.location.reload(); // Quick fix for refresh until useFiles update
            }, 1500);

        } catch (err) {
            console.error(err);
            setUploadStatus("error");
        } finally {
            setIsUploading(false);
        }
    };

    // Card Component
    const ResourceCard = ({ file }: { file: FileMetadata }) => {
        let Icon = FileText;
        let typeLabel = "FILE";

        if (file.file_type === "video") {
            Icon = Video;
            typeLabel = "VIDEO";
        } else if (file.file_type === "image") {
            Icon = Image;
            typeLabel = "IMAGE";
        } else if (file.academic.doc_type === "notes") {
            Icon = BookOpen;
            typeLabel = "NOTES";
        } else if (file.academic.doc_type === "lab") {
            Icon = Beaker;
            typeLabel = "LAB";
        } else if (file.academic.doc_type === "pyq") {
            Icon = FileText;
            typeLabel = "PAPER";
        }

        const handleClick = () => {
            const url = `${API_BASE_URL}${file.playback_url}`;
            window.open(url, "_blank");
        };

        const authorName = file.uploaded_by || "Unknown";
        // Find human readable subject name if possible
        const subjectName = Object.values(ACADEMIC_SUBJECTS)
            .flatMap(years => Object.values(years).flat())
            .find(s => s.code === file.academic.subject)?.name || file.academic.subject;

        return (
            <motion.div
                layout
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                whileHover={{ y: -4, scale: 1.02 }}
                onClick={handleClick}
                className="group relative bg-[#0f1523] border border-slate-800 rounded-xl overflow-hidden hover:border-indigo-500/50 hover:shadow-xl hover:shadow-indigo-500/10 transition-all cursor-pointer flex flex-col h-full"
            >
                <div className="h-32 w-full bg-gradient-to-br from-slate-800 to-slate-900 relative p-4 flex flex-col justify-end group-hover:from-indigo-900/40 group-hover:to-slate-900 transition-colors">
                    <div className="absolute top-2 left-2 right-2 flex justify-between items-start">
                        <span className="inline-block px-2 py-1 rounded bg-black/40 backdrop-blur-sm text-[10px] font-bold text-white mb-1 uppercase tracking-wider">
                            {file.academic.branch || "GEN"} • {file.academic.year || "?"} • {file.academic.subject}
                        </span>
                        <div className="px-2 py-1 rounded-md bg-black/40 backdrop-blur-sm text-[10px] font-medium text-white flex items-center gap-1">
                            <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                            4.5
                        </div>
                    </div>

                    <h3 className="text-sm font-bold text-white leading-tight line-clamp-2 mt-auto">
                        {subjectName}
                    </h3>
                    <p className="text-[10px] text-slate-400 mt-1 truncate">
                        {file.original_name}
                    </p>
                </div>

                <div className="p-3 mt-auto">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                        <div className="flex items-center gap-1.5">
                            <span className="w-5 h-5 rounded-full bg-slate-800 flex items-center justify-center text-[10px] font-bold text-slate-300 uppercase">
                                {authorName.charAt(0)}
                            </span>
                            <span className="truncate max-w-[80px]">{authorName}</span>
                        </div>
                        <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400">
                            <Icon className="w-3 h-3" />
                            <span className="uppercase text-[10px] font-bold">{typeLabel}</span>
                        </div>
                    </div>
                </div>
            </motion.div>
        );
    };

    const NotebookCard = ({ notebook }: { notebook: typeof NOTEBOOKS[0] }) => (
        <motion.div
            whileHover={{ y: -4, scale: 1.02 }}
            className="group relative bg-[#0f1523] border border-slate-800 rounded-xl overflow-hidden hover:border-indigo-500/50 hover:shadow-xl hover:shadow-indigo-500/10 transition-all cursor-pointer flex flex-col"
        >
            <div className={`h-28 w-full ${notebook.thumbnail} relative`}>
                <div className="absolute inset-0 bg-black/20" />
                <div className="absolute top-2 left-2 px-2 py-1 rounded bg-black/40 backdrop-blur-sm text-[10px] font-bold text-slate-200">
                    Private
                </div>
            </div>
            <div className="p-4 flex-1 flex flex-col">
                <h3 className="text-sm font-bold text-white mb-1">{notebook.title}</h3>
                <p className="text-[10px] text-slate-500 mb-4">Last modified {notebook.lastModified}</p>

                <div className="mt-auto flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 flex items-center gap-1">
                        <Users className="w-3 h-3" /> {notebook.chats} chats
                    </span>
                    <button className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500 hover:text-white transition-colors">
                        <TrendingUp className="w-4 h-4" />
                    </button>
                </div>
            </div>
        </motion.div>
    );

    return (
        <div className="flex flex-col h-screen w-full bg-[#0a0e1a] text-slate-200 overflow-hidden">
            <Header />

            {/* Upload Modal */}
            <AnimatePresence>
                {showUploadModal && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
                    >
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.95, opacity: 0 }}
                            className="w-full max-w-2xl bg-[#0f1523] border border-slate-700/50 rounded-2xl shadow-2xl overflow-hidden"
                        >
                            <div className="flex items-center justify-between p-4 border-b border-slate-800/50">
                                <h2 className="text-lg font-bold text-white">Upload Material</h2>
                                <button
                                    onClick={() => setShowUploadModal(false)}
                                    className="text-slate-500 hover:text-slate-300 transition-colors"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            <div className="p-6 space-y-6">
                                {uploadStatus === "success" ? (
                                    <div className="flex flex-col items-center justify-center py-10 space-y-4">
                                        <CheckCircle2 className="w-16 h-16 text-emerald-500" />
                                        <h3 className="text-xl font-bold text-white">Upload Successful!</h3>
                                        <p className="text-slate-400">Your file has been added to the knowledge base.</p>
                                    </div>
                                ) : uploadStatus === "error" ? (
                                    <div className="flex flex-col items-center justify-center py-10 space-y-4">
                                        <AlertCircle className="w-16 h-16 text-red-500" />
                                        <h3 className="text-xl font-bold text-white">Upload Failed</h3>
                                        <p className="text-slate-400">Something went wrong. Please try again.</p>
                                        <button
                                            onClick={() => setUploadStatus("idle")}
                                            className="px-4 py-2 bg-slate-800 text-white rounded-lg hover:bg-slate-700"
                                        >
                                            Try Again
                                        </button>
                                    </div>
                                ) : (
                                    <>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <label className="text-xs font-semibold text-slate-400 uppercase">Branch</label>
                                                <select
                                                    value={uploadData.branch}
                                                    onChange={(e) => setUploadData({ ...uploadData, branch: e.target.value, subject: "" })}
                                                    className="w-full py-2 px-3 rounded-lg bg-slate-800/50 border border-slate-700 text-slate-300 text-sm focus:outline-none focus:border-indigo-500/50"
                                                >
                                                    <option value="">Select Branch</option>
                                                    {BRANCHES.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
                                                </select>
                                            </div>
                                            <div className="space-y-2">
                                                <label className="text-xs font-semibold text-slate-400 uppercase">Year</label>
                                                <select
                                                    value={uploadData.year}
                                                    onChange={(e) => setUploadData({ ...uploadData, year: e.target.value, subject: "" })}
                                                    className="w-full py-2 px-3 rounded-lg bg-slate-800/50 border border-slate-700 text-slate-300 text-sm focus:outline-none focus:border-indigo-500/50"
                                                >
                                                    <option value="">Select Year</option>
                                                    {YEARS.map(y => <option key={y.value} value={y.value}>{y.label}</option>)}
                                                </select>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-3 gap-4">
                                            <div className="col-span-2 space-y-2">
                                                <label className="text-xs font-semibold text-slate-400 uppercase">Subject</label>
                                                <select
                                                    value={uploadData.subject}
                                                    onChange={(e) => setUploadData({ ...uploadData, subject: e.target.value })}
                                                    disabled={!availableSubjects.length}
                                                    className="w-full py-2 px-3 rounded-lg bg-slate-800/50 border border-slate-700 text-slate-300 text-sm focus:outline-none focus:border-indigo-500/50 disabled:opacity-50"
                                                >
                                                    <option value="">{availableSubjects.length ? "Select Subject" : "Select Branch & Year first"}</option>
                                                    {availableSubjects.map(s => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
                                                </select>
                                            </div>
                                            <div className="space-y-2">
                                                <label className="text-xs font-semibold text-slate-400 uppercase">Unit</label>
                                                <input
                                                    type="number"
                                                    value={uploadData.unit}
                                                    onChange={(e) => setUploadData({ ...uploadData, unit: e.target.value })}
                                                    className="w-full py-2 px-3 rounded-lg bg-slate-800/50 border border-slate-700 text-slate-300 text-sm focus:outline-none focus:border-indigo-500/50"
                                                />
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <label className="text-xs font-semibold text-slate-400 uppercase">Document Type</label>
                                            <div className="flex p-1 bg-slate-800/50 rounded-lg overflow-x-auto">
                                                {DOC_TYPES.map(type => (
                                                    <button
                                                        key={type.value}
                                                        onClick={() => setUploadData({ ...uploadData, doc_type: type.value })}
                                                        className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${uploadData.doc_type === type.value
                                                                ? "bg-indigo-600 text-white"
                                                                : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/50"
                                                            }`}
                                                    >
                                                        {type.label}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        <div
                                            onClick={() => fileInputRef.current?.click()}
                                            className="border-2 border-dashed border-slate-700 bg-slate-800/20 rounded-xl p-8 flex flex-col items-center justify-center gap-3 hover:border-indigo-500/30 transition-colors group cursor-pointer relative"
                                        >
                                            <input
                                                type="file"
                                                ref={fileInputRef}
                                                className="hidden"
                                                onChange={(e) => e.target.files && setUploadData({ ...uploadData, file: e.target.files[0] })}
                                            />
                                            {uploadData.file ? (
                                                <div className="flex flex-col items-center">
                                                    <FileText className="w-8 h-8 text-emerald-500 mb-2" />
                                                    <p className="text-sm font-medium text-white">{uploadData.file.name}</p>
                                                    <p className="text-xs text-slate-500">{(uploadData.file.size / 1024 / 1024).toFixed(2)} MB</p>
                                                </div>
                                            ) : (
                                                <>
                                                    <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center group-hover:bg-indigo-500/10 transition-colors">
                                                        <Upload className="w-5 h-5 text-slate-400 group-hover:text-indigo-400" />
                                                    </div>
                                                    <div className="text-center">
                                                        <p className="text-sm font-medium text-slate-300">Click to upload file</p>
                                                        <p className="text-xs text-slate-500">PDF, Images, Video</p>
                                                    </div>
                                                </>
                                            )}
                                        </div>

                                        <button
                                            onClick={handleUpload}
                                            disabled={isUploading || !uploadData.file}
                                            className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                        >
                                            {isUploading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Upload Material"}
                                        </button>
                                    </>
                                )}
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="flex flex-1 overflow-hidden relative">
                {/* ── Left Sidebar: Filter Resources ──────────────── */}
                <aside className="w-64 h-full bg-[#070b14] border-r border-slate-800/50 flex flex-col shrink-0 z-20">
                    <div className="p-5 border-b border-slate-800/50">
                        <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                            <Filter className="w-4 h-4 text-indigo-400" />
                            Filter Resources
                        </h2>
                    </div>

                    <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-thin scrollbar-thumb-slate-800">
                        {FILTER_SECTIONS.map((section) => (
                            <div key={section.id} className="space-y-3">
                                <button
                                    onClick={() => toggleSection(section.id)}
                                    className="w-full flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider hover:text-slate-300 transition-colors"
                                >
                                    {section.name}
                                    <ChevronDown
                                        className={`w-4 h-4 transition-transform ${openSections[section.id] ? "rotate-180" : ""}`}
                                    />
                                </button>

                                {openSections[section.id] && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: "auto", opacity: 1 }}
                                        className="space-y-1"
                                    >
                                        {section.options.map((option) => (
                                            <button
                                                key={option.value} // Use value here
                                                onClick={() => toggleFilter(section.id, option.value)}
                                                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center justify-between group ${selectedFilters[section.id]?.includes(option.value)
                                                    ? "bg-indigo-600/10 text-indigo-400 font-medium"
                                                    : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
                                                    }`}
                                            >
                                                {option.label} {/* Show Label */}
                                                {selectedFilters[section.id]?.includes(option.value) && (
                                                    <motion.div layoutId={`check-${section.id}`} className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                                                )}
                                            </button>
                                        ))}
                                    </motion.div>
                                )}
                            </div>
                        ))}
                    </div>

                    <div className="p-4 border-t border-slate-800/50">
                        <button
                            onClick={() => setSelectedFilters({})}
                            className="w-full py-2.5 rounded-lg border border-slate-700 bg-transparent hover:bg-slate-800 text-slate-400 text-xs font-medium transition-colors"
                        >
                            Clear All Filters
                        </button>
                    </div>
                </aside>

                <main className="flex-1 overflow-y-auto p-6 lg:p-10 scrollbar-thin scrollbar-thumb-slate-800">
                    <div className="flex items-center justify-between mb-8">
                        <div className="flex items-center gap-1 bg-slate-900/50 p-1 rounded-xl w-fit border border-slate-800">
                            <button
                                onClick={() => setActiveTab("all")}
                                className={`px-6 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === "all"
                                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                                    }`}
                            >
                                All
                            </button>
                            <button
                                onClick={() => setActiveTab("notebook")}
                                className={`px-6 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === "notebook"
                                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                                    }`}
                            >
                                My Notebook
                            </button>
                        </div>

                        <button
                            onClick={() => setShowUploadModal(true)}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-lg shadow-indigo-500/20"
                        >
                            <Upload className="w-4 h-4" />
                            Upload
                        </button>
                    </div>

                    {activeTab === "all" ? (
                        <div className="space-y-6">
                            {loading && (
                                <div className="text-center py-20 text-slate-500">
                                    <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                                    Loading resources...
                                </div>
                            )}

                            {error && (
                                <div className="text-center py-20 text-red-400 bg-red-500/10 rounded-xl border border-red-500/20">
                                    <p>Error: {error}</p>
                                </div>
                            )}

                            {!loading && !error && files.length === 0 && (
                                <div className="text-center py-20 text-slate-500">
                                    <p>No resources found matching your filters.</p>
                                </div>
                            )}

                            {!loading && files.length > 0 && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4"
                                >
                                    {files.map((file) => (
                                        <ResourceCard key={file.file_id} file={file} />
                                    ))}
                                </motion.div>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                            <motion.button
                                onClick={() => setShowUploadModal(true)}
                                whileHover={{ scale: 1.02, backgroundColor: "rgba(15, 23, 42, 0.5)" }}
                                className="group h-full min-h-[220px] rounded-xl border-2 border-dashed border-slate-700 hover:border-indigo-500/50 flex flex-col items-center justify-center gap-3 text-slate-500 hover:text-indigo-400 transition-all"
                            >
                                <div className="w-12 h-12 rounded-full bg-slate-800 group-hover:bg-indigo-500/10 flex items-center justify-center transition-colors">
                                    <Plus className="w-6 h-6" />
                                </div>
                                <span className="text-sm font-medium">Create new notebook</span>
                            </motion.button>

                            {NOTEBOOKS.map(notebook => (
                                <NotebookCard key={notebook.id} notebook={notebook} />
                            ))}
                        </div>
                    )}

                </main>
            </div>
        </div>
    );
}
