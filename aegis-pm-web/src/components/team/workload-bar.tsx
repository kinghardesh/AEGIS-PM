"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type WorkloadSegments = {
  todo: number;
  in_progress: number;
  done: number;
  paused?: number;
};

/**
 * A clickable workload summary.
 *
 * Displayed as a single bar with three coloured segments (todo / in_progress
 * / done) proportional to the task counts. Clicking it calls `onOpen` — the
 * parent opens a drawer with the full task list.
 *
 * The whole surface is a <button> so it's keyboard-accessible out of the
 * box; hitting Enter / Space fires the same handler.
 */
export function WorkloadBar({
  total,
  segments,
  onOpen,
  active,
  label = "Workload",
}: {
  total: number;
  segments: WorkloadSegments;
  onOpen: () => void;
  active?: boolean;
  label?: string;
}) {
  const { todo, in_progress, done, paused = 0 } = segments;
  const denom = Math.max(1, todo + in_progress + done + paused);
  const pct = (n: number) => (n / denom) * 100;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Open ${total} task${total === 1 ? "" : "s"}`}
      className={cn(
        "group w-full rounded-md p-2 -mx-2 text-left transition-colors",
        "hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "bg-accent"
      )}
    >
      <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>{label}</span>
        <span className="tabular-nums">
          {total} task{total === 1 ? "" : "s"}
        </span>
      </div>

      {total > 0 ? (
        <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <span
            className="block bg-emerald-500 transition-[width]"
            style={{ width: `${pct(done)}%` }}
          />
          <span
            className="block bg-blue-500 transition-[width]"
            style={{ width: `${pct(in_progress)}%` }}
          />
          <span
            className="block bg-amber-500 transition-[width]"
            style={{ width: `${pct(paused)}%` }}
          />
          <span
            className="block bg-muted-foreground/30 transition-[width]"
            style={{ width: `${pct(todo)}%` }}
          />
        </div>
      ) : (
        <div className="h-1.5 w-full rounded-full bg-muted" />
      )}

      <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
        <Legend swatch="bg-emerald-500" value={done} label="done" />
        <Legend swatch="bg-blue-500"    value={in_progress} label="in progress" />
        {paused > 0 && <Legend swatch="bg-amber-500" value={paused} label="paused" />}
        <Legend swatch="bg-muted-foreground/30" value={todo} label="todo" />
      </div>
    </button>
  );
}

function Legend({
  swatch,
  value,
  label,
}: {
  swatch: string;
  value: number;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      <span className={cn("size-1.5 rounded-full", swatch)} />
      {value} {label}
    </span>
  );
}
