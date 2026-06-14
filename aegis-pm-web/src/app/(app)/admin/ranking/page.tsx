"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Loader2, Sparkles } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  CandidatePanel,
  type Recommendation,
} from "@/components/staging/candidate-panel";

/**
 * Rank with PRD — match the staged candidate pool against a project's needs.
 *
 * Upload a PRD to auto-extract required + priority skills (optionally also
 * creating the project + tasks), tune the thresholds, then rank everyone
 * who's been uploaded on the "Upload Employees" page. Provision your top
 * picks straight from the ranked table.
 */
export default function RankWithPrdPage() {
  // ── PRD upload ────────────────────────────────────────────────────
  const [prdFile, setPrdFile] = React.useState<File | null>(null);
  const [createProject, setCreateProject] = React.useState(true);
  const [prdInfo, setPrdInfo] = React.useState<null | {
    id: number;
    filename: string;
    method: string;
    model: string | null;
    task_description: string;
    skills: string[];
    priority: string[];
    project: { id: number; name: string } | null;
    task_count: number;
  }>(null);

  // ── Ranking inputs ────────────────────────────────────────────────
  const [skills, setSkills] = React.useState("");
  const [priority, setPriority] = React.useState("");
  const [minExperience, setMinExperience] = React.useState(0);
  const [minScore, setMinScore] = React.useState(0);
  const [recs, setRecs] = React.useState<Recommendation[] | null>(null);

  const uploadPrd = useMutation({
    mutationFn: async (f: File) => {
      if (createProject) {
        const r = await api.admin.uploadPrdAndCreateProject(f);
        return {
          kind: "combined" as const,
          prd_id: r.prd_id,
          project: { id: r.project_id, name: r.project_name },
          tasks: r.tasks,
          extraction: {
            method: r.method,
            model: r.model,
            task_description: "",
            skills: r.skills,
            priority_skills: r.priority,
          },
          filename: f.name,
        };
      }
      const r = await api.admin.uploadPrd(f);
      return {
        kind: "parse-only" as const,
        prd_id: r.prd.id,
        project: null,
        tasks: [] as Array<{
          id: number;
          title: string;
          priority: string;
          estimated_hours: number;
          required_skills: string[];
        }>,
        extraction: r.extraction,
        filename: r.prd.filename,
      };
    },
    onSuccess: (res) => {
      setPrdInfo({
        id: res.prd_id,
        filename: res.filename,
        method: res.extraction.method,
        model: res.extraction.model ?? null,
        task_description: res.extraction.task_description,
        skills: res.extraction.skills,
        priority: res.extraction.priority_skills,
        project: res.kind === "combined" ? res.project : null,
        task_count: res.kind === "combined" ? res.tasks.length : 0,
      });
      setSkills(res.extraction.skills.join(", "));
      setPriority(res.extraction.priority_skills.join(", "));
      toast.success(
        res.kind === "combined" ? "Project created from PRD" : "PRD parsed",
        {
          description:
            res.kind === "combined"
              ? `${res.project?.name} · ${res.tasks.length} tasks · ${res.extraction.skills.length} skills`
              : `${res.extraction.skills.length} skills · ${res.extraction.priority_skills.length} priority · via ${res.extraction.method}`,
        }
      );
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "PRD upload failed"),
  });

  const rank = useMutation({
    mutationFn: () =>
      api.admin.recommendedEmployees({
        skills: skills.trim(),
        priority: priority.trim() || undefined,
        min_experience: minExperience > 0 ? minExperience : undefined,
        min_score: minScore > 0 ? minScore : undefined,
      }),
    onSuccess: (res) => setRecs(res),
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Rank failed"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Rank with PRD</h1>
        <p className="text-sm text-muted-foreground">
          Upload a project&apos;s PRD to extract its required skills, then rank
          the uploaded candidate pool by fit and provision your top picks. Add
          people first on the <span className="font-medium">Upload Employees</span>{" "}
          page.
        </p>
      </div>

      {/* ── Step 1: Upload PRD ─────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="size-4" /> 1. Upload PRD
          </CardTitle>
          <CardDescription>
            PDF / TXT / DOCX. We extract required + priority skills and pre-fill
            the ranking below so you can rank in one click.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (prdFile) uploadPrd.mutate(prdFile);
            }}
            className="space-y-3"
          >
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="file"
                accept=".pdf,.txt,.md,.docx"
                onChange={(e) => setPrdFile(e.target.files?.[0] ?? null)}
                className="block text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm hover:file:bg-accent"
              />
              <Button
                type="submit"
                disabled={!prdFile || uploadPrd.isPending}
                variant="outline"
              >
                {uploadPrd.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : createProject ? (
                  "Create project from PRD"
                ) : (
                  "Parse PRD only"
                )}
              </Button>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={createProject}
                onChange={(e) => setCreateProject(e.target.checked)}
              />
              Also create a project and seed tasks from this PRD (recommended).
            </label>
          </form>

          {prdInfo && (
            <div className="mt-4 space-y-2 rounded-md border border-border/60 bg-secondary/40 p-3 text-sm">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  {prdInfo.filename}
                </span>
                <span>·</span>
                <span>
                  extracted via <span className="font-mono">{prdInfo.method}</span>
                  {prdInfo.model ? ` (${prdInfo.model})` : ""}
                </span>
              </div>
              {prdInfo.project && (
                <div className="text-xs">
                  Project created:{" "}
                  <span className="font-medium text-foreground">
                    {prdInfo.project.name}
                  </span>{" "}
                  ·{" "}
                  <span className="text-muted-foreground">
                    {prdInfo.task_count} task{prdInfo.task_count === 1 ? "" : "s"}{" "}
                    seeded
                  </span>
                </div>
              )}
              {prdInfo.task_description && (
                <p className="text-xs text-muted-foreground">
                  {prdInfo.task_description}
                </p>
              )}
              <div className="flex flex-wrap gap-1">
                {prdInfo.skills.map((s) => (
                  <span
                    key={s}
                    className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                      prdInfo.priority.includes(s)
                        ? "bg-primary/10 text-primary"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {s}
                  </span>
                ))}
              </div>
              {prdInfo.skills.length === 0 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  No skills extracted — check the PRD format or edit the skills
                  below manually.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Step 2: Rank ───────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4" /> 2. Rank against required skills
          </CardTitle>
          <CardDescription>
            Comma-separated. Example: <code>React, Node.js, MongoDB</code>.
            Embeddings-based when OpenAI is reachable, keyword fallback otherwise.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (skills.trim()) rank.mutate();
            }}
            className="space-y-3"
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Required skills
                </label>
                <Input
                  placeholder="React, Node.js, MongoDB"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Priority (must-have subset, optional)
                </label>
                <Input
                  placeholder="TypeScript"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Min experience (years):{" "}
                  <span className="font-mono">{minExperience}</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={15}
                  step={1}
                  value={minExperience}
                  onChange={(e) => setMinExperience(Number(e.target.value))}
                  className="w-full accent-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Min match score:{" "}
                  <span className="font-mono">{Math.round(minScore * 100)}%</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={minScore * 100}
                  onChange={(e) => setMinScore(Number(e.target.value) / 100)}
                  className="w-full accent-primary"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                disabled={!skills.trim() || rank.isPending}
                variant="outline"
              >
                {rank.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  "Rank candidates"
                )}
              </Button>
              {recs && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setRecs(null)}
                >
                  Clear ranking
                </Button>
              )}
              {recs && (
                <span className="text-xs text-muted-foreground">
                  {recs.length} candidate{recs.length === 1 ? "" : "s"} returned
                  {recs.some((r) => r.semantic) && " · semantic"}
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {/* ── Step 3: Select + provision (ranked) ────────────────────── */}
      <CandidatePanel recs={recs} batchId={null} />
    </div>
  );
}
