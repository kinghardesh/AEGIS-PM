"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type {
  CreateProjectInput,
  UpdateProjectInput,
} from "@/lib/types";

const KEYS = {
  all: ["projects"] as const,
  detail: (id: number) => ["projects", id] as const,
  tasks: (id: number) => ["projects", id, "tasks"] as const,
};

export function useProjects() {
  return useQuery({ queryKey: KEYS.all, queryFn: api.projects.list });
}

export function useProject(id: number) {
  return useQuery({
    queryKey: KEYS.detail(id),
    queryFn: () => api.projects.get(id),
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useProjectTasks(id: number) {
  return useQuery({
    queryKey: KEYS.tasks(id),
    queryFn: async () => {
      const res = await api.projects.listTasks(id);
      return Array.isArray(res) ? res : res.tasks;
    },
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProjectInput) => api.projects.create(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success("Project created");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: UpdateProjectInput }) =>
      api.projects.update(id, input),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: KEYS.detail(id) });
      toast.success("Project updated");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.projects.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success("Project deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useParsePrd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.projects.parsePrd(id),
    onSuccess: (data, id) => {
      qc.invalidateQueries({ queryKey: KEYS.tasks(id) });
      qc.invalidateQueries({ queryKey: KEYS.detail(id) });
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success(`Generated ${data.tasks_created} tasks`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useAssignAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.projects.assignAll(id),
    onSuccess: (data, id) => {
      qc.invalidateQueries({ queryKey: KEYS.tasks(id) });
      const emails = data.emails_sent ? ` · ${data.emails_sent} emails sent` : "";
      toast.success(`Assigned ${data.total_assigned} tasks${emails}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUnassignAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.projects.unassignAll(id),
    onSuccess: (data, id) => {
      qc.invalidateQueries({ queryKey: KEYS.tasks(id) });
      toast.success(`Cleared ${data.unassigned} assignments`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export const projectKeys = KEYS;
