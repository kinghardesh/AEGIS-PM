"use client";

import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuth } from "@/lib/auth-context";

export type Notification = {
  id: number;
  user_id: number;
  kind: string;
  title: string;
  body: string | null;
  resource_type: string | null;
  resource_id: number | null;
  actor_user_id: number | null;
  read_at: string | null;
  created_at: string;
};

const WS_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, "ws").replace(/\/$/, "") ||
  "ws://127.0.0.1:8000";

/**
 * Subscribe to the authenticated user's notification stream.
 *
 * Responsibilities:
 *   - Keep an authenticated WebSocket open to /ws?token=...
 *   - On every incoming push, invalidate the notifications query so the
 *     bell count + list update immediately.
 *   - Show a toast for task assignments and completions (audible feedback).
 *   - Auto-reconnect with exponential backoff.
 */
export function useNotifications() {
  const { user, ready } = useAuth();
  const qc = useQueryClient();
  const wsRef = React.useRef<WebSocket | null>(null);
  const backoffRef = React.useRef(1000);

  // Persisted list — the source of truth after initial mount.
  const listQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.notifications.list(),
    enabled: ready && !!user,
    staleTime: 30_000,
  });

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api.notifications.unreadCount(),
    enabled: ready && !!user,
    staleTime: 30_000,
  });

  // WebSocket lifecycle.
  //
  // Auth model: we do NOT send the token in the URL. We open a plain
  // WS to /ws, then send {type:"auth",token:"..."} as the very first
  // message. The server waits up to 5s for that frame, validates the
  // JWT + session, and replies with {type:"ready"} or closes with
  // 4401 (unauthenticated) / 4408 (timeout). This prevents the token
  // from ever appearing in access logs, proxy logs, or browser history.
  //
  // Visibility-change wake: browsers throttle WS sockets in background
  // tabs and some kill them outright. We listen for visibilitychange and
  // kick off a reconnect on focus so the user's dashboard always has a
  // live stream when they're actively looking at it.
  React.useEffect(() => {
    if (!ready || !user) return;

    let disposed = false;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    function connect() {
      if (disposed) return;
      // Close any stale socket before opening a new one.
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        return;
      }
      const token = getToken();
      if (!token) return;

      const ws = new WebSocket(`${WS_BASE}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        // First frame: auth. Must be sent before the server's 5s timeout.
        ws.send(JSON.stringify({ type: "auth", token }));
      };

      ws.onmessage = (ev) => {
        let msg: { type: string; payload?: Record<string, unknown> };
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }

        if (msg.type === "ready") {
          backoffRef.current = 1000;
          // Heartbeat — detect half-open connections behind NAT/LBs.
          if (pingTimer) clearInterval(pingTimer);
          pingTimer = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send("ping");
          }, 25_000);
          return;
        }

        if (msg.type === "notification" || msg.type === "admin_notification") {
          const payload = (msg.payload ?? {}) as {
            title?: string;
            body?: string;
            kind?: string;
            resource_type?: string;
          };
          if (payload.title) {
            if (payload.kind === "task_completed") {
              toast.success(payload.title, { description: payload.body ?? undefined });
            } else {
              toast(payload.title, { description: payload.body ?? undefined });
            }
          }
          qc.invalidateQueries({ queryKey: ["notifications"] });

          // Task events (assigned / updated / completed) must re-run the
          // employee's dashboard + my-tasks queries AND the admin's
          // monitoring + per-employee task drawer queries so both sides
          // update live without waiting for the 30s poll.
          const isTaskEvent =
            payload.resource_type === "task" ||
            payload.kind === "task_assigned" ||
            payload.kind === "task_update" ||
            payload.kind === "task_completed";
          if (isTaskEvent) {
            qc.invalidateQueries({ queryKey: ["me", "tasks"] });
            qc.invalidateQueries({ queryKey: ["me", "projects"] });
            qc.invalidateQueries({ queryKey: ["employee", "tasks"] });
            qc.invalidateQueries({ queryKey: ["admin", "employee-monitoring"] });
            qc.invalidateQueries({ queryKey: ["admin", "employee-tasks"] });
          }
        }
      };

      ws.onclose = (ev) => {
        wsRef.current = null;
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        if (disposed) return;

        // 4401 = auth rejected. Don't retry blindly — token is bad/expired.
        // The api.ts 401 handler will bounce the user to /login soon enough.
        if (ev.code === 4401) return;

        const delay = Math.min(backoffRef.current, 15_000);
        backoffRef.current = Math.min(backoffRef.current * 2, 15_000);
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    // Wake on tab focus — if the socket died while backgrounded, reconnect
    // AND force a refetch of the data queries so the user sees the latest
    // state within a frame of returning to the tab.
    function onFocus() {
      if (disposed) return;
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        connect();
      }
      qc.invalidateQueries({ queryKey: ["me", "tasks"] });
      qc.invalidateQueries({ queryKey: ["employee", "tasks"] });
      qc.invalidateQueries({ queryKey: ["me", "projects"] });
    }
    function onVisibility() {
      if (document.visibilityState === "visible") onFocus();
    }
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      disposed = true;
      if (pingTimer) clearInterval(pingTimer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [ready, user, qc]);

  return {
    notifications: (listQuery.data ?? []) as Notification[],
    unread: unreadQuery.data?.count ?? 0,
    markRead: async (id: number) => {
      await api.notifications.markRead(id);
      await qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    markAllRead: async () => {
      await api.notifications.markAllRead();
      await qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  };
}
