"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Search, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

function useBreadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  return segments.map((seg, i) => ({
    label: seg.charAt(0).toUpperCase() + seg.slice(1),
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));
}

export function Topbar() {
  const crumbs = useBreadcrumbs();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const isDark = mounted && (resolvedTheme ?? theme) === "dark";

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm">
        {crumbs.length === 0 && (
          <span className="text-muted-foreground">Home</span>
        )}
        {crumbs.map((c, i) => (
          <React.Fragment key={c.href}>
            {i > 0 && (
              <span className="text-muted-foreground/50" aria-hidden>
                /
              </span>
            )}
            {c.isLast ? (
              <span className="font-medium text-foreground">{c.label}</span>
            ) : (
              <Link
                href={c.href}
                className="text-muted-foreground hover:text-foreground"
              >
                {c.label}
              </Link>
            )}
          </React.Fragment>
        ))}
      </nav>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            const evt = new KeyboardEvent("keydown", {
              key: "k",
              metaKey: true,
            });
            document.dispatchEvent(evt);
          }}
          className="hidden items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-xs text-muted-foreground shadow-sm hover:bg-accent hover:text-accent-foreground sm:flex"
          aria-label="Open command palette"
        >
          <Search className="size-3.5" />
          <span>Search…</span>
          <kbd className="ml-2 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
            ⌘K
          </kbd>
        </button>

        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle theme"
          onClick={() => setTheme(isDark ? "light" : "dark")}
        >
          {mounted ? (
            isDark ? (
              <Sun className="size-4" />
            ) : (
              <Moon className="size-4" />
            )
          ) : (
            <Moon className="size-4" />
          )}
        </Button>
      </div>
    </header>
  );
}
