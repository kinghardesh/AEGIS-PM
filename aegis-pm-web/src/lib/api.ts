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

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t =
    window.sessionStorage.getItem("aegis.token") ||
    window.localStorage.getItem("aegis.token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
    ...init,
  });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    // On expired/invalid token, bounce back to login.
    if (res.status === 401 && typeof window !== "undefined") {
      window.sessionStorage.removeItem("aegis.token");
      window.sessionStorage.removeItem("aegis.user");
      window.localStorage.removeItem("aegis.token");
      window.localStorage.removeItem("aegis.user");
      document.cookie = "aegis_token=; path=/; max-age=0";
      document.cookie = "aegis_role=; path=/; max-age=0";
      if (!window.location.pathname.endsWith("/login")) {
        window.location.href = "/login";
      }
    }
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
    /**
     * Auto-assign via the balancer — picks the best-fit person (human
     * OR AI) for each unassigned task, preferring humans when skills
     * are comparable. Updates load between iterations so a batch can't
     * dog-pile one member.
     */
    autoAssignAll: (id: number) =>
      request<{
        assigned: number;
        new: number;
        reassigned: number;
        unchanged: number;
        results: Array<{
          task_id: number;
          task_title: string;
          member_id: number;
          member_name: string;
          member_type: "AI" | "HUMAN";
          score: number;
          outcome: "new" | "reassigned" | "unchanged";
        }>;
      }>(`/admin/projects/${id}/balance-assign-all`, { method: "POST" }),
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
    setAgentType: (id: number, agent_type: string) =>
      request<Task>(`/tasks/${id}/agent-type`, {
        method: "PUT",
        body: JSON.stringify({ agent_type }),
      }),
    execute: (id: number) =>
      request<{
        task_id: number;
        agent_type: string;
        deliverable: string;
        duration_ms: number;
        status: string;
      }>(`/tasks/${id}/execute`, { method: "POST" }),
    executorOutput: (id: number) =>
      request<{
        task_id: number;
        agent_type: string | null;
        executor_status: string | null;
        executor_output: string | null;
        executor_error: string | null;
        executor_run_at: string | null;
      }>(`/tasks/${id}/executor-output`),
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
    addAiAgents: () =>
      request<{ added: number; skipped: number; agents: Employee[] }>(
        "/team/add-ai-agents",
        { method: "POST" }
      ),
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
    complete: (id: number, notes?: string) =>
      request<unknown>(`/alerts/${id}/complete`, {
        method: "POST",
        body: JSON.stringify({ notes }),
      }),
    assign: (id: number, user_id: number) =>
      request<unknown>(`/alerts/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ user_id }),
      }),
    list: (params: { limit?: number; offset?: number; status?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      if (params.status) qs.set("status", params.status);
      const q = qs.toString();
      return request<PaginatedAlerts>(`/alerts${q ? `?${q}` : ""}`);
    },
    mine: (status?: string) => {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      return request<import("./types").Alert[]>(`/me/alerts${qs}`);
    },
    myTasks: (status?: string) => {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      return request<import("./types").Task[]>(`/me/tasks${qs}`);
    },
    myProjects: () =>
      request<
        Array<
          import("./types").Project & { my_total: number; my_done: number }
        >
      >("/me/projects"),
    stats: () =>
      request<{
        pending: number;
        approved: number;
        notified: number;
        dismissed: number;
        total: number;
      }>("/stats"),
  },

  // ── Auth (unauthenticated endpoints) ──────────────────────────────
  auth: {
    register: (input: { name: string; email: string; password: string }) =>
      request<import("./auth").AuthUser>("/auth/register", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    forgotPassword: (input: { user_id?: string; email?: string }) =>
      request<{ ok: boolean }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    resetPassword: (token: string, new_password: string) =>
      request<{ ok: boolean }>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password }),
      }),
  },

  // ── Notifications ─────────────────────────────────────────────────
  notifications: {
    list: (unread = false) =>
      request<import("./hooks/use-notifications").Notification[]>(
        `/notifications${unread ? "?unread=true" : ""}`
      ),
    unreadCount: () => request<{ count: number }>("/notifications/unread-count"),
    markRead: (id: number) =>
      request<unknown>(`/notifications/${id}/read`, { method: "POST" }),
    markAllRead: () =>
      request<{ ok: boolean; marked: number }>(`/notifications/read-all`, {
        method: "POST",
      }),
  },

  // ── Admin ─────────────────────────────────────────────────────────
  admin: {
    dashboard: () =>
      request<{
        system: { status: string; database: string; active_sessions: number };
        tasks_by_status: Record<string, number>;
        recent_completions: Array<{
          alert_id: number;
          task_key: string;
          task_summary: string | null;
          completed_at: string;
          completed_by: string | null;
          completed_by_role: string | null;
        }>;
        completions_by_user_30d: Array<{
          user: string;
          role: string;
          completed: number;
        }>;
      }>("/admin/dashboard"),
    activity: (params: { user_id?: number; action?: string; since_hours?: number; limit?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.user_id) qs.set("user_id", String(params.user_id));
      if (params.action) qs.set("action", params.action);
      if (params.since_hours) qs.set("since_hours", String(params.since_hours));
      if (params.limit) qs.set("limit", String(params.limit));
      return request<Array<{
        id: number;
        user_id: number | null;
        user_handle: string | null;
        action: string;
        method: string | null;
        path: string | null;
        status_code: number | null;
        ip_address: string | null;
        created_at: string;
      }>>(`/activity${qs.toString() ? `?${qs}` : ""}`);
    },
    sessions: () =>
      request<Array<{
        id: number;
        user_id: number;
        user_handle: string;
        role: string;
        device: string | null;
        ip_address: string | null;
        last_seen_at: string;
        expires_at: string;
      }>>("/activity/sessions"),
    revokeSession: (id: number) =>
      request<unknown>(`/activity/sessions/${id}/revoke`, { method: "POST" }),
    users: () =>
      request<Array<import("./auth").AuthUser>>("/auth/users"),

    // ── Balancer (AI vs HUMAN even-distribution) ─────────────────
    unassignedTasks: () =>
      request<
        Array<{
          task_id: number;
          title: string;
          priority: "high" | "medium" | "low" | string;
          required_skills: string[];
          project_id: number;
          recommended: null | {
            member_id: number;
            member_name: string;
            member_type: "AI" | "HUMAN";
            score: number;
            reason: string;
          };
        }>
      >("/admin/tasks/unassigned"),
    balanceAssign: (
      task_id: number,
      body: { confirm?: boolean; priority_override?: string } = {}
    ) =>
      request<{
        task_id: number;
        priority: string;
        ai_share: number;
        human_share: number;
        recommendations: Array<{
          member_id: number;
          member_name: string;
          member_type: "AI" | "HUMAN";
          score: number;
          skill_match: number;
          workload_score: number;
          balance_score: number;
          priority_score: number;
          reason: string;
          current_load: number;
        }>;
        assigned: null | { employee_id: number; name: string; type: string; score: number };
      }>(`/admin/tasks/${task_id}/balance-assign`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    createEmployee: (input: {
      name: string;
      email?: string;
      role_title?: string;
      skills?: string[];
    }) =>
      request<{
        user: import("./auth").AuthUser;
        employee_id: number;
        generated_user_id: string;
        generated_password: string;
      }>("/admin/create-employee", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    employeeMonitoring: () =>
      request<
        Array<{
          employee_id: number;
          employee_name: string;
          employee_email: string | null;
          user_id: string | null;
          role: string | null;
          last_login_at: string | null;
          total: number;
          todo: number;
          in_progress: number;
          done: number;
          paused: number;
          last_activity_at: string | null;
          avg_progress: number;
        }>
      >("/admin/employee-monitoring"),
    employeeTasks: (employee_id: number) =>
      request<import("./types").Task[]>(`/admin/employees/${employee_id}/tasks`),

    // ── Bulk upload & staging ────────────────────────────────────────
    uploadEmployees: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      // Upload uses multipart; `request` forces JSON content-type, so
      // go direct to fetch here and still reuse the auth header.
      const token = typeof window !== "undefined"
        ? (window.sessionStorage.getItem("aegis.token") || window.localStorage.getItem("aegis.token"))
        : null;
      const BASE =
        process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
      const res = await fetch(`${BASE}/admin/upload-employees`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail =
          (body && typeof body === "object" && "detail" in body
            ? String((body as { detail: unknown }).detail)
            : res.statusText) || "Upload failed";
        throw new Error(detail);
      }
      return body as {
        batch_id: string;
        rows_parsed: number;
        rows_staged: number;
        duplicates_skipped: number;
        errors: string[];
      };
    },
    listStaging: (params: { batch_id?: string; status?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.batch_id) qs.set("batch_id", params.batch_id);
      if (params.status) qs.set("status", params.status);
      return request<
        Array<{
          id: number;
          name: string;
          email: string | null;
          skills: string[];
          experience: number | null;
          department: string | null;
          is_manager: boolean;
          upload_batch_id: string;
          status: string;
          created_at: string;
        }>
      >(`/admin/staging${qs.toString() ? `?${qs}` : ""}`);
    },
    recommendedEmployees: (args: {
      skills: string;
      priority?: string;
      batch_id?: string;
      min_experience?: number;
      min_score?: number;
    }) => {
      const qs = new URLSearchParams({ skills: args.skills });
      if (args.priority) qs.set("priority", args.priority);
      if (args.batch_id) qs.set("batch_id", args.batch_id);
      if (args.min_experience && args.min_experience > 0)
        qs.set("min_experience", String(args.min_experience));
      if (args.min_score && args.min_score > 0)
        qs.set("min_score", String(args.min_score));
      return request<
        Array<{
          staging_id: number;
          name: string;
          email: string | null;
          skills: string[];
          experience: number | null;
          department: string | null;
          is_manager: boolean;
          score: number;
          skill_score: number;
          experience_score: number;
          priority_bonus: number;
          confidence: number;
          matched_skills: string[];
          missing_skills: string[];
          reason: string;
          semantic: boolean;
        }>
      >(`/admin/recommended-employees?${qs}`);
    },
    analyzeEmployees: (body: {
      required: string[];
      priority?: string[];
      min_experience?: number;
      batch_id?: string;
    }) =>
      request<{
        requirement_hash: string;
        analyzed: number;
        top: Array<{
          staging_id: number;
          name: string;
          email: string | null;
          experience: number | null;
          score: number;
          skill_score: number;
          experience_score: number;
          priority_bonus: number;
          confidence: number;
          matched_skills: string[];
          missing_skills: string[];
          reason: string;
          semantic: boolean;
          analyzed_at: string;
        }>;
      }>("/admin/analyze-employees", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // ── PRD pipeline ───────────────────────────────────────────────
    uploadPrd: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const token = typeof window !== "undefined"
        ? (window.sessionStorage.getItem("aegis.token") || window.localStorage.getItem("aegis.token"))
        : null;
      const BASE =
        process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
      const res = await fetch(`${BASE}/admin/upload-prd`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail =
          (body && typeof body === "object" && "detail" in body
            ? String((body as { detail: unknown }).detail)
            : res.statusText) || "Upload failed";
        throw new Error(detail);
      }
      return body as {
        prd: {
          id: number;
          filename: string;
          created_at: string;
          latest_extraction: null | {
            skills: string[];
            priority_skills: string[];
            task_description: string;
            method: string;
            model: string | null;
            extracted_at: string;
          };
        };
        extraction: {
          skills: string[];
          priority_skills: string[];
          task_description: string;
          method: string;
          model: string | null;
          extracted_at: string;
        };
      };
    },
    uploadPrdAndCreateProject: async (file: File, project_name?: string) => {
      const form = new FormData();
      form.append("file", file);
      const token = typeof window !== "undefined"
        ? (window.sessionStorage.getItem("aegis.token") || window.localStorage.getItem("aegis.token"))
        : null;
      const BASE =
        process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
      const qs = project_name ? `?project_name=${encodeURIComponent(project_name)}` : "";
      const res = await fetch(`${BASE}/admin/upload-prd-and-create-project${qs}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail =
          (body && typeof body === "object" && "detail" in body
            ? String((body as { detail: unknown }).detail)
            : res.statusText) || "Upload failed";
        throw new Error(detail);
      }
      return body as {
        project_id: number;
        prd_id: number;
        project_name: string;
        skills: string[];
        priority: string[];
        method: string;
        model: string | null;
        tasks: Array<{
          id: number;
          title: string;
          priority: string;
          estimated_hours: number;
          required_skills: string[];
        }>;
      };
    },
    parsePrd: (prd_id: number) =>
      request<{
        skills: string[];
        priority_skills: string[];
        task_description: string;
        method: string;
        model: string | null;
        extracted_at: string;
      }>(`/admin/parse-prd/${prd_id}`, { method: "POST" }),
    listPrds: () =>
      request<
        Array<{
          id: number;
          filename: string;
          created_at: string;
          latest_extraction: null | {
            skills: string[];
            priority_skills: string[];
          };
        }>
      >("/admin/prds"),
    analyzeCandidates: (body: {
      prd_id: number;
      batch_id?: string;
      min_experience?: number;
    }) =>
      request<{
        requirement_hash: string;
        analyzed: number;
        top: Array<{
          staging_id: number;
          name: string;
          email: string | null;
          experience: number | null;
          score: number;
          skill_score: number;
          experience_score: number;
          priority_bonus: number;
          confidence: number;
          matched_skills: string[];
          missing_skills: string[];
          reason: string;
          semantic: boolean;
        }>;
      }>("/admin/analyze-candidates", {
        method: "POST",
        body: JSON.stringify(body),
      }),

    employeeScores: (params: {
      requirement_hash?: string;
      batch_id?: string;
      min_score?: number;
      limit?: number;
    } = {}) => {
      const qs = new URLSearchParams();
      if (params.requirement_hash) qs.set("requirement_hash", params.requirement_hash);
      if (params.batch_id) qs.set("batch_id", params.batch_id);
      if (params.min_score) qs.set("min_score", String(params.min_score));
      if (params.limit) qs.set("limit", String(params.limit));
      return request<
        Array<{
          staging_id: number;
          name: string;
          email: string | null;
          experience: number | null;
          score: number;
          skill_score: number;
          experience_score: number;
          priority_bonus: number;
          confidence: number;
          matched_skills: string[];
          missing_skills: string[];
          reason: string;
          semantic: boolean;
          analyzed_at: string;
        }>
      >(`/admin/employee-scores${qs.toString() ? `?${qs}` : ""}`);
    },
    createSelectedEmployees: (staging_ids: number[]) =>
      request<{
        batch_id: string;
        created: Array<{
          name: string;
          email: string | null;
          user_id: string;
          password: string;
          employee_id: number;
        }>;
        skipped: Array<{ staging_id: number; reason: string }>;
      }>("/admin/create-selected-employees", {
        method: "POST",
        body: JSON.stringify({ staging_ids }),
      }),
    credentialsExportUrl: (batch_id: string) => {
      const BASE =
        process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";
      return `${BASE}/admin/credentials-export?batch_id=${encodeURIComponent(batch_id)}`;
    },
    assignTaskAi: (body: {
      task_id: number;
      confirm?: boolean;
      required?: string[];
      candidates?: number[];
    }) =>
      request<{
        task_id: number;
        required: string[];
        recommendations: Array<{
          employee_id: number;
          name: string;
          skills: string[];
          score: number;
          matched: string[];
          missing: string[];
        }>;
        assigned: { employee_id: number; name: string; score: number } | null;
      }>("/admin/assign-task-ai", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  // ── Employee workflow ─────────────────────────────────────────────
  employee: {
    tasks: () => request<import("./types").Task[]>("/employee/tasks"),
    updateProgress: (
      task_id: number,
      body: { progress_pct: number; status?: string; note?: string }
    ) =>
      request<import("./types").Task>(
        `/employee/update-progress/${task_id}`,
        {
          method: "POST",
          body: JSON.stringify(body),
        }
      ),

    // ── Day-by-day plan ─────────────────────────────────────────────
    generateDays: (task_id: number, days?: number) => {
      const qs = days ? `?days=${days}` : "";
      return request<{
        task_id: number;
        total_days: number;
        method: "llm" | "keyword";
        model: string | null;
        entries: Array<{
          id: number;
          task_id: number;
          day_number: number;
          planned_description: string | null;
          actual_note: string | null;
          completed_at: string | null;
          created_at: string;
        }>;
      }>(`/employee/tasks/${task_id}/generate-days${qs}`, { method: "POST" });
    },
    listDays: (task_id: number) =>
      request<{
        task_id: number;
        total_days: number;
        completed: number;
        progress_pct: number;
        entries: Array<{
          id: number;
          task_id: number;
          day_number: number;
          planned_description: string | null;
          actual_note: string | null;
          completed_at: string | null;
          created_at: string;
        }>;
      }>(`/employee/tasks/${task_id}/days`),
    checkInDay: (
      task_id: number,
      day_number: number,
      body: { note?: string; completed?: boolean }
    ) =>
      request<{
        task_id: number;
        day_number: number;
        completed: boolean;
        total_days: number;
        completed_days: number;
        progress_pct: number;
      }>(`/employee/tasks/${task_id}/days/${day_number}/check-in`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  // ── Health ────────────────────────────────────────────────────────
  health: () =>
    request<{ status: string; service: string; database: string }>("/health"),

  // ── Analytics aggregate ───────────────────────────────────────────
  analytics: () => request<AnalyticsResponse>("/analytics"),

  // ── Executor agents (ad-hoc runs) ─────────────────────────────────
  executors: {
    list: () => request<ExecutorInfo[]>("/executors"),
    run: (input: { agent: string; summary: string; description?: string }) =>
      request<ExecutorRunResponse>("/executors/run", {
        method: "POST",
        body: JSON.stringify({
          agent: input.agent,
          summary: input.summary,
          description: input.description ?? "",
        }),
      }),
  },
};

export type ExecutorInfo = {
  name: string;
  label: string;
  header: string;
};

export type ExecutorRunResponse = {
  agent: string;
  summary: string;
  deliverable: string;
  duration_ms: number;
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
