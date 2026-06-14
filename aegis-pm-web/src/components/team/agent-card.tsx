"use client";

import * as React from "react";
import { Bot, Mail } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { WorkloadBar, type WorkloadSegments } from "./workload-bar";

export type Agent = {
  id: number;
  name: string;
  role: string | null;
  email: string | null;
  availability: string;
  skills: string[];
  department: string | null;
  is_manager: boolean;
  segments: WorkloadSegments;
  total: number;
};

/**
 * One card per agent/employee. Purely presentational — the parent wires
 * `onOpen` and `active` based on which card the user has selected.
 */
export function AgentCard({
  agent,
  active,
  onOpen,
}: {
  agent: Agent;
  active?: boolean;
  onOpen: () => void;
}) {
  const isAi = isAiAgent(agent.email);

  return (
    <Card
      onClick={onOpen}
      className={cn(
        "cursor-pointer transition-[border-color,box-shadow,transform]",
        "hover:border-primary/40 hover:shadow-sm",
        isAi && !active && "border-primary/40 bg-primary/[0.02]",
        active && "border-primary ring-2 ring-primary/20"
      )}
    >
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "grid size-10 place-items-center rounded-full text-sm font-semibold",
              isAi ? "bg-primary/10 text-primary" : "bg-secondary"
            )}
          >
            {isAi ? <Bot className="size-5" /> : initials(agent.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-medium truncate">{agent.name}</span>
              {isAi && <AiBadge />}
              {agent.is_manager && <ManagerBadge />}
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {agent.department && (
                <span className="rounded-md bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:text-sky-400">
                  {agent.department}
                </span>
              )}
              <span className="truncate">{agent.role ?? "—"}</span>
            </div>
          </div>
          <AvailabilityPill availability={agent.availability} />
        </div>

        {agent.email && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Mail className="size-3" />
            <span className="truncate">{agent.email}</span>
          </div>
        )}

        {/* Stop-propagation on the bar click so card click + bar click don't
            both fire. The bar has its own focus/hover state, too. */}
        <div onClick={(e) => e.stopPropagation()}>
          <WorkloadBar
            total={agent.total}
            segments={agent.segments}
            onOpen={onOpen}
            active={active}
          />
        </div>

        {agent.skills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.skills.slice(0, 6).map((s) => (
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
}

// ── Helpers ────────────────────────────────────────────────────────────────

function isAiAgent(email: string | null): boolean {
  return !!email && email.endsWith("@aegis.ai");
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

function ManagerBadge() {
  return (
    <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-700 ring-1 ring-inset ring-amber-500/20 dark:text-amber-400">
      Mgr
    </span>
  );
}

function AiBadge() {
  return (
    <span className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-primary ring-1 ring-inset ring-primary/20">
      AI
    </span>
  );
}

function AvailabilityPill({ availability }: { availability: string }) {
  const styles: Record<string, string> = {
    available: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-400",
    busy:      "bg-amber-500/10 text-amber-700 ring-amber-500/20 dark:text-amber-400",
    on_leave:  "bg-muted text-muted-foreground ring-border",
  };
  const cls = styles[availability] ?? "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset",
        cls
      )}
    >
      {availability.replace("_", " ")}
    </span>
  );
}
