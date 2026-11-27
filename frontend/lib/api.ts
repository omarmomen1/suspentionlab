/**
 * Canonical frontend API client.
 *
 * Every backend call that touches an authenticated endpoint MUST go through
 * `apiFetch`: it attaches cookies (`credentials: "include"`) and the
 * `X-CSRF-Token` double-submit header the backend's `verify_api_key`
 * requires on non-GET requests. Raw `fetch()` calls silently omit these and
 * fail with 401/403 — or worse, tempt someone to weaken the backend.
 *
 * ESLint enforces this via `no-restricted-syntax` in eslint.config.mjs:
 * direct `fetch(...)` calls outside the allowlist are flagged.
 */

export function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(^| )csrf_token=([^;]+)/);
  return match ? match[2] : "";
}

/**
 * Wave 6: cookie-only auth. Access tokens live exclusively in HttpOnly cookies
 * and are never readable from JavaScript. Kept for compatibility; always "".
 */
export function getAuthToken(): string {
  return "";
}

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

export function normalizeApiUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  const cleanUrl = url.startsWith("/") ? url : `/${url}`;
  if (!API_BASE) {
    return cleanUrl;
  }
  if (cleanUrl === API_BASE || cleanUrl.startsWith(`${API_BASE}/`)) {
    return cleanUrl;
  }
  if (API_BASE.endsWith("/api/v1") && cleanUrl.startsWith("/api/v1")) {
    const basePrefix = API_BASE.slice(0, -"/api/v1".length);
    return `${basePrefix}${cleanUrl}`;
  }
  if (API_BASE.endsWith("/api") && cleanUrl.startsWith("/api/")) {
    const basePrefix = API_BASE.slice(0, -"/api".length);
    return `${basePrefix}${cleanUrl}`;
  }
  return `${API_BASE}${cleanUrl}`;
}

/** Window event fired when a 401 could not be refreshed; AuthContext listens. */
export const SESSION_EXPIRED_EVENT = "sl:session-expired";

let apiRefreshPromise: Promise<boolean> | null = null;

/** Cookie-only session refresh: the server reads the HttpOnly sl_refresh_token
 * cookie and rotates both cookies. Resolves true when the session was renewed. */
async function tryRefreshSession(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (apiRefreshPromise) return apiRefreshPromise;

  apiRefreshPromise = (async () => {
    try {
      const refreshUrl = normalizeApiUrl("/api/v1/auth/refresh");
      const res = await fetch(refreshUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      apiRefreshPromise = null;
    }
  })();

  return apiRefreshPromise;
}

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const fullUrl = normalizeApiUrl(url);

  const headers: Record<string, string> = {
    "X-CSRF-Token": getCsrfToken(),
    ...(options.headers as Record<string, string> ?? {}),
  };

  let res = await fetch(fullUrl, { ...options, credentials: "include", headers });

  const isAuthEndpoint =
    fullUrl.includes("/auth/login") ||
    fullUrl.includes("/auth/refresh") ||
    fullUrl.includes("/auth/clear-cookie");

  if (res.status === 401 && !isAuthEndpoint) {
    const refreshed = await tryRefreshSession();
    if (refreshed) {
      // Rotated cookies ride along automatically on the retry.
      res = await fetch(fullUrl, { ...options, credentials: "include", headers });
    } else if (typeof window !== "undefined") {
      // Refresh failed: tell AuthContext so it opens the same ReAuthModal that
      // fetchWithAuth callers get (no hard logout, unsaved inputs stay mounted).
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }

  return res;
}

/** JSON helper: apiFetch + parse + typed result, throws on !ok. */
export async function apiJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await apiFetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText}: ${body.slice(0, 300)}`);
  }
  return (await res.json()) as T;
}
