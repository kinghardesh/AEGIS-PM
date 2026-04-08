"use client";

import { Mail } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useEmployees } from "@/lib/hooks/use-employees";

export default function TeamPage() {
  const { data, isLoading, isError, error } = useEmployees();

  return (
    <>
      <PageHeader
        title="Team"
        description="The people Aegis can assign work to."
      />

      {isLoading && <Skeleton />}
      {isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            {(error as Error).message}
          </CardContent>
        </Card>
      )}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">
            No team members yet.
          </CardContent>
        </Card>
      )}
      {data && data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((e) => {
            const skills = e.skills_list ?? safeParse(e.skills);
            const loadPct = Math.min(100, e.current_load * 15);
            return (
              <Card key={e.id}>
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-start gap-3">
                    <div className="grid size-10 place-items-center rounded-full bg-secondary text-sm font-semibold">
                      {initials(e.name)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{e.name}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {e.role ?? "—"}
                      </div>
                    </div>
                    <AvailabilityPill availability={e.availability} />
                  </div>

                  {e.email && (
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Mail className="size-3" />
                      <span className="truncate">{e.email}</span>
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                      <span>Workload</span>
                      <span>{e.current_load} tasks</span>
                    </div>
                    <div className="h-1 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${loadPct}%` }}
                      />
                    </div>
                  </div>

                  {skills.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {skills.slice(0, 6).map((s) => (
                        <span
                          key={s}
                          className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function safeParse(s: string | undefined): string[] {
  if (!s) return [];
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function AvailabilityPill({ availability }: { availability: string }) {
  const styles: Record<string, string> = {
    available:
      "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
    busy: "bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400",
    on_leave: "bg-muted text-muted-foreground ring-border",
  };
  const cls =
    styles[availability] ?? "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${cls}`}
    >
      {availability.replace("_", " ")}
    </span>
  );
}

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="space-y-3 p-5">
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
            <div className="h-1 w-full animate-pulse rounded bg-muted" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
