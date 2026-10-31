import { API_BASE_URL } from "@/app/config";

export function filePlaybackUrl(path: string, token?: string): string {
    const url = `${API_BASE_URL}${path}`;
    if (token && path.startsWith("/api/files/") && path.split("?")[0].endsWith("/download")) {
        return `${url}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
    }
    return url;
}
