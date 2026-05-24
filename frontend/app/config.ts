/**
 * Frontend Configuration
 * Manages dynamic backend URL resolution to avoid hardcoding 127.0.0.1.
 */

// In SSR (Next.js server-side), window is not defined. 
// We use a safe check and fallback to localhost.
const getBackendHost = () => {
    if (typeof window !== "undefined") {
        return window.location.hostname;
    }
    return "localhost";
};

/**
 * The base API URL for the backend.
 * Priority: 
 * 1. NEXT_PUBLIC_API_URL environment variable
 * 2. Dynamic hostname based on current URL
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || `http://${getBackendHost()}:8000`;

/**
 * The base WebSocket URL for real-time features.
 */
export const WS_BASE_URL = (() => {
    const host = getBackendHost();
    const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${host}:8000`;
})();

console.log(`[Config] 🚀 API Base: ${API_BASE_URL}`);
console.log(`[Config] 🔄 WS Base: ${WS_BASE_URL}`);
