"use client";
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { getUserPlanLevel, PLAN_LEVELS } from "../lib/planGate";

export function resolveApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const envBase = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL)
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "")
    : "";

  if (envBase) {
    if (cleanPath === envBase || cleanPath.startsWith(`${envBase}/`)) {
      return cleanPath;
    }
    if (envBase.endsWith("/api/v1") && cleanPath.startsWith("/api/v1")) {
      const basePrefix = envBase.slice(0, -"/api/v1".length);
      return `${basePrefix}${cleanPath}`;
    }
    if (envBase.endsWith("/api") && cleanPath.startsWith("/api/")) {
      const basePrefix = envBase.slice(0, -"/api".length);
      return `${basePrefix}${cleanPath}`;
    }
    return `${envBase}${cleanPath}`;
  }

  // Fall back to relative API route which Next.js rewrites to the backend
  if (cleanPath.startsWith("/api/")) {
    return cleanPath;
  }
  return `/api/v1${cleanPath}`;
}

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  plan: "FREE" | "PRO" | "ENTERPRISE" | "TRIAL";
  onboarding_complete: boolean;
  team_id?: string;
  team_role?: string;
  org_role?: string;
  organization_id?: string;
  is_admin?: boolean;
  is_trial?: boolean;
  trial_status?: string;
  trial_expires_at?: string;
  redirect_url?: string;
  permissions?: string[];
}

interface AuthContextValue {
  user:     AuthUser | null;
  /** Always null: tokens live exclusively in HttpOnly cookies (Wave 6). Kept for API compatibility. */
  token:    string | null;
  loading:  boolean;
  sessionExpired: boolean;
  login:    (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout:   () => void;
  authHeader: () => Record<string, string>;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
  can:      (permission: string) => boolean;
  refreshSession: (force?: boolean) => Promise<AuthUser | null>;
  dismissReAuth: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

let refreshPromise: Promise<boolean> | null = null;
let mePromise: Promise<AuthUser | null> | null = null;
let cachedUser: AuthUser | null = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 10000; // 10s session cache prevents repeated navigation hits

/** Wave 6: purge any legacy token material left in web storage by older builds. */
function purgeLegacyStorage() {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem("sl_token");
    localStorage.removeItem("sl_refresh_token");
    localStorage.removeItem("sl_user");
    sessionStorage.removeItem("sl_token");
    sessionStorage.removeItem("sl_refresh_token");
  } catch {}
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const didInitRef = useRef(false);

  const fetchMe = useCallback(async (force = false): Promise<AuthUser | null> => {
    if (!force && cachedUser && Date.now() - lastFetchTime < CACHE_TTL_MS) {
      return cachedUser;
    }
    if (mePromise) {
      return mePromise;
    }

    mePromise = (async () => {
      try {
        // Cookie-only auth: the HttpOnly sl_token cookie is sent automatically.
        const res = await fetch(resolveApiUrl("/auth/me"), {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          const userObj: AuthUser = { ...data, plan: data.plan ?? "FREE" };
          cachedUser = userObj;
          lastFetchTime = Date.now();
          setUser(userObj);
          return userObj;
        } else {
          cachedUser = null;
          setUser(null);
          return null;
        }
      } catch (err) {
        console.warn("Auth check failed (network/offline):", err);
        return cachedUser;
      } finally {
        mePromise = null;
      }
    })();

    return mePromise;
  }, []);

  // Restore session from cookies on mount (once) and purge legacy localStorage tokens
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;
    purgeLegacyStorage();
    fetchMe(false).finally(() => setLoading(false));
  }, [fetchMe]);

  const login = useCallback(async (email: string, password: string): Promise<AuthUser> => {
    const res = await fetch(resolveApiUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }
    // Server sets HttpOnly sl_token / sl_refresh_token cookies; the token in the
    // JSON body is intentionally NOT stored anywhere client-side.
    const data = await res.json();
    const userObj: AuthUser = {
      user_id: data.user_id,
      email: data.email,
      name: data.name,
      plan: data.plan ?? "FREE",
      onboarding_complete: data.onboarding_complete ?? true,
      is_trial: data.is_trial ?? (data.plan === "TRIAL"),
      trial_status: data.trial_status,
      trial_expires_at: data.trial_expires_at,
      redirect_url: data.redirect_url,
    };
    cachedUser = userObj;
    lastFetchTime = Date.now();
    setUser(userObj);
    setSessionExpired(false);
    return userObj;
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const res = await fetch(resolveApiUrl("/auth/register"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Registration failed");
    }
    // Cookies set by server; hydrate the profile via /auth/me.
    cachedUser = null;
    setSessionExpired(false);
    await fetchMe(true);
  }, [fetchMe]);

  const logout = useCallback(async () => {
    cachedUser = null;
    lastFetchTime = 0;
    setSessionExpired(false);
    try {
      await fetch(resolveApiUrl("/auth/clear-cookie"), { method: "POST", credentials: "include" });
    } catch {
      // ignore network errors on logout
    }
    setUser(null);
    purgeLegacyStorage();
  }, []);

  const getCsrfToken = useCallback((): string => {
    if (typeof document === "undefined") return "";
    const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
    return match ? match[2] : "";
  }, []);

  const authHeader = useCallback((): Record<string, string> => {
    // Cookie-only auth: no Authorization bearer. The session cookie travels with
    // credentials: "include"; only the CSRF double-submit header is needed.
    return { "X-CSRF-Token": getCsrfToken() };
  }, [getCsrfToken]);

  const can = useCallback((permission: string): boolean => {
    if (!user) return false;
    if (user.is_admin) return true;
    const orgRole = user.org_role?.toUpperCase();
    if (orgRole === "ORG_ADMIN" || orgRole === "OWNER") return true;
    const teamRole = user.team_role?.toUpperCase();
    if (teamRole === "OWNER" || teamRole === "ADMIN" || teamRole === "CHIEF_ENGINEER" || teamRole === "LEAD_ENGINEER" || teamRole === "LEAD") {
      if (permission === "setup:approve") return true;
    }
    return user.permissions?.includes(permission) ?? false;
  }, [user]);

  /** Attempt a cookie-based session refresh; resolves true when the session was renewed. */
  const tryRefresh = useCallback((): Promise<boolean> => {
    if (!refreshPromise) {
      refreshPromise = fetch(resolveApiUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      }).then(async refreshRes => {
        // Rotated cookies are set by the server on success.
        return refreshRes.ok;
      }).catch(err => {
        console.error("Token refresh request failed:", err);
        return false;
      }).finally(() => {
        refreshPromise = null;
      });
    }
    return refreshPromise;
  }, []);

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    const fullUrl = resolveApiUrl(url);
    const headers = { "X-CSRF-Token": getCsrfToken(), ...options.headers };

