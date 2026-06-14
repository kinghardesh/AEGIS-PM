"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [name, setName]         = React.useState("");
  const [email, setEmail]       = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading]   = React.useState(false);
  const [error, setError]       = React.useState<string | null>(null);

  function validate(): string | null {
    if (!name.trim()) return "Name is required.";
    if (!email.includes("@")) return "Enter a valid email.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
      return "Password must contain both letters and digits.";
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
      await api.auth.register({ name: name.trim(), email: email.trim(), password });
      // Immediately log them in so they land on the User dashboard.
      await login(email.trim(), password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
            <div className="text-sm font-semibold">Create your Aegis account</div>
            <div className="text-xs text-muted-foreground">Free · takes 10 seconds</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="name">
            Name
          </label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} autoFocus required />

          <label className="block text-xs font-medium text-muted-foreground pt-1" htmlFor="email">
            Email
          </label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />

          <label className="block text-xs font-medium text-muted-foreground pt-1" htmlFor="password">
            Password
          </label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
          <p className="text-[11px] text-muted-foreground">
            8+ characters with letters and digits.
          </p>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : "Create account"}
          </Button>
        </form>

        <div className="mt-4 text-center text-xs text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
