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

export default function DashboardPage() {
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
        title="Dashboard"
        description="A snapshot of what your team is working on right now."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {KPIS.map((kpi) => (
          <Card key={kpi.label}>
            <CardHeader className="pb-2">
              <CardDescription>{kpi.label}</CardDescription>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                {kpi.value}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{kpi.hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {projects.data && projects.data.length > 0 && (
        <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Recent projects</CardTitle>
              <CardDescription>The 5 most recently updated.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {projects.data.slice(0, 5).map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="truncate font-medium">{p.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {Math.round(p.progress ?? 0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Alert breakdown</CardTitle>
              <CardDescription>Current state of all alerts.</CardDescription>
            </CardHeader>
            <CardContent>
              {alertStats.data ? (
                <ul className="space-y-2 text-sm">
                  {(["pending", "approved", "notified", "dismissed"] as const).map(
                    (k) => (
                      <li
                        key={k}
                        className="flex items-center justify-between"
                      >
                        <span className="capitalize text-muted-foreground">
                          {k}
                        </span>
                        <span className="font-mono">
                          {alertStats.data?.[k] ?? 0}
                        </span>
                      </li>
                    )
                  )}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Loading…</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

function fmt(n: number, loading: boolean) {
  return loading ? "—" : String(n);
}
