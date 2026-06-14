"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";

export function useEmployees() {
  return useQuery({ queryKey: ["employees"], queryFn: api.employees.list });
}

export function useAddAiAgents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.employees.addAiAgents,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["employees"] });
      if (data.added > 0) {
        toast.success(
          `${data.added} AI agent${data.added === 1 ? "" : "s"} added to the team`
        );
      } else {
        toast.info("All 6 AI agents are already on the team");
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
