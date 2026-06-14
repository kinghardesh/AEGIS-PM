"use client";

import * as React from "react";
import Link from "next/link";
import { Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = React.useState("");
  const [loading, setLoading]       = React.useState(false);
  const [sent, setSent]             = React.useState(false);
  const [error, setError]           = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body = identifier.includes("@")
        ? { email: identifier.trim() }
        : { user_id: identifier.trim() };
      await api.auth.forgotPassword(body);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-background px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <Shield className="size-4" />
          </div>
          <div>
            <div className="text-sm font-semibold">Reset password</div>
            <div className="text-xs text-muted-foreground">
              We&apos;ll email you a reset link.
            </div>
          </div>
        </div>

        {sent ? (
          <div className="space-y-3">
            <div className="rounded-md border border-border bg-secondary/40 p-3 text-sm">
              If an account exists for <span className="font-mono">{identifier}</span>,
              a reset link is on its way. The link expires in 30 minutes.
            </div>
            <Link
              href="/login"
              className="block text-center text-xs text-primary hover:underline"
            >
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            <label className="block text-xs font-medium text-muted-foreground" htmlFor="id">
              User ID or email
            </label>
            <Input
              id="id"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoFocus
            />
            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="size-4 animate-spin" /> : "Send reset link"}
            </Button>
            <div className="text-center text-xs text-muted-foreground">
              Remembered it?{" "}
              <Link href="/login" className="text-primary hover:underline">
                Sign in
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
