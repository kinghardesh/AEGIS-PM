"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type ExecutorRunResponse } from "@/lib/api";

export function useExecutors() {
  return useQuery({
    queryKey: ["executors"],
    queryFn: api.executors.list,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRunExecutor() {
  return useMutation<
    ExecutorRunResponse,
    Error,
    { agent: string; summary: string; description?: string }
  >({
    mutationFn: api.executors.run,
    onError: (e) => toast.error(e.message),
  });
}
