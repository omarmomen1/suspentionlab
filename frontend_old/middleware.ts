import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that don't require authentication
const PUBLIC_ROUTES = [
  "/",
  "/pricing",
  "/docs",
  "/auth/login",
  "/auth/register",
  "/auth/forgot",
  "/legal",
];

// Routes that logged-in users shouldn't visit (redirect to app)
const AUTH_ROUTES = ["/auth/login", "/auth/register"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow public routes and static files
  const isPublic = PUBLIC_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );
  const isStatic =
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".") ||
    pathname.startsWith("/onboarding");

  if (isStatic) return NextResponse.next();

  // Check for JWT token in cookie or Authorization header
  // In this app the token is in localStorage (client-side only),
  // so we use a lightweight cookie approach: the auth context sets
  // a 'sl_authed' cookie (httpOnly=false, just a presence flag).
  const authed = request.cookies.has("sl_authed");

  // Redirect authenticated users away from auth pages
  if (authed && AUTH_ROUTES.some((r) => pathname.startsWith(r))) {
    return NextResponse.redirect(new URL("/quarter-car", request.url));
  }

  // Redirect unauthenticated users away from private routes
  if (!isPublic && !authed) {
    const loginUrl = new URL("/auth/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static (static files)
     * - _next/image (image optimisation)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
