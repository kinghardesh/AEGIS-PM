// Token + user storage for the browser.
//
// ── Storage strategy ─────────────────────────────────────────────────────────
// We use `sessionStorage` (not localStorage) so each tab owns its own
// session. Testing admin-in-tab-1 + employee-in-tab-2 in the same browser
// was corrupting each other when both shared localStorage. With
// sessionStorage, tabs are independent — the per-tab bearer is the
// canonical source of truth for API calls.
//
// Cookies still exist (`aegis_token`, `aegis_role`) because Next's
// middleware runs at the edge and can only read cookies, not
// sessionStorage. Cookies are shared across tabs; they only drive INITIAL
// redirect routing (e.g. "not logged in → /login"). Once the page loads,
// each tab's fetcher uses its own sessionStorage bearer for data. A
// cookie mismatch at most causes one tab to route to an admin page it
// then gets a 403 on — no data leaks.
//
// If you want truly independent sessions across windows, use incognito
// or two different browsers.

const TOKEN_KEY = "aegis.token";
const USER_KEY  = "aegis.user";

export type AuthUser = {
  id: number;
  user_id: string;
  email: string | null;
  full_name: string | null;
  role: "user" | "admin" | "agent" | "employee";
  employee_id: number | null;
  is_active: boolean;
  last_login_at: string | null;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: AuthUser;
};

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

export function getToken(): string | null {
  if (!hasWindow()) return null;
  // sessionStorage first (per-tab canonical). Fall back to localStorage for
  // anyone with pre-existing session data so we don't log them out mid-flow.
  return (
    window.sessionStorage.getItem(TOKEN_KEY) ||
    window.localStorage.getItem(TOKEN_KEY)
  );
}

export function getStoredUser(): AuthUser | null {
  if (!hasWindow()) return null;
  const raw =
    window.sessionStorage.getItem(USER_KEY) ||
    window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function saveSession(res: LoginResponse) {
  if (!hasWindow()) return;
  // Canonical store — per tab.
  window.sessionStorage.setItem(TOKEN_KEY, res.access_token);
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(res.user));
  // Nuke any stale localStorage from earlier builds so getToken() never
  // returns the wrong tab's bearer.
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  // Cookie — used only by middleware for routing redirects.
  document.cookie = `aegis_token=${res.access_token}; path=/; SameSite=Lax; max-age=${
    60 * 60 * 12
  }`;
  document.cookie = `aegis_role=${res.user.role}; path=/; SameSite=Lax; max-age=${
    60 * 60 * 12
  }`;
}

export function clearSession() {
  if (!hasWindow()) return;
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  document.cookie = "aegis_token=; path=/; max-age=0";
  document.cookie = "aegis_role=; path=/; max-age=0";
}
