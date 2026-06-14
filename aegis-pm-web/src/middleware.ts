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
  const { pathname } = req.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/public") ||
    isPublic(pathname)
  ) {
    return NextResponse.next();
  }

  const token = req.cookies.get("aegis_token")?.value;
  const role  = req.cookies.get("aegis_role")?.value;

  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = pathname.startsWith("/admin") ? "/admin/login" : "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // Admin-only paths: require admin role at the edge too. This is a
  // UX guardrail — the backend also enforces role on every /admin/*,
  // /projects/*, /employees/*, /analytics, /executors/* etc.
  const ADMIN_PATHS = [
    "/admin",
    "/projects",
    "/executors",
    "/team",
    "/analytics",
    "/alerts",
  ];
  const isAdminPath = ADMIN_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
  if (isAdminPath && role !== "admin") {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Run on everything except Next internals and static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|css|js)$).*)"],
};
