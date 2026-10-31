"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarCheck, Loader2, RefreshCw } from "lucide-react";
import { API_BASE_URL } from "@/app/config";

type Payload = { title: string; announcement: string; description: string; date: string };
type Source = { chunk_id: string; file_id: string; file_name: string; page_number: number | null; text: string };
type Draft = {
    workflow_id: string; topic: string; payload: Payload; version: number; payload_hash: string;
    status: "awaiting_approval" | "approved" | "completed" | "rejected";
    sources: Source[]; expires_at: string;
    result: { announcement: { announcement_id: string }; event: { event_id: string } } | null;
};

const statusText = { awaiting_approval: "Awaiting your review", approved: "Approved · ready to post", completed: "Posted and scheduled", rejected: "Rejected" };
const inputStyle = "w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 disabled:bg-slate-50";
const buttonStyle = "rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold disabled:opacity-40";

export default function RevisionSessionPanel({ classroomId, token, onPublished }: {
    classroomId: string; token: string; onPublished: () => void;
}) {
    const [drafts, setDrafts] = useState<Draft[]>([]);
    const [selectedId, setSelectedId] = useState("");
    const [payload, setPayload] = useState<Payload | null>(null);
    const [topic, setTopic] = useState("");
    const [date, setDate] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const selected = drafts.find(d => d.workflow_id === selectedId);
    const closed = selected?.status === "completed" || selected?.status === "rejected";
    const expired = selected ? new Date(selected.expires_at).getTime() <= Date.now() : false;
    const dirty = !!selected && !!payload && JSON.stringify(selected.payload) !== JSON.stringify(payload);
    const today = new Date().toLocaleDateString("en-CA");

    const request = useCallback(async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
        const response = await fetch(`${API_BASE_URL}/api/workflows${path}`, {
            method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }), cache: "no-store",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not complete this request. Check the fields and try again.");
        return data as T;
    }, [token]);

    const reload = useCallback(async () => {
        const result = await request<{ workflows: Draft[] }>(`?classroom_id=${encodeURIComponent(classroomId)}`);
        setDrafts(result.workflows);
        setSelectedId(current => result.workflows.some(d => d.workflow_id === current) ? current : result.workflows[0]?.workflow_id || "");
    }, [classroomId, request]);

    useEffect(() => { reload().catch(err => setError(err.message)); }, [reload]);
    useEffect(() => { setPayload(selected ? { ...selected.payload } : null); }, [selected]);

    const accept = (draft: Draft) => {
        setDrafts(current => [draft, ...current.filter(d => d.workflow_id !== draft.workflow_id)]);
        setSelectedId(draft.workflow_id);
    };

    const run = async (operation: () => Promise<void>) => {
        setBusy(true); setError("");
        try { await operation(); } catch (err) { setError(err instanceof Error ? err.message : "Please retry."); }
        finally { setBusy(false); }
    };

    const action = (name: "approve" | "reject" | "execute") => run(async () => {
        if (!selected) return;
        const draft = await request<Draft>(`/${selected.workflow_id}/${name}`, "POST",
            name === "execute" ? undefined : { version: selected.version, payload_hash: selected.payload_hash });
        accept(draft);
        if (name === "execute") onPublished();
    });

    return (
        <section aria-labelledby="revision-session-title" className="rounded-[2rem] border border-amber-200 bg-white p-6 md:p-8 shadow-sm space-y-6">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <h2 id="revision-session-title" className="flex items-center gap-2 text-xl font-black text-slate-900"><CalendarCheck size={22} /> Plan a revision session</h2>
                    <p className="mt-2 text-sm text-slate-500">Create a draft from course materials. Review it before posting an announcement and calendar event.</p>
                </div>
                <button type="button" aria-label="Reload revision drafts" disabled={busy} onClick={() => run(reload)} className={buttonStyle}><RefreshCw size={16} /></button>
            </div>
            <form onSubmit={event => { event.preventDefault(); run(async () => {
                const draft = await request<Draft>("/revision", "POST", { classroom_id: classroomId, topic, date });
                accept(draft);
            }); }} className="grid gap-3 md:grid-cols-[1fr_auto_auto] items-end">
                <label className="space-y-1 text-sm font-bold text-slate-700">Topic
                    <input required maxLength={2000} value={topic} disabled={busy} onChange={e => setTopic(e.target.value)} placeholder="e.g. Backpropagation and the chain rule" className={inputStyle} />
                </label>
                <label className="space-y-1 text-sm font-bold text-slate-700">Session date
                    <input required type="date" min={today} value={date} disabled={busy} onChange={e => setDate(e.target.value)} className={inputStyle} />
                </label>
                <button disabled={busy || !topic.trim() || !date} className={`${buttonStyle} bg-amber-100 border-amber-200 text-amber-950`}>{busy ? <Loader2 size={18} className="animate-spin" /> : "Prepare draft"}</button>
            </form>
            {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
            {drafts.length > 0 && <label className="block text-sm font-bold text-slate-700">Saved drafts
                <select aria-label="Saved revision drafts" disabled={busy} value={selectedId} onChange={e => setSelectedId(e.target.value)} className={`${inputStyle} mt-1`}>
                    {drafts.map(draft => <option key={draft.workflow_id} value={draft.workflow_id}>{draft.payload.title} — {statusText[draft.status]}</option>)}
                </select>
            </label>}
            {selected && payload && <div className="space-y-4 border-t border-slate-100 pt-5">
                <p className="text-sm font-bold text-amber-800" aria-live="polite">{statusText[selected.status]} · Version {selected.version}</p>
                {expired && !closed && <p className="text-sm text-red-700">This draft has expired. Prepare a new draft with current sources.</p>}
                <label className="block text-sm font-bold text-slate-700">Title
                    <input maxLength={200} value={payload.title} disabled={busy || closed || expired} onChange={e => setPayload({ ...payload, title: e.target.value })} className={`${inputStyle} mt-1`} />
                </label>
                <label className="block text-sm font-bold text-slate-700">Date
                    <input type="date" min={today} value={payload.date} disabled={busy || closed || expired} onChange={e => setPayload({ ...payload, date: e.target.value })} className={`${inputStyle} mt-1`} />
                </label>
                <label className="block text-sm font-bold text-slate-700">Announcement
                    <textarea rows={4} maxLength={5000} value={payload.announcement} disabled={busy || closed || expired} onChange={e => setPayload({ ...payload, announcement: e.target.value })} className={`${inputStyle} mt-1`} />
                </label>
                <label className="block text-sm font-bold text-slate-700">Calendar description
                    <textarea rows={3} maxLength={1000} value={payload.description} disabled={busy || closed || expired} onChange={e => setPayload({ ...payload, description: e.target.value })} className={`${inputStyle} mt-1`} />
                </label>
                <details className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                    <summary className="cursor-pointer font-bold">Review source evidence ({selected.sources.length})</summary>
                    <div className="mt-3 space-y-3">{selected.sources.map(source => <div key={source.chunk_id}>
                        <p className="font-bold">{source.file_name}{source.page_number != null ? ` · Page ${source.page_number}` : ""}</p>
                        <p className="mt-1 whitespace-pre-wrap max-h-48 overflow-auto">{source.text}</p>
                    </div>)}</div>
                </details>
                {!closed && !expired && <div className="flex flex-wrap gap-3">
                    {dirty ? <button disabled={busy || !payload.title.trim() || !payload.announcement.trim() || !payload.description.trim() || !payload.date} onClick={() => run(async () => {
                        accept(await request<Draft>(`/${selected.workflow_id}`, "PATCH", { version: selected.version, payload_hash: selected.payload_hash, payload }));
                    })} className={`${buttonStyle} bg-slate-900 text-white`}>Save changes</button> : selected.status === "awaiting_approval" ?
                        <button disabled={busy} onClick={() => action("approve")} className={`${buttonStyle} bg-amber-100 text-amber-950`}>Approve draft</button> :
                        <button disabled={busy} onClick={() => action("execute")} className={`${buttonStyle} bg-slate-900 text-white`}>Post announcement &amp; add event</button>}
                    <button disabled={busy || dirty} onClick={() => action("reject")} className={buttonStyle}>Reject draft</button>
                    {dirty && <p className="self-center text-xs text-slate-500">Save changes, then review and approve again.</p>}
                </div>}
                {selected.status === "completed" && <p role="status" className="text-sm text-green-700">The announcement and calendar event were created.</p>}
            </div>}
        </section>
    );
}
