"use client";

import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { projectKeys } from "./use-projects";

function invalidateTaskDerived(qc: QueryClient, projectId?: number) {
  if (projectId !== undefined) {
    qc.invalidateQueries({ queryKey: projectKeys.tasks(projectId) });
    qc.invalidateQueries({ queryKey: projectKeys.detail(projectId) });
  }
  qc.invalidateQueries({ queryKey: projectKeys.all });
  qc.invalidateQueries({ queryKey: ["analytics"] });
  qc.invalidateQueries({ queryKey: ["admin", "dashboard"] });
  qc.invalidateQueries({ queryKey: ["me", "tasks"] });
  qc.invalidateQueries({ queryKey: ["me", "projects"] });
  qc.invalidateQueries({ queryKey: ["employee", "tasks"] });
}

export const invalidateAllTaskDerived = invalidateTaskDerived;

export function useGenerateInstructions(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => api.tasks.generateInstructions(taskId),
    onSuccess: () => {
      invalidateTaskDerived(qc, projectId);
      toast.success("Instructions generated");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useAssignTask(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      employeeId,
      employeeName,
    }: {
      taskId: number;
      employeeId: number;
      employeeName: string;
    }) => api.tasks.assign(taskId, employeeId, employeeName),
    onSuccess: (data) => {
      invalidateTaskDerived(qc, projectId);
      const emailNote =
        "email_sent" in data && data.email_sent
          ? " · email sent"
          : "";
      toast.success(`Task assigned${emailNote}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useSetTaskStatus(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, status }: { taskId: number; status: string }) =>
      api.tasks.setStatus(taskId, status),
    onSuccess: () => {
      invalidateTaskDerived(qc, projectId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteTask(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => api.tasks.delete(taskId),
    onSuccess: () => {
      invalidateTaskDerived(qc, projectId);
      toast.success("Task deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useSetTaskAgentType(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      agent_type,
    }: {
      taskId: number;
      agent_type: string;
    }) => api.tasks.setAgentType(taskId, agent_type),
    onSuccess: () => {
      invalidateTaskDerived(qc, projectId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useExecuteTask(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => api.tasks.execute(taskId),
    onSuccess: () => {
      invalidateTaskDerived(qc, projectId);
      toast.success("Task executed");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
