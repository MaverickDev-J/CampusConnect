"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Download, Loader2, RefreshCw } from "lucide-react";
import { Sidebar } from "@/app/components/Sidebar";
import Header from "@/app/components/Header";
import { useAuth } from "@/app/context/auth-context";
import { useClassrooms } from "@/app/hooks/useClassrooms";
import { API_BASE_URL } from "@/app/config";

type Stage = { stage: string; duration_ms?: number; offset_ms?: number; status?: string; input_tokens?: number | null; output_tokens?: number | null; fallback_reason?: string | null };
type Run = { run_id: string; kind: string; origin: string; status: string; duration_ms: number; cache_status: string; strategy: string | null; fallback_reason: string | null; events: Stage[]; created_at: string };
type Overview = { requests: number; errors: number; cancelled: number; fallbacks: number; cache_hits: number; p50_ms: number | null; p95_ms: number | null; usage: { input_tokens: number | null; output_tokens: number | null; measured_calls: number } };
type Source = { chunk_id: string; file_name: string; page_number: number | null; chunk_preview: string };
type Comparison = { run_id: string; corpus_version: number; strategies: Record<string, { status: string; sources: Source[]; candidate_ids: string[]; duration_ms?: number; fallback_reason?: string | null; strategy?: string; reason?: string }> };
type Report = { evaluation_id: string; dataset_version: string; dataset_hash: string; reviewed: boolean; corpus_version: number; created_at: string; report: { case_count: number; label_status: string; summary: Record<string, { recall_at_12: number | null; ndcg_at_6: number | null; scored_cases: number; fallback_cases: number }> } };
const names: Record<string, string> = { dense: "Dense", hybrid: "Hybrid", hybrid_rerank: "Hybrid + reranking" };
const field = "rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800";

