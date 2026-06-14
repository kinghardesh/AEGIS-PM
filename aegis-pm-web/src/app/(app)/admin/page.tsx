"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Activity, Bot, CheckCircle2, Database, Loader2, User, Users } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function AdminDashboardPage() {
  const qc = useQueryClient();
  const dash = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: () => api.admin.dashboard(),
    refetchInterval: 15_000,
  });
  const activity = useQuery({
    queryKey: ["admin", "activity"],
    queryFn: () => api.admin.activity({ since_hours: 24, limit: 30 }),
    refetchInterval: 15_000,
  });
  const sessions = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: () => api.admin.sessions(),
    refetchInterval: 30_000,
  });
  const unassigned = useQuery({
    queryKey: ["admin", "unassigned-tasks"],
    queryFn: () => api.admin.unassignedTasks(),
    refetchInterval: 10_000,
  });
  const employees = useQuery({
    queryKey: ["admin", "employees-list"],
    queryFn: () => api.employees.list(),
    staleTime: 30_000,
  });

  // Build a grouped option list: humans first (so the admin sees them
  // before AI), then AI. Each option carries employee_id + type + current
  // load so the dropdown label stays informative.
  type MemberOption = {
    id: number;
    name: string;
    type: "AI" | "HUMAN";
  };
  const members: MemberOption[] = React.useMemo(() => {
    const list = (employees.data ?? []).map((e) => ({
      id: e.id,
      name: e.name,
      type: (e.email ?? "").toLowerCase().endsWith("@aegis.ai") ? "AI" as const : "HUMAN" as const,
    }));
    list.sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name) : a.type === "HUMAN" ? -1 : 1
    );
    return list;
  }, [employees.data]);

  // Per-row selection state. Key = task_id, value = employee_id (or "auto").
  const [selected, setSelected] = React.useState<Record<number, string>>({});

  const assignManual = useMutation({
    mutationFn: (v: { task_id: number; employee_id: number; employee_name: string }) =>
      api.tasks.assign(v.task_id, v.employee_id, v.employee_name),
    onSuccess: (_, v) => {
      toast.success(`Assigned to ${v.employee_name}`);
      qc.invalidateQueries({ queryKey: ["admin", "unassigned-tasks"] });
      qc.invalidateQueries({ queryKey: ["admin", "employee-monitoring"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Assignment failed"),
  });

  const assignAuto = useMutation({
    mutationFn: (taskId: number) => api.admin.balanceAssign(taskId, { confirm: true }),
    onSuccess: (res) => {
      if (res.assigned) {
        toast.success(`Auto-assigned to ${res.assigned.name}`, {
          description: `${res.assigned.type} · match ${Math.round(res.assigned.score * 100)}%`,
        });
      }
      qc.invalidateQueries({ queryKey: ["admin", "unassigned-tasks"] });
      qc.invalidateQueries({ queryKey: ["admin", "employee-monitoring"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Assignment failed"),
  });

  function doAssign(task: { task_id: number; recommended: { member_id: number; member_name: string } | null }) {
    const raw = selected[task.task_id] ?? "auto";
    if (raw === "auto") {
      assignAuto.mutate(task.task_id);
      return;
    }
    const empId = Number(raw);
    const m = members.find((x) => x.id === empId);
    if (!m) return;
    assignManual.mutate({
      task_id: task.task_id,
      employee_id: m.id,
      employee_name: m.name,
    });
  }

  const d = dash.data;
  const tbs = d?.tasks_by_status ?? {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Admin Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Real-time system state, task overview, and who did what.
        </p>
      </div>

      {/* ── System row ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="System"
          value={d?.system.status ?? "…"}
          hint={d?.system.database}
          icon={<Database className="size-4" />}
          tone={d?.system.status === "ok" ? "good" : "warn"}
        />
        <StatCard
          label="Active Sessions"
          value={String(d?.system.active_sessions ?? "…")}
          hint="Non-revoked devices"
          icon={<Users className="size-4" />}
        />
        <StatCard
          label="Completed"
          value={String(tbs.completed ?? 0)}
          hint="Tasks closed"
          icon={<CheckCircle2 className="size-4" />}
          tone="good"
        />
        <StatCard
          label="Pending"
          value={String(tbs.pending ?? 0)}
          hint="Awaiting triage"
          icon={<Activity className="size-4" />}
          tone={(tbs.pending ?? 0) > 0 ? "warn" : undefined}
        />
      </div>

      {/* ── Unassigned tasks with balancer recommendations ─────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Unassigned tasks · balancer</CardTitle>
          <CardDescription>
            Top recommendation per task, balancing skill match, current workload,
            and AI/HUMAN distribution.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {unassigned.isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {unassigned.isSuccess && unassigned.data.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing to assign — every task has an owner.</p>
          )}
          <ul className="space-y-3">
            {unassigned.data?.map((t) => {
              const chosen = selected[t.task_id] ?? "auto";
              const isBusy =
                (assignManual.isPending && assignManual.variables?.task_id === t.task_id) ||
                (assignAuto.isPending && assignAuto.variables === t.task_id);
              return (
                <li
                  key={t.task_id}
                  className="flex flex-col gap-2 border-b border-border/60 pb-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{t.title}</span>
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] uppercase",
                          t.priority === "high"
                            ? "bg-red-500/10 text-red-700 dark:text-red-400"
                            : t.priority === "low"
                            ? "bg-muted text-muted-foreground"
                            : "bg-amber-500/10 text-amber-700 dark:text-amber-400"
                        )}
                      >
                        {t.priority}
                      </span>
                    </div>
                    {t.required_skills.length > 0 && (
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {t.required_skills.slice(0, 6).map((s) => (
                          <span
                            key={s}
                            className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                    {t.recommended && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span>Balancer suggests:</span>
                        <TypeBadge type={t.recommended.member_type} />
                        <span className="font-medium text-foreground">
                          {t.recommended.member_name}
                        </span>
                        <span>({Math.round(t.recommended.score * 100)}%)</span>
                        <span className="opacity-70">· {t.recommended.reason}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <select
                      value={chosen}
                      onChange={(e) =>
                        setSelected((s) => ({ ...s, [t.task_id]: e.target.value }))
                      }
                      className="rounded-md border border-input bg-background px-2 py-1.5 text-xs max-w-[200px]"
                      disabled={isBusy}
                    >
                      <option value="auto">
                        Auto-balance{t.recommended ? ` (${t.recommended.member_name})` : ""}
                      </option>
                      <optgroup label="👤 Humans">
                        {members
                          .filter((m) => m.type === "HUMAN")
                          .map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
                          ))}
                      </optgroup>
                      <optgroup label="🤖 AI">
                        {members
                          .filter((m) => m.type === "AI")
                          .map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
                          ))}
                      </optgroup>
                    </select>
                    <Button
                      size="sm"
                      disabled={isBusy || (chosen === "auto" && !t.recommended)}
                      onClick={() => doAssign(t)}
                    >
                      {isBusy ? <Loader2 className="size-3.5 animate-spin" /> : "Assign"}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ── Who completed what ─────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Who completed what</CardTitle>
          </CardHeader>
          <CardContent>
            {d?.recent_completions.length === 0 && (
              <p className="text-sm text-muted-foreground">No completions yet.</p>
            )}
            <ul className="space-y-2">
              {d?.recent_completions.map((c) => (
                <li
                  key={c.alert_id}
                  className="flex items-start justify-between gap-2 border-b border-border/60 pb-2 last:border-b-0"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{c.task_key}</div>
                    {c.task_summary && (
                      <div className="line-clamp-1 text-xs text-muted-foreground">
                        {c.task_summary}
                      </div>
                    )}
                    <div className="mt-0.5 text-xs">
                      <span className="font-medium text-foreground">{c.completed_by ?? "—"}</span>
                      {c.completed_by_role && (
                        <span className="ml-1 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                          {c.completed_by_role}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 text-[11px] text-muted-foreground">
                    {formatDistanceToNow(new Date(c.completed_at), { addSuffix: true })}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* ── Top completers (30d) ───────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Top completers · 30d</CardTitle>
          </CardHeader>
          <CardContent>
            {d?.completions_by_user_30d.length === 0 && (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            )}
            <ul className="space-y-2">
              {d?.completions_by_user_30d.map((r) => (
                <li key={r.user} className="flex items-center justify-between gap-2 text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="truncate font-medium">{r.user}</span>
                    <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                      {r.role}
                    </span>
                  </div>
                  <span className="font-mono text-xs">{r.completed}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* ── Activity feed ────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Activity · last 24h</CardTitle>
        </CardHeader>
        <CardContent>
          {activity.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No activity yet.</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-2 text-left font-medium">When</th>
                  <th className="py-2 text-left font-medium">User</th>
                  <th className="py-2 text-left font-medium">Action</th>
                  <th className="py-2 text-left font-medium">Status</th>
                  <th className="py-2 text-left font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {activity.data?.map((a) => (
                  <tr key={a.id} className="border-b border-border/40">
                    <td className="py-1.5 text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}
                    </td>
                    <td className="py-1.5 text-xs">{a.user_handle ?? "—"}</td>
                    <td className="py-1.5 font-mono text-xs">{a.action}</td>
                    <td className="py-1.5 text-xs">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 font-mono text-[10px]",
                          a.status_code && a.status_code >= 400
                            ? "bg-destructive/10 text-destructive"
                            : "bg-secondary text-muted-foreground"
                        )}
                      >
                        {a.status_code ?? "—"}
                      </span>
                    </td>
                    <td className="py-1.5 font-mono text-xs text-muted-foreground">
                      {a.ip_address ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* ── Active sessions ──────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
        </CardHeader>
        <CardContent>
          {sessions.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No active sessions.</p>
          )}
          <ul className="space-y-2">
            {sessions.data?.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 last:border-b-0"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {s.user_handle}{" "}
                    <span className="ml-1 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                      {s.role}
                    </span>
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {s.device || "unknown device"} · {s.ip_address}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    last seen {formatDistanceToNow(new Date(s.last_seen_at), { addSuffix: true })}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await api.admin.revokeSession(s.id);
                    sessions.refetch();
                  }}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function TypeBadge({ type }: { type: "AI" | "HUMAN" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        type === "AI"
          ? "bg-primary/10 text-primary"
          : "bg-secondary text-muted-foreground"
      )}
    >
      {type === "AI" ? <Bot className="size-3" /> : <User className="size-3" />}
      {type === "AI" ? "AI" : "Human"}
    </span>
  );
}

function StatCard({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ReactNode;
  tone?: "good" | "warn";
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 pt-6">
        <div
          className={cn(
            "grid size-9 place-items-center rounded-md",
            tone === "good"
              ? "bg-green-500/10 text-green-600"
              : tone === "warn"
              ? "bg-amber-500/10 text-amber-600"
              : "bg-secondary text-muted-foreground"
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="truncate text-lg font-semibold capitalize">{value}</div>
          {hint && <div className="truncate text-[11px] text-muted-foreground">{hint}</div>}
        </div>
      </CardContent>
    </Card>
  );
}
