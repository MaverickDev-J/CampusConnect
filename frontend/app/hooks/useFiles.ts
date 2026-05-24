"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/app/context/auth-context";
import { API_BASE_URL } from "@/app/config";

// Updated Types matching the Multi-Tenant API
export interface FileMetadata {
    file_id: string;
    original_name: string;
    mime_type: string;
    file_type: string;
    file_size_bytes: number;
    classroom_id: string;
    source: {
        type: string;
        youtube_video_id: string | null;
    };
    academic: {
        doc_type: string;
        // Legacy fields kept as optional for compatibility during transition
        year?: number;
        branch?: string;
        subject?: string;
        unit?: number;
    };
    processing: {
        status: string;
        chunk_count: number;
        page_count: number | null;
        error: string | null;
    };
    visibility: string;
    uploaded_by: string;
    uploaded_at: string;
    playback_url: string;
}

interface FilesResponse {
    files: FileMetadata[];
    count: number;
}

interface FileFilters {
    classroom_id?: string | null;
    doc_type?: string | null;
    file_type?: string | null;
}

/**
 * useFiles: Hook to fetch files scoped by classroom or global filters.
 * @param classroomId Optional classroom ID to scope the results
 */
export function useFiles(classroomId?: string) {
    const [files, setFiles] = useState<FileMetadata[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const { user } = useAuth();

    const fetchFiles = useCallback(async () => {
        if (!user || !user.token) return;

        setLoading(true);
        setError(null);
        try {
            const token = user.token;
            const headers: HeadersInit = {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            };

            const params = new URLSearchParams();
            if (classroomId) params.append("classroom_id", classroomId);

            // Fetch from the new classroom-aware endpoint
            // If classroomId is provided, the backend enforces membership
            const res = await fetch(`${API_BASE_URL}/api/files?${params.toString()}`, {
                headers: headers,
            });

            if (!res.ok) {
                throw new Error(`Failed to fetch files: ${res.statusText}`);
            }

            const data: FilesResponse = await res.json();
            setFiles(data.files || []);
        } catch (err) {
            console.error(err);
            setError(err instanceof Error ? err.message : "An error occurred");
        } finally {
            setLoading(false);
        }
    }, [user, classroomId]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const uploadFile = async (
        file: File, 
        docType: string = "academic_material",
        onProgress?: (percent: number) => void
    ): Promise<{ file_id: string } | any> => {
        if (!user || !user.token) return;

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const formData = new FormData();
            formData.append("file", file);
            formData.append("classroom_id", classroomId || "");
            formData.append("doc_type", docType);

            xhr.upload.addEventListener("progress", (event) => {
                if (event.lengthComputable && onProgress) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    onProgress(percent);
                }
            });

            xhr.onreadystatechange = () => {
                if (xhr.readyState === XMLHttpRequest.DONE) {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            const result = JSON.parse(xhr.responseText);
                            fetchFiles(); // Refresh list
                            resolve(result);
                        } catch {
                            resolve({ success: true });
                        }
                    } else {
                        try {
                            const error = JSON.parse(xhr.responseText);
                            reject(new Error(error.detail || "Upload failed"));
                        } catch {
                            reject(new Error("Upload failed"));
                        }
                    }
                }
            };

            xhr.open("POST", `${API_BASE_URL}/api/upload/file`);
            xhr.setRequestHeader("Authorization", `Bearer ${user.token}`);
            xhr.send(formData);
        });
    };

    return { files, loading, error, refetch: fetchFiles, uploadFile };
}