    // Prevent recursive refresh loops on authentication endpoints
    const isAuthRoute = fullUrl.includes("/auth/login") || fullUrl.includes("/auth/refresh") || fullUrl.includes("/auth/clear-cookie");

    const res = await fetch(fullUrl, { ...options, credentials: "include", headers });
    if (res.status === 401 && !isAuthRoute) {
      const refreshed = await tryRefresh();
      if (refreshed) {
        return fetch(fullUrl, { ...options, credentials: "include", headers });
      }
      // Refresh failed: the session is gone. Open the re-auth gate instead of a
      // hard logout so in-progress page state (unsaved inputs) stays mounted.
      setSessionExpired(true);
    }
    return res;
  }, [tryRefresh, getCsrfToken]);

  // apiFetch callers (lib/api.ts) signal an unrecoverable 401 via a window event so
  // they open the same re-auth modal as fetchWithAuth callers.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onExpired = () => setSessionExpired(true);
    window.addEventListener("sl:session-expired", onExpired);
    return () => window.removeEventListener("sl:session-expired", onExpired);
  }, []);

  const dismissReAuth = useCallback(() => {
    // User chose to browse signed-out areas; clear the stale profile locally.
    cachedUser = null;
    lastFetchTime = 0;
    setUser(null);
    setSessionExpired(false);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token: null, loading, sessionExpired, login, register, logout, authHeader, fetchWithAuth, can, refreshSession: fetchMe, dismissReAuth }}>
      {children}
      {sessionExpired && <ReAuthModal />}
    </AuthContext.Provider>
  );
}

/**
 * Wave 6: clean re-auth gate. Rendered alongside (not instead of) the page tree,
 * so unsaved workspace inputs stay mounted while the user signs back in.
 */
function ReAuthModal() {
  const { user, login, logout } = useAuth();
  const [password, setPassword] = useState("");
  const [typedEmail, setTypedEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // When the profile has no email (e.g. the session is already gone), the field
  // must be editable so the user is never trapped in a read-only blank modal.
  const emailLocked = Boolean(user?.email);
  const emailValue = emailLocked ? (user?.email as string) : typedEmail;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailValue.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await login(emailValue.trim(), password);
      // login() clears sessionExpired; page state below the modal is preserved.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Session expired"
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.6)", display: "flex",
        alignItems: "center", justifyContent: "center",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          background: "#111827", color: "#e5e7eb", borderRadius: 12,
          padding: 24, width: 360, maxWidth: "90vw",
          boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        }}
      >
        <h2 style={{ margin: "0 0 8px", fontSize: 18 }}>Session expired</h2>
        <p style={{ margin: "0 0 16px", fontSize: 14, color: "#9ca3af" }}>
          Your work is still here. Re-enter your password to continue where you left off.
        </p>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          <span style={{ display: "block", marginBottom: 4 }}>Email</span>
          <input
            id="reauth-email"
            type="email"
            value={emailValue}
            readOnly={emailLocked}
            onChange={(ev) => setTypedEmail(ev.target.value)}
            autoComplete="username"
            style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #374151", background: "#1f2937", color: emailLocked ? "#9ca3af" : "#e5e7eb" }}
          />
        </label>
        <label style={{ display: "block", fontSize: 13, marginBottom: 12 }}>
          <span style={{ display: "block", marginBottom: 4 }}>Password</span>
          <input
            id="reauth-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            required
            style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #374151", background: "#1f2937", color: "#e5e7eb" }}
          />
        </label>
        {error && <p role="alert" style={{ color: "#f87171", fontSize: 13, margin: "0 0 12px" }}>{error}</p>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => logout()}
            style={{ padding: "8px 14px", borderRadius: 6, border: "1px solid #374151", background: "transparent", color: "#9ca3af", cursor: "pointer" }}
          >
            Sign out
          </button>
          <button
            type="submit"
            disabled={busy || !password}
            style={{ padding: "8px 14px", borderRadius: 6, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", opacity: busy ? 0.6 : 1 }}
          >
            {busy ? "Signing in..." : "Continue"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Returns true if the user has at least the required plan. */
export function usePlanGate(required: "FREE" | "PRO" | "ENTERPRISE"): boolean {
  const { user } = useAuth();
  const userLevel = getUserPlanLevel(user);
  return userLevel >= (PLAN_LEVELS[required] ?? 0);
}
