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

export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem("sl_token") || sessionStorage.getItem("sl_token") || "";
  } catch {
    return "";
  }
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

let apiRefreshPromise: Promise<string | null> | null = null;

async function tryRefreshToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  let storedRefreshToken = "";
  try {
    storedRefreshToken = (localStorage.getItem("sl_refresh_token") || sessionStorage.getItem("sl_refresh_token") || "").trim();
  } catch {
    return null;
  }
  if (!storedRefreshToken) {
    return null;
  }
  if (apiRefreshPromise) return apiRefreshPromise;

  apiRefreshPromise = (async () => {
    try {
      const refreshUrl = normalizeApiUrl("/api/v1/auth/refresh");
      const res = await fetch(refreshUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.token) {
          try {
            localStorage.setItem("sl_token", data.token);
            if (data.refresh_token) {
              localStorage.setItem("sl_refresh_token", data.refresh_token);
            }
          } catch {}
          return data.token as string;
        }
      }
      try {
        localStorage.removeItem("sl_refresh_token");
      } catch {}
      return null;
    } catch {
      return null;
    } finally {
      apiRefreshPromise = null;
    }
  })();

  return apiRefreshPromise;
}

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const fullUrl = normalizeApiUrl(url);
  const token = getAuthToken();

  const headers: Record<string, string> = {
    "X-CSRF-Token": getCsrfToken(),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  };
  
  let res = await fetch(fullUrl, { ...options, credentials: "include", headers });

  const isAuthEndpoint =
    fullUrl.includes("/auth/login") ||
    fullUrl.includes("/auth/refresh") ||
    fullUrl.includes("/auth/clear-cookie");

  if (res.status === 401 && !isAuthEndpoint) {
    const refreshedToken = await tryRefreshToken();
    if (refreshedToken) {
      const retryHeaders: Record<string, string> = {
        ...headers,
        Authorization: `Bearer ${refreshedToken}`,
      };
      res = await fetch(fullUrl, { ...options, credentials: "include", headers: retryHeaders });
    } else {
      if (typeof window !== "undefined") {
        try {
          localStorage.removeItem("sl_token");
        } catch {}
      }
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
