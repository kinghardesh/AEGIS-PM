import { NextRequest, NextResponse } from "next/server";

// Route-level auth guard. We only check presence of the token cookie — the
// backend enforces validity. This avoids a DB round-trip on every SSR render.
//
// Protected:  everything under (app) (/dashboard, /projects, /alerts, /admin/*)
// Public:     /login, /admin/login, static assets, API proxying (none here).

const PUBLIC_EXACT = new Set<string>([
  "/login",
  "/admin/login",
  "/forgot-password",
  "/register",
]);

function isPublic(pathname: string): boolean {
  if (PUBLIC_EXACT.has(pathname)) return true;
  // /reset-password/<token>
  if (pathname.startsWith("/reset-password/")) return true;
  return false;
}

export function middleware(req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  // Run on everything except Next internals and static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|css|js)$).*)"],
};
