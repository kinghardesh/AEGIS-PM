"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useEmployees() {
  return useQuery({ queryKey: ["employees"], queryFn: api.employees.list });
}
