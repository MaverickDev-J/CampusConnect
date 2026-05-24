"use client";

import { useEffect, useRef, useCallback } from "react";
import { WS_BASE_URL } from "@/app/config";

/**
 * useClassroomSocket — Real-time event listener for a specific classroom.
 * Handles JWT auth, automatic reconnection with exponential backoff,
 * and a 30-second heartbeat to keep the connection alive.
 */
export function useClassroomSocket(
    classroomId: string | undefined,
    user: any,
    onMessage: (data: { type: string; [key: string]: any }) => void
) {
    const socketRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const reconnectAttempts = useRef(0);

    const connect = useCallback(() => {
        if (!classroomId || !user) return;

        let isMounted = true;

        const connectSocket = () => {
            if (!user?.token || !classroomId || !isMounted) return;

            // ✅ Use centralized WS URL to avoid hardcoding 127.0.0.1
            const url = `${WS_BASE_URL}/ws/classroom/${classroomId}?token=${encodeURIComponent(user.token)}`;
            const ws = new WebSocket(url);
            socketRef.current = ws;

            ws.onopen = () => {
                if (!isMounted) { ws.close(); return; }
                console.log(`[useClassroomSocket] ✅ Connected to classroom: ${classroomId}`);
                reconnectAttempts.current = 0;

                // Start 30-second ping to keep connection alive
                // (server closes after 60s without a message)
                pingIntervalRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send("ping");
                    }
                }, 30_000);
            };

            ws.onmessage = (event) => {
                if (!isMounted) return;
                if (event.data === "pong") return; // Ignore server heartbeat responses
                try {
                    const data = JSON.parse(event.data);
                    onMessage(data);
                } catch (err) {
                    console.error("[useClassroomSocket] ❌ Error parsing message:", err);
                }
            };

            ws.onclose = (event) => {
                if (!isMounted) return;
                if (pingIntervalRef.current) {
                    clearInterval(pingIntervalRef.current);
                    pingIntervalRef.current = null;
                }

                // 4001 = auth failed, 4003 = not a member — don't auto-reconnect
                if (event.code === 4001 || event.code === 4003) {
                    console.error(`[useClassroomSocket] ⛔ Auth/permission denied (${event.code}): ${event.reason}. Not reconnecting.`);
                    return;
                }

                if (event.code !== 1000 && event.code !== 1001) {
                    console.warn(`[useClassroomSocket] ⚠️ Closed (${event.code}: ${event.reason || "None"})`);
                    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
                    reconnectAttempts.current += 1;
                    console.log(`[useClassroomSocket] 🔄 Reconnecting in ${delay / 1000}s...`);
                    reconnectTimeoutRef.current = setTimeout(connectSocket, delay);
                } else {
                    console.log(`[useClassroomSocket] Connection closed normally (${event.code})`);
                }
                socketRef.current = null;
            };

            ws.onerror = (err: any) => {
                if (!isMounted) return;
                const states = ["CONNECTING", "OPEN", "CLOSING", "CLOSED"];
                console.error(`[useClassroomSocket] ❌ Error (State: ${states[ws?.readyState ?? 3]})`, {
                    type: err.type,
                    target: err.target?.url,
                });
            };
        };

        const timeoutId = setTimeout(connectSocket, 50);

        return () => {
            isMounted = false;
            clearTimeout(timeoutId);
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
            if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
            if (socketRef.current) {
                if (
                    socketRef.current.readyState === WebSocket.OPEN ||
                    socketRef.current.readyState === WebSocket.CONNECTING
                ) {
                    socketRef.current.close(1000, "Component unmounted");
                }
                socketRef.current = null;
            }
        };
    }, [classroomId, user?.token, onMessage]);

    useEffect(() => {
        const cleanup = connect();
        return cleanup;
    }, [connect]);

    return {
        isConnected: !!socketRef.current && socketRef.current.readyState === WebSocket.OPEN,
    };
}
