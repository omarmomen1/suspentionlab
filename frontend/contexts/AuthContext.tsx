"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  plan: "FREE" | "PRO" | "ENTERPRISE";
  onboarding_complete: boolean;
}

interface AuthContextValue {
  user:     AuthUser | null;
  token:    string | null;
  loading:  boolean;
  login:    (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout:   () => void;
  authHeader: () => Record<string, string>;
  fetchWithAuth: (url: string, options?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

let refreshPromise: Promise<string | null> | null = null;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [token,   setToken]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        credentials: "include"
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ ...data, plan: data.plan ?? "FREE" });
      } else {
        setToken(null);
        setUser(null);
      }
    } catch (err) {
      console.warn("Auth check failed (network/offline):", err);
    }
  };

  // Restore session from cookie on mount
  useEffect(() => {
    setTimeout(() => fetchMe().finally(() => setLoading(false)), 0);
  }, []);  

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
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
    setUser({ user_id: data.user_id, email: data.email, name: data.name, plan: data.plan, onboarding_complete: data.onboarding_complete });
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
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
    setUser({ user_id: data.user_id, email: data.email, name: data.name, plan: data.plan, onboarding_complete: data.onboarding_complete });
  }, []);

  const logout = useCallback(async () => {
    // Remove the HttpOnly cookies by telling backend
    await fetch(`${API_BASE}/auth/clear-cookie`, { method: "POST", credentials: "include" });
    setToken(null);
    setUser(null);
  }, []);

  const getCsrfToken = useCallback((): string => {
    if (typeof document === "undefined") return "";
    const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
    return match ? match[2] : "";
  }, []);

  const authHeader = useCallback((): Record<string, string> => {
    return { "X-CSRF-Token": getCsrfToken() };
  }, [getCsrfToken]);

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    const headers = { "X-CSRF-Token": getCsrfToken(), ...options.headers };
    const res = await fetch(url, { ...options, credentials: "include", headers });
    if (res.status === 401) {
        if (!refreshPromise) {
            refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({}),
            }).then(async refreshRes => {
                if (refreshRes.ok) {
                    const { token: newToken } = await refreshRes.json();
                    return newToken as string;
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
            return fetch(url, { ...options, credentials: "include", headers });
        } else {
            logout();
        }
    }
    return res;
  }, [logout]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, authHeader, fetchWithAuth }}>
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
  const levels = { FREE: 0, PRO: 1, ENTERPRISE: 2 };
  const userLevel = levels[user?.plan ?? "FREE"] ?? 0;
  return userLevel >= (levels[required] ?? 0);
}
