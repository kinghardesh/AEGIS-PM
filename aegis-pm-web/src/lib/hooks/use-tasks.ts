"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { projectKeys } from "./use-projects";

export function useGenerateInstructions(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => api.tasks.generateInstructions(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.tasks(projectId) });
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
      qc.invalidateQueries({ queryKey: projectKeys.tasks(projectId) });
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
      qc.invalidateQueries({ queryKey: projectKeys.tasks(projectId) });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteTask(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => api.tasks.delete(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.tasks(projectId) });
      toast.success("Task deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