export default function QualityPage() {
    const { user, loading } = useAuth();
    const { classrooms } = useClassrooms();
    const courses = classrooms.filter(c => c.created_by === user?.user_id || user?.role === "superadmin");
    const [classroomId, setClassroomId] = useState("");
    const [origin, setOrigin] = useState("live");
    const [overview, setOverview] = useState<Overview | null>(null);
    const [runs, setRuns] = useState<Run[]>([]);
    const [reports, setReports] = useState<Report[]>([]);
    const [query, setQuery] = useState("");
    const [comparison, setComparison] = useState<Comparison | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const allowed = user?.role === "teacher" || user?.role === "superadmin";

    useEffect(() => { if (!classroomId && courses.length) setClassroomId(courses[0].classroom_id); }, [classroomId, courses]);
    const request = useCallback(async <T,>(path: string, body?: unknown): Promise<T> => {
        const response = await fetch(`${API_BASE_URL}/api/quality${path}`, { method: body ? "POST" : "GET", cache: "no-store",
            headers: { Authorization: `Bearer ${user?.token}`, "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load quality data.");
        return data as T;
    }, [user?.token]);
    const reload = useCallback(async () => {
        if (!classroomId || !user?.token || !allowed) return;
        const scope = `classroom_id=${encodeURIComponent(classroomId)}`;
        const [stats, history, evaluations] = await Promise.all([
            request<Overview>(`/overview?${scope}&origin=${origin}`), request<{ runs: Run[] }>(`/runs?${scope}`), request<{ evaluations: Report[] }>(`/evaluations?${scope}`),
        ]);
        setOverview(stats); setRuns(history.runs); setReports(evaluations.evaluations);
    }, [classroomId, user?.token, allowed, origin, request]);
    useEffect(() => { setComparison(null); setError(""); reload().catch(err => setError(err.message)); }, [reload]);
    const download = (report: Report) => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = `${report.evaluation_id}.json`; link.click(); URL.revokeObjectURL(url);
    };

    if (loading) return <div className="p-10">Loading...</div>;
    if (!allowed) return <div className="p-10">Faculty access required. <Link href="/classrooms" className="underline">View classrooms</Link></div>;

    return <div className="flex min-h-screen bg-slate-50"><Sidebar /><main className="flex-1 min-w-0"><Header />
        <div className="mx-auto max-w-7xl p-5 md:p-10 space-y-8">
            <div><h1 className="flex items-center gap-3 text-3xl font-black text-slate-900"><Activity /> Quality & Runs</h1>
                <p className="mt-2 text-sm text-slate-500">Inspect real runs, compare retrieval evidence, and review saved evaluations.</p></div>
            <div className="flex flex-wrap gap-3 items-center">
                <label className="text-sm font-bold text-slate-700">Classroom <select aria-label="Quality classroom" className={`${field} ml-2`} value={classroomId} onChange={e => setClassroomId(e.target.value)}>
                    <option value="" disabled>Select a classroom</option>{courses.map(c => <option key={c.classroom_id} value={c.classroom_id}>{c.name}</option>)}
                </select></label>
                <label className="text-sm font-bold text-slate-700">Overview <select aria-label="Traffic origin" className={`${field} ml-2`} value={origin} onChange={e => setOrigin(e.target.value)}>
                    <option value="live">Live traffic</option><option value="benchmark">Benchmarks</option><option value="synthetic">Synthetic checks</option>
                </select></label>
                <button aria-label="Refresh quality data" disabled={busy} onClick={() => reload().catch(err => setError(err.message))} className={field}><RefreshCw size={18} /></button>
            </div>
            {error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-700 text-sm">{error}</p>}
            {!courses.length && <p className="text-slate-500">Create a classroom to view its quality data.</p>}
            {overview && <>
                <p className="text-xs text-slate-500">Last 14 days · {origin} traffic only · {overview.requests} recorded runs</p>
                <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">{[
                    ["Runs", overview.requests], ["Cache hits", overview.cache_hits], ["Failures", overview.errors], ["Fallbacks", overview.fallbacks], ["p95 duration", overview.p95_ms == null ? "Unavailable" : `${Math.round(overview.p95_ms)} ms`],
                ].map(([label, value]) => <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-2xl font-black text-slate-900">{value}</p></div>)}</div>
                <p className="text-sm text-slate-500">Reported provider usage: {overview.usage.input_tokens ?? "unknown"} input tokens · {overview.usage.output_tokens ?? "unknown"} output tokens · {overview.usage.measured_calls} measured calls. Monetary cost is not estimated.</p>
            </>}
            <section className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
                <h2 className="text-xl font-bold text-slate-900">Compare retrieval</h2>
                <p className="text-sm text-slate-500">One shared query embedding, three strategies, and fresh source checks. Answer caches are bypassed. This compares evidence; it does not grade generated answers.</p>
                <form className="flex flex-col md:flex-row gap-3" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try {
                    setComparison(await request<Comparison>("/compare", { classroom_id: classroomId, query, origin })); await reload();
                } catch (err) { setError(err instanceof Error ? err.message : "Comparison failed."); } finally { setBusy(false); } }}>
                    <input aria-label="Comparison question" required maxLength={2000} className={`${field} flex-1`} value={query} onChange={e => setQuery(e.target.value)} placeholder="Ask an exact-term question or a paraphrase" />
                    <button disabled={busy || !classroomId || !query.trim()} className="rounded-xl bg-slate-900 text-white px-5 py-3 font-bold disabled:opacity-40">{busy ? <Loader2 className="animate-spin" size={20} /> : "Compare"}</button>
                </form>
                {comparison && <div className="grid lg:grid-cols-3 gap-4">{Object.entries(comparison.strategies).map(([name, result]) => <article key={name} className="rounded-xl bg-slate-50 p-4 space-y-3">
                    <h3 className="font-bold text-slate-900">{names[name]}</h3><p className="text-xs text-slate-500">{result.status} · {result.duration_ms == null ? "Timing unavailable" : `${result.duration_ms} ms`} · {result.candidate_ids.length} candidates</p>
                    {(result.fallback_reason || result.reason) && <p className="text-xs text-amber-800">Fallback: {result.fallback_reason || result.reason}</p>}
                    {result.sources.map((source, i) => <div key={source.chunk_id} className="rounded-lg border border-slate-200 bg-white p-3"><p className="text-sm font-bold">{i + 1}. {source.file_name}{source.page_number == null ? "" : ` · Page ${source.page_number}`}</p><p className="mt-1 text-xs text-slate-600">{source.chunk_preview}</p></div>)}
                </article>)}</div>}
            </section>
            <section className="space-y-4"><h2 className="text-xl font-bold text-slate-900">Recent runs · all origins</h2>
                {!runs.length && <p className="text-sm text-slate-500">No recorded runs yet. Ask a course question or run a comparison.</p>}
                {runs.map(run => <details key={run.run_id} className="rounded-xl border border-slate-200 bg-white p-4">
                    <summary className="cursor-pointer text-sm font-bold text-slate-700">{run.kind} · {run.origin} · {run.status} · {run.duration_ms} ms · cache {run.cache_status}</summary>
                    <p className="mt-2 text-xs text-slate-500">{new Date(run.created_at).toLocaleString()} · {run.strategy || "Strategy unavailable"}{run.fallback_reason ? ` · Fallback: ${run.fallback_reason}` : ""}</p>
                    <ol className="mt-4 space-y-2">{run.events.filter(event => event.duration_ms != null).sort((a, b) => (a.offset_ms || 0) - (b.offset_ms || 0)).map((event, i) => <li key={i} className="flex justify-between gap-3 rounded-lg bg-slate-50 p-3 text-xs"><span>{event.stage} · {event.status}</span><span>{event.duration_ms} ms</span></li>)}</ol>
                </details>)}
            </section>
            <section className="space-y-4"><h2 className="text-xl font-bold text-slate-900">Evaluation history</h2>
                {!reports.length && <p className="text-sm text-slate-500">No evaluations yet. Run the benchmark CLI with a labeled dataset to save a report here.</p>}
                {reports.map(report => <article key={report.evaluation_id} className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
                    <div className="flex justify-between gap-3"><div><h3 className="font-bold">{report.dataset_version} · {report.report.case_count} cases</h3><p className="text-xs text-slate-500">{report.report.label_status} · Corpus {report.corpus_version} · Retrieval only</p></div><button aria-label={`Download ${report.dataset_version}`} className={field} onClick={() => download(report)}><Download size={16} /></button></div>
                    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Strategy</th><th className="p-2">Recall@12</th><th className="p-2">nDCG@6</th><th className="p-2">Scored cases</th><th className="p-2">Fallbacks</th></tr></thead><tbody>{Object.entries(report.report.summary).map(([name, scores]) => <tr key={name}><td className="p-2">{names[name]}</td><td className="p-2">{scores.recall_at_12 == null ? "Unavailable" : scores.recall_at_12.toFixed(3)}</td><td className="p-2">{scores.ndcg_at_6 == null ? "Unavailable" : scores.ndcg_at_6.toFixed(3)}</td><td className="p-2">{scores.scored_cases}</td><td className="p-2">{scores.fallback_cases}</td></tr>)}</tbody></table></div>
                </article>)}
            </section>
        </div>
    </main></div>;
}
