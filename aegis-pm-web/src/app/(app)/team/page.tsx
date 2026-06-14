"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AgentCard, type Agent } from "@/components/team/agent-card";
import { TaskDrawer } from "@/components/team/task-drawer";
import { api } from "@/lib/api";
import { useAddAiAgents, useEmployees } from "@/lib/hooks/use-employees";

/**
 * Team page — agent/employee directory with clickable workload bars.
 *
 * Data sources (both admin-only):
 *   /employees                     → skills, availability, email
 *   /admin/employee-monitoring     → real task counts + status segments
 * Merged client-side by employee_id so the user sees one card per person.
 *
 * Clicking a card (or its workload bar) opens a right-side drawer that
 * lazily fetches /admin/employees/{id}/tasks and renders the full list.
 */
export default function TeamPage() {
  const employees = useEmployees();
  const addAi     = useAddAiAgents();

  const monitoring = useQuery({
    queryKey: ["admin", "employee-monitoring"],
    queryFn: () => api.admin.employeeMonitoring(),
    refetchInterval: 20_000,
  });

  // Build the Agent[] array fed into the card grid.
  const agents: Agent[] = React.useMemo(() => {
    type MonitoringRow = NonNullable<typeof monitoring.data>[number];
    const byId = new Map<number, MonitoringRow>();
    (monitoring.data ?? []).forEach((m) => byId.set(m.employee_id, m));

    return (employees.data ?? []).map((e) => {
      const m = byId.get(e.id);
      return {
        id:   e.id,
        name: e.name,
        role: e.role ?? null,
        email: e.email ?? null,
        availability: e.availability,
        skills: e.skills_list ?? safeParseSkills(e.skills),
        department: e.department ?? null,
        is_manager: Boolean(e.is_manager),
        total: m?.total ?? e.current_load ?? 0,
        segments: {
          todo:        m?.todo ?? 0,
          in_progress: m?.in_progress ?? 0,
          done:        m?.done ?? 0,
          paused:      m?.paused ?? 0,
        },
      };
    });
  }, [employees.data, monitoring.data]);

  // Department filter. "all" shows everyone; otherwise narrow to one dept.
  const [deptFilter, setDeptFilter] = React.useState<string>("all");
  const departments = React.useMemo(() => {
    const set = new Set<string>();
    agents.forEach((a) => a.department && set.add(a.department));
    return Array.from(set).sort();
  }, [agents]);
  const visibleAgents = React.useMemo(
    () =>
      deptFilter === "all"
        ? agents
        : agents.filter((a) => (a.department ?? "") === deptFilter),
    [agents, deptFilter]
  );

  // Selected card id. Only one card can be "active" at a time — the drawer
  // always shows exactly the selection, if any.
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const selectedAgent = agents.find((a) => a.id === selectedId) ?? null;

  return (
    <>
      <PageHeader
        title="Team"
        description="The people — and AI agents — Aegis can assign work to. Click a card to see their tasks."
        actions={
          <Button
            onClick={() => addAi.mutate()}
            disabled={addAi.isPending}
            className="gap-1.5"
          >
            <Sparkles className="size-4" />
            {addAi.isPending ? "Adding…" : "Add AI agents"}
          </Button>
        }
      />

      {employees.isLoading && <Skeleton />}
      {employees.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            {(employees.error as Error).message}
          </CardContent>
        </Card>
      )}

      {employees.data && employees.data.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Bot className="size-8 text-muted-foreground" />
            <p className="text-sm font-medium">No team members yet</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Click <span className="font-medium">Add AI agents</span> to
              onboard the six executor agents in one click.
            </p>
          </CardContent>
        </Card>
      )}

      {agents.length > 0 && departments.length > 0 && (
        <div className="mb-4 flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">
            Department
          </label>
          <select
            value={deptFilter}
            onChange={(e) => setDeptFilter(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="all">All departments</option>
            {departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">
            {visibleAgents.length} of {agents.length}
          </span>
        </div>
      )}

      {agents.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleAgents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              active={selectedId === agent.id}
              onOpen={() => setSelectedId(agent.id)}
            />
          ))}
        </div>
      )}

      <TaskDrawer
        agent={
          selectedAgent
            ? {
                id:    selectedAgent.id,
                name:  selectedAgent.name,
                role:  selectedAgent.role,
                email: selectedAgent.email,
              }
            : null
        }
        onClose={() => setSelectedId(null)}
      />
    </>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function safeParseSkills(s: string | undefined): string[] {
  if (!s) return [];
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="space-y-3 p-5">
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
            <div className="h-1 w-full animate-pulse rounded bg-muted" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
