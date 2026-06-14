"use client";

import * as React from "react";
import {
  Bot,
  Code2,
  FlaskConical,
  FileText,
  Search,
  Eye,
  Stethoscope,
  Sparkles,
  Copy,
  Check,
  Clock,
} from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useExecutors, useRunExecutor } from "@/lib/hooks/use-executors";

type AgentMeta = {
  name: string;
  title: string;
  blurb: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
  placeholderSummary: string;
  placeholderDesc: string;
};

const AGENT_META: Record<string, AgentMeta> = {
  code_writer: {
    name: "code_writer",
    title: "Code Writer",
    blurb: "Turns a feature description into a runnable implementation.",
    icon: Code2,
    accent: "text-sky-500",
    placeholderSummary: "Add rate limiting to the /login endpoint",
    placeholderDesc:
      "Describe the feature: what should be built, which files, constraints, tech stack, acceptance criteria…",
  },
  test_writer: {
    name: "test_writer",
    title: "Test Writer",
    blurb: "Writes pytest / vitest tests for a feature or bug.",
    icon: FlaskConical,
    accent: "text-emerald-500",
    placeholderSummary: "Write tests for the billing invoice service",
    placeholderDesc:
      "What are we testing? Include the contract/behaviour, any edge cases you care about, and the tech stack.",
  },
  doc_writer: {
    name: "doc_writer",
    title: "Doc Writer",
    blurb: "Produces READMEs, API references, runbooks, or ADRs.",
    icon: FileText,
    accent: "text-violet-500",
    placeholderSummary: "Runbook: database connection pool exhaustion",
    placeholderDesc:
      "What are we documenting? Add any facts the doc must include — commands, URLs, owners, steps.",
  },
  researcher: {
    name: "researcher",
    title: "Researcher",
    blurb: "Compares options and recommends an approach.",
    icon: Search,
    accent: "text-amber-500",
    placeholderSummary: "Choose a queueing system for async email delivery",
    placeholderDesc:
      "Pose the question, list the candidates you already have in mind, and the constraints (cost, scale, ops burden).",
  },
  reviewer: {
    name: "reviewer",
    title: "Reviewer",
    blurb: "Reviews a diff or code snippet and returns blockers + suggestions.",
    icon: Eye,
    accent: "text-rose-500",
    placeholderSummary: "Review auth middleware change",
    placeholderDesc:
      "Paste the diff, the full file, or describe the change. Include any non-obvious context the reviewer needs.",
  },
  triage: {
    name: "triage",
    title: "Triage",
    blurb: "Produces a severity, repro, root cause, and next steps.",
    icon: Stethoscope,
    accent: "text-orange-500",
    placeholderSummary: "Intermittent 500s on checkout after last deploy",
    placeholderDesc:
      "Describe the symptom, what's in the logs/stack trace, when it started, and any reproduction steps you have.",
  },
};

const AGENT_ORDER = [
  "code_writer",
  "test_writer",
  "doc_writer",
  "researcher",
  "reviewer",
  "triage",
] as const;

