"use client";

import { PageHeader } from "@/components/app-shell/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useProjects } from "@/lib/hooks/use-projects";
import { useEmployees } from "@/lib/hooks/use-employees";
import { useAlertStats } from "@/lib/hooks/use-alerts";
import { useAuth } from "@/lib/auth-context";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";
import Link from "next/link";

export default function DashboardPage() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  // Users see only their assignments; admins see the full workspace view.
  if (user?.role !== "admin") return <UserDashboard />;
  return <AdminWorkspaceDashboard />;
}

// ── User dashboard ────────────────────────────────────────────────────────────

function UserDashboard() {
  const { user } = useAuth();
  const tasks = useQuery({
    queryKey: ["me", "tasks"],
    queryFn: () => api.alerts.myTasks(),
    refetchInterval: 8_000,
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
  });
  const projects = useQuery({
    queryKey: ["me", "projects"],
    queryFn: () => api.alerts.myProjects(),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  const openTasks = (tasks.data ?? []).filter((t) => t.status !== "done");
  const doneTasks = (tasks.data ?? []).filter((t) => t.status === "done");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome, {user?.full_name || user?.user_id}
        </h1>
        <p className="text-sm text-muted-foreground">
          Your assigned tasks and projects.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Open tasks" value={openTasks.length} loading={tasks.isLoading} />
        <Stat label="Completed" value={doneTasks.length} loading={tasks.isLoading} />
        <Stat label="Projects" value={projects.data?.length ?? 0} loading={projects.isLoading} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>My tasks</CardTitle>
          <CardDescription>
            <Link href="/my-tasks" className="text-primary hover:underline">
              Open full list →
            </Link>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tasks.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!tasks.isLoading && openTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing assigned to you yet — your admin will link you to tasks soon.
            </p>
          )}
          <ul className="space-y-2">
            {openTasks.slice(0, 6).map((t) => (
              <li
                key={t.id}
                className="flex items-start justify-between gap-3 border-b border-border/60 pb-2 last:border-b-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{t.title}</span>
                    <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                      {t.status}
                    </span>
                  </div>
                  {t.description && (
                    <p className="line-clamp-1 text-xs text-muted-foreground">
                      {t.description}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {t.created_at &&
                    formatDistanceToNow(new Date(t.created_at), { addSuffix: true })}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>My projects</CardTitle>
          <CardDescription>Projects you&apos;re contributing to.</CardDescription>
        </CardHeader>
        <CardContent>
          {projects.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!projects.isLoading && (projects.data?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">No projects yet.</p>
          )}
          <ul className="space-y-2">
            {projects.data?.map((p) => (
              <li
                key={p.id}
                className="border-b border-border/60 pb-2 last:border-b-0"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium truncate">{p.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {p.my_done}/{p.my_total} mine
                  </span>
                </div>
                {p.description && (
                  <p className="line-clamp-1 text-xs text-muted-foreground">
                    {p.description}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  loading,
}: {
  label: string;
  value: number;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold">{loading ? "—" : value}</div>
      </CardContent>
    </Card>
  );
}

// ── Admin workspace dashboard (existing content) ─────────────────────────────

function AdminWorkspaceDashboard() {
  const projects = useProjects();
  const employees = useEmployees();
  const alertStats = useAlertStats();

  const activeProjects =
    projects.data?.filter((p) => p.status === "active").length ?? 0;
  const tasksInFlight =
    projects.data?.reduce(
      (acc, p) => acc + (p.task_stats?.in_progress ?? 0),
      0
    ) ?? 0;
  const alertsPending = alertStats.data?.pending ?? 0;
  const utilization = (() => {
    if (!employees.data?.length) return 0;
    const avg =
      employees.data.reduce((a, e) => a + e.current_load, 0) /
      employees.data.length;
    return Math.round(Math.min(100, avg * 15));
  })();

  const KPIS = [
    {
      label: "Active projects",
      value: fmt(activeProjects, projects.isLoading),
      hint: "Across your workspace",
    },
    {
      label: "Tasks in flight",
      value: fmt(tasksInFlight, projects.isLoading),
      hint: "In progress right now",
    },
    {
      label: "Alerts pending",
      value: fmt(alertsPending, alertStats.isLoading),
      hint: "Awaiting human review",
    },
    {
      label: "Team utilization",
      value: employees.isLoading ? "—" : `${utilization}%`,
      hint: "Avg. load across team",
    },
  ];

  return (
    <>
      <PageHeader
        title="Workspace"
        description="Everything you need to see is below. Keep shipping."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {KPIS.map((k) => (
          <Card key={k.label}>
            <CardHeader className="pb-2">
              <CardDescription>{k.label}</CardDescription>
              <CardTitle className="text-2xl font-semibold">{k.value}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{k.hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

function fmt(n: number, loading: boolean): string {
  return loading ? "—" : String(n);
}
