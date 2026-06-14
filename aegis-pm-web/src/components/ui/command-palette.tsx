"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  LayoutDashboard,
  FolderKanban,
  Users,
  Bell,
  BarChart3,
  Settings,
  Search,
  Inbox,
  ShieldCheck,
  Upload,
  Sparkles,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

type Nav = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
};

const NAV_ITEMS: Nav[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "My Tasks", href: "/my-tasks", icon: Inbox },
  { label: "Projects", href: "/projects", icon: FolderKanban, adminOnly: true },
  { label: "Team", href: "/team", icon: Users, adminOnly: true },
  { label: "Alerts", href: "/alerts", icon: Bell, adminOnly: true },
  { label: "Analytics", href: "/analytics", icon: BarChart3, adminOnly: true },
  { label: "Admin Console", href: "/admin", icon: ShieldCheck, adminOnly: true },
  { label: "Employees", href: "/admin/employees", icon: Users, adminOnly: true },
  { label: "Upload Employees", href: "/admin/staging", icon: Upload, adminOnly: true },
  { label: "Rank with PRD", href: "/admin/ranking", icon: Sparkles, adminOnly: true },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function CommandPalette() {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  // Searchable content — fetched only while the palette is open, and only for
  // admins (the underlying endpoints require admin; a 401 would bounce a
  // non-admin to /login). Shares the ["projects"]/["employees"] cache.
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects.list,
    enabled: open && isAdmin,
  });
  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: api.employees.list,
    enabled: open && isAdmin,
  });

  const navItems = NAV_ITEMS.filter((n) => isAdmin || !n.adminOnly);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/20 px-4 pt-[18vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <Command
        label="Command palette"
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center border-b border-border px-3">
          <Search className="size-4 text-muted-foreground" />
          <Command.Input
            autoFocus
            placeholder="Search projects, people, pages…"
            className="flex h-11 w-full bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="ml-2 hidden rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline">
            ESC
          </kbd>
        </div>
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="px-2 py-6 text-center text-sm text-muted-foreground">
            No results.
          </Command.Empty>

          <Command.Group
            heading="Navigation"
            className="px-2 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >
            {navItems.map(({ label, href, icon: Icon }) => (
              <Command.Item
                key={href}
                value={`go ${label}`}
                onSelect={() => go(href)}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm",
                  "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                )}
              >
                <Icon className="size-4 text-muted-foreground" />
                <span>{label}</span>
              </Command.Item>
            ))}
          </Command.Group>

          {isAdmin && projects.data && projects.data.length > 0 && (
            <Command.Group
              heading="Projects"
              className="px-2 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
            >
              {projects.data.map((p) => (
                <Command.Item
                  key={`project-${p.id}`}
                  value={`project ${p.name} ${p.status ?? ""}`}
                  onSelect={() => go(`/projects/${p.id}`)}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm",
                    "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                  )}
                >
                  <FolderKanban className="size-4 text-muted-foreground" />
                  <span className="truncate">{p.name}</span>
                  {p.status && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {p.status}
                    </span>
                  )}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {isAdmin && employees.data && employees.data.length > 0 && (
            <Command.Group
              heading="People"
              className="px-2 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
            >
              {employees.data.map((e) => (
                <Command.Item
                  key={`emp-${e.id}`}
                  value={`person ${e.name} ${e.email ?? ""} ${e.department ?? ""}`}
                  onSelect={() => go("/team")}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm",
                    "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                  )}
                >
                  <UserRound className="size-4 text-muted-foreground" />
                  <span className="truncate">{e.name}</span>
                  {e.department && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {e.department}
                    </span>
                  )}
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}
