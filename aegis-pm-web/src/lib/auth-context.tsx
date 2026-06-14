"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AuthUser,
  LoginResponse,
  clearSession,
  getStoredUser,
  getToken,
  saveSession,
} from "./auth";

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  ready: boolean;
  /**
   * Authenticate with email (preferred) or legacy user_id. The backend
   * accepts either; we route based on whether the identifier contains '@'.
   */
  login: (identifier: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [token, setToken] = React.useState<string | null>(null);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    setUser(getStoredUser());
    setToken(getToken());
    setReady(true);
  }, []);

  const login = React.useCallback(
    async (identifier: string, password: string): Promise<AuthUser> => {
      const body = identifier.includes("@")
        ? { email: identifier, password }
        : { user_id: identifier, password };
      const res = await fetch(`${BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail =
          (await res.json().catch(() => null))?.detail || "Login failed";
        throw new Error(detail);
      }
      const data = (await res.json()) as LoginResponse;
      saveSession(data);
      setUser(data.user);
      setToken(data.access_token);
      return data.user;
    },
    []
  );

  const logout = React.useCallback(async () => {
    const tok = getToken();
    if (tok) {
      await fetch(`${BASE}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tok}` },
      }).catch(() => {});
    }
    clearSession();
    setUser(null);
    setToken(null);
    router.push("/login");
  }, [router]);

  const value = React.useMemo<AuthContextValue>(
    () => ({ user, token, ready, login, logout }),
    [user, token, ready, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
