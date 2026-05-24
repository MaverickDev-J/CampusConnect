"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";

export interface Announcement {
    announcement_id: string;
    classroom_id: string;
    author_name: string;
    author_role: string;
    content: string;
    created_at: string;
    file_id?: string;
    file?: any;
}

export function useAnnouncements(classroomId: string) {
    const [announcements, setAnnouncements] = useState<Announcement[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const { user } = useAuth();

    const fetchAnnouncements = useCallback(async () => {
        if (!user?.token || !classroomId) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/announcements/${classroomId}`, {
                headers: { "Authorization": `Bearer ${user.token}` }
            });
            if (!res.ok) throw new Error("Failed to load announcements");
            const data = await res.json();
            setAnnouncements(data.announcements || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error");
        } finally {
            setLoading(false);
        }
    }, [user?.token, classroomId]);

    const postAnnouncement = async (content: string, fileId: string | null = null) => {
        if (!user?.token) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/announcements`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${user.token}` 
                },
                body: JSON.stringify({ 
                    classroom_id: classroomId, 
                    content,
                    file_id: fileId 
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to post");
            }
            const newAnn = await res.json();
            // Optimistic update or just refetch
            setAnnouncements(prev => [newAnn, ...prev]);
            return newAnn;
        } catch (err) {
            throw err;
        }
    };

    useEffect(() => {
        fetchAnnouncements();
    }, [fetchAnnouncements]);

    return { announcements, loading, error, postAnnouncement, refresh: fetchAnnouncements };
}
