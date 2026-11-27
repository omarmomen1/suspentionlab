/**
 * Wave 6: Cookie-Only Auth Migration guards.
 *
 * Asserts the frontend never persists session tokens in web storage and that
 * the re-auth modal flow exists in AuthContext. These are static source guards
 * (no DOM render) so they run in the default vitest environment.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const root = path.resolve(__dirname, "..");
const read = (rel: string) => fs.readFileSync(path.join(root, rel), "utf-8");

const FORBIDDEN_WRITES = [
  /localStorage\.setItem\(\s*["']sl_token["']/,
  /localStorage\.setItem\(\s*["']sl_refresh_token["']/,
  /sessionStorage\.setItem\(\s*["']sl_token["']/,
  /sessionStorage\.setItem\(\s*["']sl_refresh_token["']/,
  /localStorage\.setItem\(\s*["']sl_user["']/,
];

const AUTH_TOUCHING_SOURCES = [
  "contexts/AuthContext.tsx",
  "lib/api.ts",
  "lib/telemetry/useLiveTelemetry.ts",
  "app/settings/page.tsx",
];

describe("Wave 6 Cookie-Only Auth Migration", () => {
  it("never writes session tokens or the user profile to web storage", () => {
    for (const rel of AUTH_TOUCHING_SOURCES) {
      const src = read(rel);
      for (const pattern of FORBIDDEN_WRITES) {
        expect(pattern.test(src), `${rel} must not match ${pattern}`).toBe(false);
      }
    }
  });

  it("never reads sl_token / sl_refresh_token from web storage for credentials", () => {
    const readPatterns = [
      /localStorage\.getItem\(\s*["']sl_token["']/,
      /localStorage\.getItem\(\s*["']sl_refresh_token["']/,
      /sessionStorage\.getItem\(\s*["']sl_token["']/,
      /sessionStorage\.getItem\(\s*["']sl_refresh_token["']/,
    ];
    for (const rel of AUTH_TOUCHING_SOURCES) {
      const src = read(rel);
      for (const pattern of readPatterns) {
        expect(pattern.test(src), `${rel} must not match ${pattern}`).toBe(false);
      }
    }
  });

  it("authHeader issues only the CSRF double-submit header (no bearer token)", () => {
    const src = read("contexts/AuthContext.tsx");
    expect(src).not.toMatch(/headers\["Authorization"\]\s*=\s*`Bearer/);
    expect(src).toContain("X-CSRF-Token");
  });

  it("session refresh posts to /auth/refresh without a body token (cookie-based)", () => {
    const ctx = read("contexts/AuthContext.tsx");
    const api = read("lib/api.ts");
    // No refresh_token payload may be constructed from web storage anymore.
    expect(ctx).not.toMatch(/JSON\.stringify\(\{\s*refresh_token/);
    expect(api).not.toMatch(/JSON\.stringify\(\{\s*refresh_token/);
  });

  it("exposes a re-auth gate (sessionExpired + modal) instead of hard logout on 401", () => {
    const src = read("contexts/AuthContext.tsx");
    expect(src).toContain("sessionExpired");
    expect(src).toContain("ReAuthModal");
    expect(src).toContain("setSessionExpired(true)");
    expect(src).toContain("aria-modal");
  });

  it("purges legacy web-storage tokens on mount", () => {
    const src = read("contexts/AuthContext.tsx");
    expect(src).toContain('localStorage.removeItem("sl_token")');
    expect(src).toContain('localStorage.removeItem("sl_refresh_token")');
  });

  it("live telemetry socket omits the token query param when cookie auth applies", () => {
    const src = read("lib/telemetry/useLiveTelemetry.ts");
    expect(src).not.toContain('"demo"');
    expect(src).toContain("sl_token"); // comment documents the cookie fallback
  });
});

describe("Wave 6 review fixes: session-expired signalling and re-auth email", () => {
  it("apiFetch dispatches sl:session-expired when refresh fails, AuthContext listens", () => {
    const api = read("lib/api.ts");
    expect(api).toContain('SESSION_EXPIRED_EVENT = "sl:session-expired"');
    expect(api).toMatch(/dispatchEvent\(new Event\(SESSION_EXPIRED_EVENT\)\)/);
    const ctx = read("contexts/AuthContext.tsx");
    expect(ctx).toMatch(/addEventListener\("sl:session-expired"/);
    expect(ctx).toMatch(/removeEventListener\("sl:session-expired"/);
  });

  it("ReAuthModal email is editable when the profile has no email", () => {
    const ctx = read("contexts/AuthContext.tsx");
    expect(ctx).toContain("const emailLocked = Boolean(user?.email)");
    expect(ctx).toContain("readOnly={emailLocked}");
    expect(ctx).not.toMatch(/value=\{user\?\.email \?\? ""\}\s*\n\s*readOnly\s*\n/);
  });

  it("ReAuthModal opens only when this tab had an authenticated session", () => {
    const ctx = read("contexts/AuthContext.tsx");
    expect(ctx).toContain("const hadSessionRef = useRef(false)");
    expect((ctx.match(/if \(hadSessionRef\.current\) setSessionExpired\(true\)/g) || []).length).toBe(2);
    expect(ctx).not.toMatch(/^\s*setSessionExpired\(true\);/m);
  });
});

// ---------------------------------------------------------------------------
// Behavioral tests (run the real apiFetch against a stubbed fetch and window).
// ---------------------------------------------------------------------------
import { vi, beforeEach, afterEach } from "vitest";
import { apiFetch, getCsrfToken, getAuthToken, SESSION_EXPIRED_EVENT } from "../lib/api";

describe("apiFetch cookie-only behaviour (executed, not grepped)", () => {
  const calls: { url: string; init: any }[] = [];
  let responses: { status: number }[] = [];
  let events: string[] = [];

  beforeEach(() => {
    calls.length = 0;
    events = [];
    (globalThis as any).document = { cookie: "a=1; csrf_token=tok123; b=2" };
    (globalThis as any).window = { dispatchEvent: (e: Event) => { events.push(e.type); return true; } };
    vi.stubGlobal("fetch", async (url: string, init: any) => {
      calls.push({ url, init });
      const r = responses.shift() ?? { status: 200 };
      return { status: r.status, ok: r.status >= 200 && r.status < 300 } as Response;
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete (globalThis as any).document;
    delete (globalThis as any).window;
  });

  it("sends cookies and the CSRF header, and never an Authorization bearer", async () => {
    responses = [{ status: 200 }];
    await apiFetch("/api/v1/x", { method: "POST" });
    expect(calls[0].init.credentials).toBe("include");
    expect(calls[0].init.headers["X-CSRF-Token"]).toBe("tok123");
    expect(calls[0].init.headers.Authorization).toBeUndefined();
    expect(getCsrfToken()).toBe("tok123");
    expect(getAuthToken()).toBe("");
  });

  it("a 401 triggers a cookie refresh with an empty body, then retries", async () => {
    responses = [{ status: 401 }, { status: 200 }, { status: 200 }];
    const res = await apiFetch("/api/v1/x");
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/x", "/api/v1/auth/refresh", "/api/v1/x"]);
    expect(calls[1].init.body).toBe("{}");
    expect(calls[1].init.credentials).toBe("include");
    expect(res.status).toBe(200);
    expect(events).toEqual([]);
  });

  it("a failed refresh fires sl:session-expired and does not retry", async () => {
    responses = [{ status: 401 }, { status: 401 }];
    const res = await apiFetch("/api/v1/x");
    expect(calls.length).toBe(2);
    expect(res.status).toBe(401);
    expect(events).toEqual([SESSION_EXPIRED_EVENT]);
  });

  it("a 401 from an auth endpoint never loops into refresh", async () => {
    responses = [{ status: 401 }];
    await apiFetch("/api/v1/auth/login", { method: "POST" });
    expect(calls.length).toBe(1);
    expect(events).toEqual([]);
  });

  it("getCsrfToken is empty with no cookie", () => {
    (globalThis as any).document = { cookie: "a=1" };
    expect(getCsrfToken()).toBe("");
  });
});