export default function ExecutorsPage() {
  const { data: executors } = useExecutors();
  const [selected, setSelected] = React.useState<string>("code_writer");
  const [summary, setSummary] = React.useState("");
  const [description, setDescription] = React.useState("");
  const run = useRunExecutor();

  const meta = AGENT_META[selected] ?? AGENT_META.code_writer;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;
    run.mutate({
      agent: selected,
      summary: summary.trim(),
      description: description.trim(),
    });
  };

  return (
    <>
      <PageHeader
        title="Executor Agents"
        description="Pick an agent, describe the task, and it gets done. The agent's output appears below — no Jira ticket needed."
      />

      {/* Agent picker */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {AGENT_ORDER.map((key) => {
          const m = AGENT_META[key];
          const active = selected === key;
          const available = executors?.some((e) => e.name === key) ?? true;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setSelected(key)}
              disabled={!available}
              className={cn(
                "group flex flex-col items-start gap-2 rounded-lg border p-3 text-left transition-all",
                active
                  ? "border-primary bg-secondary shadow-sm"
                  : "border-border bg-card hover:border-border/80 hover:bg-muted/40",
                !available && "cursor-not-allowed opacity-50"
              )}
            >
              <div
                className={cn(
                  "grid size-8 place-items-center rounded-md bg-muted transition-colors",
                  active && "bg-background"
                )}
              >
                <m.icon className={cn("size-4", m.accent)} />
              </div>
              <div className="min-w-0 space-y-0.5">
                <div className="text-sm font-medium">{m.title}</div>
                <div className="text-[11px] leading-tight text-muted-foreground">
                  {m.blurb}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Form + result layout */}
      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="flex items-center gap-2">
                <meta.icon className={cn("size-4", meta.accent)} />
                <h2 className="text-sm font-semibold">
                  {meta.title} · run ad-hoc
                </h2>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="exec-summary"
                  className="text-xs font-medium text-muted-foreground"
                >
                  Task summary
                </label>
                <Input
                  id="exec-summary"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder={meta.placeholderSummary}
                  maxLength={500}
                  disabled={run.isPending}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="exec-desc"
                  className="text-xs font-medium text-muted-foreground"
                >
                  Description{" "}
                  <span className="text-[10px]">(context, constraints, examples)</span>
                </label>
                <textarea
                  id="exec-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={meta.placeholderDesc}
                  rows={10}
                  maxLength={20000}
                  disabled={run.isPending}
                  className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                />
                <p className="text-[10px] text-muted-foreground">
                  {description.length}/20,000 characters
                </p>
              </div>

              <div className="flex items-center justify-between gap-3 pt-2">
                <p className="text-[11px] text-muted-foreground">
                  Typical runs take 5-60 seconds.
                </p>
                <Button
                  type="submit"
                  disabled={!summary.trim() || run.isPending}
                  className="gap-1.5"
                >
                  {run.isPending ? (
                    <>
                      <Spinner />
                      Running…
                    </>
                  ) : (
                    <>
                      <Sparkles className="size-3.5" />
                      Run {meta.title}
                    </>
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="lg:col-span-3">
          <DeliverablePanel
            loading={run.isPending}
            error={run.error?.message}
            data={run.data}
            agentTitle={meta.title}
          />
        </div>
      </div>
    </>
  );
}

function DeliverablePanel({
  loading,
  error,
  data,
  agentTitle,
}: {
  loading: boolean;
  error?: string;
  data?: { deliverable: string; duration_ms: number; agent: string };
  agentTitle: string;
}) {
  const [copied, setCopied] = React.useState(false);
  const onCopy = async () => {
    if (!data?.deliverable) return;
    await navigator.clipboard.writeText(data.deliverable);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-20 text-center">
          <Spinner size="lg" />
          <p className="text-sm font-medium">{agentTitle} is working…</p>
          <p className="text-xs text-muted-foreground">
            The LLM is drafting your deliverable. This usually takes under a minute.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-16 text-center">
          <p className="text-sm font-medium text-destructive">Run failed</p>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-20 text-center text-muted-foreground">
          <Bot className="size-8 opacity-40" />
          <p className="text-sm">
            Your deliverable will appear here.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider">
            {data.agent}
          </span>
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="size-3" />
            {(data.duration_ms / 1000).toFixed(1)}s
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onCopy}
          className="h-7 gap-1 text-xs"
        >
          {copied ? (
            <>
              <Check className="size-3" />
              Copied
            </>
          ) : (
            <>
              <Copy className="size-3" />
              Copy
            </>
          )}
        </Button>
      </div>
      <pre className="whitespace-pre-wrap break-words px-5 py-4 font-mono text-[12.5px] leading-relaxed text-foreground">
        {data.deliverable}
      </pre>
    </Card>
  );
}

function Spinner({ size = "sm" }: { size?: "sm" | "lg" }) {
  const dim = size === "lg" ? "size-6" : "size-3.5";
  return (
    <span
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-current border-t-transparent",
        dim
      )}
    />
  );
}
