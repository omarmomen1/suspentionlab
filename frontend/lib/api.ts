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

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    "X-CSRF-Token": getCsrfToken(),
    ...(options.headers ?? {}),
  };
  return fetch(url, { ...options, credentials: "include", headers });
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
