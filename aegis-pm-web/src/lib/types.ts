// Hand-written types matching the FastAPI backend at api/main.py.
// When the backend changes, regenerate or update here.

export type Project = {
  id: number;
  name: string;
  description: string | null;
  prd_text: string | null;
  status: string;
  total_tasks: number;
  completed_tasks: number;
  created_at: string;
  updated_at: string;
  task_stats?: Record<string, number>;
  progress?: number;
};

export type Task = {
  id: number;
  project_id: number;
  title: string;
  description: string | null;
  priority: "high" | "medium" | "low" | string;
  status: "todo" | "in_progress" | "done" | "paused" | string;
  estimated_hours: number;
  assigned_to: number | null;
  assigned_name: string | null;
  ai_confidence: number | null;
  required_skills: string | null; // JSON string
  required_skills_list?: string[];
  created_at: string;
};

export type Employee = {
  id: number;
  name: string;
  email: string | null;
  role: string | null;
  skills: string; // JSON string
  skills_list?: string[];
  availability: "available" | "busy" | "on_leave" | string;
  current_load: number;
  created_at: string;
};

export type Alert = {
  id: number;
  task_key: string;
  task_summary: string | null;
  assignee: string | null;
  assignee_email: string | null;
  jira_url: string | null;
  last_updated: string;
  detected_at: string;
  status: "pending" | "approved" | "dismissed" | "notified" | string;
  slack_sent: boolean;
  slack_ts: string | null;
  notes: string | null;
};

export type PaginatedAlerts = {
  items: Alert[];
  total: number;
  limit: number;
  offset: number;
};

export type CreateProjectInput = {
  name: string;
  description?: string;
  prd_text?: string;
};

export type UpdateProjectInput = Partial<CreateProjectInput> & {
  status?: string;
};

export type CreateEmployeeInput = {
  name: string;
  email?: string;
  role?: string;
  skills?: string[];
  availability?: string;
};
