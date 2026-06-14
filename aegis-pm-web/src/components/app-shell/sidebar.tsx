"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  Users,
  Bell,
  BarChart3,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  Shield,
  ShieldCheck,
  Sparkles,
  Inbox,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
};

const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Workspace",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "My Tasks", href: "/my-tasks", icon: Inbox },
      { label: "Alerts", href: "/alerts", icon: Bell, adminOnly: true },
    ],
  },
  {
    title: "Build",
    items: [
      { label: "Projects", href: "/projects", icon: FolderKanban, adminOnly: true },
      { label: "Team", href: "/team", icon: Users, adminOnly: true },
    ],
  },
  {
    title: "Insights",
    items: [{ label: "Analytics", href: "/analytics", icon: BarChart3, adminOnly: true }],
  },
  {
    title: "Admin",
    items: [
      { label: "Admin Console", href: "/admin", icon: ShieldCheck, adminOnly: true },
      { label: "Employees", href: "/admin/employees", icon: Users, adminOnly: true },
      { label: "Upload Employees", href: "/admin/staging", icon: Upload, adminOnly: true },
      { label: "Rank with PRD", href: "/admin/ranking", icon: Sparkles, adminOnly: true },
    ],
  },
  {
    title: "Account",
    items: [{ label: "Settings", href: "/settings", icon: Settings }],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const [collapsed, setCollapsed] = React.useState(false);

  const sections = React.useMemo(
    () =>
      SECTIONS.map((s) => ({
        ...s,
        items: s.items.filter((i) => !i.adminOnly || user?.role === "admin"),
      })).filter((s) => s.items.length > 0),
    [user?.role]
  );

  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "group/sidebar fixed inset-y-0 left-0 z-40 flex flex-col border-r border-border bg-card transition-[width] duration-200 ease-out",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
        <div className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
          <Shield className="size-4" />
        </div>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight">
            Aegis PM
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {sections.map((section) => (
          <div key={section.title} className="mb-6 last:mb-0">
            {!collapsed && (
              <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map(({ label, href, icon: Icon }) => {
                const active =
                  pathname === href || pathname.startsWith(href + "/");
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      title={collapsed ? label : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-secondary text-foreground"
                          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                      )}
                    >
                      <Icon className="size-4 shrink-0" />
                      {!collapsed && <span>{label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Collapse */}
      <div className="border-t border-border p-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-muted-foreground"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? (
            <ChevronsRight className="size-4" />
          ) : (
            <>
              <ChevronsLeft className="size-4" />
              <span>Collapse</span>
            </>
          )}
        </Button>
      </div>
    </aside>
  );
}
