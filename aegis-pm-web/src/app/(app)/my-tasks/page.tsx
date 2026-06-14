"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, formatDistanceToNow, isPast } from "date-fns";
import { toast } from "sonner";
import {
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  ListChecks,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import { invalidateAllTaskDerived } from "@/lib/hooks/use-tasks";

export default function MyTasksPage() {
  const qc = useQueryClient();
  const tasks = useQuery({
    queryKey: ["employee", "tasks"],
    queryFn: () => api.employee.tasks(),
    // 8 s poll is a safety net when WS push is unavailable (e.g. Redis
    // down, token expired, background-tab throttle). In the happy path
    // the WS hook invalidates this query instantly on assignment so the
    // poll is a no-op most of the time.
    refetchInterval: 8_000,
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
  });

  const list = tasks.data ?? [];
  const open = list.filter((t) => t.status !== "done");
  const done = list.filter((t) => t.status === "done");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">My Tasks</h1>
        <p className="text-sm text-muted-foreground">
          Tasks your admin has assigned to you. Update your progress below.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            Open <span className="text-muted-foreground">· {open.length}</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tasks.isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {!tasks.isLoading && open.length === 0 && (
            <p className="text-sm text-muted-foreground">
              You&apos;re all caught up — nothing open right now.
            </p>
          )}
          <ul className="space-y-4">
            {open.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                onChanged={() => invalidateAllTaskDerived(qc)}
              />
            ))}
          </ul>
        </CardContent>
      </Card>

      {done.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Completed <span className="text-muted-foreground">· {done.length}</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5">
              {done.slice(0, 10).map((t) => (
                <li
                  key={t.id}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span className="truncate text-muted-foreground line-through">
                    {t.title}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {t.last_activity_at &&
                      formatDistanceToNow(new Date(t.last_activity_at), { addSuffix: true })}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Task row with progress slider ────────────────────────────────────────────

function TaskRow({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const qc = useQueryClient();
  const [pct, setPct]   = React.useState<number>(task.progress_pct ?? 0);
  const [note, setNote] = React.useState<string>("");

  React.useEffect(() => setPct(task.progress_pct ?? 0), [task.id, task.progress_pct]);

  const save = useMutation({
    mutationFn: (payload: { progress_pct: number; status?: string; note?: string }) =>
      api.employee.updateProgress(task.id, payload),
    onSuccess: () => {
      toast.success("Progress updated", { description: task.title });
      setNote("");
      invalidateAllTaskDerived(qc);
      qc.invalidateQueries({ queryKey: ["employee", "task-days", task.id] });
      onChanged();
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Failed to update"),
  });

  const deadlineOverdue =
    task.end_date && !isPast(new Date(task.end_date))
      ? false
      : Boolean(task.end_date) && task.status !== "done";

  return (
    <li className="rounded-md border border-border/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">{task.title}</span>
            <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
              {task.status}
            </span>
            {task.priority && task.priority !== "medium" && (
              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] uppercase text-amber-700 dark:text-amber-400">
                {task.priority}
              </span>
            )}
          </div>
          {task.description && (
            <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
              {task.description}
            </p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
            {task.start_date && (
              <span className="inline-flex items-center gap-1">
                <Calendar className="size-3" />
                starts {format(new Date(task.start_date), "MMM d")}
              </span>
            )}
            {task.end_date && (
              <span
                className={cn(
                  "inline-flex items-center gap-1",
                  deadlineOverdue && "text-destructive"
                )}
              >
                <Clock className="size-3" />
                due {format(new Date(task.end_date), "MMM d")}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Daily plan — breaks the task into per-day check-ins; progress
          is computed from completed days when present. */}
      <DailyPlanPanel task={task} onChanged={onChanged} />

      {/* Manual progress override — still available for tasks without a
          daily plan, or when the user wants a rough % without checking
          off individual days. */}
      <div className="mt-3 space-y-2 border-t border-border/40 pt-3">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={pct}
            onChange={(e) => setPct(Number(e.target.value))}
            className="flex-1 accent-primary"
          />
          <span className="w-10 text-right font-mono text-xs">{pct}%</span>
        </div>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note"
          className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs"
          maxLength={1000}
        />
        <div className="flex items-center justify-end gap-2">
          {task.status !== "done" && (
            <Button
              size="sm"
              variant="ghost"
              disabled={save.isPending}
              onClick={() =>
                save.mutate({ progress_pct: pct, note: note || undefined })
              }
            >
              Save progress
            </Button>
          )}
          {task.status !== "done" && pct < 100 && (
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() =>
                save.mutate({
                  progress_pct: 100,
                  status: "done",
                  note: note || undefined,
                })
              }
            >
              {save.isPending ? <Loader2 className="size-3.5 animate-spin" /> : "Mark done"}
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

// ── Daily plan panel ────────────────────────────────────────────────────────

function DailyPlanPanel({
  task,
  onChanged,
}: {
  task: Task;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);

  const days = useQuery({
    queryKey: ["employee", "task-days", task.id],
    queryFn: () => api.employee.listDays(task.id),
    enabled: open || task.progress_pct > 0,
    refetchInterval: open ? 15_000 : false,
  });

  const generate = useMutation({
    mutationFn: () => api.employee.generateDays(task.id),
    onSuccess: (res) => {
      toast.success(
        `Plan generated · ${res.total_days} day${res.total_days === 1 ? "" : "s"}`,
        {
          description:
            res.method === "llm"
              ? `AI-drafted (${res.model ?? "llm"})`
              : "Generic fallback (no AI key available)",
        }
      );
      qc.invalidateQueries({ queryKey: ["employee", "task-days", task.id] });
      invalidateAllTaskDerived(qc);
      onChanged();
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Failed to generate plan"),
  });

  const data = days.data;
  const hasPlan = !!data && data.total_days > 0;

  return (
    <div className="mt-3 rounded-md border border-border/60">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-accent"
      >
        <span className="inline-flex items-center gap-2 font-medium">
          <ListChecks className="size-3.5" /> Daily plan
          {hasPlan && (
            <span className="text-muted-foreground">
              · {data.completed}/{data.total_days} days · {data.progress_pct}%
            </span>
          )}
          {!hasPlan && (
            <span className="text-muted-foreground">· not generated yet</span>
          )}
        </span>
        {open ? (
          <ChevronUp className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="space-y-2 border-t border-border/40 px-3 py-3">
          {days.isLoading && (
            <div className="text-xs text-muted-foreground">Loading…</div>
          )}

          {!days.isLoading && !hasPlan && (
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                No daily breakdown yet. Generate one — the AI splits this task
                into day-by-day steps based on its timeline and scope.
              </p>
              <Button
                size="sm"
                disabled={generate.isPending}
                onClick={() => generate.mutate()}
              >
                {generate.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  "Generate plan"
                )}
              </Button>
            </div>
          )}

          {hasPlan && (
            <>
              <ul className="space-y-2">
                {data.entries.map((e) => (
                  <DayRow
                    key={e.id}
                    taskId={task.id}
                    dayNumber={e.day_number}
                    planned={e.planned_description ?? ""}
                    actual={e.actual_note ?? ""}
                    completedAt={e.completed_at}
                    onChanged={() => {
                      qc.invalidateQueries({ queryKey: ["employee", "task-days", task.id] });
                      onChanged();
                    }}
                  />
                ))}
              </ul>
              <div className="flex justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={generate.isPending}
                  onClick={() => generate.mutate()}
                  title="Regenerate the plan from scratch (wipes existing check-ins)"
                >
                  {generate.isPending ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    "Regenerate"
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DayRow({
  taskId,
  dayNumber,
  planned,
  actual,
  completedAt,
  onChanged,
}: {
  taskId: number;
  dayNumber: number;
  planned: string;
  actual: string;
  completedAt: string | null;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = React.useState(actual);
  React.useEffect(() => setNote(actual), [actual, completedAt]);

  const checkIn = useMutation({
    mutationFn: (v: { note: string; completed: boolean }) =>
      api.employee.checkInDay(taskId, dayNumber, v),
    onSuccess: (res) => {
      toast.success(
        `Day ${dayNumber} ${res.completed ? "checked in" : "re-opened"}`,
        { description: `${res.completed_days}/${res.total_days} days · ${res.progress_pct}%` }
      );
      qc.invalidateQueries({ queryKey: ["employee", "task-days", taskId] });
      invalidateAllTaskDerived(qc);
      onChanged();
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Check-in failed"),
  });

  const done = !!completedAt;

  return (
    <li
      className={cn(
        "rounded-md border border-border/60 p-2 text-xs",
        done && "bg-emerald-500/5 border-emerald-500/30"
      )}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          aria-label={done ? `Mark day ${dayNumber} not done` : `Mark day ${dayNumber} done`}
          onClick={() =>
            checkIn.mutate({
              note: note.trim(),
              completed: !done,
            })
          }
          disabled={checkIn.isPending}
          className={cn(
            "mt-0.5 grid size-5 place-items-center rounded-sm border text-[10px]",
            done
              ? "bg-emerald-500 border-emerald-500 text-white"
              : "border-input hover:border-foreground"
          )}
        >
          {done && <Check className="size-3" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">Day {dayNumber}</span>
            {done && completedAt && (
              <span className="text-[10px] text-muted-foreground">
                · {formatDistanceToNow(new Date(completedAt), { addSuffix: true })}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-muted-foreground">{planned || "—"}</p>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What did you do today?"
            rows={2}
            maxLength={2000}
            className="mt-1.5 w-full resize-y rounded border border-input bg-background px-2 py-1 text-xs"
          />
          <div className="mt-1 flex items-center justify-end gap-1.5">
            {!done ? (
              <Button
                size="sm"
                disabled={checkIn.isPending}
                onClick={() =>
                  checkIn.mutate({ note: note.trim(), completed: true })
                }
              >
                {checkIn.isPending ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  "Check in"
                )}
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                disabled={checkIn.isPending}
                onClick={() =>
                  checkIn.mutate({ note: note.trim(), completed: true })
                }
              >
                Update note
              </Button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}
