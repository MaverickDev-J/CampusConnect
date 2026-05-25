/**
 * Frontend Configuration
 * ─────────────────────────────────────────────────────────
 * Production: set NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL in .env.local
 * Development: auto-detects localhost:8000 so no config needed locally.
 */

const getBackendUrl = () => {
    if (typeof window !== "undefined") {
        const hostname = window.location.hostname;
        const port = window.location.port;
        // If we are in dev (Next.js default port 3000), point to backend port 8000.
        // Otherwise (production Nginx on port 80/443), route through Nginx proxy.
        if (port === "3000") {
            return `http://${hostname}:8000`;
        }
        const protocol = window.location.protocol;
        return `${protocol}//${hostname}`;
    }
    return "http://localhost:8000";
};

const getWsUrl = () => {
    if (typeof window !== "undefined") {
        const hostname = window.location.hostname;
        const port = window.location.port;
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        if (port === "3000") {
            return `${protocol}://${hostname}:8000`;
        }
        return `${protocol}://${hostname}`;
    }
    return "ws://localhost:8000";
};

/**
 * HTTP API base URL.
 * Production:  set NEXT_PUBLIC_API_URL=https://yourdomain.com  (no trailing slash)
 * Development: falls back to http://localhost:8000
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || getBackendUrl();

/**
 * WebSocket base URL.
 * Production:  set NEXT_PUBLIC_WS_URL=wss://yourdomain.com   (no trailing slash)
 * Development: falls back to ws://localhost:8000
 */
export const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || getWsUrl();

if (typeof window !== "undefined") {
    console.log(`[Config] 🚀 API Base: ${API_BASE_URL}`);
    console.log(`[Config] 🔄 WS Base: ${WS_BASE_URL}`);
}
