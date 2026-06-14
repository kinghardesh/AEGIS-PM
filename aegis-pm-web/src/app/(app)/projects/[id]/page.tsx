"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Sparkles,
  UserPlus,
  FileText,
  BookOpen,
  Bot,
  User,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useAssignAll,
  useAutoAssignAll,
  useParsePrd,
  useProject,
  useProjectTasks,
  useUnassignAll,
} from "@/lib/hooks/use-projects";
import { useEmployees } from "@/lib/hooks/use-employees";
import {
  useAssignTask,
  useGenerateInstructions,
  useSetTaskStatus,
} from "@/lib/hooks/use-tasks";
import type { ExecutorStatus, Task } from "@/lib/types";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);

  const project = useProject(id);
  const tasks = useProjectTasks(id);
  const employees = useEmployees();
  const parse = useParsePrd();
  const assignAll = useAssignAll();
  const autoAssignAll = useAutoAssignAll();
  const unassignAll = useUnassignAll();
  const setStatus = useSetTaskStatus(id);
  const generate = useGenerateInstructions(id);
  const assign = useAssignTask(id);

  const [openTask, setOpenTask] = React.useState<Task | null>(null);

  return (
    <>
      <button
        onClick={() => router.push("/projects")}
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        All projects
      </button>

      <PageHeader
        title={project.data?.name ?? "Project"}
        description={project.data?.description ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => parse.mutate(id)}
              disabled={parse.isPending}
            >
              <Sparkles className="size-4" />
              {parse.isPending ? "Generating…" : "Parse PRD"}
            </Button>
            <Button
              variant="outline"
              onClick={() => unassignAll.mutate(id)}
              disabled={unassignAll.isPending}
            >
              {unassignAll.isPending ? "Clearing…" : "Unassign all"}
            </Button>
            <Button
              variant="outline"
              onClick={() => assignAll.mutate(id)}
              disabled={assignAll.isPending || autoAssignAll.isPending}
            >
              <UserPlus className="size-4" />
              {assignAll.isPending ? "Assigning…" : "AI assign"}
            </Button>
            <Button
              onClick={() => autoAssignAll.mutate(id)}
              disabled={autoAssignAll.isPending || assignAll.isPending}
              title="Balanced: picks best-fit person (human or AI) for each task, preferring humans when skills are comparable."
            >
              <Sparkles className="size-4" />
              {autoAssignAll.isPending ? "Auto-assigning…" : "Auto-assign"}
            </Button>
          </div>
        }
      />

      <Card>
        <CardContent className="p-0">
          {tasks.isLoading && (
            <div className="space-y-2 p-6">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 animate-pulse rounded bg-muted"
                />
              ))}
            </div>
          )}
          {tasks.isError && (
            <div className="p-6 text-sm text-destructive">
              Could not load tasks: {(tasks.error as Error).message}
            </div>
          )}
          {tasks.data && tasks.data.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <FileText className="size-8 text-muted-foreground" />
              <p className="text-base font-medium">No tasks yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Click <span className="font-medium">Parse PRD</span> to break
                this project into actionable tasks.
              </p>
            </div>
          )}
          {tasks.data && tasks.data.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  <th className="px-6 py-3">Task</th>
                  <th className="px-6 py-3">Assignee</th>
                  <th className="px-6 py-3">Priority</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.data.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-border last:border-0 hover:bg-muted/30"
                  >
                    <td className="px-6 py-3">
                      <button
                        onClick={() => setOpenTask(t)}
                        className="block text-left"
                      >
                        <div className="font-medium">{t.title}</div>
                        {t.description && (
                          <div className="line-clamp-1 text-xs text-muted-foreground">
                            {t.description.replace(/\*\*/g, "").slice(0, 100)}
                          </div>
                        )}
                      </button>
                    </td>
                    <td className="px-6 py-3">
                      <AssigneeBadge
                        assignedName={t.assigned_name}
                        assignedTo={t.assigned_to}
                        employees={employees.data ?? []}
                      />
                    </td>
                    <td className="px-6 py-3">
                      <PriorityPill priority={t.priority} />
                    </td>
                    <td className="px-6 py-3">
                      <select
                        value={t.status}
                        onChange={(e) =>
                          setStatus.mutate({
                            taskId: t.id,
                            status: e.target.value,
                          })
                        }
                        className="rounded-md border border-input bg-background px-2 py-1 text-xs"
                      >
                        <option value="todo">Todo</option>
                        <option value="in_progress">In progress</option>
                        <option value="done">Done</option>
                        <option value="paused">Paused</option>
                      </select>
                    </td>
                    <td className="px-6 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setOpenTask(t)}
                        >
                          <BookOpen className="size-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {openTask && (
        <TaskDetailDrawer
          task={openTask}
          onClose={() => setOpenTask(null)}
          onGenerate={async () => {
            const res = await generate.mutateAsync(openTask.id);
            setOpenTask({ ...openTask, description: res.description });
          }}
          generating={generate.isPending}
          employees={employees.data ?? []}
          onAssign={async (employeeId, employeeName) => {
            await assign.mutateAsync({
              taskId: openTask.id,
              employeeId,
              employeeName,
            });
          }}
        />
      )}
    </>
  );
}

