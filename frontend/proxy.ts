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

import { jwtVerify } from "jose";

const JWT_SECRET = new TextEncoder().encode(process.env.JWT_SECRET ?? "");

export default async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isStatic =
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".") ||
    pathname.startsWith("/onboarding");

  if (isStatic) return NextResponse.next();

  const isPublic = PUBLIC_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );

  const token = request.cookies.get("sl_token")?.value;
  let authed = false;
  if (token) {
      try {
          await jwtVerify(token, JWT_SECRET);
          authed = true;
      } catch (err) {
          console.error("JWT Verify Error in proxy.ts:", err);
          authed = false;
      }
  }

  if (authed && AUTH_ROUTES.some((r) => pathname.startsWith(r))) {
    return NextResponse.redirect(new URL("/quarter-car", request.url));
  }

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


