"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { FileText, Sparkles, Users } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/**
 * Employee monitoring (admin-only).
 *
 * Manual employee creation was removed per the PRD pipeline mandate:
 * employees are provisioned exclusively from the AI-ranked staging flow.
 * This page is now monitoring-only; the call-to-action links to
 * /admin/staging where the upload → rank → select → credentials flow
 * lives.
 */
export default function AdminEmployeesPage() {
  const monitoring = useQuery({
    queryKey: ["admin", "employee-monitoring"],
    queryFn: () => api.admin.employeeMonitoring(),
    refetchInterval: 20_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Employees</h1>
        <p className="text-sm text-muted-foreground">
          Monitor task progress for everyone the AI pipeline has onboarded.
        </p>
      </div>

      {/* ── Callout: where provisioning happens now ─────────────── */}
      <Card className="border-primary/40 bg-primary/[0.03]">
        <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary">
              <Sparkles className="size-4" />
            </div>
            <div>
              <div className="text-sm font-semibold">
                Employees are now provisioned via the PRD pipeline
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Upload a PRD + a candidate dataset, let the AI rank them, then
                approve the ones you want. Credentials are generated only for
                selected candidates.
              </p>
            </div>
          </div>
          <Link href="/admin/staging" className="shrink-0">
            <Button variant="outline" className="gap-1.5">
              <FileText className="size-4" /> Go to PRD pipeline
            </Button>
          </Link>
        </CardContent>
      </Card>

      {/* ── Monitoring ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="size-4" /> Monitoring
          </CardTitle>
          <CardDescription>
            All employees · task counts by status · last activity. Auto-refreshes
            every 20 seconds.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {monitoring.isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-2 text-left font-medium">Employee</th>
                  <th className="py-2 text-left font-medium">Login</th>
                  <th className="py-2 text-right font-medium">Tasks</th>
                  <th className="py-2 text-right font-medium">In-prog</th>
                  <th className="py-2 text-right font-medium">Done</th>
                  <th className="py-2 text-right font-medium">Avg %</th>
                  <th className="py-2 text-left font-medium">Last activity</th>
                </tr>
              </thead>
              <tbody>
                {monitoring.data?.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="py-8 text-center text-xs text-muted-foreground"
                    >
                      No employees yet — run the{" "}
                      <Link href="/admin/staging" className="text-primary hover:underline">
                        PRD pipeline
                      </Link>{" "}
                      to onboard candidates.
                    </td>
                  </tr>
                )}
                {monitoring.data?.map((r) => (
                  <tr key={r.employee_id} className="border-b border-border/40">
                    <td className="py-1.5">
                      <div className="font-medium">{r.employee_name}</div>
                      {r.employee_email && (
                        <div className="text-[11px] text-muted-foreground">
                          {r.employee_email}
                        </div>
                      )}
                    </td>
                    <td className="py-1.5">
                      {r.user_id ? (
                        <>
                          <span className="font-mono text-xs">{r.user_id}</span>
                          {r.role && (
                            <span className="ml-1 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                              {r.role}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right font-mono text-xs">{r.total}</td>
                    <td className="py-1.5 text-right font-mono text-xs">{r.in_progress}</td>
                    <td className="py-1.5 text-right font-mono text-xs">{r.done}</td>
                    <td className="py-1.5 text-right font-mono text-xs">{r.avg_progress}</td>
                    <td className="py-1.5 text-xs text-muted-foreground">
                      {r.last_activity_at
                        ? formatDistanceToNow(new Date(r.last_activity_at), { addSuffix: true })
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
