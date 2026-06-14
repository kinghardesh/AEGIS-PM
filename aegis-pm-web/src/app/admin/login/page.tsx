"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ShieldCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { ThreeBg } from "@/components/ui/three-bg";

export default function AdminLoginPage() {
  const router = useRouter();
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
      if (user.role !== "admin") {
        setError("This account is not authorised for admin access.");
        setLoading(false);
        return;
      }
      router.push("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setLoading(false);
    }
  }

  return (
    <div className="dark relative min-h-screen grid place-items-center px-4 overflow-hidden text-foreground">
      <ThreeBg />
      <div className="w-full max-w-sm rounded-xl border border-border/40 bg-card/60 backdrop-blur-md p-6 shadow-2xl relative z-10">
        <div className="flex items-center gap-2 mb-6">
          <div className="grid size-8 place-items-center rounded-md bg-destructive text-destructive-foreground">
            <ShieldCheck className="size-4" />
          </div>
          <div>
            <div className="text-sm font-semibold">Aegis PM — Admin</div>
            <div className="text-xs text-muted-foreground">Production access</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="id">
            Admin User ID
          </label>
          <Input
            id="id"
            type="text"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username"
            placeholder="admin"
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

        <div className="mt-4 text-center text-xs text-muted-foreground">
          Not an admin?{" "}
          <Link href="/login" className="text-primary hover:underline">
            User login
          </Link>
        </div>
      </div>
    </div>
  );
}
