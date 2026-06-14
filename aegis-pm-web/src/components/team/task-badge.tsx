import { cn } from "@/lib/utils";

// Shared badge styling for task status/priority. Kept as one component so
// status colours are defined in a single place — changing the palette here
// updates every surface that renders tasks.

const STATUS_STYLES: Record<string, string> = {
  todo: "bg-muted text-muted-foreground",
  in_progress: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  paused: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  done: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  completed: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  pending: "bg-muted text-muted-foreground",
};

const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-red-500/10 text-red-700 dark:text-red-400",
  medium: "bg-muted text-muted-foreground",
  low: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "bg-muted text-muted-foreground";
  return <Pill className={style}>{status.replace("_", " ")}</Pill>;
}

export function PriorityBadge({ priority }: { priority: string | null | undefined }) {
  if (!priority || priority === "medium") return null;
  const style = PRIORITY_STYLES[priority] ?? "bg-muted text-muted-foreground";
  return <Pill className={style}>{priority}</Pill>;
}

function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        className
      )}
    >
      {children}
    </span>
  );
}
