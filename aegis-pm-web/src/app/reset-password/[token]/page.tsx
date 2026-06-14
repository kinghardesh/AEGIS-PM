"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export default function ResetPasswordPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token  = decodeURIComponent(params?.token ?? "");

  const [pw1, setPw1]       = React.useState("");
  const [pw2, setPw2]       = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState<string | null>(null);
  const [done, setDone]       = React.useState(false);

  function validate(): string | null {
    if (pw1.length < 8) return "Password must be at least 8 characters.";
    if (pw1.length > 128) return "Password too long.";
    if (!/[A-Za-z]/.test(pw1) || !/\d/.test(pw1))
      return "Password must contain both letters and digits.";
    if (pw1 !== pw2) return "Passwords do not match.";
    return null;
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const v = validate();
    if (v) {
      setError(v);
      return;
    }
    setLoading(true);
    try {
      await api.auth.resetPassword(token, pw1);
      setDone(true);
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
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
            <div className="text-sm font-semibold">Set a new password</div>
            <div className="text-xs text-muted-foreground">This link is single-use.</div>
          </div>
        </div>

        {done ? (
          <div className="space-y-3">
            <div className="rounded-md border border-border bg-secondary/40 p-3 text-sm">
              Password updated. Redirecting to sign in…
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            <label className="block text-xs font-medium text-muted-foreground" htmlFor="pw1">
              New password
            </label>
            <Input
              id="pw1"
              type="password"
              value={pw1}
              onChange={(e) => setPw1(e.target.value)}
              autoFocus
              required
            />

            <label className="block text-xs font-medium text-muted-foreground pt-1" htmlFor="pw2">
              Confirm password
            </label>
            <Input
              id="pw2"
              type="password"
              value={pw2}
              onChange={(e) => setPw2(e.target.value)}
              required
            />

            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="size-4 animate-spin" /> : "Update password"}
            </Button>

            <div className="text-center text-xs text-muted-foreground">
              <Link href="/login" className="text-primary hover:underline">
                Back to sign in
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
