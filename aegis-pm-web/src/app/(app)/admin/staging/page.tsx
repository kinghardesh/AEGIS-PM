"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Upload } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { CandidatePanel } from "@/components/staging/candidate-panel";

/**
 * Upload Employees — pure employee entry.
 *
 * Upload a CSV / XLSX / structured PDF of people, then provision the ones you
 * pick (mints a user_id + one-time password each). Department and manager
 * status are parsed/inferred from the file. PRD-based ranking lives on the
 * separate "Rank with PRD" page.
 */
export default function UploadEmployeesPage() {
  const qc = useQueryClient();

  const [file, setFile]       = React.useState<File | null>(null);
  const [batchId, setBatchId] = React.useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (f: File) => api.admin.uploadEmployees(f),
    onSuccess: (res) => {
      setBatchId(res.batch_id);
      qc.invalidateQueries({ queryKey: ["staging"] });
      toast.success("File processed", {
        description: `${res.rows_staged} staged · ${res.duplicates_skipped} duplicate(s)`,
      });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Upload failed"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Upload Employees
        </h1>
        <p className="text-sm text-muted-foreground">
          Add people to the team. Upload a CSV, XLSX, or structured PDF — we
          parse their skills, department, and manager status — then provision
          the ones you pick. To rank candidates against a project&apos;s PRD,
          use <span className="font-medium">Rank with PRD</span>.
        </p>
      </div>

      {/* ── Step 1: Upload ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="size-4" /> 1. Upload
          </CardTitle>
          <CardDescription>
            Required column: <code>Name</code>. Optional: <code>Email</code>,{" "}
            <code>Skills</code>, <code>Experience</code>, <code>Department</code>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (file) upload.mutate(file);
            }}
            className="flex flex-wrap items-center gap-3"
          >
            <input
              type="file"
              accept=".csv,.xlsx,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm hover:file:bg-accent"
            />
            <Button type="submit" disabled={!file || upload.isPending}>
              {upload.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "Process file"
              )}
            </Button>
            {upload.data && (
              <span className="text-xs text-muted-foreground">
                Batch <span className="font-mono">{upload.data.batch_id}</span>
                {" · "}
                {upload.data.rows_parsed} parsed · {upload.data.rows_staged}{" "}
                staged · {upload.data.duplicates_skipped} duplicate(s)
              </span>
            )}
          </form>
        </CardContent>
      </Card>

      {/* ── Step 2: Select + provision ─────────────────────────────── */}
      <CandidatePanel recs={null} batchId={batchId} />
    </div>
  );
}
