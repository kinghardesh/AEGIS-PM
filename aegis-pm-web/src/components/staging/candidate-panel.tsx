"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, Download, Loader2, UserPlus } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export type StagingRow = Awaited<
  ReturnType<typeof api.admin.listStaging>
>[number];
export type Recommendation = Awaited<
  ReturnType<typeof api.admin.recommendedEmployees>
>[number];

type Creds = {
  batch_id: string;
  created: {
    name: string;
    email: string | null;
    user_id: string;
    password: string;
    employee_id: number;
  }[];
  skipped: { staging_id: number; reason: string }[];
};

/**
 * Candidate selection + provisioning panel — shared by the "Upload Employees"
 * and "Rank with PRD" pages.
 *
 *  - `recs == null`  → plain pending-staging list (entry flow).
 *  - `recs != null`  → ranked list with score columns (PRD flow); rows scoring
 *                      ≥ 0.5 are pre-checked.
 */
export function CandidatePanel({
  recs,
  batchId,
}: {
  recs: Recommendation[] | null;
  batchId: string | null;
}) {
  const qc = useQueryClient();

  const staging = useQuery({
    queryKey: ["staging", batchId],
    queryFn: () => api.admin.listStaging({ batch_id: batchId ?? undefined }),
  });

  const [selected, setSelected] = React.useState<Set<number>>(new Set());
  const [creds, setCreds] = React.useState<Creds | null>(null);

  // When a ranking arrives, pre-check everything scoring ≥ 0.5.
  React.useEffect(() => {
    if (recs) {
      setSelected(
        new Set(recs.filter((r) => r.score >= 0.5).map((r) => r.staging_id))
      );
    }
  }, [recs]);

  const provision = useMutation({
    mutationFn: () => api.admin.createSelectedEmployees(Array.from(selected)),
    onSuccess: (res) => {
      setCreds(res);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["staging"] });
      toast.success(`${res.created.length} employee(s) provisioned`);
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Provisioning failed"),
  });

  const rows: Array<StagingRow & Partial<Recommendation>> = React.useMemo(() => {
    if (recs && recs.length > 0) {
      return recs.map((r) => ({
        id: r.staging_id,
        name: r.name,
        email: r.email,
        skills: r.skills,
        experience: r.experience,
        department: r.department,
        is_manager: r.is_manager,
        upload_batch_id: batchId ?? "",
        status: "pending",
        created_at: "",
        staging_id: r.staging_id,
        score: r.score,
        skill_score: r.skill_score,
        experience_score: r.experience_score,
        priority_bonus: r.priority_bonus,
        confidence: r.confidence,
        matched_skills: r.matched_skills,
        missing_skills: r.missing_skills,
        reason: r.reason,
        semantic: r.semantic,
      }));
    }
    return (staging.data ?? []).filter((r) => r.status === "pending");
  }, [recs, staging.data, batchId]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === rows.length && rows.length > 0) {
      setSelected(new Set());
    } else {
      setSelected(new Set(rows.map((r) => r.id)));
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="size-4" /> Select + create
          </CardTitle>
          <CardDescription>
            Check the ones you want to provision. We&apos;ll mint a{" "}
            <code>user_id</code> and one-time password for each.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-2 pr-2 text-left">
                    <input
                      type="checkbox"
                      checked={selected.size === rows.length && rows.length > 0}
                      onChange={toggleAll}
                      aria-label="Select all"
                    />
                  </th>
                  <th className="py-2 text-left font-medium">Candidate</th>
                  <th className="py-2 text-left font-medium">Department</th>
                  <th className="py-2 text-left font-medium">Skills</th>
                  <th className="py-2 text-right font-medium">Exp</th>
                  {recs && (
                    <>
                      <th className="py-2 text-right font-medium">Match</th>
                      <th className="py-2 text-right font-medium">Skill</th>
                      <th className="py-2 text-right font-medium">Exp %</th>
                      <th className="py-2 text-right font-medium">Pri</th>
                      <th className="py-2 text-left font-medium">Reason</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={recs ? 10 : 5}
                      className="py-8 text-center text-xs text-muted-foreground"
                    >
                      {staging.isLoading
                        ? "Loading…"
                        : "Nothing here yet — upload a file to begin."}
                    </td>
                  </tr>
                )}
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className={cn(
                      "border-b border-border/40 transition-colors hover:bg-accent/40",
                      selected.has(r.id) && "bg-accent/60"
                    )}
                  >
                    <td className="py-1.5 pr-2">
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggle(r.id)}
                      />
                    </td>
                    <td className="py-1.5">
                      <div className="font-medium">{r.name}</div>
                      {r.email && (
                        <div className="text-[11px] text-muted-foreground">{r.email}</div>
                      )}
                    </td>
                    <td className="py-1.5">
                      {r.department ? (
                        <span className="rounded-md bg-sky-500/10 px-1.5 py-0.5 text-[11px] text-sky-700 dark:text-sky-400">
                          {r.department}
                        </span>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">—</span>
                      )}
                      {r.is_manager && (
                        <span className="ml-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">
                          Manager
                        </span>
                      )}
                    </td>
                    <td className="py-1.5">
                      <div className="flex flex-wrap gap-1">
                        {(r.skills ?? []).slice(0, 6).map((s) => (
                          <span
                            key={s}
                            className={cn(
                              "rounded-md px-1.5 py-0.5 text-[10px]",
                              r.matched_skills?.includes(s)
                                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                                : "bg-muted text-muted-foreground"
                            )}
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                      {recs && r.missing_skills && r.missing_skills.length > 0 && (
                        <div className="mt-1 text-[10px] text-muted-foreground">
                          missing: {r.missing_skills.join(", ")}
                        </div>
                      )}
                    </td>
                    <td className="py-1.5 text-right font-mono text-xs">
                      {r.experience ?? "—"}
                    </td>
                    {recs && (
                      <>
                        <td className="py-1.5 text-right font-mono text-xs">
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5",
                              (r.score ?? 0) >= 0.7
                                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                                : (r.score ?? 0) >= 0.4
                                ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
                                : "bg-muted text-muted-foreground"
                            )}
                          >
                            {Math.round((r.score ?? 0) * 100)}%
                            {r.semantic && <span className="ml-1 opacity-60">·AI</span>}
                          </span>
                        </td>
                        <td className="py-1.5 text-right font-mono text-xs text-muted-foreground">
                          {Math.round((r.skill_score ?? 0) * 100)}%
                        </td>
                        <td className="py-1.5 text-right font-mono text-xs text-muted-foreground">
                          {Math.round((r.experience_score ?? 0) * 100)}%
                        </td>
                        <td className="py-1.5 text-right font-mono text-xs text-muted-foreground">
                          {Math.round((r.priority_bonus ?? 0) * 100)}%
                        </td>
                        <td className="py-1.5 text-[11px] text-muted-foreground max-w-[240px]">
                          {r.reason || "—"}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {selected.size} selected
            </span>
            <Button
              onClick={() => provision.mutate()}
              disabled={selected.size === 0 || provision.isPending}
            >
              {provision.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                `Create ${selected.size} employee${selected.size === 1 ? "" : "s"}`
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {creds && <CredentialsModal creds={creds} onClose={() => setCreds(null)} />}
    </>
  );
}

// ── Credentials modal ──────────────────────────────────────────────────────

function CredentialsModal({
  creds,
  onClose,
}: {
  creds: Creds;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const unassigned = useQuery({
    queryKey: ["admin", "unassigned-tasks"],
    queryFn: () => api.admin.unassignedTasks(),
    refetchInterval: 15_000,
  });

  const [picked, setPicked] = React.useState<Record<string, string>>({});
  const [doneRows, setDoneRows] = React.useState<Record<string, number>>({});

  const assignMut = useMutation({
    mutationFn: (v: { taskId: number; employeeId: number; name: string; userKey: string }) =>
      api.tasks.assign(v.taskId, v.employeeId, v.name),
    onSuccess: (_, v) => {
      toast.success(`Task assigned to ${v.name}`);
      setDoneRows((prev) => ({ ...prev, [v.userKey]: v.taskId }));
      setPicked((prev) => ({ ...prev, [v.userKey]: "" }));
      qc.invalidateQueries({ queryKey: ["admin", "unassigned-tasks"] });
      qc.invalidateQueries({ queryKey: ["admin", "employee-monitoring"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Assign failed"),
  });

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
      <div className="w-full max-w-4xl rounded-xl border border-border bg-card p-6 shadow-2xl">
        <h2 className="mb-1 text-lg font-semibold">
          Credentials ({creds.created.length})
        </h2>
        <p className="mb-4 text-xs text-muted-foreground">
          These passwords are shown <strong>only once</strong>. Download the CSV
          now or copy each row. Optionally, assign each new employee an open task
          right here — the picker below is filtered to tasks that don&apos;t yet
          have an owner.
        </p>

        <div className="max-h-96 overflow-y-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th className="py-2 px-3 text-left">Name</th>
                <th className="py-2 px-3 text-left">User ID</th>
                <th className="py-2 px-3 text-left">Password</th>
                <th className="py-2 px-3 text-left">Assign task</th>
                <th className="py-2 px-2" />
              </tr>
            </thead>
            <tbody>
              {creds.created.map((c) => {
                const chosen = picked[c.user_id] ?? "";
                const alreadyDone = doneRows[c.user_id];
                const busy =
                  assignMut.isPending && assignMut.variables?.userKey === c.user_id;
                return (
                  <tr key={c.user_id} className="border-b border-border/40 align-top">
                    <td className="py-2 px-3">{c.name}</td>
                    <td className="py-2 px-3 font-mono text-xs">{c.user_id}</td>
                    <td className="py-2 px-3 font-mono text-xs">{c.password}</td>
                    <td className="py-2 px-3">
                      {alreadyDone ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600">
                          <Check className="size-3" />
                          assigned #{alreadyDone}
                        </span>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <select
                            value={chosen}
                            onChange={(e) =>
                              setPicked((s) => ({ ...s, [c.user_id]: e.target.value }))
                            }
                            disabled={busy || unassigned.isLoading}
                            className="max-w-[220px] rounded-md border border-input bg-background px-2 py-1 text-xs"
                          >
                            <option value="">
                              {unassigned.isLoading
                                ? "Loading…"
                                : unassigned.data?.length
                                ? "Pick an open task…"
                                : "No open tasks"}
                            </option>
                            {unassigned.data?.map((t) => (
                              <option key={t.task_id} value={t.task_id}>
                                [{t.priority}] {t.title.slice(0, 40)}
                              </option>
                            ))}
                          </select>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={!chosen || busy}
                            onClick={() =>
                              assignMut.mutate({
                                taskId: Number(chosen),
                                employeeId: c.employee_id,
                                name: c.name,
                                userKey: c.user_id,
                              })
                            }
                          >
                            {busy ? (
                              <Loader2 className="size-3 animate-spin" />
                            ) : (
                              "Assign"
                            )}
                          </Button>
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-2">
                      <CopyBtn value={`${c.user_id}\t${c.password}`} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {creds.skipped.length > 0 && (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">
            Skipped {creds.skipped.length}:{" "}
            {creds.skipped.map((s) => `#${s.staging_id} (${s.reason})`).join(", ")}
          </p>
        )}

        <div className="mt-4 flex items-center justify-end gap-2">
          <a
            href={api.admin.credentialsExportUrl(creds.batch_id)}
            target="_blank"
            rel="noreferrer"
            download
          >
            <Button variant="outline" className="gap-1.5">
              <Download className="size-4" /> Download CSV
            </Button>
          </a>
          <Button onClick={onClose}>Done</Button>
        </div>
      </div>
    </div>
  );
}

function CopyBtn({ value }: { value: string }) {
  const [ok, setOk] = React.useState(false);
  return (
    <button
      aria-label="Copy"
      className="rounded p-1 text-muted-foreground hover:bg-accent"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setOk(true);
        setTimeout(() => setOk(false), 1100);
      }}
    >
      {ok ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  );
}
