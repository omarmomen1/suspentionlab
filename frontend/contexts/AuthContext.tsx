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
  token:    string | null;
  loading:  boolean;
  login:    (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout:   () => void;
  authHeader: () => Record<string, string>;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
  can:      (permission: string) => boolean;
  refreshSession: (force?: boolean) => Promise<AuthUser | null>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

let refreshPromise: Promise<string | null> | null = null;
let mePromise: Promise<AuthUser | null> | null = null;
let cachedUser: AuthUser | null = null;
let lastFetchTime = 0;
const CACHE_TTL_MS = 10000; // 10s session cache prevents repeated navigation hits

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [token,   setToken]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;
  const didInitRef = useRef(false);

  const fetchMe = useCallback(async (force = false, overrideToken?: string): Promise<AuthUser | null> => {
    if (!force && cachedUser && Date.now() - lastFetchTime < CACHE_TTL_MS) {
      return cachedUser;
    }
    if (mePromise) {
      return mePromise;
    }

    mePromise = (async () => {
      try {
        const headers: Record<string, string> = {};
        const activeToken = overrideToken || tokenRef.current;
        if (activeToken) {
          headers["Authorization"] = `Bearer ${activeToken}`;
        }
        const res = await fetch(resolveApiUrl("/auth/me"), {
          credentials: "include",
          headers,
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
          setToken(null);
          setUser(null);
          if (typeof window !== "undefined") {
            try {
              localStorage.removeItem("sl_token");
              localStorage.removeItem("sl_refresh_token");
              localStorage.removeItem("sl_user");
            } catch {}
          }
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

  // Restore session from localStorage or cookie on mount (once)
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;
    let savedToken: string | null = null;
    if (typeof window !== "undefined") {
      try {
        savedToken = localStorage.getItem("sl_token");
        const savedUserStr = localStorage.getItem("sl_user");
        if (savedToken) {
          setToken(savedToken);
          tokenRef.current = savedToken;
        }
        if (savedUserStr) {
          const parsed = JSON.parse(savedUserStr);
          setUser(parsed);
          cachedUser = parsed;
        }
      } catch {}
    }
    fetchMe(false, savedToken || undefined).finally(() => setLoading(false));
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
    const data = await res.json();
    setToken(data.token);
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
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("sl_token", data.token);
        if (data.refresh_token) {
          localStorage.setItem("sl_refresh_token", data.refresh_token);
        }
        localStorage.setItem("sl_user", JSON.stringify(userObj));
      } catch {}
    }
    cachedUser = userObj;
    lastFetchTime = Date.now();
    setUser(userObj);
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
    const data = await res.json();
    setToken(data.token);
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("sl_token", data.token);
        if (data.refresh_token) {
          localStorage.setItem("sl_refresh_token", data.refresh_token);
        }
      } catch {}
    }
    cachedUser = null;
    await fetchMe(true, data.token);
  }, [fetchMe]);

  const logout = useCallback(async () => {
    cachedUser = null;
    lastFetchTime = 0;
    try {
      await fetch(resolveApiUrl("/auth/clear-cookie"), { method: "POST", credentials: "include" });
    } catch {
      // ignore network errors on logout
    }
    setToken(null);
    setUser(null);
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem("sl_token");
        localStorage.removeItem("sl_refresh_token");
        localStorage.removeItem("sl_user");
      } catch {}
    }
  }, []);

  const getCsrfToken = useCallback((): string => {
    if (typeof document === "undefined") return "";
    const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
    return match ? match[2] : "";
  }, []);

  const authHeader = useCallback((): Record<string, string> => {
    const headers: Record<string, string> = { "X-CSRF-Token": getCsrfToken() };
    const activeToken = token || tokenRef.current || (typeof window !== "undefined" ? localStorage.getItem("sl_token") : null);
    if (activeToken) {
      headers["Authorization"] = `Bearer ${activeToken}`;
    }
    return headers;
  }, [getCsrfToken, token]);

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

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    const fullUrl = resolveApiUrl(url);
    const authHeaders: Record<string, string> = { "X-CSRF-Token": getCsrfToken() };
    const activeToken = token || tokenRef.current || (typeof window !== "undefined" ? localStorage.getItem("sl_token") : null);
    if (activeToken) {
      authHeaders["Authorization"] = `Bearer ${activeToken}`;
    }
    const headers = { ...authHeaders, ...options.headers };
    
    // Prevent recursive refresh loops on authentication endpoints
    const isAuthRoute = fullUrl.includes("/auth/login") || fullUrl.includes("/auth/refresh") || fullUrl.includes("/auth/clear-cookie");

    const res = await fetch(fullUrl, { ...options, credentials: "include", headers });
    if (res.status === 401 && !isAuthRoute) {
        const storedRefreshToken =
          typeof window !== "undefined"
            ? (localStorage.getItem("sl_refresh_token") || "").trim()
            : "";

        if (!storedRefreshToken) {
            logout();
            return res;
        }

        if (!refreshPromise) {
            refreshPromise = fetch(resolveApiUrl("/auth/refresh"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ refresh_token: storedRefreshToken }),
            }).then(async refreshRes => {
                if (refreshRes.ok) {
                    const data = await refreshRes.json();
                    if (typeof window !== "undefined") {
                      try {
                        if (data.token) localStorage.setItem("sl_token", data.token);
                        if (data.refresh_token) localStorage.setItem("sl_refresh_token", data.refresh_token);
                      } catch {}
                    }
                    return (data.token as string) || null;
                }
                return null;
            }).catch(err => {
                console.error("Token refresh request failed:", err);
                return null;
            }).finally(() => {
                refreshPromise = null;
            });
        }
        
        const newToken = await refreshPromise;
        if (newToken) {
            setToken(newToken);
            return fetch(fullUrl, { ...options, credentials: "include", headers: { ...headers, Authorization: `Bearer ${newToken}` } });
        } else {
            logout();
        }
    }
    return res;
  }, [logout, getCsrfToken]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, authHeader, fetchWithAuth, can, refreshSession: fetchMe }}>
      {children}
    </AuthContext.Provider>
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
