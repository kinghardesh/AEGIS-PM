// Typed fetch client for the Aegis PM FastAPI backend.

import type {
  Project,
  Task,
  Employee,
  PaginatedAlerts,
  CreateProjectInput,
  UpdateProjectInput,
  CreateEmployeeInput,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
    ...init,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText) || "Request failed";
    throw new ApiError(res.status, detail, body);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  // ── Projects ──────────────────────────────────────────────────────
  projects: {
    list: () => request<Project[]>("/projects"),
    get: (id: number) => request<Project>(`/projects/${id}`),
    create: (input: CreateProjectInput) =>
      request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: number, input: UpdateProjectInput) =>
      request<Project>(`/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    delete: (id: number) =>
      request<{ deleted: boolean; project_id: number }>(`/projects/${id}`, {
        method: "DELETE",
      }),
    parsePrd: (id: number) =>
      request<{ project_id: number; tasks_created: number; tasks: Task[] }>(
        `/projects/${id}/parse`,
        { method: "POST" }
      ),
    assignAll: (id: number) =>
      request<{
        project_id: number;
        total_assigned: number;
        emails_sent?: number;
        assignments: unknown[];
      }>(`/projects/${id}/assign-all`, { method: "POST" }),
    unassignAll: (id: number) =>
      request<{ project_id: number; unassigned: number }>(
        `/projects/${id}/unassign-all`,
        { method: "POST" }
      ),
    listTasks: (id: number) =>
      request<Task[] | { tasks: Task[] }>(`/projects/${id}/tasks`),
  },

  // ── Tasks ─────────────────────────────────────────────────────────
  tasks: {
    setStatus: (id: number, status: string) =>
      request<Task>(`/tasks/${id}/status`, {
        method: "PUT",
        body: JSON.stringify({ status }),
      }),
    assign: (id: number, employee_id: number, employee_name: string) =>
      request<Task & { email_sent?: boolean }>(`/tasks/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ employee_id, employee_name }),
      }),
    pause: (id: number) =>
      request<Task>(`/tasks/${id}/pause`, { method: "POST" }),
    resume: (id: number) =>
      request<Task>(`/tasks/${id}/resume`, { method: "POST" }),
    delete: (id: number) =>
      request<{ deleted: boolean }>(`/tasks/${id}`, { method: "DELETE" }),
    generateInstructions: (id: number) =>
      request<{ task_id: number; description: string }>(
        `/tasks/${id}/generate-instructions`,
        { method: "POST" }
      ),
  },

  // ── Employees ─────────────────────────────────────────────────────
  employees: {
    list: () => request<Employee[]>("/employees"),
    create: (input: CreateEmployeeInput) =>
      request<Employee>("/employees", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<CreateEmployeeInput>) =>
      request<Employee>(`/employees/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    delete: (id: number) =>
      request<unknown>(`/employees/${id}`, { method: "DELETE" }),
  },

  // ── Alerts ────────────────────────────────────────────────────────
  alerts: {
    approve: (id: number) =>
      request<unknown>(`/alerts/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    dismiss: (id: number) =>
      request<unknown>(`/alerts/${id}/dismiss`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    list: (params: { limit?: number; offset?: number; status?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      if (params.status) qs.set("status", params.status);
      const q = qs.toString();
      return request<PaginatedAlerts>(`/alerts${q ? `?${q}` : ""}`);
    },
    stats: () =>
      request<{
        pending: number;
        approved: number;
        notified: number;
        dismissed: number;
        total: number;
      }>("/stats"),
  },

  // ── Health ────────────────────────────────────────────────────────
  health: () =>
    request<{ status: string; service: string; database: string }>("/health"),

  // ── Analytics aggregate ───────────────────────────────────────────
  analytics: () => request<AnalyticsResponse>("/analytics"),
};

export type AnalyticsResponse = {
  status_distribution: Record<string, number>;
  assignee_breakdown: Array<{
    assignee: string;
    total: number;
    pending: number;
    approved: number;
    dismissed: number;
    notified: number;
  }>;
  daily_trend: Array<{ date: string; label: string; count: number }>;
  recent_activity: Array<{
    id: number;
    alert_id: number;
    from_status: string | null;
    to_status: string;
    actor: string;
    notes: string | null;
    created_at: string;
  }>;
  metrics: {
    total_alerts: number;
    total_resolved: number;
    resolution_rate: number;
    pending: number;
    total_projects: number;
    active_projects: number;
    total_tasks: number;
    tasks_done: number;
    tasks_in_progress: number;
    tasks_todo: number;
    assigned_tasks: number;
    task_completion_rate: number;
    total_employees: number;
    available_employees: number;
  };
  task_status_dist: Record<string, number>;
  task_priority_dist: Record<string, number>;
  employee_workload: Array<{
    name: string;
    role: string;
    total_tasks: number;
    done: number;
    in_progress: number;
    todo: number;
    availability: string;
  }>;
  projects_summary: Array<{
    name: string;
    status: string;
    total_tasks: number;
    completed_tasks: number;
    completion_pct: number;
  }>;
};

export { ApiError };
