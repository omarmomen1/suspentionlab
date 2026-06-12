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
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [token,   setToken]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = async (tok: string) => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${tok}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ ...data, plan: data.plan ?? "FREE" });
      } else {
        // Token invalid or expired — clear session
        localStorage.removeItem("sl_token");
        setToken(null);
        setUser(null);
      }
    } catch {
      // Network error — keep token, user may be offline
    }
  };

  // Restore session from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("sl_token");
    if (stored) {
      setToken(stored);
      fetchMe(stored).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }
    const data = await res.json();
    localStorage.setItem("sl_token", data.token);
    document.cookie = "sl_authed=1; path=/; SameSite=Lax";
    setToken(data.token);
    setUser({ user_id: data.user_id, email: data.email, name: data.name, plan: data.plan, onboarding_complete: data.onboarding_complete });
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Registration failed");
    }
    const data = await res.json();
    localStorage.setItem("sl_token", data.token);
    document.cookie = "sl_authed=1; path=/; SameSite=Lax";
    setToken(data.token);
    setUser({ user_id: data.user_id, email: data.email, name: data.name, plan: data.plan, onboarding_complete: data.onboarding_complete });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("sl_token");
    // Remove the middleware cookie
    document.cookie = "sl_authed=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    setToken(null);
    setUser(null);
  }, []);

  // Returns headers for authenticated API requests
  const authHeader = useCallback((): Record<string, string> => {
    if (token) return { Authorization: `Bearer ${token}` };
    return {};
  }, [token]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, authHeader }}>
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
