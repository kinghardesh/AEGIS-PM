"use client";

import * as React from "react";
import { formatDistanceToNow } from "date-fns";
import { Check, ExternalLink, X } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useAlerts,
  useApproveAlert,
  useDismissAlert,
} from "@/lib/hooks/use-alerts";

const FILTERS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "notified", label: "Notified" },
  { value: "dismissed", label: "Dismissed" },
];

export default function AlertsPage() {
  const [status, setStatus] = React.useState("");
  const { data, isLoading, isError, error } = useAlerts({
    limit: 100,
    status: status || undefined,
  });
  const approve = useApproveAlert();
  const dismiss = useDismissAlert();

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Stale tasks and risks the monitor agent has surfaced."
      />

      <div className="mb-4 flex gap-1 rounded-lg border border-border bg-card p-1 text-sm">
        {FILTERS.map((f) => (
          <button
            key={f.value || "all"}
            onClick={() => setStatus(f.value)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              status === f.value
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton />}
      {isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            {(error as Error).message}
          </CardContent>
        </Card>
      )}
      {data && data.items.length === 0 && (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">
            No alerts in this view.
          </CardContent>
        </Card>
      )}
      {data && data.items.length > 0 && (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3">Task</th>
                <th className="px-6 py-3">Assignee</th>
                <th className="px-6 py-3">Detected</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr
                  key={a.id}
                  className="border-b border-border last:border-0 hover:bg-muted/30"
                >
                  <td className="px-6 py-3">
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {a.task_key}
                    </div>
                    <div className="font-medium">{a.task_summary}</div>
                  </td>
                  <td className="px-6 py-3 text-muted-foreground">
                    {a.assignee ?? "—"}
                  </td>
                  <td className="px-6 py-3 text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(a.detected_at), {
                      addSuffix: true,
                    })}
                  </td>
                  <td className="px-6 py-3">
                    <StatusPill status={a.status} />
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      {a.status === "pending" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => approve.mutate(a.id)}
                            disabled={approve.isPending}
                            className="border-emerald-500/30 text-emerald-700 hover:bg-emerald-500/10 hover:text-emerald-700 dark:text-emerald-400"
                          >
                            <Check className="size-3.5" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => dismiss.mutate(a.id)}
                            disabled={dismiss.isPending}
                            className="border-destructive/30 text-destructive hover:bg-destructive/10"
                          >
                            <X className="size-3.5" />
                            Reject
                          </Button>
                        </>
                      )}
                      {a.jira_url && (
                        <a
                          href={a.jira_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          Jira <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t border-border px-6 py-3 text-xs text-muted-foreground">
            Showing {data.items.length} of {data.total}
          </div>
        </Card>
      )}
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending:
      "bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400",
    approved:
      "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
    notified: "bg-sky-500/10 text-sky-700 ring-sky-500/20 dark:text-sky-400",
    dismissed: "bg-muted text-muted-foreground ring-border",
  };
  const cls =
    styles[status] ?? "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {status}
    </span>
  );
}

function Skeleton() {
  return (
    <Card>
      <div className="divide-y divide-border">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-6 py-4">
            <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-4 w-20 animate-pulse rounded bg-muted" />
            <div className="ml-auto h-4 w-16 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </div>
    </Card>
  );
}