function ExecutorStatusPill({ status }: { status: ExecutorStatus }) {
  if (!status) return null;
  const map: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
    queued: {
      label: "Queued",
      icon: <Bot className="size-3" />,
      cls: "bg-muted text-muted-foreground ring-border",
    },
    running: {
      label: "Running",
      icon: <Loader2 className="size-3 animate-spin" />,
      cls: "bg-sky-500/10 text-sky-700 ring-sky-500/20 dark:text-sky-400",
    },
    done: {
      label: "Done",
      icon: <CheckCircle2 className="size-3" />,
      cls: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
    },
    failed: {
      label: "Failed",
      icon: <AlertCircle className="size-3" />,
      cls: "bg-destructive/10 text-destructive ring-destructive/20",
    },
  };
  const m = map[status];
  if (!m) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${m.cls}`}
    >
      {m.icon}
      {m.label}
    </span>
  );
}

function AssigneeBadge({
  assignedName,
  assignedTo,
  employees,
}: {
  assignedName: string | null;
  assignedTo: number | null;
  employees: { id: number; email?: string | null }[];
}) {
  if (!assignedName) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  // Classify AI vs Human by the aegis.ai email convention (mirrors
  // the backend balancer's _classify()). Unknown/missing email → Human.
  const emp = employees.find((e) => e.id === assignedTo);
  const isAi =
    !!emp?.email && (emp.email as string).toLowerCase().endsWith("@aegis.ai");
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs ${
        isAi
          ? "bg-primary/10 text-primary"
          : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      }`}
      title={isAi ? "AI agent" : "Human employee"}
    >
      {isAi ? <Bot className="size-3" /> : <User className="size-3" />}
      <span className="max-w-[140px] truncate">{assignedName}</span>
    </span>
  );
}

function PriorityPill({ priority }: { priority: string }) {
  const styles: Record<string, string> = {
    high: "bg-rose-500/10 text-rose-700 ring-rose-500/20 dark:text-rose-400",
    medium:
      "bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400",
    low: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
  };
  const cls =
    styles[priority] ?? "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {priority}
    </span>
  );
}

function TaskDetailDrawer({
  task,
  onClose,
  onGenerate,
  generating,
  employees,
  onAssign,
}: {
  task: Task;
  onClose: () => void;
  onGenerate: () => void;
  generating: boolean;
  employees: { id: number; name: string }[];
  onAssign: (id: number, name: string) => Promise<void>;
}) {
  const isWeak =
    !task.description ||
    task.description.length < 80 ||
    /derived from PRD/i.test(task.description);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-foreground/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto border-l border-border bg-popover text-popover-foreground shadow-2xl"
      >
        <header className="border-b border-border px-6 py-5">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Task #{task.id}
          </p>
          <h2 className="mt-1 text-lg font-semibold">{task.title}</h2>
          <p className="mt-2 text-xs text-muted-foreground">
            {task.priority} priority · {task.estimated_hours}h ·{" "}
            {task.assigned_name ?? "unassigned"}
          </p>
        </header>

        <div className="flex-1 px-6 py-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Developer brief
            </h3>
            <Button
              size="sm"
              variant="outline"
              onClick={onGenerate}
              disabled={generating}
            >
              <Sparkles className="size-3.5" />
              {generating
                ? "Generating…"
                : isWeak
                  ? "Generate with AI"
                  : "Regenerate"}
            </Button>
          </div>
          {task.description ? (
            <div
              className="prose prose-sm max-w-none text-sm leading-relaxed text-foreground"
              dangerouslySetInnerHTML={{
                __html: renderBriefHtml(task.description),
              }}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              No instructions yet. Click Generate to create them.
            </p>
          )}

          {task.executor_output && (
            <div className="mt-8 border-t border-border pt-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Executor output
                  {task.agent_type && (
                    <span className="ml-2 rounded-md bg-secondary px-1.5 py-0.5 font-mono text-[10px] normal-case tracking-normal">
                      {task.agent_type}
                    </span>
                  )}
                </h3>
                <ExecutorStatusPill status={task.executor_status} />
              </div>
              <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                {task.executor_output}
              </pre>
            </div>
          )}

          {task.executor_error && (
            <div className="mt-8 border-t border-border pt-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-destructive">
                Executor error
              </h3>
              <pre className="whitespace-pre-wrap break-words rounded-md border border-destructive/20 bg-destructive/5 p-3 font-mono text-[11px] text-destructive">
                {task.executor_error}
              </pre>
            </div>
          )}

          <div className="mt-8 border-t border-border pt-5">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Assign to
            </h3>
            <div className="flex flex-wrap gap-2">
              {employees.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No team members yet. Add one in Team.
                </p>
              )}
              {employees.map((e) => (
                <Button
                  key={e.id}
                  size="sm"
                  variant="outline"
                  onClick={() => onAssign(e.id, e.name)}
                >
                  {e.name}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <footer className="border-t border-border px-6 py-4">
          <Button variant="ghost" onClick={onClose} className="w-full">
            Close
          </Button>
        </footer>
      </aside>
    </div>
  );
}

function renderBriefHtml(md: string) {
  // Tiny markdown subset: **bold**, line breaks, escape HTML.
  const escaped = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}
