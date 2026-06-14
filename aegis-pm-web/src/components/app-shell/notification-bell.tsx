"use client";

import * as React from "react";
import { Bell, Check, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useNotifications } from "@/lib/hooks/use-notifications";
import { formatDistanceToNow } from "date-fns";

export function NotificationBell() {
  const { notifications, unread, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="icon"
        aria-label={`${unread} unread notifications`}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 inline-grid size-4 place-items-center rounded-full bg-destructive text-[10px] font-semibold text-destructive-foreground">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-medium">Notifications</span>
            {unread > 0 && (
              <button
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => markAllRead()}
              >
                <CheckCheck className="size-3" /> Mark all read
              </button>
            )}
          </div>

          <ul className="max-h-96 overflow-y-auto">
            {notifications.length === 0 && (
              <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                You&apos;re all caught up.
              </li>
            )}
            {notifications.map((n) => (
              <li
                key={n.id}
                className={cn(
                  "flex items-start gap-2 border-b border-border/60 px-3 py-2 text-sm last:border-b-0",
                  !n.read_at && "bg-secondary/40"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{n.title}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                      {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  {n.body && (
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{n.body}</p>
                  )}
                </div>
                {!n.read_at && (
                  <button
                    aria-label="Mark read"
                    onClick={() => markRead(n.id)}
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                  >
                    <Check className="size-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
