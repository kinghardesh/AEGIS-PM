"use client";

import Link from "next/link";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { useDeleteProject, useProjects } from "@/lib/hooks/use-projects";

export default function ProjectsPage() {
  const { data: projects, isLoading, isError, error } = useProjects();
  const del = useDeleteProject();

  return (
    <>
      <PageHeader
        title="Projects"
        description="Every PRD you've turned into a coordinated plan."
        actions={<CreateProjectDialog />}
      />

      {isLoading && <SkeletonList />}

      {isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            Could not load projects: {(error as Error).message}
          </CardContent>
        </Card>
      )}

      {projects && projects.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <p className="text-base font-medium">No projects yet</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Paste a PRD to generate tasks, assign them by skill, and start
              tracking progress.
            </p>
          </CardContent>
        </Card>
      )}

      {projects && projects.length > 0 && (
        <Card>
          <div className="overflow-hidden rounded-lg">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  <th className="px-6 py-3">Project</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Progress</th>
                  <th className="px-6 py-3">Tasks</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-border last:border-0 hover:bg-muted/30"
                  >
                    <td className="px-6 py-4">
                      <Link
                        href={`/projects/${p.id}`}
                        className="block max-w-md"
                      >
                        <div className="font-medium text-foreground">
                          {p.name}
                        </div>
                        {p.description && (
                          <div className="line-clamp-1 text-xs text-muted-foreground">
                            {p.description}
                          </div>
                        )}
                      </Link>
                    </td>
                    <td className="px-6 py-4">
                      <StatusPill status={p.status} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary"
                            style={{ width: `${p.progress ?? 0}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-muted-foreground">
                          {Math.round(p.progress ?? 0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-muted-foreground">
                      {p.completed_tasks}/{p.total_tasks}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-1">
                        <Link
                          href={`/projects/${p.id}`}
                          className="inline-flex h-8 items-center justify-center rounded-md border border-input bg-background px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
                        >
                          Open
                        </Link>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Delete ${p.name}`}
                          onClick={() => {
                            if (
                              confirm(
                                `Delete "${p.name}" and all its tasks? This cannot be undone.`
                              )
                            ) {
                              del.mutate(p.id);
                            }
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label="More"
                          disabled
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active:
      "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
    archived: "bg-muted text-muted-foreground ring-border",
  };
  const cls = styles[status] ?? "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {status}
    </span>
  );
}

function SkeletonList() {
  return (
    <Card>
      <div className="divide-y divide-border">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-6 py-4">
            <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-4 w-16 animate-pulse rounded bg-muted" />
            <div className="ml-auto h-4 w-24 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </div>
    </Card>
  );
}
