"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";

export default function UserLoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { login } = useAuth();

  const [identifier, setIdentifier] = React.useState("");
  const [password, setPassword]     = React.useState("");
  const [loading, setLoading]       = React.useState(false);
  const [error, setError]           = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await login(identifier.trim(), password);
      const next = params.get("next");
      router.push(next || (user.role === "admin" ? "/admin" : "/dashboard"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
            <div className="text-sm font-semibold">Aegis PM</div>
            <div className="text-xs text-muted-foreground">Sign in</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="id">
            User ID
          </label>
          <Input
            id="id"
            type="text"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username"
            placeholder="Use the ID your admin shared"
            autoFocus
            required
          />

          <label className="block text-xs font-medium text-muted-foreground pt-1" htmlFor="pw">
            Password
          </label>
          <Input
            id="pw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : "Sign in"}
          </Button>

          <div className="text-right">
            <Link
              href="/forgot-password"
              className="text-[11px] text-muted-foreground hover:text-foreground hover:underline"
            >
              Forgot password?
            </Link>
          </div>
        </form>

        <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            New here?{" "}
            <Link href="/register" className="text-primary hover:underline">
              Create an account
            </Link>
          </span>
          <Link href="/admin/login" className="text-primary hover:underline">
            Admin login
          </Link>
        </div>
      </div>
    </div>
  );
}
