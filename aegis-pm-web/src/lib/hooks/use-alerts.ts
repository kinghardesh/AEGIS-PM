"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";

export function useAlerts(params: { limit?: number; status?: string } = {}) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => api.alerts.list(params),
  });
}

export function useAlertStats() {
  return useQuery({ queryKey: ["alert-stats"], queryFn: api.alerts.stats });
}

export function useApproveAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.alerts.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-stats"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Approved · task moved to in progress");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDismissAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.alerts.dismiss(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-stats"] });
      toast.success("Alert dismissed");
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
