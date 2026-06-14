"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import { Bot, Calendar, Clock, Inbox, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Task } from "@/lib/types";
import { PriorityBadge, StatusBadge } from "./task-badge";

type Agent = {
  id: number;
  name: string;
  role: string | null;
  email: string | null;
};

/**
 * Right-side drawer showing the full task list for one agent/employee.
 *
 * Data is fetched lazily — only when `agent` becomes non-null. Queries
 * are cached per-agent so re-opening the same card is instant.
 *
 * The drawer itself is a framer-motion element with an overlay. ESC or
 * a backdrop click closes it. Focus returns to the triggering card via
 * the parent — this component is stateless about focus.
 */
export function TaskDrawer({
  agent,
  onClose,
}: {
  agent: Agent | null;
  onClose: () => void;
}) {
  const isAi = !!agent?.email?.endsWith("@aegis.ai");

  const tasks = useQuery<Task[]>({
    queryKey: ["admin", "employee-tasks", agent?.id],
    queryFn: () => api.admin.employeeTasks(agent!.id),
    enabled: !!agent,
    staleTime: 15_000,
  });

  // ESC to close.
  React.useEffect(() => {
    if (!agent) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [agent, onClose]);

  return (
    <AnimatePresence>
      {agent && (
        <>
          {/* Overlay */}
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]"
          />

          {/* Drawer */}
          <motion.aside
            key="drawer"
            role="dialog"
            aria-modal="true"
            aria-label={`Tasks for ${agent.name}`}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 36 }}
            className={cn(
              "fixed right-0 top-0 z-50 flex h-dvh w-full max-w-md flex-col",
              "border-l border-border bg-background shadow-2xl"
            )}
          >
            {/* Header */}
            <header className="flex items-start gap-3 border-b border-border px-5 py-4">
              <div
                className={cn(
                  "grid size-10 shrink-0 place-items-center rounded-full text-sm font-semibold",
                  isAi ? "bg-primary/10 text-primary" : "bg-secondary"
                )}
              >
                {isAi ? <Bot className="size-5" /> : initials(agent.name)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">{agent.name}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {agent.role ?? "—"}
                </div>
              </div>
              <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
                <X className="size-4" />
              </Button>
            </header>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {tasks.isLoading && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Loading tasks…
                </div>
              )}
              {tasks.isError && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  {(tasks.error as Error).message}
                </div>
              )}

              {tasks.isSuccess && tasks.data.length === 0 && <EmptyState />}

              {tasks.isSuccess && tasks.data.length > 0 && (
                <ul className="space-y-3">
                  {tasks.data.map((t) => (
                    <TaskRow key={t.id} task={t} />
                  ))}
                </ul>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

// ── Task row ──────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: Task }) {
  return (
    <li className="rounded-md border border-border/60 p-3">
      <div className="mb-1 flex items-center gap-2">
        <StatusBadge status={task.status} />
        <PriorityBadge priority={task.priority} />
        {typeof task.progress_pct === "number" && task.progress_pct > 0 && (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            {task.progress_pct}%
          </span>
        )}
      </div>

      <div className="font-medium">{task.title}</div>

      {task.description && (
        <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
          {task.description}
        </p>
      )}

      {task.progress_pct > 0 && task.status !== "done" && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${task.progress_pct}%` }}
          />
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        {task.start_date && (
          <span className="inline-flex items-center gap-1">
            <Calendar className="size-3" /> starts {format(new Date(task.start_date), "MMM d")}
          </span>
        )}
        {task.end_date && (
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" /> due {format(new Date(task.end_date), "MMM d")}
          </span>
        )}
        {task.last_activity_at && (
          <span className="text-muted-foreground/80">
            updated {formatDistanceToNow(new Date(task.last_activity_at), { addSuffix: true })}
          </span>
        )}
        {!task.last_activity_at && task.created_at && (
          <span className="text-muted-foreground/80">
            created {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
          </span>
        )}
      </div>
    </li>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center">
      <div className="grid size-10 place-items-center rounded-full bg-muted">
        <Inbox className="size-4 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">No tasks assigned</p>
      <p className="max-w-xs text-xs text-muted-foreground">
        Once an admin assigns a task, it&apos;ll show up here in real time.
      </p>
    </div>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
