"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const INTEGRATIONS = [
  {
    name: "PostgreSQL",
    description: "Primary datastore for projects, tasks, and team",
    keyHint: "DATABASE_URL",
    healthCheck: true,
  },
  {
    name: "Groq",
    description: "LLM provider for AI parsing and developer briefs",
    keyHint: "GROQ_API_KEY",
  },
  {
    name: "OpenAI",
    description: "Fallback LLM provider",
    keyHint: "OPENAI_API_KEY",
  },
  {
    name: "Resend",
    description: "Transactional email when tasks are assigned",
    keyHint: "RESEND_API_KEY",
  },
  {
    name: "Jira",
    description: "Source of truth for stale-task monitoring",
    keyHint: "JIRA_API_TOKEN",
  },
];

export default function SettingsPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  return (
    <>
      <PageHeader
        title="Settings"
        description="Workspace, integrations, and API keys."
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Workspace</CardTitle>
            <CardDescription>
              Connected to{" "}
              <span className="font-mono text-xs">
                {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-4 py-3 text-sm">
              <div>
                <div className="font-medium">Backend health</div>
                <div className="text-xs text-muted-foreground">
                  {health.isLoading
                    ? "Checking…"
                    : health.data
                      ? `${health.data.service} · DB ${health.data.database}`
                      : "Unreachable"}
                </div>
              </div>
              {health.data ? (
                <CheckCircle2 className="size-5 text-emerald-500" />
              ) : (
                <XCircle className="size-5 text-destructive" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Integrations</CardTitle>
            <CardDescription>
              Configure these via your <code className="font-mono">.env</code>{" "}
              file. Keys are loaded server-side and never sent to the browser.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {INTEGRATIONS.map((i) => (
              <div
                key={i.name}
                className="flex items-center justify-between rounded-md border border-border px-4 py-3"
              >
                <div>
                  <div className="text-sm font-medium">{i.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {i.description}
                  </div>
                </div>
                <code className="rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {i.keyHint}
                </code>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
