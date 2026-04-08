"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDistanceToNow } from "date-fns";
import { PageHeader } from "@/components/app-shell/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api } from "@/lib/api";

const COLORS = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899"];

export default function AnalyticsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["analytics"],
    queryFn: api.analytics,
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Analytics" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
                <div className="mt-3 h-8 w-1/3 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="Analytics" />
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            {(error as Error)?.message ?? "Could not load analytics."}
          </CardContent>
        </Card>
      </>
    );
  }

  const m = data.metrics;

  const KPIS = [
    {
      label: "Total tasks",
      value: m.total_tasks,
      hint: `${m.tasks_done} done · ${m.tasks_in_progress} in progress`,
    },
    {
      label: "Completion rate",
      value: `${m.task_completion_rate}%`,
      hint: `${m.tasks_done}/${m.total_tasks} tasks done`,
    },
    {
      label: "Alerts pending",
      value: m.pending,
      hint: `${m.total_resolved} resolved · ${m.resolution_rate}%`,
    },
    {
      label: "Team capacity",
      value: `${m.available_employees}/${m.total_employees}`,
      hint: "Available members",
    },
  ];

  const taskStatusData = Object.entries(data.task_status_dist).map(
    ([k, v]) => ({ name: humanize(k), value: v })
  );
  const taskPriorityData = Object.entries(data.task_priority_dist).map(
    ([k, v]) => ({ name: humanize(k), value: v })
  );
  const trendData = data.daily_trend.map((d) => ({
    label: d.label,
    alerts: d.count,
  }));
  const workloadData = data.employee_workload.map((e) => ({
    name: e.name,
    Todo: e.todo,
    "In progress": e.in_progress,
    Done: e.done,
  }));
  const assigneeData = data.assignee_breakdown.slice(0, 8).map((a) => ({
    name: a.assignee,
    Pending: a.pending,
    Approved: a.approved,
  }));
  const projectData = data.projects_summary.map((p) => ({
    name: p.name.length > 16 ? p.name.slice(0, 14) + "…" : p.name,
    Done: p.completed_tasks,
    Remaining: p.total_tasks - p.completed_tasks,
    completion: p.completion_pct,
  }));

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Throughput, team load, alert volume, and trends."
      />

      {/* KPI strip */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {KPIS.map((k) => (
          <Card key={k.label}>
            <CardHeader className="pb-2">
              <CardDescription>{k.label}</CardDescription>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                {k.value}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{k.hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Trend + Status */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Alert volume — last 7 days</CardTitle>
            <CardDescription>
              How many alerts the monitor agent surfaced each day.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="label" stroke="currentColor" fontSize={11} />
                <YAxis stroke="currentColor" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="alerts"
                  stroke="#6366f1"
                  fill="url(#grad)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Task status</CardTitle>
            <CardDescription>Across all projects.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={taskStatusData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={45}
                  outerRadius={80}
                  paddingAngle={2}
                >
                  {taskStatusData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Workload + Priority */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Team workload</CardTitle>
            <CardDescription>
              Tasks per team member, broken down by status.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer>
              <BarChart data={workloadData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis type="number" stroke="currentColor" fontSize={11} />
                <YAxis
                  type="category"
                  dataKey="name"
                  stroke="currentColor"
                  fontSize={11}
                  width={90}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Todo" stackId="a" fill="#94a3b8" />
                <Bar dataKey="In progress" stackId="a" fill="#6366f1" />
                <Bar dataKey="Done" stackId="a" fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Priority mix</CardTitle>
            <CardDescription>Task urgency distribution.</CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={taskPriorityData}
                  dataKey="value"
                  nameKey="name"
                  outerRadius={80}
                  paddingAngle={2}
                >
                  {taskPriorityData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={
                        ["#ef4444", "#f59e0b", "#10b981"][i] ?? COLORS[i]
                      }
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Project + Assignee */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Project completion</CardTitle>
            <CardDescription>Done vs. remaining per project.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <BarChart data={projectData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="name" stroke="currentColor" fontSize={11} />
                <YAxis stroke="currentColor" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Done" stackId="a" fill="#10b981" />
                <Bar dataKey="Remaining" stackId="a" fill="#475569" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Alerts by assignee</CardTitle>
            <CardDescription>Pending vs. approved per person.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <BarChart data={assigneeData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="name" stroke="currentColor" fontSize={11} />
                <YAxis stroke="currentColor" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Pending" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Approved" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Resolution rate over time + activity feed */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Cumulative alerts</CardTitle>
            <CardDescription>
              Running total based on the 7-day trend.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer>
              <LineChart data={cumulative(trendData)}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="label" stroke="currentColor" fontSize={11} />
                <YAxis stroke="currentColor" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="cumulative"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Last 10 state transitions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {data.recent_activity.slice(0, 10).map((a) => (
              <div
                key={a.id}
                className="flex items-start justify-between gap-2 border-b border-border pb-2 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <div className="truncate text-xs">
                    <span className="font-mono text-muted-foreground">
                      #{a.alert_id}
                    </span>{" "}
                    <span className="text-muted-foreground">
                      {a.from_status ?? "—"} → {a.to_status}
                    </span>
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {a.actor}
                  </div>
                </div>
                <div className="whitespace-nowrap text-[10px] text-muted-foreground">
                  {formatDistanceToNow(new Date(a.created_at), {
                    addSuffix: true,
                  })}
                </div>
              </div>
            ))}
            {data.recent_activity.length === 0 && (
              <p className="text-xs text-muted-foreground">No activity yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function humanize(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function cumulative(rows: { label: string; alerts: number }[]) {
  let acc = 0;
  return rows.map((r) => {
    acc += r.alerts;
    return { label: r.label, cumulative: acc };
  });
}
