"use client";

import * as React from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateProject } from "@/lib/hooks/use-projects";

export function CreateProjectDialog() {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [prd, setPrd] = React.useState("");
  const create = useCreateProject();

  function reset() {
    setName("");
    setDescription("");
    setPrd("");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await create.mutateAsync({
      name: name.trim(),
      description: description.trim() || undefined,
      prd_text: prd.trim() || undefined,
    });
    reset();
    setOpen(false);
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus className="size-4" />
        New project
      </Button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal
          aria-labelledby="create-project-title"
          onClick={() => setOpen(false)}
        >
          <form
            onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl"
          >
            <header className="flex items-center justify-between border-b border-border px-6 py-4">
              <h2 id="create-project-title" className="text-base font-semibold">
                New project from PRD
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="space-y-4 px-6 py-5">
              <div className="space-y-1.5">
                <label className="text-xs font-medium" htmlFor="p-name">
                  Project name
                </label>
                <Input
                  id="p-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Checkout redesign"
                  autoFocus
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium" htmlFor="p-desc">
                  Short description
                </label>
                <Input
                  id="p-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="One sentence about the goal"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium" htmlFor="p-prd">
                  PRD
                </label>
                <textarea
                  id="p-prd"
                  value={prd}
                  onChange={(e) => setPrd(e.target.value)}
                  placeholder="Paste markdown or plain text. Aegis will parse it into tasks."
                  rows={8}
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                />
              </div>
            </div>
            <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create project"}
              </Button>
            </footer>
          </form>
        </div>
      )}
    </>
  );
}
