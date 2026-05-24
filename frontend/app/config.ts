/**
 * Frontend Configuration
 * ─────────────────────────────────────────────────────────
 * Production: set NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL in .env.local
 * Development: auto-detects localhost:8000 so no config needed locally.
 */

const isDev = process.env.NODE_ENV === "development";

/**
 * HTTP API base URL.
 * Production:  set NEXT_PUBLIC_API_URL=https://yourdomain.com  (no trailing slash)
 * Development: falls back to http://localhost:8000
 */
export const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    (isDev ? "http://localhost:8000" : "");

/**
 * WebSocket base URL.
 * Production:  set NEXT_PUBLIC_WS_URL=wss://yourdomain.com   (no trailing slash)
 * Development: falls back to ws://localhost:8000
 */
export const WS_BASE_URL =
    process.env.NEXT_PUBLIC_WS_URL ||
    (isDev ? "ws://localhost:8000" : (() => {
        // Runtime fallback for browser (should not happen if env var is set)
        if (typeof window !== "undefined") {
            const proto = window.location.protocol === "https:" ? "wss" : "ws";
            return `${proto}://${window.location.host}`;
        }
        return "";
    })());

if (typeof window !== "undefined") {
    console.log(`[Config] 🚀 API Base: ${API_BASE_URL}`);
    console.log(`[Config] 🔄 WS Base: ${WS_BASE_URL}`);
}
